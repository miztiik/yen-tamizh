# yen-tamizh Build Roadmap (Phases 0-8)

**Last Updated**: 2026-07-25
**Level**: 5 (core design + data model + runtime picks). Per-row Level is stated on each row; every Level-5 row is an ESCALATE point (section 0).

Companion to the system-design proposal [`README.md`](README.md). This plan turns that proposal into PR-sized rows an autonomous orchestrator can run. Authored for review per [`../docs/how-to/author-a-plan.md`](../docs/how-to/author-a-plan.md); **not authorized to execute** until the user says go (section 0).

Aligned to the contract as committed 2026-07-25 (`CLAUDE.md` sections 1a, 3, 4, 11): the build-time producer is **`backend/`** (Python), every schema is a flat `schemas/<name>.schema.json` carrying a **date-stamp `version` + `changelog`** (never an integer), generated data ships **in the bundle under `frontend/public/`** (Holy Law #1 - no runtime fetches, works offline), and every boundary is an **event carrying a serializable payload, not a call** (section 1a).

## 0. Operating contract

| Field | Value |
| --- | --- |
| Why this plan exists | Build yen-tamizh - a static Tamil word-puzzle PWA - from the current scaffold to a multi-Game, multi-Mode, Journey-threaded game, on the committed engineering contract. |
| Hard scope - in | Repo skeleton (frontend Svelte/Vite/Tailwind + backend Python); PWA/offline; the evolutionary Pydantic -> JSON-Schema -> TS/ajv contract pipeline; ezhuthu library; 6 Games (anagram, word-ladder, missing-letters, wordle, word-search, crossword); 4 Modes (daily, journey, infinite, time-trial); corpus ingest + curated wordlists; design system (tokens/animation/glyphs); telemetry; CI (ci/daily-bank/deploy). |
| Hard scope - out | Runtime backend, runtime fetches to external hosts, accounts, push, runtime analytics SDK, monetisation (`CLAUDE.md` sections 0a, 1 Holy Law #1). No non-Tamil packs in this plan. |
| ESCALATE triggers | Any Level-5 row (3, 5, 7, 15, 21) pauses for user sign-off before merge. A new `## Design rationale` that changes a persisted contract. An unresolved persona conflict. A corpus-license question (Row 8). |
| Chosen strategy | Reuse+adapt from `yen-tamizh_OLD` (TS Mode x Game shell, `tamil/` ezhuthu logic, Python generator, curated wordlists) and `yen-cinthanai` (Svelte/config/schemas/bank patterns); Pydantic in `backend/` is the single source of truth for every persisted shape; Games read generated, schema-validated contracts so a corpus refresh never rebuilds a Game (Fowler). |
| Perf stance | Richness-first, measure-then-optimize; NO artificial byte cap (`CLAUDE.md` Holy Law #2, user-directed). Constraint = 60fps + input-to-photon <50ms on a mid-tier Android (Carmack). |
| Execution | orchestrator per [`../docs/how-to/execute-a-plan.md`](../docs/how-to/execute-a-plan.md): one worktree-isolated worker subagent per row; workers consult personas on ambiguity; AUTO-merge on green gates. Parallel N = 2. AUTHOR-AND-STOP until the user authorizes. |

### Architecture principles in force (`CLAUDE.md` section 1a - every row honors these)
- **Event-driven, payloads not calls.** The frontend<->backend contract is committed JSON (a serializable payload validated against a schema), never a function call. Runtime modules (Mode -> Runner -> Game -> telemetry) communicate through structured-payload events on one bus.
- **Async, non-blocking.** No boundary blocks the main thread; the render loop keeps painting. Timers use `requestAnimationFrame`, never `setInterval`.
- **Config-driven, sane defaults.** A fresh clone runs on `config/` defaults. No magic numbers in code.
- **Schema-first.** A config or payload that fails its `schemas/<name>.schema.json` fails the build.
- **Visual feedback is first-class.** Input-confirming animation/colour/motion is expected, not optional (game feel, not a11y tooling).

### Data-delivery model (Holy Law #1)
`backend/` (Python, build-time) writes the puzzle **bank** and level data into **`frontend/public/`** at build time; the deployed static bundle carries it; the game loads it same-origin and the service worker precaches it so it works offline. **No `raw.githubusercontent.com`, no external CDN, no runtime fetch to a server.** The game never reads raw `datasets/` or `assets/` - only baked `frontend/public/` output.

### The contract pipeline (evolutionary data model - Row 5 builds it)
`backend/` Pydantic models are authoritative -> `model_json_schema()` exports flat `schemas/<name>.schema.json` (relative `$id`, `version` date-stamp, `changelog[]`) -> a frontend codegen step emits TS types + ajv validators into `frontend/src/contracts/`. A CI drift gate regenerates and fails on any diff. An additive corpus/field change appends a `changelog` entry and regenerates types; Games keep compiling untouched. Only a breaking change writes a read-side migration (in the reader, not the Game).

### Event & payload catalog (registered in Row 7, cited by later rows)
Envelope `{ ts, src, v, session, name, level, ctx, data }`. Game: `puzzle.started` / `puzzle.attempt.submitted` / `puzzle.hint.used` / `puzzle.completed` / `puzzle.abandoned`. Mode/session: `mode.session.started` / `mode.session.completed` / `streak.updated`. Backend pipeline (stdout JSON lines): `pipeline.stage.started|completed|failed` / `puzzle.generated` / `bank.updated`. No network sink (Non-Goal): dev logs to console, prod ring-buffers for `window.__yt_dump()`.

### Reuse provenance (exact sources to port)
- Shell/runtime + Games + telemetry (TS, vanilla -> adapt to Svelte): `yen-tamizh_OLD/frontend/src/{shell,session,services,telemetry,modes,games}`.
- Ezhuthu (grapheme) logic (TS): `yen-tamizh_OLD/frontend/src/tamil/`.
- Generator + pipeline (Python): `yen-tamizh_OLD/backend/src/yen_tamizh_backend/`.
- Curated wordlists (data): `yen-tamizh_OLD/data/wordlists/game_words_{2..6}_letter.json`.
- Raw corpus (data, incomplete - supplement): `yen-tamizh_OLD/words_and_frequency/`, `yen-tamizh_OLD/src/dictionary/`.

## 1. Status Reckoner

| # | Row title | Level | Depends-on | Group | Status | Worktree | PR | Subagent |
| --- | --- | :---: | --- | --- | --- | --- | --- | --- |
| 1 | Contract right-size + rebrand | 5 | - | - | DONE (2026-07-25 commit) | - | - | - |
| 2 | Foundational concept + how-to docs + AGENTS.md | 3 | 1 | A | DONE | - | #1 | worker |
| 3 | Repo skeleton (frontend + backend) + CI wiring | 5 | 1 | A | DONE | - | #2 | worker |
| 4 | PWA + offline shell (service worker, base-path, install) | 4 | 3 | B | IN-FLIGHT | ../yen-tamizh-row4 | - | worker |
| 5 | Evolutionary contract pipeline (Pydantic -> JSON Schema -> TS/ajv) | 5 | 3 | B | READY (ESCALATE) | - | - | - |
| 6 | Ezhuthu library (Python + TS twins) | 4 | 3 | B | DONE | - | #3 | worker |
| 7 | Core schemas (app-config/event-envelope/save/puzzle-file/bank-index/anagram) | 5 | 5,6 | C | PENDING | - | - | - |
| 8 | Corpus ingest + master wordlist | 4 | 5,6 | C | PENDING | - | - | - |
| 9 | Derived-wordlist framework + anagram set | 3 | 8 | - | PENDING | - | - | - |
| 10 | Design system (tokens + animation + glyph bake + manifest) | 3 | 5 | - | PENDING | - | - | - |
| 11 | Shell + runtime (SessionShell/Runner/registry/storage/bus) | 4 | 7,10 | - | PENDING | - | - | - |
| 12 | AnagramGame | 3 | 11 | - | PENDING | - | - | - |
| 13 | DailyMode + daily bank generator + Home | 4 | 9,12 | - | PENDING | - | - | - |
| 14 | Daily playlist + hints (changelog evolution) | 3 | 13 | - | PENDING | - | - | - |
| 15 | Ladder graph builder + word-ladder schema | 5 | 7,8 | - | PENDING | - | - | - |
| 16 | WordLadderGame + share-result card | 3 | 11,15 | - | PENDING | - | - | - |
| 17 | JourneyMode + winding-path home | 4 | 10,16 | - | PENDING | - | - | - |
| 18 | MissingLettersGame + gen + derived set | 3 | 9,11 | G | PENDING | - | - | - |
| 19 | WordleGame + gen + derived set | 3 | 9,11 | G | PENDING | - | - | - |
| 20 | WordSearchGame + gen + derived set | 3 | 9,11 | G | PENDING | - | - | - |
| 21 | CrosswordGame + placement solver + derived set | 5 | 9,11 | G | PENDING | - | - | - |
| 22 | InfiniteMode + bulk pool + index | 4 | 12,13 | H | PENDING | - | - | - |
| 23 | TimeTrialMode | 3 | 12,22 | H | PENDING | - | - | - |

Dependency spine: `1(done) -> {2,3} -> {4,5,6} -> {7,8} -> {9,10} -> 11 -> 12 -> 13 -> 14`; Word Ladder `15 -> 16 -> 17`; Games `18..21` parallel after `9,11`; Modes `22 -> 23` after `12,13`. Parallel groups: A `{2,3}`, B `{4,5,6}`, C `{7,8}`, G `{18,19,20,21}`, H `{22,23}`.

---

## 2. Rows

### Phase 0 - Foundation

### Row #1 - Contract right-size + rebrand (Level 5) - DONE
- **Status:** Executed by the user's 2026-07-25 commit `docs(contract): right-size CLAUDE.md and align guardrails, agents, workflows`. Recorded here for lineage; no further work.
- **Shipped:** `CLAUDE.MD` -> `CLAUDE.md` renamed + rebranded to yen-tamizh; Holy Law #2 restored; section 1a Architecture Principles added; schema versioning changed to date-stamp `version` + in-schema `changelog`; topology rebuilt (`backend/` not `tools/`, `schemas/` + `datasets/` added); root `README.md` created; `guardrails.md`, the five agent files, and `ci`/`daily`/`deploy` workflows aligned to `backend/`.
- **Decisions (as ruled by the user, superseding the v1 plan):**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Keep the general game-dev contract (canvas/renderer/physics language stays) rather than stripping it to a pure DOM contract. | User (supersedes v1 Row 1) |
  | 2 | Schema version is a date-stamp `version` + `changelog[]`, never an integer/epoch. | Fowler (user-committed) |
  | 3 | Build-time producer is `backend/` (Python), writing into `frontend/public/`; no CDN. | Fowler + Carmack (user-committed) |

- **Residual folded into Row 2:** root `AGENTS.md` (referenced by the DoD, not yet created).

### Row #2 - Foundational concept + how-to docs + AGENTS.md (Level 3)
- **Scope:** Author the greenfield concept docs and the two missing how-to docs the harness links to, plus the root `AGENTS.md`, so no bootstrap/guardrails link dangles.
- **Reuse:** adapt the shape of `yen-tamizh_OLD/docs/concepts/{vision,principles,architecture}.md` and `yen-cinthanai/docs/`; content is yen-tamizh-specific.
- **Files touched:**
  - `docs/concepts/{vision,principles,core-loop,ui-shell,difficulty-and-scoring,games,modes,journeys,telemetry,config,design-system}.md`.
  - `docs/how-to/{execute-a-plan,handle-scope-change}.md` (referenced by `author-a-plan.md`/`bootstrap.md`, currently absent).
  - `docs/architecture/overview.md` (the two-runtime static-first + data-delivery diagram), `docs/architecture/contracts/schemas.md` (referenced by guardrails).
  - `AGENTS.md` (root; points at `docs/`, lists do-not-open corpora).
- **Acceptance gates:** every doc has H1 + `Last Updated` + "See also"; `rg` across `docs/` + `.github/agents/` + `CLAUDE.md` resolves every relative link (zero dangling); ASCII-punctuation lint clean.
- **Oracle:** coverage - the set of doc paths referenced by `docs/agents/*.md`, `docs/how-to/author-a-plan.md`, and `guardrails.md` is a subset of files that now exist.
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Concept docs (vocabulary) precede code; subsystem docs land with their code row, not here. | Fowler |
  | 2 | Journey is a Mode (curated ordered Session), defined once in `concepts/journeys.md`. | Fowler + Palm |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Defer docs until code exists | Bootstrap/guardrails links dangle now; the harness cannot run its ritual. | Fowler |
  | 2 | Author every subsystem doc up front | Subsystem docs are living snapshots; they land with their code to avoid drift. | Fowler |

### Row #3 - Repo skeleton (frontend + backend) + CI wiring (Level 5)
- **Scope:** Land the empty-but-building `frontend/` (Svelte+Vite+TS+Tailwind) and `backend/` (Python+Pydantic) trees, the `config/`+`schemas/`+`datasets/` dirs, and wire the three workflows to green on the skeleton.
- **Reuse:** `yen-tamizh_OLD/frontend/{vite.config.ts,tsconfig*,tailwind.config.js,postcss.config.js,vitest.config.ts}` as a starting point (add `svelte.config.js`, `@sveltejs/vite-plugin-svelte`); `yen-tamizh_OLD/backend/pyproject.toml` for the Python packaging shape.
- **Files touched:**
  - `frontend/{package.json,vite.config.ts,svelte.config.js,tsconfig*.json,tailwind.config.js,postcss.config.js,index.html,.eslintrc,vitest.config.ts,playwright.config.ts}`, `frontend/src/{main.ts,App.svelte,app.css}`, `frontend/tests/smoke.spec.ts`.
  - `backend/pyproject.toml` (package `yen_tamizh_backend`, deps: `pydantic>=2`, `pytest`, `mypy`), `backend/yen_tamizh_backend/__init__.py`, `backend/utilities/__init__.py`, `backend/tests/test_smoke.py`.
  - `config/app-config.json` (minimal defaults), `config/copy.json` (empty map), `schemas/README.md`, `datasets/README.md`.
  - `.github/workflows/ci.yml` (jobs: `frontend` = eslint + svelte-check + vitest + playwright + build; `backend` = mypy + pytest; `contracts` = schema drift-gate placeholder), `deploy.yml` (Pages, base-path `GH_PAGES_BASE`, `dist/404.html` == `dist/index.html`), `daily.yml` (bank-gen stub).
- **Acceptance gates:** `npm run build` emits `frontend/dist`; `npm run test` + `pytest` + `mypy` green on smoke tests; deploy builds a base-path bundle; browser smoke shows the empty shell, zero console `[error]`/404.
- **Oracle:** a from-clean CI run passes every job on the skeleton, proving the full toolchain (both runtimes + deploy) before any feature lands.
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Frontend = Svelte + Vite + Tailwind; backend = Python package `yen_tamizh_backend` + `backend/utilities/`. | Fowler + Carmack (user-directed) |
  | 2 | Per-Game route-level code-splitting so a Game's bytes load on first open. | Carmack |
  | 3 | `config/` ships sane defaults; a fresh clone runs with no env (section 1a). | Fowler |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Vanilla TS + DOM (yen-tamizh_OLD stack) | User chose Svelte; component ergonomics for many Games/screens. | Fowler |
  | 2 | pnpm monorepo (yen-neram) | One `frontend/` app + `backend/` is simpler; no second package earns its keep. | Fowler |

### Row #4 - PWA + offline shell (Level 4)
- **Scope:** Make the shell an installable PWA whose service worker precaches the app shell and serves same-origin bank data offline, base-path aware.
- **Reuse:** the offline/base-path contract in [`../docs/how-to/ship-to-github-pages.md`](../docs/how-to/ship-to-github-pages.md).
- **Files touched:**
  - `frontend/vite.config.ts` (+ `vite-plugin-pwa` / workbox), `frontend/public/manifest.webmanifest` (relative `start_url`/`scope`/icons), `frontend/src/sw-register.ts`.
  - `frontend/src/lib/base.ts` (base-aware path helper using `import.meta.env.BASE_URL`).
  - `docs/architecture/runtime/stack-and-bundle.md` (the PWA/offline + base-path rationale doc referenced by the how-to).
- **Acceptance gates:** installable manifest; SW precaches shell; a base-path production build resolves asset + `404.html` deep links; browser smoke in a production-like build proves the install/update path (per `CLAUDE.md` section 12); offline reload of a visited route still renders.
- **Oracle:** offline - after one online load, a reload with the network cut still boots the shell and replays the last opened puzzle from cache.
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Recent bank days are precached; older days load same-origin on demand and are runtime-cached (bank archive is not fully precached). | Carmack |
  | 2 | Theme/motif art is a runtime (non-precached) asset; the default theme ships in the shell. | Carmack + Jony |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Precache the entire puzzle archive | Unbounded precache growth; violates the phone-first budget. | Carmack |
  | 2 | Fetch daily puzzles from an external CDN | Holy Law #1 forbids runtime fetches to external hosts. | Fowler |

### Phase 0 cross-cutting - Contracts + Data

### Row #5 - Evolutionary contract pipeline (Level 5)
- **Scope:** Make backend Pydantic models the single source of truth that export flat JSON Schemas, from which the frontend's TS types + ajv validators are generated, gated against drift.
- **Reuse:** greenfield (the yen-cinthanai `schemas/` + Pydantic pattern is the model, not the code).
- **Files touched:**
  - `backend/yen_tamizh_backend/contracts/{__init__,base}.py` (Pydantic `SchemaModel` base carrying `version` date-stamp + `changelog: list[ChangelogEntry]`; `ChangelogEntry = {version, change, why}`).
  - `backend/yen_tamizh_backend/contracts/export.py` (writes `schemas/<name>.schema.json` with relative `$id`, draft 2020-12).
  - `frontend/scripts/gen-contracts.mjs` (JSON Schema -> `frontend/src/contracts/<name>.d.ts` via json-schema-to-typescript; ajv validators compiled).
  - `frontend/src/contracts/index.ts` (typed load-boundary validators; `loadValidated<T>(url, schema)`), `.github/workflows/ci.yml` (`contracts` job: regenerate, `git diff --exit-code`).
- **Contracts:** establishes the `version`/`changelog` convention for every later schema; `$id` = `<name>.schema.json` (relative, offline-validatable).
- **Events / payloads:** this is the "payloads not calls" spine (section 1a) - the frontend consumes backend output only as schema-validated JSON payloads.
- **Acceptance gates:** regenerating schemas + TS types leaves the tree clean; a malformed fixture is rejected by both the Pydantic model and the frontend ajv validator (contract-tier test both sides); mypy + vitest green.
- **Oracle:** round-trip bijection - `Pydantic -> JSON Schema` and `JSON Schema -> TS types` both reproduce byte-identical committed files (the CI drift gate).
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Pydantic is authoritative; JSON Schema + TS types + validators are generated, never hand-authored. | Fowler (user-directed) |
  | 2 | Frontend runtime validation = ajv over the generated schema; static types = json-schema-to-typescript. | Fowler |
  | 3 | Schemas are flat `schemas/<name>.schema.json` with an internal `version`/`changelog`; no `vN/` folders. | Fowler (per `CLAUDE.md` section 11) |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Hand-authored Zod on the frontend | A second source of truth that drifts from Pydantic; defeats "refresh corpus without rebuilding mechanics". | Fowler |
  | 2 | `schemas/<name>/vN.schema.json` folders (yen-tamizh_OLD) | The committed contract versions in-file via `version`/`changelog`, not by folder. | Fowler |
  | 3 | valibot | Weaker JSON-Schema codegen path than ajv today. | Fowler |

### Row #6 - Ezhuthu library (Python + TS twins) (Level 4)
- **Scope:** Ship grapheme-cluster (ezhuthu) segmentation + reconstruction in both Python and TS, proven identical against one golden corpus.
- **Reuse:** port `yen-tamizh_OLD/frontend/src/tamil/` to `frontend/src/tamil/ezhuthu.ts`; write the Python twin fresh.
- **Files touched:**
  - `backend/yen_tamizh_backend/ezhuthu/{segment,classify}.py` (uyir / mei+pulli / uyirmei; `segment(word) -> list[str]`).
  - `frontend/src/tamil/ezhuthu.ts` (same surface).
  - `datasets/fixtures/ezhuthu_golden.jsonl` (word -> ezhuthu[] pairs, incl. edge cases: pulli, uyirmei, `ksha`, Grantha).
  - `backend/tests/test_ezhuthu.py`, `frontend/src/tamil/ezhuthu.test.ts`.
- **Acceptance gates:** both implementations pass the shared golden corpus; pytest + vitest green; property test: `join(segment(w)) == w`.
- **Oracle:** cross-language parity - for every golden row, `segment_py(word) == segment_ts(word)`.
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | The atomic unit everywhere (tiles, cells, wordle letters, ladder rungs, crossword interlock) is the ezhuthu. | Fowler + Player |
  | 2 | Two implementations kept in lockstep by a shared golden corpus (a contract fixture), not one shared runtime. | Fowler |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Codepoint-level handling | Splits uyirmei/pulli clusters mid-letter; unplayable. | Player |
  | 2 | One WASM ezhuthu module shared by both | Overkill for string segmentation; two tested twins are lighter. | Carmack |

### Row #7 - Core schemas (Level 5)
- **Scope:** Define the first wave of persisted contracts as Pydantic models via the Row 5 pipeline: `app-config`, `event-envelope`, `save`, `puzzle-file`, `bank-index`, `anagram-puzzle`.
- **Reuse:** field shapes from `yen-tamizh_OLD/schemas/{app-config,event-envelope,progress-record,puzzle-file,puzzle-index,anagram-puzzle}` (re-expressed as Pydantic + the new `version`/`changelog`).
- **Files touched:**
  - `backend/yen_tamizh_backend/contracts/{app_config,event_envelope,save,puzzle_file,bank_index,anagram_puzzle}.py` -> generated `schemas/*.schema.json` + `frontend/src/contracts/*`.
  - `config/app-config.json` (validated), `config/copy.json` (validated).
- **Contracts (key fields):**
  - `app-config`: `{ version, changelog, daily:{playlistLength, mix:{<gameId>:n}}, hints:{enabled, perGame}, infinite:{lruWindow, defaultDifficulty}, timeTrial:{durationSec}, ui:{enabledModes, defaultMode, defaultTheme} }`.
  - `event-envelope`: `{ ts, src, v, session, name, level, ctx, data }`.
  - `save`: `{ version, changelog, dayKey, streak, lastPlayed, perMode, seenInfiniteIds }`; `dayKey` recomputed on read from `date|modeId|gameId|packId` (never trusted).
  - `puzzle-file`: `{ version, changelog, date, items:[{ gameId, packId, difficulty, payload, hints? }] }`.
  - `bank-index`: `{ version, changelog, days:[{date, itemCount}] }`.
  - `anagram-puzzle`: `{ word, tiles:[ezhuthu], reveal?, timeLimitSec, attempts, hints?:[{kind,text,cost}] }`.
- **Events / payloads:** registers the envelope + the standard event names (section 0 catalog); the logger refuses an unregistered `name`.
- **Acceptance gates:** every `config/*.json` + example payload validates; contract-tier tests (reader + writer vs schema) green both sides; drift gate clean.
- **Oracle:** contract - a fixture that omits a required field or mistypes one is rejected by BOTH the Pydantic model and the frontend ajv validator.
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Save `dayKey` recomputed on read from its value fields, never trusted from storage. | Fowler |
  | 2 | Player-facing text in `config/copy.json`; identifiers are separate stable slugs/enums. | Jony + Fowler |
  | 3 | Per-Game payload schemas (not one mega-schema) so Games evolve independently. | Fowler |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | One mega puzzle schema | Couples every Game's evolution; per-Game payloads isolate change. | Fowler |
  | 2 | Trust the stored `dayKey` | A renamed/tampered key mis-routes progress; derive it. | Fowler |

### Row #8 - Corpus ingest + master wordlist (Level 4)
- **Scope:** Stream-process the OLD Tamil corpus plus one fresh open dataset into a ranked, ezhuthu-segmented master wordlist under a versioned schema.
- **Reuse:** `yen-tamizh_OLD/words_and_frequency/` + `src/dictionary/` (incomplete - supplement); relocate `yen-tamizh_OLD/data/wordlists/game_words_{2..6}_letter.json` into `datasets/wordlists/by-length/`.
- **Files touched:**
  - `backend/yen_tamizh_backend/corpus/{ingest,rank}.py` (streaming; never whole-file `json.load`).
  - `backend/yen_tamizh_backend/contracts/master_wordlist.py` -> `schemas/master-wordlist.schema.json`.
  - `datasets/corpus/` (relocated + supplemented sources with a per-source `provenance.json`: source, url, license, bytes), `datasets/wordlists/master/words_ranked.json`.
- **Contracts:** `master-wordlist` row `{ word, ezhuthu:[...], length, freqRank, freqBand, sources:[...], pos?, category? }`.
- **Acceptance gates:** ingest runs within memory on the full corpus; every master row validates; each source has a license row; pytest green.
- **Oracle:** integrity - every master word carries a valid ezhuthu segmentation (Row 6) and a `freqBand`, and the row count reconciles against the ingest logs (no silent drops).
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Corpus = OLD sources + one fresh open Tamil dataset (OLD incomplete); name license + bytes per source. | Fowler (user-directed) |
  | 2 | Master list is the single source of truth; per-Game sets derive from it (Row 9). | Fowler |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | OLD corpus only | User says it is incomplete; short-length gaps starve Word Ladder. | Fowler |
  | 2 | Commit raw multi-MB corpora into the served bundle | Game must never read raw `datasets/`; commit derived output to `frontend/public/` only. | Fowler |

### Row #9 - Derived-wordlist framework + anagram set (Level 3)
- **Scope:** Build the reproducible per-Game derived-set pipeline and produce the anagram-friendly set.
- **Reuse:** the derived-set idea from `yen-tamizh_OLD` PLAN D3/D4.
- **Files touched:**
  - `backend/yen_tamizh_backend/corpus/derive.py`, `backend/yen_tamizh_backend/scripts/rebuild_wordlists.py`.
  - `backend/yen_tamizh_backend/contracts/game_wordlist.py` -> `schemas/game-wordlist.schema.json`.
  - `datasets/wordlists/derived/anagram.json`.
- **Contracts:** `game-wordlist` row `{ word, ezhuthu, freqBand, hints?:{category_ta, first_ezhuthu, length} }`.
- **Acceptance gates:** `rebuild_wordlists` is deterministic (same input -> byte-identical output); anagram set non-empty at each target length; pytest green.
- **Oracle:** by construction, every `anagram.json` entry shares its ezhuthu multiset with >=1 other master word (unscramble tension guaranteed).
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | One `rebuild_wordlists` regenerates all derived sets from the master; sets are build artifacts, never hand-edited. | Fowler |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Hand-curate each Game's list | Not reproducible; drifts from the master on refresh. | Fowler |

### Phase 1 - Shell + Anagram + Daily

### Row #10 - Design system (tokens + animation + glyph bake + manifest) (Level 3)
- **Scope:** Land the CSS design-token layer, the animation keyframe set, and the build-time glyph bake + manifest + `Glyph` component.
- **Reuse:** the token/keyframe patterns from `yen-doku/docs/style.css` (tokens in `:root`, dark-mode override, spring easing, victory/toast/modal/shimmer keyframes, `prefers-reduced-motion` kill-switch).
- **Files touched:**
  - `frontend/src/app.css` (`:root` tokens: `--font-display/mono`, `--space-*`, `--radius-*`, `--shadow-*`, colour set, `--diff-1..4`, `--tile-empty/present/correct/absent`, `--ease`, `--ease-spring`, `--dur-*`; `@media (prefers-color-scheme: dark)`; `[data-theme]` axis).
  - `frontend/tailwind.config.js` (theme.extend mirrors every token as `var(--...)`), `frontend/src/contracts/app-tokens.test.ts` (mirror-or-exempt gate).
  - `frontend/src/designsystem/animations.css`, `frontend/src/designsystem/Glyph.svelte`.
  - `backend/yen_tamizh_backend/glyphs/bake.py` -> `frontend/public/assets/glyphs/index.json`; `backend/yen_tamizh_backend/contracts/glyph_manifest.py` -> `schemas/glyph-manifest.schema.json`.
- **Contracts:** `glyph-manifest` `{ version, changelog, glyphs:{ <id>:{ viewBox, path } } }` (assets referenced by id, per guardrails identifier discipline).
- **Events / payloads:** none (pure chrome + build artifact).
- **Acceptance gates:** every non-exempt `--var` has a Tailwind mirror (contract test); `Glyph.svelte` refuses an unknown id; reduced-motion zeroes durations; browser smoke screenshots light + dark.
- **Oracle:** coverage - every `--token` in `app.css` is referenced in `tailwind.config.js` or in an explicit `exemptFromMirror` set (no orphan token).
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | CSS-event-driven view: state classes + `data-*` attrs drive the look; animation is `transform`+`opacity` only. | Jony + Carmack |
  | 2 | All icons are vector glyphs referenced by id from the baked manifest (Holy Law #10); no inline SVG in components. | Jony |
  | 3 | Theme is a `[data-theme]` token swap so a Journey can carry its palette. | Jony |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Per-component bespoke colours | Breaks the single token source; Jony refuses per-screen components. | Jony |
  | 2 | Inline SVG icons | Not styleable/cacheable as a set; violates Holy Law #10. | Jony |

### Row #11 - Shell + runtime (Level 4)
- **Scope:** Build the `SessionShell` (slots), `SessionRunner`, Game registry, `StorageService`, and the event bus + structured logger.
- **Reuse:** adapt `yen-tamizh_OLD/frontend/src/{shell,session,services,telemetry}` (vanilla TS) to Svelte components + TS services.
- **Files touched:**
  - `frontend/src/shell/SessionShell.svelte` (header/rail/stage/footer slots; rail -> bottom sheet on mobile).
  - `frontend/src/session/{SessionRunner.ts,types.ts}`, `frontend/src/games/registry.ts` (`gameId -> {component loader}`).
  - `frontend/src/services/StorageService.ts` (`localStorage`+`IndexedDB`, `yt:` prefix, save schema from Row 7).
  - `frontend/src/telemetry/{bus.ts,logger.ts}` (emits `event-envelope`; injected via Svelte context).
- **Events / payloads:** Runner emits `mode.session.started`/`completed`; Games receive a `GameContext` (logger, config slice, payload) - no direct calls between Game and storage (section 1a).
- **Acceptance gates:** unit (runner advance, storage round-trip), integration (fake Game renders into `stage` only, save-and-reload resumes mid-session), keyboard reachability of shell controls (v2 a11y), browser smoke clean.
- **Oracle:** integration - a two-item fake Session advances, persists, reloads, and resumes at the same item (state round-trip preserved).
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Games own only `stage`; the shell owns responsive chrome once (DRY UI). | Jony + Fowler |
  | 2 | `StorageService` is the only writer to persistence; Games never touch storage. | Fowler |
  | 3 | Logger/bus injected via context; no `console.log`, no singletons in Game/Mode code. | Fowler |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Per-Game layout | Duplicates responsive logic; Jony refuses per-screen chrome. | Jony |
  | 2 | Games call storage directly | Breaks the single-writer boundary and the payloads-not-calls rule. | Fowler |

### Row #12 - AnagramGame (Level 3)
- **Scope:** Implement Anagram (சொல் கலைப்பு) as a pure-mechanic Game rendering into `stage`, over ezhuthu tiles, with hints and state round-trip.
- **Reuse:** port the mechanic from `yen-tamizh_OLD/frontend/src/games/` (AnagramGame/AnagramMode) into Svelte.
- **Files touched:** `frontend/src/games/anagram/{AnagramGame.svelte,logic.ts,AnagramGame.test.ts}`; registration in `frontend/src/games/registry.ts`.
- **Contracts:** consumes `anagram-puzzle` payload (Row 7).
- **Events / payloads:** emits `puzzle.started`, `puzzle.attempt.submitted {attemptIndex, attempt, correct, elapsedMs}`, `puzzle.hint.used {kind}`, `puzzle.completed {score, attempts, elapsedMs}` / `puzzle.abandoned`.
- **Acceptance gates:** unit (scramble/solve/score over ezhuthu), import-boundary test (imports neither `appConfig` nor `StorageService`), `getState`/`restoreState` round-trip, keyboard play (tab to tiles, Enter to place), browser smoke plays a puzzle.
- **Oracle:** contract - the Game reads only its `payload` + `GameContext` (verified by an import-boundary test).
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Anagram is the first playable Game (proven, fastest vertical slice). | Palm (user-directed) |
  | 2 | Tiles are ezhuthu; score subtracts revealed `hints[].cost`. | Palm |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Word Ladder first | Needs the build-time ladder graph (Row 15) first; higher risk for a first slice. | Palm |

### Row #13 - DailyMode + daily bank generator + Home (Level 4)
- **Scope:** Ship Daily (இன்றைய புதிர்) end-to-end: a date-seeded backend generator bakes today's puzzle-file into the bundle; DailyMode plays it; the Home lists Mode cards.
- **Reuse:** port `yen-tamizh_OLD/backend/src/yen_tamizh_backend` generate + `frontend/src/modes/DailyMode.ts`.
- **Files touched:**
  - `backend/yen_tamizh_backend/generate/anagram.py`, `backend/yen_tamizh_backend/scripts/generate_today.py` -> `frontend/public/bank/<YYYY>/<YYYY-MM-DD>.json` + `frontend/public/bank/index.json`.
  - `frontend/src/modes/DailyMode.ts`, `frontend/src/home/HomeShell.svelte` (Daily enabled; others "coming soon" from `config.ui.enabledModes`).
  - `.github/workflows/daily.yml` (cron 00:05 UTC: run generator, commit `frontend/public/bank/**`, trigger deploy).
- **Contracts:** writes `puzzle-file` + `bank-index` (Row 7); the game loads them same-origin (Holy Law #1 - no external fetch), SW-cached (Row 4).
- **Events / payloads:** backend emits `puzzle.generated {date, gameId, outputPath}` + `bank.updated`; frontend `streak.updated {before, after}` on completion.
- **Acceptance gates:** generator date-seeded idempotent; output validates against `puzzle-file`; frontend loads + plays today's item; streak ticks once/day; browser smoke + one cross-route smoke; e2e first-load-to-playable.
- **Oracle:** determinism - two runs of `generate_today` for the same date produce byte-identical JSON.
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | The bank ships in `frontend/public/` (same-origin, offline), regenerated + committed daily; no CDN. | Fowler + Carmack (Holy Law #1) |
  | 2 | Streak ticks once per completed day, not per item. | Palm |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Serve puzzles from `raw.githubusercontent.com` (yen-tamizh_OLD model) | A runtime external fetch; Holy Law #1 now forbids it. | Fowler |
  | 2 | Generate today's puzzle in the browser | Non-deterministic + unvalidated; generation is build-time. | Carmack |

### Row #14 - Daily playlist + hints (changelog evolution) (Level 3)
- **Scope:** Turn Daily into a playlist of N items with progress + summary, surface the footer hint widget, and evolve the anagram schema additively to carry hints.
- **Reuse:** the playlist/hints model from `yen-tamizh_OLD` PLAN Phase 2.
- **Files touched:** `frontend/src/session/SessionRunner.ts` (inter-item "X of N" + summary), `frontend/src/shell/HintFooter.svelte`, `backend/yen_tamizh_backend/generate/anagram.py` (emit `hints[]`), `schemas/anagram-puzzle.schema.json` (append `changelog` entry, keep same shape valid), `config/app-config.json` (`daily.playlistLength`, `daily.mix`, `hints.*`).
- **Contracts:** demonstrates the evolutionary model - `anagram-puzzle` gains optional `hints[]` as an ADDITIVE change: append `{version: <today>, change, why}` to `changelog`, no migration; old bank files still validate.
- **Acceptance gates:** playlist of N plays with progress + summary; hint visibility honors config; a pre-hints fixture still validates after the append (contract test); browser smoke.
- **Oracle:** backward-compat - a pre-hints `anagram-puzzle` fixture validates unchanged after the `changelog` append (additive, no break), proving "refresh data without rebuilding mechanics".
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Playlist length + mix are config, not code. | Fowler |
  | 2 | Hints land as an additive `changelog` entry, not a breaking bump. | Fowler |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Treat hints as a breaking change | Additive optional fields keep old payloads valid; no migration needed. | Fowler |

### Phase 3 - Word Ladder + Journey

### Row #15 - Ladder graph builder + word-ladder schema (Level 5)
- **Scope:** Build the offline add-one-ezhuthu reachability graph and emit validated Word Ladder puzzles, seeding from a curated list where Tamil density is thin.
- **Reuse:** master wordlist (Row 8) + ezhuthu library (Row 6); greenfield graph builder.
- **Files touched:** `backend/yen_tamizh_backend/generate/word_ladder.py` (graph over master; rung = +1 ezhuthu, rearrange allowed; validate a solvable chain), `backend/yen_tamizh_backend/contracts/word_ladder_puzzle.py` -> `schemas/word-ladder-puzzle.schema.json`, `datasets/wordlists/derived/ladder.json`, `datasets/curated/ladder_seeds.json`.
- **Contracts:** `word-ladder-puzzle` `{ rungs:[{ word, ezhuthu, added? }], startEzhuthuCount, timeLimitSec }`.
- **Acceptance gates:** every emitted ladder validated solvable rung-by-rung; pytest covers the reachability + rearrange rule over ezhuthu; drift gate clean.
- **Oracle:** validity - for each emitted ladder, consecutive words differ by exactly one added ezhuthu under a multiset+rearrange check (proven before ship).
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Ladder reachability computed + validated at build time; the browser only plays proven ladders. | Fowler + Carmack |
  | 2 | Seed from a curated list where short-length Tamil density is thin. | Palm + Fowler |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Compute reachability in the browser | Runtime compute forbidden (Holy Law #1); risks shipping an unsolvable puzzle. | Carmack |
  | 2 | Pure-search ladders only | Sparse short-word graph may yield no chain; curated seeds guarantee content. | Palm |

### Row #16 - WordLadderGame + share-result card (Level 3)
- **Scope:** Implement Word Ladder (ஒரு எழுத்து ஏற்று) with the rung UI, the +ezhuthu badge, TIME/INSTINCT/RETRIES/STREAK stats, and a shareable result card.
- **Reuse:** the playonemoreletter reference (proposal section 4); shell chrome from Row 11.
- **Files touched:** `frontend/src/games/word-ladder/{WordLadderGame.svelte,logic.ts,ShareCard.svelte}` + registry.
- **Contracts:** consumes `word-ladder-puzzle` (Row 15).
- **Events / payloads:** standard Game events; stats derived from `puzzle.attempt.submitted`/`completed` payloads (no new save fields).
- **Acceptance gates:** unit (rung validation over ezhuthu, stat derivation), share card renders from telemetry-derived stats, no-network assertion, keyboard play, browser smoke completes a ladder.
- **Oracle:** the four completion stats are each derivable purely from emitted events (no bespoke save field).
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Stats derive from standard telemetry payloads, not new save fields. | Fowler |
  | 2 | Share is a locally-rendered card (image/text), no network call. | Jony + Player |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | A share endpoint / server card | Violates static-first no-backend; render locally. | Fowler |

### Row #17 - JourneyMode + winding-path home (Level 4)
- **Scope:** Add the Journey Mode (பயணம்) and the winding-path node map as its level-select chrome, driven by a `journey` definition.
- **Reuse:** the Phase-8 winding-path motif from `yen-tamizh_OLD` PLAN.
- **Files touched:** `frontend/src/modes/JourneyMode.ts`, `backend/yen_tamizh_backend/contracts/journey.py` -> `schemas/journey.schema.json`, `frontend/src/home/JourneyMap.svelte` (nodes, unlock state, mascot glyph), `datasets/journeys/*.json` (e.g. Beginner's Ladder), `config/app-config.json` (`ui.enabledModes`).
- **Contracts:** `journey` `{ version, changelog, id, title_ta, theme, nodes:[{ id, gameId, packId, difficulty, unlockRule }] }`.
- **Acceptance gates:** a journey definition validates; completing a node unlocks the next; map renders horizontal (desktop) + vertical (mobile); keyboard-navigable nodes; browser smoke.
- **Oracle:** progression - node N+1 is playable iff node N is recorded complete (unlock invariant vs the save).
- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | A Journey is a data-defined ordered Session; new journeys = new data, not new code. | Fowler + Palm |
  | 2 | The winding-path map is Journey chrome doubling as level-select; layout swaps by breakpoint. | Jony |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Hardcode journeys in code | Blocks authoring new paths without a redeploy; keep them as data. | Fowler |

### Phase 4-7 - Games (each follows the add-a-game pattern proven by Row 12; each: Svelte Game into `stage` + a `backend/` generator + a per-Game payload schema via Row 5 + a derived wordlist via Row 9)

### Row #18 - MissingLettersGame + gen + derived set (Level 3)
- **Scope:** Add Missing Letters (இடைவெளி நிரப்பு): blank whole ezhuthu of a shown word.
- **Files touched:** `frontend/src/games/missing-letters/*` + registry; `backend/yen_tamizh_backend/generate/missing_letters.py`; `backend/.../contracts/missing_letters_puzzle.py` -> `schemas/missing-letters-puzzle.schema.json`; `datasets/wordlists/derived/missing-letters.json`.
- **Acceptance gates:** blanking on whole ezhuthu; generator output validates; unit + import-boundary + keyboard + browser smoke; Daily `mix` can include it.
- **Oracle:** contract - reads only payload + context (import-boundary test), same gate as Row 12.
- **Decisions:** blank whole ezhuthu, never a partial cluster (Player + Fowler).
- **Rejected alternatives:** codepoint-level blanking - produces unreadable partial clusters (Player).

### Row #19 - WordleGame + gen + derived set (Level 3)
- **Scope:** Add Wordle-style (சொல் யூகி): guess an N-ezhuthu word with present/correct/absent feedback and an ezhuthu keyboard.
- **Files touched:** `frontend/src/games/wordle/*` (+ ezhuthu composer keyboard: uyir/mei/uyirmei) + registry; `backend/.../generate/wordle.py`; `schemas/wordle-puzzle.schema.json`; `datasets/wordlists/derived/wordle.json` (exactly 5 ezhuthu, common/mid band).
- **Acceptance gates:** feedback computed over ezhuthu (not codepoints); flip/shake animations honor reduced-motion; unit + keyboard + browser smoke.
- **Oracle:** feedback correctness - a known guess/answer pair yields the exact present/correct/absent vector over ezhuthu.
- **Decisions:** "letter" = ezhuthu; on-screen keyboard is an ezhuthu composer (Player + Jony).
- **Rejected alternatives:** Latin single-key input - Tamil composes clusters; unplayable (Player).

### Row #20 - WordSearchGame + gen + derived set (Level 3)
- **Scope:** Add Word Search (சொல் தேடல்): trace hidden words in an ezhuthu grid across 8 directions.
- **Files touched:** `frontend/src/games/word-search/*` (drag + keyboard trace) + registry; `backend/.../generate/word_search.py` (place words, fill grid); `schemas/word-search-puzzle.schema.json`; `datasets/wordlists/derived/word-search.json`.
- **Acceptance gates:** placement generator validates every hidden word is traceable; pointer + keyboard trace; unit + browser smoke.
- **Oracle:** placement - every target word in a generated grid is recoverable by a straight-line ezhuthu trace in one of 8 directions.
- **Decisions:** grid cells are ezhuthu; tracing/matching over ezhuthu identity (Fowler).
- **Rejected alternatives:** codepoint grid - splits clusters across cells; untraceable (Player).

### Row #21 - CrosswordGame + placement solver + derived set (Level 5)
- **Scope:** Add a mini Crossword (சொற்கட்டம்) whose interlocking layout is placed by a build-time solver.
- **Files touched:** `frontend/src/games/crossword/*` + registry; `backend/.../generate/crossword.py` (constraint/OR-Tools placement on shared ezhuthu); `schemas/crossword-puzzle.schema.json`; `datasets/wordlists/derived/crossword.json`.
- **Acceptance gates:** solver emits a fully-interlocked, uniquely-fillable mini grid; validation fails CI on a bad grid; unit + keyboard + browser smoke.
- **Oracle:** interlock - every crossing cell holds one ezhuthu satisfying both its across and down entries (whole-grid constraint satisfied).
- **Decisions:** placement is a build-time solver in `backend/`; interlock on ezhuthu identity (Carmack + Fowler).
- **Rejected alternatives:** runtime placement - expensive + risks an unsolvable grid; solve in CI (Carmack).

### Phase 8 - Modes

### Row #22 - InfiniteMode + bulk pool + index (Level 4)
- **Scope:** Add Infinite (முடிவில்லா): a lazy anti-repeat stream over a pre-generated, bundle-shipped pool, difficulty-bucket pickable.
- **Files touched:** `backend/yen_tamizh_backend/scripts/generate_infinite.py` -> `frontend/public/pool/<gameId>/NNNNN.json` + `frontend/public/pool/<gameId>/index.json` (schema `pool-index`); `frontend/src/modes/InfiniteMode.ts`; `frontend/src/services/StorageService.ts` (`seenInfiniteIds` LRU via `config.infinite.lruWindow`); Home enables the Infinite card.
- **Contracts:** `pool-index` `{ version, changelog, items:[{ id, difficulty }], totalCount }`.
- **Acceptance gates:** pool + index validate; no repeat within the configured LRU window; difficulty filter works; SW-cached same-origin (offline); browser smoke streams items.
- **Oracle:** anti-repeat - across `lruWindow+1` picks, no item recurs within the window (invariant vs `seenInfiniteIds`).
- **Decisions:** Infinite reuses existing Game pools (new Session framing, no new Game); LRU window + default difficulty are config (Fowler).
- **Rejected alternatives:** generate infinite items in the browser - runtime compute forbidden; pre-generate in CI (Carmack).

### Row #23 - TimeTrialMode (Level 3)
- **Scope:** Add Time Trial (நேர சவால்): as many items as fit in a configured duration, header countdown, local-only best runs.
- **Files touched:** `frontend/src/modes/TimeTrialMode.ts`, `frontend/src/shell/CountdownHeader.svelte`, `config/app-config.json` (`timeTrial.durationSec`), Home enables the card.
- **Contracts:** best-runs stored in the `save` schema (Row 7), local only.
- **Acceptance gates:** countdown drives session end via `requestAnimationFrame` (not `setInterval`); best run persists locally; browser smoke runs a sprint.
- **Oracle:** the session ends within one frame of the configured duration and records items-completed (timer correctness).
- **Decisions:** reuses Infinite pools; leaderboards local-only; timing via `requestAnimationFrame` (Fowler + Carmack).
- **Rejected alternatives:** global/online leaderboard - needs a backend + accounts, both non-goals (Fowler).

---

## 3. Execution stamp

`Execute per docs/how-to/execute-a-plan.md: orchestrator dispatches one worktree-isolated worker subagent per row; workers consult personas (Fowler/Carmack/Jony/Palm/Player/Explore) on ambiguity; AUTO-merge on green gates; parallel N = 2; honor the ESCALATE triggers in section 0. EXECUTING (user-authorized 2026-08-13). Rows 1-3 DONE (Row 1 = 2026-07-25 contract commit; Row 2 = PR #1; Row 3 = PR #2, skeleton green on CI). Frontier = Group B {4, 5, 6}: Rows 4 (PWA, Level 4) and 6 (ezhuthu, Level 4) are AUTO-dispatchable in parallel; Row 5 (contract pipeline, Level 5) is an ESCALATE pause awaiting user sign-off before merge.`

## See also

- [`README.md`](README.md) - the system-design proposal this plan implements.
- [`../CLAUDE.md`](../CLAUDE.md) - the engineering contract (sections 1a, 3, 4, 11 this plan aligns to).
- [`../docs/how-to/author-a-plan.md`](../docs/how-to/author-a-plan.md) - the authoring format this doc follows.
- [`../docs/agents/bootstrap.md`](../docs/agents/bootstrap.md) - the autonomy policy the execution stamp cites.
- [`../docs/agents/guardrails.md`](../docs/agents/guardrails.md) - Holy Laws, non-goals, schema + path + identifier discipline every row honors.
- [`../docs/how-to/ship-to-github-pages.md`](../docs/how-to/ship-to-github-pages.md) - base-path, SPA fallback, PWA + service-worker contract (Row 4).
</content>
