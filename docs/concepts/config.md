# Config

**Last Updated**: 2026-07-29

Where tunable behaviour and player-facing copy live, and the rule that separates a knob from an identifier. Config-driven with sane defaults is a project principle ([principles.md](principles.md), Holy Law #6): a fresh clone runs on the defaults, and no game-balance number is hardcoded in code.

## What `config/` is

`config/` holds **human-edited, schema-validated tunable knobs**. Both runtimes read it: the frontend at play time and `backend/` at build time ([../architecture/overview.md](../architecture/overview.md)). Every config file conforms to a typed schema in `schemas/` before the logic that reads it exists ([../architecture/contracts/schemas.md](../architecture/contracts/schemas.md)); a config file that fails its schema fails the build (`CLAUDE.md` section 1a).

## The knobs (`app-config`)

The main config surface is `app-config`. It carries, at least:

- **Enabled Modes and Games** - which [`modeId`](modes.md) and [`gameId`](games.md) values are live vs "coming soon".
- **Daily playlist** - length N and the Game mix ([modes.md](modes.md)).
- **Hints** - per-Game visibility, count, and cost ([core-loop.md](core-loop.md), [difficulty-and-scoring.md](difficulty-and-scoring.md)).
- **Infinite** - the anti-repeat LRU window size.
- **Time Trial** - the run duration.
- **Difficulty and scoring** - the difficulty ramp and the star thresholds ([difficulty-and-scoring.md](difficulty-and-scoring.md)).
- **Telemetry** - which events emit and at what level ([telemetry.md](telemetry.md)).

These are examples of the surface, not the field list - the concrete schema and defaults land with the config schema row. Every knob ships a sane default.

## Copy vs identifiers

Player-facing text lives in **`config/copy.json`**, separate from the knobs. This enforces the identifier-and-copy discipline from [../agents/guardrails.md](../agents/guardrails.md):

- **Identifiers** (`modeId`, `gameId`, `packId`, a [Journey](journeys.md) slug, a glyph id) are stable, schema-validated enums or slugs. Code references them; they never change to match a label.
- **Copy** (a Mode's display title, a Game's name, a button label) is a *field* in `config/copy.json`, never an identifier.

This is where the Tamil display names for the Games and Modes - working names today - get finalized after a native-speaker pass, without touching a single `gameId` or line of code.

## Design rationale

Splitting `app-config` (knobs) from `config/copy.json` (text) keeps a translation or a difficulty re-tune from ever forcing a code change or an identifier rename: the enums are the stable spine, the JSON files are the movable surface. The rejected alternative - inlining labels next to the enums, or hardcoding defaults in code - couples display text to identifiers and reintroduces the magic numbers Holy Law #6 forbids. Authority: Fowler (contract shape) and the guardrails identifier discipline.

## See also

- [principles.md](principles.md) - config-driven with sane defaults.
- [games.md](games.md) - the `gameId` enums and per-Game copy.
- [modes.md](modes.md) - the `modeId` enums and playlist knobs.
- [difficulty-and-scoring.md](difficulty-and-scoring.md) - the difficulty ramp and star thresholds.
- [core-loop.md](core-loop.md) - the hint shape config tunes.
- [telemetry.md](telemetry.md) - the emit / level knobs.
- [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) - the schema every config file conforms to.
- [../agents/guardrails.md](../agents/guardrails.md) - the identifier-and-copy discipline.
