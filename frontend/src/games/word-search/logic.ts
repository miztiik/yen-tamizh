// The word-search mechanic's pure core - no DOM, no storage, no singletons
// (docs/concepts/games.md `word-search`). Everything here is a function of its
// arguments, so the whole mechanic unit-tests in a node environment while the
// Svelte view stays a thin projection of this state.
//
// Five invariants the rest of the Game leans on:
//
//   - A GRID CELL IS ONE EZHUTHU. The payload's grid arrives already split by
//     the shared Row 6 library on the generator's side and its contract
//     re-checks every cell, so this file never re-splits anything: a trace is a
//     list of cells, and what it spells is those cells joined. Working in code
//     points instead would let a trace end half way through a cluster and spell
//     something no Tamil reader could name.
//   - A TRACE IS A STRAIGHT LINE, and the same one whichever way it is read.
//     Pointer and keyboard both produce (anchor, head) and both resolve it the
//     same way through `tracePath`, so there is exactly one definition of what
//     is selected and the two input methods cannot disagree.
//   - A TRACE IS JUDGED BY WHAT IT SPELLS, not by where it is. Tracing a word
//     backwards finds it, and so does finding a second copy of it that the
//     filler happened to make - both spell the word, and telling a player "you
//     found it, but not in the right place" would be the game marking its own
//     bookkeeping rather than their answer.
//   - A WRONG TRACE COSTS NOTHING. Tracing is how a player LOOKS; charging for
//     looking would turn the only exploratory mechanic in the game into a
//     guessing game. There is no attempt budget and no way to lose.
//   - REVEALING IS THE ONLY PRICE. A player who cannot find a word may hand it
//     over, and it is paid for in exactly that word's points. That is why this
//     Game bakes no hint ladder: the price depends on which words are still
//     outstanding when it is spent, so it cannot be a rung with a number on it.

import { segment } from "../../tamil/ezhuthu";
import type { WordSearchPuzzle } from "../../contracts/word-search-puzzle";

/**
 * The runtime payload: the `word-search-puzzle` contract minus its schema-stamp
 * fields. `version`/`changelog` describe how the SCHEMA FILE evolves; a
 * `puzzle-file` item's `payload` carries neither.
 */
export type WordSearchPayload = Omit<WordSearchPuzzle, "version" | "changelog">;

/** One word hidden in the grid, as it travels in the payload. */
export type Target = WordSearchPayload["targets"][number];

/** The eight straight lines a trace may run along. */
export type Direction = Target["direction"];

/** One cell address in the grid. */
export interface Cell {
  row: number;
  col: number;
}

/**
 * Each direction as the (row, col) step it takes. The set is closed under
 * negation, which is what makes a backwards trace the same trace read the other
 * way rather than a case of its own. It is written out here rather than derived
 * so the twin of this table in the Python contract can be compared line by line.
 */
export const STEPS: Readonly<Record<Direction, Cell>> = {
  right: { row: 0, col: 1 },
  "down-right": { row: 1, col: 1 },
  down: { row: 1, col: 0 },
  "down-left": { row: 1, col: -1 },
  left: { row: 0, col: -1 },
  "up-left": { row: -1, col: -1 },
  up: { row: -1, col: 0 },
  "up-right": { row: -1, col: 1 },
};

/** Points per ezhuthu found - the same rate every other Game pays. */
export const DEFAULT_POINTS_PER_EZHUTHU = 10;

/** One word the player has traced out, and the line they traced it along. */
export interface FoundTrace {
  word: string;
  row: number;
  col: number;
  direction: Direction;
}

/** The resumable state the runner persists. */
export interface WordSearchState {
  /** Words traced by the player, in the order they were found. */
  found: FoundTrace[];
  /** Words the player handed over rather than found; they earn nothing. */
  revealed: string[];
  /** Where the keyboard cursor is. Always on the grid. */
  cursor: Cell;
  /** Where the current trace started, or `null` when nothing is being traced. */
  anchor: Cell | null;
  /** Terminal flag: every word is on the board, found or revealed. */
  finished: boolean;
  /** Awarded points. */
  score: number;
  /** Whether every word was traced rather than revealed. */
  solved: boolean;
}

/** How many rows the grid has. Derived: a stored height could disagree with it. */
export function gridRows(payload: WordSearchPayload): number {
  return payload.grid.length;
}

/** How many columns the grid has. */
export function gridCols(payload: WordSearchPayload): number {
  return payload.grid[0]?.length ?? 0;
}

/** Whether a cell address is on the grid. */
export function onGrid(payload: WordSearchPayload, cell: Cell): boolean {
  return (
    cell.row >= 0 &&
    cell.row < gridRows(payload) &&
    cell.col >= 0 &&
    cell.col < gridCols(payload)
  );
}

/** The ezhuthu in one cell, or "" when the address is off the grid. */
export function cellAt(payload: WordSearchPayload, cell: Cell): string {
  return payload.grid[cell.row]?.[cell.col] ?? "";
}

/** A fresh, untouched state. The cursor starts at the top-left cell. */
export function initialState(): WordSearchState {
  return {
    found: [],
    revealed: [],
    cursor: { row: 0, col: 0 },
    anchor: null,
    finished: false,
    score: 0,
    solved: false,
  };
}

function isCell(raw: unknown): raw is Cell {
  if (typeof raw !== "object" || raw === null) return false;
  const value = raw as Partial<Cell>;
  return typeof value.row === "number" && typeof value.col === "number";
}

function isDirection(raw: unknown): raw is Direction {
  return typeof raw === "string" && Object.prototype.hasOwnProperty.call(STEPS, raw);
}

function isTrace(raw: unknown): raw is FoundTrace {
  if (!isCell(raw)) return false;
  const value = raw as Partial<FoundTrace>;
  return typeof value.word === "string" && isDirection(value.direction);
}

/**
 * Normalize an untrusted (persisted) snapshot back into a valid state.
 *
 * A restored trace naming a word this board does not hide is dropped rather
 * than kept: a save from a previous day would otherwise mark cells of a board
 * it never saw.
 */
export function normalizeState(
  payload: WordSearchPayload,
  raw: unknown,
): WordSearchState {
  const base = initialState();
  if (typeof raw !== "object" || raw === null) return base;
  const snapshot = raw as Partial<WordSearchState>;
  const wanted = new Set(payload.targets.map((target) => target.word));
  const found = Array.isArray(snapshot.found)
    ? snapshot.found.filter(isTrace).filter((trace) => wanted.has(trace.word))
    : base.found;
  const revealed = Array.isArray(snapshot.revealed)
    ? snapshot.revealed.filter(
        (word): word is string => typeof word === "string" && wanted.has(word),
      )
    : base.revealed;
  const cursor =
    isCell(snapshot.cursor) && onGrid(payload, snapshot.cursor)
      ? snapshot.cursor
      : base.cursor;
  const state: WordSearchState = {
    found,
    revealed,
    cursor,
    // A trace in progress is never restored: it is a gesture, not progress.
    anchor: null,
    finished: false,
    score: 0,
    solved: false,
  };
  return settle(payload, state);
}

/** Every cell a trace from `anchor` to `head` covers, or `[]` if it is not a line. */
export function tracePath(anchor: Cell, head: Cell): Cell[] {
  const downwards = head.row - anchor.row;
  const across = head.col - anchor.col;
  const straight =
    downwards === 0 || across === 0 || Math.abs(downwards) === Math.abs(across);
  if (!straight) return [];
  const length = Math.max(Math.abs(downwards), Math.abs(across)) + 1;
  const stepRow = Math.sign(downwards);
  const stepCol = Math.sign(across);
  return Array.from({ length }, (_, index) => ({
    row: anchor.row + stepRow * index,
    col: anchor.col + stepCol * index,
  }));
}

/** The direction a trace runs in, or `null` when it is a single cell or bent. */
export function traceDirection(anchor: Cell, head: Cell): Direction | null {
  const stepRow = Math.sign(head.row - anchor.row);
  const stepCol = Math.sign(head.col - anchor.col);
  if (stepRow === 0 && stepCol === 0) return null;
  if (tracePath(anchor, head).length === 0) return null;
  const entry = Object.entries(STEPS).find(
    ([, step]) => step.row === stepRow && step.col === stepCol,
  );
  return entry === undefined ? null : (entry[0] as Direction);
}

/** The cells the player is currently selecting (empty when nothing is traced). */
export function selectedCells(state: WordSearchState): Cell[] {
  return state.anchor === null ? [] : tracePath(state.anchor, state.cursor);
}

/** What the current selection spells, left to right along the trace. */
export function selectedWord(
  payload: WordSearchPayload,
  state: WordSearchState,
): string {
  return selectedCells(state)
    .map((cell) => cellAt(payload, cell))
    .join("");
}

/** The cells one already-found or revealed word occupies. */
export function cellsOf(entry: FoundTrace | Target): Cell[] {
  const start = "start" in entry ? entry.start : entry;
  const step = STEPS[entry.direction];
  const length = segment(entry.word).length;
  return Array.from({ length }, (_, index) => ({
    row: start.row + step.row * index,
    col: start.col + step.col * index,
  }));
}

/** Every cell that belongs to a word already on the board, as `"row,col"` keys. */
export function markedCells(
  payload: WordSearchPayload,
  state: WordSearchState,
): Set<string> {
  const marked = new Set<string>();
  for (const trace of state.found) {
    for (const cell of cellsOf(trace)) marked.add(`${cell.row},${cell.col}`);
  }
  for (const word of state.revealed) {
    const target = payload.targets.find((entry) => entry.word === word);
    if (target === undefined) continue;
    for (const cell of cellsOf(target)) marked.add(`${cell.row},${cell.col}`);
  }
  return marked;
}

/** Whether this word is already on the board, traced or handed over. */
export function isResolved(state: WordSearchState, word: string): boolean {
  return (
    state.found.some((trace) => trace.word === word) || state.revealed.includes(word)
  );
}

/** The targets still to find, in payload order. */
export function outstanding(
  payload: WordSearchPayload,
  state: WordSearchState,
): Target[] {
  return payload.targets.filter((target) => !isResolved(state, target.word));
}

/** What one word is worth: its ezhuthu count at the shared rate. */
export function wordValue(word: string): number {
  return segment(word).length * DEFAULT_POINTS_PER_EZHUTHU;
}

/** The full board's value, if every word is traced. */
export function fullScore(
  payload: WordSearchPayload,
  config: Readonly<Record<string, unknown>> = {},
): number {
  const configured = config.baseScore;
  if (typeof configured === "number" && Number.isFinite(configured) && configured > 0) {
    return Math.round(configured);
  }
  return payload.targets.reduce((sum, target) => sum + wordValue(target.word), 0);
}

/**
 * The score so far: the share of the board's value the player TRACED.
 *
 * A revealed word earns nothing, which is the whole price of revealing - and it
 * is proportional rather than all-or-nothing, so a player stuck on the last
 * word keeps everything they earned before it. When a Mode overrides the total
 * with `config.baseScore`, the same share of that total is awarded, so the knob
 * still means "what this puzzle is worth".
 */
export function scoreFor(
  payload: WordSearchPayload,
  state: WordSearchState,
  config: Readonly<Record<string, unknown>> = {},
): number {
  const earned = state.found.reduce((sum, trace) => sum + wordValue(trace.word), 0);
  const whole = payload.targets.reduce((sum, t) => sum + wordValue(t.word), 0);
  if (whole === 0) return 0;
  return Math.round((fullScore(payload, config) * earned) / whole);
}

/** Recompute the derived flags after any change to what is on the board. */
function settle(
  payload: WordSearchPayload,
  state: WordSearchState,
  config: Readonly<Record<string, unknown>> = {},
): WordSearchState {
  const done = outstanding(payload, state).length === 0;
  return {
    ...state,
    finished: done,
    solved: done && state.revealed.length === 0,
    score: scoreFor(payload, state, config),
  };
}

/** Move the keyboard cursor, clamped to the grid. */
export function moveCursor(
  payload: WordSearchPayload,
  state: WordSearchState,
  step: Cell,
): WordSearchState {
  const next = {
    row: Math.min(Math.max(state.cursor.row + step.row, 0), gridRows(payload) - 1),
    col: Math.min(Math.max(state.cursor.col + step.col, 0), gridCols(payload) - 1),
  };
  return { ...state, cursor: next };
}

/** Put the cursor on a particular cell (what a pointer does). */
export function setCursor(
  payload: WordSearchPayload,
  state: WordSearchState,
  cell: Cell,
): WordSearchState {
  return onGrid(payload, cell) ? { ...state, cursor: cell } : state;
}

/** Start a trace at a cell: the keyboard's first Enter, the pointer's press. */
export function startTrace(
  payload: WordSearchPayload,
  state: WordSearchState,
  cell: Cell = state.cursor,
): WordSearchState {
  if (state.finished || !onGrid(payload, cell)) return state;
  return { ...state, anchor: cell, cursor: cell };
}

/** Abandon the trace in progress. Nothing is spent, because nothing ever is. */
export function cancelTrace(state: WordSearchState): WordSearchState {
  return state.anchor === null ? state : { ...state, anchor: null };
}

/** What a submitted trace turned out to be. */
export type TraceVerdict = "found" | "already" | "also-valid" | "miss" | "none";

/** The outcome of submitting one trace. */
export interface TraceOutcome {
  state: WordSearchState;
  verdict: TraceVerdict;
  /** What the trace spelled, left to right. */
  attempt: string;
  /** The target word it matched, whichever way it was read. */
  word: string | null;
  /** How many traces have been submitted, including this one. */
  attemptIndex: number;
  /** True when this trace put the last word on the board. */
  completed: boolean;
}

/** The same trace read the other way, which finds a word placed backwards. */
function reversed(word: string): string {
  return segment(word).reverse().join("");
}

/**
 * Submit the trace in progress.
 *
 * It is judged by what it SPELLS. A trace that spells a target - in either
 * direction - finds that target, and it is recorded along the line the player
 * actually drew rather than the one the payload recorded, so a second copy the
 * filler happened to make marks the cells the player really traced. A trace
 * that spells a word on `alsoValid` is answered as a real Tamil word that is
 * not on today's list; anything else is a miss, and a miss costs nothing.
 */
export function submitTrace(
  payload: WordSearchPayload,
  state: WordSearchState,
  config: Readonly<Record<string, unknown>> = {},
): TraceOutcome {
  const attempt = selectedWord(payload, state);
  const cells = selectedCells(state);
  const cleared = { ...state, anchor: null };
  const attemptIndex = state.found.length + 1;
  if (state.finished || cells.length < 2) {
    return {
      state: cleared,
      verdict: "none",
      attempt,
      word: null,
      attemptIndex,
      completed: false,
    };
  }
  const backwards = reversed(attempt);
  const hit = payload.targets.find(
    (target) => target.word === attempt || target.word === backwards,
  );
  if (hit !== undefined) {
    if (isResolved(state, hit.word)) {
      return {
        state: cleared,
        verdict: "already",
        attempt,
        word: hit.word,
        attemptIndex,
        completed: false,
      };
    }
    // Record the line the PLAYER drew, oriented so it reads as the word.
    const forwards = hit.word === attempt;
    const head = forwards ? cells[0] : cells[cells.length - 1];
    const tail = forwards ? cells[cells.length - 1] : cells[0];
    const direction = traceDirection(head as Cell, tail as Cell);
    const trace: FoundTrace = {
      word: hit.word,
      row: (head as Cell).row,
      col: (head as Cell).col,
      direction: direction ?? hit.direction,
    };
    const next = settle(
      payload,
      { ...cleared, found: [...state.found, trace] },
      config,
    );
    return {
      state: next,
      verdict: "found",
      attempt,
      word: hit.word,
      attemptIndex,
      completed: next.finished,
    };
  }
  // Widened deliberately: the generated tuple type collapses `includes` to
  // `never`, so a plain string could not be looked up in the payload's own list.
  const spare: readonly string[] = payload.alsoValid ?? [];
  if (spare.includes(attempt) || spare.includes(backwards)) {
    return {
      state: cleared,
      verdict: "also-valid",
      attempt,
      word: null,
      attemptIndex,
      completed: false,
    };
  }
  return {
    state: cleared,
    verdict: "miss",
    attempt,
    word: null,
    attemptIndex,
    completed: false,
  };
}

/** The word a reveal would hand over next, or `null` when none is left. */
export function nextReveal(
  payload: WordSearchPayload,
  state: WordSearchState,
): Target | null {
  return outstanding(payload, state)[0] ?? null;
}

/**
 * Hand over the next unfound word.
 *
 * This is the whole of this Game's help, and its price is the word: the player
 * keeps every point they traced and forfeits that one. It is not a baked rung
 * because its cost is not knowable at bake time - it depends on what is still
 * outstanding when it is spent.
 */
export function revealNext(
  payload: WordSearchPayload,
  state: WordSearchState,
  config: Readonly<Record<string, unknown>> = {},
): { state: WordSearchState; word: string | null; cost: number } {
  const target = nextReveal(payload, state);
  if (state.finished || target === null) {
    return { state, word: null, cost: 0 };
  }
  const next = settle(
    payload,
    { ...state, anchor: null, revealed: [...state.revealed, target.word] },
    config,
  );
  return { state: next, word: target.word, cost: wordValue(target.word) };
}

/** What a keyboard key means on the grid (the pure keyboard contract). */
export type GridAction =
  | { kind: "move"; step: Cell }
  | { kind: "trace" }
  | { kind: "cancel" }
  | null;

/**
 * Map a `KeyboardEvent.key` to a grid action; unknown keys do nothing.
 *
 * The arrows move a cursor and Enter does double duty: the first press drops an
 * anchor, the second submits whatever line the cursor has since drawn. That is
 * the whole keyboard mechanic, and it is deliberately the SAME two-point
 * gesture the pointer makes - press, move, release - so the two input methods
 * resolve through one definition of what is selected and cannot disagree about
 * what a trace covers.
 */
export function keyToAction(key: string): GridAction {
  if (key === "ArrowRight") return { kind: "move", step: { row: 0, col: 1 } };
  if (key === "ArrowLeft") return { kind: "move", step: { row: 0, col: -1 } };
  if (key === "ArrowDown") return { kind: "move", step: { row: 1, col: 0 } };
  if (key === "ArrowUp") return { kind: "move", step: { row: -1, col: 0 } };
  if (key === "Enter" || key === " " || key === "Spacebar") return { kind: "trace" };
  if (key === "Escape") return { kind: "cancel" };
  return null;
}

/** Apply one keyboard action, returning the new state and anything it submitted. */
export function applyKey(
  payload: WordSearchPayload,
  state: WordSearchState,
  key: string,
  config: Readonly<Record<string, unknown>> = {},
): { state: WordSearchState; outcome: TraceOutcome | null; handled: boolean } {
  const action = keyToAction(key);
  if (action === null) return { state, outcome: null, handled: false };
  if (action.kind === "move") {
    return { state: moveCursor(payload, state, action.step), outcome: null, handled: true };
  }
  if (action.kind === "cancel") {
    return { state: cancelTrace(state), outcome: null, handled: true };
  }
  if (state.anchor === null) {
    return { state: startTrace(payload, state), outcome: null, handled: true };
  }
  const outcome = submitTrace(payload, state, config);
  return { state: outcome.state, outcome, handled: true };
}

/** The player-facing strings; a Mode may override any of them via the config slice. */
export interface WordSearchLabels {
  prompt: string;
  grid: string;
  list: string;
  found: string;
  remaining: string;
  reveal: string;
  revealed: string;
  complete: string;
  already: string;
  alsoValid: string;
  miss: string;
  tracing: string;
  cellHint: string;
}

/** Tamil first, with the English the median player also reads (Player #7). */
export const DEFAULT_LABELS: WordSearchLabels = {
  // sol thedal - "word search"
  prompt: "\u0B9A\u0BCA\u0BB2\u0BCD \u0BA4\u0BC7\u0B9F\u0BB2\u0BCD",
  grid: "\u0B8E\u0BB4\u0BC1\u0BA4\u0BCD\u0BA4\u0BC1\u0B95\u0BCD \u0B95\u0B9F\u0BCD\u0B9F\u0BAE\u0BCD",
  list: "\u0BA4\u0BC7\u0B9F\u0BB5\u0BC7\u0BA3\u0BCD\u0B9F\u0BBF\u0BAF \u0B9A\u0BCA\u0BB1\u0BCD\u0B95\u0BB3\u0BCD",
  found: "\u0B95\u0BA3\u0BCD\u0B9F\u0BC1\u0BAA\u0BBF\u0B9F\u0BBF\u0BA4\u0BCD\u0BA4\u0BC0\u0BB0\u0BCD\u0B95\u0BB3\u0BCD!",
  remaining: "\u0BAE\u0BC0\u0BA4\u0BAE\u0BCD",
  reveal: "\u0B92\u0BB0\u0BC1 \u0B9A\u0BCA\u0BB2\u0BCD\u0BB2\u0BC8\u0B95\u0BCD \u0B95\u0BBE\u0B9F\u0BCD\u0B9F\u0BC1",
  revealed: "\u0B95\u0BBE\u0B9F\u0BCD\u0B9F\u0BAA\u0BCD\u0BAA\u0B9F\u0BCD\u0B9F\u0BA4\u0BC1",
  complete: "\u0B8E\u0BB2\u0BCD\u0BB2\u0BBE\u0B9A\u0BCD \u0B9A\u0BCA\u0BB1\u0BCD\u0B95\u0BB3\u0BC1\u0BAE\u0BCD \u0B95\u0BBF\u0B9F\u0BC8\u0BA4\u0BCD\u0BA4\u0BA9!",
  already: "\u0B8F\u0B95\u0BA9\u0BB5\u0BC7 \u0B95\u0BA3\u0BCD\u0B9F\u0BC1\u0BAA\u0BBF\u0B9F\u0BBF\u0BA4\u0BCD\u0BA4\u0BA4\u0BC1",
  alsoValid: "\u0B85\u0BA4\u0BC1\u0BB5\u0BC1\u0BAE\u0BCD \u0B92\u0BB0\u0BC1 \u0B9A\u0BCA\u0BB2\u0BCD - \u0B86\u0BA9\u0BBE\u0BB2\u0BCD \u0BAA\u0B9F\u0BCD\u0B9F\u0BBF\u0BAF\u0BB2\u0BBF\u0BB2\u0BCD \u0B87\u0BB2\u0BCD\u0BB2\u0BC8",
  miss: "\u0B85\u0BA4\u0BC1 \u0B92\u0BB0\u0BC1 \u0B9A\u0BCA\u0BB2\u0BCD \u0B85\u0BB2\u0BCD\u0BB2",
  tracing: "Tracing",
  cellHint: "Enter to start a trace, arrows to extend it, Enter again to submit",
};

/**
 * Resolve the labels from the injected config slice. The Game never imports the
 * app config or the copy map - a Mode hands down whatever it wants overridden
 * (Fowler: payloads, not calls), and the defaults keep a fresh clone playable.
 */
export function resolveLabels(
  config: Readonly<Record<string, unknown>> = {},
): WordSearchLabels {
  const overrides = config.labels;
  if (typeof overrides !== "object" || overrides === null) return DEFAULT_LABELS;
  const partial = overrides as Partial<Record<keyof WordSearchLabels, unknown>>;
  const merged: WordSearchLabels = { ...DEFAULT_LABELS };
  for (const key of Object.keys(DEFAULT_LABELS) as (keyof WordSearchLabels)[]) {
    const value = partial[key];
    if (typeof value === "string" && value.length > 0) merged[key] = value;
  }
  return merged;
}
