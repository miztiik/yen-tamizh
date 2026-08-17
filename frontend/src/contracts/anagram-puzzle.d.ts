/* eslint-disable */
/**
 * DO NOT EDIT. Generated from schemas/<name>.schema.json by
 * scripts/gen-contracts.mjs (Row 5 contract pipeline). To change a shape,
 * edit the Pydantic model under backend/yen_tamizh_backend/contracts/,
 * re-run the exporter, then re-run `npm run gen:contracts`.
 */

export type Alsovalid = ([string, ...(string)[]] | null)
export type Attempts = number
/**
 * @minItems 1
 */
export type Changelog = [ChangelogEntry, ...(ChangelogEntry)[]]
export type Change = string
export type Version = string
export type Why = string
export type Hints = (Hint[] | null)
export type Cost = number
export type Kind = string
export type Text = string
export type Meaning = (string | null)
export type Reveal = (number | null)
/**
 * @minItems 1
 */
export type Tiles = [string, ...(string)[]]
export type Timelimitsec = number
export type Translationen = (string | null)
export type Version1 = string
export type Word = string

/**
 * One anagram puzzle: a target word, its scrambled ezhuthu tiles, and rules.
 * 
 * ``meaning``, ``translationEn`` and ``alsoValid`` are RESOLVED at bake time,
 * never at play time. The generator holds the lexicon columns and the whole
 * served wordlist; the player downloads what those resolved to, not the inputs
 * they resolved from - so all three are finished display values, never arrays
 * the Game would have to pick from.
 * 
 * ``meaning`` is one already-rendered Tamil display string - what the word
 * means, shown free on the summary once the word is revealed. It is absent
 * when the lexicon has nothing to say, and an absent meaning renders as the
 * word alone: an empty slot would advertise a hole in the data.
 * 
 * ``translationEn`` is the summary's DEMOTED second line and nothing else. It
 * is never a hint and never the meaning line: a paid rung the player cannot
 * read is a rung that stole score, so the meaning rung is omitted rather than
 * answered in English.
 * 
 * ``alsoValid`` lists the OTHER served words the same tiles spell. It has to
 * be baked because the Game cannot derive it - ``anagramFanOut`` is a count,
 * and reading a wordlist at runtime is forbidden - and without it a player who
 * arranges a real Tamil word gets a flat rejection instead of "that is a word,
 * but not today's". It is absent for the overwhelming majority of words: true
 * Tamil co-anagrams are rare.
 */
export interface AnagramPuzzle {
alsoValid?: Alsovalid
attempts: Attempts
changelog: Changelog
hints?: Hints
meaning?: Meaning
reveal?: Reveal
tiles: Tiles
timeLimitSec: Timelimitsec
translationEn?: Translationen
version: Version1
word: Word
}
/**
 * One dated entry in a schema's in-file change log (newest first).
 * 
 * ``version`` is the date-stamp of the change; ``change`` is what changed;
 * ``why`` is the reason it changed (CLAUDE.md section 11).
 */
export interface ChangelogEntry {
change: Change
version: Version
why: Why
}
/**
 * One optional, honest hint: its kind, its text, and its score cost.
 * 
 * ``text`` is per-puzzle generated DATA (the next honest step for this
 * puzzle), not a static UI label - so it lives in the puzzle payload, not in
 * ``config/copy.json``. A hint never sells a power-up (a project non-goal); it
 * reveals the next honest step (core-loop.md).
 */
export interface Hint {
cost: Cost
kind: Kind
text: Text
}
