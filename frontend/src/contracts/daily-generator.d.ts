/* eslint-disable */
/**
 * DO NOT EDIT. Generated from schemas/<name>.schema.json by
 * scripts/gen-contracts.mjs (Row 5 contract pipeline). To change a shape,
 * edit the Pydantic model under backend/yen_tamizh_backend/contracts/,
 * re-run the exporter, then re-run `npm run gen:contracts`.
 */

export type Bankdir = string
/**
 * @minItems 1
 */
export type Changelog = [ChangelogEntry, ...(ChangelogEntry)[]]
export type Change = string
export type Version = string
export type Why = string
export type Daysahead = number
/**
 * @minItems 1
 */
export type Games = [GameGeneration, ...(GameGeneration)[]]
export type Attempts = number
/**
 * @minItems 1
 */
export type Difficulties = [DifficultyBand, ...(DifficultyBand)[]]
export type Id = string
export type Maxlength = number
export type Minlength = number
export type Gameid = string
export type Cost = number
export type Kind = string
export type Template = string
export type Hints = HintSpec[]
export type Packid = string
export type Reveal = number
export type Timelimitsec = number
export type Wordlist = string
export type Version1 = string

/**
 * The daily engine's knobs: where the bank lands and how a day is filled.
 */
export interface DailyGenerator {
bankDir: Bankdir
changelog: Changelog
daysAhead: Daysahead
games: Games
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
 * How one Game turns a wordlist row into a playable puzzle.
 */
export interface GameGeneration {
attempts: Attempts
difficulties: Difficulties
gameId: Gameid
hints?: Hints
packId: Packid
reveal: Reveal
timeLimitSec: Timelimitsec
wordlist: Wordlist
}
/**
 * One difficulty bucket: the ezhuthu lengths it covers and its id.
 * 
 * Difficulty is derived from the word's ezhuthu count because that is the only
 * honest difficulty signal the derived set carries; a 3-ezhuthu scramble has 6
 * arrangements and a 6-ezhuthu one has 720. Where the cuts fall is a
 * game-balance number, so it lives here rather than in Python (Holy Law #6).
 */
export interface DifficultyBand {
id: Id
maxLength: Maxlength
minLength: Minlength
}
/**
 * One offered hint: its kind, its wording, and what revealing it costs.
 * 
 * ``template`` is a Python format string over the wordlist row's honest hint
 * fields (``{firstEzhuthu}``, ``{length}``). The rendered TEXT is per-puzzle
 * data and ships inside the puzzle payload, but the WORDING is player-facing
 * copy - so it lives in config, not in a Python literal, and the generator
 * only fills in the values.
 */
export interface HintSpec {
cost: Cost
kind: Kind
template: Template
}
