# How to author an execution-ready plan-doc

**Last Updated**: 2026-07-05

The procedure for turning a rough idea or draft into a `TODO/<YYYYMMDD>-<slug>-plan.md` that an autonomous agent can run end-to-end with no further instruction. This is the canonical home for the authoring ritual; the [`prepare-plan`](../../.claude/skills/prepare-plan/SKILL.md) skill is a thin wrapper that points here, mirroring how [`bootstrap`](../../.claude/skills/bootstrap/SKILL.md) points at [../agents/bootstrap.md](../agents/bootstrap.md).

Authoring produces the plan; it does NOT start the work. Running the plan is a separate ritual in [execute-a-plan.md](execute-a-plan.md).

Run the `bootstrap` skill first (skip only for Level-0/1). The plan-doc is a living doc on `master`, never a frozen artifact.

When editing agent/customization Markdown, use ASCII only: "-", "->", ">=", "section".

## When this fires

A user says "make a plan", "prepare a plan", "plan this out", or "write an execution-ready plan for X". You produce ONE file: `TODO/<YYYYMMDD>-<slug>-plan.md`. You do NOT start coding the work.

## Procedure

1. **Investigate against the code, not the draft.** Read the actual files the work touches. Verify every load-bearing claim directly (read the enforcement predicate, the consumer call site, the row-count), never via a subagent summary alone. If a draft says "X violates Y", open Y and confirm. Dispatch `Explore` subagents for breadth so the main context does not overflow. Spot-check any id-overlap claim with a real `set(a) & set(b)` sample before trusting it.
2. **Size and split into PR-rows.** One row = one PR = one branch = one reviewable unit. Phase the rows with hard dependency lines (A -> B -> ...), reader-before-writer for any schema or contract change. Bundle only where the work itself is one atomic surface; never bundle mixed risk profiles.
3. **Resolve ambiguity by naming the deciding authority inline.** Use the authority table in [../agents/guardrails.md](../agents/guardrails.md) (CLAUDE.md section 14 is the roster). Where a decision is contested, run the relevant personas (`fowler`, `carmack`, `palm`, `jony`, `player`) in DEBATE - they converge to ONE written ruling baked into the row, not independent parallel reviews. Red-team passes are research-only and return exact old -> new text.
4. **Set the Level + ESCALATE triggers.** Per CLAUDE.md section 6. Anything Level-5 (core design / data model / runtime) PAUSES for user sign-off; write the trigger explicitly so the executing agent stops there and nowhere else.
5. **Write the plan-doc** using the structure below. Stamp the execution pointer (see [execute-a-plan.md](execute-a-plan.md)) near the top. STOP after writing. Do not implement.

## Plan-doc structure (what you emit)

The plan is a tabular instrument for parallel dispatch, not a narrative. It contains only what ships, what was decided, and what was evaluated-and-rejected. No fluff, no chatter, no verbatim user quotes (CLAUDE.md section 10 anti-pattern).

- **H1 title + `Last Updated` + Level.** Nothing else above section 0.
- **Section 0 - Operating contract** (table, not prose):

  | Field | Value |
  | --- | --- |
  | Why this plan exists | one sentence |
  | Hard scope - in | bullets, no narrative |
  | Hard scope - out | bullets |
  | ESCALATE triggers | enumerated |
  | Chosen strategy | one line + the persona that ruled it |
  | Execution | `autonomous orchestrator per docs/how-to/execute-a-plan.md. Parallel N = <n>.` |

- **Section 1 - Status Reckoner** (the authoritative parallelization + agent-tracking table):

  | # | Row title | Depends-on | Parallel-group | Status | Worktree | PR | Subagent |

  - `#` integer ordinal.
  - `Depends-on` lists `#` values that must be DONE before this row can start; `-` means no predecessor.
  - `Parallel-group` is a letter; rows sharing a letter are mutually independent and dispatched together.
  - `Status` starts `PENDING`, flips through `IN-FLIGHT` to `DONE #<pr>` or `COLLAPSED` (with cited rationale).
  - `Worktree` is the isolated absolute path the orchestrator created for the row (or `-` until dispatched).
  - `Subagent` names the dispatched agent (or `-` until dispatched).

- **Section 2+ - one section per row, fixed shape, no prose padding:**

  ### Row #N - <title>
  - **Scope:** one sentence, what ships.
  - **Files touched:** bullet list of exact paths.
  - **Acceptance gates:** bullet list (tests, lint, type-check, browser-verify ...).
  - **Oracle:** ONE load-bearing check (bijection / coverage / contract / parity) that proves correctness.
  - **Decisions** (enumerated table):

    | # | Decision | Authority |

  - **Rejected alternatives** (enumerated table):

    | # | Option | Why rejected | Authority |

- **The execution stamp**: one line, not a pasted block. See [execute-a-plan.md](execute-a-plan.md#the-one-line-stamp-a-plan-doc-carries). This is the part that makes "implement it" sufficient.

## Plan-doc style rules (enforced; reviewers reject violations)

- No narrative paragraphs outside section 0 and the per-row Scope sentence.
- No agent chatter (no "I will ...", "let me ...", "we should ...").
- No verbatim user quotes from chat. Capture intent in neutral agent prose; cite who decided and when.
- No "future work" / "nice to have" / "if time permits" sections. If it is not a row, it is not in the plan.
- No restatement of CLAUDE.md or skill rules. Link, do not copy.
- Every claim that drove a decision lives in a Decisions row or a Rejected alternatives row - nowhere else.

## See also

- [execute-a-plan.md](execute-a-plan.md) - the orchestrator contract that runs the plan this doc writes.
- [distill-a-plan.md](distill-a-plan.md) - the closure and archive ritual after every row merges.
- [handle-scope-change.md](handle-scope-change.md) - STOP-AND-SURFACE when scope shifts mid-plan.
- [../reference/documentation-structure.md](../reference/documentation-structure.md) - the plan-doc single-snapshot rule and Diataxis tiers.
- [../../CLAUDE.md](../../CLAUDE.md) - correction levels (section 6), anti-patterns (section 10), agent roster (section 14).
