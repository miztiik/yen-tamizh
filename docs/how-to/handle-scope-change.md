# How to handle a scope change mid-plan (STOP-AND-SURFACE)

**Last Updated**: 2026-07-29

What a worker or orchestrator does when work in flight no longer matches the plan-doc's Hard scope: a row turns out bigger than its Scope sentence, a dependency was missed, a Decision collides with a Holy Law, or the user's intent shifts. The rule (CLAUDE.md section 10 anti-pattern): never reinterpret, downgrade, substitute, or scope-narrow silently. STOP and SURFACE.

## When this fires

- A row's real surface exceeds its `Files touched` / `Scope` - it is actually two rows.
- A `Depends-on` was missing and the row cannot proceed without an unplanned change.
- A Decision in the row conflicts with CLAUDE.md, a schema contract, or another row's Decision.
- The user changes intent, or a persona ruling invalidates a planned row.
- A Level-5 trigger surfaces mid-row.

## The procedure

1. STOP the affected row at its last clean state; do not force the change through.
2. SURFACE in one paragraph: what the plan assumed, what reality is, two-to-three options, and the recommended option + the persona that would rule it.
3. If AUTO and the change is in-scope-but-larger: split the row (update the Status Reckoner - add rows, redraw `Depends-on`), then continue. A pure split that ships the same intent needs no user pause.
4. If the change alters a persisted contract, the Hard scope, or a Level-5 surface: PAUSE for user sign-off. Do not proceed on assumption.
5. Record the resolution where it belongs: a Status Reckoner edit for a split; a `## Design rationale` on the impacted living doc for a contract change (never an ADR file); a `/memories/` note for an agent-craft lesson.

## What never happens

- Silently narrowing a row to fit the time or context budget.
- Deleting a planned row without citing why in its Status (`COLLAPSED` + rationale).
- Expanding a row into unplanned surface without updating the Status Reckoner.

## See also

- [execute-a-plan.md](execute-a-plan.md) - the orchestrator loop this interrupts.
- [author-a-plan.md](author-a-plan.md) - the plan-doc + Status Reckoner this updates.
- [../../CLAUDE.md](../../CLAUDE.md) - the STOP-AND-SURFACE anti-pattern (section 10), correction levels (section 6).
