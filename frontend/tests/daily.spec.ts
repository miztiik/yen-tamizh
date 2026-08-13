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
  payload: { word: string; tiles: string[] };
}

const day = JSON.parse(
  readFileSync(resolve(bankDir, PLAY_DAY.slice(0, 4), `${PLAY_DAY}.json`), "utf-8"),
) as { date: string; items: BankItem[] };

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

  // The one live Mode is a real button; the rest are honestly marked, not
  // disabled controls that invite a tap and then punish it.
  await expect(page.getByTestId("mode-card")).toHaveCount(1);
  await expect(page.getByTestId("mode-card")).toHaveAttribute("data-mode", "daily");
  await expect(page.getByTestId("mode-card-locked")).toHaveCount(3);

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
  await page.getByTestId("mode-card").click();
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
