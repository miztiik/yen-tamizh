# CLAUDE.md - yen-tamizh Engineering Contract

**Last Updated**: 2026-07-25

Non-negotiable contract for any human or AI agent working in this repo.

You are a game development agent.

## 0. User Approval

User approval supersedes every agent and every rule in this file. Amend conflicting rules in the same commit.

## 0a. Non-Goals

- ~~**Accessibility** (a11y / ARIA / WCAG / axe-core / contrast-ratio tooling / screen-reader hints). Descoped at project level. No a11y deps, assertions, agent doctrine, or `aria-*` enforcement. Re-scope by editing this entry.~~ However, **basic ARIA + keyboard nav are IN scope** as of v2 production polish: visible focus rings, labelled controls, semantic landmarks, keyboard reachability of every interactive surface, screen-reader-friendly button names. The line is: design-level a11y choices (label your buttons, use real semantics) are encouraged; framework / audit tooling is not. Still descoped: no a11y deps, no automated audits, no doctrine pass that gates merges on WCAG levels.
- **Production backend.** See Holy Law #1.
- **Account systems** (login, signup, email collection, cross-device sync that requires a server). Game state is `localStorage` / `IndexedDB` only.
- **Push notifications.** The player decides when to play.
- **Runtime telemetry / analytics SDKs / third-party scripts that fetch at runtime.** Static-first means no runtime calls home. Measure perf locally in DevTools.

## 1. Holy Laws (Read First, Every Session)

1. **Static-first production.** The deployed game is a static bundle on GitHub Pages. No production backend, no runtime fetches, no runtime servers, no runtime compute. Everything the game needs at runtime ships in the bundle and works offline. No runtime telemetry / analytics / error-tracking SDKs, no runtime ads or monetisation, no runtime account system, no runtime push notifications. The player decides when to play.
2. **The player's phone is the architecture.** Every runtime decision is measured against a mid-tier Android (Snapdragon 6-series, 4GB RAM, ~2022) over patchy 4G: input-to-photon < 50ms, sustained 60fps. Ship the richer game first, then optimize (code-split, lazy-load, WASM, asset compression) only when the target device drops below 60fps. No fixed byte cap.
3. **Contracts before logic.** Every persisted shape - save format, level / puzzle data, config, asset manifest - gets a typed schema in `schemas/` before logic is written.
4. **docs/ = agent memory; a decision lives on the page it impacts.** Gameplay rules, UI shape, tuning knobs, and current subsystem contracts live in `docs/concepts/`, `docs/how-to/`, or the relevant `docs/architecture/<area>/` living doc. A choice that clears the bar (a real rejected alternative, cross-system consequences, non-trivial reversal cost) is recorded IN the living doc it impacts, as a `## Design rationale` / `## Rejected alternatives` section on that page - never as a standalone record. There is no ADR file and no `docs/architecture/decisions/` directory; the page a reader searches for the behaviour is the page that explains why it is that way.
5. **Structural fixes only.** No band-aids, no monkey patches, no "temporary" hacks. Escalate the correction level instead.
6. **No hardcoding.** Tunable knobs (game-balance numbers, asset paths, difficulty thresholds) live in `config/`; schema-validated.
7. **No mocks unless asked.** Real implementations and real fixtures. Mocks only on explicit user request or for genuinely untestable external boundaries (a WASM module in unit tests, `fetch` in loader unit tests).
8. **Open source first.** Prefer mature OSS over custom builds. Every dependency must name a beneficiary feature and its byte cost.
9. **Tests ship with the feature.** Behaviour-changing commit lands with tests. Full suite green at merge.
10. **Use Glyphs** (or equivalent) for all icons. Glyphs are vector, small, and styleable.

## 1a. Architecture Principles

These operationalize the Holy Laws and shape every subsystem.

- **Event-driven.** Subsystems communicate through structured-payload events, never direct method / procedure / process calls. The contract between the frontend and the build-time backend, and between runtime modules, is a typed event carrying a serializable payload - not a function signature.
- **Asynchronous, non-blocking.** Every event is dispatched async; nothing blocks the main thread. The render loop keeps painting so the game stays responsive (Holy Law #2) - which is what makes rich animation, and stickiness, possible.
- **Payloads, not calls.** Data crossing any boundary is a serializable structured payload (JSON-shaped), so it can be logged, validated, replayed, and tested with real fixtures - never an in-process object handed across a call.
- **Config-driven, sane defaults.** Both the frontend and the build-time backend read tunable behaviour from `config/`; every knob has a sane default; a fresh clone runs on the defaults (Holy Law #6).
- **Schema-first.** Every config file and every persisted payload conforms to a typed schema in `schemas/`; a config or payload that fails its schema fails the build (Holy Law #3).
- **Visual feedback is first-class.** Animation, colour cues, and motion that confirm a player's input are expected, not optional - they are what make the game feel responsive and sticky. This is game feel, not accessibility tooling (section 0a).

## 2. Path Rules

For anything leaving the process (JSON, logs, asset manifests, agent memory, error messages, doc cross-links):

- Relative paths only. No absolute paths. No drive letters.
- POSIX separators only (`/`). Never `\`.
- Minimal reconstructable form.

In-memory `Path` objects for local I/O may stay platform-native. Rule applies at the moment a path leaves the process.

## 3. Repository Topology

| Directory            | Status     | Purpose                                                                                                      |
| -------------------- | ---------- | ------------------------------------------------------------------------------------------------------------ |
| `CLAUDE.md`          | created    | This file - the engineering contract.                                                                        |
| `README.md`          | created    | Entry point.                                                                                                  |
| `docs/`              | partial    | Canonical knowledge (Diataxis tiers, 3-level depth).                                                          |
| `.claude/skills/`    | created    | Claude Code skill wrappers (bootstrap, prepare-plan) that point at `docs/`.                                   |
| `.github/agents/`    | created    | Persona advisors (Carmack, Fowler, Jony, Palm, Player).                                                       |
| `.github/workflows/` | created    | CI, daily bank generation, and GitHub Pages deploy.                                                           |
| `config/`            | planned    | Human-edited tunable knobs (game balance, thresholds), schema-validated. Read by `frontend/` and `backend/`. |
| `schemas/`           | planned    | Typed schema every config and persisted payload conforms to (Holy Law #3, section 1a). Mandatory.            |
| `backend/`           | planned    | Build-time producer (Python): corpus ingest, generate, solve/validate, bake. `backend/utilities/` for helpers; NOT a runtime server (Holy Law #1). |
| `datasets/`          | planned    | Raw + cleaned source corpora the backend reads. Never read directly by the game.                             |
| `frontend/`          | planned    | The web app: `package.json`, `vite.config.ts`, `svelte.config.js`, `tsconfig.json`, `index.html`, `src/`, `public/`, `tests/`. |
| `assets/`            | planned    | Source assets pre-pipeline (raw art, sounds). Never read directly by the game; the backend bakes them.       |
| `frontend/dist/`     | gitignored | Built bundle for GitHub Pages.                                                                                |
| `TODO/` `notes/`     | optional   | Working scratchpads - non-authoritative.                                                                     |

Folders are created only when real code is about to land. The first real PR picks the build tool (Vite / esbuild / plain), the language (TypeScript / vanilla), and the component layer (Svelte / vanilla); those picks land alongside the code, not as speculative scaffolding.

## 4. Layer and Dependency Rules

- `frontend/src/` MUST NOT depend on a runtime backend service - there is none in production.
- The build-time producer is `backend/` (Python: corpus ingest, generate, solve/validate, bake). It writes pipeline output into `frontend/public/` at build time; the game reads only that output, never raw `assets/` or `datasets/` sources.
- Game / domain code MUST NOT import backend / build code, and the backend MUST NOT import frontend code. They meet only through committed data (Holy Law #1, section 1a).
- The game canvas is one DOM element styled by Tailwind to fit its container. **Tailwind does NOT style canvas internals** - those are the renderer's job. (Jony's canvas-boundary constraint, Carmack worldview #20.)
- Long compute (any physics step, pathfinding, procedural generation) runs in a Web Worker. The main thread keeps painting.
- Subsystems talk in events with structured payloads, not cross-boundary calls (section 1a).

## 5. Documentation Discipline

- Diataxis tiers under `docs/`: `architecture/`, `how-to/`, `concepts/`, `reference/` (+ `getting-started/`, `archive/`, `research/`).
- Max depth: `docs/<tier>/<topic>/<file>.md`.
- Every doc: H1 title, `Last Updated: YYYY-MM-DD`, "See also" cross-links.
- One concept defined once; everywhere else links to it.
- ASCII-only in all repo text: commit messages, docs, code comments, log strings, agent markdown, CLI output (use `-`, `->`, `>=`, and "section"). No curly quotes, em-dashes, or non-ASCII symbols. Applies going forward; no retroactive fixing.
- Agent memory (`AGENTS.md`, `/memories/repo/`) is derived, not authoritative; if it disagrees with `docs/`, docs win.
- Architecture decisions are recorded IN the living doc they impact, never as standalone records under a `decisions/` directory. When a choice clears the Holy Law #4 bar (real rejected alternative, cross-system consequences, non-trivial reversal cost), capture its rationale and the rejected alternative as a `## Design rationale` / `## Rejected alternatives` section on the concept / how-to / subsystem doc where the decision takes effect; git history is the immutable record of when it changed. Most changes are not decisions at all - they update an existing concept, how-to, reference, or subsystem doc in place.
- Open questions live in the active plan-doc under `TODO/`, not in this file.
- Docs-only PRs are a code smell.

## 6. Correction Levels

| Level | Scope                                                      | Workflow                              |
| :---: | ---------------------------------------------------------- | ------------------------------------- |
|   0   | Comments, typos, log strings                               | Direct fix                            |
|   1   | 1 file, ~50 lines, isolated bug                            | Direct fix                            |
|   2   | 1-2 files, explicit behavior change                        | Plan -> execute once scope is clear   |
|   3   | 2-3 files, cross-cutting                                   | Plan -> phased execution              |
|   4   | 4+ files, structural                                       | Propose breakdown first               |
|   5   | Core design / save format / renderer / physics-engine pick | Design consultation only - pause work |

When in doubt, choose the higher level.

## 7. Debug Logging

- Temporary logs MUST be prefixed `[DEBUG]`.
- Before finalizing: grep for `[DEBUG]` and remove every match. Re-run tests after cleanup.

## 8. Git Hygiene

User saying finish / ship / merge authorizes the normal reversible git workflow: inspect, named branch, stage exact paths, commit, push, gates, merge.

Avoid (broad / lossy / history-rewriting):

- `git stash`
- `git reset --hard`
- `git clean -fd`
- `git checkout .` / broad `git restore .`
- `git add .` / `git add -A`
- `git push --force` / `git push --force-with-lease`
- Amending pushed commits
- Leaving a merged PR's remote branch undeleted or its `: gone]` local tracking branches unpruned.

Safe workflow: `git status --porcelain`, leave unrelated dirty files alone, stage only explicit paths, verify with `git diff --cached --name-only`, small reversible commits on a named branch, push, merge after gates pass.

Commit messages describe the change. **No AI co-author / attribution tags.**

## 9. Definition of Done

- [ ] Tests added/updated at the tier appropriate to the surface (section 13). No mocks per Holy Law #7.
- [ ] Full suite green locally before commit.
- [ ] Lint, type-check, tests all pass.
- [ ] For runtime changes: smoke-tested via integrated browser tools per section 12 - including a perf check against the target device profile when the change touches the render loop, physics, or asset load.
- [ ] Canonical docs updated in `docs/` (right tier).
- [ ] Schemas version-stamped + changelogged (and migrated if breaking) when any persisted contract changed (save format, level / puzzle data, config, asset manifest - section 11).
- [ ] Module `AGENTS.md` updated if structure or invariants changed.
- [ ] No `[DEBUG]` markers left.
- [ ] No new hardcoded values.
- [ ] No new mocks unless explicitly requested.
- [ ] Lockfiles in sync with manifests.
- [ ] Responsiveness held on the target device (60fps, input-to-photon <50ms). No fixed byte cap; optimize only if the device drops below target.
- [ ] Frame budget respected (no new feature drops the target device profile below 60fps).

## 10. Anti-Patterns (Do NOT)

- Reinterpret, downgrade, substitute, or scope-narrow a source or instruction the user named explicitly, without surfacing it as a scope change for sign-off (STOP-AND-SURFACE).
- Assume a backend exists in production.
- Hardcode game-balance values, asset paths, level-difficulty thresholds, magic strings. They live in `config/`.
- Store absolute / backslash paths in any persisted artifact.
- Build custom HTTP / retry / parsing / validation / physics / rendering / particle systems when a mature OSS library exists. Justify any custom build against the OSS alternative.
- Swallow exceptions or silently coerce invalid input - fail fast at the boundary.
- Mock in tests by default.
- Run a renderer / physics step / animation on the main thread when it can be offloaded to a Web Worker.
- Use `setTimeout` / `setInterval` for game-loop timing. Use `requestAnimationFrame`.
- Ship a layout-triggering CSS animation when `transform` + `opacity` will do.
- Style canvas internals with Tailwind. Tailwind is for the chrome (HUD, menu, modal); the canvas is the renderer's job.
- Add a runtime telemetry / analytics / error-tracking SDK.
- Add a monetisation pattern (ads, IAP, timers, lives-with-IAP, pay-to-skip, streak-savers).
- Ship a feature that depends on a runtime backend, account, or push notification.
- Add a framework / library / build tool without naming the bytes it adds and the beneficiary feature.
- Pick the renderer / physics engine in isolation. Carmack (Engine & Runtime) picks both together, with the dimensionality, body-count budget, and determinism requirement named in writing.
- Mint a new save-format / level-data field without stamping the schema `version` date, appending a `changelog` entry, and writing the read-side migration in the same commit.
- Lower the perf target to fit a feature. The target is the player's phone, not the feature - if the feature can only run at 20fps on the target device, the feature is removed or simplified.
- Let `TODO/`, chat logs, `AGENTS.md`, or `/memories/` become the source of truth for architecture.
- Pre-create empty modules "for later".
- Skip the docs update.

## 11. Schema Versioning

Every config file and every persisted surface conforms to a typed schema in `schemas/` before logic is written (Holy Law #3, section 1a). The persisted surfaces this project cares about:

- **Save format** (`localStorage` / `IndexedDB` JSON) - owned by the game; consumed by the next version of the game. Older saves must continue to load (one or two versions back) or be migrated on read.
- **Level / puzzle data** (per-level JSON shipped in the bundle).
- **Config** (the tunable knobs in `config/`).
- **Asset + glyph manifest** (the index of in-bundle assets).

### `version` is a date-stamp, not an integer

Each schema carries a `version` field that is a human-readable date-stamp - never an integer, never an epoch timestamp:

- Format: `YYYY-MM-DD` (e.g. `2026-07-25`). When more than one change lands the same day, extend to the minute or second: `YYYY-MM-DDTHH:MM` or `YYYY-MM-DDTHH:MM:SS`.
- The value is ASCII-sortable and self-documenting: `version` tells you *when* the shape last changed, and equals the newest `changelog` entry's version.

### `changelog` array (in-schema change log)

Each schema carries a `changelog` array - newest entry first - recording every change and why it was made. Each entry is `{ version, change, why }`:

- `version` - the date-stamp of that change (same format as above).
- `change` - what changed (field added / removed / retyped, semantics shifted).
- `why` - the reason for the change.

Each change is one commit:

- **Additive, backwards-compatible** (new optional field): append a `changelog` entry, set `version` to today; older payloads still validate.
- **Breaking** (removed field, type change, semantic shift): append a `changelog` entry, set `version` to today, AND write the read-side migration the new build runs on older payloads - same commit.

A player whose save from yesterday no longer loads today is a contract break and a release blocker.

## 12. UI Verification (Browser Smoke)

Any runtime change MUST be verified by the agent using integrated browser tools, not deferred to the human.

Minimum loop:

1. Confirm dev server up; start if not.
2. Navigate to affected route(s) plus one cross-route smoke.
3. Read page console; confirm zero new `[error]` events and zero new `404`.
4. If layout-sensitive: screenshot to confirm visual intent.
5. If perf-sensitive (render loop, physics, asset load): open DevTools Performance, throttle CPU 4x + Network "Slow 4G", record an interaction, confirm the relevant Carmack budget (worldview #9-15).
6. Only then mark done.

Does not apply to pure tooling / docs / schema-only changes.

## 13. Test Coverage Policy

Four tiers - **Unit / Contract / Integration / End-to-end**. Change without an appropriate-tier test in the same commit is a Definition-of-Done failure. Mock carve-outs: (a) `fetch` in loader unit tests, (b) a WASM module in unit tests, (c) explicit user request.

Per tier:

- **Unit** - pure functions (math, score, level validation, save-data serialization round-trip).
- **Contract** - the schemas (save format, level data, asset manifest) vs the readers and the writers.
- **Integration** - game logic + renderer + physics engine working together at a level boundary, with real fixtures.
- **End-to-end** - Playwright (or equivalent) drives the actual game in a real browser. Cover at minimum: first-load to playable, one level start-to-win, save-and-reload preserves progress.

No pytest / vitest / playwright test fetches the network at runtime - use local fixtures.

## 14. Agent Roster

Five persona advisors live under `.github/agents/`, each at a distinct altitude:

| Agent                               | File               | Altitude                                                              |
| ----------------------------------- | ------------------ | --------------------------------------------------------------------- |
| Player                              | `player.agent.md`  | mental model of the median casual-game player                         |
| Jony (UI/UX)                        | `jony.agent.md`    | game chrome (HUD, menu, modal, settings)                              |
| Palm (Casual Design)                | `palm.agent.md`    | game verb / level shape / progression curve                           |
| Fowler (Architecture & Engineering) | `fowler.agent.md`  | architecture + contracts + commits + tests                            |
| Carmack (Engine & Runtime)          | `carmack.agent.md` | renderer + physics + asset pipeline + frame budget + bundle + offline |

Rule: adding a new agent requires justifying a distinct altitude not already covered. Two agents at the same altitude collapse into one (see Fowler's 4-head construction).

## See also

- [`docs/agents/bootstrap.md`](docs/agents/bootstrap.md) - the load ritual every persona runs before answering.
- [`docs/agents/guardrails.md`](docs/agents/guardrails.md) - the rules-only digest of this contract.
- [`docs/reference/documentation-structure.md`](docs/reference/documentation-structure.md) - where each kind of doc lives.
- [`TODO/README.md`](TODO/README.md) - the system-design proposal this contract serves.
