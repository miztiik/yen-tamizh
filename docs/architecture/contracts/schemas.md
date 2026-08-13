# Persisted-Surface Schemas (Overview)

**Last Updated**: 2026-08-13

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

These schemas are not hand-authored twice. The pipeline (built in Row 5) runs one way:

1. **`backend/yen_tamizh_backend/contracts/`** - Pydantic models are authoritative. `base.py` gives every contract its `version` + `changelog` (and enforces `version == changelog[0].version`); each model subclasses `SchemaModel`.
2. **`export.py`** (`python -m yen_tamizh_backend.contracts.export`) walks the model `REGISTRY` and writes each flat `schemas/<name>.schema.json` - draft 2020-12, relative `$id`, deterministic bytes (sorted keys, 2-space indent, LF, trailing newline, ASCII).
3. **`frontend/scripts/gen-contracts.mjs`** (`npm run gen:contracts`) reads those schemas and writes, under `frontend/src/contracts/`, a `<name>.d.ts` (TypeScript types via `json-schema-to-typescript`) plus a byte-copy `<name>.schema.json` that ajv compiles into a runtime validator.
4. **`frontend/src/contracts/index.ts`** is the typed load-boundary: `loadValidated<T>(url, schemaName)` fetches JSON same-origin and validates it with the compiled ajv validator, throwing at the boundary on invalid data (section 1a, "payloads not calls").
5. **The CI `contracts` job** regenerates both sides and fails on any diff (`git diff --exit-code`), so the schema, the types, and the validators can never drift from the models.

A tiny `example` contract (`example.schema.json`) ships as the pipeline's demonstrator and drift-gate exercise; the real named surfaces below are added to the registry in their own rows. The two-runtime context is in [../overview.md](../overview.md).

## Design rationale

- **Pydantic is the single source of truth; JSON Schema, TS types, and validators are generated, never hand-authored.** One model definition yields every downstream artifact, so a corpus/field change is made once and the generated types + validators follow. The drift gate makes divergence impossible rather than merely discouraged. (Fowler, user-directed.)
- **Runtime validation is ajv over the generated schema; static types are `json-schema-to-typescript`.** The frontend consumes backend output only as schema-validated payloads and fails fast at the load-boundary. ajv is a runtime dependency (it ships when the boundary is used); `json-schema-to-typescript` is build-time only. (Fowler.)
- **Determinism is engineered, not assumed.** The drift gate runs on CI (Python 3.12, npm 10.9.2) but authors run other versions, so the pipeline pins `pydantic` exactly, canonicalises the JSON (sorted keys, fixed indent), pins `json-schema-to-typescript` and disables its external formatter (`format:false`), and forces LF (`export` `newline`, `.gitattributes`). Same inputs -> byte-identical outputs on every machine.

## Rejected alternatives

| Option | Why rejected | Authority |
| --- | --- | --- |
| Hand-authored Zod on the frontend | A second source of truth that drifts from Pydantic; defeats "refresh the corpus without rebuilding the mechanics". | Fowler |
| `schemas/<name>/vN.schema.json` version folders | The contract versions in-file via `version`/`changelog` (CLAUDE.md section 11), not by folder; folders duplicate history git already keeps. | Fowler |
| valibot | Weaker JSON-Schema codegen path than ajv today. | Fowler |
| ajv standalone precompiled validators | More generated, version-sensitive surface in the drift gate for no current benefit; runtime-compile is simpler. If Carmack's frame budget later flags ajv's bytes, standalone is the named optimization. | Fowler / Carmack |

## See also

- [../overview.md](../overview.md) - the two-runtime split and the contract pipeline.
- [../../concepts/config.md](../../concepts/config.md) - the `app-config` and copy surfaces.
- [../../concepts/telemetry.md](../../concepts/telemetry.md) - the `event-envelope` surface.
- [../../concepts/games.md](../../concepts/games.md) - the per-Game puzzle payloads.
- [../../concepts/design-system.md](../../concepts/design-system.md) - the glyph / asset manifest.
- [../../agents/guardrails.md](../../agents/guardrails.md) - the rules-only schema-versioning digest.
- [../../../CLAUDE.md](../../../CLAUDE.md) - section 11, the authoritative schema-versioning spec.
