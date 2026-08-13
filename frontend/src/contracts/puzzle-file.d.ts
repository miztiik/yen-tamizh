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
export type Date = string
/**
 * @minItems 1
 */
export type Items = [PuzzleItem, ...(PuzzleItem)[]]
export type Difficulty = string
export type Gameid = string
export type Hints = (Hint[] | null)
export type Cost = number
export type Kind = string
export type Text = string
export type Packid = string
export type Version1 = string

/**
 * One day's committed, ordered playlist of puzzle items.
 */
export interface PuzzleFile {
changelog: Changelog
date: Date
items: Items
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
 * One playlist entry: a Game + Pack + difficulty and its open payload.
 */
export interface PuzzleItem {
difficulty: Difficulty
gameId: Gameid
hints?: Hints
packId: Packid
payload: Payload
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
export interface Payload {
[k: string]: unknown
}
