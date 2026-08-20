# Architecture Overview

**Last Updated**: 2026-08-20

Why yen-tamizh is split into two runtimes that never meet at run time, and how data crosses the gap between them. This is the top of the architecture tier; the subsystem docs (the runtime, the generator pipeline, the design pipeline) land with their code and describe *how* each half is built. This page fixes *why* the split exists and what the boundary is. The vocabulary it uses is defined in [../concepts/vision.md](../concepts/vision.md) and [../concepts/principles.md](../concepts/principles.md).

## Two runtimes, one boundary

There are exactly two runtimes, and they share no live connection:

```
AUTHOR (CI / local)                 GITHUB (storage)              PLAYER (browser)
  backend/  (Python, BUILD-TIME)      frontend/dist -> Pages         Svelte app loads the shell
    ingest   corpora -> wordlist      static HTML / JS / CSS         computes today's date (UTC)
    rank     wordlist -> tiers        + baked bank + glyph manifest  reads baked data same-origin
    generate list -> puzzle JSON      (all inside the bundle)        caches it in IndexedDB
    solve/validate (gate CI)                                         persists progress + streak
    bake     glyphs + assets                                         emits structured events (local)
        |  commits validated data + bundle
        v
   the frontend bundle contains ZERO generator logic
```

- **`backend/` is a stateless producer** (Python): it runs only in CI or locally to generate, solve, validate, score, and bake. It writes; it never reads player state, and it never runs in the browser.
- **`frontend/` is a stateless consumer** (Svelte): it reads baked data, renders, interacts, and persists locally. It is never authoritative over puzzle correctness - the committed, validated JSON is the source of truth.
- **They meet only through committed data**, validated against a schema ([contracts/schemas.md](contracts/schemas.md)). No live API ever crosses the boundary.

## Data delivery: baked into the bundle, never fetched

The game needs puzzle data at run time, and it gets it **without any runtime call home** (Holy Law #1):

`backend/` writes the puzzle **bank** and level data into **`frontend/public/`** at build time. Vite copies `public/` into the served bundle, so the deployed static site carries the data. The game loads it **same-origin**, and the service worker precaches it, so a fresh Daily works offline the moment the bundle is cached. The game never reads raw `datasets/` or `assets/` sources - only baked `public/` output. See [../how-to/ship-to-github-pages.md](../how-to/ship-to-github-pages.md) for the base-path and offline mechanics.

### Design rationale

The prior-generation proposal served puzzle JSON from `raw.githubusercontent.com` as a free CDN. yen-tamizh **rejects the runtime CDN**: baking the data into the bundle is what makes the game work offline and removes the only runtime call home, satisfying Holy Law #1 literally rather than "mostly". The cost - a slightly larger bundle and a redeploy to ship a new day - is acceptable under Holy Law #2 (no fixed byte cap; measure-then-optimize) and is exactly what the daily-bank CI workflow is for.

### Rejected alternatives

- **Serve puzzles from `raw.githubusercontent.com` (a runtime CDN).** Rejected: it is a runtime fetch to an external host - it breaks offline play and violates Holy Law #1. Authority: the committed contract (`CLAUDE.md` Holy Law #1).

## Determinism and the CI gate

Generation is **date-seeded and idempotent** - same input, same output - which makes bugs and tests tractable. **Validation gates CI**: a generated puzzle that is unsolvable or malformed fails CI and never ships. Whether a board also admits something ELSE is a per-Game ruling rather than a blanket rule: every Game so far RECORDS its alternatives (`alsoValid`, `anagramFanOut`) instead of requiring uniqueness, and the crossword measured what requiring it would cost - see [contracts/schemas.md](contracts/schemas.md). This is what lets the game trust the committed JSON blindly and carry zero solver logic.

## The contract pipeline

Persisted shapes flow one way, from an authoritative source to typed consumers: `backend/` Pydantic models export a flat `schemas/<name>.schema.json`, and a frontend codegen step emits the TypeScript types and validators the game reads. A CI drift gate fails on any divergence. The shape discipline (date-stamp `version` + `changelog`, additive-vs-breaking, read-side migration) is described in [contracts/schemas.md](contracts/schemas.md); the pipeline that runs it lands with its own row.

## Layer and dependency rules

These keep the boundary honest (`CLAUDE.md` section 4, [../agents/guardrails.md](../agents/guardrails.md)):

- `frontend/src/` MUST NOT depend on a runtime backend service - there is none in production.
- `backend/` is the only writer of pipeline output under `frontend/public/`.
- Game and domain code MUST NOT import build tools; `backend/` MUST NOT import frontend code.
- Runtime modules (Mode -> runner -> Game -> telemetry) communicate through **structured-payload events on one bus, not cross-boundary calls** (`CLAUDE.md` section 1a). See [../concepts/core-loop.md](../concepts/core-loop.md) and [../concepts/telemetry.md](../concepts/telemetry.md).

## See also

- [../concepts/vision.md](../concepts/vision.md) - what the product is and is not.
- [../concepts/principles.md](../concepts/principles.md) - the ethos this architecture serves.
- [../concepts/core-loop.md](../concepts/core-loop.md) - the runtime event model.
- [../concepts/telemetry.md](../concepts/telemetry.md) - the build-time and runtime event names.
- [../concepts/config.md](../concepts/config.md) - the tunables both runtimes read.
- [contracts/schemas.md](contracts/schemas.md) - the persisted-surface schema discipline.
- [../how-to/ship-to-github-pages.md](../how-to/ship-to-github-pages.md) - base-path, SPA fallback, and the service worker.
- [../reference/documentation-structure.md](../reference/documentation-structure.md) - where each kind of doc lives.
- [../../CLAUDE.md](../../CLAUDE.md) - the engineering contract.
- [../../TODO/README.md](../../TODO/README.md) - the full system-design proposal.
