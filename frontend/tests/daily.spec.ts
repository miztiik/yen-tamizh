import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { test, expect, type Page } from "@playwright/test";

import { segment } from "../src/tamil/ezhuthu";

// THE headline e2e for Row 13: FIRST LOAD TO PLAYABLE. A player opens the app,
// lands on the Home, taps the one live Mode, plays today's real baked puzzles to
// a win, and sees their streak - against the production bundle, with a clean
// console (CLAUDE.md sections 12 + 13).
//
// The clock is FIXED so the test asks for a day the committed bank actually
// holds, whatever date the CI runner believes it is; the app itself reads the
// real local date. Midday UTC so no timezone shifts the calendar day.
const PLAY_DAY = "2026-08-13";
const FIXED_NOW = new Date(`${PLAY_DAY}T12:00:00Z`);

const here = dirname(fileURLToPath(import.meta.url));
const bankDir = resolve(here, "../public/bank");

interface BankItem {
  gameId: string;
  payload: {
    word: string;
    tiles: string[];
    meaning?: string;
    translationEn?: string;
    hints?: { kind: string; text: string; cost: number }[];
  };
}

const day = JSON.parse(
  readFileSync(resolve(bankDir, PLAY_DAY.slice(0, 4), `${PLAY_DAY}.json`), "utf-8"),
) as { date: string; items: BankItem[] };

// Row 14's ladder, on an ANAGRAM-only day. Every day the Daily bakes now holds
// three different Games, so the one board whose three-rung ladder this covers
// appears at most once a day - and this test plays a whole day through the
// anagram's own controls. A published day from before the mix is therefore the
// right fixture: it is three anagrams, it is frozen (the re-bake guard leaves
// published days alone), and it was baked from the rebuilt ladder.
//
// The THIRD STATE - "that is a word, but not today's" - is deliberately NOT
// tested here. Only 1.6% of served words have a partner at all, so whether any
// committed day offers one is a draw that every re-bake re-rolls; it is proven
// against the harness fixture instead (tests/anagram.spec.ts).
const LADDER_DAY = "2026-08-19";
const ladderDay = JSON.parse(
  readFileSync(resolve(bankDir, LADDER_DAY.slice(0, 4), `${LADDER_DAY}.json`), "utf-8"),
) as { date: string; items: BankItem[] };

// A day from the two rings: three DIFFERENT Games, and one of the themed days
// the wider ring had to be built not to kill.
const MIXED_DAY = "2026-08-21";
const THEMED_DAY = "2026-08-23";
const readDay = (date: string) =>
  JSON.parse(
    readFileSync(resolve(bankDir, date.slice(0, 4), `${date}.json`), "utf-8"),
  ) as { date: string; theme?: string; items: { gameId: string }[] };

/** Click the tray tile carrying exactly this ezhuthu (never a prefix of one). */
async function placeEzhuthu(page: Page, ezhuthu: string): Promise<void> {
  const clicked = await page.evaluate((target) => {
    const tiles = Array.from(
      document.querySelectorAll<HTMLButtonElement>('[data-testid="anagram-tile"]'),
    );
    const tile = tiles.find((button) => button.textContent?.trim() === target);
    tile?.click();
    return tile !== undefined;
  }, ezhuthu);
  expect(clicked, `no tray tile carries "${ezhuthu}"`).toBe(true);
}

/** Solve the mounted puzzle by placing its ezhuthu in the answer's order. */
async function solve(page: Page, item: BankItem): Promise<void> {
  await expect(page.getByTestId("anagram-game")).toBeVisible();
  // Wait for THIS item's tray: the runner only advances after the previous
  // puzzle's win celebration, so the stage still shows the solved one for a
  // beat. Matching the tile multiset is what proves the new Game has mounted.
  const expected = [...item.payload.tiles].sort().join("|");
  await expect
    .poll(
      async () =>
        (await page.getByTestId("anagram-tile").allInnerTexts())
          .map((text) => text.trim())
          .sort()
          .join("|"),
      { timeout: 15_000 },
    )
    .toBe(expected);
  for (const ezhuthu of segment(item.payload.word)) await placeEzhuthu(page, ezhuthu);
}

function watchConsole(page: Page): { errors: string[]; failures: string[] } {
  const errors: string[] = [];
  const failures: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  page.on("response", (res) => {
    if (res.status() >= 400) failures.push(`${res.status()} ${res.url()}`);
  });
  return { errors, failures };
}

test("first load to playable: Home -> Daily -> a won day -> a streak", async ({ page }) => {
  const watched = watchConsole(page);
  await page.clock.setFixedTime(FIXED_NOW);

  // 1. LANDING. The Home is the default route - no harness, no query string.
  await page.goto("/", { waitUntil: "load" });
  await expect(page.getByTestId("app-shell")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("yen-tamizh");

  // The live Modes are real buttons; the rest are honestly marked, not
  // disabled controls that invite a tap and then punish it. Since Row 23 turned
  // the Time Trial on there is no "rest" left - all four Modes ship - and the
  // Daily is still the first card.
  await expect(page.getByTestId("mode-card")).toHaveCount(4);
  await expect(page.getByTestId("mode-card").first()).toHaveAttribute("data-mode", "daily");
  await expect(page.getByTestId("mode-card-locked")).toHaveCount(0);

  // Keyboard reachability with a visible focus ring (v2 a11y).
  await page.keyboard.press("Tab");
  const focus = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    return el === null
      ? null
      : {
          testid: el.getAttribute("data-testid"),
          label: el.getAttribute("aria-label"),
          outlineStyle: getComputedStyle(el).outlineStyle,
        };
  });
  expect(focus?.testid).toBe("mode-card");
  expect(focus?.label).toBeTruthy();
  expect(focus?.outlineStyle).not.toBe("none");

  // 2. ONE TAP TO PLAYING.
  await page.getByTestId("mode-card").first().click();
  await expect(page.getByTestId("session-stage")).toBeVisible();
  await expect(page.getByTestId("anagram-game")).toBeVisible();
  expect(new URL(page.url()).searchParams.get("mode")).toBe("daily");

  // 3. PLAY THE WHOLE DAY. Every item is a real baked puzzle from the bank.
  expect(day.items.length).toBeGreaterThan(0);
  for (const item of day.items) {
    await solve(page, item);
    await expect(page.getByTestId("anagram-feedback")).toBeVisible();
  }

  // 4. THE WIN MOMENT: a summary with a score and a streak that just started.
  await expect(page.getByTestId("session-summary")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("summary-streak")).toHaveText("1");
  const score = Number(await page.getByTestId("summary-score").innerText());
  expect(score).toBeGreaterThan(0);

  const events = await page.evaluate(() => {
    const dump = (window as unknown as { __yt_dump?: () => { name: string }[] }).__yt_dump;
    return dump ? dump().map((event) => event.name) : [];
  });
  expect(events).toContain("mode.session.started");
  expect(events).toContain("puzzle.completed");
  expect(events).toContain("mode.session.completed");
  expect(events).toContain("streak.updated");

  // 5. THE STREAK TICKS ONCE PER DAY. Reloading a finished day replays the
  //    summary but must not inflate the run.
  await page.reload({ waitUntil: "load" });
  await expect(page.getByTestId("session-summary")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("summary-streak")).toHaveText("1");

  // 6. BACK HOME, where the run is now on show.
  await page.getByTestId("summary-home").click();
  await expect(page.getByTestId("app-shell")).toBeVisible();
  await expect(page.getByTestId("home-streak")).toContainText("1");

  expect(watched.errors, `console errors: ${watched.errors.join(" | ")}`).toEqual([]);
  expect(watched.failures, `failed responses: ${watched.failures.join(" | ")}`).toEqual([]);
});

// The mix, end to end: a day is three different Games and the shell says which
// one the player is looking at. Without that name, item 2 is simply a different
// board with no explanation - five Games in one session reading as five apps.
test("a mixed day is three different Games, and the rail names the one on screen", async ({
  page,
}) => {
  const watched = watchConsole(page);
  const mixed = readDay(MIXED_DAY);
  const games = mixed.items.map((item) => item.gameId);
  expect(new Set(games).size, `${MIXED_DAY} repeats a Game`).toBe(games.length);
  expect(mixed.theme).toBeUndefined();

  await page.clock.setFixedTime(new Date(`${MIXED_DAY}T12:00:00Z`));
  await page.goto("/?mode=daily", { waitUntil: "load" });

  await expect(page.getByTestId(`${games[0]}-game`)).toBeVisible();
  const name = page.getByTestId("daily-game-name");
  await expect(name).toBeVisible();
  await expect(name).not.toBeEmpty();
  // The name is copy, so it must never render its own slug back at the player.
  await expect(name).not.toHaveText(new RegExp(`^game-${games[0]}-title$`));
  // An ordinary day announces no theme.
  await expect(page.getByTestId("daily-theme")).toHaveCount(0);

  expect(watched.errors, `console errors: ${watched.errors.join(" | ")}`).toEqual([]);
  expect(watched.failures, `failed responses: ${watched.failures.join(" | ")}`).toEqual([]);
});

// The round header the generator has been paying for since Row 15: a themed day
// drops the category rung from every ladder it bakes BECAUSE the theme is
// announced free here, so an unannounced themed day is a rung given up for
// nothing.
test("a themed day announces its theme in the session rail", async ({ page }) => {
  const watched = watchConsole(page);
  const themed = readDay(THEMED_DAY);
  expect(themed.theme, `${THEMED_DAY} is not a themed day`).toBeTruthy();

  await page.clock.setFixedTime(new Date(`${THEMED_DAY}T12:00:00Z`));
  await page.goto("/?mode=daily", { waitUntil: "load" });
  await expect(page.getByTestId(`${themed.items[0]!.gameId}-game`)).toBeVisible();

  const banner = page.getByTestId("daily-theme");
  await expect(banner).toBeVisible();
  await expect(banner).not.toContainText(themed.theme as string);

  expect(watched.errors, `console errors: ${watched.errors.join(" | ")}`).toEqual([]);
  expect(watched.failures, `failed responses: ${watched.failures.join(" | ")}`).toEqual([]);
});

test("cross-route smoke: a deep link opens the session and Back returns Home", async ({
  page,
}) => {
  const watched = watchConsole(page);
  await page.clock.setFixedTime(FIXED_NOW);

  await page.goto("/", { waitUntil: "load" });
  await expect(page.getByTestId("home-modes")).toBeVisible();

  // A deep link boots straight into the session - the session is a real route,
  // not a state only reachable by tapping.
  await page.goto("/?mode=daily", { waitUntil: "load" });
  await expect(page.getByTestId("anagram-game")).toBeVisible();

  await page.goBack();
  await expect(page.getByTestId("app-shell")).toBeVisible();
  await expect(page.getByTestId("home-modes")).toBeVisible();

  expect(watched.errors, `console errors: ${watched.errors.join(" | ")}`).toEqual([]);
  expect(watched.failures, `failed responses: ${watched.failures.join(" | ")}`).toEqual([]);
});

test("a bank with no day for today is a sentence, not a blank screen", async ({ page }) => {
  const watched = watchConsole(page);
  // A player whose calendar sits BEFORE the first baked day: the bank is real,
  // but none of it is theirs yet. They must still get an explanation.
  await page.clock.setFixedTime(new Date("2000-01-01T12:00:00Z"));

  await page.goto("/?mode=daily", { waitUntil: "load" });
  await expect(page.getByTestId("daily-unavailable")).toBeVisible();
  await expect(page.getByTestId("daily-unavailable")).not.toBeEmpty();

  expect(watched.errors, `console errors: ${watched.errors.join(" | ")}`).toEqual([]);
});

// Row 14, end to end: the price is disclosed BEFORE the tap, and the summary
// teaches every word of the day - the one that was lost included.
test("the hint ladder discloses its price and the summary teaches", async ({ page }) => {
  const watched = watchConsole(page);
  await page.clock.setFixedTime(new Date(`${LADDER_DAY}T12:00:00Z`));
  await page.setViewportSize({ width: 360, height: 780 }); // a mid-tier Android

  await page.goto("/?mode=daily", { waitUntil: "load" });
  await expect(page.getByTestId("anagram-game")).toBeVisible();

  const [first, second, third] = ladderDay.items as [BankItem, BankItem, BankItem];
  const ladder = first.payload.hints ?? [];
  expect(ladder.length).toBeGreaterThan(1);

  // 1. THE PRICE RIDES THE BUTTON. Each rung's cost is on the control that buys
  //    it, so it is read before the tap, never after.
  const hintButton = page.getByTestId("anagram-hint");
  for (const rung of ladder) {
    await expect(page.getByTestId("anagram-hint-cost")).toHaveText(`-${rung.cost}`);
    await page.evaluate(() => {
      document.querySelector<HTMLButtonElement>('[data-testid="anagram-hint"]')?.click();
    });
    await expect(page.getByTestId("anagram-hint-list").locator("li")).toContainText([rung.text]);
  }
  // A spent ladder names itself and drops the badge - there is no price left.
  await expect(hintButton).toBeDisabled();
  await expect(page.getByTestId("anagram-hint-cost")).toHaveCount(0);
  // The revealed rung carries its TEXT only; the cost stayed on the button.
  await expect(page.getByTestId("anagram-hint-list")).not.toContainText(/-\d/);
  // A long meaning wraps instead of pushing the stage sideways.
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);

  // 2. PLAY THE DAY OUT: solve, LOSE one on purpose, solve.
  const feedback = page.getByTestId("anagram-feedback");
  for (const ezhuthu of segment(first.payload.word)) await placeEzhuthu(page, ezhuthu);
  await expect(feedback).toContainText("+");

  await expect
    .poll(async () => (await page.getByTestId("anagram-tile").allInnerTexts()).length, {
      timeout: 15_000,
    })
    .toBe(second.payload.tiles.length);
  const backwards = [...segment(second.payload.word)].reverse();
  for (let round = 0; round < 3; round += 1) {
    for (const ezhuthu of backwards) await placeEzhuthu(page, ezhuthu);
  }
  await expect(feedback).toContainText(second.payload.word); // out of attempts

  await solve(page, third);

  // 3. THE SUMMARY TEACHES. Every word of the day, in play order, the lost one
  //    with its meaning intact - hiding it would punish twice.
  await expect(page.getByTestId("session-summary")).toBeVisible({ timeout: 15_000 });
  const words = page.getByTestId("summary-word");
  await expect(words).toHaveCount(3);
  await expect(words.nth(0)).toContainText(first.payload.word);
  await expect(words.nth(1)).toHaveAttribute("data-solved", "false");
  await expect(words.nth(1)).toContainText(second.payload.meaning as string);
  await expect(words.nth(2)).toContainText(third.payload.meaning as string);
  // English is a demoted second line, never the meaning line, and never badged
  // with how the gloss was authored.
  await expect(words.nth(0).locator('[lang="en"]')).toHaveText(
    first.payload.translationEn as string,
  );
  await expect(page.getByTestId("session-summary")).not.toContainText("AI");
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);

  expect(watched.errors, `console errors: ${watched.errors.join(" | ")}`).toEqual([]);
  expect(watched.failures, `failed responses: ${watched.failures.join(" | ")}`).toEqual([]);
});
