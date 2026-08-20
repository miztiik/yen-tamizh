// Unit tier - the word-search mechanic's pure core (docs/concepts/games.md).
//
// The board is a small real one: a 5x5 grid holding four words in four
// directions, one of them running backwards up a diagonal, plus a word the grid
// spells that nobody asked for. It is written with \uXXXX escapes so this file's
// own normalization form cannot change what the tests assert.
//
// What these cover is the two things the mechanic can get wrong that no schema
// can catch: what a trace SELECTS (the same line for a pointer and for a
// keyboard, or the two input methods disagree) and what a trace is WORTH.

import { describe, expect, it } from "vitest";

import { segment } from "../../tamil/ezhuthu";

import {
  applyKey,
  cancelTrace,
  cellsOf,
  fullScore,
  gridCols,
  gridRows,
  initialState,
  isResolved,
  keyToAction,
  markedCells,
  moveCursor,
  nextReveal,
  normalizeState,
  outstanding,
  resolveLabels,
  revealNext,
  scoreFor,
  selectedCells,
  selectedWord,
  setCursor,
  startTrace,
  submitTrace,
  tracePath,
  traceDirection,
  wordValue,
  type Cell,
  type WordSearchPayload,
  type WordSearchState,
} from "./logic";

// The letters this fixture is built from, named so the grid below reads.
const KA = "\u0b95"; // ka
const TA = "\u0ba4"; // tha
const MA = "\u0bae"; // ma
const NA = "\u0ba9"; // na
const LA = "\u0bb2"; // la
const RA = "\u0bb0"; // ra
const KAA = "\u0b95\u0bbe"; // kaa - two code points, ONE ezhuthu
const MEI_M = "\u0bae\u0bcd"; // m with a pulli - one ezhuthu of its own

// Four words, four directions, and one word the grid spells that nobody asked
// for:
//   ka-tha-ma      (0,0) right       [also traceable backwards]
//   tha-ka-na      (2,0) down
//   ma-kaa-ra      (0,4) down-left   [holds a two-code-point cluster]
//   la-ma-mei_m    (4,4) up
//   ma-ma-ka       (1,0) right       - alsoValid, a real word not on the list
const GRID: WordSearchPayload["grid"] = [
  [KA, TA, MA, LA, MA],
  [MA, MA, KA, KAA, LA],
  [TA, LA, RA, LA, MEI_M],
  [KA, LA, LA, RA, MA],
  [NA, RA, LA, RA, LA],
];

const PAYLOAD: WordSearchPayload = {
  grid: GRID,
  targets: [
    { word: KA + TA + MA, start: { row: 0, col: 0 }, direction: "right", meaning: "one" },
    { word: TA + KA + NA, start: { row: 2, col: 0 }, direction: "down" },
    { word: MA + KAA + RA, start: { row: 0, col: 4 }, direction: "down-left" },
    { word: LA + MA + MEI_M, start: { row: 4, col: 4 }, direction: "up" },
  ],
  alsoValid: [MA + MA + KA],
};

function tracedTo(state: WordSearchState, from: Cell, to: Cell): WordSearchState {
  return setCursor(PAYLOAD, startTrace(PAYLOAD, state, from), to);
}

describe("the grid is read in ezhuthu, never in code points", () => {
  it("derives its own shape rather than trusting a stored one", () => {
    expect(gridRows(PAYLOAD)).toBe(5);
    expect(gridCols(PAYLOAD)).toBe(5);
  });

  it("holds a two-code-point cluster in ONE cell", () => {
    const cell = GRID[1]?.[3] ?? "";
    expect(cell).toBe(KAA);
    expect(cell.length).toBe(2);
    expect(segment(cell)).toEqual([cell]);
  });

  it("counts a word's cells by ezhuthu, so a cluster never costs two", () => {
    const target = PAYLOAD.targets[2];
    expect(target).toBeDefined();
    expect(cellsOf(target as (typeof PAYLOAD)["targets"][number])).toEqual([
      { row: 0, col: 4 },
      { row: 1, col: 3 },
      { row: 2, col: 2 },
    ]);
  });
});

describe("what a trace selects", () => {
  it("covers the straight line between its two ends", () => {
    expect(tracePath({ row: 0, col: 0 }, { row: 0, col: 2 })).toHaveLength(3);
    expect(tracePath({ row: 0, col: 0 }, { row: 2, col: 2 })).toHaveLength(3);
    expect(tracePath({ row: 4, col: 4 }, { row: 2, col: 2 })).toHaveLength(3);
  });

  it("selects nothing when the two ends are not on one line", () => {
    expect(tracePath({ row: 0, col: 0 }, { row: 1, col: 2 })).toEqual([]);
    expect(traceDirection({ row: 0, col: 0 }, { row: 1, col: 2 })).toBeNull();
  });

  it("names all eight directions and only those", () => {
    expect(traceDirection({ row: 0, col: 0 }, { row: 0, col: 3 })).toBe("right");
    expect(traceDirection({ row: 3, col: 3 }, { row: 0, col: 0 })).toBe("up-left");
    expect(traceDirection({ row: 0, col: 3 }, { row: 3, col: 0 })).toBe("down-left");
    expect(traceDirection({ row: 1, col: 1 }, { row: 1, col: 1 })).toBeNull();
  });

  it("spells its cells joined, left to right along the line", () => {
    const state = tracedTo(initialState(), { row: 4, col: 0 }, { row: 4, col: 2 });
    expect(selectedWord(PAYLOAD, state)).toBe(NA + RA + LA);
  });
});

describe("what a trace is worth", () => {
  it("finds a word traced forwards, and misses one the grid does not spell", () => {
    const wrong = submitTrace(
      PAYLOAD,
      tracedTo(initialState(), { row: 4, col: 0 }, { row: 4, col: 2 }),
    );
    expect(wrong.attempt).toBe(NA + RA + LA);
    expect(wrong.verdict).toBe("miss");

    const right = submitTrace(
      PAYLOAD,
      tracedTo(initialState(), { row: 0, col: 0 }, { row: 0, col: 2 }),
    );
    expect(right.attempt).toBe(KA + TA + MA);
    expect(right.verdict).toBe("found");
    expect(right.completed).toBe(false);
  });

  it("finds a word traced BACKWARDS, because a trace is judged by what it spells", () => {
    const forwards = submitTrace(
      PAYLOAD,
      tracedTo(initialState(), { row: 2, col: 0 }, { row: 4, col: 0 }),
    );
    expect(forwards.verdict).toBe("found");
    expect(forwards.word).toBe(TA + KA + NA);

    const backwards = submitTrace(
      PAYLOAD,
      tracedTo(initialState(), { row: 4, col: 0 }, { row: 2, col: 0 }),
    );
    expect(backwards.verdict).toBe("found");
    expect(backwards.word).toBe(TA + KA + NA);
    // Recorded so it READS as the word, whichever way the player drew it.
    expect(backwards.state.found[0]).toEqual({
      word: TA + KA + NA,
      row: 2,
      col: 0,
      direction: "down",
    });
  });

  it("answers a real word that is not on today's list instead of refusing it", () => {
    const outcome = submitTrace(
      PAYLOAD,
      tracedTo(initialState(), { row: 1, col: 0 }, { row: 1, col: 2 }),
    );
    expect(outcome.attempt).toBe(MA + MA + KA);
    expect(outcome.verdict).toBe("also-valid");
    expect(outcome.state.found).toHaveLength(0);
  });

  it("says so rather than crediting a word twice", () => {
    const found = submitTrace(
      PAYLOAD,
      tracedTo(initialState(), { row: 2, col: 0 }, { row: 4, col: 0 }),
    );
    const again = submitTrace(
      PAYLOAD,
      tracedTo(found.state, { row: 2, col: 0 }, { row: 4, col: 0 }),
    );
    expect(again.verdict).toBe("already");
    expect(again.state.found).toHaveLength(1);
  });

  it("refuses a single cell without calling it a miss", () => {
    const outcome = submitTrace(
      PAYLOAD,
      tracedTo(initialState(), { row: 0, col: 0 }, { row: 0, col: 0 }),
    );
    expect(outcome.verdict).toBe("none");
    expect(outcome.state.anchor).toBeNull();
  });

  it("costs nothing to be wrong - there is no attempt budget to spend", () => {
    let state = initialState();
    for (let i = 0; i < 20; i += 1) {
      state = submitTrace(PAYLOAD, tracedTo(state, { row: 4, col: 0 }, { row: 4, col: 4 })).state;
    }
    expect(state.finished).toBe(false);
    expect(outstanding(PAYLOAD, state)).toHaveLength(4);
  });
});

describe("the keyboard plays the same mechanic as the pointer", () => {
  it("maps the arrows, Enter and Escape and nothing else", () => {
    expect(keyToAction("ArrowRight")).toEqual({ kind: "move", step: { row: 0, col: 1 } });
    expect(keyToAction("Enter")).toEqual({ kind: "trace" });
    expect(keyToAction("Escape")).toEqual({ kind: "cancel" });
    expect(keyToAction("q")).toBeNull();
  });

  it("keeps the cursor on the grid at every edge", () => {
    let state = initialState();
    for (let i = 0; i < 10; i += 1) state = moveCursor(PAYLOAD, state, { row: -1, col: -1 });
    expect(state.cursor).toEqual({ row: 0, col: 0 });
    for (let i = 0; i < 10; i += 1) state = moveCursor(PAYLOAD, state, { row: 1, col: 1 });
    expect(state.cursor).toEqual({ row: 4, col: 4 });
  });

  it("finds a diagonal word with arrows and two Enters", () => {
    let state = initialState();
    // Right four times to (0,4), Enter to anchor, then two steps down-left.
    for (const key of ["ArrowRight", "ArrowRight", "ArrowRight", "ArrowRight", "Enter"]) {
      state = applyKey(PAYLOAD, state, key).state;
    }
    expect(state.anchor).toEqual({ row: 0, col: 4 });
    for (const key of ["ArrowDown", "ArrowLeft", "ArrowDown", "ArrowLeft"]) {
      state = applyKey(PAYLOAD, state, key).state;
    }
    expect(selectedCells(state)).toHaveLength(3);
    const result = applyKey(PAYLOAD, state, "Enter");
    expect(result.outcome?.verdict).toBe("found");
    expect(result.outcome?.word).toBe(MA + KAA + RA);
  });

  it("selects EXACTLY what the pointer would from the same two cells", () => {
    let byKey = startTrace(PAYLOAD, initialState(), { row: 4, col: 4 });
    for (const key of ["ArrowUp", "ArrowUp"]) {
      byKey = applyKey(PAYLOAD, byKey, key).state;
    }
    const byPointer = tracedTo(initialState(), { row: 4, col: 4 }, { row: 2, col: 4 });
    expect(selectedCells(byKey)).toEqual(selectedCells(byPointer));
    expect(selectedWord(PAYLOAD, byKey)).toBe(selectedWord(PAYLOAD, byPointer));
    expect(submitTrace(PAYLOAD, byKey).word).toBe(LA + MA + MEI_M);
  });

  it("abandons a trace on Escape without spending anything", () => {
    const state = applyKey(PAYLOAD, startTrace(PAYLOAD, initialState()), "Escape").state;
    expect(state.anchor).toBeNull();
    expect(cancelTrace(state)).toBe(state);
  });
});

describe("scoring, revealing and finishing", () => {
  function findAll(): WordSearchState {
    let state = initialState();
    for (const target of PAYLOAD.targets) {
      const cells = cellsOf(target);
      const first = cells[0] as Cell;
      const last = cells[cells.length - 1] as Cell;
      state = submitTrace(PAYLOAD, tracedTo(state, first, last)).state;
    }
    return state;
  }

  it("pays per ezhuthu, so a cluster is one letter and not two", () => {
    expect(wordValue(MA + KAA + RA)).toBe(30);
    expect(fullScore(PAYLOAD)).toBe(12 * 10);
  });

  it("finishes solved when every word was traced", () => {
    const state = findAll();
    expect(state.finished).toBe(true);
    expect(state.solved).toBe(true);
    expect(state.score).toBe(fullScore(PAYLOAD));
    expect(markedCells(PAYLOAD, state).size).toBeGreaterThan(0);
  });

  it("charges a reveal exactly the word it hands over, and no more", () => {
    const before = submitTrace(
      PAYLOAD,
      tracedTo(initialState(), { row: 2, col: 0 }, { row: 4, col: 0 }),
    ).state;
    const handed = revealNext(PAYLOAD, before);
    expect(handed.word).toBe(nextReveal(PAYLOAD, before)?.word);
    expect(handed.cost).toBe(wordValue(handed.word ?? ""));
    // The traced word is still paid for; only the handed-over one is not.
    expect(handed.state.score).toBe(scoreFor(PAYLOAD, handed.state));
    expect(handed.state.score).toBe(wordValue(TA + KA + NA));
    expect(isResolved(handed.state, handed.word ?? "")).toBe(true);
    expect(handed.state.solved).toBe(false);
  });

  it("scales an overridden total by the share the player traced", () => {
    const state = submitTrace(
      PAYLOAD,
      tracedTo(initialState(), { row: 2, col: 0 }, { row: 4, col: 0 }),
    ).state;
    // 3 of 12 ezhuthu traced, so a quarter of the configured total.
    expect(scoreFor(PAYLOAD, state, { baseScore: 400 })).toBe(100);
  });

  it("ends the board once the last word is revealed rather than trapping a player", () => {
    let state = initialState();
    for (let i = 0; i < PAYLOAD.targets.length; i += 1) {
      state = revealNext(PAYLOAD, state).state;
    }
    expect(state.finished).toBe(true);
    expect(state.solved).toBe(false);
    expect(state.score).toBe(0);
    expect(revealNext(PAYLOAD, state).word).toBeNull();
  });
});

describe("restoring an untrusted snapshot", () => {
  it("rebuilds progress and recomputes what it derives", () => {
    const played = submitTrace(
      PAYLOAD,
      tracedTo(initialState(), { row: 2, col: 0 }, { row: 4, col: 0 }),
    ).state;
    const restored = normalizeState(PAYLOAD, JSON.parse(JSON.stringify(played)));
    expect(restored.found).toEqual(played.found);
    expect(restored.score).toBe(played.score);
  });

  it("drops a word this board does not hide", () => {
    const restored = normalizeState(PAYLOAD, {
      found: [{ word: "\u0b85\u0b86", row: 0, col: 0, direction: "right" }],
      revealed: ["\u0b87"],
    });
    expect(restored.found).toEqual([]);
    expect(restored.revealed).toEqual([]);
  });

  it("never restores a trace that was still in the air", () => {
    const mid = startTrace(PAYLOAD, initialState(), { row: 1, col: 1 });
    expect(normalizeState(PAYLOAD, mid).anchor).toBeNull();
  });

  it("survives junk without throwing", () => {
    expect(normalizeState(PAYLOAD, null)).toEqual(initialState());
    expect(normalizeState(PAYLOAD, { found: 7, cursor: "x" }).cursor).toEqual({
      row: 0,
      col: 0,
    });
  });
});

describe("labels", () => {
  it("answers in Tamil by default and takes a Mode's overrides", () => {
    expect(resolveLabels().prompt).toMatch(/[\u0b80-\u0bff]/);
    expect(resolveLabels({ labels: { prompt: "Find them" } }).prompt).toBe("Find them");
    expect(resolveLabels({ labels: { prompt: "" } }).prompt).toBe(resolveLabels().prompt);
  });
});
