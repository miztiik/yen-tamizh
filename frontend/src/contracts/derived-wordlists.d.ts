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
export type Note = string
/**
 * @minItems 1
 */
export type Obscenitymarkers = [string, ...(string)[]]
/**
 * @minItems 1
 */
export type Participialsuffixes = [ParticipialSuffix, ...(ParticipialSuffix)[]]
export type Linkvowel = string
export type Minstemezhuthu = number
export type Note1 = string
/**
 * @minItems 1
 */
export type Tail = [string, ...(string)[]]
/**
 * @minItems 1
 */
export type Sets = [DerivedSet, ...(DerivedSet)[]]
export type Gameid = string
export type Note2 = (string | null)
export type Out = string
export type Categories = ([string, ...(string)[]] | null)
export type Maxlength = number
export type Maxmeaningchars = (number | null)
export type Maxwords = (number | null)
export type Minattestations = number
export type Minfrequency = number
export type Minlength = number
export type Mintier1Attestations = number
export type Pos = ([("adjective" | "adverb" | "conjunction" | "determiner" | "interjection" | "noun" | "numeral" | "particle" | "postposition" | "pronoun" | "verb"), ...(("adjective" | "adverb" | "conjunction" | "determiner" | "interjection" | "noun" | "numeral" | "particle" | "postposition" | "pronoun" | "verb"))[]] | null)
export type Requireclueablemeaning = boolean
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
servingRules: ServingRules
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
 * The two exclusions the lexicon's own data can express, applied to SERVING.
 * 
 * Both are the same KIND of statement as ``config/served-denylist.json`` -
 * the word stays in the published lexicon and is only kept off the board - and
 * both are here rather than in that file because neither needs curation: each
 * is derivable from something every published row already carries.
 * 
 * ``participialSuffixes`` demotes the participial adjective. Tamil derives one
 * from almost any noun or verb, so a form like ``mozhiyaana`` arrives with a
 * dictionary listing, a clean shape and nothing to demote it - and the
 * word-hood classifier's ``inflected`` rule cannot reach it, because that rule
 * reads collected verb-form lists and a peyareccham the lists happen not to
 * contain is invisible to it. This is a SERVING rule rather than a word-hood
 * verdict for exactly that reason: it is a statement about what makes a fair
 * puzzle answer, and the lexicon's own truth about the surface is untouched.
 * 
 * ``obscenityMarkers`` refuses a row the SOURCE ITSELF labelled. Tamil
 * lexicography writes the judgement into the gloss as a usage label -
 * ``(aabaasa-c-chol)``, ``(vasai-c-chol)`` - so the signal is already in the
 * published data and needs no list of rude words to be maintained by hand.
 * The marker matches the FIRST sense only: sense zero is the one the lexicon
 * ranks most authoritative and the one a Game displays, while a label buried
 * in sense twelve marks a marginal reading and, measured, catches ordinary
 * vocabulary whose gloss merely DISCUSSES coarse speech.
 * 
 * Both lists carry no defaults for the same reason the serving gates do not:
 * an empty rule and a forgotten one produce identical output, and the failure
 * mode worth refusing is the forgotten one.
 */
export interface ServingRules {
note: Note
obscenityMarkers: Obscenitymarkers
participialSuffixes: Participialsuffixes
}
/**
 * One participial ending, written the way Tamil actually builds it.
 * 
 * A peyareccham is not glued on as a fixed string. ``mozhi`` + ``-aana``
 * surfaces as ``mozhiyaana`` with a glide, ``azhagu`` + ``-aana`` as
 * ``azhagaana`` with the stem's final vowel replaced - so the only part that
 * is CONSTANT across every formation is the last ezhuthu or two plus the VOWEL
 * the ezhuthu in front of them carries. That is what this states:
 * 
 * - ``tail`` is the literal ezhuthu the surface ends in;
 * - ``linkVowel`` is the matra the ezhuthu immediately before ``tail`` must
 *   carry - the ``aa`` of every ``-aana`` form, the ``u`` of every
 *   ``-ulla`` one - which is what makes the match a claim about Tamil
 *   morphology rather than about a run of letters;
 * - ``minStemEzhuthu`` is how many ezhuthu must remain in FRONT of the whole
 *   pattern. It is the guard that keeps the rule off short words that merely
 *   end that way: ``vaan`` (sky) and ``kolla`` are two and three ezhuthu, and
 *   a rule with no floor would delete both.
 * 
 * A suffix is stated in ezhuthu rather than code points because the linking
 * vowel is written as a mark ON the preceding consonant, so a code-point rule
 * would be reading half a syllable.
 */
export interface ParticipialSuffix {
linkVowel: Linkvowel
minStemEzhuthu: Minstemezhuthu
note: Note1
tail: Tail
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
note?: Note2
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
 * player had solved them. ``requireClueableMeaning`` and ``maxMeaningChars``
 * go one step further and ask whether that meaning can be PRINTED as the
 * question rather than as the answer, which is what a crossword needs: a
 * definition that contains its own headword hands the word over, and one
 * carrying Latin script answers a Tamil grid in English. Both default to off,
 * because for every other Game the meaning is a reward shown after the fact
 * and its wording costs nothing. ``maxWords`` caps the committed artifact
 * (``null`` means uncapped); a derived set is a build artifact in git, so an
 * uncapped one is an unbounded commit.
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
maxMeaningChars?: Maxmeaningchars
maxWords?: Maxwords
minAttestations: Minattestations
minFrequency: Minfrequency
minLength: Minlength
minTier1Attestations: Mintier1Attestations
pos?: Pos
requireClueableMeaning?: Requireclueablemeaning
requireMeaning: Requiremeaning
wordClasses: Wordclasses
}
