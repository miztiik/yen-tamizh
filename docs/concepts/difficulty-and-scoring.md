# Difficulty and Scoring

**Last Updated**: 2026-07-29

The tuning vocabulary: how hard a puzzle is, how a result is scored, and how the streak and stats are derived. This page fixes the terms; the concrete numbers are config-driven ([config.md](config.md)) so tuning never touches code (Holy Law #6). Difficulty as a designed experience is Palm's altitude ([../../.github/agents/palm.agent.md](../../.github/agents/palm.agent.md)).

## Difficulty is a curve, not a slider

Difficulty is a **designed curve**, not a raw dial (Palm worldview #4). Each puzzle carries a difficulty grade on a small ramp (easy -> extreme); the ramp has a colour token per step ([design-system.md](design-system.md)). Early items are nearly impossible to lose so the first 60 seconds end in a win; new wrinkles arrive a few items apart. A [Mode](modes.md) reads difficulty to shape its Session (Daily's mix, Infinite's pickable bucket, a [Journey](journeys.md)'s rising path); a [Game](games.md) reads it to size its own puzzle. What "hard" means is per-Game and lives in that Game's generator, not here.

## Scoring is derived, not stored twice

A result is **derived from the standard [telemetry](telemetry.md) events**, never persisted as a second source of truth. From `puzzle.started`, `puzzle.attempt.submitted`, `puzzle.hint.used`, and `puzzle.completed` the scorer computes the visible stats:

- **TIME** - active elapsed time (the clock pauses when the tab is hidden, so time off the puzzle never counts).
- **INSTINCT** - first-try successes (e.g. rungs solved on the first submission).
- **RETRIES** - wrong submissions.
- **STREAK** - consecutive completed days (below).

Beating a puzzle is the floor; a **three-star** grade is the ceiling (Iisalo, via Palm) - a reason to replay a puzzle already solved, which doubles content depth without doubling content cost. Star thresholds are config knobs.

## The streak

The streak ticks **once per completed [Daily](modes.md) day** and is the shared brag. It is recomputed on read (never trusted from the payload) against a fixed **UTC** day boundary, so it is device-clock-independent and share-stable. A replay of an already-won day is practice: it never re-bumps the streak or the best time. Only Daily advances the streak; a Journey, Infinite, or Time Trial result does not.

## Hints cost the brag, not money

A hint is free and unlimited in spirit but costs the **brag**: taking one excludes the day from the best-time record and stamps "hints" on the share card. This is the honest answer to the "stuck" moment (Palm worldview #7) - the game reads a stuck player and offers a free, well-timed hint or a suggestion to replay an earlier item, and it *never* sells a power-up, ships a timer as scarcity, or gates progress behind a purchase (project non-goals, [principles.md](principles.md)). Per-Game hint visibility, count, and cost are config-driven ([config.md](config.md)); the hint shape is defined in [core-loop.md](core-loop.md).

## The share moment

The end-of-session summary ([ui-shell.md](ui-shell.md)) is designed to look good in a screenshot - the score, the stars, the streak, and a small game name - because players share screenshots, not links (Player worldview #8). The share card carries no spoiler and no tracking link.

## See also

- [core-loop.md](core-loop.md) - the events the scorer reads and the hint shape.
- [modes.md](modes.md) - the Daily streak and per-Mode framing.
- [games.md](games.md) - where per-Game "hard" is actually defined.
- [journeys.md](journeys.md) - the rising-difficulty path and its stats row.
- [telemetry.md](telemetry.md) - the event envelope every stat is derived from.
- [config.md](config.md) - the difficulty ramp, star thresholds, and hint knobs.
- [design-system.md](design-system.md) - the difficulty colour ramp tokens.
