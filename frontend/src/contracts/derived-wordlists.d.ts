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
export type Masterpath = string
/**
 * @minItems 1
 */
export type Sets = [DerivedSet, ...(DerivedSet)[]]
export type Gameid = string
export type Note = (string | null)
export type Out = string
/**
 * @minItems 1
 */
export type Bands = [("common" | "mid" | "rare"), ...(("common" | "mid" | "rare"))[]]
export type Maxlength = number
export type Maxwords = (number | null)
export type Minlength = number
export type Requirecoanagram = boolean
export type Requirevalidwordfinal = boolean
export type Version1 = string

/**
 * The registry: one master in, one derived set out per registered Game.
 */
export interface DerivedWordlists {
changelog: Changelog
masterPath: Masterpath
sets: Sets
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
 * One registered per-Game derived set: who consumes it and where it lands.
 */
export interface DerivedSet {
gameId: Gameid
note?: Note
out: Out
selection: DerivedSelection
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
