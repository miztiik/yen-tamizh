import { describe, expect, it } from "vitest";

import { segment } from "../../tamil/ezhuthu";

import {
  DEFAULT_LABELS,
  DEFAULT_POINTS_PER_BLANK,
  attemptsRemaining,
  baseScore,
  buildChoices,
  cells,
  clearBlank,
  clearFilled,
  fillNextBlank,
  initialState,
  isAlsoValid,
  isFull,
  isSolved,
  keyToAction,
  nextHint,
  normalizeState,
  remainingChoices,
  resolveLabels,
  revealNextHint,
  revealedHints,
  scoreFor,
  spelledWord,
  submitAttempt,
  targetEzhuthu,
  undoLast,
  type MissingLettersPayload,
} from "./logic";

// "\u0BB5\u0BBE\u0BAF\u0BCD\u0BAA\u0BCD\u0BAA\u0BC1" (vaayppu) is FOUR ezhuthu -
// "\u0BB5\u0BBE" / "\u0BAF\u0BCD" / "\u0BAA\u0BCD" / "\u0BAA\u0BC1" - two of them
// mei clusters carrying a pulli. Escaped like datasets/fixtures/*, so the
// fixture's own normalization form cannot change what these tests assert.
const WORD = "\u0BB5\u0BBE\u0BAF\u0BCD\u0BAA\u0BCD\u0BAA\u0BC1";
const UNITS = ["\u0BB5\u0BBE", "\u0BAF\u0BCD", "\u0BAA\u0BCD", "\u0BAA\u0BC1"];

/** The bank: the two hideable ezhuthu these tests use, plus two decoys. The
 *  generated `choices` type is a minItems-2 tuple, so the literal is one too. */
const BANK: [string, string, ...string[]] = [
  "\u0BA4\u0BCD",
  "\u0BAF\u0BCD",
  "\u0BAA\u0BCD",
  "\u0B95\u0BCD",
];

function payload(overrides: Partial<MissingLettersPayload> = {}): MissingLettersPayload {
  return {
    word: WORD,
    blanks: [1],
    choices: BANK,
    attempts: 3,
    ...overrides,
  };
}

/** Play the choice carrying this ezhuthu into the next hole. */
function place(
  base: MissingLettersPayload,
  state: ReturnType<typeof initialState>,
  ezhuthu: string,
): ReturnType<typeof initialState> {
  const choices = buildChoices(base);
  const choice = choices.find((c) => c.ezhuthu === ezhuthu);
  expect(choice, `no choice carries ${ezhuthu}`).toBeDefined();
  return fillNextBlank(base, state, choice?.id ?? "");
}

describe("missing-letters: the board is read in ezhuthu", () => {
  it("segments the answer with the shared library, not by code point", () => {
    expect(targetEzhuthu(payload())).toEqual(UNITS);
    expect(segment(WORD)).toEqual(UNITS);
    // Four ezhuthu over eight code points is the whole point of the unit.
    expect(WORD.length).toBe(8);
  });

  it("draws one cell per ezhuthu, with the blanked position empty", () => {
    const base = payload();
    const board = cells(base, buildChoices(base), initialState());
    expect(board).toHaveLength(4);
    expect(board.map((c) => c.blankIndex)).toEqual([-1, 0, -1, -1]);
    expect(board.filter((c) => c.blankIndex === -1).map((c) => c.ezhuthu)).toEqual([
      UNITS[0],
      UNITS[2],
      UNITS[3],
    ]);
    expect(board[1]?.ezhuthu).toBe("");
  });

  it("hides whole clusters even when two positions are blanked", () => {
    const base = payload({ blanks: [1, 2] });
    const board = cells(base, buildChoices(base), initialState());
    expect(board.filter((c) => c.blankIndex !== -1).map((c) => c.index)).toEqual([1, 2]);
    // A pulli never floats free: the printed cells are complete clusters.
    for (const cell of board.filter((c) => c.blankIndex === -1)) {
      expect(segment(cell.ezhuthu)).toHaveLength(1);
    }
  });
});

describe("missing-letters: filling and taking back", () => {
  it("drops a choice into the next hole and takes it out of the bank", () => {
    const base = payload();
    const choices = buildChoices(base);
    const filled = place(base, initialState(), UNITS[1] ?? "");
    expect(filled.filledChoiceIds).toHaveLength(1);
    expect(remainingChoices(choices, filled)).toHaveLength(BANK.length - 1);
    expect(spelledWord(base, choices, filled)).toBe(WORD);
    expect(isFull(base, filled)).toBe(true);
  });

  it("fills holes left to right", () => {
    const base = payload({ blanks: [1, 2] });
    const choices = buildChoices(base);
    let state = place(base, initialState(), UNITS[1] ?? "");
    state = place(base, state, UNITS[2] ?? "");
    expect(spelledWord(base, choices, state)).toBe(WORD);
  });

  it("refuses to place the same choice twice, or to overfill", () => {
    const base = payload();
    const choices = buildChoices(base);
    const first = choices[0]?.id ?? "";
    const once = fillNextBlank(base, initialState(), first);
    expect(fillNextBlank(base, once, first)).toBe(once);
    expect(fillNextBlank(base, once, choices[1]?.id ?? "")).toBe(once);
  });

  it("takes one hole back, undoes the last, and clears them all", () => {
    const base = payload({ blanks: [1, 2] });
    let state = place(base, initialState(), UNITS[1] ?? "");
    state = place(base, state, UNITS[2] ?? "");
    expect(clearBlank(state, 0).filledChoiceIds).toHaveLength(1);
    expect(undoLast(state).filledChoiceIds).toHaveLength(1);
    expect(clearFilled(state).filledChoiceIds).toEqual([]);
    // Out-of-range and empty are no-ops rather than corruption.
    expect(clearBlank(state, 7)).toBe(state);
    expect(undoLast(initialState())).toEqual(initialState());
    expect(clearFilled(initialState())).toEqual(initialState());
  });
});

describe("missing-letters: submitting", () => {
  it("scores a win and finishes", () => {
    const base = payload();
    const choices = buildChoices(base);
    const filled = place(base, initialState(), UNITS[1] ?? "");
    expect(isSolved(base, choices, filled)).toBe(true);
    const outcome = submitAttempt(base, choices, filled);
    expect(outcome.correct).toBe(true);
    expect(outcome.attempt).toBe(WORD);
    expect(outcome.state.finished).toBe(true);
    expect(outcome.state.solved).toBe(true);
    expect(outcome.state.score).toBe(DEFAULT_POINTS_PER_BLANK);
  });

  it("spends an attempt on a miss and hands the board back", () => {
    const base = payload();
    const choices = buildChoices(base);
    const wrong = place(base, initialState(), BANK[0] ?? "");
    const outcome = submitAttempt(base, choices, wrong);
    expect(outcome.correct).toBe(false);
    expect(outcome.exhausted).toBe(false);
    expect(outcome.state.filledChoiceIds).toEqual([]);
    expect(attemptsRemaining(base, outcome.state)).toBe(2);
  });

  it("ends the puzzle when the last attempt is spent", () => {
    const base = payload({ attempts: 1 });
    const choices = buildChoices(base);
    const wrong = place(base, initialState(), BANK[0] ?? "");
    const outcome = submitAttempt(base, choices, wrong);
    expect(outcome.exhausted).toBe(true);
    expect(outcome.state.finished).toBe(true);
    expect(outcome.state.solved).toBe(false);
    expect(outcome.alternative).toBe(false);
  });

  it("answers a real served word instead of rejecting it (the third state)", () => {
    // A synthetic pair standing in for what the bake records when a mask admits
    // more than one served word: a player who spells one of the others and is
    // told "wrong" concludes the game cheated (schemas.md - recorded, not
    // required). Real pairs are measured in the backend suite, over the real set.
    const alternative = "\u0BA4\u0BBE\u0BAF\u0BCD\u0BAA\u0BCD\u0BAA\u0BC1";
    const base = payload({
      blanks: [0],
      choices: ["\u0BB5\u0BBE", "\u0BA4\u0BBE", "\u0B95\u0BBE"],
      alsoValid: [alternative],
    });
    const choices = buildChoices(base);
    const state = place(base, initialState(), "\u0BA4\u0BBE");
    expect(spelledWord(base, choices, state)).toBe(alternative);
    expect(isAlsoValid(base, choices, state)).toBe(true);
    const outcome = submitAttempt(base, choices, state);
    expect(outcome.correct).toBe(false);
    expect(outcome.alternative).toBe(true);
    // It costs an attempt like any other miss - the honesty is in the wording,
    // not in the accounting, or shuffling until a word appears is a free probe.
    expect(attemptsRemaining(base, outcome.state)).toBe(2);
  });

  it("says nothing about an alternative on the exhausting attempt", () => {
    const alternative = "\u0BA4\u0BBE\u0BAF\u0BCD\u0BAA\u0BCD\u0BAA\u0BC1";
    const base = payload({
      attempts: 1,
      blanks: [0],
      choices: ["\u0BB5\u0BBE", "\u0BA4\u0BBE", "\u0B95\u0BBE"],
      alsoValid: [alternative],
    });
    const choices = buildChoices(base);
    const state = place(base, initialState(), "\u0BA4\u0BBE");
    const outcome = submitAttempt(base, choices, state);
    expect(outcome.exhausted).toBe(true);
    expect(outcome.alternative).toBe(false);
  });

  it("ignores every move once the puzzle is finished", () => {
    const base = payload();
    const done = { ...initialState(), finished: true };
    expect(fillNextBlank(base, done, "c0")).toBe(done);
    expect(clearBlank(done, 0)).toBe(done);
    expect(undoLast(done)).toBe(done);
    expect(clearFilled(done)).toBe(done);
    expect(revealNextHint(base, done)).toBe(done);
  });
});

describe("missing-letters: hints and score", () => {
  const hinted = payload({
    hints: [
      { kind: "category", text: "a tag", cost: 1 },
      { kind: "meaning", text: "a phrase", cost: 3 },
    ],
  });

  it("walks the ladder in order and stops when it is spent", () => {
    let state = initialState();
    expect(nextHint(hinted, state)?.kind).toBe("category");
    state = revealNextHint(hinted, state);
    expect(revealedHints(hinted, state)).toHaveLength(1);
    state = revealNextHint(hinted, state);
    expect(nextHint(hinted, state)).toBeNull();
    expect(revealNextHint(hinted, state)).toBe(state);
  });

  it("counts HOLES rather than the printed word, and charges every rung", () => {
    expect(baseScore(payload())).toBe(DEFAULT_POINTS_PER_BLANK);
    expect(baseScore(payload({ blanks: [1, 2] }))).toBe(2 * DEFAULT_POINTS_PER_BLANK);
    let state = initialState();
    state = revealNextHint(hinted, state);
    state = revealNextHint(hinted, state);
    expect(scoreFor(hinted, state)).toBe(DEFAULT_POINTS_PER_BLANK - 4);
  });

  it("takes a base score from the config slice and never goes negative", () => {
    expect(baseScore(payload(), { baseScore: 55 })).toBe(55);
    expect(baseScore(payload(), { baseScore: -5 })).toBe(DEFAULT_POINTS_PER_BLANK);
    const spent = { ...initialState(), revealedHintCount: 2 };
    expect(scoreFor(hinted, spent, { baseScore: 2 })).toBe(0);
  });
});

describe("missing-letters: state round-trip and keys", () => {
  it("rebuilds a valid state from junk", () => {
    expect(normalizeState(null)).toEqual(initialState());
    expect(normalizeState("nope")).toEqual(initialState());
    expect(normalizeState({ filledChoiceIds: ["c1", 7, null] }).filledChoiceIds).toEqual([
      "c1",
    ]);
    const real = { ...initialState(), filledChoiceIds: ["c2"], attempts: 1, score: 20 };
    expect(normalizeState(real)).toEqual(real);
  });

  it("maps keys to mechanic actions and nothing else", () => {
    expect(keyToAction("Enter")).toBe("place");
    expect(keyToAction(" ")).toBe("place");
    expect(keyToAction("Backspace")).toBe("undo");
    expect(keyToAction("Escape")).toBe("clear");
    expect(keyToAction("a")).toBeNull();
  });

  it("takes label overrides from the config slice, and only strings", () => {
    expect(resolveLabels()).toEqual(DEFAULT_LABELS);
    expect(resolveLabels({ labels: { prompt: "fill it" } }).prompt).toBe("fill it");
    expect(resolveLabels({ labels: { prompt: 7 } }).prompt).toBe(DEFAULT_LABELS.prompt);
    expect(resolveLabels({ labels: { prompt: "" } }).prompt).toBe(DEFAULT_LABELS.prompt);
  });

  it("labels the board in Tamil by default", () => {
    // Every default a player reads is Tamil script, not a romanisation.
    for (const key of ["prompt", "bank", "answer", "hint", "correct", "wrong"] as const) {
      expect(/[\u0B80-\u0BFF]/.test(DEFAULT_LABELS[key])).toBe(true);
    }
  });
});
