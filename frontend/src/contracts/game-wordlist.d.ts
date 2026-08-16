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
export type Lexiconrows = number
export type Outsideclass = number
export type Outsidelength = number
export type Rowskept = number
export type Withoutmeaning = number
export type Gameid = string
export type Maxlength = number
export type Maxwords = (number | null)
export type Minattestations = number
export type Minfrequency = number
export type Minlength = number
export type Mintier1Attestations = number
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
/**
 * @minItems 1
 */
export type Ezhuthu = [string, ...(string)[]]
export type Frequency = number
export type Frequencystratum = number
export type Firstezhuthu = string
export type Length = number
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
 */
export interface DerivedCounters {
belowAttestations: Belowattestations
belowFrequency: Belowfrequency
capped: Capped
lexiconRows: Lexiconrows
outsideClass: Outsideclass
outsideLength: Outsidelength
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
 * There is no ``categories`` knob either. Only about 1,290 words carry a
 * category, so gating admission on one would cut the served set to roughly a
 * thousand rows and re-create the scarcity the lexicon exists to remove.
 * Categories are a selection DIMENSION for a themed round, never an admission
 * test.
 * 
 * This model is shared: the registry declares it and the emitted wordlist
 * echoes back the selection that produced it, so a reviewer reading a diff can
 * see which knob moved. Defining it once is why the two cannot disagree.
 */
export interface DerivedSelection {
maxLength: Maxlength
maxWords?: Maxwords
minAttestations: Minattestations
minFrequency: Minfrequency
minLength: Minlength
minTier1Attestations: Mintier1Attestations
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
 * concluding the game cheated.
 */
export interface GameWord {
anagramFanOut: Anagramfanout
ezhuthu: Ezhuthu
frequency: Frequency
frequencyStratum: Frequencystratum
hints?: (GameWordHints | null)
word: Word
}
/**
 * The honest, derivable hint material for one word.
 * 
 * Both fields are recomputed from ``ezhuthu`` on every rebuild and validated
 * against it, so precomputing them cannot drift.
 * 
 * A category hint is deliberately absent. Only about 1,290 lexicon rows carry
 * a category at all, and a Tamil category name is player-facing COPY, which
 * lives in ``config/copy.json`` and never inside a dataset. Inventing Tamil
 * category strings here would be a dishonest field.
 */
export interface GameWordHints {
firstEzhuthu: Firstezhuthu
length: Length
}
