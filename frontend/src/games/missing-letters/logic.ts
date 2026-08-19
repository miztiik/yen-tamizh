// The missing-letters mechanic's pure core - no DOM, no storage, no singletons
// (docs/concepts/games.md `missing-letters`). Everything here is a function of
// its arguments, so the whole mechanic unit-tests in a node environment while
// the Svelte view stays a thin projection of this state.
//
// Three invariants the rest of the Game leans on:
//
//   - A BLANK IS A WHOLE EZHUTHU. `blanks` index the shared Row 6 segmentation
//     of the answer, never its code points, so a hole can never swallow half a
//     cluster (docs/concepts/core-loop.md). The payload deliberately does NOT
//     ship the segmentation: it is derived here from `word` by the same library
//     the generator used, which is why the two can never drift.
//   - THE BANK IS THE INPUT METHOD. There is no Tamil keyboard, so `choices` is
//     how a hidden ezhuthu is entered at all. It arrives already ordered by the
//     bake, so a re-render or a mid-puzzle reload never reshuffles it under the
//     player's thumb.
//   - A REAL WORD IS ANSWERED, NOT REJECTED. When more than one served word
//     fits the mask the generator records the others in `alsoValid`, so a
//     player who fills a real Tamil word is told it is one.

import { segment } from "../../tamil/ezhuthu";
import type { MissingLettersPuzzle } from "../../contracts/missing-letters-puzzle";

/**
 * The runtime payload: the `missing-letters-puzzle` contract minus its
 * schema-stamp fields. `version`/`changelog` describe how the SCHEMA FILE
 * evolves; a `puzzle-file` item's `payload` carries neither.
 */
export type MissingLettersPayload = Omit<MissingLettersPuzzle, "version" | "changelog">;

/** One honest hint from the payload: its kind, its text, and its score cost. */
export type MissingLettersHint = NonNullable<MissingLettersPayload["hints"]>[number];

/** One tile in the bank: an ezhuthu plus a stable id (the bank may repeat one). */
export interface Choice {
  readonly id: string;
  readonly ezhuthu: string;
}

/** One cell of the word as it is drawn: a printed ezhuthu, or a hole. */
export interface Cell {
  /** Position in `segment(word)`. */
  readonly index: number;
  /** Which hole this is (0-based), or -1 for a printed ezhuthu. */
  readonly blankIndex: number;
  /** What to render: the answer's ezhuthu, the filled one, or "". */
  readonly ezhuthu: string;
  /** The choice sitting in this hole, if any. */
  readonly choiceId: string | null;
}

/** The resumable state the runner persists; ids make a restore unambiguous. */
export interface MissingLettersState {
  /** Choice ids in hole order: entry i fills `payload.blanks[i]`. */
  filledChoiceIds: string[];
  /** Submitted attempts so far (a full board auto-submits). */
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

/**
 * Points per HOLE when the config slice does not set a base score.
 *
 * The count is of hidden ezhuthu, not of the word's length: this Game prints
 * most of the answer, and charging the same as a scramble - where every ezhuthu
 * has to be placed - would make the easier win worth more per unit of work. One
 * blank is 20 and two are 40, against the anagram's 40 to 60, which is the
 * honest ordering of the two boards.
 */
export const DEFAULT_POINTS_PER_BLANK = 20;

/** A fresh, untouched state. */
export function initialState(): MissingLettersState {
  return {
    filledChoiceIds: [],
    attempts: 0,
    revealedHintCount: 0,
    finished: false,
    score: 0,
    solved: false,
  };
}

/** Normalize an untrusted (persisted) snapshot back into a valid state. */
export function normalizeState(raw: unknown): MissingLettersState {
  const base = initialState();
  if (typeof raw !== "object" || raw === null) return base;
  const s = raw as Partial<MissingLettersState>;
  return {
    filledChoiceIds: Array.isArray(s.filledChoiceIds)
      ? s.filledChoiceIds.filter((id): id is string => typeof id === "string")
      : base.filledChoiceIds,
    attempts: typeof s.attempts === "number" ? s.attempts : base.attempts,
    revealedHintCount:
      typeof s.revealedHintCount === "number" ? s.revealedHintCount : base.revealedHintCount,
    finished: typeof s.finished === "boolean" ? s.finished : base.finished,
    score: typeof s.score === "number" ? s.score : base.score,
    solved: typeof s.solved === "boolean" ? s.solved : base.solved,
  };
}

/** The answer as ezhuthu - the only representation the mechanic compares. */
export function targetEzhuthu(payload: MissingLettersPayload): string[] {
  return segment(payload.word);
}

/** The bank, in the order the bake shuffled it. Ids are stable across renders. */
export function buildChoices(payload: MissingLettersPayload): Choice[] {
  return payload.choices.map((ezhuthu, index) => ({ id: `c${index}`, ezhuthu }));
}

/** The ezhuthu a choice id carries, or "" when the id is unknown. */
function ezhuthuOf(choices: readonly Choice[], id: string | undefined): string {
  if (id === undefined) return "";
  return choices.find((choice) => choice.id === id)?.ezhuthu ?? "";
}

/**
 * The word as it is drawn right now: every position, marked as printed or as a
 * hole, with whatever the player has dropped into it.
 */
export function cells(
  payload: MissingLettersPayload,
  choices: readonly Choice[],
  state: MissingLettersState,
): Cell[] {
  const answer = targetEzhuthu(payload);
  return answer.map((ezhuthu, index) => {
    const blankIndex = payload.blanks.indexOf(index);
    if (blankIndex === -1) {
      return { index, blankIndex, ezhuthu, choiceId: null };
    }
    const choiceId = state.filledChoiceIds[blankIndex] ?? null;
    return {
      index,
      blankIndex,
      ezhuthu: choiceId === null ? "" : ezhuthuOf(choices, choiceId),
      choiceId,
    };
  });
}

/** Choices still in the bank (a placement takes one out). */
export function remainingChoices(
  choices: readonly Choice[],
  state: MissingLettersState,
): Choice[] {
  return choices.filter((choice) => !state.filledChoiceIds.includes(choice.id));
}

/** Whether every hole is filled (the auto-submit trigger). */
export function isFull(payload: MissingLettersPayload, state: MissingLettersState): boolean {
  return state.filledChoiceIds.length === payload.blanks.length;
}

/** The word the player has currently spelled, holes included as they stand. */
export function spelledWord(
  payload: MissingLettersPayload,
  choices: readonly Choice[],
  state: MissingLettersState,
): string {
  return cells(payload, choices, state)
    .map((cell) => cell.ezhuthu)
    .join("");
}

/** Whether the board spells the answer. */
export function isSolved(
  payload: MissingLettersPayload,
  choices: readonly Choice[],
  state: MissingLettersState,
): boolean {
  return spelledWord(payload, choices, state) === payload.word;
}

/**
 * Whether the board spells one of the OTHER served words this mask admits
 * (`payload.alsoValid`, resolved at bake time - a Game may not read a wordlist).
 */
export function isAlsoValid(
  payload: MissingLettersPayload,
  choices: readonly Choice[],
  state: MissingLettersState,
): boolean {
  // Widened deliberately: the generated type is a minItems tuple, and a tuple
  // union collapses `includes`' parameter to `never`.
  const alternatives: readonly string[] = payload.alsoValid ?? [];
  return alternatives.includes(spelledWord(payload, choices, state));
}

/** Attempts left before the puzzle ends (never negative). */
export function attemptsRemaining(
  payload: MissingLettersPayload,
  state: MissingLettersState,
): number {
  return Math.max(0, payload.attempts - state.attempts);
}

/** The hints the player has revealed so far, in payload order. */
export function revealedHints(
  payload: MissingLettersPayload,
  state: MissingLettersState,
): MissingLettersHint[] {
  return (payload.hints ?? []).slice(0, state.revealedHintCount);
}

/** The next hint to reveal, or `null` when they are all spent. */
export function nextHint(
  payload: MissingLettersPayload,
  state: MissingLettersState,
): MissingLettersHint | null {
  return (payload.hints ?? [])[state.revealedHintCount] ?? null;
}

/**
 * The score before hints: `config.baseScore` when the Mode sets one, else a
 * sane default that scales with how much of the word is HIDDEN (Holy Law #6 -
 * a fresh clone runs on the defaults, and the knob arrives through the config
 * slice, never an import of the app config).
 */
export function baseScore(
  payload: MissingLettersPayload,
  config: Readonly<Record<string, unknown>> = {},
): number {
  const configured = config.baseScore;
  if (typeof configured === "number" && Number.isFinite(configured) && configured > 0) {
    return Math.round(configured);
  }
  return payload.blanks.length * DEFAULT_POINTS_PER_BLANK;
}

/**
 * The awarded score: the base minus the cost of every hint the player revealed
 * (docs/concepts/difficulty-and-scoring.md - a hint costs the brag, not money).
 * Clamped at 0 so a heavily-hinted win never goes negative.
 */
export function scoreFor(
  payload: MissingLettersPayload,
  state: MissingLettersState,
  config: Readonly<Record<string, unknown>> = {},
): number {
  const spent = revealedHints(payload, state).reduce((sum, hint) => sum + hint.cost, 0);
  return Math.max(0, baseScore(payload, config) - spent);
}

/** Drop a choice into the next empty hole. No-op when finished, full, or used. */
export function fillNextBlank(
  payload: MissingLettersPayload,
  state: MissingLettersState,
  choiceId: string,
): MissingLettersState {
  if (state.finished || isFull(payload, state) || state.filledChoiceIds.includes(choiceId)) {
    return state;
  }
  return { ...state, filledChoiceIds: [...state.filledChoiceIds, choiceId] };
}

/** Take one hole's choice back to the bank (tap a filled blank to undo it). */
export function clearBlank(
  state: MissingLettersState,
  blankIndex: number,
): MissingLettersState {
  if (state.finished || blankIndex < 0 || blankIndex >= state.filledChoiceIds.length) {
    return state;
  }
  return {
    ...state,
    filledChoiceIds: state.filledChoiceIds.filter((_, index) => index !== blankIndex),
  };
}

/** Undo the last placement (Backspace). */
export function undoLast(state: MissingLettersState): MissingLettersState {
  if (state.finished || state.filledChoiceIds.length === 0) return state;
  return { ...state, filledChoiceIds: state.filledChoiceIds.slice(0, -1) };
}

/** Empty every hole (Escape). */
export function clearFilled(state: MissingLettersState): MissingLettersState {
  if (state.finished || state.filledChoiceIds.length === 0) return state;
  return { ...state, filledChoiceIds: [] };
}

/** Reveal the next hint; the cost is applied when the puzzle is scored. */
export function revealNextHint(
  payload: MissingLettersPayload,
  state: MissingLettersState,
): MissingLettersState {
  if (state.finished || nextHint(payload, state) === null) return state;
  return { ...state, revealedHintCount: state.revealedHintCount + 1 };
}

/** The outcome of submitting a full board. */
export interface AttemptOutcome {
  state: MissingLettersState;
  correct: boolean;
  /** True when this attempt ended the puzzle without a win (attempts spent). */
  exhausted: boolean;
  /**
   * True when the miss was a REAL served word that is simply not today's - the
   * third state. It is false on the exhausting attempt even when the board was
   * a word: the terminal message wins, one message per moment. It never changes
   * the accounting - an alternative spends an attempt exactly like any other
   * miss.
   */
  alternative: boolean;
  attemptIndex: number;
  /** The submitted board as a word, for the attempt event. */
  attempt: string;
}

/**
 * Submit the current board. A win finishes and scores; a miss spends an attempt
 * and empties the holes so the player can try again; spending the last attempt
 * ends the puzzle honestly (no purchase, no timer - Palm).
 */
export function submitAttempt(
  payload: MissingLettersPayload,
  choices: readonly Choice[],
  state: MissingLettersState,
  config: Readonly<Record<string, unknown>> = {},
): AttemptOutcome {
  const attempt = spelledWord(payload, choices, state);
  const correct = isSolved(payload, choices, state);
  const attempts = state.attempts + 1;

  if (correct) {
    const solvedState: MissingLettersState = {
      ...state,
      attempts,
      finished: true,
      solved: true,
    };
    return {
      state: { ...solvedState, score: scoreFor(payload, solvedState, config) },
      correct: true,
      exhausted: false,
      alternative: false,
      attemptIndex: attempts,
      attempt,
    };
  }

  const exhausted = attempts >= payload.attempts;
  return {
    state: { ...state, attempts, filledChoiceIds: [], finished: exhausted },
    correct: false,
    exhausted,
    alternative: !exhausted && isAlsoValid(payload, choices, state),
    attemptIndex: attempts,
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
export interface MissingLettersLabels {
  prompt: string;
  bank: string;
  answer: string;
  hint: string;
  hintsSpent: string;
  attemptsLeft: string;
  correct: string;
  wrong: string;
  alsoValid: string;
  outOfAttempts: string;
  blank: string;
  filledBlank: string;
  shown: string;
  choice: string;
}

/** Tamil first, with the English the median player also reads (Player #7). */
export const DEFAULT_LABELS: MissingLettersLabels = {
  prompt: "இடைவெளியை நிரப்புங்கள்",
  bank: "எழுத்துகள்",
  answer: "சொல்",
  hint: "குறிப்பு",
  hintsSpent: "குறிப்புகள் முடிந்தன",
  attemptsLeft: "முயற்சி மீதம்",
  correct: "சரி!",
  wrong: "தவறு",
  alsoValid: "இது ஒரு சொல், ஆனால் இன்றைய சொல் அல்ல",
  outOfAttempts: "முயற்சிகள் முடிந்தன",
  blank: "Blank",
  filledBlank: "Remove letter from blank",
  shown: "Letter",
  choice: "Fill the next blank",
};

/**
 * Resolve the labels from the injected config slice. The Game never imports the
 * app config or the copy map - a Mode hands down whatever it wants overridden
 * (Fowler: payloads, not calls), and the defaults keep a fresh clone playable.
 */
export function resolveLabels(
  config: Readonly<Record<string, unknown>> = {},
): MissingLettersLabels {
  const overrides = config.labels;
  if (typeof overrides !== "object" || overrides === null) return DEFAULT_LABELS;
  const partial = overrides as Partial<Record<keyof MissingLettersLabels, unknown>>;
  const merged: MissingLettersLabels = { ...DEFAULT_LABELS };
  for (const key of Object.keys(DEFAULT_LABELS) as (keyof MissingLettersLabels)[]) {
    const value = partial[key];
    if (typeof value === "string" && value.length > 0) merged[key] = value;
  }
  return merged;
}
