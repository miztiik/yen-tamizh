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
export type Belowattestations = number
export type Belowfrequency = number
export type Capped = number
export type Denylisted = number
export type Lexiconrows = number
export type Outsidecategories = number
export type Outsideclass = number
export type Outsidelength = number
export type Outsidepos = number
export type Rowskept = number
export type Withoutmeaning = number
export type Gameid = string
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
export type Metapath = string
export type Rows = number
export type Sha256 = string
export type Version1 = string
export type Version2 = string
export type Anagramfanout = number
export type Categories1 = ([string, ...(string)[]] | null)
export type Definitionta = (string | null)
/**
 * @minItems 1
 */
export type Ezhuthu = [string, ...(string)[]]
export type Frequency = number
export type Frequencystratum = number
export type Firstezhuthu = string
export type Length = number
export type Synonymsta = ([string, ...(string)[]] | null)
export type Translationen = (string | null)
export type Word = string
export type Words = GameWord[]

/**
 * One Game's derived wordlist, with the lexicon and selection that made it.
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
 * The reconciliation ledger for one derive run - one bucket per gate.
 * 
 * The buckets are listed in the order the identity is read, and a row that
 * fails more than one gate is counted under the first one that stopped it.
 * ``outsideClass`` comes off the lexicon's own partition table rather than
 * from reading those files: selection is an allow-list, so the derived layer
 * opens only the classes it serves, and the classes it will not serve are
 * counted from what the meta document declares about them.
 * 
 * ``outsideCategories`` and ``outsidePos`` are the two SELECTION dimensions
 * rather than gates: they are 0 unless the set asked to be themed, and they
 * are charged before the gates so a themed ledger reads as "of the rows this
 * theme covers, here is what each gate then removed" rather than burying the
 * theme's own reach inside ``outsideLength``.
 * 
 * ``denylisted`` is the curated exclusion, and it is charged LAST of the
 * row-level buckets - after every automatic gate and before the cap. A word an
 * automatic gate already stopped is charged to that gate, so this bucket
 * counts only the words the deny-list ALONE keeps off the board: how much
 * hand curation the set actually needed, which is the number that says whether
 * an entry still earns its line.
 */
export interface DerivedCounters {
belowAttestations: Belowattestations
belowFrequency: Belowfrequency
capped: Capped
denylisted: Denylisted
lexiconRows: Lexiconrows
outsideCategories: Outsidecategories
outsideClass: Outsideclass
outsideLength: Outsidelength
outsidePos: Outsidepos
rowsKept: Rowskept
withoutMeaning: Withoutmeaning
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
/**
 * The exact lexicon a derived set was cut from, pinned by content.
 * 
 * ``metaPath`` names ``lexicon.meta.json`` rather than the directory of
 * published files, and ``sha256`` digests that one document - which itself
 * carries the sha256 of every partition, so a single digest still pins a
 * partitioned input. ``rows`` is the lexicon's PUBLISHED row count, which is
 * what the ledger reconciles against.
 */
export interface DerivedSource {
metaPath: Metapath
rows: Rows
sha256: Sha256
version: Version1
}
/**
 * One word a Game may build a puzzle from.
 * 
 * ``frequency`` is the lexicon's raw count, carried through unchanged. It is
 * what ``minFrequency`` gates on and what the difficulty curve reads, and it
 * replaces the old rank-relative band: a band computed over a population where
 * thousands of rows appear zero times is a different filter wearing the same
 * name.
 * 
 * ``frequencyStratum`` is which quarter of THIS SET the row's frequency puts
 * it in, 1 being the most familiar. It is computed over the SERVED rows and
 * nothing wider - a quartile taken over millions of lexicon surfaces would say
 * nothing about the words a player is actually offered. It is the second axis
 * of difficulty: length alone is anti-correlated at both tails, because long
 * Tamil headwords are mostly compounds that decompose while short rare words
 * are brutal.
 * 
 * ``anagramFanOut`` counts how many SERVED rows share this row's ezhuthu
 * multiset, including the row itself - so a word whose tiles spell nothing
 * else carries ``1``, never ``0``. It is a recorded signal, not an admission
 * test: a Game that knows a submitted arrangement is a different served word
 * can answer "that is a word, but not today's" instead of a flat rejection,
 * which is the difference between a player learning something and a player
 * concluding the game cheated. It is a COUNT and stays one - the partner WORDS
 * are computed at bake time, because a row carrying its own partner list would
 * duplicate thousands of word lists into a committed artifact.
 * 
 * The four MEANING columns are what a hint and a summary are rendered from.
 * They are carried raw so the RULE that turns them into one display string
 * lives in the generator, where the wording already lives, rather than being
 * frozen into this artifact:
 * 
 * - ``definitionTa`` is the lexicon's FIRST sense, not its list of senses. The
 *   lexicon orders senses most-authoritative-first and a Game has exactly one
 *   display slot, so senses two and beyond have no reader here while costing
 *   4.89 MB across the served set - a build artifact holding 34 senses so that
 *   one can be shown is bytes for nothing.
 * - ``synonymsTa`` travels WHOLE, because it is not a ranked list: every
 *   member is an equally correct answer to "what does this mean", so there is
 *   no principled first element to keep and no principled remainder to drop -
 *   and the generator reads down it, because a synonym that spells out the
 *   answer or carries a Latin-script romanisation cannot be sold as a hint.
 * - ``categories`` are the lexicon's own English slugs. The Tamil a player
 *   reads is hint WORDING and lives in ``config/daily-generator.json`` beside
 *   the templates, never here: baking a Tamil label into a dataset would mean
 *   correcting a word by rebuilding the set.
 * - ``translationEn`` is carried for the summary's demoted second line. It is
 *   never a hint: a paid rung the player cannot read is a rung that stole
 *   score, so the meaning rung is omitted rather than answered in English.
 */
export interface GameWord {
anagramFanOut: Anagramfanout
categories?: Categories1
definitionTa?: Definitionta
ezhuthu: Ezhuthu
frequency: Frequency
frequencyStratum: Frequencystratum
hints?: (GameWordHints | null)
synonymsTa?: Synonymsta
translationEn?: Translationen
word: Word
}
/**
 * The honest hint material a word's own SPELLING yields.
 * 
 * Both fields are recomputed from ``ezhuthu`` on every rebuild and validated
 * against it, so precomputing them cannot drift.
 * 
 * ``length`` no longer feeds a hint - a rung that charges for the tile count
 * already on screen was deleted - but it stays as the cheapest integrity check
 * the row has: it is validated against the live segmentation, so a row whose
 * parts and count disagree can never reach a generator.
 * 
 * What a word MEANS is not spelling, so it is not here: those fields sit on
 * ``GameWord`` itself, where the generator resolves them into rendered text.
 */
export interface GameWordHints {
firstEzhuthu: Firstezhuthu
length: Length
}
