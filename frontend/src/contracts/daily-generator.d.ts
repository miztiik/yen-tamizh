/* eslint-disable */
/**
 * DO NOT EDIT. Generated from schemas/<name>.schema.json by
 * scripts/gen-contracts.mjs (Row 5 contract pipeline). To change a shape,
 * edit the Pydantic model under backend/yen_tamizh_backend/contracts/,
 * re-run the exporter, then re-run `npm run gen:contracts`.
 */

export type Bankdir = string
/**
 * @minItems 1
 */
export type Changelog = [ChangelogEntry, ...(ChangelogEntry)[]]
export type Change = string
export type Version = string
export type Why = string
export type Daysahead = number
/**
 * @minItems 1
 */
export type Games = [GameGeneration, ...(GameGeneration)[]]
export type Attempts = number
export type Choicecount = number
/**
 * @minItems 1
 */
export type Difficulties = [DifficultyBand, ...(DifficultyBand)[]]
export type Blanks = number
export type Id = string
export type Maxlength = number
export type Maxstratum = number
export type Minlength = number
export type Targets = number
export type Gameid = string
export type Gridcols = number
export type Gridrows = number
export type Cost = number
export type Kind = string
export type Template = string
export type Hints = HintSpec[]
export type Packid = string
export type Reveal = number
export type Copyslug = string
export type Wordlist = string
export type Themes = ThemedSet[]
export type Timelimitsec = number
export type Wordlist1 = string
export type Themeeveryndays = number
export type Version1 = string

/**
 * The daily engine's knobs: where the bank lands and how a day is filled.
 */
export interface DailyGenerator {
bankDir: Bankdir
changelog: Changelog
daysAhead: Daysahead
games: Games
themeEveryNDays: Themeeveryndays
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
 * How one Game turns a wordlist row into a playable puzzle.
 */
export interface GameGeneration {
attempts: Attempts
categoryLabels?: Categorylabels
choiceCount?: Choicecount
difficulties: Difficulties
gameId: Gameid
gridCols?: Gridcols
gridRows?: Gridrows
hints?: Hints
packId: Packid
reveal: Reveal
themes?: Themes
timeLimitSec: Timelimitsec
wordlist: Wordlist1
}
export interface Categorylabels {
/**
 * This interface was referenced by `Categorylabels`'s JSON-Schema definition
 * via the `patternProperty` "^[a-z][a-z0-9-]*$".
 */
[k: string]: string
}
/**
 * One difficulty bucket: the ezhuthu lengths and the familiarity it covers.
 * 
 * Difficulty is TWO-AXIS - length and familiarity - because length alone is
 * anti-correlated at both tails. A long Tamil headword is usually a compound
 * that decomposes into recognisable chunks and is EASIER than its ezhuthu
 * count suggests, while a short rare word is brutal; a length-only easy bucket
 * therefore forces the generator into the shortest words, which are
 * disproportionately literary. A 3-ezhuthu answer also has only six
 * arrangements against three attempts, so it is brute-forceable by shuffling
 * without the player ever recognising the word.
 * 
 * ``maxStratum`` is the coarsest frequency quarter the band admits, 1 being
 * the most familiar quarter of the SERVED set. Bands deliberately OVERLAP on
 * length and tile on familiarity: what separates easy from hard is mostly how
 * well the player knows the word, not how many tiles it has.
 * 
 * ``blanks`` is how many ezhuthu a band HIDES, and it is read only by the
 * Games whose mechanic hides letters. It defaults to 1 so a Game that shows
 * every tile - the anagram - never has to mention it, and so every day baked
 * before this knob existed still validates. Hiding a second ezhuthu is the
 * honest way to make a band harder without reaching for a rarer word: it
 * multiplies the guess space instead of narrowing the vocabulary.
 * 
 * ``targets`` is how many WORDS a band hides, read only by the Games whose
 * board holds more than one. It defaults to 1, which is what every other Game
 * deals. On a search board it is the main difficulty dial, and the reason is
 * an inversion worth stating: length is NOT a difficulty axis here. A longer
 * word occupies more cells and is more distinctive, so it is EASIER to spot
 * than a short one, which is the opposite of what length does to a scramble or
 * a wordle board. What makes a search harder is how many words are still
 * outstanding and how well the player knows them.
 * 
 * Where the cuts fall is a game-balance number, so it lives here rather than
 * in Python (Holy Law #6).
 */
export interface DifficultyBand {
blanks?: Blanks
id: Id
maxLength: Maxlength
maxStratum: Maxstratum
minLength: Minlength
targets?: Targets
}
/**
 * One rung of the ladder: its kind, its wording, and what it costs.
 * 
 * ``template`` is a Python format string over the CLOSED vocabulary of fields
 * the Game it is registered under can fill from a served row. The vocabulary
 * is PER GAME and lives in that Game's builder, because what counts as a hint
 * depends on the board: the anagram sells ``{firstEzhuthu}`` because its tiles
 * are shuffled and knowing which one leads is real progress, while a
 * missing-letters board has already printed every ezhuthu it is not hiding, so
 * the same field is either a fact on the screen or the answer. ``{category}``
 * and ``{meaning}`` are common to both. The rendered TEXT is per-puzzle data
 * and ships inside the puzzle payload, but the WORDING is player-facing copy,
 * so it lives here and the generator only fills in the values.
 * 
 * A template naming a field OUTSIDE its Game's vocabulary fails the bake
 * loudly; a template naming one INSIDE it that a particular row cannot fill
 * has its rung skipped for that row. Those are different mistakes: the first is
 * a typo in config, the second is the honest state of a lexicon where barely
 * one word in fifteen carries a category.
 * 
 * ``{length}`` is deliberately in NO Game's vocabulary. A rung charging for the
 * tile count already on the player's screen was deleted, and leaving the field
 * fillable would let one config line put it back.
 */
export interface HintSpec {
cost: Cost
kind: Kind
template: Template
}
/**
 * One themed wordlist this Game may run a whole day from.
 * 
 * A theme is the Daily's VARIETY mechanism, not a Mode and not a Game: three
 * unrelated anagrams are a list, three sharing a theme are a round. It costs no
 * new engine - it is one derived set cut on the ``categories`` dimension, and
 * ``wordlist`` is where that set landed.
 * 
 * ``copySlug`` names the theme's player-facing Tamil label in
 * ``config/copy.json``. The SLUG travels in the baked day, never the label: a
 * Tamil category name is copy, and copy never gets baked into a dataset where
 * it could only be changed by a rebuild.
 * 
 * A themed day is OPPORTUNISTIC. The day runs a theme only when a whole
 * playlist can be drawn from that theme's own wordlist without repeating a
 * word the bank has already served; otherwise the day is ordinary. A theme is
 * never padded out with an off-theme word, because the round's whole claim is
 * that the three words belong together.
 */
export interface ThemedSet {
copySlug: Copyslug
wordlist: Wordlist
}
