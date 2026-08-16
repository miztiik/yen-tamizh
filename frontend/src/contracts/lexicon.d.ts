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
export type Ezhuthu = string
export type Kind = ("uyir" | "mei" | "uyirmei" | "aytham" | "other")
export type Roman = string
/**
 * @minItems 1
 */
export type Partitionkeys = [string, ...(string)[]]
/**
 * @minItems 1
 */
export type Partitions = [LexiconPartition, ...(LexiconPartition)[]]
export type Basefirstezhuthu = string
export type Bytes = number
export type Path = string
export type Rows1 = number
export type Sha256 = string
export type Wordclass = ("headword" | "inflected" | "colloquial" | "properNoun" | "loanword" | "boundStem" | "sandhiArtifact" | "suspectedTypo" | "notAWord" | "unclassified")
/**
 * @minItems 1
 */
export type Provenance = [LexiconProvenance, ...(LexiconProvenance)[]]
export type Bytes1 = number
export type Facts = number
export type Id = string
export type Name = string
export type Observations = number
export type Origin = string
export type Path1 = string
export type Sha2561 = string
export type Attestedby = ([string, ...(string)[]] | null)
export type Categories = ([string, ...(string)[]] | null)
export type Categorysource = (("attested" | "authored" | "reviewed") | null)
export type Compound = (boolean | null)
export type Definitionta = (string | null)
export type Freqrank = (number | null)
export type Frequency = number
export type Length = number
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
 * in-memory row list, so the reconciliation reads ``counters.published.rows``
 * and the partition table's declared counts rather than ``len(words)`` - a
 * document model holding every row could not be constructed at this size and
 * would quietly re-introduce the materialization the publisher exists to
 * avoid.
 */
export interface Lexicon {
changelog: Changelog
counters: LexiconCounters
ezhuthuIndex: Ezhuthuindex
partitionKeys: Partitionkeys
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
 * The two censuses, and the rule that binds them.
 * 
 * ``classified`` counts the WHOLE population the store holds, class by class,
 * including every class the publish policy withholds. ``published`` counts
 * what the files carry. Committing both is what makes "nothing was discarded"
 * a checkable statement: a withheld class is still on the record here, at its
 * real size, in the repository.
 * 
 * Publication is ALL-OR-NOTHING per class, and that is the rule the model
 * enforces. A class is published whole or not at all, so a published count
 * that is neither zero nor the classified count means rows went missing
 * between the classifier and the writer - the one failure a per-class policy
 * would otherwise hide.
 */
export interface LexiconCounters {
classified: LexiconCensus
published: LexiconCensus
}
/**
 * A per-class ledger: every counted row lands under exactly one class.
 * 
 * ``byClass`` carries a bucket for EVERY ``wordClass`` - a missing bucket and
 * a zero bucket say different things, and only one of them is a measurement.
 */
export interface LexiconCensus {
byClass: Byclass
rows: Rows
}
export interface Byclass {
[k: string]: number
}
export interface Ezhuthuindex {
[k: string]: EzhuthuIndexEntry
}
/**
 * What one partition's hex code point stands for, spelled out for a human.
 * 
 * This is where the Tamil letter and its ASCII spelling live: as correctable
 * DATA in a document a reviewer already opens, never as a path component. A
 * code point is fixed by an external standard, so it can carry an address; a
 * romanization is a judgement call, and correcting one must not rename a
 * published file.
 * 
 * ``kind`` classifies the BASE character taken alone, so a consonant reads
 * ``uyirmei`` - the bare consonant carries the inherent /a/. It is never
 * ``mei``: a mei needs a pulli, and a pulli cannot be a word's first
 * character.
 */
export interface EzhuthuIndexEntry {
ezhuthu: Ezhuthu
kind: Kind
roman: Roman
}
/**
 * One published NDJSON file, and what it holds.
 * 
 * Addressed by ``wordClass`` then ``baseFirstEzhuthu`` - the lowercase 4-digit
 * hex of the word's first code point, which is also the base its first ezhuthu
 * is built from. Both keys are immutable per word, so a refresh INSERTS into a
 * file and never reshuffles one; only a changed ``wordClass`` moves a row, and
 * that is a reviewable semantic event. Hex keeps every path ASCII;
 * ``ezhuthuIndex`` on the meta document is what maps it back to the letter.
 */
export interface LexiconPartition {
baseFirstEzhuthu: Basefirstezhuthu
bytes: Bytes
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
 * 
 * ``observations`` and ``facts`` are what the STORE can prove about the
 * source - the surfaces it contributed and the typed assertions it made. They
 * are named for what they are: no stage retains a raw input row count once the
 * extract is written, so a field called ``rowsIn`` could only ever have been
 * filled with one of these two wearing the wrong name.
 */
export interface LexiconProvenance {
bytes: Bytes1
facts: Facts
id: Id
name: Name
observations: Observations
origin: Origin
path: Path1
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
 * 
 * There is no ``ezhuthu`` column. It is ``segment(word)`` - a pure function of
 * a column that IS published - so the same omission principle covers it, and
 * it measured 35.4 B a row. Publishing it would also mint a drift surface: a
 * stored copy of a derived value can disagree with what it was derived from,
 * and the cheapest way not to have that disagreement is not to store it.
 * ``length`` stays, because it is the key selection reads and because
 * checking it against the live segmentation is what keeps a corrupt row out
 * at a fortieth of the bytes.
 */
export interface LexiconEntry {
attestedBy?: Attestedby
categories?: Categories
categorySource?: Categorysource
compound?: Compound
definitionTa?: Definitionta
freqRank?: Freqrank
frequency: Frequency
length: Length
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
