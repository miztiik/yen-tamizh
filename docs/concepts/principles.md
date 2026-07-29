# Principles

**Last Updated**: 2026-07-29

The small set of beliefs that shape every yen-tamizh decision, stated once as vocabulary. These operationalize the engineering contract for a Tamil word game; the authoritative rules live in [../../CLAUDE.md](../../CLAUDE.md) and the rules-only digest in [../agents/guardrails.md](../agents/guardrails.md). This page explains the *why* a reader needs before those rules make sense - it does not restate them.

## 1. Static-first, offline-capable

The deployed game is a static bundle. There is no production backend, no runtime server, no runtime fetch to a host that calls home (Holy Law #1). Everything the game needs at play time ships in the bundle and works on a plane. The `backend/` folder is a **build-time producer** only (Python, runs in CI), never a runtime service. See [../architecture/overview.md](../architecture/overview.md).

## 2. The player's phone is the architecture

Every runtime decision is measured against a mid-tier Android (Snapdragon 6-series, 4GB RAM, ~2022) over patchy 4G: input-to-photon < 50ms, sustained 60fps (Holy Law #2). Ship the richer game first, then optimize only if the target device drops below 60fps. There is no fixed byte cap; per-Game code lazy-loads so the shell stays light. The [Player](../../.github/agents/player.agent.md) persona is the reality check.

## 3. Contracts before logic

Every persisted shape - save format, puzzle data, config, asset manifest - gets a typed schema before the logic that reads or writes it (Holy Law #3). Schemas carry a date-stamp `version` and a `changelog`; a change appends a changelog entry in the same commit. See [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md).

## 4. Ezhuthu is the atom

Because the app is Tamil-only, one technical choice touches every layer: the unit a player manipulates - a tile, a grid cell, a Wordle "letter", a ladder rung - is the **ezhuthu** (grapheme cluster), never the codepoint. This is the reason a naive port of an English word game breaks. Defined in [core-loop.md](core-loop.md); every Game's scoring, blanking, shuffling, and interlock is expressed over ezhuthu.

## 5. Config-driven, sane defaults

Tunable behaviour - playlist length and mix, hint visibility, Infinite anti-repeat window, Time Trial duration, enabled Modes and Games - lives in `config/`, schema-validated, with sane defaults so a fresh clone runs (Holy Law #6). No magic numbers in code. See [config.md](config.md).

## 6. Events carry payloads, not calls

Subsystems communicate through structured-payload events on one bus, never direct cross-boundary calls (`CLAUDE.md` section 1a). The frontend/backend contract is committed JSON validated against a schema - a serializable payload that can be logged, replayed, and tested with real fixtures. The same bus drives the view and the [telemetry](telemetry.md) log. A new Game is "wired up" the moment it emits the standard events.

## 7. Visual feedback is first-class

Animation, colour cues, and motion that confirm a player's input are expected, not optional - they are what make the game feel responsive and sticky (`CLAUDE.md` section 1a). This is game feel, not accessibility tooling. Motion is `transform` + `opacity` only, and `prefers-reduced-motion` is a hard kill-switch. See [design-system.md](design-system.md).

## 8. Open source first, glyphs for icons

Prefer mature OSS over custom builds; every dependency names its beneficiary feature and byte cost (Holy Law #8). All icons are vector **glyphs** referenced by id from a generated manifest, never inline SVG or a hardcoded path (Holy Law #10). See [design-system.md](design-system.md).

## Design rationale

These eight are not new law - they are the concept-tier restatement of the Holy Laws in the vocabulary a Tamil word game needs, so a contributor learns the *why* from the concept tier and the *rule* from the contract. The rejected alternative was to let each concept doc re-derive the ethos in passing; that duplicates the contract and drifts (Holy Law #4, one definition). Authority: Fowler ([../../.github/agents/fowler.agent.md](../../.github/agents/fowler.agent.md)).

## See also

- [vision.md](vision.md) - what the product is and is not.
- [core-loop.md](core-loop.md) - the ezhuthu unit and the game verb.
- [config.md](config.md) - the tunable knobs and their defaults.
- [../architecture/overview.md](../architecture/overview.md) - the two-runtime split these principles produce.
- [../agents/guardrails.md](../agents/guardrails.md) - the rules-only digest of the contract.
- [../../CLAUDE.md](../../CLAUDE.md) - the authoritative engineering contract.
