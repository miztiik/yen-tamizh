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
export type Playlistlength = number
export type Enabled = boolean
export type Defaultdifficulty = string
export type Lruwindow = number
export type Durationsec = number
export type Defaultmode = string
export type Defaulttheme = string
/**
 * @minItems 1
 */
export type Enabledmodes = [string, ...(string)[]]
export type Version1 = string

/**
 * The tunable knobs both runtimes read; a fresh clone runs on the defaults.
 */
export interface AppConfig {
changelog: Changelog
daily: DailyConfig
hints: HintsConfig
infinite: InfiniteConfig
timeTrial: TimeTrialConfig
ui: UiConfig
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
 * The Daily playlist: how many items and the per-Game mix (modes.md).
 */
export interface DailyConfig {
mix: Mix
playlistLength: Playlistlength
}
export interface Mix {
/**
 * This interface was referenced by `Mix`'s JSON-Schema definition
 * via the `patternProperty` "^[a-z][a-z0-9-]*$".
 */
[k: string]: number
}
/**
 * Hint availability: a global switch and a per-Game allowance.
 */
export interface HintsConfig {
enabled: Enabled
perGame: Pergame
}
export interface Pergame {
/**
 * This interface was referenced by `Pergame`'s JSON-Schema definition
 * via the `patternProperty` "^[a-z][a-z0-9-]*$".
 */
[k: string]: number
}
/**
 * Infinite mode: the anti-repeat LRU window and the default difficulty.
 */
export interface InfiniteConfig {
defaultDifficulty: Defaultdifficulty
lruWindow: Lruwindow
}
/**
 * Time Trial mode: the run duration in seconds.
 */
export interface TimeTrialConfig {
durationSec: Durationsec
}
/**
 * UI shell: which Modes are live, and the default Mode and theme.
 */
export interface UiConfig {
defaultMode: Defaultmode
defaultTheme: Defaulttheme
enabledModes: Enabledmodes
}
