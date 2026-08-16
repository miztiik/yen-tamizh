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
export type Maxstratum = number
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
 * One difficulty bucket: the ezhuthu lengths and the familiarity it covers.
 * 
 * Difficulty is TWO-AXIS - length and familiarity - because length alone is
 * anti-correlated at both tails. A long Tamil headword is usually a compound
 * that decomposes into recognisable chunks and is EASIER than its ezhuthu
 * count suggests, while a short rare word is brutal; a length-only easy bucket
 * therefore forces the generator into the shortest words, which are
 * disproportionately literary. A 3-ezhuthu answer also has only six
 * arrangements against three attempts, so it is brute-forceable by shuffling
 * without the player ever recognising the word.
 * 
 * ``maxStratum`` is the coarsest frequency quarter the band admits, 1 being
 * the most familiar quarter of the SERVED set. Bands deliberately OVERLAP on
 * length and tile on familiarity: what separates easy from hard is mostly how
 * well the player knows the word, not how many tiles it has.
 * 
 * Where the cuts fall is a game-balance number, so it lives here rather than
 * in Python (Holy Law #6).
 */
export interface DifficultyBand {
id: Id
maxLength: Maxlength
maxStratum: Maxstratum
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
