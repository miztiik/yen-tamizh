# yen-tamizh

**Last Updated**: 2026-07-25

A small, daily **Tamil word-puzzle game** - a static Progressive Web App on GitHub Pages. No server, no accounts, no ads, no tracking; it downloads what it needs and plays offline.

It is not a single game but a shell that hosts many word Games, framed by several Modes, threaded into player Journeys:

- **Games** (the verb): Word Ladder, Anagram, Missing Letters, Wordle-style, Word Search, Crossword.
- **Modes** (how a session is framed): Daily, Journey, Infinite, Time Trial.
- **Journeys** (the path a player walks): a curated, ordered map of levels.

The Tamil twist that touches every layer: the atomic unit is the **ezhuthu (grapheme cluster)**, never the Unicode codepoint.

## How it is built

- **`frontend/`** - a static Svelte + Vite + Tailwind app; the only thing the player downloads.
- **`backend/`** - a build-time Python producer (corpus ingest, generate, solve/validate, bake). It runs in CI, never at runtime, and writes committed data the frontend reads.
- **`config/`** + **`schemas/`** - tunable knobs, schema-validated; no hardcoded values.
- **`datasets/`** - raw + cleaned Tamil corpora the backend reads.

Static-first: everything the game needs ships in the bundle and works offline - no runtime backend, no runtime calls home. Communication is event-driven with structured payloads, asynchronous and non-blocking, so the game stays responsive.

## Start here

- [`CLAUDE.md`](CLAUDE.md) - the engineering contract (read first).
- [`docs/`](docs/) - canonical knowledge (Diataxis tiers).
- [`docs/agents/bootstrap.md`](docs/agents/bootstrap.md) - the context-load ritual every agent runs.
- [`TODO/README.md`](TODO/README.md) - the full system-design proposal.

## See also

- [`docs/reference/documentation-structure.md`](docs/reference/documentation-structure.md) - where each kind of doc lives.
