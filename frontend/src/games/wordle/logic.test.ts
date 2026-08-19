import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

import { segment } from "../../tamil/ezhuthu";

import {
  AYTHAM,
  BASE_KEYS,
  DEFAULT_LABELS,
  EZHUTHU_INVENTORY,
  MATRA,
  MEI_BASES,
  PULLI,
  UYIR,
  VOWEL_FORMS,
  answerEzhuthu,
  applyVowelForm,
  attemptsRemaining,
  backspace,
  baseOf,
  baseScore,
  boardWidth,
  clearDraft,
  compose,
  initialState,
  isDraftFull,
  keyStates,
  keyToAction,
  liveBase,
  markGuess,
  markedRows,
  nextHint,
  normalizeState,
  pushEzhuthu,
  resolveLabels,
  revealNextHint,
  revealedHints,
  scoreFor,
  submitAttempt,
  type Mark,
  type WordlePayload,
} from "./logic";

// Tamil in a SOURCE file is written as \uXXXX escapes (the repo's encoding
// convention: raw UTF-8 belongs in data files, escapes in code), with the
// romanisation in a comment so the table can be read without a Tamil font.

// mee | tr | koo | L | ka | L   -  "meeRkooLkaL", quotations. Every property the
// Oracle needs in one real served word: the mei L TWICE, the two-part matra koo,
// and three pulli-bearing mei.
const ANSWER = [
  "\u0BAE\u0BC7", // mee
  "\u0BB1\u0BCD", // tr (mei)
  "\u0B95\u0BCB", // koo  - two-part matra, one code point in NFC
  "\u0BB3\u0BCD", // L (mei)
  "\u0B95", // ka
  "\u0BB3\u0BCD", // L (mei) - the duplicate
];

const PAYLOAD: WordlePayload = {
  word: ANSWER.join(""),
  attempts: 8,
};

/** A guess row, written as ezhuthu so the table reads as the board does. */
interface OracleCase {
  name: string;
  guess: string[];
  answer: string[];
  expected: Mark[];
  why: string;
}

// THE FEEDBACK ORACLE. Every row was derived BY HAND from the two-pass rule and
// then written down; the implementation is what has to agree with it, not the
// other way round. `c`/`p`/`.` in the `why` line is the expected vector.
const C: Mark = "correct";
const P: Mark = "present";
const A: Mark = "absent";

const ORACLE: OracleCase[] = [
  {
    name: "the answer itself is all correct",
    guess: [...ANSWER],
    answer: ANSWER,
    expected: [C, C, C, C, C, C],
    why: "every position matches, so nothing reaches the second pass at all",
  },
  {
    name: "DUPLICATE: the guess plays ka twice, one of them in the right place",
    // kaa | y | ka | tri | ka | L  -  "kaaykaRikaL", vegetables
    guess: [
      "\u0B95\u0BBE",
      "\u0BAF\u0BCD",
      "\u0B95",
      "\u0BB1\u0BBF",
      "\u0B95",
      "\u0BB3\u0BCD",
    ],
    answer: ANSWER,
    expected: [A, A, A, A, C, C],
    why:
      "the answer holds ONE ka and the guess plays two. The exact match at 4 " +
      "takes it, so it never enters the leftover pool and the ka at 2 has " +
      "nothing to claim - absent, not present. A single-pass 'is it anywhere' " +
      "test would light both up and claim the word holds two.",
  },
  {
    name: "DUPLICATE: the guess plays ka twice and NEITHER is in the right place",
    // chu | ru | k | ka | maa | ka  -  "surukkamaaka", briefly
    guess: [
      "\u0B9A\u0BC1",
      "\u0BB0\u0BC1",
      "\u0B95\u0BCD",
      "\u0B95",
      "\u0BAE\u0BBE",
      "\u0B95",
    ],
    answer: ANSWER,
    expected: [A, A, A, P, A, A],
    why:
      "the pool holds one ka, so the leftmost unmatched ka takes it and the " +
      "second gets nothing. The k at index 2 is a MEI and a different ezhuthu " +
      "from the ka the answer holds, so it is absent rather than present.",
  },
  {
    name: "DUPLICATE both sides: the answer holds L twice and the guess plays it twice",
    // kee | L | vi | th | thaa | L  -  "keeLviththaaL", a question paper
    guess: [
      "\u0B95\u0BC7",
      "\u0BB3\u0BCD",
      "\u0BB5\u0BBF",
      "\u0BA4\u0BCD",
      "\u0BA4\u0BBE",
      "\u0BB3\u0BCD",
    ],
    answer: ANSWER,
    expected: [A, P, A, A, A, C],
    why:
      "both of the answer's L are accounted for and neither is double-counted: " +
      "the aligned one at 5 is correct, which leaves exactly one in the pool " +
      "for the unaligned one at 1.",
  },
  {
    name: "TWO-PART MATRA: kaa is not koo, even though both are ka plus a vowel",
    // ka | N | kaa | Ni | p | pu  -  "kaNkaaNippu", supervision
    guess: [
      "\u0B95",
      "\u0BA3\u0BCD",
      "\u0B95\u0BBE",
      "\u0BA3\u0BBF",
      "\u0BAA\u0BCD",
      "\u0BAA\u0BC1",
    ],
    answer: ANSWER,
    expected: [P, A, A, A, A, A],
    why:
      "index 2 plays kaa against the answer's koo. They share the base ka and " +
      "are DIFFERENT ezhuthu, so the mark is absent - a marker walking code " +
      "points would find the ka code point in both and wrongly say present. " +
      "The bare ka at index 0 really is present, from the answer's index 4.",
  },
  {
    name: "PULLI: the mei L is not the uyirmei La",
    // vi | La | m | pa | ra | m  -  "viLamparam", an advertisement
    answer: [
      "\u0BB5\u0BBF",
      "\u0BB3",
      "\u0BAE\u0BCD",
      "\u0BAA",
      "\u0BB0",
      "\u0BAE\u0BCD",
    ],
    // the same word with the pulli ADDED at index 1, which is a legal row here
    // because this Game accepts any complete row of ezhuthu
    guess: [
      "\u0BB5\u0BBF",
      "\u0BB3\u0BCD",
      "\u0BAE\u0BCD",
      "\u0BAA",
      "\u0BB0",
      "\u0BAE\u0BCD",
    ],
    expected: [C, A, C, C, C, C],
    why:
      "one pulli is the whole difference. L and La are different ezhuthu, so " +
      "the position is absent rather than present - the answer holds no L at " +
      "all. Five correct beside it is what makes the single miss legible.",
  },
  {
    name: "a guess sharing nothing is all absent",
    guess: [
      "\u0BB5\u0BBF",
      "\u0BB3",
      "\u0BAE\u0BCD",
      "\u0BAA",
      "\u0BB0",
      "\u0BAE\u0BCD",
    ],
    answer: ANSWER,
    expected: [A, A, A, A, A, A],
    why: "no ezhuthu of viLamparam appears in meeRkooLkaL, pulli and all",
  },
];

describe("wordle feedback (ORACLE)", () => {
  test.each(ORACLE.map((entry) => entry.name))("%s", (name) => {
    const entry = ORACLE.find((candidate) => candidate.name === name);
    expect(entry, name).toBeDefined();
    if (entry === undefined) return;
    expect(markGuess(entry.guess, entry.answer), entry.why).toEqual(entry.expected);
  });

  test("every Oracle row is a well-formed board row", () => {
    for (const entry of ORACLE) {
      expect(entry.guess).toHaveLength(entry.answer.length);
      expect(entry.expected).toHaveLength(entry.answer.length);
      // Each written unit really is ONE ezhuthu by the shared Row 6 library, so
      // the table cannot silently be testing code points.
      for (const unit of [...entry.guess, ...entry.answer]) {
        expect(segment(unit)).toEqual([unit]);
      }
    }
  });

  test("the table covers every mark and both duplicate shapes", () => {
    const marks = new Set(ORACLE.flatMap((entry) => entry.expected));
    expect([...marks].sort()).toEqual(["absent", "correct", "present"]);
    expect(ORACLE.filter((entry) => entry.name.startsWith("DUPLICATE"))).toHaveLength(3);
  });

  test("a guess of the wrong width is refused rather than partly marked", () => {
    expect(() => markGuess(ANSWER.slice(0, 3), ANSWER)).toThrow(/3 ezhuthu against a 6/);
  });

  test("marking is symmetric in count: correct plus present never exceeds the answer's copies", () => {
    // The property behind the two-pass rule, checked over the whole table.
    for (const entry of ORACLE) {
      const marked = markGuess(entry.guess, entry.answer);
      const answered = new Map<string, number>();
      for (const unit of entry.answer) {
        answered.set(unit, (answered.get(unit) ?? 0) + 1);
      }
      const claimed = new Map<string, number>();
      entry.guess.forEach((unit, index) => {
        if (marked[index] !== "absent") claimed.set(unit, (claimed.get(unit) ?? 0) + 1);
      });
      for (const [unit, count] of claimed) {
        expect(count, `${entry.name}: claimed more copies than the answer holds`).toBeLessThanOrEqual(
          answered.get(unit) ?? 0,
        );
      }
    }
  });
});

describe("the ezhuthu composer", () => {
  test("holds exactly the 247, with no repeats", () => {
    expect(EZHUTHU_INVENTORY).toHaveLength(247);
    expect(new Set(EZHUTHU_INVENTORY).size).toBe(247);
    expect(UYIR).toHaveLength(12);
    expect(MEI_BASES).toHaveLength(18);
    expect(MATRA).toHaveLength(11);
    expect(VOWEL_FORMS).toHaveLength(13);
  });

  test("every inventory entry is exactly ONE ezhuthu by the shared library", () => {
    for (const unit of EZHUTHU_INVENTORY) {
      expect(segment(unit), unit).toEqual([unit]);
    }
  });

  test("thirty-one keys commit on their own; the rest are reached by re-spelling", () => {
    expect(BASE_KEYS).toHaveLength(31);
    expect(new Set(BASE_KEYS).size).toBe(31);
    const reachable = new Set(BASE_KEYS);
    for (const base of MEI_BASES) {
      for (const form of VOWEL_FORMS) reachable.add(compose(base, form));
    }
    // Every one of the 247 is reachable in at most two taps.
    for (const unit of EZHUTHU_INVENTORY) expect(reachable.has(unit), unit).toBe(true);
  });

  test("a vowel form re-spells the last cell instead of adding a letter", () => {
    let state = initialState();
    state = pushEzhuthu(PAYLOAD, state, "\u0B95"); // ka
    expect(state.draft).toEqual(["\u0B95"]);
    state = applyVowelForm(state, "\u0BBE"); // + aa sign
    expect(state.draft).toEqual(["\u0B95\u0BBE"]); // kaa, still ONE cell
    state = applyVowelForm(state, "\u0BBF"); // + i sign, replacing aa
    expect(state.draft).toEqual(["\u0B95\u0BBF"]); // ki
    state = applyVowelForm(state, PULLI);
    expect(state.draft).toEqual(["\u0B95\u0BCD"]); // k, the mei
    state = applyVowelForm(state, ""); // back to the inherent /a/
    expect(state.draft).toEqual(["\u0B95"]);
  });

  test("a uyir and the aytham have no base, so a form key does nothing to them", () => {
    for (const unit of ["\u0B85", AYTHAM]) {
      let state = pushEzhuthu(PAYLOAD, initialState(), unit);
      expect(baseOf(unit)).toBeNull();
      expect(liveBase(state)).toBeNull();
      state = applyVowelForm(state, "\u0BBE");
      expect(state.draft).toEqual([unit]);
    }
  });

  test("the live base follows the last composed cell", () => {
    let state = initialState();
    expect(liveBase(state)).toBeNull();
    state = pushEzhuthu(PAYLOAD, state, "\u0B95\u0BCB"); // koo
    expect(liveBase(state)).toBe("\u0B95");
    state = pushEzhuthu(PAYLOAD, state, "\u0BAE\u0BC7"); // mee
    expect(liveBase(state)).toBe("\u0BAE");
    state = backspace(state);
    expect(liveBase(state)).toBe("\u0B95");
  });

  test("the row fills to the board's width and stops", () => {
    let state = initialState();
    for (let i = 0; i < 10; i += 1) state = pushEzhuthu(PAYLOAD, state, "\u0B95");
    expect(state.draft).toHaveLength(boardWidth(PAYLOAD));
    expect(isDraftFull(PAYLOAD, state)).toBe(true);
    expect(clearDraft(state).draft).toEqual([]);
    expect(backspace(state).draft).toHaveLength(5);
  });

  test("the board's width is derived from the answer, never stored", () => {
    expect(boardWidth(PAYLOAD)).toBe(6);
    expect(answerEzhuthu(PAYLOAD)).toEqual(ANSWER);
    expect(answerEzhuthu({ ...PAYLOAD, word: "\u0B95\u0BCB\u0BAF\u0BBF" })).toEqual([
      "\u0B95\u0BCB",
      "\u0BAF\u0BBF",
    ]);
  });
});

describe("every served answer is typeable on the composer", () => {
  // The parity Oracle against the Python contract: `WordlePuzzle` refuses a word
  // holding an ezhuthu outside the 247, and this asserts the SAME property from
  // the keyboard's side over the whole committed set. If the two inventories
  // ever diverged, a puzzle would validate on the backend and be unwinnable in
  // the browser.
  const here = dirname(fileURLToPath(import.meta.url));
  const setPath = resolve(here, "../../../../datasets/wordlists/derived/wordle.json");
  const served = JSON.parse(readFileSync(setPath, "utf-8")) as { words: { word: string }[] };
  const inventory = new Set(EZHUTHU_INVENTORY);

  test("the committed set is non-trivial", () => {
    expect(served.words.length).toBeGreaterThan(1000);
  });

  test("no served word holds an ezhuthu the keyboard cannot produce", () => {
    const unreachable = new Set<string>();
    for (const row of served.words) {
      for (const unit of segment(row.word)) {
        if (!inventory.has(unit)) unreachable.add(unit);
      }
    }
    expect([...unreachable]).toEqual([]);
  });

  test("every served word is exactly six ezhuthu, the one width the board draws", () => {
    const widths = new Set(served.words.map((row) => segment(row.word).length));
    expect([...widths]).toEqual([6]);
  });
});

describe("keyboard state", () => {
  test("keeps the BEST fact about an ezhuthu, not the latest", () => {
    // kaa y ka tri ka L marks ka correct at 4; a later row plays ka elsewhere.
    const first = [
      "\u0B95\u0BBE",
      "\u0BAF\u0BCD",
      "\u0B95",
      "\u0BB1\u0BBF",
      "\u0B95",
      "\u0BB3\u0BCD",
    ];
    const second = [
      "\u0B9A\u0BC1",
      "\u0BB0\u0BC1",
      "\u0B95\u0BCD",
      "\u0B95",
      "\u0BAE\u0BBE",
      "\u0B95",
    ];
    const state = { ...initialState(), guesses: [first, second] };
    const states = keyStates(PAYLOAD, state);
    expect(states.get("\u0B95")).toBe("correct");
    expect(states.get("\u0BB3\u0BCD")).toBe("correct");
    expect(states.get("\u0B95\u0BBE")).toBe("absent");
    // Never aggregated over a base: koo is still unknown even though kaa is out.
    expect(states.has("\u0B95\u0BCB")).toBe(false);
  });

  test("says nothing before the first guess", () => {
    expect(keyStates(PAYLOAD, initialState()).size).toBe(0);
    expect(markedRows(PAYLOAD, initialState())).toEqual([]);
  });
});

describe("playing a round", () => {
  function fill(units: string[]) {
    let state = initialState();
    for (const unit of units) state = pushEzhuthu(PAYLOAD, state, unit);
    return state;
  }

  test("a short row is refused without spending an attempt", () => {
    const state = fill(ANSWER.slice(0, 3));
    expect(submitAttempt(PAYLOAD, state)).toBeNull();
    expect(attemptsRemaining(PAYLOAD, state)).toBe(8);
  });

  test("a complete row is always accepted, whatever it spells", () => {
    // Six copies of one ezhuthu is not a Tamil word and is still a legal guess:
    // this Game ships no accept list, so a real word can never be refused.
    const nonsense = Array.from({ length: 6 }, () => "\u0B95");
    const outcome = submitAttempt(PAYLOAD, fill(nonsense));
    expect(outcome).not.toBeNull();
    expect(outcome?.correct).toBe(false);
    expect(outcome?.state.guesses).toHaveLength(1);
    // One ka in the answer, six played: exactly one may be marked.
    expect(outcome?.marks.filter((mark) => mark !== "absent")).toHaveLength(1);
  });

  test("a winning row finishes, scores, and leaves the marks on the board", () => {
    const outcome = submitAttempt(PAYLOAD, fill(ANSWER));
    expect(outcome?.correct).toBe(true);
    expect(outcome?.state.finished).toBe(true);
    expect(outcome?.state.solved).toBe(true);
    expect(outcome?.state.score).toBe(60); // 6 ezhuthu at the shared 10 a letter
    expect(outcome?.attempt).toBe(PAYLOAD.word);
    expect(markedRows(PAYLOAD, outcome?.state ?? initialState())).toHaveLength(1);
  });

  test("spending the last attempt ends the puzzle without a win", () => {
    let state = initialState();
    const miss = ["\u0BB5\u0BBF", "\u0BB3", "\u0BAE\u0BCD", "\u0BAA", "\u0BB0", "\u0BAE\u0BCD"];
    for (let attempt = 1; attempt <= PAYLOAD.attempts; attempt += 1) {
      const draft = { ...state, draft: [...miss] };
      const outcome = submitAttempt(PAYLOAD, draft);
      expect(outcome).not.toBeNull();
      state = outcome?.state ?? state;
      expect(outcome?.exhausted).toBe(attempt === PAYLOAD.attempts);
    }
    expect(state.finished).toBe(true);
    expect(state.solved).toBe(false);
    expect(state.score).toBe(0);
    expect(attemptsRemaining(PAYLOAD, state)).toBe(0);
    // A finished board takes no more input.
    expect(pushEzhuthu(PAYLOAD, state, "\u0B95")).toBe(state);
    expect(submitAttempt(PAYLOAD, { ...state, draft: [...miss] })).toBeNull();
  });

  test("a hint costs the brag, and a heavily hinted win never goes negative", () => {
    const hinted: WordlePayload = {
      ...PAYLOAD,
      hints: [
        { kind: "category", text: "\u0B95", cost: 1 },
        { kind: "meaning", text: "\u0B95", cost: 3 },
      ],
    };
    let state = initialState();
    expect(nextHint(hinted, state)?.kind).toBe("category");
    state = revealNextHint(hinted, state);
    state = revealNextHint(hinted, state);
    expect(revealedHints(hinted, state)).toHaveLength(2);
    expect(nextHint(hinted, state)).toBeNull();
    expect(revealNextHint(hinted, state)).toBe(state);
    expect(scoreFor(hinted, state)).toBe(60 - 4);
    expect(scoreFor({ ...hinted, hints: [{ kind: "k", text: "t", cost: 500 }] }, {
      ...state,
      revealedHintCount: 1,
    })).toBe(0);
  });

  test("the Mode may override the base score through the config slice", () => {
    expect(baseScore(PAYLOAD)).toBe(60);
    expect(baseScore(PAYLOAD, { baseScore: 25 })).toBe(25);
    expect(baseScore(PAYLOAD, { baseScore: "lots" })).toBe(60);
    expect(baseScore(PAYLOAD, { baseScore: -4 })).toBe(60);
  });
});

describe("state round-trip", () => {
  test("a persisted snapshot restores", () => {
    const state = {
      ...initialState(),
      guesses: [[...ANSWER]],
      draft: ["\u0B95"],
      revealedHintCount: 1,
      score: 7,
    };
    expect(normalizeState(JSON.parse(JSON.stringify(state)))).toEqual(state);
  });

  test("junk reads back as a fresh board rather than crashing", () => {
    expect(normalizeState(null)).toEqual(initialState());
    expect(normalizeState("nope")).toEqual(initialState());
    expect(normalizeState({ guesses: "no", draft: 4, score: "x" })).toEqual(initialState());
    // A row that is not a list of strings is dropped, not half-restored.
    expect(normalizeState({ guesses: [["\u0B95"], [1, 2]] }).guesses).toEqual([["\u0B95"]]);
  });
});

describe("keys and copy", () => {
  test("maps the physical keyboard to mechanic actions", () => {
    expect(keyToAction("Enter")).toBe("press");
    expect(keyToAction(" ")).toBe("press");
    expect(keyToAction("Backspace")).toBe("undo");
    expect(keyToAction("Escape")).toBe("clear");
    expect(keyToAction("q")).toBeNull();
  });

  test("labels default to Tamil and accept overrides from the config slice", () => {
    expect(resolveLabels()).toEqual(DEFAULT_LABELS);
    expect(resolveLabels({ labels: { correct: "yes" } }).correct).toBe("yes");
    expect(resolveLabels({ labels: { correct: "" } }).correct).toBe(DEFAULT_LABELS.correct);
    expect(resolveLabels({ labels: 4 })).toEqual(DEFAULT_LABELS);
  });
});
