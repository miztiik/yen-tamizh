# Handover - yen-tamizh wordsmith lexicon

**Last Updated**: 2026-08-16
**Read with**: [`20260814-wordsmith-lexicon-pipeline-plan.md`](20260814-wordsmith-lexicon-pipeline-plan.md) (the plan) and [`../notes/20260815-wordsmith-deviation-log.md`](../notes/20260815-wordsmith-deviation-log.md) (the trail of course changes).

Start here. Do task 1 before anything else - there is finished work stranded on disk that is lost if a worktree is removed carelessly.

## State, verified 2026-08-16

`origin/main` is at `233be60`. Seventeen rows are merged (PRs #13-#30): the source layer, contracts, the four pipeline stages, eight word-hood signals, the classifier and its two corrections, the Tamil Wiktionary title + content sources, IndoWordNet, the published lexicon, and the derived-layer cutover.

| Surface | Value |
| --- | --- |
| Sources registered | 21 |
| Surfaces classified | ~6.78M |
| `headword` published | 162,361 |
| …with a Tamil meaning | 101,659 |
| Served anagram words | 32,310 (floor was 6,000) |
| Published files on `main` | 238 (115 headword) |

## TASK 1 - recover the stranded row 12a work. Do this FIRST.

`c:\Users\kumarsnaveen\Downloads\NawiN\personal\gitrepos\yen-tamizh-fix`, branch `feat/senses-and-propernouns`, holds **279 uncommitted files**. It was never committed, pushed or merged. Two workers yielded at the gate stage. **Removing that worktree destroys the work.**

What it contains, all verified working:

| Fix | Evidence |
| --- | --- |
| Multi-sense meanings | Root cause was PUBLISH, not EXTRACT - `definitionTa` was one precedence-resolved slot. **115,545 senses were being discarded**; 58,193 of 234,853 Wiktionary pages carry more than one. `definitionTa` is now a LIST. The `; siris` reference fragment is stripped. |
| Row order | Rows now begin `{"word": ...}` with counts last, instead of `{"attestations": ...}`. |
| Base-letter files | 115 headword files -> **22**, largest 7.0 MB, zero stale 8-hex-digit files. |
| `ta-wikipedia-titles` acquired | Registered, fixtures committed, sha recorded. **No classifier rule shipped** - see task 3. |
| Bank rebaked | 2026-08-17 onward. `\u0b85\u0ba4\u0bbe\u0ba9\u0bbf` (Adani) is GONE. Days 08-13..08-16 untouched, correctly. |

**To finish it:** run `mypy` and `pytest` from `<worktree>/backend` (two failures were outstanding - triage, do not weaken), the drift gate, the frontend suite, and a browser smoke. Then stage exact paths - including the DELETIONS of the old full-letter files - commit, push, open a PR, wait for CI, merge.

Do NOT re-run the pipeline. The store (`datasets/lexicon/cache/lexicon.db`, ~3 GB) is already rebuilt and current.

## TASK 2 - verify what the user actually sees

After task 1 merges, confirm in the main worktree that `datasets/lexicon/by-class/headword/` holds 22 files and that `0b95.ndjson`'s first row begins with `"word"`. The user checks this in VS Code; until it merges they see the old layout and are right to say the reorder did not happen.

## TASK 3 - proper nouns need a different approach

**Row 12's stated goal - proper nouns stop being served - is NOT achieved.** The cutover cleared the named cases, but the general problem stands. Days baked after it still served `\u0b9a\u0baa\u0bbe\u0baa\u0ba4\u0bbf`, `\u0bae\u0ba3\u0bbf\u0bae\u0bca\u0bb4\u0bbf`, `\u0b85\u0b9e\u0bcd\u0b9a\u0ba9\u0bbe` - all personal names. `properNoun` holds only 1,074 members.

Why it is hard: most Tamil personal names ARE meaningful words. `\u0b85\u0b9e\u0bcd\u0b9a\u0ba9\u0bbe` is kohl, `\u0bae\u0ba3\u0bbf\u0bae\u0bca\u0bb4\u0bbf` is gem-like speech. The classifier is not simply wrong.

**Tamil Wikipedia titles were tried and MEASURED AS INSUFFICIENT.** 75.8% of proper nouns have an article versus 4.9% of headwords - good in aggregate - but 2 of the 3 named personal names have NO article while every control word does. Best rule reached ~32% precision, deleting two real words per name caught. Do not retry this alone.

Approaches not yet tried, in rough order of promise:
1. **Wikidata `instance of: human` / `given name`** - a direct entity-type assertion rather than mere article existence. Only 904 Tamil lexemes exist, but Tamil LABELS on human entities are far more numerous.
2. **A name-suffix signal** - `-\u0bb5\u0bc7\u0bb2\u0bcd`, `-\u0bb0\u0bbe\u0b9c\u0bcd`, `-\u0bb2\u0bbf\u0b99\u0bcd\u0b95\u0bae\u0bcd`, `-\u0ba8\u0bbe\u0ba4\u0bcd` and similar are strongly name-forming.
3. **A curated deny-list** of public figures, as data in `config/`. Small, honest, and instantly effective for the political-name case that started this.
4. **An LLM pass over the 32,310 served words** - a bounded, one-time review that is small enough to be practical.

Consult Palm and Player before choosing; this is about what a player is served.

## TASK 4 - the other known content gap

Row 12a's rebake put participial adjectives on 2026-08-22: `\u0bae\u0bca\u0bb4\u0bbf\u0baf\u0bbe\u0ba9`, `\u0bae\u0bbf\u0b95\u0bc1\u0ba4\u0bbf\u0baf\u0bbe\u0ba9`, `\u0ba4\u0bb5\u0bb1\u0bbf\u0bb2\u0bcd\u0bb2\u0bbe\u0ba4`. These are inflected forms the classifier still admits as `headword`. Row 10a hit the same wall - it declined roughly 65% of its top-frequency candidates on exactly these grounds. A classifier pass that demotes participles would raise the quality of every future bake.

## TASK 5 - clean up worktrees

Only `yen-tamizh` (main) and `yen-tamizh-fix` should exist. Remove `yen-tamizh-fix` ONLY after task 1 merges. Several stale sibling directories may remain from earlier sessions - check `git worktree list` against what is on disk, and note `yen-tamizh-row4` / `yen-tamizh-row5` are inert non-git leftovers.

## Remaining plan rows

| Row | What | Depends on |
| --- | --- | --- |
| 13 | Retire the corpus layer; delete `datasets/wordlists/master/`, `contracts/corpus_sources.py`, `contracts/master_wordlist.py`, `config/corpus-sources.json`. This is what finally tidies `datasets/`. | task 1 |
| 15 | Themed selection (`categories` + `pos`) | 13 |
| 14 | Hint ladder rebuild; show a solved word's meaning on the summary | 13, 15 |

Row 13's Oracle is a repo-wide zero-hit search for the retired identifiers (`masterPath`, `masterRows`, `load_master`, `MasterWord`, `MasterWordlist`, `master-wordlist`, `_MASTER`, `datasets/wordlists/master/`, `corpus-sources`, `CorpusSources`). Row 12 already confirmed `FreqBand` has no usages outside the modules row 13 deletes.

## Standing context the next session needs

- **Row 14 has an unresolved dependency.** `meaningSource` and `categorySource` were dropped from the published row at the user's instruction, so nothing carries `reviewed`. Row 14's rule - an unreviewed meaning may render free but may not be SOLD as a paid hint - has no field to check. Row 14 must name a mechanism.
- **`compound` was never published**, so row 12 decision 5's claim that long headwords are mostly compounds is unmeasured.
- **`spokenRatio` is 0.0 on 91.9% of served rows** and separates nothing. It needs a second spoken-register source or it should be dropped.
- **No off-repo archive exists** for the ~819 MB of raw sources. They live only on this machine; `yen-tamizh_OLD` is NOT a git repository. Carmack made this a merge condition on publishing and it was never met.
- **Workers cannot dispatch personas** in this harness. The orchestrator must run persona consults itself and feed the ruling back.
- **Two workers yielded mid-row** on long pipeline runs. For any row that re-runs ENRICH (~20 min), expect to dispatch a separate completion pass for the gates and the ship.
- User rulings that supersede the plan as authored: no licence gate on Tamil language facts; attested Tamil definitions publish verbatim; provenance fields do not belong in the dataset; keep the published row lean.

## See also

- [`20260814-wordsmith-lexicon-pipeline-plan.md`](20260814-wordsmith-lexicon-pipeline-plan.md) - the plan, with the Status Reckoner.
- [`../notes/20260815-wordsmith-deviation-log.md`](../notes/20260815-wordsmith-deviation-log.md) - 14 course changes, the defects, and corrections to claims that turned out wrong.
- [`../docs/how-to/rebuild-the-lexicon.md`](../docs/how-to/rebuild-the-lexicon.md) - running the pipeline.
- [`../docs/how-to/execute-a-plan.md`](../docs/how-to/execute-a-plan.md) - the orchestrator contract.
