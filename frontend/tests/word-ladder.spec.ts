import { test, expect, type Page } from "@playwright/test";

import { DEFAULT_LABELS } from "../src/games/word-ladder/logic";

// Row 16 browser smoke: the SIXTH Game, driven end to end inside the real
// runtime (CLAUDE.md section 12). It proves the climb, keyboard play, the
// +ezhuthu badge, the state round-trip through a real reload, the result card
// and its four stats - and that NO request leaves the page while that card is
// on screen, which is the whole share decision (Holy Law #1).
//
// The climb is the committed contract fixture:
// "\u0B92\u0BB0\u0BC1" (oru) -> "\u0B92\u0BB0\u0BC1\u0BAE\u0BC8" (orumai)
// -> "\u0B92\u0BB0\u0BC1\u0BAE\u0BC8\u0BAF" (orumaiya).
const HARNESS = "/?harness=word-ladder";

// The two additions the climb needs, in order.
const FIRST_STEP = "\u0BAE\u0BC8";
const SECOND_STEP = "\u0BAF";
// In the bank and a real served word from the first rung - just not this rung.
const ALSO_VALID = "\u0B95\u0BC8";
const ALSO_VALID_WORD = "\u0B92\u0BB0\u0BC1\u0B95\u0BC8";
// In the bank and spells nothing at all.
const MISS = "\u0B9A\u0BBF";

/** Click the bank tile carrying this ezhuthu. */
async function pick(page: Page, ezhuthu: string): Promise<void> {
  await page
    .getByTestId("word-ladder-choice")
    .filter({ hasText: new RegExp(`^${ezhuthu}$`) })
    .first()
    .click();
}

/** The event names the runtime recorded (the prod debugging ring buffer). */
async function emittedEvents(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const dump = (window as unknown as { __yt_dump?: () => { name: string }[] }).__yt_dump;
    return dump ? dump().map((e) => e.name) : [];
  });
}

test("word ladder: a climb, a reload mid-ladder, and a locally rendered card", async ({
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

  // The Game mounted into the shell's stage: three rungs with only the bottom
  // one printed, and one bank for the whole climb.
  await expect(page.getByTestId("word-ladder-game")).toBeVisible();
  await expect(page.getByTestId("word-ladder-rung")).toHaveCount(3);
  await expect(page.getByTestId("word-ladder-choice")).toHaveCount(8);
  await expect(page.getByTestId("word-ladder-progress")).toContainText("0/2");
  expect(await emittedEvents(page)).toContain("puzzle.started");

  // Nothing is badged yet: the badge is the record of a step already taken.
  await expect(page.getByTestId("word-ladder-badge")).toHaveCount(0);

  // Keyboard play: Tab walks the shell chrome and reaches a bank tile with a
  // visible focus ring, and Enter picks it (v2 a11y - every interactive
  // surface is keyboard reachable and labelled).
  let focused: { testid: string | null; label: string | null; outlineStyle: string } | null =
    null;
  for (let i = 0; i < 8 && focused?.testid !== "word-ladder-choice"; i += 1) {
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
  expect(focused?.testid).toBe("word-ladder-choice");
  expect(focused?.label).toBeTruthy();
  expect(focused?.outlineStyle).not.toBe("none");

  // A pick that spells NOTHING costs a message and nothing else - a ladder has
  // no attempt budget, so a wrong pick costs time rather than the climb.
  await pick(page, MISS);
  await expect(page.getByTestId("word-ladder-feedback")).toContainText(DEFAULT_LABELS.miss);
  await expect(page.getByTestId("word-ladder-choice")).toHaveCount(8);
  await expect(page.getByTestId("word-ladder-progress")).toContainText("0/2");

  // THE THIRD STATE: a pick that spells a REAL served word is told so, by name,
  // rather than flatly rejected.
  await pick(page, ALSO_VALID);
  await expect(page.getByTestId("word-ladder-feedback")).toContainText(ALSO_VALID_WORD);
  await expect(page.getByTestId("word-ladder-choice")).toHaveCount(8);

  // The first rung: the tile leaves the bank and the rung is badged with it.
  await pick(page, FIRST_STEP);
  await expect(page.getByTestId("word-ladder-progress")).toContainText("1/2");
  await expect(page.getByTestId("word-ladder-choice")).toHaveCount(7);
  await expect(page.getByTestId("word-ladder-badge")).toHaveCount(1);
  await expect(page.getByTestId("word-ladder-badge")).toContainText(FIRST_STEP);
  await expect(page.getByTestId("word-ladder-rungs")).toContainText(
    "\u0B92\u0BB0\u0BC1\u0BAE\u0BC8",
  );

  // STATE ROUND-TRIP: the runner persisted the climbed rung; a full reload
  // rebuilds the Game and restoreState() puts the player back on it.
  await page.reload({ waitUntil: "load" });
  await expect(page.getByTestId("word-ladder-game")).toBeVisible();
  await expect(page.getByTestId("word-ladder-progress")).toContainText("1/2");
  await expect(page.getByTestId("word-ladder-badge")).toHaveCount(1);
  await expect(page.getByTestId("word-ladder-choice")).toHaveCount(7);

  // From here on, every request is a share-decision violation.
  const requestsAfterWin: string[] = [];
  page.on("request", (req) => requestsAfterWin.push(`${req.method()} ${req.url()}`));

  // THE TOP: the last rung closes the climb and the card takes the stage.
  await pick(page, SECOND_STEP);
  await expect(page.getByTestId("word-ladder-card")).toBeVisible();
  await expect(page.getByTestId("word-ladder-badge")).toHaveCount(2);

  // The four completion stats, all of them derived from the emitted events.
  await expect(page.getByTestId("word-ladder-stat-time")).toBeVisible();
  // One rung fell on the first pick, one after two misses at the rung below.
  await expect(page.getByTestId("word-ladder-stat-instinct")).toContainText("/2");
  await expect(page.getByTestId("word-ladder-stat-retries")).toBeVisible();
  await expect(page.getByTestId("word-ladder-stat-streak")).toBeVisible();
  await expect(page.getByTestId("word-ladder-card-marks")).not.toBeEmpty();

  // Sharing is a LOCAL move: the card is already on the device.
  await page.getByTestId("word-ladder-share").click();
  expect(
    requestsAfterWin,
    `the result card made a request: ${requestsAfterWin.join(" | ")}`,
  ).toEqual([]);

  // The card is the gate: the runner only hears once the player taps through,
  // so the result cannot be swept off the screen before it is read.
  expect(await emittedEvents(page)).not.toContain("puzzle.completed");
  await page.getByTestId("word-ladder-continue").click();

  await expect(page.getByTestId("session-summary")).toBeVisible();
  await expect(page.getByTestId("session-summary")).toContainText("40 points");

  const events = await emittedEvents(page);
  expect(events).toContain("puzzle.attempt.submitted");
  expect(events).toContain("puzzle.completed");
  expect(events).toContain("mode.session.completed");

  expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
  expect(pageErrors, `page errors: ${pageErrors.join(" | ")}`).toEqual([]);
  expect(failedResponses, `failed responses: ${failedResponses.join(" | ")}`).toEqual([]);
});
