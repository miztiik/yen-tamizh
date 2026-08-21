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
export type Id = string
/**
 * @minItems 1
 */
export type Nodes = [JourneyNode, ...(JourneyNode)[]]
export type Difficulty = string
export type Gameid = string
export type Id1 = string
export type Packid = string
export type Unlockrule = ("open" | "previous-complete")
export type Theme = string
export type Titleta = string
export type Version1 = string

/**
 * One curated path: its title, its palette, and its nodes in walking order.
 */
export interface Journey {
changelog: Changelog
id: Id
nodes: Nodes
theme: Theme
titleTa: Titleta
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
 * One level of the path: which Game, how hard, when it opens, and its board.
 * 
 * ``gameId``/``packId``/``difficulty``/``payload`` are deliberately the same
 * four fields a ``puzzle-file`` item carries, because a node IS one item - the
 * difference between a Journey and a Daily is which order they are met in and
 * what decides that, not what a puzzle is.
 */
export interface JourneyNode {
difficulty: Difficulty
gameId: Gameid
id: Id1
packId: Packid
payload: Payload
unlockRule: Unlockrule
}
export interface Payload {
[k: string]: unknown
}
