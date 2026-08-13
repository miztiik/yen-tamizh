// Session + Game vocabulary - what a Mode hands the SessionRunner, and the
// contract a Game implements (docs/concepts/ui-shell.md, games.md).
//
// The boundary that matters (CLAUDE.md section 1a, Fowler): a Game receives a
// GameContext and renders into the shell's `stage` element. It gets its
// `payload`, a scoped `logger`, a read-only `config` slice, and a clock - and
// nothing else. It cannot reach storage, app config, or the shell chrome, so it
// cannot break the single-writer or DRY-UI invariants. A Game reports progress
// by EMITTING events (payloads, not calls); the runner listens and persists.

import type { Logger } from "../telemetry/logger";

/** One playable item in a session; mirrors a `puzzle-file` playlist entry. */
export interface SessionItem {
  readonly gameId: string;
  /** The puzzle payload (schema-validated upstream by the loader). */
  readonly payload: unknown;
}

/** What a Mode hands the runner: an ordered, finite list of items to walk. */
export interface Session {
  readonly modeId: string;
  readonly packId: string;
  /** The primary gameId (single-game sessions for now); part of the day key. */
  readonly gameId: string;
  /** Stable id for telemetry + storage scoping. */
  readonly sessionId: string;
  /** The calendar day (YYYY-MM-DD) this session is anchored to. */
  readonly date: string;
  readonly items: readonly SessionItem[];
}

/** The resumable snapshot of a session run, persisted under `save.perMode`. */
export interface SessionState {
  /** Index of the current (not-yet-completed) item. */
  itemIndex: number;
  completedCount: number;
  totalScore: number;
  /** The current item's Game state, so a reload resumes mid-puzzle. */
  currentGameState: unknown;
}

/** The outcome the runner reports when a session ends. */
export interface SessionResult {
  modeId: string;
  sessionId: string;
  itemsCompleted: number;
  itemsTotal: number;
  totalScore: number;
  durationMs: number;
  reason: "completed" | "exited";
}

/** A read-only slice of config a Game may consult; never the whole app config. */
export type GameConfigSlice = Readonly<Record<string, unknown>>;

/**
 * Everything a Game is handed. Deliberately small: payload + a scoped logger +
 * a config slice + a clock. No storage, no shell, no app config (Fowler).
 */
export interface GameContext<TPayload = unknown> {
  readonly payload: TPayload;
  /** The ONLY telemetry channel; scoped to this Game's src + session context. */
  readonly logger: Logger;
  readonly config: GameConfigSlice;
  /** Injectable monotonic clock (epoch ms) for deterministic play/tests. */
  now(): number;
}

/**
 * A puzzle mechanic. The runner mounts it into `stage`, listens for the events
 * it emits, snapshots `getState()` for durability, and `restoreState()`s it on
 * resume. A Game never sees the runner, the Mode, or storage.
 */
export interface GameModule<TState = unknown> {
  /** Render into the shell's `stage` element and start play. */
  mount(stage: HTMLElement, ctx: GameContext): void;
  /** Tear down; the runner clears `stage` between items. */
  destroy(): void;
  /** Serialize resumable state (the runner persists it via StorageService). */
  getState(): TState;
  /** Rehydrate previously persisted state (resume mid-session). */
  restoreState(state: TState): void;
}
