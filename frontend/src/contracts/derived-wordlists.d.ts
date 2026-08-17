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
export type Denylistpath = string
export type Lexiconpath = string
/**
 * @minItems 1
 */
export type Sets = [DerivedSet, ...(DerivedSet)[]]
export type Gameid = string
export type Note = (string | null)
export type Out = string
export type Categories = ([string, ...(string)[]] | null)
export type Maxlength = number
export type Maxwords = (number | null)
export type Minattestations = number
export type Minfrequency = number
export type Minlength = number
export type Mintier1Attestations = number
export type Pos = ([("adjective" | "adverb" | "conjunction" | "determiner" | "interjection" | "noun" | "numeral" | "particle" | "postposition" | "pronoun" | "verb"), ...(("adjective" | "adverb" | "conjunction" | "determiner" | "interjection" | "noun" | "numeral" | "particle" | "postposition" | "pronoun" | "verb"))[]] | null)
export type Requiremeaning = boolean
/**
 * @minItems 1
 */
export type Wordclasses = [("headword" | "colloquial"), ...(("headword" | "colloquial"))[]]
export type Version1 = string

/**
 * The registry: one lexicon in, one derived set out per registered Game.
 */
export interface DerivedWordlists {
changelog: Changelog
denylistPath: Denylistpath
lexiconPath: Lexiconpath
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
 * One registered derived set: who consumes it and where it lands.
 * 
 * ``gameId`` is the registry's unique key. A Game that runs themed days
 * registers more than one set - its ordinary one plus a themed variant per
 * theme - so a themed set's id names the THEME (``themed-nature``) while the
 * Game that draws it is named in ``config/daily-generator.json``, which is the
 * file that decides which set a day is filled from.
 */
export interface DerivedSet {
gameId: Gameid
note?: Note
out: Out
selection: DerivedSelection
}
/**
 * Which lexicon rows a derived set SERVES. Every knob is tunable data.
 * 
 * The lexicon is everything the pipeline knows; this is the far smaller set a
 * player is actually asked to spell. PRESENT and SERVED are different
 * populations on purpose, and these knobs are the whole difference.
 * 
 * ``wordClasses`` is an ALLOW-LIST, never a deny-list, so a word the
 * classifier could not place cannot reach a player by omission.
 * ``minLength`` / ``maxLength`` count EZHUTHU, not code points - the unit
 * every Game plays in (Row 6). ``minAttestations`` together with
 * ``minTier1Attestations`` is the composition rule: how many word-hood
 * authorities called this a word, and how many of those were dictionaries
 * rather than bare listings. Two bare wordlists agreeing is not evidence - a
 * spellchecker list is several times the size of the largest dictionary and
 * co-occurs with nearly any orthographically legal string. ``minFrequency`` is
 * the absolute floor that keeps a museum piece off the board.
 * ``requireMeaning`` keeps out words the game could not explain once the
 * player had solved them. ``maxWords`` caps the committed artifact (``null``
 * means uncapped); a derived set is a build artifact in git, so an uncapped one
 * is an unbounded commit.
 * 
 * There is deliberately no anagram knob. Whether a word's tiles also spell
 * something else is RECORDED on the emitted row as ``anagramFanOut``, never
 * used to admit or reject: a scramble of a word with no second arrangement is
 * a perfectly ordinary puzzle, and demanding a partner cut the served set by
 * two orders of magnitude while selecting for bound stems, because fragments
 * are what collide with real words.
 * 
 * ``categories`` and ``pos`` are the two SELECTION DIMENSIONS, and they are a
 * different kind of knob from the six gates above. Each keeps the rows whose
 * own set-valued column INTERSECTS the one named here - a row tagged both
 * ``birds`` and ``animals`` satisfies a selection naming either. Both are
 * OPTIONAL, and absent means the dimension is not applied at all: that is the
 * only honest default, because neither may ever gate admission for an ordinary
 * set. Fewer than 3,000 published headwords carry a category, and how far
 * ``pos`` reaches over the served set is unmeasured, so a set that named one by
 * accident would collapse to a few hundred rows or to none. A set that names
 * one is a THEMED set, drawn only on the days a whole themed playlist can be
 * filled from it.
 * 
 * This model is shared: the registry declares it and the emitted wordlist
 * echoes back the selection that produced it, so a reviewer reading a diff can
 * see which knob moved. Defining it once is why the two cannot disagree.
 */
export interface DerivedSelection {
categories?: Categories
maxLength: Maxlength
maxWords?: Maxwords
minAttestations: Minattestations
minFrequency: Minfrequency
minLength: Minlength
minTier1Attestations: Mintier1Attestations
pos?: Pos
requireMeaning: Requiremeaning
wordClasses: Wordclasses
}
