// The anagram mechanic's unit tests - the rules that must hold before any pixel
// is drawn. Every assertion is over EZHUTHU (Row 6 clusters), never code points,
// so a two-part matra or a pulli/mei cluster can never be split by the mechanic.

import { describe, expect, it } from "vitest";

import { segment } from "../../tamil/ezhuthu";

import {
  attemptsRemaining,
  baseScore,
  buildTray,
  clearPlaced,
  DEFAULT_LABELS,
  DEFAULT_POINTS_PER_EZHUTHU,
  ezhuthuArraysEqual,
  initialState,
  isAlsoValid,
  isFull,
  isSolved,
  keyToAction,
  normalizeState,
  nextHint,
  placeTile,
  placedEzhuthu,
  remainingTiles,
  removeTile,
  resolveLabels,
  revealNextHint,
  revealedHints,
  scoreFor,
  shuffleDeterministic,
  submitAttempt,
  targetEzhuthu,
  undoLast,
  type AnagramPayload,
  type AnagramState,
} from "./logic";

// "\u0BA4\u0BAE\u0BBF\u0BB4\u0BCD" = tamizh: [ta, mi (two-code-point uyirmei),
// zh + pulli (a mei cluster)]. Escapes keep the fixture NFC/NFD-unambiguous, the
// same discipline as datasets/fixtures/ezhuthu_golden.jsonl (Row 6).
const TAMIZH = "\u0BA4\u0BAE\u0BBF\u0BB4\u0BCD";
// kolam, written two ways: NFC (ka + precomposed o-sign) and NFD, where "ko" is
// a TWO-PART matra (ka + e-sign + aa-sign) that must still be ONE tile.
const KOLAM_NFC = "\u0B95\u0BCA\u0BB2\u0BAE\u0BCD";
const KOLAM_TWO_PART = "\u0B95\u0BC6\u0BBE\u0BB2\u0BAE\u0BCD";

function payloadFor(word: string, overrides: Partial<AnagramPayload> = {}): AnagramPayload {
  return {
    word,
    tiles: segment(word) as AnagramPayload["tiles"],
    timeLimitSec: 0,
    attempts: 3,
    ...overrides,
  };
}

/** Place tiles by the ezhuthu they carry, in the given order. */
function arrange(payload: AnagramPayload, order: readonly string[]): AnagramState {
  const tray = buildTray(payload);
  let state = initialState();
  const used = new Set<string>();
  for (const cluster of order) {
    const tile = tray.find((t) => t.ezhuthu === cluster && !used.has(t.id));
    if (tile === undefined) throw new Error(`no tray tile for "${cluster}"`);
    used.add(tile.id);
    state = placeTile(payload, state, tile.id);
  }
  return state;
}

describe("scramble determinism", () => {
  it("produces the same tray for the same puzzle on every build", () => {
    const payload = payloadFor(TAMIZH);
    const a = buildTray(payload);
    const b = buildTray(payload);
    expect(b).toEqual(a);
    expect(a.map((t) => t.id)).toEqual(["t0", "t1", "t2"]);
  });

  it("keeps every ezhuthu tile intact and accounted for", () => {
    const payload = payloadFor(TAMIZH);
    const tray = buildTray(payload);
    expect([...tray.map((t) => t.ezhuthu)].sort()).toEqual([...payload.tiles].sort());
    // The mei cluster (zh + pulli) survives as ONE tile, never two.
    expect(tray.map((t) => t.ezhuthu)).toContain("\u0BB4\u0BCD");
  });

  it("never hands the player a tray already in the answer order", () => {
    for (const word of [TAMIZH, KOLAM_NFC, "\u0B85\u0B95\u0BAE\u0BCD", "\u0BAA\u0BB2\u0BAE\u0BCD"]) {
      const payload = payloadFor(word);
      const tray = buildTray(payload);
      expect(ezhuthuArraysEqual(tray.map((t) => t.ezhuthu), targetEzhuthu(payload))).toBe(false);
    }
  });

  it("shuffleDeterministic is a permutation that depends only on the seed", () => {
    const items = ["a", "b", "c", "d", "e", "f"];
    expect(shuffleDeterministic(items, 12345)).toEqual(shuffleDeterministic(items, 12345));
    expect(shuffleDeterministic(items, 12345)).not.toEqual(shuffleDeterministic(items, 999));
    expect([...shuffleDeterministic(items, 12345)].sort()).toEqual(items);
  });
});

describe("solve and validation over ezhuthu", () => {
  it("accepts the target arrangement of a word with a mei (pulli) cluster", () => {
    const payload = payloadFor(TAMIZH);
    const tray = buildTray(payload);
    const state = arrange(payload, targetEzhuthu(payload));
    expect(isFull(payload, state)).toBe(true);
    expect(isSolved(payload, tray, state)).toBe(true);
    expect(placedEzhuthu(tray, state).join("")).toBe(TAMIZH);
  });

  it("accepts a word whose NFD two-part matra is a single tile", () => {
    const payload = payloadFor(KOLAM_TWO_PART);
    const target = targetEzhuthu(payload);
    // ka + e-sign + aa-sign is ONE ezhuthu; the word has 3 tiles, not 4.
    expect(target).toHaveLength(3);
    expect(target[0]).toBe("\u0B95\u0BC6\u0BBE");
    const tray = buildTray(payload);
    const state = arrange(payload, target);
    expect(isSolved(payload, tray, state)).toBe(true);
  });

  it("rejects a wrong order and rejects a partial arrangement", () => {
    const payload = payloadFor(TAMIZH);
    const tray = buildTray(payload);
    const target = targetEzhuthu(payload);
    const swapped = [target[1] as string, target[0] as string, target[2] as string];
    expect(isSolved(payload, tray, arrange(payload, swapped))).toBe(false);
    expect(isSolved(payload, tray, arrange(payload, target.slice(0, 2)))).toBe(false);
  });

  it("compares clusters, not code points", () => {
    // Same code points, different clustering -> not equal.
    expect(ezhuthuArraysEqual(["\u0BB4\u0BCD"], ["\u0BB4", "\u0BCD"])).toBe(false);
    expect(ezhuthuArraysEqual(segment(TAMIZH), segment(TAMIZH))).toBe(true);
  });
});

describe("placement, undo and clear", () => {
  it("places into the next free slot and refuses a placed or extra tile", () => {
    const payload = payloadFor(TAMIZH);
    const tray = buildTray(payload);
    const first = tray[0]!.id;
    let state = placeTile(payload, initialState(), first);
    expect(state.placedTileIds).toEqual([first]);
    expect(placeTile(payload, state, first)).toBe(state); // already placed
    expect(remainingTiles(tray, state)).toHaveLength(2);

    state = arrange(payload, targetEzhuthu(payload));
    expect(placeTile(payload, state, tray[0]!.id)).toBe(state); // no free slot
  });

  it("undo pops the last tile, remove takes a specific one, clear empties", () => {
    const payload = payloadFor(TAMIZH);
    const tray = buildTray(payload);
    const state = arrange(payload, targetEzhuthu(payload));
    expect(undoLast(state).placedTileIds).toEqual(state.placedTileIds.slice(0, -1));
    expect(removeTile(state, state.placedTileIds[0]!).placedTileIds).toEqual(
      state.placedTileIds.slice(1),
    );
    expect(clearPlaced(state).placedTileIds).toEqual([]);
    expect(placedEzhuthu(tray, clearPlaced(state))).toEqual([]);
  });

  it("freezes the board once the puzzle is finished", () => {
    const payload = payloadFor(TAMIZH);
    const tray = buildTray(payload);
    const finished: AnagramState = { ...initialState(), finished: true };
    expect(placeTile(payload, finished, tray[0]!.id)).toBe(finished);
    expect(undoLast({ ...finished, placedTileIds: ["t0"] })).toEqual({
      ...finished,
      placedTileIds: ["t0"],
    });
  });
});

describe("attempts", () => {
  it("a wrong attempt spends one and clears the board, a win finishes it", () => {
    const payload = payloadFor(TAMIZH);
    const tray = buildTray(payload);
    const target = targetEzhuthu(payload);
    const wrong = submitAttempt(
      payload,
      tray,
      arrange(payload, [target[1] as string, target[0] as string, target[2] as string]),
    );
    expect(wrong.correct).toBe(false);
    expect(wrong.exhausted).toBe(false);
    expect(wrong.attemptIndex).toBe(1);
    expect(wrong.state.placedTileIds).toEqual([]);
    expect(wrong.state.finished).toBe(false);
    expect(attemptsRemaining(payload, wrong.state)).toBe(2);

    const win = submitAttempt(payload, tray, arrange(payload, target));
    expect(win.correct).toBe(true);
    expect(win.attempt).toBe(TAMIZH);
    expect(win.state.finished).toBe(true);
    expect(win.state.solved).toBe(true);
  });

  it("spending the last attempt ends the puzzle", () => {
    const payload = payloadFor(TAMIZH, { attempts: 1 });
    const tray = buildTray(payload);
    const target = targetEzhuthu(payload);
    const out = submitAttempt(
      payload,
      tray,
      arrange(payload, [target[2] as string, target[1] as string, target[0] as string]),
    );
    expect(out.exhausted).toBe(true);
    expect(out.state.finished).toBe(true);
    expect(out.state.solved).toBe(false);
    expect(attemptsRemaining(payload, out.state)).toBe(0);
  });
});

describe("scoring", () => {
  const hints = [
    { kind: "reveal-first", text: "first", cost: 3 },
    { kind: "reveal-last", text: "last", cost: 2 },
  ];

  it("scores base points per ezhuthu when no hint is taken", () => {
    const payload = payloadFor(TAMIZH, { hints });
    const tray = buildTray(payload);
    const win = submitAttempt(payload, tray, arrange(payload, targetEzhuthu(payload)));
    expect(baseScore(payload)).toBe(3 * DEFAULT_POINTS_PER_EZHUTHU);
    expect(win.state.score).toBe(30);
  });

  it("subtracts the cost of every revealed hint", () => {
    const payload = payloadFor(TAMIZH, { hints });
    const tray = buildTray(payload);
    let state = arrange(payload, targetEzhuthu(payload));
    state = revealNextHint(payload, state);
    expect(revealedHints(payload, state)).toHaveLength(1);
    expect(scoreFor(payload, state)).toBe(30 - 3);

    state = revealNextHint(payload, state);
    expect(nextHint(payload, state)).toBeNull();
    expect(revealNextHint(payload, state).revealedHintCount).toBe(2); // no more to spend
    expect(scoreFor(payload, state)).toBe(30 - 5);
    expect(submitAttempt(payload, tray, state).state.score).toBe(25);
  });

  it("takes the base score from the injected config slice and never goes negative", () => {
    const payload = payloadFor(TAMIZH, { hints: [{ kind: "big", text: "big", cost: 99 }] });
    expect(baseScore(payload, { baseScore: 12 })).toBe(12);
    const state = revealNextHint(payload, initialState());
    expect(scoreFor(payload, state, { baseScore: 12 })).toBe(0);
  });

  it("has no hints to reveal when the payload carries none", () => {
    const payload = payloadFor(TAMIZH);
    expect(nextHint(payload, initialState())).toBeNull();
    expect(revealNextHint(payload, initialState())).toEqual(initialState());
    expect(revealedHints(payload, initialState())).toEqual([]);
  });
});

describe("the third state - a real word, but not today's", () => {
  // A permutation of TAMIZH's ezhuthu, standing in for a co-anagram the bake
  // found in the served set. Escaped for the same NFC/NFD reason as TAMIZH.
  const OTHER_WORD = "\u0BAE\u0BBF\u0BA4\u0BB4\u0BCD";
  const OTHER = ["\u0BAE\u0BBF", "\u0BA4", "\u0BB4\u0BCD"];

  it("recognizes a listed alternative, and nothing else, as ezhuthu", () => {
    const payload = payloadFor(TAMIZH, { alsoValid: [OTHER_WORD] });
    const tray = buildTray(payload);
    expect(isAlsoValid(payload, tray, arrange(payload, OTHER))).toBe(true);
    // The answer itself is never an alternative, and neither is a third order.
    expect(isAlsoValid(payload, tray, arrange(payload, targetEzhuthu(payload)))).toBe(false);
    const third = [OTHER[2] as string, OTHER[1] as string, OTHER[0] as string];
    expect(isAlsoValid(payload, tray, arrange(payload, third))).toBe(false);
    // A payload with no alternatives has no third state at all.
    const plain = payloadFor(TAMIZH);
    expect(isAlsoValid(plain, buildTray(plain), arrange(plain, OTHER))).toBe(false);
  });

  it("costs exactly one attempt, the same as any other miss", () => {
    const payload = payloadFor(TAMIZH, { alsoValid: [OTHER_WORD] });
    const tray = buildTray(payload);
    const out = submitAttempt(payload, tray, arrange(payload, OTHER));
    expect(out.alternative).toBe(true);
    expect(out.correct).toBe(false);
    expect(out.exhausted).toBe(false);
    expect(out.attempt).toBe(OTHER_WORD);
    // Identical accounting to a plain wrong answer: one attempt spent, board
    // handed back. If it were free, shuffling until a word appears would be a
    // free probe and the attempts counter would start lying.
    const plain = payloadFor(TAMIZH);
    const wrong = submitAttempt(plain, buildTray(plain), arrange(plain, OTHER));
    expect(out.state.attempts).toBe(wrong.state.attempts);
    expect(out.state.placedTileIds).toEqual([]);
    expect(attemptsRemaining(payload, out.state)).toBe(2);
  });

  it("yields to the terminal message on the exhausting attempt", () => {
    const payload = payloadFor(TAMIZH, { attempts: 1, alsoValid: [OTHER_WORD] });
    const tray = buildTray(payload);
    const out = submitAttempt(payload, tray, arrange(payload, OTHER));
    // One message per moment: out-of-attempts wins, so the flip never fires.
    expect(out.exhausted).toBe(true);
    expect(out.alternative).toBe(false);
    expect(out.state.finished).toBe(true);
  });

  it("never fires on a win", () => {
    const payload = payloadFor(TAMIZH, { alsoValid: [OTHER_WORD] });
    const tray = buildTray(payload);
    const win = submitAttempt(payload, tray, arrange(payload, targetEzhuthu(payload)));
    expect(win.correct).toBe(true);
    expect(win.alternative).toBe(false);
  });
});

describe("a ladder of 1, 2 or 3 rungs", () => {
  const RUNGS = [
    { kind: "category", text: "a", cost: 1 },
    { kind: "first-ezhuthu", text: "b", cost: 2 },
    { kind: "meaning", text: "c", cost: 3 },
  ];

  // build_hints skips a rung the word cannot honestly fill, so a baked ladder is
  // 3, 2 or 1 rungs - nothing may assume three.
  it.each([1, 2, 3])("walks a %i-rung ladder in order and then stops", (length) => {
    const hints = RUNGS.slice(0, length);
    const payload = payloadFor(TAMIZH, { hints });
    let state = initialState();
    for (const rung of hints) {
      // The price the button discloses BEFORE the tap is the next rung's.
      expect(nextHint(payload, state)).toEqual(rung);
      state = revealNextHint(payload, state);
      expect(revealedHints(payload, state).at(-1)).toEqual(rung);
    }
    expect(nextHint(payload, state)).toBeNull();
    expect(revealedHints(payload, state)).toHaveLength(length);
    const spent = hints.reduce((sum, rung) => sum + rung.cost, 0);
    expect(scoreFor(payload, state)).toBe(3 * DEFAULT_POINTS_PER_EZHUTHU - spent);
  });
});

describe("keyboard contract", () => {
  it("maps Enter and Space to place, Backspace to undo, Escape to clear", () => {
    expect(keyToAction("Enter")).toBe("place");
    expect(keyToAction(" ")).toBe("place");
    expect(keyToAction("Backspace")).toBe("undo");
    expect(keyToAction("Delete")).toBe("undo");
    expect(keyToAction("Escape")).toBe("clear");
    expect(keyToAction("a")).toBeNull();
    expect(keyToAction("Tab")).toBeNull(); // Tab must stay the browser's own
  });
});

describe("state round-trip", () => {
  it("normalizes a persisted snapshot back to an identical in-progress state", () => {
    const payload = payloadFor(TAMIZH, { hints: [{ kind: "k", text: "t", cost: 1 }] });
    const target = targetEzhuthu(payload);
    const state = revealNextHint(payload, arrange(payload, target.slice(0, 2)));
    const roundTripped = normalizeState(JSON.parse(JSON.stringify(state)) as unknown);
    expect(roundTripped).toEqual(state);
    expect(placedEzhuthu(buildTray(payload), roundTripped)).toEqual(target.slice(0, 2));
  });

  it("falls back to a fresh state for a missing or malformed snapshot", () => {
    expect(normalizeState(null)).toEqual(initialState());
    expect(normalizeState("nope")).toEqual(initialState());
    expect(normalizeState({ placedTileIds: ["t1", 7, null] })).toEqual({
      ...initialState(),
      placedTileIds: ["t1"],
    });
  });
});

describe("labels", () => {
  it("uses the Tamil defaults and lets the config slice override any of them", () => {
    expect(resolveLabels()).toEqual(DEFAULT_LABELS);
    expect(resolveLabels({ labels: { hint: "Clue" } }).hint).toBe("Clue");
    expect(resolveLabels({ labels: { hint: "" } }).hint).toBe(DEFAULT_LABELS.hint);
    expect(resolveLabels({ labels: "nope" }).hint).toBe(DEFAULT_LABELS.hint);
  });

  it("takes the third state's wording from the Mode, which is where copy lives", () => {
    expect(DEFAULT_LABELS.alsoValid).not.toBe("");
    expect(resolveLabels({ labels: { alsoValid: "a word, not today's" } }).alsoValid).toBe(
      "a word, not today's",
    );
  });
});
