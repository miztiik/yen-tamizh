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
export type Belowfrequencyfloor = number
export type Capped = number
export type Distinct = number
export type Duplicates = number
export type Rejected = number
export type Rowsin = number
export type Rowskept = number
export type Generatedat = string
/**
 * @minItems 1
 */
export type Provenance = [SourceProvenance, ...(SourceProvenance)[]]
export type Bytes = number
export type Id = string
export type Name = string
export type Origin = string
export type Path = string
export type Rowsin1 = number
export type Rowskept1 = number
export type Sha256 = string
export type Version1 = string
export type Category = (string[] | null)
/**
 * @minItems 1
 */
export type Ezhuthu = [string, ...(string)[]]
export type Freqband = ("common" | "mid" | "rare")
export type Freqrank = number
export type Length = number
/**
 * @minItems 1
 */
export type Sources = [string, ...(string)[]]
export type Word = string
export type Words = MasterWord[]

/**
 * Every kept corpus word, ranked and banded, with its ingest provenance.
 */
export interface MasterWordlist {
changelog: Changelog
counters: IngestCounters
generatedAt: Generatedat
provenance: Provenance
version: Version1
words: Words
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
 * The reconciliation ledger for one ingest run (no silent drops).
 */
export interface IngestCounters {
belowFrequencyFloor: Belowfrequencyfloor
capped: Capped
distinct: Distinct
duplicates: Duplicates
rejected: Rejected
rowsIn: Rowsin
rowsKept: Rowskept
}
/**
 * What one enabled source contributed, and which bytes it contributed from.
 * 
 * ``sha256`` + ``bytes`` identify the exact input, so a later run can prove it
 * read the same file. The user waived license classification for plain word
 * lists; ``name`` + ``origin`` are the traceability record.
 */
export interface SourceProvenance {
bytes: Bytes
id: Id
name: Name
origin: Origin
path: Path
rowsIn: Rowsin1
rowsKept: Rowskept1
sha256: Sha256
}
/**
 * One ranked corpus word.
 * 
 * ``length`` counts EZHUTHU, not code points: the ezhuthu is the unit every
 * Game plays in, and a 3-ezhuthu word can be 5 code points long.
 */
export interface MasterWord {
category?: Category
ezhuthu: Ezhuthu
freqBand: Freqband
freqRank: Freqrank
length: Length
sources: Sources
word: Word
}
