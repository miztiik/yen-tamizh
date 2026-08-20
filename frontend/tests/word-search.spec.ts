import { test, expect, type Page } from "@playwright/test";

// Row 20 browser smoke: the FOURTH Game, driven end to end inside the real
// runtime (CLAUDE.md section 12). It proves a trace by POINTER and a trace by
// KEYBOARD produce the same result, that a word placed backwards up a diagonal
// is found, that a word the grid spells but nobody asked for is answered rather
// than refused, that a reveal costs exactly the word it hands over, and that
// finding every word wins - all against the production bundle, with a clean
// console.
//
// The harness board is a real generated one (see WordSearchHarness.svelte). Its
// four words run in four different directions, which is why they are driven
// here by their recorded coordinates rather than by their text: what this spec
// is checking is the GESTURE, and a gesture is a pair of cells.
const HARNESS = "/?harness=word-search";

/** The four words, and the two cells whose line spells each one. */
const WORDS = [
  // thillumullu - down-left from (2,5) to (7,0). Traced by POINTER.
  {
    word: "\u0ba4\u0bbf\u0bb2\u0bcd\u0bb2\u0bc1\u0bae\u0bc1\u0bb2\u0bcd\u0bb2\u0bc1",
    from: { row: 2, col: 5 },
    to: { row: 7, col: 0 },
  },
  // malaiyamaan - up-right from (7,3) to (3,7). Traced BACKWARDS by pointer, so
  // the grid is read the other way and must still find it.
  {
    word: "\u0bae\u0bb2\u0bc8\u0baf\u0bae\u0bbe\u0ba9\u0bcd",
    from: { row: 3, col: 7 },
    to: { row: 7, col: 3 },
  },
  // aqkam - down-right from (2,0) to (5,3). Traced by KEYBOARD.
  {
    word: "\u0b85\u0b83\u0b95\u0bae\u0bcd",
    from: { row: 2, col: 0 },
    to: { row: 5, col: 3 },
  },
  // thirumaNa - right from (1,1) to (1,4). Traced by KEYBOARD.
  {
    word: "\u0ba4\u0bbf\u0bb0\u0bc1\u0bae\u0ba3",
    from: { row: 1, col: 1 },
    to: { row: 1, col: 4 },
  },
] as const;

// akamathi - a real Tamil word the filler happened to spell, at (7,1) running
// right over four cells. It is on `alsoValid`, so the board answers it instead
// of refusing it.
const UNASKED = {
  word: "\u0b85\u0b95\u0bae\u0ba4\u0bbf",
  from: { row: 7, col: 1 },
  to: { row: 7, col: 4 },
};

type Point = { row: number; col: number };

/** The centre of one grid cell, in page coordinates. */
async function centreOf(page: Page, cell: Point): Promise<{ x: number; y: number }> {
  const box = await page
    .locator(`[data-testid="word-search-cell"][data-r="${cell.row}"][data-c="${cell.col}"]`)
    .boundingBox();
  expect(box, `cell (${cell.row}, ${cell.col}) has no box`).not.toBeNull();
  const found = box as { x: number; y: number; width: number; height: number };
  return { x: found.x + found.width / 2, y: found.y + found.height / 2 };
}

/** Drag from one cell to another - the pointer half of the mechanic. */
async function dragTrace(page: Page, from: Point, to: Point): Promise<void> {
  const start = await centreOf(page, from);
  const end = await centreOf(page, to);
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  // A mid-point move so the drag really passes over the cells between the ends,
  // which is what a finger does and what `elementFromPoint` has to resolve.
  await page.mouse.move((start.x + end.x) / 2, (start.y + end.y) / 2, { steps: 4 });
  await page.mouse.move(end.x, end.y, { steps: 4 });
  await page.mouse.up();
}

/** Walk the cursor to a cell and trace to another - the keyboard half. */
async function keyTrace(page: Page, from: Point, to: Point): Promise<void> {
  await page.locator('[data-testid="word-search-cell"][tabindex="0"]').focus();
  const cursor = await page.evaluate(() => {
    const cell = document.querySelector('[data-testid="word-search-cell"][tabindex="0"]');
    return {
      row: Number(cell?.getAttribute("data-r")),
      col: Number(cell?.getAttribute("data-c")),
    };
  });
  const step = async (rows: number, cols: number): Promise<void> => {
    for (let i = 0; i < Math.abs(rows); i += 1) {
      await page.keyboard.press(rows > 0 ? "ArrowDown" : "ArrowUp");
    }
    for (let i = 0; i < Math.abs(cols); i += 1) {
      await page.keyboard.press(cols > 0 ? "ArrowRight" : "ArrowLeft");
    }
  };
  await step(from.row - cursor.row, from.col - cursor.col);
  await page.keyboard.press("Enter");
  await step(to.row - from.row, to.col - from.col);
  await page.keyboard.press("Enter");
}

/** Whether the word list shows this word as struck through. */
async function isStruck(page: Page, word: string): Promise<boolean> {
  return page
    .locator(`[data-testid="word-search-word"][data-word="${word}"]`)
    .evaluate((li) => li.getAttribute("data-found") === "true");
}

/** The event names the runtime recorded (the prod debugging ring buffer). */
async function emittedEvents(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const dump = (window as unknown as { __yt_dump?: () => { name: string }[] }).__yt_dump;
    return dump ? dump().map((e) => e.name) : [];
  });
}

test("word-search: trace by pointer and by keyboard, answer a stray word, and win", async ({
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

  // The Game mounted into the shell's stage: an 8x8 grid and a list of four
  // words, none of them struck through yet.
  await expect(page.getByTestId("word-search-game")).toBeVisible();
  await expect(page.getByTestId("word-search-cell")).toHaveCount(64);
  await expect(page.getByTestId("word-search-word")).toHaveCount(4);
  await expect(page.getByTestId("word-search-remaining")).toContainText("4");
  expect(await emittedEvents(page)).toContain("puzzle.started");

  // Eight columns is the phone measurement this Game was designed around, so it
  // is asserted rather than assumed: 36px cells with a 4px gutter make 316px,
  // inside the 328px a 360px screen leaves after its margins.
  const gridBox = await page.getByTestId("word-search-grid").boundingBox();
  expect(gridBox).not.toBeNull();
  expect((gridBox as { width: number }).width).toBeLessThanOrEqual(328);

  // A wrong trace costs nothing and says so - there is no attempt budget here.
  await dragTrace(page, { row: 0, col: 0 }, { row: 0, col: 3 });
  await expect(page.getByTestId("word-search-feedback")).not.toBeEmpty();
  await expect(page.getByTestId("word-search-remaining")).toContainText("4");

  // A real Tamil word the grid happens to spell is ANSWERED, not refused: it
  // does not join the list and it does not read as a mistake.
  await dragTrace(page, UNASKED.from, UNASKED.to);
  await expect(page.getByTestId("word-search-feedback")).toContainText(UNASKED.word);
  await expect(page.getByTestId("word-search-remaining")).toContainText("4");

  // POINTER: a diagonal running down-left, and one traced BACKWARDS up a
  // diagonal - both are found, because a trace is judged by what it spells.
  for (const entry of [WORDS[0], WORDS[1]]) {
    await dragTrace(page, entry.from, entry.to);
    await expect
      .poll(() => isStruck(page, entry.word), { message: `${entry.word} not struck` })
      .toBe(true);
  }
  await expect(page.getByTestId("word-search-remaining")).toContainText("2");
  // A found word explains itself, free, right where the player found it.
  await expect(page.getByTestId("word-search-meaning").first()).toBeVisible();

  // KEYBOARD: the same mechanic, driven entirely by arrows and Enter. A grid
  // that could only be played by dragging would fail this repo's keyboard bar.
  const focus = await page.evaluate(() => {
    const cell = document.querySelector<HTMLElement>(
      '[data-testid="word-search-cell"][tabindex="0"]',
    );
    cell?.focus();
    const active = document.activeElement as HTMLElement | null;
    return {
      testid: active?.getAttribute("data-testid") ?? null,
      outline: active === null ? "" : getComputedStyle(active).outlineStyle,
    };
  });
  expect(focus.testid).toBe("word-search-cell");
  expect(focus.outline).not.toBe("none");

  for (const entry of [WORDS[2], WORDS[3]]) {
    await keyTrace(page, entry.from, entry.to);
    await expect
      .poll(() => isStruck(page, entry.word), { message: `${entry.word} not struck` })
      .toBe(true);
  }

  // Every word found: the board completes and the session advances to its
  // summary with the whole board's score.
  await expect(page.getByTestId("session-summary")).toBeVisible({ timeout: 5_000 });
  await expect(page.getByTestId("session-summary")).toContainText("1/1");
  await expect(page.getByTestId("session-summary")).toContainText("190 points");

  const events = await emittedEvents(page);
  expect(events).toContain("puzzle.attempt.submitted");
  expect(events).toContain("puzzle.completed");
  // No event name outside the catalog, and nothing was abandoned.
  expect(events).not.toContain("puzzle.abandoned");

  expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
  expect(pageErrors, `page errors: ${pageErrors.join(" | ")}`).toEqual([]);
  expect(failedResponses, `failed responses: ${failedResponses.join(" | ")}`).toEqual([]);
});

test("word-search: a reveal hands over one word, and the rest still pay", async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });

  await page.goto(HARNESS, { waitUntil: "load" });
  await expect(page.getByTestId("word-search-game")).toBeVisible();

  // The price rides the button, before the purchase: this word is 6 ezhuthu.
  await expect(page.getByTestId("word-search-reveal-cost")).toContainText("60");

  // Trace one word, then hand the other three over. The board still finishes -
  // a player can never be trapped by a word they cannot see - and it pays for
  // exactly what was traced.
  await dragTrace(page, WORDS[3].from, WORDS[3].to);
  await expect.poll(() => isStruck(page, WORDS[3].word)).toBe(true);

  for (let i = 0; i < 3; i += 1) {
    await page.getByTestId("word-search-reveal").click();
  }

  await expect(page.getByTestId("session-summary")).toBeVisible({ timeout: 5_000 });
  // 4 of the 19 ezhuthu were traced: 40 of 190 points.
  await expect(page.getByTestId("session-summary")).toContainText("40 points");

  const events = await emittedEvents(page);
  expect(events).toContain("puzzle.hint.used");
  expect(events).toContain("puzzle.completed");

  expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
});
