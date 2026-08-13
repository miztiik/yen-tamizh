/* eslint-disable */
/**
 * DO NOT EDIT. Generated from schemas/<name>.schema.json by
 * scripts/gen-contracts.mjs (Row 5 contract pipeline). To change a shape,
 * edit the Pydantic model under backend/yen_tamizh_backend/contracts/,
 * re-run the exporter, then re-run `npm run gen:contracts`.
 */

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
export type Reveal = (number | null)
/**
 * @minItems 1
 */
export type Tiles = [string, ...(string)[]]
export type Timelimitsec = number
export type Version1 = string
export type Word = string

/**
 * One anagram puzzle: a target word, its scrambled ezhuthu tiles, and rules.
 */
export interface AnagramPuzzle {
attempts: Attempts
changelog: Changelog
hints?: Hints
reveal?: Reveal
tiles: Tiles
timeLimitSec: Timelimitsec
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
