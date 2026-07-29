# Persisted-Surface Schemas (Overview)

**Last Updated**: 2026-07-29

The map of every persisted surface in yen-tamizh and the discipline every schema follows. This is a **forward-declaring overview**: it names the surfaces and fixes the versioning rules so [../../agents/guardrails.md](../../agents/guardrails.md) and the concept docs have a stable place to link. It deliberately does **not** list concrete fields - the schema files and their field-level contracts land with the contract-pipeline and core-schema code rows. The full rules live in [../../../CLAUDE.md](../../../CLAUDE.md) section 11; this page is the concept-level index of them.

## The discipline (contracts before logic)

Every persisted shape gets a typed schema **before** the logic that reads or writes it (Holy Law #3). Each schema is a single flat file, `schemas/<name>.schema.json`, and:

- carries a **`version`** that is a **date-stamp** (`YYYY-MM-DD`, or `YYYY-MM-DDTHH:MM[:SS]` for same-day revisions) - never an integer, never an epoch;
- carries a **`changelog`** array (newest first), and **every change appends one entry** (`{ version, change, why }`) in the same commit;
- sets **`$id`** to the schema's own relative path (`<name>.schema.json`), local not URL, so an offline IDE validates it.

Change rules:

- **Additive, backwards-compatible** (a new optional field): append a `changelog` entry, set `version` to today - older payloads still validate.
- **Breaking** (a removed field, a type change, a semantic shift): append a `changelog` entry, set `version` to today, **and** write the read-side migration the new build runs on older payloads - same commit.

## Migration classes

The surfaces fall into two classes by who reads them across versions:

- **Migrating surface** - written by one version of the game and read by a later version. There is exactly one: the browser-owned **save**. A save from yesterday that no longer loads today is a contract break and a release blocker, so the save is the surface that carries read-side migrations ([../../concepts/ui-shell.md](../../concepts/ui-shell.md), StorageService).
- **Rewrite-in-place surfaces** - shipped fresh in every bundle and never migrated, because a new build simply replaces them (config, puzzle data, wordlists, manifests). A schema change here still stamps `version` and appends a `changelog` entry; it just needs no reader migration.

## The persisted surfaces

Named here so every doc has one place to point; the field lists are owned by the schema rows.

**Runtime, browser-owned (migrating):**

- `save` / `progress-record` - today's progress, streak, and last-played day. The one migrating surface; its key is recomputed on read ([../../concepts/core-loop.md](../../concepts/core-loop.md)).

**Runtime, bundle-shipped (rewrite-in-place):**

- `app-config` - the tunable knobs ([../../concepts/config.md](../../concepts/config.md)).
- `puzzle-file` - a Daily playlist ([../../concepts/modes.md](../../concepts/modes.md)).
- `journey` - a Journey definition ([../../concepts/journeys.md](../../concepts/journeys.md)).
- One payload schema per [Game](../../concepts/games.md): `anagram-puzzle`, `word-ladder-puzzle`, `missing-letters-puzzle`, `wordle-puzzle`, `word-search-puzzle`, `crossword-puzzle`.
- `event-envelope` - the [telemetry](../../concepts/telemetry.md) shape.
- `asset-manifest` / `glyph-manifest` - the baked glyph and asset index ([../../concepts/design-system.md](../../concepts/design-system.md)).

**Build-time, data (rewrite-in-place):**

- `master-wordlist` / `game-wordlist` - the curated data the generators consume.

## The source of truth

These schemas are not hand-authored twice. `backend/` Pydantic models are authoritative and export the flat `schemas/<name>.schema.json`; a frontend codegen step emits the TypeScript types and validators the game uses, and a CI drift gate fails on any divergence. That pipeline is described in [../overview.md](../overview.md) and built in its own row - this page only fixes the surface list and the versioning rules it must honour.

## See also

- [../overview.md](../overview.md) - the two-runtime split and the contract pipeline.
- [../../concepts/config.md](../../concepts/config.md) - the `app-config` and copy surfaces.
- [../../concepts/telemetry.md](../../concepts/telemetry.md) - the `event-envelope` surface.
- [../../concepts/games.md](../../concepts/games.md) - the per-Game puzzle payloads.
- [../../concepts/design-system.md](../../concepts/design-system.md) - the glyph / asset manifest.
- [../../agents/guardrails.md](../../agents/guardrails.md) - the rules-only schema-versioning digest.
- [../../../CLAUDE.md](../../../CLAUDE.md) - section 11, the authoritative schema-versioning spec.
