# Telemetry

**Last Updated**: 2026-07-29

The structured-event vocabulary: the envelope every event carries, the standard event names, and the rule that there is no network sink. This is the debugging and replay backbone, and it is the *same* bus that drives the view ([core-loop.md](core-loop.md)) - so a [Game](games.md) that emits the standard events is observable for free. "Telemetry" here means a local, structured log; it is not a runtime analytics SDK, which is a project non-goal ([principles.md](principles.md)).

## The envelope

Every event is one flat, serializable payload with a fixed envelope:

`{ ts, src, v, session, name, level, ctx, data }`

| Field | Meaning |
| --- | --- |
| `ts` | Timestamp of the event. |
| `src` | The subsystem that emitted it (a Game, a Mode, the runner, the pipeline). |
| `v` | Envelope version, so a reader can evolve. |
| `session` | The play-session id the event belongs to. |
| `name` | The event name (from the standard set below). |
| `level` | Severity / log level. |
| `ctx` | Stable context (`modeId`, `gameId`, `packId`, day). |
| `data` | The event-specific payload. |

The envelope is a persisted surface with its own schema (`event-envelope`), stamped and evolved like any contract - see [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md). This page fixes the shape and names; the schema row owns the concrete field types.

## Standard event names

A Game or Mode is "wired up" the moment it emits these - there is no central switch statement to edit.

**Runtime (frontend):**

- `app.started`
- `puzzle.started` / `puzzle.attempt.submitted` / `puzzle.hint.used` / `puzzle.completed` / `puzzle.abandoned`
- `mode.session.started` / `mode.session.completed`
- `streak.updated`

**Build-time (`backend/` pipeline, emitted as stdout JSON lines):**

- `pipeline.stage.started` / `pipeline.stage.completed` / `pipeline.stage.failed`
- `puzzle.generated`
- `bank.updated`

The runtime names are the source of the derived stats in [difficulty-and-scoring.md](difficulty-and-scoring.md); the build-time names make a generator run auditable ([../architecture/overview.md](../architecture/overview.md)).

## No network sink

There is no runtime call home (Holy Law #1):

- In **development**, events log to the console.
- In **production**, events ring-buffer in memory and are dumped on demand via `window.__yt_dump()` for debugging - never sent anywhere.

Because every event is a plain serializable payload, a captured buffer is a fixture: it can be logged, replayed, and asserted against in tests with no mocks (Holy Law #7). Which events emit and at what level is config-driven where it matters ([config.md](config.md)).

## See also

- [core-loop.md](core-loop.md) - the bus these events share with the view.
- [games.md](games.md) - the Game contract that emits the runtime events.
- [modes.md](modes.md) - the session events a Mode emits.
- [difficulty-and-scoring.md](difficulty-and-scoring.md) - the stats derived from these events.
- [config.md](config.md) - the emit / level knobs.
- [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) - the `event-envelope` schema.
- [../architecture/overview.md](../architecture/overview.md) - where the build-time events fit the pipeline.
- [../../CLAUDE.md](../../CLAUDE.md) - the no-runtime-telemetry-SDK non-goal (section 0a).
