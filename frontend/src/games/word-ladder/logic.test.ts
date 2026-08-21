// Unit tier - the word-ladder mechanic's pure core (docs/concepts/games.md
// `word-ladder`). Node env, no DOM, no mocks: every rule is a function of its
// arguments, so the whole mechanic is provable here and the Svelte view stays a
// projection.
//
// The fixtures are REAL climbs. `CLIMB` is the committed contract fixture
// (datasets/fixtures/contracts/word-ladder-puzzle_valid.json), lifted from the
// served set through the real generator. `CLUSTERS` is hand-built for one
// purpose the real climb cannot serve: proving the rung rule is stated over
// EZHUTHU. It carries a two-part matra and a pulli/mei cluster, both of which a
// code-point walk would split - which is exactly how a ladder could climb one
// rung while claiming to have added nothing.

import { describe, expect, it } from "vitest";

import { segment } from "../../tamil/ezhuthu";

import {
  DEFAULT_LABELS,
  DEFAULT_POINTS_PER_RUNG,
  alternativeFor,
  buildChoices,
  climbs,
  currentRung,
  fullScore,
  height,
  initialState,
  keyToAction,
  ladderRows,
  nextReveal,
  normalizeState,
  pickChoice,
  remainingChoices,
  resolveLabels,
  resolveStreak,
  revealNext,
  scoreFor,
  stepCount,
  targetRung,
  tileKey,
  wasRevealed,
  type WordLadderPayload,
  type WordLadderState,
} from "./logic";

// "\u0B92\u0BB0\u0BC1" (oru) -> "\u0B92\u0BB0\u0BC1\u0BAE\u0BC8" (orumai)
// -> "\u0B92\u0BB0\u0BC1\u0BAE\u0BC8\u0BAF" (orumaiya). The middle rung is
// reachable three OTHER ways from the same bank, which is what makes the
// third state testable without inventing a payload.
const CLIMB: WordLadderPayload = {
  rungs: [
    { word: "\u0b92\u0bb0\u0bc1", meaning: "\u0b85\u0bb4\u0bbf\u0b9e\u0bcd\u0b9a\u0bbf\u0bb2\u0bcd" },
    {
      word: "\u0b92\u0bb0\u0bc1\u0bae\u0bc8",
      meaning: "\u0b87\u0bb1\u0bc8\u0baf\u0bc1\u0ba3\u0bb0\u0bcd\u0bb5\u0bc1",
      alsoValid: [
        "\u0b92\u0bb0\u0bc1\u0b95\u0bc8",
        "\u0b92\u0bb0\u0bc1\u0bae\u0bbe",
        "\u0b92\u0bb0\u0bc1\u0bb5\u0bc1",
      ],
    },
    { word: "\u0b92\u0bb0\u0bc1\u0bae\u0bc8\u0baf", meaning: null },
  ],
  choices: [
    "\u0b9a\u0bc8",
    "\u0bae\u0bc8",
    "\u0bb5\u0bc1",
    "\u0baf",
    "\u0b9a\u0bbf",
    "\u0bae\u0bbe",
    "\u0baa\u0bca",
    "\u0b95\u0bc8",
  ],
  timeLimitSec: 0,
} as unknown as WordLadderPayload;

// The cluster ladder. Not real Tamil words, and deliberately so: `climbs()` is
// pure multiset arithmetic over ezhuthu with no wordlist behind it, so this
// fixture can ask the one question the real climb cannot. Rung 1 starts on a
// pulli/mei cluster ("\u0B95\u0BAE\u0BCD" is TWO ezhuthu and THREE code
// points), rung 2 adds a two-part matra, and rung 3 adds another that BRACKETS
// its consonant and lands at the FRONT of the word.
const CLUSTERS: WordLadderPayload = {
  rungs: [
    // "\u0B95\u0BAE\u0BCD" = ka + m-with-pulli: 2 ezhuthu, 3 code points.
    { word: "\u0b95\u0bae\u0bcd", meaning: null },
    // + "\u0BB2\u0BC8" (lai, a two-part matra) -> "\u0B95\u0BAE\u0BCD\u0BB2\u0BC8".
    { word: "\u0b95\u0bae\u0bcd\u0bb2\u0bc8", meaning: null },
    // + "\u0B95\u0BCB" (ko, a two-part matra that BRACKETS its consonant),
    // rearranged to the front.
    { word: "\u0b95\u0bcb\u0b95\u0bae\u0bcd\u0bb2\u0bc8", meaning: null },
  ],
  choices: ["\u0bb2\u0bc8", "\u0b95\u0bcb", "\u0bae\u0bcd", "\u0b95"],
  timeLimitSec: 0,
} as unknown as WordLadderPayload;

/** Find the bank tile carrying an ezhuthu (the id play is driven by). */
function idOf(payload: WordLadderPayload, ezhuthu: string): string {
  const choice = buildChoices(payload).find((one) => one.ezhuthu === ezhuthu);
  if (choice === undefined) throw new Error(`no bank tile for ${ezhuthu}`);
  return choice.id;
}

/** Play a run of picks, returning the state they leave behind. */
function play(payload: WordLadderPayload, ezhuthu: readonly string[]): WordLadderState {
  const choices = buildChoices(payload);
  let state = initialState();
  let picksHere = 0;
  for (const unit of ezhuthu) {
    const outcome = pickChoice(
      payload,
      choices,
      state,
      idOf(payload, unit),
      picksHere + 1,
    );
    if (outcome === null) continue;
    state = outcome.state;
    picksHere = outcome.verdict === "climb" ? 0 : outcome.attemptIndex;
  }
  return state;
}

describe("the rung rule is stated over ezhuthu, never over code points", () => {
  it("accepts a climb that adds exactly one ezhuthu", () => {
    expect(climbs("\u0b92\u0bb0\u0bc1", "\u0bae\u0bc8", "\u0b92\u0bb0\u0bc1\u0bae\u0bc8")).toBe(
      true,
    );
  });

  it("accepts a climb that rearranges every tile it already had", () => {
    // The added "\u0B95\u0BCB" lands at the FRONT of the word, so the rung is
    // judged by its tiles rather than by where the new one went.
    expect(
      climbs("\u0b95\u0bae\u0bcd\u0bb2\u0bc8", "\u0b95\u0bcb", "\u0b95\u0bcb\u0b95\u0bae\u0bcd\u0bb2\u0bc8"),
    ).toBe(true);
  });

  it("refuses a mei cluster split into its consonant and its pulli", () => {
    // "\u0B95\u0BAE\u0BCD" is 2 ezhuthu and 3 code points. A code-point walk
    // would see "\u0BCD" as an addable unit; the ezhuthu library does not.
    expect(segment("\u0b95\u0bae\u0bcd")).toEqual(["\u0b95", "\u0bae\u0bcd"]);
    expect(climbs("\u0b95\u0bae", "\u0bcd", "\u0b95\u0bae\u0bcd")).toBe(false);
  });

  it("refuses a two-part matra split from the consonant it belongs to", () => {
    // "\u0BB2\u0BC8" is ONE ezhuthu; adding the bare vowel sign is not a rung.
    expect(segment("\u0b95\u0bae\u0bcd\u0bb2\u0bc8")).toEqual([
      "\u0b95",
      "\u0bae\u0bcd",
      "\u0bb2\u0bc8",
    ]);
    expect(climbs("\u0b95\u0bae\u0bcd\u0bb2", "\u0bc8", "\u0b95\u0bae\u0bcd\u0bb2\u0bc8")).toBe(
      false,
    );
  });

  it("refuses a pick that adds two ezhuthu or none", () => {
    expect(climbs("\u0b92\u0bb0\u0bc1", "\u0bae\u0bc8\u0baf", "\u0b92\u0bb0\u0bc1\u0bae\u0bc8")).toBe(
      false,
    );
    expect(climbs("\u0b92\u0bb0\u0bc1", "\u0bae\u0bc8", "\u0b92\u0bb0\u0bc1")).toBe(false);
  });

  it("keys two words the same exactly when the same tiles spell both", () => {
    expect(tileKey(segment("\u0b92\u0bb0\u0bc1\u0bae\u0bc8"))).toBe(
      tileKey(segment("\u0bae\u0bc8\u0b92\u0bb0\u0bc1")),
    );
    expect(tileKey(segment("\u0b92\u0bb0\u0bc1"))).not.toBe(
      tileKey(segment("\u0b92\u0bb0\u0bc1\u0bae\u0bc8")),
    );
  });
});

describe("picking one tile out of the bank", () => {
  it("climbs the rung and spends the tile", () => {
    const choices = buildChoices(CLIMB);
    const outcome = pickChoice(
      CLIMB,
      choices,
      initialState(),
      idOf(CLIMB, "\u0bae\u0bc8"),
      1,
    );
    expect(outcome?.verdict).toBe("climb");
    expect(outcome?.spells).toBe("\u0b92\u0bb0\u0bc1\u0bae\u0bc8");
    expect(height(outcome?.state ?? initialState())).toBe(1);
    expect(remainingChoices(choices, outcome?.state ?? initialState())).toHaveLength(7);
  });

  it("answers a pick that spells ANOTHER served word rather than rejecting it", () => {
    const outcome = pickChoice(
      CLIMB,
      buildChoices(CLIMB),
      initialState(),
      idOf(CLIMB, "\u0b95\u0bc8"),
      1,
    );
    expect(outcome?.verdict).toBe("also-valid");
    expect(outcome?.spells).toBe("\u0b92\u0bb0\u0bc1\u0b95\u0bc8");
    // Nothing was spent: a ladder charges time, not tiles.
    expect(height(outcome?.state ?? initialState())).toBe(0);
    expect(outcome?.state.misses).toBe(1);
  });

  it("costs a miss and nothing else when the pick spells no word at all", () => {
    const outcome = pickChoice(
      CLIMB,
      buildChoices(CLIMB),
      initialState(),
      idOf(CLIMB, "\u0b9a\u0bbf"),
      1,
    );
    expect(outcome?.verdict).toBe("miss");
    expect(outcome?.spells).toBeNull();
    expect(outcome?.state.misses).toBe(1);
    expect(outcome?.state.finished).toBe(false);
  });

  it("refuses a tile that is already spent, and every pick once the climb is over", () => {
    const choices = buildChoices(CLIMB);
    const done = play(CLIMB, ["\u0bae\u0bc8", "\u0baf"]);
    expect(done.finished).toBe(true);
    expect(pickChoice(CLIMB, choices, done, idOf(CLIMB, "\u0b9a\u0bc8"), 1)).toBeNull();
    const midway = play(CLIMB, ["\u0bae\u0bc8"]);
    expect(pickChoice(CLIMB, choices, midway, idOf(CLIMB, "\u0bae\u0bc8"), 1)).toBeNull();
  });

  it("names the other served word a pick spells, from the rung's own list", () => {
    expect(
      alternativeFor("\u0b92\u0bb0\u0bc1", "\u0bb5\u0bc1", CLIMB.rungs[1]),
    ).toBe("\u0b92\u0bb0\u0bc1\u0bb5\u0bc1");
    expect(alternativeFor("\u0b92\u0bb0\u0bc1", "\u0b9a\u0bbf", CLIMB.rungs[1])).toBeNull();
  });
});

describe("the climb, its shape and its score", () => {
  it("has one fewer step than it has rungs - the first one is given", () => {
    expect(CLIMB.rungs).toHaveLength(3);
    expect(stepCount(CLIMB)).toBe(2);
  });

  it("stands on the given rung and aims at the one above it", () => {
    const fresh = initialState();
    expect(currentRung(CLIMB, fresh).word).toBe("\u0b92\u0bb0\u0bc1");
    expect(targetRung(CLIMB, fresh)?.word).toBe("\u0b92\u0bb0\u0bc1\u0bae\u0bc8");
    const done = play(CLIMB, ["\u0bae\u0bc8", "\u0baf"]);
    expect(currentRung(CLIMB, done).word).toBe("\u0b92\u0bb0\u0bc1\u0bae\u0bc8\u0baf");
    expect(targetRung(CLIMB, done)).toBeNull();
  });

  it("pays per rung climbed, in proportion, and pays nothing for a revealed one", () => {
    expect(fullScore(CLIMB)).toBe(stepCount(CLIMB) * DEFAULT_POINTS_PER_RUNG);
    expect(scoreFor(CLIMB, initialState())).toBe(0);
    expect(scoreFor(CLIMB, play(CLIMB, ["\u0bae\u0bc8"]))).toBe(DEFAULT_POINTS_PER_RUNG);
    const won = play(CLIMB, ["\u0bae\u0bc8", "\u0baf"]);
    expect(won.score).toBe(fullScore(CLIMB));
    expect(won.solved).toBe(true);
  });

  it("charges nothing for a miss - a wrong pick costs time, not points", () => {
    const stumbled = play(CLIMB, ["\u0b9a\u0bbf", "\u0b95\u0bc8", "\u0bae\u0bc8", "\u0baf"]);
    expect(stumbled.misses).toBe(2);
    expect(stumbled.score).toBe(fullScore(CLIMB));
    expect(stumbled.solved).toBe(true);
  });

  it("takes a configured base score over the per-rung rate", () => {
    expect(fullScore(CLIMB, { baseScore: 55 })).toBe(55);
  });
});

describe("the reveal, and what it costs", () => {
  it("hands over the next rung, spends its tile, and pays nothing for it", () => {
    const choices = buildChoices(CLIMB);
    const before = initialState();
    expect(nextReveal(CLIMB, before)?.word).toBe("\u0b92\u0bb0\u0bc1\u0bae\u0bc8");
    const outcome = revealNext(CLIMB, choices, before);
    expect(outcome.word).toBe("\u0b92\u0bb0\u0bc1\u0bae\u0bc8");
    expect(outcome.cost).toBe(DEFAULT_POINTS_PER_RUNG);
    expect(height(outcome.state)).toBe(1);
    expect(wasRevealed(outcome.state, 0)).toBe(true);
    expect(outcome.state.score).toBe(0);
  });

  it("leaves the climber everything they earned below the rung they bought", () => {
    const choices = buildChoices(CLIMB);
    const climbed = play(CLIMB, ["\u0bae\u0bc8"]);
    const bought = revealNext(CLIMB, choices, climbed);
    expect(bought.state.finished).toBe(true);
    expect(bought.state.solved).toBe(false);
    expect(bought.state.score).toBe(DEFAULT_POINTS_PER_RUNG);
  });

  it("offers nothing once the climb is over", () => {
    const done = play(CLIMB, ["\u0bae\u0bc8", "\u0baf"]);
    expect(nextReveal(CLIMB, done)).toBeNull();
    expect(revealNext(CLIMB, buildChoices(CLIMB), done).word).toBeNull();
  });
});

describe("the ladder as the board renders it", () => {
  it("prints the given rung, blanks everything above, and badges what was added", () => {
    const rows = ladderRows(CLIMB, buildChoices(CLIMB), initialState());
    expect(rows.map((row) => row.status)).toEqual(["given", "target", "locked"]);
    expect(rows[0]?.word).toBe("\u0b92\u0bb0\u0bc1");
    expect(rows[0]?.added).toBeNull();
    // A rung above the player carries NO word: the climb is the guess.
    expect(rows[1]?.word).toBeNull();
    expect(rows[2]?.word).toBeNull();
  });

  it("badges each resolved rung with the one ezhuthu it cost", () => {
    const rows = ladderRows(CLIMB, buildChoices(CLIMB), play(CLIMB, ["\u0bae\u0bc8"]));
    expect(rows[1]?.status).toBe("climbed");
    expect(rows[1]?.added).toBe("\u0bae\u0bc8");
    expect(rows[1]?.word).toBe("\u0b92\u0bb0\u0bc1\u0bae\u0bc8");
    expect(rows[1]?.meaning).toBe("\u0b87\u0bb1\u0bc8\u0baf\u0bc1\u0ba3\u0bb0\u0bcd\u0bb5\u0bc1");
    expect(rows[2]?.status).toBe("target");
  });

  it("badges a bought rung too, and marks it as bought rather than climbed", () => {
    const bought = revealNext(CLIMB, buildChoices(CLIMB), initialState()).state;
    const rows = ladderRows(CLIMB, buildChoices(CLIMB), bought);
    expect(rows[1]?.status).toBe("revealed");
    expect(rows[1]?.added).toBe("\u0bae\u0bc8");
  });

  it("renders a cluster ladder without ever splitting an ezhuthu", () => {
    const climbed = play(CLUSTERS, ["\u0bb2\u0bc8", "\u0b95\u0bcb"]);
    expect(climbed.solved).toBe(true);
    const rows = ladderRows(CLUSTERS, buildChoices(CLUSTERS), climbed);
    expect(rows.map((row) => row.added)).toEqual([null, "\u0bb2\u0bc8", "\u0b95\u0bcb"]);
  });
});

describe("restoring a persisted snapshot", () => {
  it("round-trips a mid-ladder climb", () => {
    const choices = buildChoices(CLIMB);
    const midway = play(CLIMB, ["\u0b9a\u0bbf", "\u0bae\u0bc8"]);
    const restored = normalizeState(CLIMB, choices, JSON.parse(JSON.stringify(midway)));
    expect(height(restored)).toBe(1);
    expect(restored.finished).toBe(false);
    expect(restored.score).toBe(DEFAULT_POINTS_PER_RUNG);
    expect(ladderRows(CLIMB, choices, restored)[1]?.added).toBe("\u0bae\u0bc8");
  });

  it("round-trips a finished climb, revealed rungs and all", () => {
    const choices = buildChoices(CLIMB);
    const bought = revealNext(CLIMB, choices, play(CLIMB, ["\u0bae\u0bc8"])).state;
    const restored = normalizeState(CLIMB, choices, JSON.parse(JSON.stringify(bought)));
    expect(restored.finished).toBe(true);
    expect(restored.solved).toBe(false);
    expect(restored.revealedSteps).toEqual([1]);
  });

  it("restores as far as it honestly can from a save of another ladder", () => {
    const choices = buildChoices(CLIMB);
    // The first id climbs; the second names a tile that does not.
    const foreign = { spentChoiceIds: ["c1", "c0"], revealedSteps: [], misses: 4 };
    const restored = normalizeState(CLIMB, choices, foreign);
    expect(height(restored)).toBe(1);
    expect(restored.misses).toBe(4);
  });

  it("reads garbage as an untouched ladder rather than crashing", () => {
    const choices = buildChoices(CLIMB);
    for (const raw of [null, undefined, 7, "x", {}, { spentChoiceIds: [1, 2] }]) {
      const restored = normalizeState(CLIMB, choices, raw);
      expect(height(restored)).toBe(0);
      expect(restored.finished).toBe(false);
    }
  });
});

describe("the injected slice", () => {
  it("takes a Mode's wording and keeps the defaults for anything it omits", () => {
    const labels = resolveLabels({ labels: { statTime: "T", alsoValid: "" } });
    expect(labels.statTime).toBe("T");
    // An empty override is not an override - it would blank a control.
    expect(labels.alsoValid).toBe(DEFAULT_LABELS.alsoValid);
    expect(resolveLabels({}).prompt).toBe(DEFAULT_LABELS.prompt);
    expect(resolveLabels({ labels: 7 }).prompt).toBe(DEFAULT_LABELS.prompt);
  });

  it("reads the streak the Mode handed down, and nothing else", () => {
    expect(resolveStreak({ streak: 12 })).toBe(12);
    expect(resolveStreak({ streak: 3.7 })).toBe(3);
    // Absent, negative, or the wrong type all read as a zero run.
    expect(resolveStreak({})).toBe(0);
    expect(resolveStreak({ streak: -4 })).toBe(0);
    expect(resolveStreak({ streak: "9" })).toBe(0);
  });

  it("maps only the keys that mean a pick", () => {
    expect(keyToAction("Enter")).toBe("pick");
    expect(keyToAction(" ")).toBe("pick");
    expect(keyToAction("a")).toBeNull();
  });
});
