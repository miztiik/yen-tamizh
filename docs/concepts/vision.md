# Vision

**Last Updated**: 2026-07-29

What yen-tamizh is, what it is not, and the one-sentence product idea every other concept doc serves. This is the top of the concept tier; if a later doc contradicts this page, this page is wrong and gets fixed.

## What it is

yen-tamizh is a small, daily **Tamil word-puzzle game** that runs as a static Progressive Web App on GitHub Pages. Open the page, play today's puzzle, close the tab; tomorrow there is a new one. A build-time Python pipeline generates and validates the puzzles; a Svelte front-end renders and plays them; the browser remembers your progress locally.

The product is not one game. It is a **shell that hosts many word [Games](games.md), framed by several [Modes](modes.md), threaded into player [Journeys](journeys.md)**:

- **Games** are the verb - what you do: Word Ladder, Anagram, Missing Letters, Wordle-style, Word Search, Crossword.
- **Modes** are how a session is framed: Daily, Journey, Infinite, Time Trial.
- **Journeys** are the path a player walks - a curated, ordered map of levels, so different players take different routes through the same Games.

The Tamil twist that touches every layer: the atomic unit a player manipulates is the **ezhuthu** (grapheme cluster), never the Unicode codepoint. See [core-loop.md](core-loop.md).

## What it is not

These non-goals are load-bearing (`CLAUDE.md` section 0a, [guardrails.md](../agents/guardrails.md)) - do not raise them as gaps:

- **Not a product with a server.** No production backend, no live API, no runtime fetch that calls home (Holy Law #1). Everything the game needs at runtime ships in the bundle and works offline.
- **Not a multi-user system.** No accounts, no sign-in, no server-side state, no cross-device sync. Progress is browser-local only.
- **Not monetised.** No ads, no in-app purchase, no timers-as-scarcity, no lives-with-IAP, no pay-to-skip, no streak-savers. Language is a public good.
- **Not tracked.** No runtime analytics or error-tracking SDK. [Telemetry](telemetry.md) is a local debugging bus with no network sink.
- **Not a learning-management system.** It does not grade students or track a curriculum.

## How it is hosted and remembered

- **Hosted** as static HTML / JS / CSS on GitHub Pages, base-path aware, with an SPA `404.html` fallback for deep links. See [../how-to/ship-to-github-pages.md](../how-to/ship-to-github-pages.md).
- **Persisted** browser-locally only: `localStorage` for small flags plus streak, `IndexedDB` for cached puzzle data (offline replay). Clearing the browser clears the player.
- **Fed** by committed, schema-validated data baked into `frontend/public/` at build time - never a runtime CDN. See [../architecture/overview.md](../architecture/overview.md).

## The daily ritual

One headline puzzle set per day is the ritual and the shared artifact: a Daily playlist, a streak tick per completed day, a shareable result card, and a countdown to the next puzzle. Everything else - more Games, the winding-path Journey map, Infinite, Time Trial - hangs off that spine. See [modes.md](modes.md).

## See also

- [principles.md](principles.md) - the ethos and constraints every subsystem inherits.
- [core-loop.md](core-loop.md) - the game verb and the ezhuthu unit.
- [games.md](games.md) - the six Game mechanics.
- [modes.md](modes.md) - the four Modes that frame a session.
- [journeys.md](journeys.md) - the curated path a player walks.
- [../architecture/overview.md](../architecture/overview.md) - the two-runtime static-first architecture.
- [../../CLAUDE.md](../../CLAUDE.md) - the engineering contract (Holy Laws, non-goals).
- [../../TODO/README.md](../../TODO/README.md) - the full system-design proposal this vision distills.
