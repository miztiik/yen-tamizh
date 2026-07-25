---
name: prepare-plan
description: Turn a rough idea or draft into an execution-ready plan-doc under TODO/ that an autonomous agent can run end-to-end with no further instruction. Use when the user says "make a plan", "prepare a plan", "plan this", or "write an execution-ready plan". This skill AUTHORS the plan; it does NOT execute it.
---

# prepare-plan

This skill is a thin wrapper. The canonical authoring procedure lives in [`docs/how-to/author-a-plan.md`](../../../docs/how-to/author-a-plan.md), and the orchestrator execution contract that the plan-doc stamps lives in [`docs/how-to/execute-a-plan.md`](../../../docs/how-to/execute-a-plan.md). Read those and follow them - there is one source of truth (the docs), not a copy embedded here.

The wrapper exists so the `.claude/` harness can invoke the same authoring behaviour a "make a plan" request expects, via a one-line pointer, exactly as [`bootstrap`](../bootstrap/SKILL.md) points at `docs/agents/bootstrap.md`.

## What you must do

1. Run [`bootstrap`](../bootstrap/SKILL.md) first (skip only for Level-0/1).
2. Open [`docs/how-to/author-a-plan.md`](../../../docs/how-to/author-a-plan.md) and follow its five-step procedure and plan-doc structure.
3. Emit ONE file: `TODO/<YYYYMMDD>-<slug>-plan.md`. Stamp the execution pointer (a single line, not a pasted block) per [`docs/how-to/execute-a-plan.md`](../../../docs/how-to/execute-a-plan.md). STOP after writing; do not implement.
4. When editing agent/customization Markdown, use ASCII only: "-", "->", ">=", "section".

## See also

- [`docs/how-to/author-a-plan.md`](../../../docs/how-to/author-a-plan.md) - the authoring procedure this wrapper points to.
- [`docs/how-to/execute-a-plan.md`](../../../docs/how-to/execute-a-plan.md) - the orchestrator contract the plan-doc stamps.
- [`docs/how-to/distill-a-plan.md`](../../../docs/how-to/distill-a-plan.md) - closure + archive ritual.
- [`docs/how-to/handle-scope-change.md`](../../../docs/how-to/handle-scope-change.md) - STOP-AND-SURFACE.
- [`bootstrap`](../bootstrap/SKILL.md) - run before authoring.
