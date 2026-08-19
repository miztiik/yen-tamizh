import { test, expect, type Page } from "@playwright/test";

import {
  BASE_KEYS,
  DEFAULT_LABELS,
  MATRA,
  PULLI,
  baseOf,
  compose,
} from "../src/games/wordle/logic";

// Row 19 browser smoke: the THIRD Game, driven end to end inside the real
// runtime (CLAUDE.md section 12). It proves the composer keyboard, per-position
// marking over EZHUTHU, the accumulated key state, the hint cost, the state
// round-trip through a real reload, a win, and a board that runs out of
// attempts - all against the production bundle, with a clean console.
//
// The answer is "\u0BAE\u0BC7\u0BB1\u0BCD\u0B95\u0BCB\u0BB3\u0BCD\u0B95\u0BB3\u0BCD"
// (meeRkooLkaL, quotations): six ezhuthu holding the mei \u0BB3\u0BCD twice and
// the two-part matra \u0B95\u0BCB, so a run that types it has exercised every
// shape the composer can make.
const HARNESS = "/?harness=wordle";
const SHORT_HARNESS = `${HARNESS}&fixture=short`;

const ANSWER = [
  "\u0BAE\u0BC7", // mee
  "\u0BB1\u0BCD", // tr (mei)
  "\u0B95\u0BCB", // koo - two-part matra
  "\u0BB3\u0BCD", // L (mei)
  "\u0B95", // ka
  "\u0BB3\u0BCD", // L (mei)
];

// kaa | y | ka | tri | ka | L (kaaykaRikaL, vegetables): a real opening word
// that lands the duplicate case - one ka correct, the other absent.
const OPENER = [
  "\u0B95\u0BBE",
  "\u0BAF\u0BCD",
  "\u0B95",
  "\u0BB1\u0BBF",
  "\u0B95",
  "\u0BB3\u0BCD",
];

const BASES = new Set(BASE_KEYS);
const SIGNS = new Set<string>([PULLI, ...MATRA]);

/** Press the keys that compose one ezhuthu - one tap, or a base plus a form. */
async function typeEzhuthu(page: Page, ezhuthu: string): Promise<void> {
  if (BASES.has(ezhuthu)) {
    await page.locator(`[data-testid="wordle-key"][data-ezhuthu="${ezhuthu}"]`).click();
    return;
  }
  const base = baseOf(ezhuthu);
  expect(base, `${ezhuthu} has no composable base`).not.toBeNull();
  const sign = ezhuthu.slice(base?.length ?? 0);
  expect(SIGNS.has(sign), `${ezhuthu} is not base + one vowel form`).toBe(true);
  expect(compose(base ?? "", sign)).toBe(ezhuthu);
  await page.locator(`[data-testid="wordle-key"][data-ezhuthu="${base}"]`).click();
  const form = sign === PULLI ? "pulli" : sign;
  await page.locator(`[data-testid="wordle-form-key"][data-form="${form}"]`).click();
}

/** Compose a whole row and submit it. */
async function playRow(page: Page, row: string[]): Promise<void> {
  for (const ezhuthu of row) await typeEzhuthu(page, ezhuthu);
  await page.getByTestId("wordle-submit").click();
}

/** The marks on the most recently submitted row, left to right. */
async function lastRowMarks(page: Page): Promise<(string | null)[]> {
  return page.evaluate(() => {
    const rows = [...document.querySelectorAll('[data-testid="wordle-row"][data-submitted]')];
    const last = rows[rows.length - 1];
    if (last === undefined) return [];
    return [...last.querySelectorAll('[data-testid="wordle-cell"]')].map((cell) =>
      cell.getAttribute("data-mark"),
    );
  });
}

/** The event names the runtime recorded (the prod debugging ring buffer). */
async function emittedEvents(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const dump = (window as unknown as { __yt_dump?: () => { name: string }[] }).__yt_dump;
    return dump ? dump().map((e) => e.name) : [];
  });
}

test("wordle: compose, mark per ezhuthu, keep a hint through a reload, and win", async ({
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

  // The Game mounted into the shell's stage: an eight-row board six cells wide,
  // and a composer rather than 247 keys.
  await expect(page.getByTestId("wordle-game")).toBeVisible();
  await expect(page.getByTestId("wordle-row")).toHaveCount(8);
  await expect(page.getByTestId("wordle-cell")).toHaveCount(48);
  await expect(page.getByTestId("wordle-key")).toHaveCount(31);
  await expect(page.getByTestId("wordle-form-key")).toHaveCount(13);
  expect(await emittedEvents(page)).toContain("puzzle.started");

  // Keyboard play: Tab reaches a composer key with a visible focus ring, and
  // Enter presses it (v2 a11y - every interactive surface is keyboard reachable
  // and labelled). Done first, from the top of the document, so the walk is not
  // starting from wherever a previous click left focus.
  let focused: { testid: string | null; label: string | null; outlineStyle: string } | null = null;
  for (let i = 0; i < 20 && focused?.testid !== "wordle-key"; i += 1) {
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
  expect(focused?.testid).toBe("wordle-key");
  expect(focused?.label).toBeTruthy();
  expect(focused?.outlineStyle).not.toBe("none");
  await page.keyboard.press("Enter");
  await expect(page.locator('[data-draft-cell="true"]').first()).not.toBeEmpty();

  // A short row is refused WITHOUT spending an attempt, and leaves the board
  // exactly as it was - this Game never charges for a guess nobody finished.
  // The submit key stays ENABLED for it: a dead key teaches nothing, so the
  // refusal comes with a reason.
  await expect(page.getByTestId("wordle-submit")).toBeEnabled();
  await expect(page.getByTestId("wordle-submit")).toHaveAttribute("data-ready", "false");
  await page.getByTestId("wordle-submit").click();
  await expect(page.getByTestId("wordle-feedback")).toContainText(DEFAULT_LABELS.incomplete);
  await expect(page.getByTestId("wordle-attempts")).toContainText("8");
  await expect(page.locator('[data-testid="wordle-row"][data-submitted]')).toHaveCount(0);
  await page.getByTestId("wordle-erase").click();
  await expect(page.locator('[data-draft-cell="true"]').first()).toBeEmpty();

  // A real opening word. It plays ka twice against an answer holding one, so
  // the duplicate rule is visible on the board: one correct, one absent.
  await playRow(page, OPENER);
  expect(await lastRowMarks(page)).toEqual([
    "absent",
    "absent",
    "absent",
    "absent",
    "correct",
    "correct",
  ]);
  await expect(page.getByTestId("wordle-attempts")).toContainText("7");

  // The keyboard carries what the row taught, per EZHUTHU: ka is correct, kaa is
  // absent, and koo - which shares the base ka - is still unknown.
  const keyMarks = await page.evaluate(() => {
    const read = (ezhuthu: string): string | null => {
      const key = document.querySelector(`[data-testid="wordle-key"][data-ezhuthu="${ezhuthu}"]`);
      return key === null ? null : key.className;
    };
    return { ka: read("\u0B95"), la: read("\u0BB3") };
  });
  expect(keyMarks.ka).toContain("bg-tile-correct");
  // The L key commits the UYIRMEI La, which the answer does not hold at all, so
  // it stays unmarked even though the mei L is correct twice.
  expect(keyMarks.la).not.toContain("bg-tile-correct");

  // A hint is honest and free of charge - it costs the brag (score), not money.
  await page.getByTestId("wordle-hint").click();
  await expect(page.getByTestId("wordle-hint-list")).toBeVisible();
  expect(await emittedEvents(page)).toContain("puzzle.hint.used");

  // STATE ROUND-TRIP: the runner persisted the submitted row and the revealed
  // hint; a full reload rebuilds the Game and restoreState() puts both back.
  await page.reload({ waitUntil: "load" });
  await expect(page.getByTestId("wordle-game")).toBeVisible();
  await expect(page.getByTestId("wordle-hint-list").locator("li")).toHaveCount(1);
  await expect(page.getByTestId("wordle-attempts")).toContainText("7");
  expect(await lastRowMarks(page)).toHaveLength(6);

  // WIN PATH: compose the answer one ezhuthu at a time. Four of the six need a
  // vowel form, so this drives the composer's second half as well as its first.
  await playRow(page, ANSWER);
  expect(await lastRowMarks(page)).toEqual(Array.from({ length: 6 }, () => "correct"));
  // Six ezhuthu at the shared 10 a letter, less the 3-point meaning rung.
  await expect(page.getByTestId("wordle-feedback")).toContainText("57");

  // The Game reported completion, so the runner advanced and ended the session.
  await expect(page.getByTestId("session-summary")).toBeVisible();
  await expect(page.getByTestId("session-summary")).toContainText("57 points");

  const events = await emittedEvents(page);
  expect(events).toContain("puzzle.attempt.submitted");
  expect(events).toContain("puzzle.completed");
  expect(events).toContain("mode.session.completed");

  expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
  expect(pageErrors, `page errors: ${pageErrors.join(" | ")}`).toEqual([]);
  expect(failedResponses, `failed responses: ${failedResponses.join(" | ")}`).toEqual([]);
});

test("wordle: a board that runs out of attempts ends honestly and shows the answer", async ({
  page,
}) => {
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(`pageerror: ${err.message}`));

  await page.goto(SHORT_HARNESS, { waitUntil: "load" });
  await expect(page.getByTestId("wordle-game")).toBeVisible();
  await expect(page.getByTestId("wordle-attempts")).toContainText("2");

  // A row of one repeated ezhuthu is not a Tamil word and is accepted anyway:
  // this Game ships no accept list, so it can never tell a player that a real
  // word is not a word. It spends an attempt like any other guess.
  const nonsense = Array.from({ length: 6 }, () => "\u0BAA");
  await playRow(page, nonsense);
  await expect(page.getByTestId("wordle-attempts")).toContainText("1");
  expect(await lastRowMarks(page)).toEqual(Array.from({ length: 6 }, () => "absent"));

  await playRow(page, nonsense);
  // The answer is shown rather than withheld: the puzzle is over, and a word the
  // player never learns is a round that taught nothing (Palm).
  const feedback = page.getByTestId("wordle-feedback");
  await expect(feedback).toContainText(ANSWER.join(""));
  await expect(page.getByTestId("wordle-attempts")).toHaveCount(0);
  // The keyboard is dead, so a finished board cannot be typed into.
  await expect(page.getByTestId("wordle-submit")).toBeDisabled();

  // The loss is reported after the beat, which is what lets the runner advance
  // and end the session - a lost puzzle still finishes the day.
  await expect(page.getByTestId("session-summary")).toBeVisible();
  const events = await emittedEvents(page);
  expect(events).toContain("puzzle.abandoned");

  expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
});
