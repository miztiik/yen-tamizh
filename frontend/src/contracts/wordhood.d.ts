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
