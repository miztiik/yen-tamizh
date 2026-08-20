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
 * @minItems 2
 */
export type Choices = [string, string, ...(string)[]]
/**
 * @minItems 3
 */
export type Rungs = [LadderRung, LadderRung, LadderRung, ...(LadderRung)[]]
export type Alsovalid = ([string, ...(string)[]] | null)
export type Meaning = (string | null)
export type Word = string
export type Timelimitsec = number
export type Version1 = string

/**
 * One climb: the rungs in order, the bank they are built from, and the clock.
 * 
 * ``rungs`` are ordered from the shortest word up, and the first one is GIVEN -
 * it is the ledge the player starts on rather than a word they are asked for.
 * A ladder of two would be a single question, so three is the floor.
 */
export interface WordLadderPuzzle {
changelog: Changelog
choices: Choices
rungs: Rungs
timeLimitSec: Timelimitsec
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
 * One step of the climb: the word, what it means, and what else reaches it.
 * 
 * ``meaning`` is resolved at bake time and shown FREE beside the rung once the
 * player has climbed it (the Row 14 rule that a solved word explains itself).
 * It rides the RUNG rather than the puzzle because a ladder asks for several
 * words at once and the session summary carries one line per item, so this
 * board is the only place these meanings can ever be read - the same reasoning
 * the search board's ``WordSearchTarget`` made. ``translationEn`` does not
 * travel for the same reason it does not travel there: an English gloss under
 * every rung of a Tamil ladder doubles the board's height to say something the
 * paid ladder is banned from selling anyway.
 */
export interface LadderRung {
alsoValid?: Alsovalid
meaning?: Meaning
word: Word
}
