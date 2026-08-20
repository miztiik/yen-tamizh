# Modes

**Last Updated**: 2026-08-20

The catalog of Modes and the contract every Mode honours. A **Mode** (`modeId`) is *how a session is framed* - the thing a player picks from the home screen. It is one of the two orthogonal axes of a play session; the other is the [Game](games.md). A session is **one Mode x one-or-more Games x a [Pack](games.md#pack)**.

## The Mode contract

Every Mode **owns session framing** and nothing else. It:

- builds a `Session` - an ordered supply of items with `next()`, `totalItems`, and a `puzzleDate` where the Mode is calendar-bound;
- reads its knobs from [config](config.md) instead of hardcoding (playlist length and mix, anti-repeat window, run duration, enabled Modes and Games);
- never renders DOM - the [shell](ui-shell.md) draws every screen; the Mode only supplies items and framing;
- emits `mode.session.started` and `mode.session.completed` via the runner ([telemetry.md](telemetry.md)).

Because the Mode never touches the DOM and the Game never touches framing, any Mode can serve any Game with no new engine - the composition is the product.

## The catalog

The `modeId` values are locked identifiers. Tamil titles are **working names** (copy, not identifiers - see [config.md](config.md)); Tamil script is content.

| `modeId` | Tamil (working name) | Session shape | Home-screen chrome |
| --- | --- | --- | --- |
| `daily` | இன்றைய புதிர் | Today's committed playlist of N items, each a different [Game](games.md) drawn from a config-driven ring. One streak tick per completed day. Shareable result card plus a "next puzzle in HH:MM" countdown. | A month calendar path: today highlighted, past days done or missed, future days locked. |
| `journey` | பயணம் | A curated, ordered path of levels from a journey definition; clearing a node unlocks the next. | The winding-path map with numbered nodes and a mascot guide. Defined in [journeys.md](journeys.md). |
| `infinite` | முடிவில்லா | A lazy, endless stream with anti-repeat over an LRU window (size from config); difficulty bucket is pickable. | A single "start" node and a glyph-only difficulty picker. |
| `time-trial` | நேர சவால் | As many items as fit in the configured run duration; best runs are kept locally only. | A single "start a run" node and a countdown in the header slot. |

## The Daily holds three different Games, chosen by a window over a ring

A Daily day is **three slots and five Games**, so which Games a day holds cannot be a fixed per-Game count: five do not fit in three slots, and a fixed mix naming three leaves the other two permanently dark. `daily.games` is therefore a **ring**, and a day takes the `playlistLength`-long window that starts at its own date. Every Game comes round within one turn of the ring, consecutive days share only the Game the window carries over, and because the ring is at least as long as the playlist - which the contract enforces - **an ordinary day never deals the same Game twice**.

The ring's ORDER decides which Games co-occur, not which comes first. That is the day's own ordering rule ([difficulty-and-scoring.md](difficulty-and-scoring.md)): the window is sorted by each Game's `dailyRank` before it is dealt. The shipped order was chosen by measuring what a day asks of a player, counted as answers per board: it produces days of 7, 7, 8, 8 and 11 answers, where declaring the ring in ramp order instead gives 3 to 11 - a day nobody notices and a day nobody finishes.

### A themed day is a SECOND ring, not the same one

A themed day draws every slot from one theme's own wordlist ([difficulty-and-scoring.md](difficulty-and-scoring.md)), which means every Game on that day must both register the theme AND be able to build a puzzle from its few hundred rows. Widening one ring to all five Games would therefore have turned every themed day off in silence - which is exactly why the mix was left at three anagrams through four Game rows.

`daily.themedGames` is the shape a themed day takes, and it is allowed to be SHORTER than the playlist. The two rings make different claims, so they get different rules:

- an ordinary day claims **variety of Games**, so it never repeats one;
- a themed day claims **its words belong together**, so it holds only the Games the theme can honestly fill and deals one of them twice rather than reaching for a Game whose slots the theme cannot fill. A theme is never padded out with an off-theme word.

Whether a theme can fill a Game is not a judgement call, it is a bake-time test - buckets, no repeats, and every drawn row actually buildable - so a themed ring that outgrows its theme costs a themed day rather than a failed bake.

### Design rationale

Measured against `themed-nature`'s 429 rows, the anagram and the missing-letters board together fill 62 consecutive themed dates without repeating a word - more than a year at one themed day a week - against 58 for the anagram alone, because two Games spread the draw across two sets of difficulty buckets rather than exhausting one. The other three Games are off the themed ring for measured reasons: the wordle's easy bucket on this theme holds TWO words, the search board draws four to six words a board and repeats an already-served one by the third themed date, and the crossword's solver cannot build a single board from a set this thin - four of the 28 easy rows, none of the 14 medium, none of 60 hard tried. Authority: Palm ([../../.github/agents/palm.agent.md](../../.github/agents/palm.agent.md)).

### Rejected alternatives

- **Raise `playlistLength` to five so every day holds every Game.** Rejected: a day of five boards including a six-answer crossword, a six-word search grid and an eight-guess wordle is a sitting rather than the burst the Daily is, and the difficulty tolerance this Mode is tuned against is stated for a day of three ("one unknown word in a day of three is the GOOD day"). It also could never run a theme, because no theme can fill all five.
- **Keep the fixed `daily.mix` and name three of the five Games.** Rejected: the two Games left out would never reach a player, which is the defect this replaces.
- **One ring for both ordinary and themed days.** Rejected and measured: with all five Games on it, no registered theme can fill a themed date, so themed days stop qualifying and the feature dies with no error and no test failure.
- **Let a themed day fall back to whichever subset of the ring the theme can fill.** Rejected: the shape a day takes is a design decision, and deriving it silently from what happened to fill means the config no longer says what a themed day is (Holy Law #6).

## Journey is a Mode, not a third axis

A **[Journey](journeys.md)** is a Mode whose Session is a curated, ordered path of levels - as opposed to Daily (calendar-bound), Infinite (endless, anti-repeat), or Time Trial (a timed sprint). It is deliberately *not* a new top-level axis: modelling it as a Mode composes cleanly with the existing Game registry and needs no new engine. The full definition, including the winding-path home and unlock rule, lives once in [journeys.md](journeys.md).

### Design rationale

Journey could have been a third top-level axis alongside Mode and Game. It is modelled as a Mode instead because a Journey is fully expressible as a curated ordered Session - the one thing a Mode already owns - so the third-axis version would add engine surface with no capability the Mode version lacks (architecture as selling options: the Mode framing forecloses nothing and costs nothing extra). Authority: Fowler ([../../.github/agents/fowler.agent.md](../../.github/agents/fowler.agent.md)) plus Palm ([../../.github/agents/palm.agent.md](../../.github/agents/palm.agent.md)).

### Rejected alternatives

- **Journey as a third axis (Mode x Game x Journey x Pack).** Rejected: it needs a new engine and a new persisted surface to express what a curated ordered Session already expresses. Authority: Fowler.

## See also

- [journeys.md](journeys.md) - the Journey Mode in full (the curated path and its home).
- [games.md](games.md) - the Games a Mode frames into a session.
- [core-loop.md](core-loop.md) - the verb inside every session.
- [difficulty-and-scoring.md](difficulty-and-scoring.md) - the streak and scorer a Mode drives.
- [ui-shell.md](ui-shell.md) - the shell that renders each Mode's home and session.
- [config.md](config.md) - the per-Mode knobs.
- [telemetry.md](telemetry.md) - the session events a Mode emits.
