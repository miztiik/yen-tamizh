// TimeTrialMode - the sprint (docs/concepts/modes.md `time-trial`).
//
// This Mode is the Infinite stream with a clock on it, and that is the whole
// design: it deals from the SAME pre-generated pools (Row 22), rotates the SAME
// ring of Games, and adds exactly one thing a stream does not have - an end.
// So it is a new SESSION FRAMING and not a new Game, and it reuses
// `InfiniteStream` rather than re-implementing a pool reader that would then be
// free to drift from the one the Infinite Mode uses.
//
// THE CLOCK IS THE CONTRACT, and two properties make it honest:
//
//   - IT IS DERIVED, NEVER DECREMENTED. Remaining time is
//     `duration - (now - startedAt)` against a MONOTONIC clock, recomputed from
//     scratch every frame. A counter that subtracts a frame's worth of time per
//     frame drifts by exactly as much time as the browser declined to give it,
//     and a backgrounded tab is given almost none - so a player who switched
//     apps for thirty seconds would come back to a clock that owed them thirty
//     seconds they had already spent. Deriving costs the same arithmetic and
//     cannot be wrong.
//   - IT IS DRIVEN BY `requestAnimationFrame`, never `setInterval` or
//     `setTimeout` (CLAUDE.md section 10). rAF is the browser's own frame
//     clock: it fires in step with the paint the countdown is being drawn into,
//     it is throttled rather than queued when the tab is hidden, and it costs
//     nothing when nothing is painting. A timer loop would fight the render
//     loop for the main thread and still be less accurate.
//
// The clock source is `performance.now()` - a monotonic reading unaffected by
// the wall clock moving - so changing the device's time mid-run cannot lengthen
// or end it.
//
// WHAT A HIDDEN TAB DOES, stated because it is a design position and not an
// accident: a browser stops delivering frames to a background tab entirely, so
// the readout FREEZES while the player is elsewhere and the run ends on the
// first frame after they come back. That is the behaviour worth having. The
// player gains nothing by hiding the tab - the elapsed time is measured against
// the clock, not against the frames they were given, so they return to a run
// that is already over rather than to the time they left on it - and a run that
// ended and scored itself while nobody was watching would be worse than one
// that waits to be seen.

import type { Save } from "../contracts";
import { InfiniteStream, type StreamOutcome, type StreamStep } from "./InfiniteMode";

/** The Mode's stable identifier (the `modeId` in the save and in telemetry). */
export const TIME_TRIAL_MODE_ID = "time-trial";

/** One recorded best run, as the save spells it. */
export type BestRun = NonNullable<Save["bestTimeTrialRuns"]>[number];

/**
 * Milliseconds left in a run, given when it started and what time it is now.
 *
 * Clamped to `[0, durationMs]` at both ends. The upper clamp matters as much as
 * the lower one: a monotonic clock cannot run backwards, but an injected one in
 * a test can, and a countdown that reads longer than the run it belongs to is a
 * lie whatever produced it.
 */
export function remainingMs(startedAt: number, now: number, durationMs: number): number {
  const elapsed = now - startedAt;
  if (elapsed <= 0) return durationMs;
  if (elapsed >= durationMs) return 0;
  return durationMs - elapsed;
}

/** Whether the run is over - the same derivation, asked as a question. */
export function hasExpired(startedAt: number, now: number, durationMs: number): boolean {
  return remainingMs(startedAt, now, durationMs) === 0;
}

/**
 * The countdown as `M:SS`, rounded UP to the second.
 *
 * Rounding up is what makes the last second visible: a run of 120 s shows 2:00
 * on its first frame rather than 1:59, and it shows 0:01 for the whole of the
 * final second rather than sitting on 0:00 while the board is still playable.
 * The clock reaches 0:00 exactly when the run is over and not a frame before.
 */
export function formatClock(ms: number): string {
  const total = Math.ceil(Math.max(0, ms) / 1000);
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

/**
 * The best-run list after a finished run, and whether the run beat the record.
 *
 * A run is only ever compared against runs of ITS OWN LENGTH: `durationSec` is
 * a config knob, so a two-minute sprint and a thirty-second one are different
 * contests and a record set at one can never be beaten from the other. The list
 * is therefore keyed by run length, and building it here - rather than checking
 * for a duplicate on write - is what guarantees the "one best per length"
 * invariant the Pydantic model states: this function cannot produce a second
 * entry for a length that already has one.
 *
 * A tie does NOT replace the record. Equalling your best is not beating it, and
 * moving the date would quietly rewrite when the record was set.
 */
export function bestRunsWith(
  existing: readonly BestRun[],
  run: BestRun,
): { runs: BestRun[]; isNewBest: boolean } {
  const previous = existing.find((entry) => entry.durationSec === run.durationSec);
  if (previous !== undefined && previous.itemsCompleted >= run.itemsCompleted) {
    return { runs: [...existing], isNewBest: false };
  }
  const others = existing.filter((entry) => entry.durationSec !== run.durationSec);
  return { runs: [...others, run], isNewBest: true };
}

/** The record standing at this run length, or `null` when none has been set. */
export function bestRunAt(
  runs: readonly BestRun[],
  durationSec: number,
): BestRun | null {
  return runs.find((entry) => entry.durationSec === durationSec) ?? null;
}

/** Schedule one frame; the browser's `requestAnimationFrame` satisfies it. */
export type FrameScheduler = (callback: () => void) => number;
/** Cancel a scheduled frame; the browser's `cancelAnimationFrame` satisfies it. */
export type FrameCanceller = (handle: number) => void;

export interface CountdownDeps {
  durationMs: number;
  /** Called once per frame with the derived remaining time. */
  onTick: (remainingMs: number) => void;
  /** Called on the FIRST frame at or after the deadline, then never again. */
  onExpire: () => void;
  /** Monotonic clock; defaults to `performance.now()`. */
  now?: () => number;
  /** Defaults to `requestAnimationFrame`. */
  schedule?: FrameScheduler;
  /** Defaults to `cancelAnimationFrame`. */
  cancel?: FrameCanceller;
}

/**
 * The run clock: a rAF loop that derives the remaining time every frame and
 * fires once when it reaches zero.
 *
 * The loop does no work beyond one subtraction and one comparison, so it cannot
 * be what drops a frame (Carmack). Its clock and its scheduler are BOTH
 * injectable, which is what lets the timer Oracle drive it frame by frame
 * against a controlled clock instead of sleeping in real time - a test that
 * sleeps proves the machine was busy, not that the arithmetic is right.
 */
export class Countdown {
  private readonly deps: CountdownDeps;
  private readonly now: () => number;
  private readonly schedule: FrameScheduler;
  private readonly cancelFrame: FrameCanceller;

  private startedAt = 0;
  private handle: number | null = null;
  private running = false;
  private fired = false;

  constructor(deps: CountdownDeps) {
    this.deps = deps;
    this.now = deps.now ?? (() => performance.now());
    this.schedule = deps.schedule ?? ((callback) => requestAnimationFrame(() => callback()));
    this.cancelFrame = deps.cancel ?? ((handle) => cancelAnimationFrame(handle));
  }

  /** The instant the run began, on the injected monotonic clock. */
  get startedAtMs(): number {
    return this.startedAt;
  }

  /** Whether the clock is still counting. */
  get isRunning(): boolean {
    return this.running;
  }

  /** Milliseconds left right now, without waiting for a frame. */
  get remaining(): number {
    return remainingMs(this.startedAt, this.now(), this.deps.durationMs);
  }

  /** Start the run. The first tick is emitted immediately, not a frame later. */
  start(): void {
    if (this.running) return;
    this.startedAt = this.now();
    this.running = true;
    this.fired = false;
    this.deps.onTick(this.deps.durationMs);
    this.queue();
  }

  /** Stop counting (the player left, or the run ended). Idempotent. */
  stop(): void {
    this.running = false;
    if (this.handle !== null) {
      this.cancelFrame(this.handle);
      this.handle = null;
    }
  }

  private queue(): void {
    this.handle = this.schedule(() => {
      this.handle = null;
      this.frame();
    });
  }

  private frame(): void {
    if (!this.running) return;
    const left = this.remaining;
    this.deps.onTick(left);
    if (left > 0) {
      this.queue();
      return;
    }
    // Expiry ends the loop here rather than on the next frame, so the session
    // ends on the FIRST frame at or after the deadline - which is the tightest
    // a frame-driven clock can be, and what the Oracle measures.
    this.stop();
    if (!this.fired) {
      this.fired = true;
      this.deps.onExpire();
    }
  }
}

/**
 * Re-frame one dealt board as a TIME TRIAL session.
 *
 * The stream builds its steps for the Infinite Mode, and a Session carries the
 * `modeId` the save is keyed by - so handing an infinite-framed session to the
 * runner would file a sprint's progress under the Infinite Mode's key and let
 * one Mode's half-finished board resume inside the other. Re-framing is a
 * rename of two fields and it is done here, once, rather than by teaching the
 * stream about a second Mode.
 */
export function reframe(step: StreamStep): StreamStep {
  return {
    ...step,
    session: {
      ...step.session,
      modeId: TIME_TRIAL_MODE_ID,
      sessionId: `${TIME_TRIAL_MODE_ID}-${step.gameId}-${step.id}`,
    },
  };
}

/**
 * The board supply for a run: the Infinite stream, re-framed.
 *
 * A thin wrapper rather than a subclass, because the Time Trial wants the
 * stream's behaviour exactly - the same ring of Games, the same anti-repeat
 * window (one pool, one window: a board met in the Infinite is not new here
 * either), the same "step over a Game whose pool will not load" - and the only
 * thing it adds is the refusal to deal a board once the clock has stopped. A
 * board dealt after the deadline would be a puzzle the player is charged for
 * and can never finish.
 */
export class TimeTrialSupply {
  private readonly stream: InfiniteStream;
  private readonly expired: () => boolean;

  constructor(stream: InfiniteStream, expired: () => boolean) {
    this.stream = stream;
    this.expired = expired;
  }

  /** The next board, or `null` when the run is over. Never throws. */
  async next(): Promise<StreamOutcome | null> {
    if (this.expired()) return null;
    const outcome = await this.stream.next();
    // Re-checked AFTER the fetch: the deadline can pass while a board is in
    // flight, and dealing it then would put a board on screen the run has
    // already ended.
    if (this.expired()) return null;
    if (outcome.status !== "ready") return outcome;
    return { status: "ready", step: reframe(outcome.step) };
  }
}
