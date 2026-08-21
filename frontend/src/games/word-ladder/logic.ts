// The word-ladder mechanic's pure core - no DOM, no storage, no singletons
// (docs/concepts/games.md `word-ladder`). Everything here is a function of its
// arguments, so the whole mechanic unit-tests in a node environment while the
// Svelte view stays a thin projection of this state.
//
// Five invariants the rest of the Game leans on:
//
//   - ONE VERB: ADD ONE EZHUTHU. The rung below is already on screen; the whole
//     move is choosing which letter from the bank joins it. Rearranging is FREE
//     - the contract states the rung rule over ezhuthu MULTISETS, so a step is
//     judged by the tiles it produces and never by the order they are in. That
//     is what keeps this a different Game from the scramble rather than the
//     scramble played three times.
//   - A PICK IS JUDGED BY ITS TILES. `climbs()` compares sorted ezhuthu
//     multisets, exactly as the generator's graph does, so the browser answers
//     a pick by counting letters rather than by searching a wordlist it does
//     not have (Holy Law #1 - nothing is looked up at runtime).
//   - THE BANK IS THE INPUT METHOD, AND IT IS SPENT. There is no Tamil
//     keyboard, so `choices` is how an addition is entered at all. It arrives
//     already ordered by the bake, one bank for the WHOLE climb, and a letter
//     that carries a rung leaves it - which letter to spend now is part of the
//     puzzle, so a letter that is wrong at this rung may be the right one two
//     rungs up.
//   - A REAL WORD IS ANSWERED, NOT REJECTED. `alsoValid` lists the other served
//     words the bank reaches from the rung below, so a climber who lands on a
//     real Tamil word is told it is one. A word sharing the ANSWER's tiles is
//     not one of these: it is reached by the correct pick, so it is a climb.
//   - A WRONG PICK COSTS TIME, NOT THE CLIMB. There is no attempt budget: the
//     ladder is the one board whose progress is a chain, and ending it mid-way
//     would confiscate the rungs already earned. Help is a per-rung REVEAL,
//     priced in exactly the rung it hands over.

import { segment } from "../../tamil/ezhuthu";
import type { WordLadderPuzzle } from "../../contracts/word-ladder-puzzle";

/**
 * The runtime payload: the `word-ladder-puzzle` contract minus its schema-stamp
 * fields. `version`/`changelog` describe how the SCHEMA FILE evolves; a
 * `puzzle-file` item's `payload` carries neither.
 */
export type WordLadderPayload = Omit<WordLadderPuzzle, "version" | "changelog">;

/** One step of the climb, as it travels in the payload. */
export type Rung = WordLadderPayload["rungs"][number];

/** One tile in the bank: an ezhuthu plus a stable id (the bank may repeat one). */
export interface Choice {
  readonly id: string;
  readonly ezhuthu: string;
}

/** Points per rung climbed - a rung is one bank pick, the same rate a blank pays. */
export const DEFAULT_POINTS_PER_RUNG = 20;

/** The resumable state the runner persists; ids make a restore unambiguous. */
export interface WordLadderState {
  /**
   * The bank tile spent on each resolved step, in climb order: entry `i`
   * carries `rungs[i + 1]`. Its length IS how high the player has climbed.
   */
  spentChoiceIds: string[];
  /** Steps handed over rather than climbed (indices into `spentChoiceIds`). */
  revealedSteps: number[];
  /** Picks that did not climb. They cost nothing but are worth reporting. */
  misses: number;
  /** Terminal flag: every rung is resolved, climbed or revealed. */
  finished: boolean;
  /** Awarded points. */
  score: number;
  /** Whether every rung was climbed rather than revealed. */
  solved: boolean;
}

/** A fresh, untouched state - standing on the given first rung. */
export function initialState(): WordLadderState {
  return {
    spentChoiceIds: [],
    revealedSteps: [],
    misses: 0,
    finished: false,
    score: 0,
    solved: false,
  };
}

/** The bank, in the order the bake shuffled it. Ids are stable across renders. */
export function buildChoices(payload: WordLadderPayload): Choice[] {
  return payload.choices.map((ezhuthu, index) => ({ id: `c${index}`, ezhuthu }));
}

/** How many steps the climb has: one fewer than its rungs, since the first is given. */
export function stepCount(payload: WordLadderPayload): number {
  return payload.rungs.length - 1;
}

/** How high the player has climbed: the index of the topmost resolved rung. */
export function height(state: WordLadderState): number {
  return state.spentChoiceIds.length;
}

/** The rung the player is standing on - the last one resolved, or the given one. */
export function currentRung(
  payload: WordLadderPayload,
  state: WordLadderState,
): Rung {
  // The payload's tuple type guarantees three rungs; the fallback keeps the
  // index access total for a restored state that over-ran the ladder.
  return payload.rungs[Math.min(height(state), stepCount(payload))] ?? payload.rungs[0];
}

/** The rung the player is climbing towards, or `null` once the ladder is done. */
export function targetRung(
  payload: WordLadderPayload,
  state: WordLadderState,
): Rung | null {
  return payload.rungs[height(state) + 1] ?? null;
}

/** The order-free key two words share exactly when the same tiles spell both. */
export function tileKey(units: readonly string[]): string {
  return [...units].sort().join("\u0000");
}

/** Whether adding `unit` to `below` produces exactly the tiles of `above`. */
export function climbs(below: string, unit: string, above: string): boolean {
  return tileKey([...segment(below), unit]) === tileKey(segment(above));
}

/**
 * The OTHER served word a pick spells, or `null`.
 *
 * Read off the rung's own `alsoValid` - a Game may not consult a wordlist - and
 * matched on tiles rather than on the added letter, because that is the same
 * question `climbs` asks and the two must agree about what a pick produced.
 */
export function alternativeFor(
  below: string,
  unit: string,
  above: Rung,
): string | null {
  const produced = tileKey([...segment(below), unit]);
  // Widened deliberately: the generated type is a minItems tuple, and a tuple
  // union collapses an array method's parameter to `never`.
  const alternatives: readonly string[] = above.alsoValid ?? [];
  return alternatives.find((word) => tileKey(segment(word)) === produced) ?? null;
}

/** Choices still in the bank (a resolved step takes one out). */
export function remainingChoices(
  choices: readonly Choice[],
  state: WordLadderState,
): Choice[] {
  return choices.filter((choice) => !state.spentChoiceIds.includes(choice.id));
}

/** The ezhuthu a choice id carries, or "" when the id is unknown. */
function ezhuthuOf(choices: readonly Choice[], id: string | undefined): string {
  if (id === undefined) return "";
  return choices.find((choice) => choice.id === id)?.ezhuthu ?? "";
}

/** Whether this step was handed over rather than climbed. */
export function wasRevealed(state: WordLadderState, step: number): boolean {
  return state.revealedSteps.includes(step);
}

/** How a rung reads on the board right now. */
export type RungStatus = "given" | "climbed" | "revealed" | "target" | "locked";

/** One rendered rung of the ladder - the view's whole model of a row. */
export interface LadderRow {
  /** Index into `payload.rungs`; 0 is the ledge the player starts on. */
  readonly index: number;
  /** The word, or `null` while the rung is still above the player. */
  readonly word: string | null;
  /** The bake-time gloss, shown free once the rung is resolved. */
  readonly meaning: string | null;
  /** The ezhuthu this rung ADDED - the badge - or `null` on the given rung. */
  readonly added: string | null;
  readonly status: RungStatus;
}

/**
 * The whole ladder as rows, bottom rung first.
 *
 * A rung above the player carries no word: the climb is the guess, so printing
 * the answer one rung early would hand over the puzzle. The badge is read off
 * the SPENT TILE rather than off the two words, so a revealed rung shows the
 * letter it cost exactly like a climbed one.
 */
export function ladderRows(
  payload: WordLadderPayload,
  choices: readonly Choice[],
  state: WordLadderState,
): LadderRow[] {
  const climbed = height(state);
  return payload.rungs.map((rung, index) => {
    const resolved = index <= climbed;
    const status: RungStatus =
      index === 0
        ? "given"
        : !resolved
          ? index === climbed + 1
            ? "target"
            : "locked"
          : wasRevealed(state, index - 1)
            ? "revealed"
            : "climbed";
    return {
      index,
      word: resolved ? rung.word : null,
      meaning: resolved ? (rung.meaning ?? null) : null,
      added: index === 0 ? null : ezhuthuOf(choices, state.spentChoiceIds[index - 1]) || null,
      status,
    };
  });
}

/** What one climbed rung is worth. */
export function rungValue(): number {
  return DEFAULT_POINTS_PER_RUNG;
}

/** The whole climb's value, if every rung is earned. */
export function fullScore(
  payload: WordLadderPayload,
  config: Readonly<Record<string, unknown>> = {},
): number {
  const configured = config.baseScore;
  if (typeof configured === "number" && Number.isFinite(configured) && configured > 0) {
    return Math.round(configured);
  }
  return stepCount(payload) * rungValue();
}

/**
 * The score so far: the share of the climb's value the player CLIMBED.
 *
 * A revealed rung earns nothing, which is the whole price of revealing - and it
 * is proportional rather than all-or-nothing, so a climber stuck on one rung
 * keeps everything they earned below it. Misses cost nothing: a wrong pick on a
 * chain costs time, and charging for it twice would be charging for looking.
 */
export function scoreFor(
  payload: WordLadderPayload,
  state: WordLadderState,
  config: Readonly<Record<string, unknown>> = {},
): number {
  const steps = stepCount(payload);
  if (steps === 0) return 0;
  const earned = height(state) - state.revealedSteps.length;
  return Math.round((fullScore(payload, config) * Math.max(0, earned)) / steps);
}

/** Recompute the derived flags after any change to how high the climb is. */
function settle(
  payload: WordLadderPayload,
  state: WordLadderState,
  config: Readonly<Record<string, unknown>> = {},
): WordLadderState {
  const done = height(state) >= stepCount(payload);
  return {
    ...state,
    finished: done,
    solved: done && state.revealedSteps.length === 0,
    score: scoreFor(payload, state, config),
  };
}

/**
 * Normalize an untrusted (persisted) snapshot back into a valid state.
 *
 * A restored step is kept only while it still describes THIS climb: its tile
 * must be in this bank, unspent so far, and it must really carry the rung it
 * claims (or have been bought). A save from another day therefore restores as
 * far as it honestly can rather than marking rungs of a ladder it never saw.
 */
export function normalizeState(
  payload: WordLadderPayload,
  choices: readonly Choice[],
  raw: unknown,
  config: Readonly<Record<string, unknown>> = {},
): WordLadderState {
  const base = initialState();
  if (typeof raw !== "object" || raw === null) return settle(payload, base, config);
  const snapshot = raw as Partial<WordLadderState>;
  const revealed = new Set(
    Array.isArray(snapshot.revealedSteps)
      ? snapshot.revealedSteps.filter((step): step is number => typeof step === "number")
      : [],
  );
  const ids = Array.isArray(snapshot.spentChoiceIds)
    ? snapshot.spentChoiceIds.filter((id): id is string => typeof id === "string")
    : [];

  const spent: string[] = [];
  const revealedSteps: number[] = [];
  for (const id of ids.slice(0, stepCount(payload))) {
    const step = spent.length;
    const below = payload.rungs[step]?.word;
    const above = payload.rungs[step + 1]?.word;
    const unit = ezhuthuOf(choices, id);
    if (below === undefined || above === undefined) break;
    if (unit === "" || spent.includes(id)) break;
    const bought = revealed.has(step);
    if (!bought && !climbs(below, unit, above)) break;
    spent.push(id);
    if (bought) revealedSteps.push(step);
  }

  const misses = typeof snapshot.misses === "number" ? Math.max(0, snapshot.misses) : 0;
  return settle(
    payload,
    { ...base, spentChoiceIds: spent, revealedSteps, misses },
    config,
  );
}

/** What one pick did: climbed the rung, spelled another real word, or nothing. */
export type PickVerdict = "climb" | "also-valid" | "miss";

/** The outcome of picking one ezhuthu out of the bank. */
export interface PickOutcome {
  state: WordLadderState;
  verdict: PickVerdict;
  /** The step this pick answered (0-based; `rungs[step + 1]` was the target). */
  step: number;
  /** How many picks the player has now made at this step (1 for the first). */
  attemptIndex: number;
  /** The ezhuthu the player added. */
  attempt: string;
  /** The word the pick spells: the rung, the alternative, or `null` for neither. */
  spells: string | null;
}

/**
 * Pick one bank tile.
 *
 * A climb spends the tile and moves up; anything else leaves the board exactly
 * as it was and costs only the miss counter, because a ladder has no attempt
 * budget to spend.
 */
export function pickChoice(
  payload: WordLadderPayload,
  choices: readonly Choice[],
  state: WordLadderState,
  choiceId: string,
  attemptIndex: number,
  config: Readonly<Record<string, unknown>> = {},
): PickOutcome | null {
  if (state.finished || state.spentChoiceIds.includes(choiceId)) return null;
  const unit = ezhuthuOf(choices, choiceId);
  const step = height(state);
  const below = payload.rungs[step];
  const above = payload.rungs[step + 1];
  if (unit === "" || below === undefined || above === undefined) return null;

  if (climbs(below.word, unit, above.word)) {
    return {
      state: settle(
        payload,
        { ...state, spentChoiceIds: [...state.spentChoiceIds, choiceId] },
        config,
      ),
      verdict: "climb",
      step,
      attemptIndex,
      attempt: unit,
      spells: above.word,
    };
  }

  const other = alternativeFor(below.word, unit, above);
  return {
    state: { ...state, misses: state.misses + 1 },
    verdict: other === null ? "miss" : "also-valid",
    step,
    attemptIndex,
    attempt: unit,
    spells: other,
  };
}

/** The rung a reveal would hand over next, or `null` when the climb is done. */
export function nextReveal(
  payload: WordLadderPayload,
  state: WordLadderState,
): Rung | null {
  return state.finished ? null : targetRung(payload, state);
}

/**
 * Hand over the next rung.
 *
 * This is the whole of this Game's help, and its price is that rung: the player
 * keeps every point they climbed and forfeits this one. It is not a baked rung
 * of the shared hint ladder because every fact such a rung could sell is about
 * the NEXT word, so it would have to be bought at the only moment it is worth
 * anything and would then hand over most of a three-letter word anyway.
 */
export function revealNext(
  payload: WordLadderPayload,
  choices: readonly Choice[],
  state: WordLadderState,
  config: Readonly<Record<string, unknown>> = {},
): { state: WordLadderState; word: string | null; cost: number } {
  const step = height(state);
  const below = payload.rungs[step];
  const above = payload.rungs[step + 1];
  if (state.finished || below === undefined || above === undefined) {
    return { state, word: null, cost: 0 };
  }
  const spend = remainingChoices(choices, state).find((choice) =>
    climbs(below.word, choice.ezhuthu, above.word),
  );
  if (spend === undefined) return { state, word: null, cost: 0 };
  return {
    state: settle(
      payload,
      {
        ...state,
        spentChoiceIds: [...state.spentChoiceIds, spend.id],
        revealedSteps: [...state.revealedSteps, step],
      },
      config,
    ),
    word: above.word,
    cost: rungValue(),
  };
}

/** What a key press means on the bank (the pure keyboard contract). */
export type KeyAction = "pick" | null;

/** Map a `KeyboardEvent.key` to a mechanic action; unknown keys do nothing. */
export function keyToAction(key: string): KeyAction {
  if (key === "Enter" || key === " " || key === "Spacebar") return "pick";
  return null;
}

/**
 * ONE emitted telemetry event, as the stats reader needs to see it.
 *
 * Structural on purpose: the runtime envelope lives behind the telemetry
 * module, which a Game may not import (`boundary.test.ts`). Reading only `name`
 * and `data` also keeps the derivation honest - it can use nothing the catalog
 * does not already carry.
 */
export interface LadderEvent {
  readonly name: string;
  readonly data?: Readonly<Record<string, unknown>>;
}

/**
 * The completion row: TIME, INSTINCT, RETRIES, STREAK - plus the denominators
 * that make the first three readable.
 *
 * Every field is DERIVED FROM THE EVENT STREAM and nothing else. That is the
 * whole design: a stat the Game had to persist would be a second copy of a fact
 * the telemetry already states, and the save contract would grow a field per
 * brag (Fowler). `streak` is the exception that proves it - it is not counted
 * here at all, it is READ off the run the StorageService already maintains and
 * relayed through the stream, so this Game never mints a parallel streak.
 */
export interface LadderStats {
  /** Elapsed play time of the climb, in ms. */
  timeMs: number;
  /** Rungs climbed on the FIRST pick at that rung. */
  instinct: number;
  /** Picks that did not climb. */
  retries: number;
  /** The consecutive-day run, as the save already counts it. */
  streak: number;
  /** Rungs the ladder asked for (the denominator INSTINCT is read against). */
  steps: number;
  /** Rungs climbed rather than handed over. */
  climbed: number;
  /** Rungs handed over by a reveal. */
  revealed: number;
  /** Points awarded, as the completion event reported them. */
  score: number;
  /** Whether the climb reached the top. */
  completed: boolean;
}

/** How one rung was resolved, in climb order - the share card's ladder marks. */
export type RungMark = "first" | "retry" | "revealed";

function numberFrom(data: LadderEvent["data"], key: string): number | null {
  const value = data?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

/**
 * Read the four completion stats off the events the Game emitted.
 *
 * One left-to-right pass, because the stream is already in emission order:
 * `puzzle.started` states the shape of the board and the streak the player
 * arrived with, each `puzzle.attempt.submitted` is one bank pick (its
 * `attemptIndex` is 1 exactly when it is the first pick at that rung, which IS
 * instinct), each `puzzle.hint.used` is a rung handed over, and
 * `puzzle.completed` closes the clock. A `streak.updated` anywhere in the
 * stream wins over the arrival value, so a card rendered after the day ticked
 * shows the run the tick produced.
 */
export function deriveStats(events: readonly LadderEvent[]): LadderStats {
  const stats: LadderStats = {
    timeMs: 0,
    instinct: 0,
    retries: 0,
    streak: 0,
    steps: 0,
    climbed: 0,
    revealed: 0,
    score: 0,
    completed: false,
  };
  for (const event of events) {
    const elapsed = numberFrom(event.data, "elapsedMs");
    if (elapsed !== null) stats.timeMs = Math.max(stats.timeMs, elapsed);
    switch (event.name) {
      case "puzzle.started":
        stats.steps = numberFrom(event.data, "steps") ?? stats.steps;
        stats.streak = numberFrom(event.data, "streak") ?? stats.streak;
        break;
      case "puzzle.attempt.submitted":
        if (event.data?.correct === true) {
          stats.climbed += 1;
          if (numberFrom(event.data, "attemptIndex") === 1) stats.instinct += 1;
        } else {
          stats.retries += 1;
        }
        break;
      case "puzzle.hint.used":
        stats.revealed += 1;
        break;
      case "streak.updated":
        stats.streak = numberFrom(event.data, "after") ?? stats.streak;
        break;
      case "puzzle.completed":
        stats.completed = true;
        stats.score = numberFrom(event.data, "score") ?? stats.score;
        break;
      default:
        break;
    }
  }
  return stats;
}

/**
 * How each rung was resolved, in climb order.
 *
 * Also a single pass, and for the same reason: misses accumulate against the
 * rung the player is standing under, and the climb that clears it reads them.
 */
export function rungMarks(events: readonly LadderEvent[]): RungMark[] {
  const marks: RungMark[] = [];
  let missesHere = 0;
  for (const event of events) {
    if (event.name === "puzzle.hint.used") {
      marks.push("revealed");
      missesHere = 0;
      continue;
    }
    if (event.name !== "puzzle.attempt.submitted") continue;
    if (event.data?.correct === true) {
      marks.push(missesHere === 0 ? "first" : "retry");
      missesHere = 0;
    } else {
      missesHere += 1;
    }
  }
  return marks;
}

/** Elapsed time as the card prints it: `m:ss`, never a bare millisecond count. */
export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const seconds = total % 60;
  return `${Math.floor(total / 60)}:${seconds < 10 ? "0" : ""}${seconds}`;
}

/** The player-facing strings; a Mode may override any of them via the config slice. */
export interface WordLadderLabels {
  prompt: string;
  bank: string;
  ladder: string;
  standing: string;
  target: string;
  climbed: string;
  alsoValid: string;
  miss: string;
  reveal: string;
  revealed: string;
  complete: string;
  choice: string;
  locked: string;
  /** The four completion stats, in the order the card prints them. */
  statTime: string;
  statInstinct: string;
  statRetries: string;
  statStreak: string;
  share: string;
  shared: string;
  continueOn: string;
  card: string;
}

/** Tamil first, with the English the median player also reads (Player #7). */
export const DEFAULT_LABELS: WordLadderLabels = {
  // sol eeni - "word ladder"
  prompt: "\u0B9A\u0BCA\u0BB2\u0BCD \u0B8F\u0BA3\u0BBF",
  // oru ezhuthu serkkavum - "add one letter"
  bank: "\u0B92\u0BB0\u0BC1 \u0B8E\u0BB4\u0BC1\u0BA4\u0BCD\u0BA4\u0BC1 \u0B9A\u0BC7\u0BB0\u0BCD\u0B95\u0BCD\u0B95\u0BB5\u0BC1\u0BAE\u0BCD",
  ladder: "\u0B8F\u0BA3\u0BBF",
  standing: "\u0B87\u0BAA\u0BCD\u0BAA\u0BCB\u0BA4\u0BC8\u0BAF \u0B9A\u0BCA\u0BB2\u0BCD",
  target: "\u0B85\u0B9F\u0BC1\u0BA4\u0BCD\u0BA4 \u0BAA\u0B9F\u0BBF",
  climbed: "\u0B8F\u0BB1\u0BBF\u0BAF\u0BBE\u0B9A\u0BCD\u0B9A\u0BC1!",
  alsoValid:
    "\u0B85\u0BA4\u0BC1\u0BB5\u0BC1\u0BAE\u0BCD \u0B92\u0BB0\u0BC1 \u0B9A\u0BCA\u0BB2\u0BCD - \u0B86\u0BA9\u0BBE\u0BB2\u0BCD \u0B87\u0BA8\u0BCD\u0BA4\u0BAA\u0BCD \u0BAA\u0B9F\u0BBF \u0B85\u0BB2\u0BCD\u0BB2",
  miss: "\u0B87\u0BA8\u0BCD\u0BA4 \u0B8E\u0BB4\u0BC1\u0BA4\u0BCD\u0BA4\u0BC1 \u0B92\u0BB0\u0BC1 \u0B9A\u0BCA\u0BB2\u0BCD\u0BB2\u0BC8 \u0B86\u0B95\u0BCD\u0B95\u0BB5\u0BBF\u0BB2\u0BCD\u0BB2\u0BC8",
  reveal: "\u0B92\u0BB0\u0BC1 \u0BAA\u0B9F\u0BBF\u0BAF\u0BC8\u0B95\u0BCD \u0B95\u0BBE\u0B9F\u0BCD\u0B9F\u0BC1",
  revealed: "\u0B95\u0BBE\u0B9F\u0BCD\u0B9F\u0BAA\u0BCD\u0BAA\u0B9F\u0BCD\u0B9F\u0BA4\u0BC1",
  complete: "\u0B8F\u0BA3\u0BBF\u0BAF\u0BBF\u0BA9\u0BCD \u0B89\u0B9A\u0BCD\u0B9A\u0BBF!",
  choice: "Add this letter",
  locked: "Not climbed yet",
  // neram - "time"
  statTime: "\u0BA8\u0BC7\u0BB0\u0BAE\u0BCD",
  // ullunarvu - "instinct"
  statInstinct: "\u0B89\u0BB3\u0BCD\u0BB3\u0BC1\u0BA3\u0BB0\u0BCD\u0BB5\u0BC1",
  // marumuyarsi - "retries"
  statRetries: "\u0BAE\u0BB1\u0BC1\u0BAE\u0BC1\u0BAF\u0BB1\u0BCD\u0B9A\u0BBF",
  // thodar naatkal - "consecutive days", the wording the summary already uses
  statStreak: "\u0BA4\u0BCA\u0B9F\u0BB0\u0BCD \u0BA8\u0BBE\u0B9F\u0BCD\u0B95\u0BB3\u0BCD",
  // pakir - "share"
  share: "\u0BAA\u0B95\u0BBF\u0BB0\u0BCD",
  // nakaleduthaakiyathu - "copied"
  shared:
    "\u0BA8\u0B95\u0BB2\u0BC6\u0B9F\u0BC1\u0B95\u0BCD\u0B95\u0BAA\u0BCD\u0BAA\u0B9F\u0BCD\u0B9F\u0BA4\u0BC1",
  // thodaravum - "continue"
  continueOn: "\u0BA4\u0BCA\u0B9F\u0BB0\u0BB5\u0BC1\u0BAE\u0BCD",
  card: "Result card",
};

/**
 * Resolve the labels from the injected config slice. The Game never imports the
 * app config or the copy map - a Mode hands down whatever it wants overridden
 * (Fowler: payloads, not calls), and the defaults keep a fresh clone playable.
 */
export function resolveLabels(
  config: Readonly<Record<string, unknown>> = {},
): WordLadderLabels {
  const overrides = config.labels;
  if (typeof overrides !== "object" || overrides === null) return DEFAULT_LABELS;
  const partial = overrides as Partial<Record<keyof WordLadderLabels, unknown>>;
  const merged: WordLadderLabels = { ...DEFAULT_LABELS };
  for (const key of Object.keys(DEFAULT_LABELS) as (keyof WordLadderLabels)[]) {
    const value = partial[key];
    if (typeof value === "string" && value.length > 0) merged[key] = value;
  }
  return merged;
}

/**
 * The streak the player arrived with, read off the injected config slice.
 *
 * The Mode reads it from the save the StorageService already owns and hands it
 * down as a payload, because a Game may not touch storage (`boundary.test.ts`).
 * An absent value is a zero run, never a crash - which is also what a fresh
 * clone and the harness get.
 */
export function resolveStreak(config: Readonly<Record<string, unknown>> = {}): number {
  const value = config.streak;
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? Math.floor(value)
    : 0;
}

/** How one rung prints on the shared card: climbed clean, climbed after misses, bought. */
const MARK_GLYPHS: Readonly<Record<RungMark, string>> = {
  first: "\u25A0",
  retry: "\u25A3",
  revealed: "\u25A1",
};

/**
 * The card as TEXT, built entirely on this device.
 *
 * This is the whole of "share": a string the player copies. There is no
 * endpoint, no server-rendered image and no share id, because a static bundle
 * has nothing to call and a brag that needs a server is a brag that stops
 * working the day the server does (Holy Law #1). The stats it prints are the
 * ones `deriveStats` read off the event stream, so the card can never claim
 * something the telemetry did not record.
 */
export function shareText(
  stats: LadderStats,
  marks: readonly RungMark[],
  labels: WordLadderLabels = DEFAULT_LABELS,
): string {
  return [
    labels.prompt,
    marks.map((mark) => MARK_GLYPHS[mark]).join(""),
    `${labels.statTime} ${formatDuration(stats.timeMs)}`,
    `${labels.statInstinct} ${stats.instinct}/${stats.steps}`,
    `${labels.statRetries} ${stats.retries}`,
    `${labels.statStreak} ${stats.streak}`,
  ]
    .filter((line) => line.length > 0)
    .join("\n");
}

/** The glyph one resolved rung prints on the card. */
export function markGlyph(mark: RungMark): string {
  return MARK_GLYPHS[mark];
}
