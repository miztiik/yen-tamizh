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
export type Lexiconroot = string
/**
 * @minItems 1
 */
export type Outputs = [("ndjson" | "csv" | "sqlite"), ...(("ndjson" | "csv" | "sqlite"))[]]
export type Note = (string | null)
export type Pos = ([("adjective" | "adverb" | "conjunction" | "determiner" | "interjection" | "noun" | "numeral" | "particle" | "postposition" | "pronoun" | "verb"), ...(("adjective" | "adverb" | "conjunction" | "determiner" | "interjection" | "noun" | "numeral" | "particle" | "postposition" | "pronoun" | "verb"))[]] | null)
export type Reject = (("notAWord" | "multiWordUnit" | "noTamilCounterpart" | "notAPosLabel") | null)
export type Wordclassevidence = ([("inflected" | "colloquial" | "properNoun" | "loanword" | "boundStem" | "sandhiArtifact" | "suspectedTypo"), ...(("inflected" | "colloquial" | "properNoun" | "loanword" | "boundStem" | "sandhiArtifact" | "suspectedTypo"))[]] | null)
/**
 * @minItems 1
 */
export type Sources = [LexiconSource, ...(LexiconSource)[]]
export type Attestationtier = (("lexicographic" | "enumerative") | null)
export type Bytes = number
export type Categoryfield = (string | null)
export type Countcolumn = (number | null)
export type Countfield = (string | null)
export type Delimiter = (string | null)
export type Elementkind = (("object" | "string") | null)
export type Enabled = boolean
export type Hasheader = boolean
export type Id = string
export type Kind = ("delimited" | "json-array" | "jsonl" | "mediawiki-xml")
export type Name = string
export type Note1 = (string | null)
export type Origin = string
export type Pagenamespace = (number | null)
export type Path = string
export type Posfield = (string | null)
export type Precedence = number
export type Role = ("authority" | "formEvidence" | "frequency" | "category" | "authored")
export type Rootkey = (string | null)
export type Sha256 = string
export type Wordcolumn = (number | null)
export type Wordfield = (string | null)
export type Version1 = string

/**
 * The declarative lexicon source registry, read by every stage.
 */
export interface LexiconSources {
categoryAliases?: Categoryaliases
changelog: Changelog
lexiconRoot: Lexiconroot
outputs: Outputs
posAliases: Posaliases
sources: Sources
version: Version1
}
export interface Categoryaliases {
[k: string]: string
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
export interface Posaliases {
[k: string]: PosAlias
}
/**
 * Where one raw source POS tag lands.
 * 
 * The census tags are not all parts of speech, so one destination is not
 * enough. A tag routes to ``pos`` (it names a part of speech Tamil has), to
 * ``wordClassEvidence`` (it is a fact about what KIND of surface this is - a
 * proper name, a bound morpheme, a contracted form - which is the classifier's
 * input, never its verdict), or it carries an explicit ``reject`` naming why
 * it yields no part of speech. A tag may route to both of the first two: a
 * plural-noun tag carries two facts and each goes to its own home.
 */
export interface PosAlias {
note?: Note
pos?: Pos
reject?: Reject
wordClassEvidence?: Wordclassevidence
}
/**
 * One registered source: where its bytes are, what it may assert, how to read it.
 */
export interface LexiconSource {
attestationTier?: Attestationtier
bytes: Bytes
categoryField?: Categoryfield
countColumn?: Countcolumn
countField?: Countfield
delimiter?: Delimiter
elementKind?: Elementkind
enabled?: Enabled
hasHeader?: Hasheader
id: Id
kind: Kind
name: Name
note?: Note1
origin: Origin
pageNamespace?: Pagenamespace
path: Path
posField?: Posfield
precedence: Precedence
role: Role
rootKey?: Rootkey
sha256: Sha256
wordColumn?: Wordcolumn
wordField?: Wordfield
}
