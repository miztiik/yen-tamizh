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
export type Minbreadth = number
export type Minngram = number
export type Minorthotactic = number
export type Evidencepriority = ("inflected" | "colloquial" | "properNoun" | "loanword" | "boundStem" | "sandhiArtifact" | "suspectedTypo" | "notAWord")[]
export type Headwordminorthotactic = number
export type Maxezhuthu = number
export type Mindistinctezhuthu = number
export type Rejectnontamil = boolean
export type Maxngram = number
export type Minneighbour = number
/**
 * @minItems 1
 */
export type Nannulsources = [string, ...(string)[]]
export type Maxeditdistance = number
export type Prunebreadth = number
export type Order = number
export type Smoothing = number
export type Clusterweight = number
export type Finalweight = number
export type Granthapenalty = number
export type Initialweight = number
/**
 * @minItems 1
 */
export type Verbformsources = [string, ...(string)[]]
export type Version1 = string

/**
 * The word-hood layer's knobs. Read by ENRICH, never by the browser.
 */
export interface Wordhood {
changelog: Changelog
classifier: ClassifierSettings
nannulSources: Nannulsources
neighbour: NeighbourSettings
ngram: NgramSettings
orthotactic: OrthotacticWeights
verbFormSources: Verbformsources
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
 * How the eight signals become exactly one ``wordClass`` (Row 9).
 * 
 * ``evidencePriority`` orders the classes a source may assert when two sources
 * assert different ones. It must be a permutation of the whole evidence
 * vocabulary - a partial list would leave an assertion with no rank, and the
 * verdict would then depend on which fact SQLite happened to return first.
 * 
 * What makes a listing an ENTRY is NOT here. It is the asserting source's
 * declared ``attestationTier`` in ``config/lexicon-sources.json``, because
 * what a source's unit IS is a property of the source and cannot be recovered
 * from one row of it (Row 9a).
 */
export interface ClassifierSettings {
discovery: DiscoveryProfile
evidencePriority: Evidencepriority
headwordMinOrthotactic: Headwordminorthotactic
notAWord: NotAWordProfile
typo: TypoProfile
}
/**
 * What a modern word the dictionaries MISSED looks like (Row 9).
 * 
 * A surface that is orthotactically clean, seen by several independent
 * sources, sits well under the sequence model and is still unattested is not
 * junk - that profile is a real word the acquired dictionaries are simply too
 * old or too thin to hold. It goes to the enrichment queue, and the reason the
 * profile is written down at all is that it must never be read as a
 * misspelling on the way there.
 */
export interface DiscoveryProfile {
minBreadth: Minbreadth
minNgram: Minngram
minOrthotactic: Minorthotactic
}
/**
 * What makes a surface not a Tamil word at all (Row 9a).
 * 
 * The classifier's PRECONDITION, weighed before any signal and before any
 * source assertion. A statement about the STRING outranks a statement about
 * the word it is not: a scraped paragraph tagged as a name is still a scraped
 * paragraph, and letting the tag win is how junk comes to wear a real class.
 * 
 * All three are thresholds rather than facts about Tamil, so all three are
 * config (Holy Law #6). The letter rules that say which shapes Tamil BUILDS
 * stay in ``ezhuthu/word_shape.py``; these say when a string is not a
 * candidate for those rules to judge.
 * 
 * ``maxEzhuthu`` is a length ceiling. Tamil compounds freely, so there is no
 * grammatical bound to appeal to - what is bounded is the length beyond which
 * every surface inspected was a scrape that lost its spaces, and the longest
 * in the real store runs to 1,212 ezhuthu.
 * 
 * ``minDistinctEzhuthu`` applies only to a surface of more than one ezhuthu:
 * a one-ezhuthu word obviously holds one distinct ezhuthu and is a perfectly
 * ordinary Tamil word. What it rejects is the same character repeated - a
 * keyboard artifact or a run of the aytham, never a word.
 * 
 * ``rejectNonTamil`` is what a unit that is not an ezhuthu at all - Latin, a
 * digit, a space, punctuation - costs. It is a knob rather than a constant
 * because it is the one clause that could reasonably be turned off: a project
 * that wanted to keep transliterations as their own class would set it false
 * and get the Row 9 behaviour back, where such a surface is judged by
 * orthography and lands in ``suspectedTypo``.
 */
export interface NotAWordProfile {
maxEzhuthu: Maxezhuthu
minDistinctEzhuthu: Mindistinctezhuthu
rejectNonTamil: Rejectnontamil
}
/**
 * What a misspelling looks like (Row 9).
 * 
 * ``minNeighbour`` is the reciprocal edit distance at which a real word is
 * close enough that this surface is probably a slip of it: one means a
 * headword exactly one ezhuthu away, a half means two. There is deliberately
 * no breadth bound here - the neighbour signal is only MEASURED where Row 8's
 * prune admitted the surface, so a widely-seen surface arrives carrying NULL
 * and the profile cannot fire on it. Restating the bound would let the two
 * drift apart.
 * 
 * ``maxNgram`` is the other half, and it is what stops the profile accusing
 * ordinary Tamil. A near neighbour ALONE is not evidence of a slip: an
 * agglutinative language generates real forms one ezhuthu apart by the
 * thousand. What a typo also is, is IMPROBABLE - and the sequence model is the
 * signal that says so. It is a separate knob from the discovery floor even
 * where the two happen to share a value, because they answer different
 * questions and tuning one must not silently move the other.
 */
export interface TypoProfile {
maxNgram: Maxngram
minNeighbour: Minneighbour
}
/**
 * How far the nearest-headword search looks, and what it skips (Row 8).
 * 
 * ``maxEditDistance`` is capped at two by the schema itself. It is the one
 * knob here whose ceiling is not a preference: the deletion neighbourhood
 * grows two and a half times and the pass grows from minutes to hours at
 * three, so a config typo has to fail on load rather than run all afternoon.
 * The pipeline asserts the same bound again before it builds anything.
 * 
 * ``pruneBreadth`` is the number of distinct sources at which a surface stops
 * being queried at all. The signal's only consumer is the ``suspectedTypo``
 * verdict, and a surface several independent sources agree on is not one - so
 * querying it would buy nothing and cost the largest pass in the stage.
 */
export interface NeighbourSettings {
maxEditDistance: Maxeditdistance
pruneBreadth: Prunebreadth
}
/**
 * How the ezhuthu sequence model is fitted (Row 8).
 * 
 * ``order`` is how much context a prediction sees. Two is a bigram and models
 * almost nothing about Tamil's cluster rules; five over a 250-ezhuthu alphabet
 * is mostly unseen contexts falling back to the smoothing mass, which measures
 * the model rather than the word. Three is the default and the range is closed
 * around what is defensible.
 * 
 * ``smoothing`` is the count added to every possible continuation before the
 * probabilities are taken. It has to be positive: at zero a single ezhuthu the
 * dictionary never happened to follow makes the whole word impossible, and an
 * impossible word has no comparable score.
 */
export interface NgramSettings {
order: Order
smoothing: Smoothing
}
/**
 * What each orthotactic defect costs the signal's score.
 * 
 * The score is ``1.0`` minus the weights of the rules a surface breaks, so a
 * clean word scores 1 and one that breaks everything scores 0. Three weights
 * rather than one, because the defects are not interchangeable: a surface that
 * cannot even OPEN like a Tamil word is a loanword or a fragment, while one
 * that merely ends wrong is usually a sandhi artifact, and a classifier that
 * wants to tell those apart needs them priced apart.
 * 
 * ``granthaPenalty`` defaults to zero on purpose. Grantha letters were
 * borrowed to write Sanskrit and foreign sounds, so carrying one is positive
 * evidence of a LOANWORD rather than a defect, and pricing it as damage would
 * tell the classifier the opposite of what the fact means. It is a knob rather
 * than a constant so that judgement stays reviewable in config.
 */
export interface OrthotacticWeights {
clusterWeight: Clusterweight
finalWeight: Finalweight
granthaPenalty: Granthapenalty
initialWeight: Initialweight
}
