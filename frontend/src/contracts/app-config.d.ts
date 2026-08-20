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
/**
 * @minItems 1
 */
export type Games = [string, ...(string)[]]
export type Playlistlength = number
/**
 * @minItems 1
 */
export type Themedgames = [string, ...(string)[]]
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
 * The Daily playlist: how long a day is, and which Games fill it (modes.md).
 * 
 * ``games`` is a RING rather than a set. A day takes the ``playlistLength``
 * window that starts at its own date, so every Game reaches a player without
 * any day holding all of them - which is what keeps the Daily a burst rather
 * than a sitting. The order of the ring is therefore a real knob: it decides
 * which Games co-occur, not which comes first (that is ``dailyRank``, in
 * ``config/daily-generator.json``).
 * 
 * ``games`` must be at least as long as the playlist, so an ordinary day can
 * never deal the same Game twice.
 * 
 * ``themedGames`` is the ring a THEMED day draws from, and it is deliberately
 * allowed to be SHORTER than the playlist. The two rings answer different
 * questions: an ordinary day's claim is variety of GAMES, so it never repeats
 * one; a themed day's claim is that its WORDS belong together, so it holds
 * only the Games that theme can honestly fill and repeats one rather than
 * reaching for a Game whose slots the theme cannot fill without padding.
 */
export interface DailyConfig {
games: Games
playlistLength: Playlistlength
themedGames: Themedgames
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
