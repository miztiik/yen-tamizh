import { test, expect, type Page } from "@playwright/test";

import { DEFAULT_LABELS } from "../src/games/anagram/logic";

// Row 12 browser smoke: the FIRST PLAYABLE Game, driven end to end inside the
// real runtime (CLAUDE.md section 12). It proves the win path, keyboard play,
// the hint cost, and the state round-trip through a real reload - all against
// the production bundle, with a clean console.
//
// The target "\u0BA4\u0BAE\u0BBF\u0BB4\u0BCD" (tamizh) is 3 ezhuthu; the last is
// a mei cluster (zh + pulli) that must arrive as ONE tile.
const TARGET = ["\u0BA4", "\u0BAE\u0BBF", "\u0BB4\u0BCD"];
const HARNESS = "/?harness=anagram";

// The harness's second fixture is a real served anagram PAIR: the answer
// "\u0B85\u0BA4\u0BBF\u0B95" (adhiga) and the OTHER word the same tiles spell,
// "\u0B85\u0B95\u0BA4\u0BBF" (agadhi), which the payload carries in alsoValid.
const PAIRED_HARNESS = `${HARNESS}&fixture=also-valid`;
const ALTERNATIVE = ["\u0B85", "\u0B95", "\u0BA4\u0BBF"];

/** Click the tray tile carrying this ezhuthu. */
async function placeEzhuthu(page: Page, ezhuthu: string): Promise<void> {
  await page.getByTestId("anagram-tile").filter({ hasText: ezhuthu }).first().click();
}

/** The event names the runtime recorded (the prod debugging ring buffer). */
async function emittedEvents(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const dump = (window as unknown as { __yt_dump?: () => { name: string }[] }).__yt_dump;
    return dump ? dump().map((e) => e.name) : [];
  });
}

test("anagram: keyboard play, a hint that survives reload, and a win", async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedResponses: string[] = [];

  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => pageErrors.push(err.message));
  page.on("response", (res) => {
    if (res.status() >= 400) failedResponses.push(`${res.status()} ${res.url()}`);
  });

  await page.goto(HARNESS, { waitUntil: "load" });

  // The Game mounted into the shell's stage with one tile per ezhuthu.
  await expect(page.getByTestId("anagram-game")).toBeVisible();
  await expect(page.getByTestId("anagram-tile")).toHaveCount(TARGET.length);
  await expect(page.getByTestId("anagram-slot")).toHaveCount(TARGET.length);
  expect(await emittedEvents(page)).toContain("puzzle.started");

  // The mei cluster is ONE tile, never split into zh + pulli.
  await expect(page.getByTestId("anagram-tile").filter({ hasText: "\u0BB4\u0BCD" })).toHaveCount(1);

  // Keyboard play: Tab walks the shell chrome and reaches a tray tile with a
  // visible focus ring, and Enter places it (v2 a11y - every interactive
  // surface is keyboard reachable and labelled).
  let focused: { testid: string | null; label: string | null; outlineStyle: string } | null = null;
  for (let i = 0; i < 6 && focused?.testid !== "anagram-tile"; i += 1) {
    await page.keyboard.press("Tab");
    focused = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      if (el === null) return null;
      return {
        testid: el.getAttribute("data-testid"),
        label: el.getAttribute("aria-label"),
        outlineStyle: getComputedStyle(el).outlineStyle,
      };
    });
  }
  expect(focused?.testid).toBe("anagram-tile");
  expect(focused?.label).toBeTruthy();
  expect(focused?.outlineStyle).not.toBe("none");

  await page.keyboard.press("Enter");
  await expect(page.getByTestId("anagram-tile")).toHaveCount(TARGET.length - 1);
  // Focus stays inside the puzzle, so play continues without another Tab.
  expect(
    await page.evaluate(() => document.activeElement?.getAttribute("data-testid")),
  ).toBe("anagram-tile");
  // Escape returns every placed tile to the tray (the pure clear action).
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("anagram-tile")).toHaveCount(TARGET.length);

  // A hint is honest and free of charge - it costs the brag (score), not money.
  await page.getByTestId("anagram-hint").click();
  await expect(page.getByTestId("anagram-hint-list")).toBeVisible();
  expect(await emittedEvents(page)).toContain("puzzle.hint.used");

  // STATE ROUND-TRIP: the runner persisted the revealed hint; a full reload
  // rebuilds the Game and restoreState() puts it back exactly.
  await page.reload({ waitUntil: "load" });
  await expect(page.getByTestId("anagram-game")).toBeVisible();
  await expect(page.getByTestId("anagram-hint-list")).toBeVisible();
  await expect(page.getByTestId("anagram-hint-list").locator("li")).toHaveCount(1);

  // WIN PATH: place every tile in the target order - the last one auto-submits.
  for (const ezhuthu of TARGET) await placeEzhuthu(page, ezhuthu);

  await expect(page.getByTestId("anagram-feedback")).toContainText("\u0B9A\u0BB0\u0BBF");
  // 3 ezhuthu * 10 base points, minus the 2-point hint that was taken.
  await expect(page.getByTestId("anagram-feedback")).toContainText("28");

  // The Game reported completion, so the runner advanced and ended the session.
  await expect(page.getByTestId("session-summary")).toBeVisible();
  await expect(page.getByTestId("session-summary")).toContainText("28 points");

  const events = await emittedEvents(page);
  expect(events).toContain("puzzle.attempt.submitted");
  expect(events).toContain("puzzle.completed");
  expect(events).toContain("mode.session.completed");

  expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
  expect(pageErrors, `page errors: ${pageErrors.join(" | ")}`).toEqual([]);
  expect(failedResponses, `failed responses: ${failedResponses.join(" | ")}`).toEqual([]);
});

test("anagram: a wrong arrangement shakes and spends one attempt", async ({ page }) => {
  await page.goto(HARNESS, { waitUntil: "load" });
  await expect(page.getByTestId("anagram-game")).toBeVisible();
  await expect(page.getByTestId("anagram-attempts")).toContainText("3");

  // Place the target in reverse - a full, wrong arrangement auto-submits.
  for (const ezhuthu of [...TARGET].reverse()) await placeEzhuthu(page, ezhuthu);

  await expect(page.getByTestId("anagram-attempts")).toContainText("2");
  // The board is handed back so the player can immediately try again.
  await expect(page.getByTestId("anagram-tile")).toHaveCount(TARGET.length);
  await expect(page.getByTestId("anagram-feedback")).toContainText("\u0BA4\u0BB5\u0BB1\u0BC1");
  await expect(page.getByTestId("session-summary")).toHaveCount(0);
});

// Row 14's THIRD STATE: an arrangement that is a real served word is told so
// rather than flatly rejected. It is driven from the harness fixture, not from
// the committed bank: only 1.6% of served words have a partner at all, so
// whether any baked day offers one is a draw that every re-bake re-rolls.
test("anagram: an arrangement that is a real word is answered, not rejected", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

  await page.goto(PAIRED_HARNESS, { waitUntil: "load" });
  await expect(page.getByTestId("anagram-game")).toBeVisible();
  await expect(page.getByTestId("anagram-attempts")).toContainText("3");

  // The same tiles, arranged into the OTHER word they spell - a full
  // arrangement, so it auto-submits like any other.
  for (const ezhuthu of ALTERNATIVE) await placeEzhuthu(page, ezhuthu);

  const feedback = page.getByTestId("anagram-feedback");
  await expect(feedback).toContainText(DEFAULT_LABELS.alsoValid);
  const tone = await page.evaluate(() => {
    const span = document.querySelector('[data-testid="anagram-feedback"] span');
    return {
      classes: span?.className ?? "",
      glyphs: document.querySelectorAll('[data-testid="anagram-feedback"] svg').length,
    };
  });
  // A flip reads as reappraisal where a shake reads as rejection, and the check
  // glyph stays success's exclusive mark.
  expect(tone.classes).toContain("anim-flip");
  expect(tone.classes).toContain("text-warning");
  expect(tone.glyphs).toBe(0);
  // It cost an attempt like any other miss - the honesty is in the wording.
  await expect(page.getByTestId("anagram-attempts")).toContainText("2");
  // And it persists until the next placement, like the wrong message.
  await expect(feedback).toContainText(DEFAULT_LABELS.alsoValid);

  expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
});
