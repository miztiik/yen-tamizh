import { describe, expect, test, vi } from "vitest";

import {
  TIME_TRIAL_MODE_ID,
  Countdown,
  TimeTrialSupply,
  bestRunAt,
  bestRunsWith,
  formatClock,
  hasExpired,
  reframe,
  remainingMs,
  type BestRun,
} from "./TimeTrialMode";
import { InfiniteStream, type StreamStep } from "./InfiniteMode";
import type { PoolIndex, PoolItem, SchemaName, SchemaPayload } from "../contracts";

// A controllable clock and a controllable frame scheduler. Together they are
// what let the timer Oracle assert what the run does at a named instant instead
// of sleeping in real time - a test that sleeps proves the machine was busy,
// not that the arithmetic is right.
class FakeFrames {
  private t = 0;
  private queued: (() => void)[] = [];
  private nextHandle = 1;
  private readonly cancelled = new Set<number>();

  now = (): number => this.t;

  schedule = (callback: () => void): number => {
    const handle = this.nextHandle;
    this.nextHandle += 1;
    this.queued.push(() => {
      if (this.cancelled.has(handle)) return;
      callback();
    });
    return handle;
  };

  cancel = (handle: number): void => {
    this.cancelled.add(handle);
  };

  /** Advance the clock by `ms` and run whatever frame was pending. ONE frame. */
  tick(ms: number): void {
    this.t += ms;
    const due = this.queued;
    this.queued = [];
    for (const run of due) run();
  }

  /** Whether the loop is still asking for frames. */
  get pending(): number {
    return this.queued.length;
  }
}

/** A 60 Hz frame, to the microsecond the browser actually uses. */
const FRAME = 1000 / 60;

describe("remaining time is DERIVED from a monotonic delta", () => {
  test("it is the duration less the elapsed time, clamped at both ends", () => {
    expect(remainingMs(1000, 1000, 5000)).toBe(5000);
    expect(remainingMs(1000, 3000, 5000)).toBe(3000);
    expect(remainingMs(1000, 6000, 5000)).toBe(0);
    // Over-run reads as zero, never as a negative countdown.
    expect(remainingMs(1000, 60_000, 5000)).toBe(0);
    // A clock that went backwards cannot lengthen the run.
    expect(remainingMs(1000, 500, 5000)).toBe(5000);
  });

  test("a THROTTLED TAB that misses many frames still reads the right time", () => {
    // THE POINT OF DERIVING RATHER THAN DECREMENTING. A hidden tab is given
    // almost no frames, so a counter that subtracted a frame's worth of time
    // per frame would owe the player every second the browser skipped. Here one
    // frame arrives after a 30-second gap, and the remaining time is exactly
    // what the wall says it should be.
    const frames = new FakeFrames();
    const ticks: number[] = [];
    const clock = new Countdown({
      durationMs: 60_000,
      onTick: (left) => ticks.push(left),
      onExpire: () => undefined,
      now: frames.now,
      schedule: frames.schedule,
      cancel: frames.cancel,
    });
    clock.start();
    frames.tick(FRAME); // one ordinary frame
    frames.tick(30_000); // ...then the tab was hidden for thirty seconds
    expect(ticks.at(-1)).toBe(60_000 - 30_000 - FRAME);
    // And a decrementing counter would have got this wrong by 29.98 seconds:
    // two frames of 16.67 ms is all it would ever have subtracted.
    expect(ticks.at(-1)).not.toBeCloseTo(60_000 - 2 * FRAME, 0);
    clock.stop();
  });

  test("hasExpired asks the same derivation as a question", () => {
    expect(hasExpired(0, 4999, 5000)).toBe(false);
    expect(hasExpired(0, 5000, 5000)).toBe(true);
    expect(hasExpired(0, 5001, 5000)).toBe(true);
  });
});

describe("the clock reads M:SS and rounds UP to the second", () => {
  test("a full run shows its whole length on the first frame", () => {
    expect(formatClock(120_000)).toBe("2:00");
    expect(formatClock(120_000 - FRAME)).toBe("2:00");
  });

  test("the final second is visible for the whole of the final second", () => {
    expect(formatClock(1000)).toBe("0:01");
    expect(formatClock(1)).toBe("0:01");
    expect(formatClock(0)).toBe("0:00");
    expect(formatClock(-500)).toBe("0:00");
  });

  test("it pads the seconds so the readout never changes width", () => {
    expect(formatClock(65_000)).toBe("1:05");
    expect(formatClock(600_000)).toBe("10:00");
  });
});

describe("THE ORACLE: the run ends within one frame of the configured duration", () => {
  test("it does not end early, and it does not overrun by more than a frame", () => {
    const frames = new FakeFrames();
    const duration = 120_000;
    const expiredAt: number[] = [];
    const clock = new Countdown({
      durationMs: duration,
      onTick: () => undefined,
      onExpire: () => expiredAt.push(frames.now()),
      now: frames.now,
      schedule: frames.schedule,
      cancel: frames.cancel,
    });

    const startedAt = frames.now();
    clock.start();

    // Run a real 60 Hz frame budget, one frame at a time, and stop the instant
    // the run reports itself over.
    let frameCount = 0;
    while (expiredAt.length === 0 && frameCount < 10_000) {
      frames.tick(FRAME);
      frameCount += 1;
    }

    expect(expiredAt).toHaveLength(1);
    const endedAfter = (expiredAt[0] ?? 0) - startedAt;

    // (a) IT DOES NOT END EARLY.
    expect(endedAfter).toBeGreaterThanOrEqual(duration);
    // (b) IT DOES NOT OVERRUN BY MORE THAN ONE FRAME.
    expect(endedAfter - duration).toBeLessThan(FRAME);
    // The frame count is the honest reading of the same claim: 120 s at 60 Hz.
    expect(frameCount).toBe(Math.ceil(duration / FRAME));
    // And the loop stopped asking for frames the moment it fired.
    expect(frames.pending).toBe(0);
  });

  test("expiry fires exactly ONCE, however long the clock is left running", () => {
    const frames = new FakeFrames();
    let fired = 0;
    const clock = new Countdown({
      durationMs: 100,
      onTick: () => undefined,
      onExpire: () => {
        fired += 1;
      },
      now: frames.now,
      schedule: frames.schedule,
      cancel: frames.cancel,
    });
    clock.start();
    for (let i = 0; i < 50; i += 1) frames.tick(FRAME);
    expect(fired).toBe(1);
  });

  test("a run stopped by the player never expires afterwards", () => {
    const frames = new FakeFrames();
    let fired = 0;
    const clock = new Countdown({
      durationMs: 1000,
      onTick: () => undefined,
      onExpire: () => {
        fired += 1;
      },
      now: frames.now,
      schedule: frames.schedule,
      cancel: frames.cancel,
    });
    clock.start();
    frames.tick(FRAME);
    clock.stop();
    frames.tick(10_000);
    expect(fired).toBe(0);
    expect(clock.isRunning).toBe(false);
  });

  test("the first tick is the whole duration, emitted before any frame runs", () => {
    const frames = new FakeFrames();
    const ticks: number[] = [];
    const clock = new Countdown({
      durationMs: 5000,
      onTick: (left) => ticks.push(left),
      onExpire: () => undefined,
      now: frames.now,
      schedule: frames.schedule,
      cancel: frames.cancel,
    });
    clock.start();
    expect(ticks).toEqual([5000]);
    clock.stop();
  });

  test("nothing in the countdown path uses a timer", () => {
    // CLAUDE.md section 10: a Game-loop clock is requestAnimationFrame, never
    // setInterval or setTimeout. Asserted by SPYING on the globals rather than
    // by reading the source, so the claim survives a refactor.
    const setInterval_ = vi.spyOn(globalThis, "setInterval");
    const setTimeout_ = vi.spyOn(globalThis, "setTimeout");
    const frames = new FakeFrames();
    const clock = new Countdown({
      durationMs: 200,
      onTick: () => undefined,
      onExpire: () => undefined,
      now: frames.now,
      schedule: frames.schedule,
      cancel: frames.cancel,
    });
    clock.start();
    for (let i = 0; i < 20; i += 1) frames.tick(FRAME);
    expect(setInterval_).not.toHaveBeenCalled();
    expect(setTimeout_).not.toHaveBeenCalled();
    setInterval_.mockRestore();
    setTimeout_.mockRestore();
  });
});

describe("best runs are per run LENGTH, and local only", () => {
  const run = (durationSec: number, itemsCompleted: number, achievedOn: string): BestRun => ({
    durationSec,
    itemsCompleted,
    achievedOn,
  });

  test("the first run at a length always sets the record", () => {
    const { runs, isNewBest } = bestRunsWith([], run(120, 4, "2026-08-21"));
    expect(isNewBest).toBe(true);
    expect(runs).toEqual([run(120, 4, "2026-08-21")]);
  });

  test("a better run replaces the record and moves its date", () => {
    const before = [run(120, 4, "2026-08-20")];
    const { runs, isNewBest } = bestRunsWith(before, run(120, 7, "2026-08-21"));
    expect(isNewBest).toBe(true);
    expect(runs).toEqual([run(120, 7, "2026-08-21")]);
  });

  test("a worse run leaves the record - and its date - alone", () => {
    const before = [run(120, 7, "2026-08-20")];
    const { runs, isNewBest } = bestRunsWith(before, run(120, 3, "2026-08-21"));
    expect(isNewBest).toBe(false);
    expect(runs).toEqual(before);
  });

  test("EQUALLING your best is not beating it", () => {
    const before = [run(120, 7, "2026-08-20")];
    const { runs, isNewBest } = bestRunsWith(before, run(120, 7, "2026-08-21"));
    expect(isNewBest).toBe(false);
    expect(runs[0]?.achievedOn).toBe("2026-08-20");
  });

  test("a different run LENGTH is a different contest, not a challenger", () => {
    const before = [run(120, 7, "2026-08-20")];
    const { runs, isNewBest } = bestRunsWith(before, run(30, 2, "2026-08-21"));
    expect(isNewBest).toBe(true);
    expect(runs).toHaveLength(2);
    expect(bestRunAt(runs, 120)?.itemsCompleted).toBe(7);
    expect(bestRunAt(runs, 30)?.itemsCompleted).toBe(2);
  });

  test("the list can never hold two records at one length", () => {
    // The save contract states this invariant; it holds because the list is
    // BUILT this way, not because anything checks it on write.
    let runs: BestRun[] = [];
    for (let i = 1; i <= 25; i += 1) {
      runs = bestRunsWith(runs, run(120, i, "2026-08-21")).runs;
      runs = bestRunsWith(runs, run(30, i, "2026-08-21")).runs;
    }
    expect(runs).toHaveLength(2);
    expect(new Set(runs.map((entry) => entry.durationSec)).size).toBe(2);
  });

  test("an unset length has no record rather than a zero", () => {
    expect(bestRunAt([], 120)).toBeNull();
    expect(bestRunAt([run(30, 2, "2026-08-21")], 120)).toBeNull();
  });
});

// --------------------------------------------------------------------------
// The board supply: the Infinite stream, re-framed and fenced by the clock.
// Real pool payloads, a local loader, no network (Holy Law #7).
// --------------------------------------------------------------------------

const INDEX: PoolIndex = {
  version: "2026-08-21",
  changelog: [{ version: "2026-08-21", change: "test", why: "unit test" }],
  gameId: "anagram",
  totalCount: 2,
  items: [
    { id: "00001", difficulty: "medium" },
    { id: "00002", difficulty: "medium" },
  ],
};

function item(id: string): PoolItem {
  return {
    id,
    gameId: "anagram",
    packId: "ta-core",
    difficulty: "medium",
    payload: { word: "\u0b95", tiles: ["\u0b95"], attempts: 3 },
  };
}

function loader(): <K extends SchemaName>(url: string, name: K) => Promise<SchemaPayload[K]> {
  return async <K extends SchemaName>(url: string): Promise<SchemaPayload[K]> => {
    if (url.endsWith("index.json")) return INDEX as SchemaPayload[K];
    const id = url.slice(url.lastIndexOf("/") + 1, -".json".length);
    return item(id) as SchemaPayload[K];
  };
}

function stream(seen: string[]): InfiniteStream {
  return new InfiniteStream({
    games: ["anagram"],
    date: "2026-08-21",
    difficulty: "medium",
    seen: () => seen,
    load: loader(),
    base: "/",
  });
}

describe("the supply deals the Infinite pool, re-framed as a sprint", () => {
  test("a dealt board is framed as a TIME TRIAL session, not an infinite one", async () => {
    const supply = new TimeTrialSupply(stream([]), () => false);
    const outcome = await supply.next();
    expect(outcome?.status).toBe("ready");
    const step = (outcome as { status: "ready"; step: StreamStep }).step;
    expect(step.session.modeId).toBe(TIME_TRIAL_MODE_ID);
    expect(step.session.sessionId.startsWith(`${TIME_TRIAL_MODE_ID}-`)).toBe(true);
    // The board itself is untouched - same pool, same id, same anti-repeat key.
    expect(step.gameId).toBe("anagram");
    expect(step.seenKey).toBe("anagram/00001");
  });

  test("no board is dealt once the run is over", async () => {
    const supply = new TimeTrialSupply(stream([]), () => true);
    expect(await supply.next()).toBeNull();
  });

  test("a board whose fetch finishes AFTER the deadline is never dealt", async () => {
    // The deadline can pass while a board is in flight; dealing it then would
    // put a puzzle on screen that the run has already ended.
    let over = false;
    const supply = new TimeTrialSupply(stream([]), () => over);
    const inFlight = supply.next();
    over = true;
    expect(await inFlight).toBeNull();
  });

  test("re-framing changes the session and nothing else", () => {
    const original: StreamStep = {
      gameId: "wordle",
      id: "00007",
      seenKey: "wordle/00007",
      difficulty: "hard",
      session: {
        modeId: "infinite",
        packId: "ta-core",
        gameId: "wordle",
        sessionId: "infinite-wordle-00007",
        date: "2026-08-21",
        items: [{ gameId: "wordle", payload: { word: "x" } }],
      },
    };
    const framed = reframe(original);
    expect(framed.session.modeId).toBe(TIME_TRIAL_MODE_ID);
    expect(framed.session.sessionId).toBe("time-trial-wordle-00007");
    expect(framed.session.items).toBe(original.session.items);
    expect(framed.difficulty).toBe("hard");
    expect(original.session.modeId).toBe("infinite"); // the input is not mutated
  });
});
