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
export type Rows = number
/**
 * @minItems 1
 */
export type Partitions = [LexiconPartition, ...(LexiconPartition)[]]
export type Bytes = number
export type Firstezhuthu = (string | null)
export type Firstezhuthuhex = (string | null)
export type Length = (number | null)
export type Path = string
export type Rows1 = number
export type Sha256 = string
export type Wordclass = ("headword" | "inflected" | "colloquial" | "properNoun" | "loanword" | "boundStem" | "sandhiArtifact" | "suspectedTypo" | "notAWord" | "unclassified")
/**
 * @minItems 1
 */
export type Provenance = [LexiconProvenance, ...(LexiconProvenance)[]]
export type Bytes1 = number
export type Factsout = number
export type Id = string
export type Name = string
export type Origin = string
export type Path1 = string
export type Rowsin = number
export type Sha2561 = string
export type Attestedby = ([string, ...(string)[]] | null)
export type Categories = ([string, ...(string)[]] | null)
export type Categorysource = (("attested" | "authored" | "reviewed") | null)
export type Compound = (boolean | null)
export type Definitionta = (string | null)
/**
 * @minItems 1
 */
export type Ezhuthu = [string, ...(string)[]]
export type Freqrank = (number | null)
export type Frequency = number
export type Length1 = number
export type Meaningsource = (("attested" | "authored" | "reviewed") | null)
export type Pos = ([("adjective" | "adverb" | "conjunction" | "determiner" | "interjection" | "noun" | "numeral" | "particle" | "postposition" | "pronoun" | "verb"), ...(("adjective" | "adverb" | "conjunction" | "determiner" | "interjection" | "noun" | "numeral" | "particle" | "postposition" | "pronoun" | "verb"))[]] | null)
export type Spokenratio = (number | null)
export type Synonymsta = ([string, ...(string)[]] | null)
export type Translationen = (string | null)
export type Translationensource = (string | null)
export type Word = string
export type Wordclass1 = ("headword" | "inflected" | "colloquial" | "properNoun" | "loanword" | "boundStem" | "sandhiArtifact" | "suspectedTypo" | "notAWord" | "unclassified")
export type Wordhood = ({
[k: string]: number
} | null)
export type Version1 = string

/**
 * The lexicon META document (``datasets/lexicon/lexicon.meta.json``).
 * 
 * It carries no ``words`` list. The lexicon is streamed NDJSON with no
 * in-memory row list, so the reconciliation reads ``counters.rows`` and the
 * partition table's declared counts rather than ``len(words)`` - a document
 * model holding every row could not be constructed at this size and would
 * quietly re-introduce the materialization the publisher exists to avoid.
 */
export interface Lexicon {
changelog: Changelog
counters: LexiconCounters
partitions: Partitions
provenance: Provenance
rowSchema?: (LexiconEntry | null)
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
 * The per-class ledger: every published row lands under exactly one class.
 * 
 * ``byClass`` carries a bucket for EVERY ``wordClass`` - a missing bucket and
 * a zero bucket say different things, and only one of them is a measurement.
 */
export interface LexiconCounters {
byClass: Byclass
rows: Rows
}
export interface Byclass {
[k: string]: number
}
/**
 * One published NDJSON cell, and what it holds.
 * 
 * The split keys - ``wordClass``, then ezhuthu ``length``, then the word's
 * BASE first ezhuthu - are all immutable per word, so a refresh INSERTS into a
 * cell and never reshuffles one. Only a changed ``wordClass`` moves a row, and
 * that is a reviewable semantic event. ``firstEzhuthuHex`` renders the base
 * ezhuthu as lowercase 4-digit hex so every path stays ASCII; this document is
 * what maps the hex back to the ezhuthu it stands for.
 */
export interface LexiconPartition {
bytes: Bytes
firstEzhuthu?: Firstezhuthu
firstEzhuthuHex?: Firstezhuthuhex
length?: Length
path: Path
rows: Rows1
sha256: Sha256
wordClass: Wordclass
}
/**
 * One source's contribution, and the exact bytes it contributed from.
 * 
 * ``sha256`` + ``bytes`` identify the input, so a later run can prove it read
 * the same file and CI can compare the declared set against the registry with
 * no network and no raw bytes on disk.
 */
export interface LexiconProvenance {
bytes: Bytes1
factsOut: Factsout
id: Id
name: Name
origin: Origin
path: Path1
rowsIn: Rowsin
sha256: Sha2561
}
/**
 * One lexicon row: every published fact about one Tamil surface.
 * 
 * Not a ``SchemaModel`` - see the module docstring.
 * 
 * Every sparse column is OPTIONAL and never a defaulted empty list.
 * ``model_dump(exclude_none=True)`` drops ``None`` but keeps ``[]``, so a
 * defaulted empty list writes an empty pair on every row that lacks the fact -
 * roughly 200 MB of nothing across the published set.
 * 
 * ``wordhood`` and ``freqRank`` are optional for the same reason the publisher
 * omits them: both are derived diagnostics rather than facts a source
 * asserted, ``freqRank`` is a sort of the published ``frequency`` and
 * ``wordClass`` IS ``wordhood``'s verdict, so neither can cost the project a
 * fact. The contract still types them, because the store-side renderings carry
 * them and an untyped diagnostic is an untyped diagnostic.
 */
export interface LexiconEntry {
attestedBy?: Attestedby
categories?: Categories
categorySource?: Categorysource
compound?: Compound
definitionTa?: Definitionta
ezhuthu: Ezhuthu
freqRank?: Freqrank
frequency: Frequency
length: Length1
meaningSource?: Meaningsource
pos?: Pos
spokenRatio?: Spokenratio
synonymsTa?: Synonymsta
translationEn?: Translationen
translationEnSource?: Translationensource
word: Word
wordClass: Wordclass1
wordhood?: Wordhood
}
