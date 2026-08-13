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
export type Capped = number
export type Invalidwordfinal = number
export type Masterrows = number
export type Outsideband = number
export type Outsidelength = number
export type Rowskept = number
export type Withoutcoanagram = number
export type Gameid = string
/**
 * @minItems 1
 */
export type Bands = [("common" | "mid" | "rare"), ...(("common" | "mid" | "rare"))[]]
export type Maxlength = number
export type Maxwords = (number | null)
export type Minlength = number
export type Requirecoanagram = boolean
export type Requirevalidwordfinal = boolean
export type Generatedat = string
export type Path = string
export type Rows = number
export type Sha256 = string
export type Version1 = string
export type Version2 = string
/**
 * @minItems 1
 */
export type Ezhuthu = [string, ...(string)[]]
export type Freqband = ("common" | "mid" | "rare")
export type Firstezhuthu = string
export type Length = number
export type Word = string
export type Words = GameWord[]

/**
 * One Game's derived wordlist, with the master and selection that made it.
 */
export interface GameWordlist {
changelog: Changelog
counters: DerivedCounters
gameId: Gameid
selection: DerivedSelection
source: DerivedSource
version: Version2
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
 * The reconciliation ledger for one derive run (no silent drops).
 */
export interface DerivedCounters {
capped: Capped
invalidWordFinal?: Invalidwordfinal
masterRows: Masterrows
outsideBand: Outsideband
outsideLength: Outsidelength
rowsKept: Rowskept
withoutCoAnagram: Withoutcoanagram
}
/**
 * Which master words a derived set keeps. Every knob is tunable data.
 * 
 * ``minLength`` / ``maxLength`` count EZHUTHU, not code points - the unit every
 * Game plays in (Row 6). ``bands`` names the ``freqBand`` values a player is
 * expected to know. ``requireCoAnagram`` keeps only words whose ezhuthu
 * multiset is shared with at least one other master word, which is what
 * guarantees an unscramble has real tension. ``requireValidWordFinal`` drops
 * tokens that do not END the way a Tamil word ends (the corpus is scraped, so
 * it carries sandhi artifacts and transliterated loanwords that no Tamil
 * speaker would accept as an ANSWER); it applies to the co-anagram partner
 * too, so tension can only come from another real word. ``maxWords`` caps the
 * committed artifact (``null`` means uncapped); a derived set is a build
 * artifact in git, so an uncapped one is an unbounded commit.
 * 
 * This model is shared: the registry declares it and the emitted wordlist
 * echoes back the selection that produced it, so a reviewer reading a diff can
 * see which knob moved. Defining it once is why the two cannot disagree.
 */
export interface DerivedSelection {
bands: Bands
maxLength: Maxlength
maxWords?: Maxwords
minLength: Minlength
requireCoAnagram?: Requirecoanagram
requireValidWordFinal?: Requirevalidwordfinal
}
/**
 * The exact master wordlist a derived set was cut from.
 */
export interface DerivedSource {
generatedAt: Generatedat
path: Path
rows: Rows
sha256: Sha256
version: Version1
}
/**
 * One word a Game may build a puzzle from.
 */
export interface GameWord {
ezhuthu: Ezhuthu
freqBand: Freqband
hints?: (GameWordHints | null)
word: Word
}
/**
 * The honest, derivable hint material for one word.
 * 
 * Both fields are recomputed from ``ezhuthu`` on every rebuild and validated
 * against it, so precomputing them cannot drift - the same bargain
 * ``MasterWord.length`` makes in the master list.
 * 
 * A category hint is deliberately absent. The master's category tags are
 * English source labels, and a Tamil category name is player-facing COPY,
 * which lives in ``config/copy.json`` and never inside a dataset. Inventing
 * Tamil category strings here would be a dishonest field.
 */
export interface GameWordHints {
firstEzhuthu: Firstezhuthu
length: Length
}
