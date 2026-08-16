# Wordsmith lexicon - deviation log

**Last Updated**: 2026-08-15

Non-authoritative working record, per CLAUDE.md section 3 (`notes/` = optional scratchpad). It exists so the PLAN stays clean - the plan carries execution instructions only, and this file carries the trail of what was discussed, what changed course, and why. If this file and `docs/` disagree, docs win. If it and the plan-doc disagree, the plan wins.

Companion to `TODO/20260814-wordsmith-lexicon-pipeline-plan.md`.

## Distilled direction (read this first)

Build the Tamil lexicon by COMBINING and CROSS-VALIDATING every authority, not by unioning whatever each source happens to contain. Enrich and validate BEFORE publishing. Decide the committed file layout LAST, from measured numbers. Low-frequency words are deferred, never dropped.

## Shipped, in order

| Row | PR | Outcome |
| --- | --- | --- |
| 1 | #13 | `requireCoAnagram` deleted - served anagram set 163 -> 17,313. Re-bake guard added. |
| 2 | #14 | `RelPath` / `SourceId` -> `contracts/common.py`. Byte-identical regeneration. |
| 4 | #15 | 19 sources acquired, 38 fixtures, the POS census. A6 NOT ACQUIRED. |
| 3 | #16 | `lexicon` + `lexicon-sources` contracts. 11-member `PartOfSpeech`. |
| 5 | #17 | EXTRACT + the source registry. 8,086,729 rows in, 16 parse rejects. |
| 6 | #18 | The delta store. `delta == full` passed first attempt. |
| 7 | #19 | Five exact word-hood signals + the orthotactic table. |
| 8 | #20 | Three inexact signals - n-gram, neighbour, Zipf. |
| 9 | #21 | The classifier. Live proper-noun bug closed: the political party and the politician are no longer `headword`. |
| 10 | #22 | `llm_enrich` - 801 authored entries covering 58.7% of the servable set's frequency mass. |
| 4a | #23 | `ta-wiktionary-titles` (A8) acquired - 410,074 titles, 98,100 single wholly-Tamil words. Ruled TIER 2 (a page title carries no gloss, so the editorial act is not in the bytes). Pinned to the dated `20260801` dump. |
| 9a | #24 | **Both classifier defects fixed.** `headword` **49,873 -> 137,991** (85,314 at 3-6 ezhuthu). A1 recovery **10,300 (9.9%) -> 97,446 (93.6%)**, its `unclassified` **86,249 -> 0**. `notAWord` minted: **949,378**. Store 6,569,694 surfaces after staging A8. |

## Course changes, and what caused each

| # | Change | Cause | Authority |
| --- | --- | --- | --- |
| D1 | Row 4 reclassified from operator-only to an agent row | The phase-split premise ("a worker cannot reach the raw sources") was verified FALSE - the predecessor repo was on the machine and all network sources returned 200 | User |
| D2 | Rows 7 and 8 serialized despite being a declared parallel pair | Row 7 creates `enrich.py` and `config/wordhood.json`; row 7's own text says row 8 extends both. They would have collided. | Orchestrator |
| D3 | `PosAlias.wordClassEvidence` narrowed off `WordClass` | It admitted `["headword"]`, so a one-line CONFIG edit could let a non-authority source assert word-hood, breaking row 4 decision 1 | Fowler, FIX-FIRST before merge |
| D4 | Row 9's `inflected` rule reversed on a literal reading | Taken literally, every verb ROOT that also appears in the 1.46M inflected-form lists became `inflected` - deleting every Tamil verb headword. An authority entry now outranks bulk form evidence. | Worker, ratified by orchestrator |
| D5 | Lexicon filenames stay HEX, never Tamil script or romanized | Tamil script: git's default `core.quotepath` renders non-ASCII paths as octal escapes, so it is LESS legible on the operator's own machine. Romanized: ISO 15919 is not ASCII; ITRANS is case-significant and collides on case-insensitive NTFS/APFS. Rule: immutable identifier in the path, correctable label in data. | Carmack |
| D6 | Split threshold 50 MiB -> 33 MiB; `<length>` made unconditional | 33 MiB is one third of GitHub's 100 MiB HARD wall (50 MiB is only the warning line). A conditional `length` made a word's address depend on the size of its class - a latent forced rename. | Carmack |
| D7 | Retention and publication separated | The gitignored store retains everything; git history is append-only and irreversible. "Nothing discarded" lives at the retention layer, not the artifact. | Fowler |
| D8 | Row 11 decision 6's named consumers rejected | It justified 300 MiB of `inflected` as "Wordle's guess-accept list" - but the plan's own "Hard scope - out" line excludes new Games, and neither Game exists. Carmack added that such a list could never be these files anyway: 2.8M forms is ~600 MiB and must ship in the browser, so it would be a ~3.4 MB Bloom filter. | Fowler + Carmack |
| D9 | **PUBLISH HALTED. Enrich and validate first; layout decided last.** | Three defects found by measurement - see below. The plan was about to publish a number it had not earned. | User |
| D10 | **Layout SETTLED: policy D, one file per first ezhuthu - 241 files, largest 2.2 MiB, 25 MiB total.** Publishes `headword` / `properNoun` / `boundStem` / `colloquial`. | Decided from the post-remeasure table. One file per class is IMPOSSIBLE if everything is published - `unclassified` alone is 387 MiB against a 100 MiB wall. Carmack's contrary argument (more files worsen a line-oriented diff) is on record and was overridden; Fowler's raw-source archive merge condition still stands and is still UNMET. | User (supersedes both personas, CLAUDE.md section 0) |
| D11 | `headword` provenance confirmed: the PREVIOUS project's dictionary attests **97,768 of 137,991 (70.9%)**, of which **9,837 exist on A1's word alone**. 40,545 headwords come from sources the old project never had. | Answering "did we lose the old dictionary?" - no; row 9a recovered it from 10,300 to 97,446. | Measured |

## The three defects that halted publish (2026-08-15)

| # | Defect | Measured |
| --- | --- | --- |
| C1 | The `headword` entry test requires a `pos` fact from the SAME source as the headword fact. A1 supplies zero `pos` facts (its blanket `nouns` tag was correctly rejected at EXTRACT), so the predecessor's curated dictionary was demoted. | A1: 104,073 headword facts, only 10,300 (9.9%) classified `headword`; 86,249 (82.6%) -> `unclassified`. Corrected projection: **139,425**. |
| C2 | No verdict for "not a word at all", so scrape junk gets a real class - repeated aytham as `loanword`, leading dots and hyphens, a 1,212-ezhuthu paragraph. | A shape pass removes **641,819 (10.3%)** and collapses cells 509 -> 140. |
| C3 | A7 is the ENGLISH edition's Tamil subset (13,773) because that is what kaikki.org publishes; kaikki supports ~20 editions and Tamil is not one. The Tamil Wiktionary itself was never tried. | `ta.wiktionary` ns0 titles: **410,074**, of which **98,100** are single wholly-Tamil words; **83,701** in the 1-7 ezhuthu band; **12,383 brand new**; **2,722** newly attestable; **82,995** gain a second independent attestation. |

## Corrections I made to my own claims

- Said macOS NFD normalization disqualified Tamil filenames. **Wrong** - the partition key is the BASE codepoint, and all 36 are singletons with no canonical decomposition. Carmack corrected it; the real disqualifier is `core.quotepath`.
- Said A6 "already vanished from DSAL". **Wrong** - it never had a bulk download; it is a search-box site and the predecessor never had it either.
- Said ta.wiktionary was "30x A7". **Overstated** - 410,074 titles, but only 98,100 usable single Tamil words, so ~9x.
- Said the three provenance fields cost 691 MiB. **Wrong** - they are conditional, so the real cost is ~32 MiB. The genuine fat was `ezhuthu` at 211 MiB, which is recomputable from `word`.

## Open questions

| # | Question | Status |
| --- | --- | --- |
| Q1 | Publish only servable classes, or every class? | Reverses a user directive - needs sign-off after the remeasure |
| Q2 | Committed file layout: one file per class, per class+length, or per first ezhuthu (up to 247)? | RE-OPENED. Decide from remeasured numbers. |
| Q3 | Raw-source archive - Release asset or private? | Carmack made it a merge condition on publish. `yen-tamizh_OLD` is NOT a git repo, so there is no upstream copy today. |
| Q4 | A6 replacement authority | Only on a user-named source with sign-off |
| Q5 | Missing-Letters per-blank-mask uniqueness | Out of scope; note it when that Game is planned |
| Q6 | **Tier-1 including A1 re-admits `அசுர`** (a bound stem, the plan's canonical junk example), because A1's dictionary lists it as a headword. Three stricter entry rules were measured and each costs 84-89% of A1's 87k recovery - a bad trade. Row 9a resolved it by splitting Oracle (b) and pinning the escape by name. | OPEN for row 12. `headword` is NOT the serving decision - row 12's four gates are (`minAttestations >= 2` + tier-1 composition, `minFrequency >= 1`, `requireMeaning`). A low-frequency bound stem with no authored meaning should fail them. **Row 12 must MEASURE whether it does, rather than assume.** |
| Q7 | `notAWord` came in at 949,378 vs the 641,819 estimate - the extra 307,559 is A8's own packaging (multi-word titles, romanizations), not new junk in the older sources. | Informational; confirms A8 needed the shape gate |

## See also

- [`../TODO/20260814-wordsmith-lexicon-pipeline-plan.md`](../TODO/20260814-wordsmith-lexicon-pipeline-plan.md) - the execution plan this log tracks.
- [`../docs/architecture/lexicon/pipeline.md`](../docs/architecture/lexicon/pipeline.md) - the durable subsystem doc.
- [`../docs/architecture/lexicon/word-hood.md`](../docs/architecture/lexicon/word-hood.md) - the signals and the classification taxonomy.
