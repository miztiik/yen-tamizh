import { test, expect, type Page } from "@playwright/test";

import { DEFAULT_LABELS } from "../src/games/missing-letters/logic";

// Row 18 browser smoke: the SECOND Game, driven end to end inside the real
// runtime (CLAUDE.md section 12). It proves the win path, keyboard play, the
// hint cost, and the state round-trip through a real reload - all against the
// production bundle, with a clean console.
//
// The solo target is "\u0B9A\u0BBF\u0BB1\u0BC1\u0B95\u0BA4\u0BC8" (sirukathai,
// a short story): four ezhuthu with the second hidden. The missing one is
// "\u0BB1\u0BC1", a uyirmei that must arrive as ONE tile.
const HARNESS = "/?harness=missing-letters";
const ANSWER = "\u0BB1\u0BC1";

// The third-state fixture: the mask "\u0B87 _ \u0B9F\u0BCD\u0B9F\u0BC8" is
// answered by two served words, and the bank holds both fillers.
const PAIRED_HARNESS = `${HARNESS}&fixture=also-valid`;
const OTHER_FILLER = "\u0BB0\u0BBE";

/** Click the bank tile carrying this ezhuthu. */
async function pick(page: Page, ezhuthu: string): Promise<void> {
  await page.getByTestId("missing-letters-choice").filter({ hasText: ezhuthu }).first().click();
}

/** The event names the runtime recorded (the prod debugging ring buffer). */
async function emittedEvents(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const dump = (window as unknown as { __yt_dump?: () => { name: string }[] }).__yt_dump;
    return dump ? dump().map((e) => e.name) : [];
  });
}

test("missing letters: keyboard play, a hint that survives reload, and a win", async ({
  page,
}) => {
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

  // The Game mounted into the shell's stage: four cells, one of them a hole.
  await expect(page.getByTestId("missing-letters-game")).toBeVisible();
  await expect(page.getByTestId("missing-letters-shown")).toHaveCount(3);
  await expect(page.getByTestId("missing-letters-blank")).toHaveCount(1);
  await expect(page.getByTestId("missing-letters-choice")).toHaveCount(8);
  expect(await emittedEvents(page)).toContain("puzzle.started");

  // The hidden ezhuthu is ONE tile in the bank, never split into its parts.
  await expect(
    page.getByTestId("missing-letters-choice").filter({ hasText: ANSWER }),
  ).toHaveCount(1);

  // Keyboard play: Tab walks the shell chrome and reaches a bank tile with a
  // visible focus ring, and Enter places it (v2 a11y - every interactive
  // surface is keyboard reachable and labelled).
  let focused: { testid: string | null; label: string | null; outlineStyle: string } | null = null;
  for (let i = 0; i < 8 && focused?.testid !== "missing-letters-choice"; i += 1) {
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
  expect(focused?.testid).toBe("missing-letters-choice");
  expect(focused?.label).toBeTruthy();
  expect(focused?.outlineStyle).not.toBe("none");

  // Enter fills the hole from the keyboard alone. The first bank tile is not
  // the answer, so the board auto-submits, spends an attempt and comes straight
  // back - and focus stays inside the puzzle, so play continues without Tab.
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("missing-letters-attempts")).toContainText("2");
  await expect(page.getByTestId("missing-letters-choice")).toHaveCount(8);
  await expect(page.getByTestId("missing-letters-feedback")).toContainText(
    DEFAULT_LABELS.wrong,
  );
  expect(
    await page.evaluate(() => document.activeElement?.getAttribute("data-testid")),
  ).toBe("missing-letters-choice");

  // A hint is honest and free of charge - it costs the brag (score), not money.
  await page.getByTestId("missing-letters-hint").click();
  await expect(page.getByTestId("missing-letters-hint-list")).toBeVisible();
  expect(await emittedEvents(page)).toContain("puzzle.hint.used");

  // STATE ROUND-TRIP: the runner persisted the spent attempt and the revealed
  // hint; a full reload rebuilds the Game and restoreState() puts both back.
  await page.reload({ waitUntil: "load" });
  await expect(page.getByTestId("missing-letters-game")).toBeVisible();
  await expect(page.getByTestId("missing-letters-hint-list").locator("li")).toHaveCount(1);
  await expect(page.getByTestId("missing-letters-attempts")).toContainText("2");

  // WIN PATH: the last hole fills and the board auto-submits.
  await pick(page, ANSWER);
  await expect(page.getByTestId("missing-letters-feedback")).toContainText(
    DEFAULT_LABELS.correct,
  );
  // One blank * 20 base points, minus the 1-point category rung that was taken.
  await expect(page.getByTestId("missing-letters-feedback")).toContainText("19");

  // The Game reported completion, so the runner advanced and ended the session.
  await expect(page.getByTestId("session-summary")).toBeVisible();
  await expect(page.getByTestId("session-summary")).toContainText("19 points");

  const events = await emittedEvents(page);
  expect(events).toContain("puzzle.attempt.submitted");
  expect(events).toContain("puzzle.completed");
  expect(events).toContain("mode.session.completed");

  expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
  expect(pageErrors, `page errors: ${pageErrors.join(" | ")}`).toEqual([]);
  expect(failedResponses, `failed responses: ${failedResponses.join(" | ")}`).toEqual([]);
});

// The THIRD STATE: a filled hole that spells a real served word is told so
// rather than flatly rejected. It is driven from the harness fixture, not from
// the committed bank: the generator prefers a mask no other served word fits,
// so an ambiguous one is a 2 percent case that every re-bake re-rolls.
test("missing letters: a fill that is a real word is answered, not rejected", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

  await page.goto(PAIRED_HARNESS, { waitUntil: "load" });
  await expect(page.getByTestId("missing-letters-game")).toBeVisible();
  await expect(page.getByTestId("missing-letters-attempts")).toContainText("3");

  // The other ezhuthu the same mask accepts - a full board, so it auto-submits.
  await pick(page, OTHER_FILLER);

  const feedback = page.getByTestId("missing-letters-feedback");
  await expect(feedback).toContainText(DEFAULT_LABELS.alsoValid);
  const tone = await page.evaluate(() => {
    const span = document.querySelector('[data-testid="missing-letters-feedback"] span');
    return {
      classes: span?.className ?? "",
      glyphs: document.querySelectorAll('[data-testid="missing-letters-feedback"] svg').length,
    };
  });
  // A flip reads as reappraisal where a shake reads as rejection, and the check
  // glyph stays success's exclusive mark.
  expect(tone.classes).toContain("anim-flip");
  expect(tone.classes).toContain("text-warning");
  expect(tone.glyphs).toBe(0);
  // It cost an attempt like any other miss - the honesty is in the wording.
  await expect(page.getByTestId("missing-letters-attempts")).toContainText("2");

  expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
});
