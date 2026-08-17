// SessionRunner - the single piece that knows how to drive a Session (docs/
// concepts/ui-shell.md). It walks the Session's items, mounts each Game into the
// shell's `stage`, reflects progress, shows the end-of-session summary, and
// emits the session events on the Mode's behalf (docs/concepts/telemetry.md).
//
// It is deliberately DOM-free and Svelte-free so it unit-tests in a node
// environment: the shell is reached only through the injected `SessionHost`
// (which owns the `stage` element and the progress/summary chrome), and Games
// are reached only through the injected registry. The runner NEVER branches on
// which Game it is hosting, and a Game NEVER sees the runner.
//
// Advance is EVENT-DRIVEN (CLAUDE.md section 1a, payloads-not-calls): a Game
// signals it is done by EMITTING `puzzle.completed` through its logger; the
// runner subscribes to the bus and advances. It also snapshots the current
// Game's state whenever a Game reports durable progress (an attempt submitted, a
// hint revealed) so a reload resumes mid-item.

import type { EventBus } from "../telemetry/bus";
import type { EventEnvelope, Logger } from "../telemetry/logger";
import type { StorageService } from "../services/StorageService";
import { resolveGame, type GameRegistry } from "../games/registry";

import type { DayContext } from "./dayKey";
import type {
  GameConfigSlice,
  GameContext,
  GameModule,
  Session,
  SessionResult,
  SessionResultItem,
  SessionState,
} from "./types";

/** Read a string field off an untrusted payload, or `undefined`. */
function displayString(payload: unknown, key: string): string | undefined {
  if (typeof payload !== "object" || payload === null) return undefined;
  const value = (payload as Record<string, unknown>)[key];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

/**
 * The summary line for one resolved item.
 *
 * This is a STRUCTURAL read of three optional display strings, not a branch on
 * which Game produced them: any payload that names a `word` gets a row, and a
 * payload that names none is left out rather than rendered as a blank. That is
 * what lets the summary stay generic while `SessionItem.payload` stays
 * `unknown` - the summary must never reach into it itself.
 */
function resultItem(payload: unknown, solved: boolean): SessionResultItem | null {
  const word = displayString(payload, "word");
  if (word === undefined) return null;
  const meaning = displayString(payload, "meaning");
  const translationEn = displayString(payload, "translationEn");
  return {
    word,
    ...(meaning === undefined ? {} : { meaning }),
    ...(translationEn === undefined ? {} : { translationEn }),
    solved,
  };
}

/** Rebuild the resolved list from a persisted (therefore untrusted) snapshot. */
function restoreResolved(raw: unknown): SessionResultItem[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((entry: unknown) => {
    const solved =
      typeof entry === "object" &&
      entry !== null &&
      (entry as Record<string, unknown>).solved === true;
    const item = resultItem(entry, solved);
    return item === null ? [] : [item];
  });
}

/** The shell surface the runner drives; the Svelte shell provides one at runtime. */
export interface SessionHost {
  /** The element Games mount into (the shell's `stage` slot). */
  readonly stage: HTMLElement;
  /** Reflect item progress into the chrome (completed of total). */
  setProgress(completed: number, total: number): void;
  /** Render the end-of-session summary. */
  showSummary(result: SessionResult): void;
  /** Clear the stage between items. */
  clearStage(): void;
}

export interface SessionRunnerDeps {
  session: Session;
  registry: GameRegistry;
  storage: StorageService;
  logger: Logger;
  bus: EventBus;
  host: SessionHost;
  /** Read-only config slice handed to every Game (default: none). */
  config?: GameConfigSlice;
  /** Injectable clock (epoch ms) for deterministic tests. */
  now?: () => number;
  /** Called when the session ends and the player leaves. */
  onExit?: (result: SessionResult) => void;
}

export class SessionRunner {
  private readonly deps: SessionRunnerDeps;
  private readonly now: () => number;
  private readonly sessionLogger: Logger;
  private readonly dayCtx: DayContext;

  private currentGame: GameModule | null = null;
  private unsubscribe: (() => void) | null = null;

  private itemIndex = 0;
  private completedCount = 0;
  private totalScore = 0;
  private startedAt = 0;
  private ended = false;
  private readonly resolved: SessionResultItem[] = [];

  private hasPendingRestore = false;
  private pendingGameState: unknown = null;
  private lastResult: SessionResult | null = null;

  constructor(deps: SessionRunnerDeps) {
    this.deps = deps;
    this.now = deps.now ?? (() => Date.now());
    const { session } = deps;
    this.dayCtx = {
      date: session.date,
      modeId: session.modeId,
      gameId: session.gameId,
      packId: session.packId,
    };
    this.sessionLogger = deps.logger.child(session.modeId, {
      modeId: session.modeId,
      gameId: session.gameId,
      packId: session.packId,
      day: session.date,
      sessionId: session.sessionId,
    });
  }

  private get totalItems(): number {
    return this.deps.session.items.length;
  }

  /** Start (or resume) the session. */
  async start(): Promise<void> {
    this.startedAt = this.now();
    this.sessionLogger.emit("mode.session.started", {
      data: { totalItems: this.totalItems },
    });

    const resumed = this.deps.storage.readSessionState(this.dayCtx);
    if (resumed !== null) {
      this.itemIndex = resumed.itemIndex;
      this.completedCount = resumed.completedCount;
      this.totalScore = resumed.totalScore;
      this.pendingGameState = resumed.currentGameState;
      this.hasPendingRestore = true;
      this.resolved.push(...restoreResolved(resumed.resolved));
    }

    this.unsubscribe = this.deps.bus.subscribe((env) => this.onBusEvent(env));
    await this.advance();
  }

  /** End the session early (e.g. the header "back" control) and notify onExit. */
  exit(): void {
    if (!this.ended) this.endSession("exited");
    if (this.lastResult) this.deps.onExit?.(this.lastResult);
  }

  private async advance(): Promise<void> {
    this.destroyCurrent();
    this.deps.host.clearStage();

    if (this.itemIndex >= this.totalItems) {
      this.endSession("completed");
      return;
    }

    const item = this.deps.session.items[this.itemIndex];
    if (item === undefined) {
      this.endSession("completed");
      return;
    }

    const entry = resolveGame(this.deps.registry, item.gameId);
    if (entry === null) {
      // Unknown gameId: skip the item rather than crash the whole session.
      this.sessionLogger.emit("puzzle.abandoned", {
        level: "warn",
        ctx: { itemIndex: this.itemIndex },
        data: { reason: "unknown-game", gameId: item.gameId },
      });
      this.itemIndex += 1;
      await this.advance();
      return;
    }

    const factory = await entry.load();
    const game = factory();
    this.currentGame = game;

    const ctx: GameContext = {
      payload: item.payload,
      logger: this.deps.logger.child(item.gameId, {
        modeId: this.deps.session.modeId,
        gameId: item.gameId,
        packId: this.deps.session.packId,
        day: this.deps.session.date,
        sessionId: this.deps.session.sessionId,
        itemIndex: this.itemIndex,
      }),
      config: this.deps.config ?? {},
      now: this.now,
    };

    game.mount(this.deps.host.stage, ctx);

    if (this.hasPendingRestore) {
      game.restoreState(this.pendingGameState);
      this.hasPendingRestore = false;
      this.pendingGameState = null;
    }

    this.snapshot();
    this.deps.host.setProgress(this.completedCount, this.totalItems);
  }

  private onBusEvent(env: EventEnvelope): void {
    if (env.ctx.sessionId !== this.deps.session.sessionId) return;
    if (this.currentGame === null) return;

    if (env.name === "puzzle.attempt.submitted" || env.name === "puzzle.hint.used") {
      // Both change durable, score-bearing state (an attempt spent, a hint
      // revealed and its cost incurred), so both must survive a reload.
      this.snapshot();
      return;
    }
    if (env.ctx.itemIndex !== this.itemIndex) return; // ignore stale completions

    if (env.name === "puzzle.completed") {
      const score = typeof env.data.score === "number" ? env.data.score : 0;
      this.completedCount += 1;
      this.totalScore += score;
      this.recordResolved(true);
      this.itemIndex += 1;
      this.persist(null);
      this.deps.host.setProgress(this.completedCount, this.totalItems);
      void this.advance();
      return;
    }
    if (env.name === "puzzle.abandoned") {
      this.recordResolved(false);
      this.itemIndex += 1;
      this.persist(null);
      void this.advance();
    }
  }

  /** Remember the current item's word for the summary (solved or lost alike). */
  private recordResolved(solved: boolean): void {
    const item = this.deps.session.items[this.itemIndex];
    const entry = item === undefined ? null : resultItem(item.payload, solved);
    if (entry !== null) this.resolved.push(entry);
  }

  /** Persist the live Game's state so a reload resumes at this item. */
  private snapshot(): void {
    if (this.currentGame === null) return;
    this.persist(this.currentGame.getState());
  }

  private persist(currentGameState: unknown): void {
    const state: SessionState = {
      itemIndex: this.itemIndex,
      completedCount: this.completedCount,
      totalScore: this.totalScore,
      currentGameState,
      resolved: [...this.resolved],
    };
    this.deps.storage.writeSessionState(this.dayCtx, state);
  }

  private endSession(reason: SessionResult["reason"]): void {
    if (this.ended) return;
    this.ended = true;
    this.destroyCurrent();

    const result: SessionResult = {
      modeId: this.deps.session.modeId,
      sessionId: this.deps.session.sessionId,
      itemsCompleted: this.completedCount,
      itemsTotal: this.totalItems,
      totalScore: this.totalScore,
      durationMs: this.now() - this.startedAt,
      reason,
      items: [...this.resolved],
    };
    this.lastResult = result;

    this.sessionLogger.emit("mode.session.completed", {
      data: {
        itemsCompleted: result.itemsCompleted,
        itemsTotal: result.itemsTotal,
        totalScore: result.totalScore,
        durationMs: result.durationMs,
        reason,
      },
    });

    this.unsubscribe?.();
    this.unsubscribe = null;

    if (reason === "completed") this.deps.host.showSummary(result);
  }

  private destroyCurrent(): void {
    if (this.currentGame !== null) {
      this.currentGame.destroy();
      this.currentGame = null;
    }
  }
}
