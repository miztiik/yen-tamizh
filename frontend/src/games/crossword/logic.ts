// The crossword mechanic's pure core - no DOM, no storage, no singletons
// (docs/concepts/games.md `crossword`). Everything here is a function of its
// arguments, so the whole mechanic unit-tests in a node environment while the
// Svelte view stays a thin projection of this state.
//
// Five invariants the rest of the Game leans on:
//
//   - A CELL HOLDS ONE EZHUTHU. The payload names each answer and where it
//     starts; the board is the union of those answers, so which cells are open,
//     what number each carries and what the finished grid says are all DERIVED
//     here rather than shipped. Working in code points would let a player half
//     fill a cluster and leave a cell holding a vowel sign nobody can read.
//   - A CROSSING CELL BELONGS TO BOTH ITS ANSWERS. Writing into it writes into
//     the across answer and the down answer at once, which is the whole game:
//     the letters a player is sure of are what makes the answers they are not
//     sure of gettable.
//   - THE CURSOR AND THE DIRECTION ARE ONE THING. A cell is ambiguous - two
//     answers run through it - so the board always knows which of them is being
//     written, and both the pointer and the keyboard change it the same way.
//     Tapping the cell you are already on turns the corner; so does Enter.
//   - A WRONG LETTER COSTS NOTHING. Writing is how a player thinks on a
//     crossword, and charging for it would make the board a quiz. There is no
//     attempt budget and no way to lose.
//   - REVEALING IS THE ONLY PRICE. A player stuck on one answer may hand it
//     over, and it is paid for in exactly that answer's points. That is why this
//     Game bakes no hint ladder: the board already prints a meaning per entry,
//     free, so every rung the shared ladder can render is a fact on the screen.

import { classify, segment } from "../../tamil/ezhuthu";
import type { CrosswordPuzzle } from "../../contracts/crossword-puzzle";

/**
 * The runtime payload: the `crossword-puzzle` contract minus its schema-stamp
 * fields. `version`/`changelog` describe how the SCHEMA FILE evolves; a
 * `puzzle-file` item's `payload` carries neither.
 */
export type CrosswordPayload = Omit<CrosswordPuzzle, "version" | "changelog">;

/** One answer on the board, as it travels in the payload. */
export type Entry = CrosswordPayload["entries"][number];

/** The two ways an answer runs. */
export type Direction = Entry["direction"];

/** One cell address in the grid. */
export interface Cell {
  row: number;
  col: number;
}

/** Each direction as the (row, col) step it takes. */
export const STEPS: Readonly<Record<Direction, Cell>> = {
  across: { row: 0, col: 1 },
  down: { row: 1, col: 0 },
};

/** Points per ezhuthu solved - the same rate every other Game pays. */
export const DEFAULT_POINTS_PER_EZHUTHU = 10;

/** The pulli, which turns a consonant into a bare mei. */
export const PULLI = "\u0BCD";

/** The aytham, which is its own letter and takes no vowel. */
export const AYTHAM = "\u0B83";

/**
 * The twelve independent vowels, in chart order.
 *
 * Written out rather than derived from a code-point range because the Tamil
 * block is not contiguous there - U+0B8B is followed by a gap - and a range
 * would silently pick up a reserved point.
 */
export const UYIR: readonly string[] = [
  "\u0B85",
  "\u0B86",
  "\u0B87",
  "\u0B88",
  "\u0B89",
  "\u0B8A",
  "\u0B8E",
  "\u0B8F",
  "\u0B90",
  "\u0B92",
  "\u0B93",
  "\u0B94",
];

/** The twelve vowel SIGNS, in the same order - the a-form writes nothing. */
export const MATRA: readonly string[] = [
  "",
  "\u0BBE",
  "\u0BBF",
  "\u0BC0",
  "\u0BC1",
  "\u0BC2",
  "\u0BC6",
  "\u0BC7",
  "\u0BC8",
  "\u0BCA",
  "\u0BCB",
  "\u0BCC",
];

/** The eighteen consonant bases, in chart order. */
export const MEI_BASES: readonly string[] = [
  "\u0B95",
  "\u0B99",
  "\u0B9A",
  "\u0B9E",
  "\u0B9F",
  "\u0BA3",
  "\u0BA4",
  "\u0BA8",
  "\u0BAA",
  "\u0BAE",
  "\u0BAF",
  "\u0BB0",
  "\u0BB2",
  "\u0BB5",
  "\u0BB4",
  "\u0BB3",
  "\u0BB1",
  "\u0BA9",
];

/**
 * The thirteen forms a consonant can take: the bare mei, then the twelve
 * vowels. One tap on a base writes its a-form; one tap on a form RE-SPELLS the
 * cell into that row of the chart, so a whole ezhuthu is always one key plus at
 * most one more - there is no pending half-written state a player could be left
 * holding.
 */
export const VOWEL_FORMS: readonly string[] = [PULLI, ...MATRA];

/** The keys that COMMIT a letter on their own. */
export const BASE_KEYS: readonly string[] = [...UYIR, AYTHAM, ...MEI_BASES];

/** Compose a consonant base with one vowel form. */
export function compose(base: string, form: string): string {
  return base + form;
}

/** The consonant base of an ezhuthu, or `null` when it takes no vowel form. */
export function baseOf(ezhuthu: string): string | null {
  const base = ezhuthu.slice(0, 1);
  return MEI_BASES.includes(base) ? base : null;
}

/** The resumable state the runner persists. */
export interface CrosswordState {
  /** What the player has written, keyed `"row,col"`. */
  filled: Record<string, string>;
  /** Answers the player handed over rather than worked out. */
  revealed: string[];
  /** Where the caret is. Always on an open cell. */
  cursor: Cell;
  /** Which of the two answers through the caret is being written. */
  direction: Direction;
  /**
   * The square the last base key wrote, which is the square a vowel form
   * re-spells. Cleared by anything that moves the caret, because after a move
   * the player is no longer writing that letter.
   */
  lastWritten: Cell | null;
  /** Terminal flag: every answer is settled, solved or revealed. */
  finished: boolean;
  /** Awarded points. */
  score: number;
  /** Whether every answer was worked out rather than revealed. */
  solved: boolean;
}

/** One cell address as a map key. */
export function cellKey(cell: Cell): string {
  return `${cell.row},${cell.col}`;
}

/** The cells one entry covers, from its start along its direction. */
export function entryCells(entry: Entry): Cell[] {
  const step = STEPS[entry.direction];
  return segment(entry.word).map((_, index) => ({
    row: entry.start.row + step.row * index,
    col: entry.start.col + step.col * index,
  }));
}

/** Every open cell on the board - the union of the entries, nothing else. */
export function openCells(payload: CrosswordPayload): Set<string> {
  const open = new Set<string>();
  for (const entry of payload.entries) {
    for (const cell of entryCells(entry)) open.add(cellKey(cell));
  }
  return open;
}

/** Whether a cell is on the board and not blocked. */
export function isOpen(payload: CrosswordPayload, cell: Cell): boolean {
  return openCells(payload).has(cellKey(cell));
}

/** The number printed in each starting cell, keyed `"row,col"`. */
export function numbers(payload: CrosswordPayload): Map<string, number> {
  const marks = new Map<string, number>();
  for (const entry of payload.entries) marks.set(cellKey(entry.start), entry.number);
  return marks;
}

/** The finished grid: what every open cell holds when the board is right. */
export function solution(payload: CrosswordPayload): Map<string, string> {
  const grid = new Map<string, string>();
  for (const entry of payload.entries) {
    const units = segment(entry.word);
    entryCells(entry).forEach((cell, index) => {
      const unit = units[index];
      if (unit !== undefined) grid.set(cellKey(cell), unit);
    });
  }
  return grid;
}

/** The first open cell in reading order - where a fresh board starts. */
export function firstCell(payload: CrosswordPayload): Cell {
  const starts = payload.entries.map((entry) => entry.start);
  return starts.reduce((best, cell) =>
    cell.row < best.row || (cell.row === best.row && cell.col < best.col) ? cell : best,
  );
}

/** A fresh, untouched state. */
export function initialState(payload?: CrosswordPayload): CrosswordState {
  return {
    filled: {},
    revealed: [],
    cursor: payload === undefined ? { row: 0, col: 0 } : firstCell(payload),
    direction: "across",
    lastWritten: null,
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

/**
 * Normalize an untrusted (persisted) snapshot back into a valid state.
 *
 * A restored letter in a cell this board does not have is dropped, and so is a
 * revealed answer this board does not ask for: a save from a previous day would
 * otherwise paint cells of a grid it never saw.
 */
export function normalizeState(payload: CrosswordPayload, raw: unknown): CrosswordState {
  const base = initialState(payload);
  if (typeof raw !== "object" || raw === null) return base;
  const snapshot = raw as Partial<CrosswordState>;
  const open = openCells(payload);
  const filled: Record<string, string> = {};
  if (typeof snapshot.filled === "object" && snapshot.filled !== null) {
    for (const [key, value] of Object.entries(snapshot.filled)) {
      if (open.has(key) && typeof value === "string" && segment(value).length === 1) {
        filled[key] = value;
      }
    }
  }
  const wanted = new Set(payload.entries.map((entry) => entry.word));
  const revealed = Array.isArray(snapshot.revealed)
    ? snapshot.revealed.filter(
        (word): word is string => typeof word === "string" && wanted.has(word),
      )
    : [];
  const cursor =
    isCell(snapshot.cursor) && open.has(cellKey(snapshot.cursor))
      ? snapshot.cursor
      : base.cursor;
  const direction = snapshot.direction === "down" ? "down" : "across";
  return settle(payload, { ...base, filled, revealed, cursor, direction });
}
/** The entry running `direction` through `cell`, or `null` when there is none. */
export function entryThrough(
  payload: CrosswordPayload,
  cell: Cell,
  direction: Direction,
): Entry | null {
  for (const entry of payload.entries) {
    if (entry.direction !== direction) continue;
    if (entryCells(entry).some((each) => each.row === cell.row && each.col === cell.col)) {
      return entry;
    }
  }
  return null;
}

/** The entry the caret is currently writing, preferring the chosen direction. */
export function activeEntry(
  payload: CrosswordPayload,
  state: CrosswordState,
): Entry | null {
  return (
    entryThrough(payload, state.cursor, state.direction) ??
    entryThrough(payload, state.cursor, state.direction === "across" ? "down" : "across")
  );
}

/** What the player has written into one entry, cell by cell (`""` when empty). */
export function writtenIn(state: CrosswordState, entry: Entry): string[] {
  return entryCells(entry).map((cell) => state.filled[cellKey(cell)] ?? "");
}

/** Whether one answer is on the board: written correctly, or handed over. */
export function isSettled(state: CrosswordState, entry: Entry): boolean {
  if (state.revealed.includes(entry.word)) return true;
  const written = writtenIn(state, entry).join("");
  if (written === entry.word) return true;
  // An alternative is a word that fits every crossing AND is a listed synonym
  // of the answer, so it answers the same clue; the payload proved both. The
  // generated type is a min-length tuple, and `.includes` on one narrows its
  // parameter to `never` - so it is widened before the lookup.
  const alternatives: readonly string[] = entry.alsoValid ?? [];
  return alternatives.includes(written);
}

/** Whether every cell of one answer has a letter in it. */
export function isComplete(state: CrosswordState, entry: Entry): boolean {
  return writtenIn(state, entry).every((unit) => unit !== "");
}

/** The answers still outstanding, in payload order. */
export function outstanding(
  payload: CrosswordPayload,
  state: CrosswordState,
): Entry[] {
  return payload.entries.filter((entry) => !isSettled(state, entry));
}

/** What one answer is worth: its ezhuthu count at the shared rate. */
export function entryValue(entry: Entry): number {
  return segment(entry.word).length * DEFAULT_POINTS_PER_EZHUTHU;
}

/** The whole board's value, if every answer is worked out. */
export function fullScore(
  payload: CrosswordPayload,
  config: Readonly<Record<string, unknown>> = {},
): number {
  const configured = config.baseScore;
  if (typeof configured === "number" && Number.isFinite(configured) && configured > 0) {
    return Math.round(configured);
  }
  return payload.entries.reduce((sum, entry) => sum + entryValue(entry), 0);
}

/**
 * The score so far: the share of the board's value the player WORKED OUT.
 *
 * A revealed answer earns nothing, which is the whole price of revealing - and
 * it is proportional rather than all-or-nothing, so a player stuck on the last
 * answer keeps everything they earned before it.
 */
export function scoreFor(
  payload: CrosswordPayload,
  state: CrosswordState,
  config: Readonly<Record<string, unknown>> = {},
): number {
  const earned = payload.entries
    .filter((entry) => !state.revealed.includes(entry.word) && isSettled(state, entry))
    .reduce((sum, entry) => sum + entryValue(entry), 0);
  const whole = payload.entries.reduce((sum, entry) => sum + entryValue(entry), 0);
  if (whole === 0) return 0;
  return Math.round((fullScore(payload, config) * earned) / whole);
}

/** Recompute the derived flags after any change to what is on the board. */
function settle(
  payload: CrosswordPayload,
  state: CrosswordState,
  config: Readonly<Record<string, unknown>> = {},
): CrosswordState {
  const done = outstanding(payload, state).length === 0;
  return {
    ...state,
    finished: done,
    solved: done && state.revealed.length === 0,
    score: scoreFor(payload, state, config),
  };
}

/**
 * The direction that really runs through a square, preferring ``wanted``.
 *
 * Most squares carry only ONE answer, so a caret arriving there with the other
 * direction still set would highlight one answer and write the other - the
 * caret steps along whatever is active, so the second letter would land
 * sideways. Adopting the direction that exists is what keeps the highlighted
 * answer and the answer being written the same thing.
 */
function directionAt(
  payload: CrosswordPayload,
  cell: Cell,
  wanted: Direction,
): Direction {
  if (entryThrough(payload, cell, wanted) !== null) return wanted;
  const flipped: Direction = wanted === "across" ? "down" : "across";
  return entryThrough(payload, cell, flipped) !== null ? flipped : wanted;
}

/** Put the caret on a cell. Tapping the cell it is already on turns the corner. */
export function setCursor(
  payload: CrosswordPayload,
  state: CrosswordState,
  cell: Cell,
): CrosswordState {
  if (!isOpen(payload, cell)) return state;
  const same = state.cursor.row === cell.row && state.cursor.col === cell.col;
  const flipped: Direction = state.direction === "across" ? "down" : "across";
  const turned = same && entryThrough(payload, cell, flipped) !== null;
  return {
    ...state,
    cursor: cell,
    direction: directionAt(payload, cell, turned ? flipped : state.direction),
    lastWritten: null,
  };
}

/** Turn the corner: write the other answer through this cell. */
export function toggleDirection(
  payload: CrosswordPayload,
  state: CrosswordState,
): CrosswordState {
  const flipped: Direction = state.direction === "across" ? "down" : "across";
  if (entryThrough(payload, state.cursor, flipped) === null) return state;
  return { ...state, direction: flipped, lastWritten: null };
}

/**
 * Move the caret one step, skipping blocked cells.
 *
 * A crossword is not a rectangle of cells, so arrowing has to jump the blocks -
 * stopping at the first open cell in the direction asked for and staying put
 * when there is none. Moving along a row or a column also SETS the direction,
 * because a player arrowing sideways is telling the board which answer they
 * mean.
 */
export function moveCursor(
  payload: CrosswordPayload,
  state: CrosswordState,
  step: Cell,
): CrosswordState {
  const open = openCells(payload);
  let cell = { row: state.cursor.row + step.row, col: state.cursor.col + step.col };
  const height = payload.rows;
  const width = payload.cols;
  while (cell.row >= 0 && cell.row < height && cell.col >= 0 && cell.col < width) {
    if (open.has(cellKey(cell))) {
      return {
        ...state,
        cursor: cell,
        direction: directionAt(payload, cell, step.row === 0 ? "across" : "down"),
        lastWritten: null,
      };
    }
    cell = { row: cell.row + step.row, col: cell.col + step.col };
  }
  return state;
}

/** The next cell along the answer being written, or the same cell at its end. */
function advance(
  payload: CrosswordPayload,
  state: CrosswordState,
): Cell {
  const entry = activeEntry(payload, state);
  if (entry === null) return state.cursor;
  const cells = entryCells(entry);
  const at = cells.findIndex(
    (cell) => cell.row === state.cursor.row && cell.col === state.cursor.col,
  );
  const next = cells[at + 1];
  return next ?? state.cursor;
}

/** What writing one letter turned out to do. */
export interface WriteOutcome {
  state: CrosswordState;
  /** The entry that just became complete, if one did. */
  completed: Entry | null;
  /** Whether that completed entry is right. */
  correct: boolean;
  /** True when this letter settled the last outstanding answer. */
  finished: boolean;
}

/**
 * Write one ezhuthu into the caret's cell and step along.
 *
 * A settled answer is not frozen: a player may write over their own work, which
 * is what a pencil does. What cannot be written over is an answer they handed
 * over - that one is the board's, not theirs.
 */
export function writeEzhuthu(
  payload: CrosswordPayload,
  state: CrosswordState,
  unit: string,
  config: Readonly<Record<string, unknown>> = {},
): WriteOutcome {
  const blank = { state, completed: null, correct: false, finished: state.finished };
  if (state.finished || !isOpen(payload, state.cursor)) return blank;
  if (segment(unit).length !== 1) return blank;
  if (isLockedCell(payload, state, state.cursor)) return blank;
  const here = state.cursor;
  const filled = { ...state.filled, [cellKey(here)]: unit };
  const written = settle(payload, { ...state, filled, lastWritten: here }, config);
  const entry = activeEntry(payload, state);
  const wasComplete = entry !== null && isComplete(state, entry);
  const nowComplete = entry !== null && isComplete(written, entry);
  return {
    state: { ...written, cursor: advance(payload, { ...written, cursor: here }) },
    completed: !wasComplete && nowComplete ? entry : null,
    correct: entry !== null && isSettled(written, entry),
    finished: written.finished,
  };
}

/**
 * The square a vowel form re-spells: the one the composer just wrote, or the
 * one under the caret when the player has moved there to correct it.
 *
 * Writing steps the caret along, so by the time the second half of the composer
 * is tapped the caret is already past the square being written - the same
 * problem the wordle's form row solves by always re-spelling the LAST cell
 * composed. Reading the caret's own square instead would be ambiguous exactly
 * where a crossword is interesting: the next square along is often a crossing
 * already filled by another answer, and a form key would silently re-shape THAT
 * letter rather than the one just written.
 */
export function formTarget(
  payload: CrosswordPayload,
  state: CrosswordState,
): Cell | null {
  const target = state.lastWritten ?? state.cursor;
  if (!isOpen(payload, target) || isLockedCell(payload, state, target)) return null;
  return baseOf(state.filled[cellKey(target)] ?? "") === null ? null : target;
}

/** The base whose thirteen forms the form row is showing, or `null` for none. */
export function liveBase(
  payload: CrosswordPayload,
  state: CrosswordState,
): string | null {
  const target = formTarget(payload, state);
  return target === null ? null : baseOf(state.filled[cellKey(target)] ?? "");
}

/**
 * Re-spell the square the composer is on into another row of the letter chart.
 *
 * The composer's second kind of key: the square already holds a consonant, and
 * this swaps its vowel. It does NOT step along, because the player is still
 * writing the same letter - so a base and a form are two taps for one ezhuthu,
 * which is what makes the 216 uyirmei reachable at all.
 */
export function applyVowelForm(
  payload: CrosswordPayload,
  state: CrosswordState,
  form: string,
): CrosswordState {
  if (state.finished) return state;
  const target = formTarget(payload, state);
  if (target === null) return state;
  const base = baseOf(state.filled[cellKey(target)] ?? "");
  if (base === null) return state;
  return settle(payload, {
    ...state,
    filled: { ...state.filled, [cellKey(target)]: compose(base, form) },
  });
}

/** Whether a cell belongs to an answer the player handed over. */
export function isLockedCell(
  payload: CrosswordPayload,
  state: CrosswordState,
  cell: Cell,
): boolean {
  return payload.entries.some(
    (entry) =>
      state.revealed.includes(entry.word) &&
      entryCells(entry).some((each) => each.row === cell.row && each.col === cell.col),
  );
}

/** Clear the caret's cell, or step back and clear that one when it is empty. */
export function backspace(
  payload: CrosswordPayload,
  state: CrosswordState,
): CrosswordState {
  if (state.finished) return state;
  const here = cellKey(state.cursor);
  if (state.filled[here] !== undefined && !isLockedCell(payload, state, state.cursor)) {
    const filled = { ...state.filled };
    delete filled[here];
    return settle(payload, { ...state, filled, lastWritten: null });
  }
  const entry = activeEntry(payload, state);
  if (entry === null) return state;
  const cells = entryCells(entry);
  const at = cells.findIndex(
    (cell) => cell.row === state.cursor.row && cell.col === state.cursor.col,
  );
  const previous = cells[at - 1];
  if (previous === undefined) return state;
  if (isLockedCell(payload, state, previous)) {
    return { ...state, cursor: previous, lastWritten: null };
  }
  const filled = { ...state.filled };
  delete filled[cellKey(previous)];
  return settle(payload, { ...state, filled, cursor: previous, lastWritten: null });
}

/** The next answer a reveal would hand over, or `null` when none is left. */
export function nextReveal(
  payload: CrosswordPayload,
  state: CrosswordState,
): Entry | null {
  const active = activeEntry(payload, state);
  if (active !== null && !isSettled(state, active)) return active;
  return outstanding(payload, state)[0] ?? null;
}

/** The outcome of handing one answer over. */
export interface RevealOutcome {
  state: CrosswordState;
  entry: Entry | null;
  cost: number;
}

/**
 * Hand over the answer the caret is on, filling its cells and forfeiting its
 * points. It cannot be expressed as a baked hint: what it costs depends on
 * which answers are still open when it is spent.
 */
export function revealNext(
  payload: CrosswordPayload,
  state: CrosswordState,
  config: Readonly<Record<string, unknown>> = {},
): RevealOutcome {
  const entry = nextReveal(payload, state);
  if (entry === null || state.finished) return { state, entry: null, cost: 0 };
  const units = segment(entry.word);
  const filled = { ...state.filled };
  entryCells(entry).forEach((cell, index) => {
    const unit = units[index];
    if (unit !== undefined) filled[cellKey(cell)] = unit;
  });
  return {
    state: settle(
      payload,
      { ...state, filled, revealed: [...state.revealed, entry.word], lastWritten: null },
      config,
    ),
    entry,
    cost: entryValue(entry),
  };
}

/** What a bare key press means on the grid. */
export type GridAction =
  | { kind: "move"; step: Cell }
  | { kind: "turn" }
  | { kind: "erase" }
  | null;

/** Map a keyboard event's `key` onto a grid action. */
export function keyToAction(key: string): GridAction {
  switch (key) {
    case "ArrowUp":
      return { kind: "move", step: { row: -1, col: 0 } };
    case "ArrowDown":
      return { kind: "move", step: { row: 1, col: 0 } };
    case "ArrowLeft":
      return { kind: "move", step: { row: 0, col: -1 } };
    case "ArrowRight":
      return { kind: "move", step: { row: 0, col: 1 } };
    case "Enter":
    case " ":
      return { kind: "turn" };
    case "Backspace":
    case "Delete":
      return { kind: "erase" };
    default:
      return null;
  }
}

/** Apply one bare key press to the board. */
export function applyKey(
  payload: CrosswordPayload,
  state: CrosswordState,
  key: string,
): CrosswordState {
  const action = keyToAction(key);
  if (action === null) return state;
  if (action.kind === "move") return moveCursor(payload, state, action.step);
  if (action.kind === "turn") return toggleDirection(payload, state);
  return backspace(payload, state);
}

/** Player-facing wording, all of it overridable through the config slice. */
export interface CrosswordLabels {
  prompt: string;
  grid: string;
  across: string;
  down: string;
  remaining: string;
  reveal: string;
  revealed: string;
  cellHint: string;
  keyboard: string;
  erase: string;
  turn: string;
}

/** The shipped Tamil wording. */
export const DEFAULT_LABELS: CrosswordLabels = {
  prompt: "\u0B9A\u0BCA\u0BB1\u0BCD\u0B95\u0B9F\u0BCD\u0B9F\u0BAE\u0BCD",
  grid: "\u0B95\u0B9F\u0BCD\u0B9F\u0BAE\u0BCD",
  across: "\u0B95\u0BC1\u0BB1\u0BC1\u0B95\u0BC7",
  down: "\u0BA8\u0BC6\u0B9F\u0BC1\u0B95\u0BC7",
  remaining: "\u0BAE\u0BC0\u0BA4\u0BAE\u0BCD",
  reveal: "\u0BB5\u0BBF\u0B9F\u0BC8 \u0B95\u0BBE\u0B9F\u0BCD\u0B9F\u0BC1",
  revealed: "\u0BB5\u0BBF\u0B9F\u0BC8",
  cellHint:
    "\u0B85\u0BAE\u0BCD\u0BAA\u0BC1\u0B95\u0BB3\u0BBF\u0BB2\u0BCD \u0BA8\u0B95\u0BB0\u0BCD\u0BA4\u0BCD\u0BA4\u0BC1\u0B99\u0BCD\u0B95\u0BB3\u0BCD; Enter \u0BA4\u0BBF\u0BB0\u0BC1\u0BAA\u0BCD\u0BAA\u0BC1\u0B95\u0BBF\u0BB1\u0BA4\u0BC1",
  keyboard: "\u0B8E\u0BB4\u0BC1\u0BA4\u0BCD\u0BA4\u0BC1\u0B95\u0BB3\u0BCD",
  erase: "\u0B85\u0BB4\u0BBF",
  turn: "\u0BA4\u0BBF\u0BB0\u0BC1\u0BAA\u0BCD\u0BAA\u0BC1",
};

/**
 * Merge the config slice's overrides over the shipped wording.
 *
 * `labels` is the same key the other four Games read, and deliberately so: one
 * session hands one config slice to every Game in its playlist, so a second key
 * per Game would be a channel the shell has to know the name of.
 */
export function resolveLabels(
  config: Readonly<Record<string, unknown>> = {},
): CrosswordLabels {
  const raw = config.labels;
  if (typeof raw !== "object" || raw === null) return DEFAULT_LABELS;
  const overrides = raw as Partial<Record<keyof CrosswordLabels, unknown>>;
  const merged = { ...DEFAULT_LABELS };
  for (const key of Object.keys(DEFAULT_LABELS) as (keyof CrosswordLabels)[]) {
    const value = overrides[key];
    if (typeof value === "string" && value.length > 0) merged[key] = value;
  }
  return merged;
}

/** Whether an ezhuthu takes a vowel form - a consonant does, a vowel does not. */
export function takesVowelForm(ezhuthu: string): boolean {
  const kind = classify(ezhuthu);
  return kind === "mei" || kind === "uyirmei";
}
