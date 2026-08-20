/* eslint-disable */
/**
 * DO NOT EDIT. Generated from schemas/<name>.schema.json by
 * scripts/gen-contracts.mjs (Row 5 contract pipeline). To change a shape,
 * edit the Pydantic model under backend/yen_tamizh_backend/contracts/,
 * re-run the exporter, then re-run `npm run gen:contracts`.
 */

export type Alsovalid = ([string, ...(string)[]] | null)
/**
 * @minItems 1
 */
export type Changelog = [ChangelogEntry, ...(ChangelogEntry)[]]
export type Change = string
export type Version = string
export type Why = string
/**
 * @minItems 1
 */
export type Grid = [string[], ...(string[])[]]
/**
 * @minItems 1
 */
export type Targets = [WordSearchTarget, ...(WordSearchTarget)[]]
export type Direction = ("right" | "down-right" | "down" | "down-left" | "left" | "up-left" | "up" | "up-right")
export type Meaning = (string | null)
export type Col = number
export type Row = number
export type Word = string
export type Version1 = string

/**
 * One word-search board: the grid, the words hidden in it, and their places.
 * 
 * The grid is a list of rows, each a list of single ezhuthu. It must be
 * rectangular, because a ragged grid has no columns to run a vertical or
 * diagonal trace down.
 * 
 * Every target must be recoverable BY READING THE GRID: stepping
 * ``len(segment(word))`` cells from its ``start`` in its ``direction`` has to
 * spell the word exactly. That is this contract's Oracle, and it is stated
 * against the grid rather than against the generator so a placement bug cannot
 * ship a word the player is asked to find and cannot.
 */
export interface WordSearchPuzzle {
alsoValid?: Alsovalid
changelog: Changelog
grid: Grid
targets: Targets
version: Version1
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
 * One word hidden in the grid: where it starts and which way it runs.
 * 
 * ``meaning`` is resolved at bake time and shown FREE beside the word once the
 * player has traced it (the Row 14 rule that a solved word explains itself).
 * It rides the TARGET rather than the puzzle because a word search asks for
 * several words at once and the session summary carries one line per item, so
 * this board is the only place these meanings can ever be read.
 * 
 * ``translationEn`` deliberately does not travel. On the other three Games it
 * is the summary's demoted second line; here there is no such line, so its only
 * possible reader would be this board - and an English gloss under every word
 * of a Tamil grid doubles the list's height on a 360px screen to say something
 * the paid ladder is banned from selling anyway.
 */
export interface WordSearchTarget {
direction: Direction
meaning?: Meaning
start: GridPoint
word: Word
}
/**
 * One cell address: a row and a column, both counted from the top-left.
 */
export interface GridPoint {
col: Col
row: Row
}
