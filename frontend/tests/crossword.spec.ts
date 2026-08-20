import { test, expect, type Page } from "@playwright/test";

// Row 21 browser smoke: the FIFTH Game, driven end to end inside the real
// runtime (CLAUDE.md section 12). It proves the board can be navigated by
// keyboard, that the composer writes a whole ezhuthu in two taps, that a letter
// written into a crossing square belongs to BOTH answers at once, that a reveal
// costs exactly the answer it hands over, and that writing every answer wins -
// all against the production bundle, with a clean console.
//
// The harness board is a real generated one (see CrosswordHarness.svelte): the
// easy band's mask, four five-ezhuthu answers crossing at four squares. The
// answers are driven by their COMPOSER KEYS rather than by their text, because
// what this spec is checking is the input method: a Tamil grid that needed an
// IME would be unplayable on the phone this repo is built for.
const HARNESS = "/?harness=crossword";

/** One tap on a base key, and optionally one on a form key to re-spell it. */
type Key = { base: string; form?: number };

// The thirteen form keys are [pulli, a, aa, i, ii, u, uu, e, ee, ai, o, oo, au],
// so index 1 writes nothing and never needs a tap - the base key alone already
// wrote that shape.
const DOWN_1 = {
  number: 1,
  direction: "down",
  word: "\u0b95\u0bc8\u0b9a\u0bcd\u0b9a\u0bc6\u0bb2\u0bb5\u0bc1",
  start: { row: 0, col: 1 },
  keys: [
    { base: "\u0b95", form: 9 },
    { base: "\u0b9a", form: 0 },
    { base: "\u0b9a", form: 7 },
    { base: "\u0bb2" },
    { base: "\u0bb5", form: 5 },
  ] as Key[],
};

const ACROSS_3 = {
  number: 3,
  direction: "across",
  word: "\u0ba4\u0bc0\u0b9a\u0bcd\u0b9a\u0bc1\u0b9f\u0bb0\u0bcd",
  start: { row: 1, col: 0 },
  keys: [
    { base: "\u0ba4", form: 4 },
    { base: "\u0b9a", form: 0 },
    { base: "\u0b9a", form: 5 },
    { base: "\u0b9f" },
    { base: "\u0bb0", form: 0 },
  ] as Key[],
};

const ACROSS_4 = {
  number: 4,
  direction: "across",
  word: "\u0bae\u0bb2\u0b95\u0bcd\u0b95\u0bae\u0bcd",
  start: { row: 3, col: 0 },
  keys: [
    { base: "\u0bae" },
    { base: "\u0bb2" },
    { base: "\u0b95", form: 0 },
    { base: "\u0b95" },
    { base: "\u0bae", form: 0 },
  ] as Key[],
};

const DOWN_2 = {
  number: 2,
  direction: "down",
  word: "\u0ba4\u0bca\u0b9f\u0b95\u0bcd\u0b95\u0bae\u0bcd",
  start: { row: 0, col: 3 },
  keys: [
    { base: "\u0ba4", form: 10 },
    { base: "\u0b9f" },
    { base: "\u0b95", form: 0 },
    { base: "\u0b95" },
    { base: "\u0bae", form: 0 },
  ] as Key[],
};

type Answer = typeof DOWN_1;

/** Put the caret on one square by tapping it. */
async function tapCell(page: Page, cell: { row: number; col: number }): Promise<void> {
  await page
    .locator(`[data-testid="crossword-cell"][data-r="${cell.row}"][data-c="${cell.col}"]`)
    .click();
}

/** Write one answer with the composer, one base tap plus at most one form tap. */
async function writeAnswer(page: Page, answer: Answer): Promise<void> {
  await tapCell(page, answer.start);
  for (const key of answer.keys) {
    await page.locator(`[data-testid="crossword-key"][data-key="${key.base}"]`).click();
    if (key.form !== undefined) {
      await page.locator(`[data-testid="crossword-form"][data-form="${key.form}"]`).click();
    }
  }
}

/** Whether the clue list shows one answer as settled. */
async function isDone(page: Page, answer: Answer): Promise<boolean> {
  return page
    .locator(
      `[data-testid="crossword-clue"][data-number="${answer.number}"]` +
        `[data-direction="${answer.direction}"]`,
    )
    .evaluate((li) => li.getAttribute("data-done") === "true");
}

/** What one square is showing, with its printed number stripped off. */
async function letterAt(page: Page, row: number, col: number): Promise<string> {
  return page
    .locator(`[data-testid="crossword-cell"][data-r="${row}"][data-c="${col}"]`)
    .evaluate((cell) => {
      const clone = cell.cloneNode(true) as HTMLElement;
      clone.querySelectorAll("span").forEach((span) => span.remove());
      return (clone.textContent ?? "").trim();
    });
}

/** Which square the caret is on. */
async function caret(page: Page): Promise<{ row: number; col: number } | null> {
  return page.evaluate(() => {
    const cell = document.querySelector('[data-testid="crossword-cell"][data-caret="true"]');
    if (cell === null) return null;
    return {
      row: Number(cell.getAttribute("data-r")),
      col: Number(cell.getAttribute("data-c")),
    };
  });
}

/** The event names the runtime recorded (the prod debugging ring buffer). */
async function emittedEvents(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const dump = (window as unknown as { __yt_dump?: () => { name: string }[] }).__yt_dump;
    return dump ? dump().map((e) => e.name) : [];
  });
}

test("crossword: navigate by keyboard, compose every answer, and win", async ({ page }) => {
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

  // The Game mounted into the shell's stage: a 5x5 mask is 16 open squares and
  // 9 blocked ones, with four clues and nothing settled yet.
  await expect(page.getByTestId("crossword-game")).toBeVisible();
  await expect(page.getByTestId("crossword-cell")).toHaveCount(16);
  await expect(page.getByTestId("crossword-block")).toHaveCount(9);
  await expect(page.getByTestId("crossword-clue")).toHaveCount(4);
  await expect(page.getByTestId("crossword-remaining")).toContainText("4");
  expect(await emittedEvents(page)).toContain("puzzle.started");

  // The board fits the phone this repo is built for: 36px squares with a 4px
  // gutter, inside the 328px a 360px screen leaves after its margins.
  const gridBox = await page.getByTestId("crossword-grid").boundingBox();
  expect(gridBox).not.toBeNull();
  expect((gridBox as { width: number }).width).toBeLessThanOrEqual(328);

  // KEYBOARD: the caret is a real focus stop with a visible ring, and arrows
  // move it. A crossword that could only be played by tapping would fail this
  // repo's keyboard bar.
  const focus = await page.evaluate(() => {
    const cell = document.querySelector<HTMLElement>(
      '[data-testid="crossword-cell"][tabindex="0"]',
    );
    cell?.focus();
    const active = document.activeElement as HTMLElement | null;
    return {
      testid: active?.getAttribute("data-testid") ?? null,
      outline: active === null ? "" : getComputedStyle(active).outlineStyle,
    };
  });
  expect(focus.testid).toBe("crossword-cell");
  expect(focus.outline).not.toBe("none");

  // The caret opens on the first square in reading order, and arrowing DOWN the
  // column it starts on walks the answer running through it.
  expect(await caret(page)).toEqual({ row: 0, col: 1 });
  await page.keyboard.press("ArrowDown");
  expect(await caret(page)).toEqual({ row: 1, col: 1 });
  // Arrowing sideways jumps the blocked squares rather than stopping at them,
  // and moving along a row also says which of the two answers is being written.
  await page.keyboard.press("ArrowRight");
  expect(await caret(page)).toEqual({ row: 1, col: 2 });

  // COMPOSER: one base tap plus at most one form tap writes a whole ezhuthu, so
  // all 216 uyirmei are reachable without moving the caret back.
  await writeAnswer(page, DOWN_1);
  await expect.poll(() => isDone(page, DOWN_1)).toBe(true);
  await expect(page.getByTestId("crossword-remaining")).toContainText("3");
  // The crossing squares now belong to the two answers that share them: the
  // across answers have not been written and already have a letter each.
  expect(await letterAt(page, 1, 1)).toBe("\u0b9a\u0bcd");
  expect(await letterAt(page, 3, 1)).toBe("\u0bb2");
  expect(await isDone(page, ACROSS_3)).toBe(false);

  for (const answer of [ACROSS_3, ACROSS_4, DOWN_2]) {
    await writeAnswer(page, answer);
    await expect
      .poll(() => isDone(page, answer), { message: `${answer.word} not settled` })
      .toBe(true);
  }

  // Every answer written: the board completes and the session advances to its
  // summary with the whole board's score - 20 ezhuthu at 10 points each.
  await expect(page.getByTestId("session-summary")).toBeVisible({ timeout: 5_000 });
  await expect(page.getByTestId("session-summary")).toContainText("1/1");
  await expect(page.getByTestId("session-summary")).toContainText("200 points");

  const events = await emittedEvents(page);
  expect(events).toContain("puzzle.attempt.submitted");
  expect(events).toContain("puzzle.completed");
  // A board with no hint ladder never sells a rung, and nothing was abandoned.
  expect(events).not.toContain("puzzle.hint.used");
  expect(events).not.toContain("puzzle.abandoned");

  expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
  expect(pageErrors, `page errors: ${pageErrors.join(" | ")}`).toEqual([]);
  expect(failedResponses, `failed responses: ${failedResponses.join(" | ")}`).toEqual([]);
});

test("crossword: a reveal hands over one answer, and the rest still pay", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });

  await page.goto(HARNESS, { waitUntil: "load" });
  await expect(page.getByTestId("crossword-game")).toBeVisible();

  // The price rides the BUTTON, before the purchase: five ezhuthu, 50 points.
  await expect(page.getByTestId("crossword-reveal-cost")).toContainText("50");

  // Work one answer out, then hand the other three over. The board still
  // finishes - a player can never be trapped by one answer they cannot get -
  // and it pays for exactly what was worked out.
  await writeAnswer(page, DOWN_1);
  await expect.poll(() => isDone(page, DOWN_1)).toBe(true);

  for (let i = 0; i < 3; i += 1) {
    await page.getByTestId("crossword-reveal").click();
  }

  await expect(page.getByTestId("session-summary")).toBeVisible({ timeout: 5_000 });
  // 5 of the 20 ezhuthu were worked out: 50 of 200 points.
  await expect(page.getByTestId("session-summary")).toContainText("50 points");

  const events = await emittedEvents(page);
  expect(events).toContain("puzzle.hint.used");
  expect(events).toContain("puzzle.completed");
  expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
});
