# Config

**Last Updated**: 2026-08-16

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

## Runtime config vs build-time config

Not every config file is for the browser. Several are read only by the build-time producer and never ship to a player:

- **`config/corpus-sources.json`** and **`config/derived-wordlists.json`** - the corpus and derived layers ([../how-to/add-a-corpus-source.md](../how-to/add-a-corpus-source.md), [../how-to/add-a-derived-wordlist.md](../how-to/add-a-derived-wordlist.md)).
- **`config/lexicon-sources.json`** - the lexicon's source registry, and the three PUBLISH knobs beside it: `publishedClasses` (which of the ten word classes the repository commits), `spokenSources` (the frequency corpora that are spoken Tamil, which is what makes `spokenRatio` computable) and `maxPartitionBytes` (the ceiling one published file may not cross). See [../how-to/add-a-lexicon-source.md](../how-to/add-a-lexicon-source.md) and [../how-to/rebuild-the-lexicon.md](../how-to/rebuild-the-lexicon.md).
- **`config/wordhood.json`** - what each word-hood defect costs, which registered source carries a ready-made grammar or verb-form judgement, how the ezhuthu sequence model is fitted, and how far the nearest-headword search looks ([../architecture/lexicon/word-hood.md](../architecture/lexicon/word-hood.md)). The letter rules themselves are NOT here: which ezhuthu may open a Tamil word is a fact about the language, not a knob, so it lives in the ezhuthu library.
- **`config/daily-generator.json`** - the daily puzzle engine: attempts, time limit, head start, hint wording and cost, and the ezhuthu-length bands that map to a difficulty ([../how-to/generate-the-daily-bank.md](../how-to/generate-the-daily-bank.md)).

`app-config` stays the SHARED surface: how many items a day holds, which Games fill it, how many hints are allowed, which Modes are live. The generator reads those same numbers, so the day it bakes and the session the shell frames can never disagree.

## How config reaches the running game

`app-config` and `copy.json` are IMPORTED into the bundle (`frontend/src/lib/config.ts`), not fetched. They are tiny, they are needed before the first paint, and importing them means one source of truth, no extra request, and nothing to 404 offline. Copying them into `frontend/public/` would have created a second copy free to drift; fetching them would have put a round trip on the critical path for about a kilobyte.

A missing copy slug renders its own slug rather than an empty control, so a forgotten string is visible in the UI instead of silently blanking a button. A Game never reads config directly - it receives a read-only slice from the session runner ([ui-shell.md](ui-shell.md)).

## Design rationale

Splitting `app-config` (knobs) from `config/copy.json` (text) keeps a translation or a difficulty re-tune from ever forcing a code change or an identifier rename: the enums are the stable spine, the JSON files are the movable surface. The rejected alternative - inlining labels next to the enums, or hardcoding defaults in code - couples display text to identifiers and reintroduces the magic numbers Holy Law #6 forbids. Authority: Fowler (contract shape) and the guardrails identifier discipline.

Splitting the daily engine's knobs OUT of `app-config` follows the same logic one layer down: attempts, hint templates, and difficulty bands are generation decisions the browser can never act on, so shipping them in the bundle would be dead bytes and a muddled surface. Authority: Fowler + Carmack.

## Rejected alternatives

| Option | Why rejected | Authority |
| --- | --- | --- |
| Fetch `config/*.json` at runtime | A round trip on the critical path for about a kilobyte, plus a request that can fail offline, to load something that never changes between builds. | Carmack |
| Copy `config/*.json` into `frontend/public/` at build time | Two copies of one file, free to drift, with nothing gating them. | Fowler |
| Put the generator's knobs in `app-config` | Ships build-time-only knobs into the player's bundle and mixes the engine's surface with the runtime's. | Fowler |

## See also

- [principles.md](principles.md) - config-driven with sane defaults.
- [games.md](games.md) - the `gameId` enums and per-Game copy.
- [modes.md](modes.md) - the `modeId` enums and playlist knobs.
- [difficulty-and-scoring.md](difficulty-and-scoring.md) - the difficulty ramp and star thresholds.
- [core-loop.md](core-loop.md) - the hint shape config tunes.
- [telemetry.md](telemetry.md) - the emit / level knobs.
- [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) - the schema every config file conforms to.
- [../agents/guardrails.md](../agents/guardrails.md) - the identifier-and-copy discipline.
