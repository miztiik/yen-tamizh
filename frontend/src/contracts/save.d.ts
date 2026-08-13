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
export type Daykey = string
export type Lastplayed = string
export type Seeninfiniteids = string[]
export type Streak = number
export type Version1 = string

/**
 * Today's progress, streak, and last-played day; browser-local only.
 */
export interface Save {
changelog: Changelog
dayKey: Daykey
lastPlayed: Lastplayed
perMode: Permode
seenInfiniteIds: Seeninfiniteids
streak: Streak
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
export interface Permode {
/**
 * This interface was referenced by `Permode`'s JSON-Schema definition
 * via the `patternProperty` "^[a-z][a-z0-9-]*$".
 */
[k: string]: {
[k: string]: unknown
}
}
