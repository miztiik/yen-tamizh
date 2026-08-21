/* eslint-disable */
/**
 * DO NOT EDIT. Generated from schemas/<name>.schema.json by
 * scripts/gen-contracts.mjs (Row 5 contract pipeline). To change a shape,
 * edit the Pydantic model under backend/yen_tamizh_backend/contracts/,
 * re-run the exporter, then re-run `npm run gen:contracts`.
 */

export type Achievedon = string
export type Durationsec = number
export type Itemscompleted = number
export type Besttimetrialruns = TimeTrialBest[]
/**
 * @minItems 1
 */
export type Changelog = [ChangelogEntry, ...(ChangelogEntry)[]]
export type Change = string
export type Version = string
export type Why = string
export type Daykey = string
export type Lastplayed = string
export type Laststreakday = (string | null)
export type Seeninfiniteids = string[]
export type Streak = number
export type Version1 = string

/**
 * Today's progress, streak, and last-played day; browser-local only.
 */
export interface Save {
bestTimeTrialRuns?: Besttimetrialruns
changelog: Changelog
dayKey: Daykey
lastPlayed: Lastplayed
lastStreakDay?: Laststreakday
perMode: Permode
seenInfiniteIds: Seeninfiniteids
streak: Streak
version: Version1
}
/**
 * The furthest a player has got in one Time Trial run length, kept locally.
 * 
 * A best run is scored in ITEMS COMPLETED, and it is recorded against the
 * ``durationSec`` it was set at: the run length is a config knob, so a sprint
 * of thirty seconds and a sprint of two minutes are two different contests and
 * a record from one can never beat the other. ``achievedOn`` is the local
 * calendar day the run finished, which is what lets the screen say when the
 * record was set without keeping any history beside it.
 */
export interface TimeTrialBest {
achievedOn: Achievedon
durationSec: Durationsec
itemsCompleted: Itemscompleted
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
