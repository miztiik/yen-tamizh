# How to execute a plan-doc (the orchestrator contract)

**Last Updated**: 2026-07-29

The step-by-step MECHANICS for running a `TODO/<YYYYMMDD>-<slug>-plan.md` that [author-a-plan.md](author-a-plan.md) produced. Authoring writes the plan; this doc runs it. The autonomy POLICY (AUTO by default, when to ESCALATE) lives in [../agents/bootstrap.md](../agents/bootstrap.md); this doc is the HOW.

Run the `bootstrap` skill first. When editing agent/customization Markdown, use ASCII only: "-", "->", ">=", "section".

## The model: an orchestrator that never codes, and disposable workers that do

The agent that runs a plan is an **orchestrator**, not an implementer. It holds only the plan-doc and one report per row, and it NEVER writes feature code inline. Every row's real work is delegated to a **worker subagent** (via `runSubagent`) that runs in its own isolated context and its own git worktree, does the row end-to-end, and returns a structured report. The orchestrator then gates, merges, flips the Status Reckoner, and advances.

Why the split exists: the orchestrator's context is the scarce resource. If it implemented rows inline, its context would fill with per-row detail and it would lose the plan. Delegation keeps the orchestrator lean - it only ever holds the plan + per-row reports, never the full implementation transcript. This is context protection, and it is the whole point.

```
orchestrator (main thread)                 worker subagent (one per row)          persona custom agents
  read plan-doc + Status Reckoner            runSubagent(default) per row            runSubagent("Fowler ...") etc.
  pick next dispatchable row(s)      ---->   bootstrap; implement the row    ---->   resolve ONE ambiguity,
  create worktree + branch                   code + tests + docs                     return a written ruling
  dispatch worker; mark IN-FLIGHT            run Oracle + acceptance gates           (an input, not an approval)
  receive structured report        <----     consult personas on ambiguity  <----
  run DoD + ship-a-pr; merge on green        return report (does NOT merge)
  flip Status DONE #pr; distill; advance
```

## Roles

### The orchestrator (main thread) does exactly this, and only this
1. Bootstrap; read the plan-doc Section 0 (operating contract) + Section 1 (Status Reckoner).
2. Select the next dispatchable row(s): every `Depends-on` is `DONE`; rows sharing a `Parallel-group` dispatch together, up to `Parallel N`.
3. Create an isolated git worktree off `origin/main` + a named branch per row. Never share a worktree between rows or with a parallel agent (worktree contamination silently sweeps one row's edits into another's PR). Fill the Status Reckoner `Worktree`.
4. Dispatch one worker subagent per row (`runSubagent`, default agent) with a self-contained brief (below). Set `Status = IN-FLIGHT`; fill `Subagent`.
5. Receive the worker's report. Run the Definition of Done (CLAUDE.md section 9) and [ship-a-pr.md](ship-a-pr.md); on green gates, AUTO-merge (`gh pr merge --squash --delete-branch`).
6. Flip `Status = DONE #<pr>`; unblock dependents; [distill](distill-a-plan.md) the closed row.
7. Repeat until every row is `DONE` or `COLLAPSED`; then close the plan.

The orchestrator does NOT open the row's source files, write its code, or run its inner test loop inline - that is the worker's job. The orchestrator's own edits are limited to the Status Reckoner and the merge.

### The worker subagent (one per row) does the actual work
Dispatched with `runSubagent` (default agent). Its brief is the row verbatim (Scope, Files touched, Acceptance gates, Oracle, Decisions, Rejected alternatives) plus the standing instruction: run bootstrap, honor CLAUDE.md, stay in scope, consult personas on ambiguity, return a report. The worker:
1. Runs bootstrap; reads the row + the docs its surface touches.
2. Implements the row end-to-end: code + tests at the tier that matches the surface (CLAUDE.md section 13) + the docs update.
3. Resolves ambiguity by consulting personas (below), baking the ruling into the code.
4. Runs the row's Oracle and every acceptance gate locally; iterates until green.
5. Returns a STRUCTURED report: files changed, gate + Oracle results, decisions taken (+ which persona ruled), any ESCALATE, and the branch / worktree state.
6. Does NOT merge, does NOT edit the Status Reckoner, does NOT start another row. Merge and closure are the orchestrator's.

### Persona custom agents resolve ambiguity (they are not an approval gate)
When a row is genuinely ambiguous - a design fork, a contested decision, a fact-finding sweep - the worker dispatches the relevant persona custom agent(s) by exact name ("Fowler (Architecture & Engineering)", "Carmack (Engine & Runtime)", "Jony (UI/UX)", "Palm (Casual Design)", "Player", or "Explore" for read-only breadth) via `runSubagent`. A persona returns a WRITTEN ruling the worker bakes into the row; it is an input to the worker's action, never a request-for-approval surface (bootstrap's AUTO policy). A contested decision runs the relevant personas in DEBATE to ONE ruling (author-a-plan.md step 3).

If the harness does not permit a worker to dispatch a nested subagent, the worker instead surfaces the ambiguity in its report; the orchestrator runs the persona consult and re-dispatches the row with the ruling appended to the brief. Either way personas are consulted - never skipped, never treated as a gate.

## The one-line stamp a plan-doc carries

Every plan-doc carries exactly one execution stamp (author-a-plan.md step 5). It is the line that makes "implement it" sufficient: the executing agent reads it, loads this doc, and follows the contract with no further instruction.

```
Execute per docs/how-to/execute-a-plan.md: orchestrator dispatches one worktree-isolated worker subagent per row; workers consult personas on ambiguity; AUTO-merge on green gates; parallel N = <n>; honor the ESCALATE triggers in section 0. AUTHOR-AND-STOP until the user authorizes.
```

Drop the `AUTHOR-AND-STOP ...` clause once the user authorizes execution.

## Parallel fan-out

Rows in the same `Parallel-group` are mutually independent and dispatched concurrently, up to `Parallel N` workers, each in its own worktree. The orchestrator parallelizes the WORK but serializes the MERGE - one PR at a time, re-checking the next worker's branch against the advanced `main` before its merge - so a green worker never lands on a stale base.

## Escalation (when to pause for the user)

AUTO is the default. PAUSE and surface only for: a Level-5 row (CLAUDE.md section 6), a new `## Design rationale` that would change a persisted contract, an unresolved persona conflict, a scope change (-> [handle-scope-change.md](handle-scope-change.md)), or a 3x cost overrun. Otherwise the orchestrator advances without asking.

## Closure

When every row is `DONE` / `COLLAPSED`: run [distill-a-plan.md](distill-a-plan.md) for each closed row, confirm the Status Reckoner is fully resolved, and delete the plan-doc once fully distilled (git history is the ledger, per [../reference/documentation-structure.md](../reference/documentation-structure.md)).

## See also

- [author-a-plan.md](author-a-plan.md) - authoring the plan this doc runs; the plan-doc structure + Status Reckoner columns (`Worktree`, `Subagent`) this contract fills.
- [../agents/bootstrap.md](../agents/bootstrap.md) - the autonomy POLICY (AUTO default, escalation) this doc mechanizes.
- [distill-a-plan.md](distill-a-plan.md) - lifting findings into canonical docs after a row merges.
- [handle-scope-change.md](handle-scope-change.md) - STOP-AND-SURFACE when scope shifts mid-row.
- [ship-a-pr.md](ship-a-pr.md) - the PR lifecycle the orchestrator runs at merge.
- [../../CLAUDE.md](../../CLAUDE.md) - correction levels (section 6), Definition of Done (section 9), agent roster (section 14).
