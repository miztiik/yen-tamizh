/* eslint-disable */
/**
 * DO NOT EDIT. Generated from schemas/<name>.schema.json by
 * scripts/gen-contracts.mjs (Row 5 contract pipeline). To change a shape,
 * edit the Pydantic model under backend/yen_tamizh_backend/contracts/,
 * re-run the exporter, then re-run `npm run gen:contracts`.
 */

export type Commonmaxpercentile = number
export type Midmaxpercentile = number
/**
 * @minItems 1
 */
export type Changelog = [ChangelogEntry, ...(ChangelogEntry)[]]
export type Change = string
export type Version = string
export type Why = string
export type Corpusroot = string
export type Dropcategories = string[]
export type Maxlength = number
export type Maxwords = (number | null)
export type Minlength = number
export type Mintotalfrequency = number
/**
 * @minItems 1
 */
export type Sources = [CorpusSource, ...(CorpusSource)[]]
export type Categoryfield = (string | null)
export type Countcolumn = (number | null)
export type Countfield = (string | null)
export type Delimiter = (string | null)
export type Enabled = boolean
export type Hasheader = boolean
export type Id = string
export type Kind = ("delimited" | "json-array")
export type Name = string
export type Note = (string | null)
export type Origin = string
export type Path = string
export type Rootkey = (string | null)
export type Wordcolumn = (number | null)
export type Wordfield = (string | null)
export type Version1 = string

/**
 * The declarative corpus source registry read by ``corpus/ingest.py``.
 */
export interface CorpusSources {
bands: CorpusBands
changelog: Changelog
corpusRoot: Corpusroot
filters: CorpusFilters
sources: Sources
version: Version1
}
/**
 * Where the ``freqBand`` cuts fall, as fractions of the ranked list.
 * 
 * A word's band is decided by its rank percentile, not by a raw count, so the
 * bands stay meaningful when a new source shifts every absolute frequency.
 */
export interface CorpusBands {
commonMaxPercentile: Commonmaxpercentile
midMaxPercentile: Midmaxpercentile
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
 * What the ingest keeps. Every knob is tunable data (Holy Law #6).
 * 
 * ``minLength`` / ``maxLength`` count EZHUTHU (Tamil grapheme clusters), not
 * code points - the same unit every Game plays in (Row 6).
 * ``dropCategories`` suppresses source category tags that carry no signal.
 * ``maxWords`` caps the committed artifact; ``null`` means uncapped.
 */
export interface CorpusFilters {
dropCategories?: Dropcategories
maxLength: Maxlength
maxWords?: Maxwords
minLength: Minlength
minTotalFrequency: Mintotalfrequency
}
/**
 * One registered word source: where its bytes are and how to read them.
 */
export interface CorpusSource {
categoryField?: Categoryfield
countColumn?: Countcolumn
countField?: Countfield
delimiter?: Delimiter
enabled?: Enabled
hasHeader?: Hasheader
id: Id
kind: Kind
name: Name
note?: Note
origin: Origin
path: Path
rootKey?: Rootkey
wordColumn?: Wordcolumn
wordField?: Wordfield
}
