# AGENTS.md

**Last Updated**: 2026-07-25

Derived pointer for coding agents. Not authoritative - if this disagrees with `docs/`, docs win (CLAUDE.md section 5).

Before any non-trivial work in this repo:

1. Read [`CLAUDE.md`](CLAUDE.md) - the engineering contract (Holy Laws, architecture principles, correction levels, schema versioning, test tiers).
2. Run the load ritual in [`docs/agents/bootstrap.md`](docs/agents/bootstrap.md); honour the rules digest in [`docs/agents/guardrails.md`](docs/agents/guardrails.md).
3. Route new documentation by [`docs/reference/documentation-structure.md`](docs/reference/documentation-structure.md).

Five persona advisors live in [`.github/agents/`](.github/agents/), each at a distinct altitude: Player, Jony (UI/UX), Palm (Casual Design), Fowler (Architecture & Engineering), Carmack (Engine & Runtime).

The build-time producer is `backend/` (Python; runs in CI, never at runtime); the player-facing app is `frontend/` (static Svelte + Vite + Tailwind). They meet only through committed data validated against `schemas/`.

## See also

- [`README.md`](README.md) - what yen-tamizh is.
- [`TODO/README.md`](TODO/README.md) - the system-design proposal.
