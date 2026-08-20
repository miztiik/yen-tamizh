// Unit tier - the crossword mechanic's pure core (docs/concepts/games.md).
//
// The board under test is a REAL baked one, lifted from the committed served set
// through the real solver rather than hand-typed: the easy band's 5x5 mask, four
// answers of five ezhuthu crossing at four squares. Tamil is written as escapes
// so the file's own normalization form cannot change what the tests mean.

import { describe, expect, it } from "vitest";

import { segment } from "../../tamil/ezhuthu";

import {
  AYTHAM,
  BASE_KEYS,
  MEI_BASES,
  PULLI,
  UYIR,
  VOWEL_FORMS,
  activeEntry,
  applyKey,
  applyVowelForm,
  backspace,
  baseOf,
  cellKey,
  compose,
  entryCells,
  entryThrough,
  entryValue,
  firstCell,
  initialState,
  isComplete,
  isLockedCell,
  isOpen,
  isSettled,
  keyToAction,
  liveBase,
  moveCursor,
  nextReveal,
  normalizeState,
  numbers,
  openCells,
  outstanding,
  resolveLabels,
  revealNext,
  scoreFor,
  setCursor,
  solution,
  toggleDirection,
  writeEzhuthu,
  writtenIn,
  type CrosswordPayload,
  type CrosswordState,
} from "./logic";

const BOARD: CrosswordPayload = {
  rows: 5,
  cols: 5,
  entries: [
    {
      number: 3,
      direction: "across",
      start: { row: 1, col: 0 },
      word: "\u0ba4\u0bc0\u0b9a\u0bcd\u0b9a\u0bc1\u0b9f\u0bb0\u0bcd",
      clue: "\u0b9a\u0bc1\u0bb5\u0bbe\u0bb2\u0bc8",
    },
    {
      number: 4,
      direction: "across",
      start: { row: 3, col: 0 },
      word: "\u0bae\u0bb2\u0b95\u0bcd\u0b95\u0bae\u0bcd",
      clue: "\u0bae\u0bb2\u0b95\u0bcd\u0b95\u0b9f\u0bbf",
    },
    {
      number: 1,
      direction: "down",
      start: { row: 0, col: 1 },
      word: "\u0b95\u0bc8\u0b9a\u0bcd\u0b9a\u0bc6\u0bb2\u0bb5\u0bc1",
      clue: "\u0b9a\u0bca\u0ba8\u0bcd\u0ba4\u0b9a\u0bcd \u0b9a\u0bc6\u0bb2\u0bb5\u0bc1",
    },
    {
      number: 2,
      direction: "down",
      start: { row: 0, col: 3 },
      word: "\u0ba4\u0bca\u0b9f\u0b95\u0bcd\u0b95\u0bae\u0bcd",
      clue: "\u0b86\u0bb0\u0bae\u0bcd\u0baa\u0bae\u0bcd",
    },
  ],
};

const ACROSS_3 = BOARD.entries[0]!;
const ACROSS_4 = BOARD.entries[1]!;
const DOWN_1 = BOARD.entries[2]!;
const DOWN_2 = BOARD.entries[3]!;

/** Write a whole answer in, one ezhuthu at a time, from its first square. */
function typeIn(state: CrosswordState, entry: (typeof BOARD)["entries"][number]) {
  let next = setCursor(BOARD, { ...state, direction: entry.direction }, entry.start);
  if (next.direction !== entry.direction) next = toggleDirection(BOARD, next);
  let last = writeEzhuthu(BOARD, next, segment(entry.word)[0]!);
  for (const unit of segment(entry.word).slice(1)) {
    last = writeEzhuthu(BOARD, last.state, unit);
  }
  return last;
}

describe("the board is derived from the entries, never shipped twice", () => {
  it("opens exactly the squares some answer runs through", () => {
    const open = openCells(BOARD);
    // 4 answers of 5 squares, 4 of which are shared -> 16 open squares.
    expect(open.size).toBe(16);
    expect(isOpen(BOARD, { row: 1, col: 0 })).toBe(true);
    expect(isOpen(BOARD, { row: 0, col: 0 })).toBe(false);
  });

  it("numbers the starting squares in reading order", () => {
    const marks = numbers(BOARD);
    expect(marks.get("0,1")).toBe(1);
    expect(marks.get("0,3")).toBe(2);
    expect(marks.get("1,0")).toBe(3);
    expect(marks.get("3,0")).toBe(4);
  });

  it("ORACLE - every crossing square satisfies BOTH its answers", () => {
    // Read out of the grid the entries build, not out of the entries.
    const grid = solution(BOARD);
    for (const entry of BOARD.entries) {
      const spelled = entryCells(entry).map((cell) => grid.get(cellKey(cell)));
      expect(spelled.join("")).toBe(entry.word);
    }
    // Four squares carry two answers each, and both agree there.
    const shared = BOARD.entries
      .flatMap((entry) => entryCells(entry).map(cellKey))
      .filter((key, index, all) => all.indexOf(key) !== index);
    expect(new Set(shared).size).toBe(4);
  });

  it("starts the caret on the first square in reading order", () => {
    expect(firstCell(BOARD)).toEqual({ row: 0, col: 1 });
    expect(initialState(BOARD).cursor).toEqual({ row: 0, col: 1 });
  });
});

describe("the caret and the direction are one thing", () => {
  it("turns the corner when the square it is on is tapped again", () => {
    const first = setCursor(BOARD, initialState(BOARD), { row: 1, col: 1 });
    expect(first.direction).toBe("across");
    const turned = setCursor(BOARD, first, { row: 1, col: 1 });
    expect(turned.direction).toBe("down");
  });

  it("refuses to turn into a direction with no answer through the square", () => {
    // (1,2) is only on the across answer; there is no down answer there.
    const state = setCursor(BOARD, initialState(BOARD), { row: 1, col: 2 });
    expect(toggleDirection(BOARD, state).direction).toBe("across");
  });

  it("ignores a tap on a blocked square", () => {
    const state = initialState(BOARD);
    expect(setCursor(BOARD, state, { row: 0, col: 0 })).toBe(state);
  });

  it("jumps blocked squares when arrowing, and stays put at the edge", () => {
    // Arrowing right from (1,0) walks the row; arrowing up from (1,0) has
    // nothing open above it.
    const start = setCursor(BOARD, initialState(BOARD), { row: 1, col: 0 });
    expect(moveCursor(BOARD, start, { row: 0, col: 1 }).cursor).toEqual({ row: 1, col: 1 });
    expect(moveCursor(BOARD, start, { row: -1, col: 0 })).toBe(start);
    // Down from (0,1) is the down answer, and it sets the direction with it.
    const top = setCursor(BOARD, initialState(BOARD), { row: 0, col: 1 });
    const moved = moveCursor(BOARD, top, { row: 1, col: 0 });
    expect(moved.cursor).toEqual({ row: 1, col: 1 });
    expect(moved.direction).toBe("down");
  });

  it("prefers the chosen direction and falls back to the other one", () => {
    const state = setCursor(BOARD, initialState(BOARD), { row: 1, col: 2 });
    expect(activeEntry(BOARD, { ...state, direction: "down" })?.number).toBe(3);
    expect(entryThrough(BOARD, { row: 1, col: 1 }, "down")?.number).toBe(1);
  });

  it("adopts the direction a square really runs, however it was reached", () => {
    // (0,1) carries only a DOWN answer. A caret arriving there still set to
    // across would highlight that down answer and then step SIDEWAYS onto the
    // across one at the first crossing, writing two answers at once.
    const tapped = setCursor(BOARD, initialState(BOARD), { row: 0, col: 1 });
    expect(tapped.direction).toBe("down");
    // The same claim for the keyboard: arrowing RIGHT onto a square with no
    // across answer keeps the caret on the answer that is really there.
    const arrowed = moveCursor(
      BOARD,
      setCursor(BOARD, initialState(BOARD), { row: 4, col: 1 }),
      { row: 0, col: 1 },
    );
    expect(arrowed.cursor).toEqual({ row: 4, col: 3 });
    expect(arrowed.direction).toBe("down");
    // And a square that really does run across keeps across.
    expect(setCursor(BOARD, initialState(BOARD), { row: 1, col: 2 }).direction).toBe(
      "across",
    );
  });
});

describe("writing a letter", () => {
  it("writes into the square and steps along the answer", () => {
    const start = setCursor(BOARD, initialState(BOARD), { row: 1, col: 0 });
    const out = writeEzhuthu(BOARD, start, segment(ACROSS_3.word)[0]!);
    expect(out.state.filled["1,0"]).toBe(segment(ACROSS_3.word)[0]);
    expect(out.state.cursor).toEqual({ row: 1, col: 1 });
    expect(out.completed).toBeNull();
  });

  it("writes into BOTH answers at a crossing square", () => {
    const start = setCursor(BOARD, initialState(BOARD), { row: 1, col: 1 });
    const out = writeEzhuthu(BOARD, start, "\u0b95");
    expect(writtenIn(out.state, ACROSS_3)[1]).toBe("\u0b95");
    expect(writtenIn(out.state, DOWN_1)[1]).toBe("\u0b95");
  });

  it("refuses anything that is not exactly one ezhuthu", () => {
    const start = setCursor(BOARD, initialState(BOARD), { row: 1, col: 0 });
    expect(writeEzhuthu(BOARD, start, "").state).toBe(start);
    expect(writeEzhuthu(BOARD, start, "\u0b95\u0b95").state).toBe(start);
  });

  it("reports an answer the moment its last square is filled", () => {
    const out = typeIn(initialState(BOARD), ACROSS_3);
    expect(out.completed?.number).toBe(3);
    expect(out.correct).toBe(true);
    expect(isComplete(out.state, ACROSS_3)).toBe(true);
    expect(isSettled(out.state, ACROSS_3)).toBe(true);
  });

  it("reports a completed answer that is WRONG without costing anything", () => {
    const state = setCursor(BOARD, initialState(BOARD), ACROSS_3.start);
    let out = writeEzhuthu(BOARD, state, "\u0b95");
    for (let index = 1; index < 5; index += 1) {
      out = writeEzhuthu(BOARD, out.state, "\u0b95");
    }
    expect(out.completed?.number).toBe(3);
    expect(out.correct).toBe(false);
    // No attempt budget: the board is still playable and nothing is lost.
    expect(out.state.finished).toBe(false);
    expect(out.state.score).toBe(0);
  });
});

describe("the composer keyboard", () => {
  it("offers 31 committing keys and 13 forms", () => {
    expect(UYIR).toHaveLength(12);
    expect(MEI_BASES).toHaveLength(18);
    expect(BASE_KEYS).toHaveLength(31);
    expect(BASE_KEYS).toContain(AYTHAM);
    expect(VOWEL_FORMS).toHaveLength(13);
    expect(VOWEL_FORMS[0]).toBe(PULLI);
  });

  it("every key it offers is exactly one ezhuthu", () => {
    for (const base of BASE_KEYS) expect(segment(base)).toEqual([base]);
    for (const base of MEI_BASES) {
      for (const form of VOWEL_FORMS) {
        const composed = compose(base, form);
        expect(segment(composed)).toEqual([composed]);
      }
    }
  });

  it("re-spells the square's consonant without stepping along", () => {
    const start = setCursor(BOARD, initialState(BOARD), { row: 1, col: 0 });
    const written = writeEzhuthu(BOARD, start, "\u0ba4");
    // The caret has already stepped, and the form row follows the square that
    // was WRITTEN rather than the one the caret landed on - so a base and a
    // form are two taps for one ezhuthu, with nothing to move back to.
    expect(written.state.cursor).toEqual({ row: 1, col: 1 });
    expect(liveBase(BOARD, written.state)).toBe("\u0ba4");
    const shaped = applyVowelForm(BOARD, written.state, "\u0bc0");
    expect(shaped.filled["1,0"]).toBe("\u0ba4\u0bc0");
    expect(shaped.cursor).toEqual({ row: 1, col: 1 });
  });

  it("re-spells what it just wrote, never the crossing square in front of it", () => {
    // The case the caret alone cannot decide: the next square along already
    // holds a letter another answer put there, so a form row reading the caret
    // would re-shape that answer instead of this one.
    const crossing = writeEzhuthu(
      BOARD,
      setCursor(BOARD, initialState(BOARD), { row: 0, col: 1 }),
      "\u0b95",
    ).state;
    expect(crossing.filled["1,1"]).toBeUndefined();
    const down = writeEzhuthu(BOARD, crossing, "\u0b9a").state;
    expect(down.filled["1,1"]).toBe("\u0b9a");
    const across = writeEzhuthu(
      BOARD,
      setCursor(BOARD, down, { row: 1, col: 0 }),
      "\u0ba4",
    ).state;
    expect(across.cursor).toEqual({ row: 1, col: 1 });
    const shaped = applyVowelForm(BOARD, across, "\u0bc0");
    expect(shaped.filled["1,0"]).toBe("\u0ba4\u0bc0");
    expect(shaped.filled["1,1"]).toBe("\u0b9a");
  });

  it("re-spells the square under the caret when the player moved there to fix it", () => {
    const start = setCursor(BOARD, initialState(BOARD), { row: 1, col: 0 });
    const written = writeEzhuthu(BOARD, start, "\u0ba4");
    const back = setCursor(BOARD, written.state, { row: 1, col: 0 });
    expect(back.lastWritten).toBeNull();
    expect(liveBase(BOARD, back)).toBe("\u0ba4");
    expect(applyVowelForm(BOARD, back, "\u0bbf").filled["1,0"]).toBe("\u0ba4\u0bbf");
  });

  it("does nothing when the square holds a vowel, which takes no form", () => {
    const start = setCursor(BOARD, initialState(BOARD), { row: 1, col: 0 });
    const written = writeEzhuthu(BOARD, start, UYIR[0]!);
    expect(liveBase(BOARD, written.state)).toBeNull();
    expect(applyVowelForm(BOARD, written.state, "\u0bc0")).toBe(written.state);
    expect(baseOf(UYIR[0]!)).toBeNull();
  });

  it("has nothing to re-spell before the first letter is written", () => {
    const start = setCursor(BOARD, initialState(BOARD), { row: 1, col: 0 });
    expect(liveBase(BOARD, start)).toBeNull();
    expect(applyVowelForm(BOARD, start, "\u0bc0")).toBe(start);
  });
});

describe("erasing and the keyboard map", () => {
  it("clears the square it is on, then steps back and clears that one", () => {
    const out = typeIn(initialState(BOARD), ACROSS_3);
    // The caret sits on the last square, which is filled.
    const once = backspace(BOARD, { ...out.state, cursor: { row: 1, col: 4 } });
    expect(once.filled["1,4"]).toBeUndefined();
    const twice = backspace(BOARD, once);
    expect(twice.cursor).toEqual({ row: 1, col: 3 });
    expect(twice.filled["1,3"]).toBeUndefined();
  });

  it("maps the arrow, turn and erase keys and nothing else", () => {
    expect(keyToAction("ArrowLeft")).toEqual({ kind: "move", step: { row: 0, col: -1 } });
    expect(keyToAction("Enter")).toEqual({ kind: "turn" });
    expect(keyToAction("Backspace")).toEqual({ kind: "erase" });
    expect(keyToAction("a")).toBeNull();
    const state = setCursor(BOARD, initialState(BOARD), { row: 1, col: 1 });
    expect(applyKey(BOARD, state, "Enter").direction).toBe("down");
    expect(applyKey(BOARD, state, "a")).toBe(state);
  });
});

describe("revealing is the only price", () => {
  it("fills the answer, locks its squares and earns nothing for it", () => {
    const state = setCursor(BOARD, initialState(BOARD), ACROSS_3.start);
    const out = revealNext(BOARD, state);
    expect(out.entry?.number).toBe(3);
    expect(out.cost).toBe(entryValue(ACROSS_3));
    expect(writtenIn(out.state, ACROSS_3).join("")).toBe(ACROSS_3.word);
    expect(isLockedCell(BOARD, out.state, { row: 1, col: 0 })).toBe(true);
    expect(scoreFor(BOARD, out.state)).toBe(0);
  });

  it("refuses to write over a square the player was given", () => {
    const revealed = revealNext(
      BOARD,
      setCursor(BOARD, initialState(BOARD), ACROSS_3.start),
    ).state;
    const on = setCursor(BOARD, revealed, { row: 1, col: 0 });
    expect(writeEzhuthu(BOARD, on, "\u0b95").state).toBe(on);
  });

  it("hands over the answer the caret is on before any other", () => {
    const state = setCursor(BOARD, initialState(BOARD), DOWN_2.start);
    expect(nextReveal(BOARD, { ...state, direction: "down" })?.number).toBe(2);
  });
});

describe("scoring and finishing", () => {
  it("pays the share of the board the player worked out", () => {
    const one = typeIn(initialState(BOARD), ACROSS_3).state;
    const whole = BOARD.entries.reduce((sum, entry) => sum + entryValue(entry), 0);
    expect(scoreFor(BOARD, one)).toBe(Math.round((whole * entryValue(ACROSS_3)) / whole));
    expect(one.finished).toBe(false);
  });

  it("finishes solved when every answer was worked out", () => {
    let state = initialState(BOARD);
    for (const entry of [ACROSS_3, ACROSS_4, DOWN_1, DOWN_2]) {
      state = typeIn(state, entry).state;
    }
    expect(outstanding(BOARD, state)).toEqual([]);
    expect(state.finished).toBe(true);
    expect(state.solved).toBe(true);
    expect(state.score).toBe(
      BOARD.entries.reduce((sum, entry) => sum + entryValue(entry), 0),
    );
  });

  it("finishes UNSOLVED when one answer was handed over", () => {
    let state = initialState(BOARD);
    for (const entry of [ACROSS_3, ACROSS_4, DOWN_1]) {
      state = typeIn(state, entry).state;
    }
    const out = revealNext(BOARD, setCursor(BOARD, state, DOWN_2.start));
    expect(out.state.finished).toBe(true);
    expect(out.state.solved).toBe(false);
  });

  it("honours a Mode's baseScore override", () => {
    let state = initialState(BOARD);
    for (const entry of BOARD.entries) state = typeIn(state, entry).state;
    expect(scoreFor(BOARD, state, { baseScore: 500 })).toBe(500);
  });
});

describe("an alternative answers the same clue", () => {
  it("accepts a listed synonym that fits every crossing", () => {
    const alternative = "\u0ba4\u0bc0\u0b9a\u0bcd\u0b9a\u0bc1\u0b9f\u0bbf";
    // `entries` is a minimum-length TUPLE in the generated contract, so it is
    // rebuilt head-first rather than mapped: a mapped array satisfies no
    // required position and TypeScript rejects it (Row 18's lesson).
    const [first, second, ...rest] = BOARD.entries;
    const board: CrosswordPayload = {
      ...BOARD,
      entries: [{ ...first, alsoValid: [alternative] }, second, ...rest],
    };
    const state = setCursor(board, initialState(board), ACROSS_3.start);
    let out = writeEzhuthu(board, state, segment(alternative)[0]!);
    for (const unit of segment(alternative).slice(1)) {
      out = writeEzhuthu(board, out.state, unit);
    }
    expect(out.correct).toBe(true);
    expect(isSettled(out.state, board.entries[0]!)).toBe(true);
  });
});

describe("restoring a persisted snapshot", () => {
  it("keeps what belongs to this board and drops what does not", () => {
    const restored = normalizeState(BOARD, {
      filled: { "1,0": "\u0ba4\u0bc0", "9,9": "\u0b95", "1,1": "not one ezhuthu" },
      revealed: ["\u0b95\u0b95\u0b95"],
      cursor: { row: 1, col: 0 },
      direction: "down",
    });
    expect(restored.filled).toEqual({ "1,0": "\u0ba4\u0bc0" });
    expect(restored.revealed).toEqual([]);
    expect(restored.cursor).toEqual({ row: 1, col: 0 });
    expect(restored.direction).toBe("down");
  });

  it("falls back to a fresh board for junk", () => {
    expect(normalizeState(BOARD, null)).toEqual(initialState(BOARD));
    expect(normalizeState(BOARD, { cursor: { row: 0, col: 0 } }).cursor).toEqual(
      firstCell(BOARD),
    );
  });

  it("recomputes the derived flags rather than trusting them", () => {
    const solved = solution(BOARD);
    const filled: Record<string, string> = {};
    for (const [key, unit] of solved) filled[key] = unit;
    const restored = normalizeState(BOARD, { filled, finished: false, score: 999 });
    expect(restored.finished).toBe(true);
    expect(restored.solved).toBe(true);
    expect(restored.score).toBe(
      BOARD.entries.reduce((sum, entry) => sum + entryValue(entry), 0),
    );
  });
});

describe("labels", () => {
  it("ships Tamil wording and takes overrides from the config slice", () => {
    expect(resolveLabels().prompt).toBe("\u0b9a\u0bca\u0bb1\u0bcd\u0b95\u0b9f\u0bcd\u0b9f\u0bae\u0bcd");
    expect(resolveLabels({ labels: { reveal: "x" } }).reveal).toBe("x");
    expect(resolveLabels({ labels: { reveal: 7 } }).reveal).toBe(
      resolveLabels().reveal,
    );
  });
});
