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
export type Functionwords = [DeniedWord, ...(DeniedWord)[]]
export type Reason = string
export type Word = string
export type Note = string
/**
 * @minItems 1
 */
export type Propernouns = [DeniedWord, ...(DeniedWord)[]]
export type Version1 = string

/**
 * The words no Game may serve, split by WHY they are unservable.
 * 
 * The split is not decoration. A function word is off the board because it is
 * grammar rather than vocabulary, and that judgement is stable for the life of
 * the language. A proper noun is off the board because a corpus made a name
 * frequent, and that judgement follows whichever corpora are staged - so the
 * two arrays age differently and a reviewer needs to know which kind of
 * argument an entry is making before deciding whether it still holds.
 * 
 * ``note`` is REQUIRED. The words deliberately KEPT are the whole difference
 * between this list and the cruder rule it replaces, and a file that does not
 * say which they are is a file the next contributor will "helpfully" widen.
 */
export interface ServedDenylist {
changelog: Changelog
functionWords: Functionwords
note: Note
properNouns: Propernouns
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
 * One denied surface and the reason it may not be a puzzle answer.
 * 
 * ``reason`` is required and never rendered: it is for the reviewer deciding
 * whether the next proposed entry belongs, which is the only thing standing
 * between a curated list and a list that grows by feel. Where a word carries a
 * real dictionary sense that is NOT what its frequency counts - ``kumaar`` is
 * listed as "prince" and occurs 329,467 times because it is a surname - the
 * reason says so, so nobody re-adds it as vocabulary that was wrongly cut.
 */
export interface DeniedWord {
reason: Reason
word: Word
}
