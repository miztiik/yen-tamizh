# Core Loop

**Last Updated**: 2026-08-17

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

The array is a **ladder walked in order**, not a menu chosen from, so its order IS its pricing - each rung costs at least what the one before it did, and the generator config refuses a ladder that is not ordered by non-decreasing cost. The anagram's three rungs escalate in what they RETURN as well as in what they cost, which is what makes the pricing legible without a word of explanation:

| Rung | Returns | Cost |
| --- | --- | --- |
| `category` | a bare one-word Tamil tag | 1 |
| `first-ezhuthu` | one position | 2 |
| `meaning` | a phrase | 3 |

Three rules keep the ladder honest, and all three are why a baked ladder is often SHORTER than three rungs:

- **A rung this word cannot answer is skipped, not invented.** Barely one served word in fifteen carries a category, so a ladder that demanded one would fail on the other fourteen. A two-rung ladder is the normal case, not a defect.
- **English is banned on a paid rung.** The `meaning` rung resolves a Tamil synonym, then the Tamil sense, then it is omitted. There is no English fallback: a hint the player cannot read is a hint that stole score. `translationEn` never reaches a hint, and a gloss that glues a Latin-script romanisation onto its Tamil is stepped over too.
- **A rung that would spell the answer out is dropped.** Tamil synonymy is dense enough that a gloss occasionally contains its own headword, and the dearest rung printing the answer is the ladder taking three points for nothing.

A `length` rung existed and was **deleted**: it charged a point for the tile count already on the player's screen, and offering it as one of two hints short-changed the player. `{length}` is not in the template vocabulary any more, so one config line cannot put it back.

On a themed day ([modes.md](modes.md)) the `category` rung is omitted from EVERY ladder that day, not per word. The theme is announced free in the round header, so the rung would charge for a fact already on screen - and because a missing rung shortens the ladder, a three-rung themed day beside an ordinary two-rung one would announce the theme before the player had spent anything.

## A solved word says what it means

Every baked anagram carries the word's meaning as one already-rendered Tamil phrase, shown FREE on the summary once the word is revealed - won or lost. It is resolved at bake time from the [lexicon](lexicon.md)'s synonyms and senses, so the player downloads the phrase rather than the arrays it came from. A word the lexicon has nothing to say about renders as the word alone: an empty slot would advertise a hole in the data. There is never a badge saying who wrote a meaning - marking some makes a player distrust all of them.

A puzzle also carries `alsoValid`, the other SERVED words its tiles spell. It has to be baked, because the Game cannot derive it and may not read a wordlist at runtime, and without it a player who arranges real Tamil gets a flat rejection instead of "that is a word, but not today's". True Tamil co-anagrams are rare, so most puzzles carry none.

## Cadence

One committed puzzle set per day is the ritual and the shared artifact - the [Daily](modes.md) Mode. Other Modes (Journey, Infinite, Time Trial) reframe the same Games without changing the verb. Daily reset is a fixed UTC boundary so the puzzle is device-clock-independent and share-stable.

## See also

- [games.md](games.md) - the six Games, each a concrete form of the verb.
- [modes.md](modes.md) - the four Modes that frame the loop into a session, and the themed day.
- [difficulty-and-scoring.md](difficulty-and-scoring.md) - the tuning dials, the scorer, and what a hint costs the brag.
- [lexicon.md](lexicon.md) - where a meaning, a synonym and a category come from.
- [ui-shell.md](ui-shell.md) - the screens and slots that host the loop.
- [design-system.md](design-system.md) - the declarative state-to-look mapping and animation vocabulary.
- [telemetry.md](telemetry.md) - the event bus the loop emits on.
- [../../CLAUDE.md](../../CLAUDE.md) - the contract (section 1a event-driven principles).
