# Journeys

**Last Updated**: 2026-07-29

The Journey Mode, defined once. A **Journey** is a [Mode](modes.md) (`modeId` = `journey`) whose Session is a **curated, ordered path of levels** - the winding-path map on the home screen - so different players can take different routes through the same [Games](games.md). This page is the single definition of the term; every other doc links here.

## What a Journey is

Where [Daily](modes.md) is calendar-bound and Infinite is endless, a Journey is a hand-authored sequence: an ordered list of nodes, each node a puzzle (of some Game, at some difficulty), walked in order. It is the "level-based, not endless" shape that casual games use to pace difficulty and hand-craft moments (Palm). Clearing a node unlocks the next; the player's position on the path is their progress.

## The winding-path home

A Journey's home-screen chrome is the **winding-path map**: numbered nodes along a path, past nodes marked done, the current node highlighted, future nodes locked, and a small mascot guide (a Tamil letter with eyes is the standing motif). The map is chrome - it lives in the [shell](ui-shell.md), not in any Game - and it is themeable per Journey through the design system's theme axis ([design-system.md](design-system.md)).

## The journey definition

A Journey is data: a **journey definition** names an ordered set of nodes, a theme, and an unlock rule. It is a persisted surface with its own schema (`journey`) - contracts before logic, see [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md). Because a Journey is just curated data over the existing Game registry, adding a themed path (a Beginner's Ladder, a Sangam-words set, a place-names set) is authoring content, not writing an engine. Which Journeys are enabled is config-driven ([config.md](config.md)).

## The headline Journey: Word Ladder

The clearest Journey to model is a **[Word Ladder](games.md)** path (the "one more letter" reference): start from a short word; each rung adds exactly one ezhuthu and may rearrange all of them to form the next valid word, over an increasingly long chain. The completion moment shows a small stats row - elapsed TIME, first-try rungs (INSTINCT), wrong submissions (RETRIES), and consecutive-day STREAK - plus a share card and a countdown to the next puzzle.

- **Tamil adaptation.** A rung adds one **ezhuthu** and rearranges ([core-loop.md](core-loop.md)). Reachability - does a one-ezhuthu-add path exist between consecutive words? - is computed and validated **at build time** in `backend/`, so the browser only ever plays a proven-valid ladder. Tamil word density at short lengths was the named risk and the measurement retired it: the served set holds 6,218 distinct four-rung climbs, so no curated seed list was needed ([games.md](games.md)).
- **Stats mapping.** TIME, INSTINCT, RETRIES, and STREAK are all derivable from the standard [telemetry](telemetry.md) events - no new persistence beyond the save record and the streak ([difficulty-and-scoring.md](difficulty-and-scoring.md)).

The countdown and the mascot are **shell-level** and reused by every Game a Journey hosts.

### Where the stats row and the share card actually landed (Row 16)

They landed in the Game (`frontend/src/games/word-ladder/ShareCard.svelte`), not in the shell, and that is a correction to the sentence this page used to carry. The reason is the gate rather than the pixels: the SessionRunner clears the stage the instant a Game reports `puzzle.completed`, so a card the shell draws afterwards is a card drawn over a puzzle that is already gone - and the ladder is the one board whose result has to WAIT for a tap, because a share moment on a timer is one nobody can share. Owning the card lets the Game hold the report back until the player taps through.

Nothing about the stats is bespoke: they are read off the emitted event stream by a pure function, which is exactly the mapping this page specified, and the derivation is a Game-agnostic 40 lines that a second Game with a completion moment can lift. What is bespoke is only the ladder's own marks - one glyph per rung, by how it was resolved. The card makes **no network call of any kind** (Holy Law #1); a share endpoint or a server-rendered image was rejected on that ground alone.

## Design rationale

Journey is defined as a Mode (not a third axis) so the winding path is expressible as a curated ordered Session over the existing Game registry - see the decision record in [modes.md](modes.md). Keeping the definition on this one page (rather than splitting it across `modes.md` and a Word-Ladder doc) honours the one-definition rule (Holy Law #4). Authority: Palm ([../../.github/agents/palm.agent.md](../../.github/agents/palm.agent.md)) on the path shape; Fowler ([../../.github/agents/fowler.agent.md](../../.github/agents/fowler.agent.md)) on the Mode framing.

## See also

- [modes.md](modes.md) - the Mode contract and the decision that Journey is a Mode.
- [games.md](games.md) - the Games a Journey sequences, including Word Ladder.
- [core-loop.md](core-loop.md) - the ezhuthu unit a ladder rung adds.
- [difficulty-and-scoring.md](difficulty-and-scoring.md) - the streak and stats a Journey shows.
- [ui-shell.md](ui-shell.md) - the shell that draws the winding-path home.
- [design-system.md](design-system.md) - the per-Journey theme axis.
- [config.md](config.md) - which Journeys are enabled.
- [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) - the `journey` definition schema.
