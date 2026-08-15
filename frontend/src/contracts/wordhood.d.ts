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
