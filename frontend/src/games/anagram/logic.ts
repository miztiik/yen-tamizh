// The anagram mechanic's pure core - no DOM, no storage, no singletons (docs/
// concepts/games.md `anagram`). Everything here is a function of its arguments,
// so the whole mechanic unit-tests in a node environment while the Svelte view
// stays a thin projection of this state.
//
// Two invariants the rest of the Game leans on:
//
//   - A TILE IS AN EZHUTHU. Comparison, scrambling and solving all work over
//     ezhuthu arrays produced by the shared Row 6 library, never over code
//     points - splitting a cluster would make the puzzle unplayable (Holy Law
//     "one concept defined once"; docs/concepts/core-loop.md).
//   - THE SCRAMBLE IS DETERMINISTIC. It is seeded from the target word, so the
//     same puzzle scrambles identically on every load; a session re-render or a
//     mid-puzzle reload never reshuffles the tray under the player's thumb.

import { segment } from "../../tamil/ezhuthu";
import type { AnagramPuzzle } from "../../contracts/anagram-puzzle";

/**
 * The runtime payload: the `anagram-puzzle` contract minus its schema-stamp
 * fields. `version`/`changelog` describe how the SCHEMA FILE evolves; a
 * `puzzle-file` item's `payload` carries neither (its file-level schema does).
 */
export type AnagramPayload = Omit<AnagramPuzzle, "version" | "changelog">;

/** One honest hint from the payload: its kind, its text, and its score cost. */
export type AnagramHint = NonNullable<AnagramPayload["hints"]>[number];

/** One tile in the tray: an ezhuthu plus a stable id (a word may repeat one). */
export interface AnagramTile {
  readonly id: string;
  readonly ezhuthu: string;
}

/** The resumable state the runner persists; ids make a restore unambiguous. */
export interface AnagramState {
  /** Tile ids in placement order (index 0 fills slot 0). */
  placedTileIds: string[];
  /** Submitted attempts so far (a full arrangement auto-submits). */
  attempts: number;
  /** How many of `payload.hints` the player has revealed, in order. */
  revealedHintCount: number;
  /** Terminal flag: solved, or attempts exhausted. */
  finished: boolean;
  /** Awarded points; 0 until solved. */
  score: number;
  /** Whether the puzzle ended in a win (vs. attempts exhausted). */
  solved: boolean;
}

/** Points per ezhuthu when the config slice does not set a base score. */
export const DEFAULT_POINTS_PER_EZHUTHU = 10;

/** A fresh, untouched state. */
export function initialState(): AnagramState {
  return {
    placedTileIds: [],
    attempts: 0,
    revealedHintCount: 0,
    finished: false,
    score: 0,
    solved: false,
  };
}

/** Normalize an untrusted (persisted) snapshot back into a valid state. */
export function normalizeState(raw: unknown): AnagramState {
  const base = initialState();
  if (typeof raw !== "object" || raw === null) return base;
  const s = raw as Partial<AnagramState>;
  return {
    placedTileIds: Array.isArray(s.placedTileIds)
      ? s.placedTileIds.filter((id): id is string => typeof id === "string")
      : base.placedTileIds,
    attempts: typeof s.attempts === "number" ? s.attempts : base.attempts,
    revealedHintCount:
      typeof s.revealedHintCount === "number" ? s.revealedHintCount : base.revealedHintCount,
    finished: typeof s.finished === "boolean" ? s.finished : base.finished,
    score: typeof s.score === "number" ? s.score : base.score,
    solved: typeof s.solved === "boolean" ? s.solved : base.solved,
  };
}

/** The target as ezhuthu - the only representation the mechanic compares. */
export function targetEzhuthu(payload: AnagramPayload): string[] {
  return segment(payload.word);
}

/** Ezhuthu-array equality: same length, same clusters, same order. */
export function ezhuthuArraysEqual(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((cluster, i) => cluster === b[i]);
}

/** FNV-1a over UTF-16 units - a small, stable, dependency-free string hash. */
export function hashSeed(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** mulberry32 - a tiny deterministic PRNG so a seed reproduces a shuffle. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Fisher-Yates driven by a seeded PRNG: same seed -> same order, always. */
export function shuffleDeterministic<T>(items: readonly T[], seed: number): T[] {
  const out = [...items];
  const rand = mulberry32(seed);
  for (let i = out.length - 1; i > 0; i -= 1) {
    const j = Math.floor(rand() * (i + 1));
    const a = out[i] as T;
    const b = out[j] as T;
    out[i] = b;
    out[j] = a;
  }
  return out;
}

/**
 * The tray for a puzzle: the payload's ezhuthu tiles, scrambled deterministically
 * from the target word. A scramble that lands on the answer is rotated by one -
 * a pre-solved anagram is not a puzzle (Palm).
 */
export function buildTray(payload: AnagramPayload): AnagramTile[] {
  const target = targetEzhuthu(payload);
  let order = shuffleDeterministic(payload.tiles, hashSeed(payload.word));
  if (order.length > 1 && ezhuthuArraysEqual(order, target)) {
    const [first, ...rest] = order;
    order = [...rest, first as string];
  }
  return order.map((ezhuthu, index) => ({ id: `t${index}`, ezhuthu }));
}

/** The ezhuthu the player has arranged, in slot order. */
export function placedEzhuthu(tray: readonly AnagramTile[], state: AnagramState): string[] {
  return state.placedTileIds.map((id) => tray.find((tile) => tile.id === id)?.ezhuthu ?? "");
}

/** Tiles still in the tray (placement order removes them). */
export function remainingTiles(tray: readonly AnagramTile[], state: AnagramState): AnagramTile[] {
  return tray.filter((tile) => !state.placedTileIds.includes(tile.id));
}

/** Whether the arrangement fills every slot (the auto-submit trigger). */
export function isFull(payload: AnagramPayload, state: AnagramState): boolean {
  return state.placedTileIds.length === targetEzhuthu(payload).length;
}

/** Whether the arrangement spells the target, compared as ezhuthu. */
export function isSolved(
  payload: AnagramPayload,
  tray: readonly AnagramTile[],
  state: AnagramState,
): boolean {
  return ezhuthuArraysEqual(placedEzhuthu(tray, state), targetEzhuthu(payload));
}

/** Attempts left before the puzzle ends (never negative). */
export function attemptsRemaining(payload: AnagramPayload, state: AnagramState): number {
  return Math.max(0, payload.attempts - state.attempts);
}

/** The hints the player has revealed so far, in payload order. */
export function revealedHints(payload: AnagramPayload, state: AnagramState): AnagramHint[] {
  return (payload.hints ?? []).slice(0, state.revealedHintCount);
}

/** The next hint to reveal, or `null` when they are all spent. */
export function nextHint(payload: AnagramPayload, state: AnagramState): AnagramHint | null {
  return (payload.hints ?? [])[state.revealedHintCount] ?? null;
}

/**
 * The score before hints: `config.baseScore` when the Mode sets one, else a
 * sane default that scales with the word's length (Holy Law #6 - a fresh clone
 * runs on the defaults, and the knob arrives through the config slice, never an
 * import of the app config).
 */
export function baseScore(
  payload: AnagramPayload,
  config: Readonly<Record<string, unknown>> = {},
): number {
  const configured = config.baseScore;
  if (typeof configured === "number" && Number.isFinite(configured) && configured > 0) {
    return Math.round(configured);
  }
  return targetEzhuthu(payload).length * DEFAULT_POINTS_PER_EZHUTHU;
}

/**
 * The awarded score: the base minus the cost of every hint the player revealed
 * (docs/concepts/difficulty-and-scoring.md - a hint costs the brag, not money).
 * Clamped at 0 so a heavily-hinted win never goes negative.
 */
export function scoreFor(
  payload: AnagramPayload,
  state: AnagramState,
  config: Readonly<Record<string, unknown>> = {},
): number {
  const spent = revealedHints(payload, state).reduce((sum, hint) => sum + hint.cost, 0);
  return Math.max(0, baseScore(payload, config) - spent);
}

/** Place a tile into the next free slot. No-op when finished, full, or already placed. */
export function placeTile(
  payload: AnagramPayload,
  state: AnagramState,
  tileId: string,
): AnagramState {
  if (state.finished || isFull(payload, state) || state.placedTileIds.includes(tileId)) {
    return state;
  }
  return { ...state, placedTileIds: [...state.placedTileIds, tileId] };
}

/** Take a specific placed tile back to the tray (tap a slot to undo it). */
export function removeTile(state: AnagramState, tileId: string): AnagramState {
  if (state.finished) return state;
  const next = state.placedTileIds.filter((id) => id !== tileId);
  return next.length === state.placedTileIds.length ? state : { ...state, placedTileIds: next };
}

/** Undo the last placement (Backspace). */
export function undoLast(state: AnagramState): AnagramState {
  if (state.finished || state.placedTileIds.length === 0) return state;
  return { ...state, placedTileIds: state.placedTileIds.slice(0, -1) };
}

/** Return every placed tile to the tray (Escape). */
export function clearPlaced(state: AnagramState): AnagramState {
  if (state.finished || state.placedTileIds.length === 0) return state;
  return { ...state, placedTileIds: [] };
}

/** Reveal the next hint; the cost is applied when the puzzle is scored. */
export function revealNextHint(payload: AnagramPayload, state: AnagramState): AnagramState {
  if (state.finished || nextHint(payload, state) === null) return state;
  return { ...state, revealedHintCount: state.revealedHintCount + 1 };
}

/** The outcome of submitting a full arrangement. */
export interface AttemptOutcome {
  state: AnagramState;
  correct: boolean;
  /** True when this attempt ended the puzzle without a win (attempts spent). */
  exhausted: boolean;
  attemptIndex: number;
  /** The submitted arrangement as a word, for the attempt event. */
  attempt: string;
}

/**
 * Submit the current arrangement. A win finishes and scores; a miss spends an
 * attempt and clears the arrangement so the player can try again; spending the
 * last attempt ends the puzzle honestly (no purchase, no timer - Palm).
 */
export function submitAttempt(
  payload: AnagramPayload,
  tray: readonly AnagramTile[],
  state: AnagramState,
  config: Readonly<Record<string, unknown>> = {},
): AttemptOutcome {
  const attempt = placedEzhuthu(tray, state).join("");
  const correct = isSolved(payload, tray, state);
  const attempts = state.attempts + 1;
  const attemptIndex = attempts;

  if (correct) {
    const solvedState: AnagramState = { ...state, attempts, finished: true, solved: true };
    return {
      state: { ...solvedState, score: scoreFor(payload, solvedState, config) },
      correct: true,
      exhausted: false,
      attemptIndex,
      attempt,
    };
  }

  const exhausted = attempts >= payload.attempts;
  return {
    state: { ...state, attempts, placedTileIds: [], finished: exhausted },
    correct: false,
    exhausted,
    attemptIndex,
    attempt,
  };
}

/** What a key press means on the tile surface (the pure keyboard contract). */
export type KeyAction = "place" | "undo" | "clear" | null;

/** Map a `KeyboardEvent.key` to a mechanic action; unknown keys do nothing. */
export function keyToAction(key: string): KeyAction {
  if (key === "Enter" || key === " " || key === "Spacebar") return "place";
  if (key === "Backspace" || key === "Delete") return "undo";
  if (key === "Escape") return "clear";
  return null;
}

/** The player-facing strings; a Mode may override any of them via the config slice. */
export interface AnagramLabels {
  prompt: string;
  tray: string;
  answer: string;
  hint: string;
  hintsSpent: string;
  attemptsLeft: string;
  correct: string;
  wrong: string;
  outOfAttempts: string;
  slot: string;
  placedSlot: string;
  trayTile: string;
}

/** Tamil first, with the English the median player also reads (Player #7). */
export const DEFAULT_LABELS: AnagramLabels = {
  prompt: "சொல்லை அடுக்குங்கள்",
  tray: "எழுத்துகள்",
  answer: "பதில்",
  hint: "குறிப்பு",
  hintsSpent: "குறிப்புகள் முடிந்தன",
  attemptsLeft: "முயற்சி மீதம்",
  correct: "சரி!",
  wrong: "தவறு",
  outOfAttempts: "முயற்சிகள் முடிந்தன",
  slot: "Slot",
  placedSlot: "Remove tile from slot",
  trayTile: "Place tile",
};

/**
 * Resolve the labels from the injected config slice. The Game never imports the
 * app config or the copy map - a Mode hands down whatever it wants overridden
 * (Fowler: payloads, not calls), and the defaults keep a fresh clone playable.
 */
export function resolveLabels(config: Readonly<Record<string, unknown>> = {}): AnagramLabels {
  const overrides = config.labels;
  if (typeof overrides !== "object" || overrides === null) return DEFAULT_LABELS;
  const partial = overrides as Partial<Record<keyof AnagramLabels, unknown>>;
  const merged: AnagramLabels = { ...DEFAULT_LABELS };
  for (const key of Object.keys(DEFAULT_LABELS) as (keyof AnagramLabels)[]) {
    const value = partial[key];
    if (typeof value === "string" && value.length > 0) merged[key] = value;
  }
  return merged;
}
