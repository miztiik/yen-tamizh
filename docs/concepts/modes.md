# Modes

**Last Updated**: 2026-08-21

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
| `infinite` | முடிவில்லா | A lazy, endless stream over a pre-generated pool, rotating the same ring of Games the Daily deals, with anti-repeat over an LRU window (size from config) and a difficulty filter the player can change mid-stream. | No menu: the card starts the stream, and the session rail carries the run counter and the three-band picker. |
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

## Infinite is a stream over a pre-generated pool

The Infinite Mode is endless, and the one thing this project cannot do is generate a puzzle at run time (Holy Law #1). "Endless" is therefore spelled out in advance: **every board the stream can ever deal is baked into the bundle** under `frontend/public/pool/<gameId>/`, one puzzle per file, with a small index beside them. The bake is `python -m yen_tamizh_backend.scripts.generate_infinite`; the boards are built by the same registry the Daily uses (`daily.BUILDERS`), so a Game gets a pool for free the moment it is registered.

The Mode reads its Games from `daily.games` - **one roster, not two**. A Game the Daily deals is a Game the stream deals, and the stream ROTATES that ring rather than emptying one pool, so an endless mode is a variety of boards instead of three hundred of the same one.

### The stream never fetches the pool

The pool is 1,765 boards and 1.39 MB, so what makes it playable on a phone is that none of it is fetched until it is played:

- **Start of a stream**: one `pool/<gameId>/index.json`, 13.8 KB raw and **1.3 KB over the wire** - an `id` and a band per item, and nothing else. A Tamil word on each line would roughly double it and tell the Mode nothing it uses.
- **Each board**: one file, 387 to 1,565 bytes (0.4 to 0.5 KB compressed).
- **Install**: nothing. The pool is runtime-cached by the service worker like the bank and the Journeys, never precached - measured, the built precache manifest is **27 entries / 397,863 bytes with the pool and 27 entries / 397,863 bytes without it**. See [../architecture/runtime/stack-and-bundle.md](../architecture/runtime/stack-and-bundle.md).

### The anti-repeat rule, and what happens when the pool runs out

`save.seenInfiniteIds` is an LRU bounded by `infinite.lruWindow` (200), kept by `StorageService` and keyed `<gameId>/<id>` because a pool id is only an ordinal inside its own Game. A board is recorded **when it is dealt, not when it is solved** - a puzzle the player abandoned has still been seen.

The Mode always prefers a board the window has not seen, taken in index order, which is not an arbitrary walk: a pool is baked in a frequency-stratified draw, so any prefix of a band is a proportional sample of how familiar its words are.

**When the window has seen every eligible board, the stream recycles the least recently seen one.** That is the documented exhaustion behaviour, and it is the only one that keeps the Mode's promise: a player who has worked through a whole band deserves the board they met longest ago, not an apology and not a dead end.

### Design rationale

`poolPerBand` is **100** and the number is arithmetic rather than taste. A stream rotating six Games at one difficulty draws from 565 distinct boards, nearly three times the 200-pick window, so a repeat inside the window is impossible rather than merely unlikely - and a player who pins one Game and one band still meets 100 boards, well over an hour, before the recycle begins. The cost is 1,371,555 bytes of boards plus 81,384 of index, the largest single addition of bytes in the repo, and it is acceptable because a phone downloads only the board it plays. Authority: Carmack ([../../.github/agents/carmack.agent.md](../../.github/agents/carmack.agent.md)) plus Palm ([../../.github/agents/palm.agent.md](../../.github/agents/palm.agent.md)).

A pool item file carries **no `version` / `changelog` stamp**, which is why its shape lives in `pool-index.schema.json`'s `$defs` rather than in a schema file of its own ([../architecture/contracts/schemas.md](../architecture/contracts/schemas.md)). Measured over the six Games the stamp is 512 to 1,196 bytes against a payload of 291 to 1,698, so stamping 1,765 files would spend roughly two fifths of the whole pool on one paragraph copied 1,765 times.

### Rejected alternatives

- **Bake the pool as the per-Game payload documents the Daily's Games already emit** (`anagram-puzzle` and its siblings), so each file validates against a registered top-level schema. Rejected on the measurement above: those schemas are `SchemaModel`s and stamp every file.
- **Price each Game's pool by BYTES rather than by boards**, which would give the wordle three times the depth of the word search (387 bytes a board against 1,565). Rejected: equal depth per Game is a property a player can feel and equal bytes is not.
- **Sixty boards per band** (830 KB). Rejected: it leaves a single-band stream 339 boards against a 200 window - still above it, but with no headroom for a Game whose bucket runs out, which the word-ladder's hard band already does at 65.
- **A second roster naming which Games have pools.** Rejected: `daily.games` is already the answer to which Games are live, and a separate list would let a Game be dealt by one Mode and not the other for no reason a player could see - or let the stream ask for a pool nobody baked.
- **Stop the stream when every eligible board has been seen.** Rejected: an endless Mode that ends is a bug with a nicer name.

## Time Trial is the same stream with a deadline

The Time Trial deals from the SAME pre-generated pool the Infinite Mode reads, rotating the same `daily.games` ring against the same `save.seenInfiniteIds` window - one pool, one anti-repeat memory, so a board met in one Mode is not new in the other. It is a new **session framing**, not a new Game and not a new dataset: the only thing it adds to a stream is an end.

A run is as many boards as fit inside `timeTrial.durationSec`, and it is scored in **boards completed**. It opens on a start card rather than on a running clock, because a countdown that begins while the first board is still being fetched charges the player for the network; the clock starts once the first board is dealt, and every board after that is dealt against a clock already running.

### The clock is derived from a monotonic delta, and driven by `requestAnimationFrame`

Two properties, and both are load-bearing:

- **Derived, never decremented.** Remaining time is `duration - (now - startedAt)` read from `performance.now()` and recomputed from scratch every frame. A counter that subtracted a frame's worth of time per frame would drift by exactly the time the browser declined to paint, so a player who switched apps would come back owing themselves the seconds they had already spent. `performance.now()` rather than the wall clock, so moving the device's time cannot lengthen or end a run.
- **`requestAnimationFrame`, never `setInterval` or `setTimeout`** (`CLAUDE.md` section 10). rAF is the browser's own frame clock: it fires in step with the paint the countdown is drawn into and costs nothing when nothing is painting.

**A hidden tab therefore freezes the readout and the run ends when the player comes back.** A browser stops delivering frames to a background tab entirely, so there is no frame in which to end. That is the behaviour worth having: the elapsed time is measured against the clock rather than against the frames the tab was given, so hiding the app buys no extra playing time - the player returns to a run that is already over. A run that ended and scored itself while nobody was watching would be the worse outcome.

The header readout is the clock's only rendering. Its accessible name is copy (`time-trial-remaining`) and its value is the digits, so the remaining time is read from the same place whether or not the last-seconds colour change is perceivable - colour is emphasis, never the channel.

### Best runs are local, and keyed by run length

A finished run is written into the save's optional `bestTimeTrialRuns` ([../architecture/contracts/schemas.md](../architecture/contracts/schemas.md)), one record per `durationSec`. The run length is a config knob, so a thirty-second sprint and a two-minute one are different contests: changing the knob starts a new record rather than invalidating the old one, and a record from one length can never beat the other. Equalling a record does not replace it - that would rewrite the date a record was set without anyone having beaten it.

### Design rationale

`timeTrial.durationSec` is **120**, the value it was minted with in Row 7, and it holds because of what the ring is: six Games deal in rotation, so two minutes is long enough that a run crosses more than one mechanic and is a test of breadth rather than of one board, and short enough that a player with three minutes finishes a whole run and sees their record move. Authority: Palm ([../../.github/agents/palm.agent.md](../../.github/agents/palm.agent.md)) plus Carmack ([../../.github/agents/carmack.agent.md](../../.github/agents/carmack.agent.md)).

The "one best per run length" rule is enforced by BUILDING the list rather than by checking it on write: JSON Schema cannot state uniqueness by key, so the invariant is a Pydantic validator on the contract and a pure function (`bestRunsWith`) that structurally cannot emit a duplicate. `StorageService` stores what it is handed, exactly as it takes the LRU window as a parameter rather than reading the config that sets it.

### Rejected alternatives

- **A global or online leaderboard.** Rejected: it needs a runtime backend and an account system, both explicit non-goals (`CLAUDE.md` section 0a). The opponent this Mode offers is the player's own last run.
- **One best run, ignoring the run length.** Rejected: `durationSec` is a knob, so a single record would be silently invalidated - or silently inflated - the first time anyone changed it.
- **A new pool baked for the sprint.** Rejected: the Time Trial asks the pool for exactly what the Infinite asks it for, and a second copy would be 1.39 MB of duplicate bytes plus a second anti-repeat window that could offer a player the board they just played.
- **Start the clock when the screen opens.** Rejected: the first board still has to be fetched, so the run would charge the player for their connection.
- **Score a run by points rather than by boards.** Rejected: the Games score on different scales, so a points total would make the sprint a test of which Games came up rather than of how fast the player is.

## Journey is a Mode, not a third axis

A **[Journey](journeys.md)** is a Mode whose Session is a curated, ordered path of levels - as opposed to Daily (calendar-bound), Infinite (endless, anti-repeat), or Time Trial (a timed sprint). It is deliberately *not* a new top-level axis: modelling it as a Mode composes cleanly with the existing Game registry and needs no new engine. The full definition, including the winding-path home and unlock rule, lives once in [journeys.md](journeys.md).

### Design rationale

Journey could have been a third top-level axis alongside Mode and Game. It is modelled as a Mode instead because a Journey is fully expressible as a curated ordered Session - the one thing a Mode already owns - so the third-axis version would add engine surface with no capability the Mode version lacks (architecture as selling options: the Mode framing forecloses nothing and costs nothing extra). Authority: Fowler ([../../.github/agents/fowler.agent.md](../../.github/agents/fowler.agent.md)) plus Palm ([../../.github/agents/palm.agent.md](../../.github/agents/palm.agent.md)).

### Rejected alternatives

- **Journey as a third axis (Mode x Game x Journey x Pack).** Rejected: it needs a new engine and a new persisted surface to express what a curated ordered Session already expresses. Authority: Fowler.

## See also

- [journeys.md](journeys.md) - the Journey Mode in full (the curated path and its home).
- [../how-to/generate-the-infinite-pool.md](../how-to/generate-the-infinite-pool.md) - baking the pool the Infinite Mode streams.
- [games.md](games.md) - the Games a Mode frames into a session.
- [core-loop.md](core-loop.md) - the verb inside every session.
- [difficulty-and-scoring.md](difficulty-and-scoring.md) - the streak and scorer a Mode drives.
- [ui-shell.md](ui-shell.md) - the shell that renders each Mode's home and session.
- [config.md](config.md) - the per-Mode knobs.
- [telemetry.md](telemetry.md) - the session events a Mode emits.
