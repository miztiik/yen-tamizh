# Core Loop

**Last Updated**: 2026-07-29

The game verb, the atomic unit, and the moment-to-moment loop that does not change per screen or per Game. This is the vocabulary a reader needs before any [Game](games.md) or [Mode](modes.md) makes sense. Tuning numbers live in [difficulty-and-scoring.md](difficulty-and-scoring.md); the screens that host the loop live in [ui-shell.md](ui-shell.md).

## The atomic unit: ezhuthu

The unit a player manipulates - a tile, a grid cell, a Wordle "letter", a ladder rung's added character - is the **ezhuthu** (எழுத்து, a Tamil grapheme cluster), never the Unicode codepoint. This single decision touches every layer and is the reason a naive port of an English word game breaks.

- "தமிழ்" is **3** ezhuthu (த + மி + ழ்) but more than three codepoints.
- An **uyirmei** (consonant + vowel sign, e.g. மி = ம + ி) is one ezhuthu, though it is several codepoints.
- A **mei** carries the pulli (ழ்); grantha clusters like க்ஷ are single units too.

The three ezhuthu classes are **uyir** (vowels), **mei** (consonants with pulli), and **uyirmei** (consonant + vowel). A small, well-tested **ezhuthu segmentation and reconstruction library** - shared by `backend/` (to build and validate) and the frontend (to render and score) - is the one implementation of this rule; every wordlist is stored with its ezhuthu segmentation precomputed. That library is built in its own code row; this page only fixes the vocabulary it uses.

## The verb

Across every Game the verb is one shape: **arrange or reveal ezhuthu to satisfy a target, then submit.** Anagram unscrambles ezhuthu tiles into a word; Wordle guesses an N-ezhuthu word; Word Ladder adds exactly one ezhuthu and rearranges; Missing Letters fills a blanked ezhuthu; Word Search traces ezhuthu; Crossword interlocks entries on shared ezhuthu. Tap, drag, and keyboard are the same verb across mouse and touch. Each Game states its own concrete form of the verb in [games.md](games.md).

## The loop (input -> event -> state -> render -> feedback)

The moment-to-moment loop is event-driven and non-blocking (`CLAUDE.md` section 1a). Nothing is styled imperatively:

```
player input (tap / drag / key) or timer tick
   |  emit a structured-payload event on the one bus
   v
a reducer updates the single state object
   |  Svelte reactivity toggles a state class or data-attribute
   v
the DOM node gains/loses a state class
   |  CSS transition or keyframe reacts declaratively
   v
pixels move (transform + opacity only) - the input is confirmed
```

The bus that carries these events is the same bus that feeds the [telemetry](telemetry.md) log, so a Game is observable for free. The declarative state-to-look mapping is the design system's job - see [design-system.md](design-system.md).

## Recoverability

A player plays in short bursts and may close the tab mid-puzzle. Every Game round-trips its state (a `getState` / `restoreState` pair over a serializable payload) so a mid-puzzle reload resumes exactly where the player left off. The save is browser-local and its key is recomputed on read from its value fields, never trusted from the payload (the derived-key rule in [../agents/guardrails.md](../agents/guardrails.md)). The save shape is a persisted surface with its own schema - see [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md).

## Hints are first-class

Every Game may carry an optional ordered `hints` array (each a `{ kind, text, cost }`). A hint is free and honest: it never sells a power-up (a project non-goal) and it reveals the next honest step, not a random answer. Hint visibility and cost are config-driven per Game ([config.md](config.md)); how a hint affects the brag is [difficulty-and-scoring.md](difficulty-and-scoring.md).

## Cadence

One committed puzzle set per day is the ritual and the shared artifact - the [Daily](modes.md) Mode. Other Modes (Journey, Infinite, Time Trial) reframe the same Games without changing the verb. Daily reset is a fixed UTC boundary so the puzzle is device-clock-independent and share-stable.

## See also

- [games.md](games.md) - the six Games, each a concrete form of the verb.
- [modes.md](modes.md) - the four Modes that frame the loop into a session.
- [difficulty-and-scoring.md](difficulty-and-scoring.md) - the tuning dials and the scorer.
- [ui-shell.md](ui-shell.md) - the screens and slots that host the loop.
- [design-system.md](design-system.md) - the declarative state-to-look mapping and animation vocabulary.
- [telemetry.md](telemetry.md) - the event bus the loop emits on.
- [../../CLAUDE.md](../../CLAUDE.md) - the contract (section 1a event-driven principles).
