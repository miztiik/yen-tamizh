# Agent Guardrails

**Last Updated**: 2026-07-04

This is the rules-only digest every persona must honour. It restates `CLAUDE.md` constraints in one place so an agent can scan the constraints quickly and so other docs (design-rationale sections, agent files, code reviews) can link to specific rules. The authoritative source remains [`CLAUDE.md`](../../CLAUDE.md); if this doc and `CLAUDE.md` disagree, `CLAUDE.md` wins and this digest gets updated.

Loaded by [`bootstrap.md`](bootstrap.md) as part of every persona's startup ritual.

Agent/customization Markdown is ASCII-only: write "-", "->", ">=", and "section" instead of fancy symbols.

**Authority assignment** (resolves stalled agent debates). The five personas live under [`.github/agents/`](../../.github/agents/); each owns one altitude (`CLAUDE.md` section 14):

| Decision class | Authority |
| --- | --- |
| Renderer / physics engine / asset pipeline / frame budget / bundle weight / offline (service-worker) contract | **Carmack** (Engine & Runtime) |
| Architecture / persisted contracts (save format, level data, asset manifest) / schema versioning / test tiers / refactor safety / module structure / when to delete | **Fowler** (Architecture & Engineering; his construction folds in Gregor Hohpe for contract + integration calls) |
| Game chrome (HUD, menu, level-select, settings, modal, win/lose) / colour system / gestures / micro-animation / visual bounds | **Jony** (UI/UX) |
| Casual design (game verb, level shape, progression curve, reward loop, difficulty tuning, the "one more turn" hook) | **Palm** (Casual Design) |
| Player reality check (playable in 60s? language understood? holds on a mid-tier Android over patchy 4G?) | **Player** |

Adding a sixth persona requires a distinct altitude not already covered; two personas at the same altitude collapse into one (`CLAUDE.md` section 14).

**User approval supersedes every agent and every rule.**

## Holy Laws (cite by number when relevant)

1. **Static-first production.** The deployed game is a static bundle on GitHub Pages. No production backend. Everything the game needs at runtime ships in the bundle.
2. **The player's phone is the architecture.** Every runtime decision is measured against a mid-tier Android (Snapdragon 6-series, 4GB RAM, ~2022) over patchy 4G: input-to-photon < 50ms, sustained 60fps. Ship the richer game first, then optimize (code-split, lazy-load, WASM, asset compression) only when the target device drops below 60fps. No fixed byte cap.
3. **Contracts before logic.** Every persisted shape - save format, level data, asset manifest - gets a typed schema before logic is written.
4. **docs/ = agent memory; a decision lives on the page it impacts.** Gameplay rules, UI shape, tuning knobs, and subsystem contracts live in `docs/concepts/`, `docs/how-to/`, or `docs/architecture/<area>/`. A choice that clears the bar (real rejected alternative, cross-system consequences, non-trivial reversal cost) becomes a `## Design rationale` / `## Rejected alternatives` section on the living doc it impacts - no ADR file, no `docs/architecture/decisions/` directory.
5. **Structural fixes only.** No band-aids, no monkey patches, no "temporary" hacks. Escalate the correction level instead.
6. **No hardcoding.** Tunable knobs (game-balance numbers, asset paths, difficulty thresholds) live in `config/`; schema-validated.
7. **No mocks unless asked.** Real implementations and real fixtures. Mocks only on explicit request or for a genuinely untestable external boundary (`fetch` in loader unit tests, a WASM module).
8. **Open source first.** Prefer mature OSS over custom builds. Every dependency names a beneficiary feature and its byte cost.
9. **Tests ship with the feature.** A behaviour-changing commit lands with tests at the tier that matches the surface (`CLAUDE.md` section 13). Full suite green at merge.
10. **Use Glyphs for all icons.** Glyphs are vector, small, and styleable; reference them by id from the generated manifest, never inline SVG.

## Project-level non-goals (do NOT raise these)

- **Production backend.** No backend at runtime (Holy Law #1). `tools/` is a build-time pipeline only.
- **Account systems** (login, signup, email collection, server-backed cross-device sync). Game state is `localStorage` / `IndexedDB` only.
- **Push notifications.** The player decides when to play.
- **Runtime telemetry / analytics SDKs / third-party scripts that fetch at runtime.** Static-first means no runtime calls home; measure perf locally in DevTools.
- **Monetisation patterns** (ads, IAP, timers, lives-with-IAP, pay-to-skip, streak-savers). Hobby project; if monetisation ever lands, the contract changes first.
- **Accessibility framework / audit tooling** (axe-core, WCAG-level gating, automated contrast checks, a11y deps). Descoped at project level. BUT basic ARIA + keyboard nav ARE in scope as of v2 polish: visible focus rings, labelled controls, semantic landmarks, keyboard-reachable interactive surfaces, screen-reader-friendly button names. Design-level a11y (label your buttons, use real semantics) is encouraged; framework/audit tooling and merge-gating on WCAG are not. See `CLAUDE.md` section 0a.

## Git hygiene for autonomous work

A user's finish/ship/merge instruction authorizes the reversible git workflow: inspect state, stage explicit paths, commit, push, run gates, and merge or enable automerge when green.

Stop only when the next action would discard or overwrite unrelated work, rewrite published history, broadly mutate the working tree, or when ownership is ambiguous after inspection.

Avoid stash, hard reset, clean, broad restore, add-all, force push, and amending pushed commits in autonomous flow.

Commit messages describe the change. **No AI co-author / attribution tags.**

## Path discipline (for persisted artifacts)

For anything leaving the process (JSON, logs, asset manifests, save data, level data, agent memory, error messages, doc cross-links):
- Relative paths only. No absolute paths, no drive letters.
- POSIX separators (`/`) only. Never `\`.
- Minimal reconstructable form.

In-memory `Path` objects for local I/O may stay platform-native; the rule applies at the moment a path leaves the process.

## Identifier and copy discipline

- Stable IDs (`tier`, `shapeId`, scenario / puzzle slug, glyph pack + slug) are schema-validated enums or slugs defined in `config/` and `datasets/`. Never invent or reformat an ID in code.
- Reference assets by id from the generated manifest (`frontend/public/assets/glyphs/index.json`), never by inline SVG or hardcoded path (Holy Law #6, #10).
- A derived key is rebuilt from its value fields, never trusted from the incoming payload (e.g. the save `dayKey = 'date|tier|shapeId'` is recomputed on read).
- Player-facing text lives in `config/copy.json`. Display titles and labels are fields, never identifiers.

## Layer / dependency rules

- `frontend/src/` MUST NOT depend on a runtime backend service - there is none in production.
- `tools/` (the Python build-time pipeline: OR-Tools solver, glyph + asset bake) is the only writer of pipeline output under `frontend/public/`. The game reads only pipeline output, never raw `assets/` sources.
- Game / domain code MUST NOT import build tools.
- Long compute in the browser (any future physics step, pathfinding, or procedural generation) runs in a Web Worker; the main thread keeps painting. The puzzle solver is build-time (Python in `tools/`), so it never runs on the runtime thread.
- The game canvas is one DOM element styled by Tailwind to fit its container. Tailwind does NOT style canvas internals - those are the renderer's job.

## Schema versioning (rules only - see `CLAUDE.md` section 11 for full spec)

The persisted surfaces: **save format** (`localStorage`, the one MIGRATING surface), **level / puzzle data**, and **asset + glyph manifest** (bundle-shipped, rewrite-in-place, no migration). Each has a typed schema in `schemas/` before logic is written (Holy Law #3).

- Each schema carries a `schemaVersion` integer and an `evolution` array; every change appends one `evolution` entry (`{version, date, change, why}`) in the same commit.
- Additive + backwards-compatible change: keep `schemaVersion`, add the evolution entry (older payloads still validate).
- Breaking change (removed field, type change, semantic shift): bump `schemaVersion` AND write the read-side migration the new build runs on older payloads - same commit.
- `$id` is the schema file's relative path (`<name>.schema.json`), local not URL, so IDE JSON-Schema plugins validate offline.
- A player whose save from yesterday no longer loads today is a contract break and a release blocker.

## UI verification (for any `frontend/` runtime change)

Per `CLAUDE.md` section 12, the agent verifies via integrated browser tools - build-clean is necessary but NOT sufficient:
- Confirm the dev server is up (start it if not); navigate the affected route(s) plus one cross-route smoke.
- Read the page console: zero new `[error]` events, zero new 404s.
- Screenshot when the change is layout-sensitive.
- When the change touches the render loop, physics, or asset load: open DevTools Performance, throttle CPU 4x + Network "Slow 4G", record an interaction, and confirm the frame budget (60fps, input-to-photon < 50ms) holds on the target-device profile.

## Correction levels (escalation rule)

When in doubt, choose the higher level (`CLAUDE.md` section 6). Level 2 and above get an explicit plan before code changes; execute once scope is clear. Level 5 (core design / save format / renderer / physics-engine pick) is a design consultation only - pause work and surface it. Stop conditions for autonomous git work are in the git-hygiene section above and `CLAUDE.md` section 8.

## Anti-patterns (do NOT)

- Reinterpret, downgrade, or scope-narrow a source or instruction the user named explicitly without surfacing it for sign-off (STOP-AND-SURFACE).
- Assume a backend exists in production.
- Hardcode game-balance values, asset paths, or difficulty thresholds. They live in `config/`, schema-validated.
- Store absolute or backslash paths in any persisted artifact.
- Build custom HTTP / retry / parsing / validation / physics / rendering / particle systems when a mature OSS library exists - justify any custom build against the OSS alternative.
- Swallow exceptions or silently coerce invalid input - fail fast at the boundary.
- Mock in tests by default.
- Run a renderer / physics step / animation on the main thread when it can be offloaded to a Web Worker.
- Use `setTimeout` / `setInterval` for game-loop timing. Use `requestAnimationFrame`.
- Ship a layout-triggering CSS animation when `transform` + `opacity` will do.
- Style canvas internals with Tailwind. Tailwind is for the chrome (HUD, menu, modal).
- Commit raw source assets (`.obj`, 4K PNG, uncompressed WAV) into the served bundle. Run them through `tools/` first.
- Add a runtime telemetry / analytics / error-tracking SDK, or a monetisation pattern (ads, IAP, timers, pay-to-skip).
- Ship a feature that depends on a runtime backend, account, or push notification.
- Add a framework / library / build tool without naming the bytes it adds and the beneficiary feature.
- Pick the renderer or physics engine in isolation - Carmack picks both together, with dimensionality, body-count budget, and determinism named in writing.
- Mint a new save-format / level-data field without bumping `schemaVersion` and writing the read-side migration in the same commit.
- Lower the perf target to fit a feature. The target is the player's phone, not the feature.
- Edit a `package.json` without updating and staging its lockfile in the same commit.
- Use broad, lossy, or history-rewriting git commands instead of the `CLAUDE.md` section 8 workflow.
- Let `TODO/`, chat logs, `AGENTS.md`, or `/memories/` become the source of truth for architecture.
- Pre-create empty modules "for later".
- Skip the docs update.

## See also

- [`bootstrap.md`](bootstrap.md) - what to load before answering.
- [`../../CLAUDE.md`](../../CLAUDE.md) - the authoritative engineering contract.
- [`../concepts/core-loop.md`](../concepts/core-loop.md) - the game verb and moment-to-moment loop.
- [`../architecture/contracts/schemas.md`](../architecture/contracts/schemas.md) - the persisted-surface schemas this digest references.
