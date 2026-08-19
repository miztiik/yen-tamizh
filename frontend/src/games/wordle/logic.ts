// The wordle mechanic's pure core - no DOM, no storage, no singletons
// (docs/concepts/games.md `wordle`). Everything here is a function of its
// arguments, so the whole mechanic unit-tests in a node environment while the
// Svelte views stay a thin projection of this state.
//
// Four invariants the rest of the Game leans on:
//
//   - THE UNIT IS THE EZHUTHU, EVERYWHERE. A board cell holds one ezhuthu, a
//     mark describes one ezhuthu, and a keyboard key commits one ezhuthu. The
//     answer is segmented by the shared Row 6 library rather than shipped
//     pre-split, so the board's width can never disagree with the word it is
//     asking for. Marking code points instead would call `கா` two letters and
//     tell a player their `க` was "somewhere else" when it is right where they
//     put it.
//   - MARKING IS TWO-PASS, SO DUPLICATES ARE HONEST. Exact positions are taken
//     first and only what is LEFT can be marked present, so an answer holding
//     one `க` never lights up two of them. See `markGuess`.
//   - THE KEYBOARD IS A COMPOSER, NOT AN ALPHABET. Tamil has 247 ezhuthu; no
//     phone shows 247 keys. A consonant key commits its bare form and the form
//     row re-spells that cell into any of its thirteen shapes, which is the
//     letter chart every Tamil reader already knows (`VOWEL_FORMS`).
//   - EVERY COMPLETE ROW IS ACCEPTED. There is no accept list and no word
//     check. A gate could only ever REJECT, and the best list this repo can
//     build - the published headword class - withholds the 1,395,218 classified
//     inflected surfaces a Tamil speaker actually types. Rejecting is also a
//     FAVOUR, since it hands the row back, so accepting everything is the
//     strictly harsher setting and the only one that can never tell a player
//     their real word is not a word.

import { segment } from "../../tamil/ezhuthu";
import type { WordlePuzzle } from "../../contracts/wordle-puzzle";

/**
 * The runtime payload: the `wordle-puzzle` contract minus its schema-stamp
 * fields. `version`/`changelog` describe how the SCHEMA FILE evolves; a
 * `puzzle-file` item's `payload` carries neither.
 */
export type WordlePayload = Omit<WordlePuzzle, "version" | "changelog">;

/** One honest hint from the payload: its kind, its text, and its score cost. */
export type WordleHint = NonNullable<WordlePayload["hints"]>[number];

/** What a submitted ezhuthu turned out to be worth, in this position. */
export type Mark = "correct" | "present" | "absent";

/** The pulli (virama): it turns a consonant into a mei, its own ezhuthu. */
export const PULLI = "\u0BCD";

/** The aytham - one ezhuthu of its own, in neither the uyir nor the mei set. */
export const AYTHAM = "\u0B83";

/**
 * The twelve uyir, listed rather than ranged: U+0B85..U+0B94 holds four
 * unassigned code points and a range would put them on the keyboard.
 */
export const UYIR: readonly string[] = [
  "\u0B85", // a
  "\u0B86", // aa
  "\u0B87", // i
  "\u0B88", // ii
  "\u0B89", // u
  "\u0B8A", // uu
  "\u0B8E", // e
  "\u0B8F", // ee
  "\u0B90", // ai
  "\u0B92", // o
  "\u0B93", // oo
  "\u0B94", // au
];

/** The eleven vowel signs; with the sign-less form they give the twelve uyirmei. */
export const MATRA: readonly string[] = [
  "\u0BBE", // aa
  "\u0BBF", // i
  "\u0BC0", // ii
  "\u0BC1", // u
  "\u0BC2", // uu
  "\u0BC6", // e
  "\u0BC7", // ee
  "\u0BC8", // ai
  "\u0BCA", // o
  "\u0BCB", // oo
  "\u0BCC", // au
];

/**
 * The eighteen native consonants, in the traditional order. Grantha (ja, sha,
 * ssa, sa, ha) is deliberately absent: it is not among the 247, and the served
 * set's word-class gate never deals a word that needs it.
 */
export const MEI_BASES: readonly string[] = [
  "\u0B95", // k
  "\u0B99", // ng
  "\u0B9A", // ch
  "\u0B9E", // nj
  "\u0B9F", // d
  "\u0BA3", // N
  "\u0BA4", // th
  "\u0BA8", // nh
  "\u0BAA", // p
  "\u0BAE", // m
  "\u0BAF", // y
  "\u0BB0", // r
  "\u0BB2", // l
  "\u0BB5", // v
  "\u0BB4", // zh
  "\u0BB3", // L
  "\u0BB1", // tr
  "\u0BA9", // n
];

/**
 * The thirteen shapes one consonant takes, in the order of the Tamil letter
 * chart: the mei column first, then the twelve uyirmei. `""` is the sign-less
 * form that carries the inherent /a/, and it is a real key rather than a gap -
 * it is how a player takes `கா` back to `க` without deleting the cell.
 */
export const VOWEL_FORMS: readonly string[] = [PULLI, "", ...MATRA];

/** Compose one ezhuthu from a base character and one of `VOWEL_FORMS`. */
export function compose(base: string, form: string): string {
  return `${base}${form}`;
}

/**
 * The 247: twelve uyir, eighteen mei, eighteen by twelve uyirmei, the aytham.
 * Built the same way the Python twin builds it, from the same three lists, so
 * the contract's "is this answer typeable" check and this keyboard agree by
 * construction rather than by a copied table.
 */
export const EZHUTHU_INVENTORY: readonly string[] = [
  ...UYIR,
  ...MEI_BASES.map((base) => compose(base, PULLI)),
  ...MEI_BASES.flatMap((base) => ["", ...MATRA].map((form) => compose(base, form))),
  AYTHAM,
];

/**
 * The keys that COMMIT an ezhuthu on their own: the twelve uyir, the aytham,
 * and each consonant in its bare form. Thirty-one keys, which is a phone
 * keyboard; the other 216 ezhuthu are reached by re-spelling with `VOWEL_FORMS`.
 */
export const BASE_KEYS: readonly string[] = [...UYIR, AYTHAM, ...MEI_BASES];

const MODIFIABLE = new Set(MEI_BASES);

/** The base character of an ezhuthu that a vowel form may re-spell, else null. */
export function baseOf(ezhuthu: string): string | null {
  const base = ezhuthu.slice(0, 1);
  return MODIFIABLE.has(base) ? base : null;
}

/** The resumable state the runner persists. */
export interface WordleState {
  /** Submitted rows, oldest first; each is a full row of ezhuthu. */
  guesses: string[][];
  /** The row being composed, left to right. */
  draft: string[];
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
 * Points per ezhuthu when the config slice does not set a base score - the
 * anagram's rate, unchanged. The same word is worth the same on both boards
 * because the score is a property of the WORD; what differs between the two
 * mechanics is how hard it is to reach, and that is absorbed by the attempt
 * budget rather than by the price. How FEW rows a win took is the wordle's own
 * brag and it is already derivable from `puzzle.attempt.submitted`
 * (difficulty-and-scoring.md), so paying for it here would count it twice.
 */
export const DEFAULT_POINTS_PER_EZHUTHU = 10;

/** A fresh, untouched state. */
export function initialState(): WordleState {
  return {
    guesses: [],
    draft: [],
    revealedHintCount: 0,
    finished: false,
    score: 0,
    solved: false,
  };
}

function stringRow(raw: unknown): string[] | null {
  if (!Array.isArray(raw)) return null;
  return raw.every((unit) => typeof unit === "string") ? (raw as string[]) : null;
}

/** Normalize an untrusted (persisted) snapshot back into a valid state. */
export function normalizeState(raw: unknown): WordleState {
  const base = initialState();
  if (typeof raw !== "object" || raw === null) return base;
  const s = raw as Partial<WordleState>;
  const guesses = Array.isArray(s.guesses)
    ? s.guesses.map(stringRow).filter((row): row is string[] => row !== null)
    : base.guesses;
  return {
    guesses,
    draft: stringRow(s.draft) ?? base.draft,
    revealedHintCount:
      typeof s.revealedHintCount === "number" ? s.revealedHintCount : base.revealedHintCount,
    finished: typeof s.finished === "boolean" ? s.finished : base.finished,
    score: typeof s.score === "number" ? s.score : base.score,
    solved: typeof s.solved === "boolean" ? s.solved : base.solved,
  };
}

/** The answer as ezhuthu - the only representation the mechanic compares. */
export function answerEzhuthu(payload: WordlePayload): string[] {
  return segment(payload.word);
}

/** How many cells a row has. Derived, never shipped: a stored width could lie. */
export function boardWidth(payload: WordlePayload): number {
  return answerEzhuthu(payload).length;
}

const RANK: Record<Mark, number> = { absent: 0, present: 1, correct: 2 };

/**
 * Mark one guess against the answer, per position - the Oracle of this Game.
 *
 * Two passes, and the order is the whole point. The first takes every EXACT
 * position and puts the answer's other ezhuthu into a pool; the second can only
 * spend what is in that pool. That is what makes duplicates honest: if the
 * answer holds one `க` and the guess holds two, the pool has at most one to
 * give, so exactly one of them lights up and the other reads absent. A
 * single-pass "is it anywhere in the answer" test would light up both and tell
 * the player the word has two.
 *
 * A length mismatch throws rather than marking what it can. The board only ever
 * submits a full row, so a short guess reaching here is a bug in the caller,
 * and silently marking a prefix would report a position that does not exist.
 */
export function markGuess(guess: readonly string[], answer: readonly string[]): Mark[] {
  if (guess.length !== answer.length) {
    throw new Error(
      `markGuess: ${guess.length} ezhuthu against a ${answer.length}-ezhuthu answer`,
    );
  }
  const marks: Mark[] = guess.map(() => "absent");
  const unmatched = new Map<string, number>();
  for (let i = 0; i < answer.length; i += 1) {
    const wanted = answer[i] as string;
    if (guess[i] === wanted) marks[i] = "correct";
    else unmatched.set(wanted, (unmatched.get(wanted) ?? 0) + 1);
  }
  for (let i = 0; i < guess.length; i += 1) {
    if (marks[i] === "correct") continue;
    const played = guess[i] as string;
    const left = unmatched.get(played) ?? 0;
    if (left > 0) {
      unmatched.set(played, left - 1);
      marks[i] = "present";
    }
  }
  return marks;
}

/** Every submitted row with its marks, oldest first - what the board draws. */
export function markedRows(
  payload: WordlePayload,
  state: WordleState,
): { guess: string[]; marks: Mark[] }[] {
  const answer = answerEzhuthu(payload);
  return state.guesses.map((guess) => ({ guess, marks: markGuess(guess, answer) }));
}

/**
 * The best thing learned about each ezhuthu so far, for the keyboard.
 *
 * Best rather than latest: once an ezhuthu has been seen correct, a later row
 * that plays it in the wrong place must not demote the key back to present.
 * The map is keyed by the WHOLE ezhuthu and never by its base consonant,
 * because there is no honest aggregate - `கா` being absent says nothing at all
 * about `கு`, and greying the `க` key on that evidence would hide a letter the
 * answer might still hold.
 */
export function keyStates(payload: WordlePayload, state: WordleState): Map<string, Mark> {
  const answer = answerEzhuthu(payload);
  const best = new Map<string, Mark>();
  for (const guess of state.guesses) {
    const marks = markGuess(guess, answer);
    guess.forEach((unit, index) => {
      const mark = marks[index] as Mark;
      const prior = best.get(unit);
      if (prior === undefined || RANK[mark] > RANK[prior]) best.set(unit, mark);
    });
  }
  return best;
}

/** The base whose thirteen forms the form row is currently showing, or null. */
export function liveBase(state: WordleState): string | null {
  const last = state.draft[state.draft.length - 1];
  return last === undefined ? null : baseOf(last);
}

/** Whether the composed row is full and may be submitted. */
export function isDraftFull(payload: WordlePayload, state: WordleState): boolean {
  return state.draft.length === boardWidth(payload);
}

/** Attempts left before the puzzle ends (never negative). */
export function attemptsRemaining(payload: WordlePayload, state: WordleState): number {
  return Math.max(0, payload.attempts - state.guesses.length);
}

/** Commit one ezhuthu into the next empty cell. No-op when finished or full. */
export function pushEzhuthu(
  payload: WordlePayload,
  state: WordleState,
  ezhuthu: string,
): WordleState {
  if (state.finished || isDraftFull(payload, state)) return state;
  return { ...state, draft: [...state.draft, ezhuthu] };
}

/**
 * Re-spell the last composed cell into another of its thirteen forms.
 *
 * This is the second half of the composer and it deliberately REPLACES rather
 * than appends: a vowel sign is not an ezhuthu of its own, it is how the one
 * already on the board is written. A cell holding a uyir or the aytham has no
 * base to re-spell, so the row is a no-op there rather than silently doing
 * something else.
 */
export function applyVowelForm(state: WordleState, form: string): WordleState {
  if (state.finished || state.draft.length === 0) return state;
  const index = state.draft.length - 1;
  const base = baseOf(state.draft[index] as string);
  if (base === null) return state;
  const draft = [...state.draft];
  draft[index] = compose(base, form);
  return { ...state, draft };
}

/** Take the last composed ezhuthu off the row. */
export function backspace(state: WordleState): WordleState {
  if (state.finished || state.draft.length === 0) return state;
  return { ...state, draft: state.draft.slice(0, -1) };
}

/** Empty the composed row (Escape). */
export function clearDraft(state: WordleState): WordleState {
  if (state.finished || state.draft.length === 0) return state;
  return { ...state, draft: [] };
}

/** The hints the player has revealed so far, in payload order. */
export function revealedHints(payload: WordlePayload, state: WordleState): WordleHint[] {
  return (payload.hints ?? []).slice(0, state.revealedHintCount);
}

/** The next hint to reveal, or `null` when they are all spent. */
export function nextHint(payload: WordlePayload, state: WordleState): WordleHint | null {
  return (payload.hints ?? [])[state.revealedHintCount] ?? null;
}

/** Reveal the next hint; the cost is applied when the puzzle is scored. */
export function revealNextHint(payload: WordlePayload, state: WordleState): WordleState {
  if (state.finished || nextHint(payload, state) === null) return state;
  return { ...state, revealedHintCount: state.revealedHintCount + 1 };
}

/**
 * The score before hints: `config.baseScore` when the Mode sets one, else the
 * shared per-ezhuthu rate (Holy Law #6 - a fresh clone runs on the defaults,
 * and the knob arrives through the config slice, never an import of the app
 * config).
 */
export function baseScore(
  payload: WordlePayload,
  config: Readonly<Record<string, unknown>> = {},
): number {
  const configured = config.baseScore;
  if (typeof configured === "number" && Number.isFinite(configured) && configured > 0) {
    return Math.round(configured);
  }
  return boardWidth(payload) * DEFAULT_POINTS_PER_EZHUTHU;
}

/**
 * The awarded score: the base minus the cost of every hint the player revealed
 * (docs/concepts/difficulty-and-scoring.md - a hint costs the brag, not money).
 * Clamped at 0 so a heavily-hinted win never goes negative.
 */
export function scoreFor(
  payload: WordlePayload,
  state: WordleState,
  config: Readonly<Record<string, unknown>> = {},
): number {
  const spent = revealedHints(payload, state).reduce((sum, hint) => sum + hint.cost, 0);
  return Math.max(0, baseScore(payload, config) - spent);
}

/** The outcome of submitting one composed row. */
export interface AttemptOutcome {
  state: WordleState;
  /** The marks the submitted row earned, per position. */
  marks: Mark[];
  correct: boolean;
  /** True when this row ended the puzzle without a win (attempts spent). */
  exhausted: boolean;
  attemptIndex: number;
  /** The submitted row as a word, for the attempt event. */
  attempt: string;
}

/**
 * Submit the composed row. It is accepted whatever it spells - see the header -
 * so the only question is what it earns. A win finishes and scores; a miss
 * keeps the row on the board with its marks and empties the draft for the next
 * one; spending the last attempt ends the puzzle honestly (no purchase, no
 * timer - Palm).
 *
 * Submitting a SHORT row is refused rather than marked, and refused without
 * spending an attempt: the row is not a guess yet, and charging for it would
 * punish a player mid-thought.
 */
export function submitAttempt(
  payload: WordlePayload,
  state: WordleState,
  config: Readonly<Record<string, unknown>> = {},
): AttemptOutcome | null {
  if (state.finished || !isDraftFull(payload, state)) return null;
  const guess = [...state.draft];
  const marks = markGuess(guess, answerEzhuthu(payload));
  const correct = marks.every((mark) => mark === "correct");
  const guesses = [...state.guesses, guess];
  const exhausted = !correct && guesses.length >= payload.attempts;
  const next: WordleState = {
    ...state,
    guesses,
    draft: [],
    finished: correct || exhausted,
    solved: correct,
  };
  return {
    state: { ...next, score: correct ? scoreFor(payload, next, config) : 0 },
    marks,
    correct,
    exhausted,
    attemptIndex: guesses.length,
    attempt: guess.join(""),
  };
}

/** What a key press means on a keyboard key (the pure keyboard contract). */
export type KeyAction = "press" | "undo" | "clear" | null;

/** Map a `KeyboardEvent.key` to a mechanic action; unknown keys do nothing. */
export function keyToAction(key: string): KeyAction {
  if (key === "Enter" || key === " " || key === "Spacebar") return "press";
  if (key === "Backspace" || key === "Delete") return "undo";
  if (key === "Escape") return "clear";
  return null;
}

/** The player-facing strings; a Mode may override any of them via the config slice. */
export interface WordleLabels {
  prompt: string;
  board: string;
  attemptsLeft: string;
  correct: string;
  outOfAttempts: string;
  incomplete: string;
  hint: string;
  hintsSpent: string;
  vowels: string;
  consonants: string;
  forms: string;
  submit: string;
  erase: string;
  markCorrect: string;
  markPresent: string;
  markAbsent: string;
  empty: string;
  pending: string;
}

/** Tamil first, with the English the median player also reads (Player #7). */
export const DEFAULT_LABELS: WordleLabels = {
  prompt: "\u0B9A\u0BCA\u0BB2\u0BCD\u0BB2\u0BC8 \u0BAF\u0BC2\u0B95\u0BBF\u0BAF\u0BC1\u0B99\u0BCD\u0B95\u0BB3\u0BCD",
  board: "\u0BAF\u0BC2\u0B95\u0BC1\u0B95\u0BB3\u0BCD",
  attemptsLeft: "\u0BAE\u0BC1\u0BAF\u0BB1\u0BCD\u0B9A\u0BBF \u0BAE\u0BC0\u0BA4\u0BAE\u0BCD",
  correct: "\u0B9A\u0BB0\u0BBF!",
  outOfAttempts: "\u0BAE\u0BC1\u0BAF\u0BB1\u0BCD\u0B9A\u0B95\u0BB3\u0BCD \u0BAE\u0BC1\u0B9F\u0BBF\u0BA8\u0BCD\u0BA4\u0BA9",
  incomplete: "\u0B8E\u0BB2\u0BCD\u0BB2\u0BBE \u0B8E\u0BB4\u0BC1\u0BA4\u0BCD\u0BA4\u0BC1\u0B95\u0BB3\u0BC8\u0BAF\u0BC1\u0BAE\u0BCD \u0BA8\u0BBF\u0BB0\u0BAA\u0BCD\u0BAA\u0BC1\u0B99\u0BCD\u0B95\u0BB3\u0BCD",
  hint: "\u0B95\u0BC1\u0BB1\u0BBF\u0BAA\u0BCD\u0BAA\u0BC1",
  hintsSpent: "\u0B95\u0BC1\u0BB1\u0BBF\u0BAA\u0BCD\u0BAA\u0BC1\u0B95\u0BB3\u0BCD \u0BAE\u0BC1\u0B9F\u0BBF\u0BA8\u0BCD\u0BA4\u0BA9",
  vowels: "\u0B89\u0BAF\u0BBF\u0BB0\u0BCD",
  consonants: "\u0BAE\u0BC6\u0BAF\u0BCD",
  forms: "\u0B89\u0BAF\u0BBF\u0BB0\u0BCD\u0BAE\u0BC6\u0BAF\u0BCD",
  submit: "Submit the row",
  erase: "Erase the last letter",
  markCorrect: "Right letter, right place",
  markPresent: "Right letter, elsewhere",
  markAbsent: "Not in the word",
  empty: "Empty cell",
  pending: "Letter",
};

/**
 * Resolve the labels from the injected config slice. The Game never imports the
 * app config or the copy map - a Mode hands down whatever it wants overridden
 * (Fowler: payloads, not calls), and the defaults keep a fresh clone playable.
 */
export function resolveLabels(
  config: Readonly<Record<string, unknown>> = {},
): WordleLabels {
  const overrides = config.labels;
  if (typeof overrides !== "object" || overrides === null) return DEFAULT_LABELS;
  const partial = overrides as Partial<Record<keyof WordleLabels, unknown>>;
  const merged: WordleLabels = { ...DEFAULT_LABELS };
  for (const key of Object.keys(DEFAULT_LABELS) as (keyof WordleLabels)[]) {
    const value = partial[key];
    if (typeof value === "string" && value.length > 0) merged[key] = value;
  }
  return merged;
}
