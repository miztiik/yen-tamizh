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
export type Gameid = string
export type Difficulty = string
export type Gameid1 = string
export type Id = string
export type Packid = string
export type Difficulty1 = string
export type Id1 = string
export type Items = PoolEntry[]
export type Totalcount = number
export type Version1 = string

/**
 * The manifest of one Game's pool: every item it holds, in id order.
 * 
 * ``totalCount`` is redundant with ``len(items)`` by construction, and the
 * validator below is what makes that redundancy safe rather than a second
 * authority: a reader may show "1 of 300" without walking the list, and a
 * hand-edited count is refused instead of believed.
 */
export interface PoolIndex {
changelog: Changelog
gameId: Gameid
itemSchema?: (PoolItem | null)
items: Items
totalCount: Totalcount
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
 * One committed pool puzzle: its address, its framing, and its board.
 */
export interface PoolItem {
difficulty: Difficulty
gameId: Gameid1
id: Id
packId: Packid
payload: Payload
}
export interface Payload {
[k: string]: unknown
}
/**
 * One line of the index: which item, and which band it belongs to.
 * 
 * Two fields, and the shortness is the point. The index is fetched before the
 * first puzzle of a stream, so every field added to it is paid for by every
 * player on every visit and multiplied by the size of the pool - a Tamil word
 * on each line would roughly double it and tell the Mode nothing it uses,
 * because the Mode picks by band and by what the save says it has seen.
 */
export interface PoolEntry {
difficulty: Difficulty1
id: Id1
}
