# Modes

**Last Updated**: 2026-07-29

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
| `daily` | இன்றைய புதிர் | Today's committed playlist of N items (mix is config-driven). One streak tick per completed day. Shareable result card plus a "next puzzle in HH:MM" countdown. | A month calendar path: today highlighted, past days done or missed, future days locked. |
| `journey` | பயணம் | A curated, ordered path of levels from a journey definition; clearing a node unlocks the next. | The winding-path map with numbered nodes and a mascot guide. Defined in [journeys.md](journeys.md). |
| `infinite` | முடிவில்லா | A lazy, endless stream with anti-repeat over an LRU window (size from config); difficulty bucket is pickable. | A single "start" node and a glyph-only difficulty picker. |
| `time-trial` | நேர சவால் | As many items as fit in the configured run duration; best runs are kept locally only. | A single "start a run" node and a countdown in the header slot. |

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
