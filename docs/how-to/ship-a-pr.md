# How to ship a PR

**Last Updated**: 2026-06-07

The end-to-end runbook for taking a worker branch from "ready to commit" to "merged + cleaned up". Procedural counterpart to [CLAUDE.md](../../CLAUDE.md) section 8 (Git Hygiene) + section 9 (Definition of Done) + section 12 (UI Verification).

The runbook is stack-agnostic on purpose: yen-tamizh has not yet picked its build tool, test runner, or component layer (CLAUDE.md section 3 says those land alongside the first real PR). The git mechanics and the 2-commit-then-squash pattern apply today; the specific gate commands fill in once the stack lands.

## When to run

For any PR you author. The mechanics scale - a one-line typo fix runs the same steps as a multi-file refactor, just faster.

## Inputs

- A correction-level assessment per [CLAUDE.md](../../CLAUDE.md) section 6 (Level 0 / 1 / 2 / 3 / 4 / 5). Level 5 stops here for design consultation.
- Branch name in the form `<type>/<scope>-<slug>` (e.g. `feat/level-1-prototype`, `chore/asset-pipeline-skeleton`, `docs/save-format-schema`).

## Pre-flight

### Status check

```powershell
git status --porcelain; git branch --show-current
```

Confirm a clean working tree (or that the dirty paths are yours). Confirm the branch you intend to commit on.

### Branching

Always branch from `origin/main`, not from a stale local `main`:

```powershell
git fetch origin main
git checkout -b <type>/<scope>-<slug> origin/main
```

## The 2-commit-then-squash pattern

Use this pattern when your PR's diff needs to cite its own to-be-allocated PR number (the most common case for any change that updates a plan-doc or durable doc with a `PR #_pending_` placeholder). The cost is one extra commit on the branch (~5 lines of churn) that vanishes at squash; the value is the in-doc PR# stamp lands in the same merge SHA as the work.

### Commit 1 - structural

All file edits, deletes, schema bumps, test changes. The plan-doc / concept / how-to / subsystem entries that reference this PR cite `PR #_pending_` as a placeholder. Stage explicit paths only:

```powershell
git add <named paths>
git status --short  # Verify EVERY named path shows M / A / D / R in column 1.
                    # Any ' M' (space-M) entry means the path is NOT staged.
git commit -F .tmp_commit_msg.txt   # or: git commit -m "<single-line message>"
```

The `git status --short` verification protects against the staged-then-silently-unstaged bug (a path can show `MM` if it was staged and then edited again; if you commit without re-`git add`, the second edit ships invisibly missing).

If you author the commit message in a scratch file with PowerShell, prefer `[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))` over `Set-Content -Encoding utf8` - the latter inserts a UTF-8 BOM that `git commit -F` treats as content.

### Push + create PR

```powershell
git push -u origin <branch>
gh pr create --base main --head <branch> --title "<title>" --body-file .tmp_pr_body.md
```

Capture the PR number from the URL it prints.

### Commit 2 - stamp

Replace `_pending_` with `#NNN` in every doc that references this PR:

```powershell
# Edit files: plan-doc row + relevant concept/how-to/subsystem doc + etc.
git add <stamped paths>
git commit -m "stamp(<scope>): PR #NNN"
git push
```

Do not record an architecture decision as a routine PR stamp. Update the living doc that owns the current shape. When this PR actively explored and rejected a real architecture alternative with non-trivial reversal cost, add a `## Design rationale` / `## Rejected alternatives` section to that same living doc - there is no `docs/architecture/decisions/` directory.

## The Definition-of-Done gates

Run the gates appropriate to the surface before merge. Reference: [CLAUDE.md](../../CLAUDE.md) section 9 (DoD) + section 12 (UI Verification) + section 13 (Test Coverage Policy).

The gate _commands_ depend on the stack picks (build tool, test runner, type-check tool, lint), which land alongside the first real PR per CLAUDE.md section 3. The gate _categories_ are stable:

1. **Schema / contract validation** - every persisted shape (save format, level data, asset manifest) validates against its schema.
2. **Unit + contract tests** - per CLAUDE.md section 13. Real fixtures, no mocks.
3. **Integration + e2e tests** - if the change touches the render loop, physics, or asset load.
4. **Lint + type-check** - zero-warning policy.
5. **Browser smoke** - per CLAUDE.md section 12. For any runtime change: dev server up, navigate affected routes, console clean, perf check on a mid-tier Android profile if the change touches render / physics / asset load.

Once the stack is picked, this section gets the actual commands inline.

## Merge

```powershell
gh pr merge NNN --squash --delete-branch
```

Both commits squash to one entry on `main`. The merged-to-main commit contains the correct `PR #NNN` reference inline.

**Do NOT use `--auto`** unless `enablePullRequestAutoMerge` is enabled in repo settings; otherwise gh returns a GraphQL error. Plain `--squash --delete-branch` is the default.

## Post-merge cleanup

This is the loop that is otherwise implicit. Run every step in order.

### Step 1 - verify the merge actually happened

```powershell
gh pr view NNN --json state,mergedAt,mergeCommit
```

`state` MUST be `MERGED`. If `gh pr merge` printed a cosmetic error during merge, the server-side merge usually succeeded anyway - this command confirms.

### Step 2 - delete the remote branch if gh skipped it

If `gh pr merge` cosmetic-errored, its post-merge git steps were skipped, including the remote-branch delete:

```powershell
git push origin --delete <branch>
```

Expected output: `[deleted]`. If `gh`'s `--delete-branch` ran successfully, this returns `error: unable to delete '<branch>': remote ref does not exist` - which is the GOOD outcome (already deleted).

### Step 3 - fetch + sync your view of origin/main

```powershell
git fetch origin main
git log --oneline origin/main -1
```

Confirms the new `main` HEAD matches the merge commit you just landed.

### Step 4 - prune stale local branches

After several merges the local repo accumulates branches whose remote-tracking ref is `: gone`. Prune in bulk, skipping the current branch (which `git branch -vv` prefixes with `* `):

```powershell
git fetch --prune
git branch -vv | Select-String ': gone\]' | ForEach-Object {
    $tokens = ($_.Line.TrimStart('*',' ').Trim() -split '\s+')
    $branchName = $tokens[0]
    if ($branchName -and -not ($branchName -match '^(main|HEAD)$')) {
        git branch -D $branchName
    }
}
```

Use `git branch -D` (force), not `-d` (merged-only), because squash-merged branches do not look "merged" to git even though they are. The `: gone` marker is the safe signal - it means the upstream was deleted (only happens after the PR merges).

Do NOT prune branches without a `: gone` marker; those have live upstreams and may be parallel work-in-progress.

### Step 5 - clean up tmp files

```powershell
Remove-Item .tmp_*.txt, .tmp_*.md, .tmp_*.log -ErrorAction SilentlyContinue
```

The `.tmp_*` pattern is the convention for ephemeral PR-authoring files. Add `.tmp_*` to `.gitignore` once it exists.

### Step 6 - distill lessons

If the PR taught you something durable - a new pattern, a gotcha, a generalisable rule - distill it per [distill-a-plan.md](distill-a-plan.md) so the next session does not rediscover it.

## See also

- [CLAUDE.md](../../CLAUDE.md) section 8 (Git Hygiene), section 9 (Definition of Done), section 12 (UI Verification), section 13 (Test Coverage Policy)
- [distill-a-plan.md](distill-a-plan.md) - what to do with the lessons a PR produced
- [../reference/documentation-structure.md](../reference/documentation-structure.md) - which doc tier the distilled content belongs in
