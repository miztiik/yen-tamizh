// ORACLE (contract tier) - THE Row 16 claim: the four completion stats are
// derived from the emitted telemetry event stream and from NOTHING ELSE.
//
// TIME, INSTINCT, RETRIES and STREAK are what the completion moment shows
// (docs/concepts/journeys.md). Every one of them could have been a counter the
// Game kept and the save persisted - which is exactly the design that was
// refused, because a stat stored beside the events that produced it is a second
// copy of a fact, free to drift, and it would have grown the `save` contract a
// field per brag (Fowler).
//
// So the test is written the way the claim is: it builds a SYNTHETIC event
// stream by hand - no payload, no state, no Game, no storage - and asserts all
// four stats fall out of it. Nothing but `name` and `data` is available to the
// derivation, so a stat it could not compute here is a stat the shipped Game
// cannot compute either.

import { describe, expect, it } from "vitest";

import {
  DEFAULT_LABELS,
  deriveStats,
  formatDuration,
  markGlyph,
  rungMarks,
  shareText,
  type LadderEvent,
} from "./logic";

/** One `puzzle.attempt.submitted`, as the Game emits it. */
function attempt(attemptIndex: number, correct: boolean, elapsedMs: number): LadderEvent {
  return {
    name: "puzzle.attempt.submitted",
    data: { attemptIndex, attempt: "\u0bae\u0bc8", correct, elapsedMs },
  };
}

// A three-rung climb played the way a real one is: the first rung falls on the
// first pick (instinct), the second takes three (two retries), and the whole
// thing ran 95 seconds. The player arrived on a 4-day run.
const STREAM: LadderEvent[] = [
  { name: "puzzle.started", data: { steps: 2, rungs: 3, choices: 8, streak: 4 } },
  attempt(1, true, 8_000),
  attempt(1, false, 20_000),
  attempt(2, false, 41_000),
  attempt(3, true, 60_000),
  { name: "puzzle.completed", data: { score: 40, attempts: 4, elapsedMs: 95_000 } },
];

describe("the four completion stats come from the event stream alone (Oracle)", () => {
  const stats = deriveStats(STREAM);

  it("reads TIME off the completion event's own clock", () => {
    expect(stats.timeMs).toBe(95_000);
    expect(formatDuration(stats.timeMs)).toBe("1:35");
  });

  it("reads INSTINCT as the rungs climbed on the FIRST pick at that rung", () => {
    // `attemptIndex` is 1 exactly when nothing has been tried at this rung yet,
    // which is the whole definition of instinct - and it is already in the
    // catalog's attempt payload, so nothing had to be minted to count it.
    expect(stats.instinct).toBe(1);
    expect(stats.steps).toBe(2);
    expect(stats.climbed).toBe(2);
  });

  it("reads RETRIES as the picks that did not climb", () => {
    expect(stats.retries).toBe(2);
  });

  it("reads STREAK off the run the save already keeps, never a parallel count", () => {
    // The Mode reads it from StorageService and hands it down; the Game stamps
    // it into `puzzle.started` and never counts a day itself.
    expect(stats.streak).toBe(4);
  });

  it("derives every one of them with no payload, no state and no storage", () => {
    // The signature IS the proof: `deriveStats` takes the stream and nothing
    // else, so there is no second source it could have consulted.
    expect(deriveStats.length).toBe(1);
    expect(stats.score).toBe(40);
    expect(stats.completed).toBe(true);
  });
});

describe("what the stream does NOT say, the stats do not claim", () => {
  it("reads an unfinished climb as unfinished, with the time it has run", () => {
    const partial = deriveStats(STREAM.slice(0, 3));
    expect(partial.completed).toBe(false);
    expect(partial.score).toBe(0);
    expect(partial.climbed).toBe(1);
    expect(partial.retries).toBe(1);
    expect(partial.timeMs).toBe(20_000);
  });

  it("reads an empty stream as a zeroed row rather than a crash", () => {
    expect(deriveStats([])).toEqual({
      timeMs: 0,
      instinct: 0,
      retries: 0,
      streak: 0,
      steps: 0,
      climbed: 0,
      revealed: 0,
      score: 0,
      completed: false,
    });
  });

  it("ignores an event whose data is missing or the wrong shape", () => {
    const junk: LadderEvent[] = [
      { name: "puzzle.started" },
      { name: "puzzle.attempt.submitted", data: { correct: "yes" } },
      { name: "mode.session.started", data: { streak: 99 } },
      { name: "puzzle.completed", data: { score: "40" } },
    ];
    const stats = deriveStats(junk);
    expect(stats.streak).toBe(0);
    expect(stats.score).toBe(0);
    // A non-boolean `correct` is not a climb, so it counts as a retry.
    expect(stats.retries).toBe(1);
    expect(stats.instinct).toBe(0);
  });

  it("counts a bought rung as bought, and never as instinct", () => {
    const bought = deriveStats([
      { name: "puzzle.started", data: { steps: 2, streak: 1 } },
      attempt(1, true, 5_000),
      { name: "puzzle.hint.used", data: { kind: "rung", cost: 20 } },
      { name: "puzzle.completed", data: { score: 20, elapsedMs: 30_000 } },
    ]);
    expect(bought.climbed).toBe(1);
    expect(bought.revealed).toBe(1);
    expect(bought.instinct).toBe(1);
  });

  it("prefers a streak tick in the stream over the run the player arrived with", () => {
    const ticked = deriveStats([
      ...STREAM,
      { name: "streak.updated", data: { before: 4, after: 5 } },
    ]);
    expect(ticked.streak).toBe(5);
  });
});

describe("the ladder marks, and the card built from them", () => {
  it("marks each rung by how it was resolved, in climb order", () => {
    expect(rungMarks(STREAM)).toEqual(["first", "retry"]);
  });

  it("marks a bought rung apart from a climbed one", () => {
    expect(
      rungMarks([
        { name: "puzzle.hint.used", data: { kind: "rung" } },
        attempt(1, false, 1),
        attempt(2, true, 2),
      ]),
    ).toEqual(["revealed", "retry"]);
  });

  it("gives the three outcomes three different glyphs", () => {
    const glyphs = new Set((["first", "retry", "revealed"] as const).map(markGlyph));
    expect(glyphs.size).toBe(3);
  });

  it("prints a card whose every line is a stat the stream stated", () => {
    const stats = deriveStats(STREAM);
    const text = shareText(stats, rungMarks(STREAM), DEFAULT_LABELS);
    const lines = text.split("\n");
    expect(lines[0]).toBe(DEFAULT_LABELS.prompt);
    expect(lines[1]).toBe(`${markGlyph("first")}${markGlyph("retry")}`);
    expect(lines[2]).toBe(`${DEFAULT_LABELS.statTime} 1:35`);
    expect(lines[3]).toBe(`${DEFAULT_LABELS.statInstinct} 1/2`);
    expect(lines[4]).toBe(`${DEFAULT_LABELS.statRetries} 2`);
    expect(lines[5]).toBe(`${DEFAULT_LABELS.statStreak} 4`);
    expect(lines).toHaveLength(6);
  });

  it("prints the Mode's wording when the Mode overrode it", () => {
    const stats = deriveStats(STREAM);
    const text = shareText(stats, rungMarks(STREAM), {
      ...DEFAULT_LABELS,
      statTime: "Time",
    });
    expect(text).toContain("Time 1:35");
  });

  it("rounds the clock to m:ss and never to a bare millisecond count", () => {
    expect(formatDuration(0)).toBe("0:00");
    expect(formatDuration(9_400)).toBe("0:09");
    expect(formatDuration(59_600)).toBe("1:00");
    expect(formatDuration(3_600_000)).toBe("60:00");
    expect(formatDuration(-5)).toBe("0:00");
  });
});
