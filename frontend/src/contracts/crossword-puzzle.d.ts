/* eslint-disable */
/**
 * DO NOT EDIT. Generated from schemas/<name>.schema.json by
 * scripts/gen-contracts.mjs (Row 5 contract pipeline). To change a shape,
 * edit the Pydantic model under backend/yen_tamizh_backend/contracts/,
 * re-run the exporter, then re-run `npm run gen:contracts`.
 */

/**
 * @minItems 1
 */
export type Changelog = [ChangelogEntry, ...(ChangelogEntry)[]]
export type Change = string
export type Version = string
export type Why = string
export type Cols = number
/**
 * @minItems 2
 */
export type Entries = [CrosswordEntry, CrosswordEntry, ...(CrosswordEntry)[]]
export type Alsovalid = ([string, ...(string)[]] | null)
export type Clue = string
export type Direction = ("across" | "down")
export type Number = number
export type Col = number
export type Row = number
export type Word = string
export type Rows = number
export type Version1 = string

/**
 * One mini crossword: how big the board is, and every answer on it.
 * 
 * Blocked cells are not listed. A cell is OPEN exactly when some entry covers
 * it, so the mask is the union of the entries and there is no second statement
 * of it that could disagree with the first.
 */
export interface CrosswordPuzzle {
changelog: Changelog
cols: Cols
entries: Entries
rows: Rows
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
 * One answer on the board: where it starts, which way it runs, and its clue.
 * 
 * ``clue`` is resolved at bake time from the lexicon's own Tamil sense for the
 * answer. It is not invented and it is not translated: an English gloss under
 * a Tamil grid asks the player to solve a puzzle in a language the board is
 * not written in. A word whose only recorded sense spells the word out, or
 * carries Latin script, is not servable to this Game at all and is cut from
 * the wordlist rather than clued badly here.
 * 
 * ``alsoValid`` holds the words that fit this entry's CROSSED cells and are a
 * listed synonym of the answer - the only rivals that can be said to answer
 * the same clue. It travels so the Game can say "that is a word for the same
 * thing, but not the one this grid was built on" instead of a red cross.
 */
export interface CrosswordEntry {
alsoValid?: Alsovalid
clue: Clue
direction: Direction
number: Number
start: CrosswordCell
word: Word
}
/**
 * One cell address: a row and a column, both counted from the top-left.
 */
export interface CrosswordCell {
col: Col
row: Row
}
