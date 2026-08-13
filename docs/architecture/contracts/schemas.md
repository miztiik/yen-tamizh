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

- `corpus-sources` - the declarative registry of raw word sources the corpus ingest reads ([../../how-to/add-a-corpus-source.md](../../how-to/add-a-corpus-source.md)).
- `derived-wordlists` - the declarative registry of per-Game derived sets ([../../how-to/add-a-derived-wordlist.md](../../how-to/add-a-derived-wordlist.md)).
- `master-wordlist` / `game-wordlist` - the curated data the generators consume.

## The source of truth

These schemas are not hand-authored twice. The pipeline (built in Row 5) runs one way:

1. **`backend/yen_tamizh_backend/contracts/`** - Pydantic models are authoritative. `base.py` gives every contract its `version` + `changelog` (and enforces `version == changelog[0].version`); each model subclasses `SchemaModel`.
2. **`export.py`** (`python -m yen_tamizh_backend.contracts.export`) walks the model `REGISTRY` and writes each flat `schemas/<name>.schema.json` - draft 2020-12, relative `$id`, deterministic bytes (sorted keys, 2-space indent, LF, trailing newline, ASCII).
3. **`frontend/scripts/gen-contracts.mjs`** (`npm run gen:contracts`) reads those schemas and writes, under `frontend/src/contracts/`, a `<name>.d.ts` (TypeScript types via `json-schema-to-typescript`) plus a byte-copy `<name>.schema.json` that ajv compiles into a runtime validator.
4. **`frontend/src/contracts/index.ts`** is the typed load-boundary: `loadValidated<T>(url, schemaName)` fetches JSON same-origin and validates it with the compiled ajv validator, throwing at the boundary on invalid data (section 1a, "payloads not calls").
5. **The CI `contracts` job** regenerates both sides and fails on any diff (`git diff --exit-code`), so the schema, the types, and the validators can never drift from the models.

A tiny `example` contract (`example.schema.json`) ships as the pipeline's demonstrator and drift-gate exercise; the real named surfaces below are added to the registry in their own rows - Row 7 registered the six core surfaces (`app-config`, `event-envelope`, `save`, `puzzle-file`, `bank-index`, `anagram-puzzle`) plus `copy`, Row 8 added the corpus layer (`corpus-sources`, `master-wordlist`), and Row 9 the derived layer between it and the puzzle engine (`derived-wordlists`, `game-wordlist`). The two-runtime context is in [../overview.md](../overview.md).

## Design rationale

- **Pydantic is the single source of truth; JSON Schema, TS types, and validators are generated, never hand-authored.** One model definition yields every downstream artifact, so a corpus/field change is made once and the generated types + validators follow. The drift gate makes divergence impossible rather than merely discouraged. (Fowler, user-directed.)
- **Runtime validation is ajv over the generated schema; static types are `json-schema-to-typescript`.** The frontend consumes backend output only as schema-validated payloads and fails fast at the load-boundary. ajv is a runtime dependency (it ships when the boundary is used); `json-schema-to-typescript` is build-time only. (Fowler.)
- **Determinism is engineered, not assumed.** The drift gate runs on CI (Python 3.12, npm 10.9.2) but authors run other versions, so the pipeline pins `pydantic` exactly, canonicalises the JSON (sorted keys, fixed indent), pins `json-schema-to-typescript` and disables its external formatter (`format:false`), and forces LF (`export` `newline`, `.gitattributes`). Same inputs -> byte-identical outputs on every machine.

### Core-surface field decisions (Row 7)

The six core surfaces plus `copy` land as Pydantic models registered in the pipeline. The shape decisions are Fowler's altitude (persisted-contract authority):

- **Per-Game payload schemas, not one mega-schema.** A `puzzle-file` item carries an OPEN `payload` object; each Game validates its own slice against its own schema (`anagram-puzzle` is the first). A new Game costs a payload schema, not an edit to `puzzle-file`, so Games evolve independently. `event-envelope`'s `ctx`/`data` are open for the same reason - pinning them would force a schema bump every time a Game emits a new context key.
- **The save `dayKey` is recomputed on read, never trusted from storage.** It is a derived key (`date|modeId|gameId|packId`); the reader rebuilds it from its value fields so a stale or tampered stored key can never select the wrong day (the guardrails derived-key rule). `compute_day_key` is that single recompute; the read-side migration and the TypeScript twin land with the reader (Row 11).
- **Identifiers are stable slugs; copy is a separate, validated surface.** `gameId`, `modeId`, `packId`, and difficulty are lower-case slugs; player-facing text lives in `config/copy.json`, keyed by a slug. `copy` is a pipeline `SchemaModel` (with `version`/`changelog`) like `app-config`, not a hand-authored map, so there is one source of truth and the drift gate covers it. (Jony + Fowler.)
- **`event-envelope` carries both `v` and `version`/`changelog`.** `v` is the lightweight per-event version a reader uses to evolve its parsing; `version`/`changelog` are the schema-discipline stamp every persisted surface carries (CLAUDE.md section 11). `name` is constrained to the canonical event catalog, so an unregistered name is rejected at the boundary.

### Corpus-layer field decisions (Row 8)

The corpus is a layer of its own: `corpus-sources` in, `master-wordlist` out, and nothing in between knows about a Game, a mode, or a day. That separation is the point - the derived per-Game sets read the master list and the daily engine reads those, so a corpus refresh never rebuilds a Game.

- **The source registry is a schema-backed config, so extending the corpus is a data change.** `config/corpus-sources.json` names every source, where its bytes are, and how to map its columns/fields; the ingest dispatches on `kind` to one reader per format. Adding a frequency list or a dictionary is an entry plus a re-run. Only an unseen FORMAT costs code (a reader plus a `SourceKind` member). A mapping that belongs to the other `kind` is rejected rather than ignored - a knob that silently does nothing is a lie in the config. (Fowler; user-directed.)
- **`master-wordlist` embeds its own provenance and counters instead of a sibling `provenance.json`.** A second file describing the same run is a second source of truth that goes stale; embedding puts the traceability (`name`, `origin`, `bytes`, `sha256`, `rowsIn`, `rowsKept` per source) under the same drift gate as the words. The `counters` block is the integrity Oracle, enforced by the model itself: `rowsIn - rejected - duplicates == distinct` and `distinct - belowFrequencyFloor - capped == rowsKept == len(words)`, so a silent drop cannot validate. (Fowler.)
- **`length` counts ezhuthu, and the model proves the segmentation rejoins.** `MasterWord` rejects any row where `"".join(ezhuthu) != word` or `length != len(ezhuthu)`, so a corrupt row cannot reach a derived set. The segmentation itself is the Row 6 library, never re-implemented.
- **Neither corpus schema is registered in `frontend/src/contracts/index.ts`.** Both are build-time surfaces the game never fetches; compiling an ajv validator for a 12 MiB dataset would ship dead runtime bytes (Holy Law #2). They still flow through the pipeline and the drift gate, exactly like `glyph-manifest`. (Carmack + Fowler.)
- **`pos` was dropped from the specified row shape; `category` was kept.** Nothing on disk produces a trustworthy part of speech - the one curated dictionary labels 99.8 percent of its entries `nouns`, including verbs and verbal nouns - so emitting `pos` would assert something the data does not support, and an always-absent optional field is a contract with no producer. Its themed tags (`trees`, `flowers`, `birds`, `animals`) do carry signal and are kept as `category`. Adding `pos` later is one additive `changelog` entry, which is what the pipeline is for. (Fowler.)

### Derived-layer field decisions (Row 9)

The derived layer sits between the corpus and the puzzle engine: `master-wordlist` plus `derived-wordlists` in, one `game-wordlist` per Game out. It selects words; it does not generate puzzles, know what a day is, or write anything into `frontend/public/`.

- **The set registry is a schema-backed config, so adding a Game's wordlist is a data change.** `config/derived-wordlists.json` names each set's `gameId`, output path, and selection knobs; `corpus/derive.py` is the single mechanism that interprets them. Adding a set is an entry plus a re-run of `rebuild_wordlists` - the same extensibility bargain `corpus-sources` makes one layer up, and the reason four more Games (Rows 18-21) cost no framework today. The selection knobs are config rather than Python literals because ezhuthu length ranges and band cutoffs are tunable game-balance numbers (Holy Law #6). Only a predicate the knobs cannot express costs code, which is the same line the corpus layer draws at an unseen source FORMAT. (Fowler.)
- **`game-wordlist` carries no wall-clock `generatedAt`.** A derived set is a pure function of the master it was cut from plus the selection applied, and a timestamp would make two runs over one master emit different bytes - the opposite of what a reproducible build artifact means, and a permanently flapping diff. `source` pins the input instead (`path`, the master's `version` and `generatedAt`, `sha256`, `rows`), and git history records when the file changed (CLAUDE.md section 5). This is what lets a test re-derive the committed artifact and compare it byte for byte, which is also the hand-edit gate. (Fowler.)
- **`counters` reconciles every master row under exactly one heading.** `masterRows - outsideLength - outsideBand - withoutCoAnagram - capped == rowsKept == len(words)`, enforced by the model, so a selection bug cannot quietly drop words. Same integrity Oracle as `master-wordlist`'s ingest ledger. (Fowler.)
- **The co-anagram rule is checked against the whole master, not the set being built.** A word qualifies when its ezhuthu multiset is shared with at least one OTHER master word, even one the Game's own selection rejects - the unscramble tension comes from the language, not from the shortlist. The rule is strict and expensive: Tamil has 247 ezhuthu against English's 26 letters, so only 558 of the 50,000 master words (1.1 percent) have any anagram at all, and the anagram set is 234 words rather than the thousands a naive length-and-band filter would yield. Reporting the honest smaller set is the point; weakening the rule would ship scrambles with exactly one possible arrangement. (Palm + Fowler.)
- **`hints` carries only what the data honestly supports.** `first_ezhuthu` and `length` are recomputed from `ezhuthu` on every rebuild and validated against it, so precomputing them cannot drift - the same bargain `MasterWord.length` makes. The specified `category_ta` is NOT emitted: the master's category tags are English source labels, and a Tamil category name is player-facing copy, which lives in `config/copy.json` and never inside a dataset. Inventing the Tamil strings here would be a field that asserts more than the data knows. Its field names are snake_case, matching the contract named in the build roadmap, where the rest of the repo's persisted shapes are camelCase. (Fowler.)
- **Neither derived-layer schema is registered in `frontend/src/contracts/index.ts`.** Both are build-time surfaces the game never fetches - the browser downloads the puzzles the daily engine bakes (Row 13), not the wordlists they were baked from - so an ajv validator for either would ship dead runtime bytes. Same precedent as the corpus schemas and `glyph-manifest`; the drift gate still covers them. (Carmack + Fowler.)

## Rejected alternatives

| Option | Why rejected | Authority |
| --- | --- | --- |
| Hand-authored Zod on the frontend | A second source of truth that drifts from Pydantic; defeats "refresh the corpus without rebuilding the mechanics". | Fowler |
| `schemas/<name>/vN.schema.json` version folders | The contract versions in-file via `version`/`changelog` (CLAUDE.md section 11), not by folder; folders duplicate history git already keeps. | Fowler |
| A separate `datasets/corpus/provenance.json` | Two files describing one run drift; the master wordlist carries its own provenance under the same drift gate. | Fowler |
| Hard-coding the corpus source list in `ingest.py` | Every new word source would then be a code change, breaking the corpus-vs-puzzle-engine separation the row exists to establish. | Fowler (user-directed) |
| Committing the raw corpora (about 265 MB) | `datasets/corpus/**` is gitignored; `origin` + `bytes` + `sha256` in the provenance block make a run reproducible without the bytes in history. | Carmack |
| Hand-curating each Game's wordlist | Not reproducible, and it drifts from the master on every corpus refresh; the sets are build artifacts regenerated by one command. | Fowler |
| A registry of named selector FUNCTIONS in `derive.py` | One Game exists today and the four named next (Rows 18-21) all reduce to the same knobs - length range, bands, cap. A plugin seam for a single implementation is speculative generality, and it would move tunable game-balance numbers out of `config/` in violation of Holy Law #6. The seam that IS earned is the config registry. | Fowler |
| Relaxing the co-anagram rule to grow the anagram set | The rule is the row's Oracle; without it a scramble can have exactly one possible arrangement, which is not a puzzle. 234 words is an honest 7-month daily bank, and the fix for wanting more is a bigger corpus, not a weaker rule. | Palm |
| Emitting `category_ta` by translating the master's English tags | Player-facing Tamil is copy (`config/copy.json`), and inventing category strings inside a dataset asserts more than the data knows. The field is simply absent until an honest producer exists. | Fowler |
| A wall-clock `generatedAt` on a derived set | Makes the artifact non-reproducible by construction and turns every rebuild into a diff; the pinned `source` block plus git history carry the same information honestly. | Fowler |
| valibot | Weaker JSON-Schema codegen path than ajv today. | Fowler |
| ajv standalone precompiled validators | More generated, version-sensitive surface in the drift gate for no current benefit; runtime-compile is simpler. If Carmack's frame budget later flags ajv's bytes, standalone is the named optimization. | Fowler / Carmack |
| One mega puzzle schema for all Games | Couples every Game's payload into one shape; a new Game or a payload change forces an edit to the shared schema and risks breaking the others. An open per-item `payload` plus one schema per Game keeps them independent. | Fowler |
| Trusting the stored save `dayKey` | A derived key read from storage can be stale or tampered and would select the wrong day's progress; it is recomputed on read from its value fields instead. | Fowler |
| A hand-authored `config/copy.json` map with no schema | A second, un-validated surface that drifts from the pipeline; `copy` is a `SchemaModel`, so the drift gate and ajv cover it like every other contract. | Fowler |

## See also

- [../overview.md](../overview.md) - the two-runtime split and the contract pipeline.
- [../../concepts/config.md](../../concepts/config.md) - the `app-config` and copy surfaces.
- [../../concepts/telemetry.md](../../concepts/telemetry.md) - the `event-envelope` surface.
- [../../concepts/games.md](../../concepts/games.md) - the per-Game puzzle payloads.
- [../../concepts/design-system.md](../../concepts/design-system.md) - the glyph / asset manifest.
- [../../agents/guardrails.md](../../agents/guardrails.md) - the rules-only schema-versioning digest.
- [../../../CLAUDE.md](../../../CLAUDE.md) - section 11, the authoritative schema-versioning spec.
