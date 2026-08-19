# Games

**Last Updated**: 2026-07-29

The catalog of Game mechanics and the contract every Game honours. A **Game** (`gameId`) is the verb - the puzzle mechanic. It is one of the two orthogonal axes of a play session (the other is the [Mode](modes.md)); the content it draws from is a [Pack](#pack). The verb itself is defined once in [core-loop.md](core-loop.md); this page catalogs its six concrete forms.

## The Game contract

Every Game is a **pure mechanic**. It:

- receives a `payload` (its puzzle data) plus a `GameContext` (the bus, logger, and config it needs), and nothing more;
- renders into the `stage` slot only (never the chrome - see [ui-shell.md](ui-shell.md));
- emits the standard [telemetry](telemetry.md) events (`puzzle.started`, `puzzle.attempt.submitted`, `puzzle.hint.used`, `puzzle.completed`, `puzzle.abandoned`) - which is what "wires it up"; there is no central switch statement;
- never reads global config beyond its payload and context, and never writes storage directly (the shell owns persistence);
- round-trips its state (`getState` / `restoreState`) so a mid-puzzle reload is recoverable ([core-loop.md](core-loop.md));
- may carry an optional ordered `hints` array (`{ kind, text, cost }`).

Each Game's puzzle `payload` is a persisted surface with its own schema (`<gameId>-puzzle`) - contracts before logic, see [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md). Each Game lands with its own code row; this doc fixes the vocabulary those rows build to.

## The catalog

The `gameId` values are the locked identifiers used in code, schemas, config, and UI copy. The Tamil column holds **working names** - display titles that need a native-speaker pass before they land in `config/copy.json` (they are copy, never identifiers; see [config.md](config.md)). Tamil script here is content, not punctuation.

| `gameId` | Tamil (working name) | Mechanic | Tamil-specific note |
| --- | --- | --- | --- |
| `word-ladder` | சொல் ஏணி (add one ezhuthu) | Add exactly one ezhuthu and rearrange to reach the next valid word. | Rungs are counted in ezhuthu, not codepoints. The reachability graph is proven at build time so the browser only plays a valid ladder. |
| `anagram` | சொல் கலைப்பு | Unscramble ezhuthu tiles into the target word. | The proven starter mechanic, ported from the prior generation. |
| `missing-letters` | இடைவெளி நிரப்பு | Fill the blanked ezhuthu of a partially shown word. | A blank is a whole ezhuthu, never half a cluster. The blanks are POSITIONS in the answer's segmentation, so the payload ships no ezhuthu array of its own. |
| `wordle` | சொல் யூகி | Guess an N-ezhuthu word in N tries; per-tile present / correct / absent feedback. | "Letter" = ezhuthu; the keyboard is an ezhuthu picker (uyir + mei + uyirmei). |
| `word-search` | சொல் தேடல் | Trace hidden words in an ezhuthu grid, 8 directions. | Grid cells are ezhuthu; tracing is drag or keyboard. |
| `crossword` | சொற்கட்டம் | Fill a mini crossword from clues; entries interlock on shared ezhuthu. | Interlock is on ezhuthu identity. A build-time solver in `backend/` places the words. |

## missing-letters

A word is printed with one or more whole ezhuthu punched out of it, and a bank of ezhuthu sits below. Tap one and it drops into the next hole; tap a filled hole to take it back. The board auto-submits the moment the last hole fills, so there is no check button and nothing to read before the first move.

Three things are true of it that are not true of the anagram, and each one shapes the contract:

- **There is no Tamil keyboard, so the bank is the input method.** Its size is therefore a balance number rather than a layout preference - it is the odds a player who knows nothing still guesses right inside the allowed attempts - and it lives in `config/daily-generator.json` as `choiceCount` (Holy Law #6).
- **The generator CHOOSES the mask.** An anagram is handed the tiles it must work with; this Game gets to pick which ezhuthu to hide, so it scores every candidate mask against the served set and takes one no other served word answers. See [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) for the measured trade-off and what happens on the words where no such mask exists.
- **The first ezhuthu can never be a hint.** The board has already printed every ezhuthu it is not hiding, so that rung is either a fact on the screen or the answer itself. Its ladder is two rungs - a category, then a meaning - where the anagram's is three.

Scoring counts HOLES, not the word's length: this Game hands the player most of the answer, so a one-blank win is worth 20 against the anagram's 40 to 60 ([difficulty-and-scoring.md](difficulty-and-scoring.md)).

## Pack

A **Pack** (`packId`) is the content and language pack a Game draws from. It is a data dimension, orthogonal to the Game and the Mode. Today there is one Pack, `ta-core` (Tamil); other Packs may follow. A play session is **one Mode x one-or-more Games x a Pack**.

## Why these six

The set spans the casual word-game space with one shared atom (the ezhuthu) and one shared contract, so a second Game costs a mechanic and a schema, not a new engine. The first Game to ship is `anagram` under [Daily](modes.md) - a proven mechanic that exercises the whole shell (payload load, verb, submit, save, share) end to end. Word Ladder is the headline [Journey](journeys.md) but ships after the build-time ladder graph exists. Authority: Palm ([../../.github/agents/palm.agent.md](../../.github/agents/palm.agent.md)) on the verb-per-Game; Fowler on the pure-mechanic contract.

## See also

- [core-loop.md](core-loop.md) - the shared verb and the ezhuthu unit.
- [modes.md](modes.md) - how a Mode frames one or more Games into a session.
- [journeys.md](journeys.md) - the curated path the Word Ladder headlines.
- [difficulty-and-scoring.md](difficulty-and-scoring.md) - per-Game difficulty and the scorer.
- [ui-shell.md](ui-shell.md) - the `stage` slot a Game renders into.
- [telemetry.md](telemetry.md) - the standard events a Game emits.
- [config.md](config.md) - per-Game tunables and display copy.
- [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) - the per-Game puzzle payload schemas.
