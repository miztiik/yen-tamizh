# Tamil lexicon pipeline (`wordsmith`) - plan

**Last Updated**: 2026-08-14
**Level**: 5 (core data model)

Execute per docs/how-to/execute-a-plan.md: orchestrator dispatches one worktree-isolated worker subagent per row; workers consult personas on ambiguity; AUTO-merge on green gates; parallel N = 2; honor the ESCALATE triggers in section 0. AUTHOR-AND-STOP until the user authorizes.

## 0. Operating contract

| Field | Value |
| --- | --- |
| Why this plan exists | The corpus layer is a one-shot destructive funnel that discards 3.9M words to reach 50,000, approximates word-hood with frequency and orthographic proxies instead of dictionary attestation, throws away the meaning / POS / category metadata its own sources carry, and currently serves proper nouns - including a political party and a sitting politician - as daily puzzle answers. |
| Hard scope - in | Delete `requireCoAnagram` while retaining its index as a difficulty signal; build the `wordsmith` package as four independently runnable stages (EXTRACT / STAGE / ENRICH / PUBLISH) supporting delta and atomic per-source update; classify every word by eight word-hood signals into a closed `wordClass` enum; retain gloss, POS, synonyms, categories, frequency; rename the `master` surface to `lexicon`; LLM gloss authoring as a committed source; cut the derived layer over with real serving gates; retire the corpus layer; rebuild the hint ladder and show a solved word's meaning; POS and themed selection as two dimensions of one mechanism; and land every decision's rationale in the living doc named in the documentation map. |
| Hard scope - out | Chunking or sharding as an optimization (row 11 partitions only if a hosting hard limit is hit); a Tamil morphological analyzer; multi-sense `senses[]` publication; new Games or Modes in the shell; a themed Mode as its own Game; runtime consumption of the lexicon (the browser reads the baked bank, never a wordlist). |
| ESCALATE triggers | `delta == full` failing over the STAGED zone after two remediation attempts (row 6); a (`wordClass`, `length`, base-first-ezhuthu) FILE exceeding 50 MiB after the row-11 decision 6 split - terminal, because no finer immutable natural key exists, and one class / length / initial ezhuthu carrying ~250k words means the CLASSIFICATION is wrong, not the layout; an unresolved persona conflict; a 3x cost overrun. Rows 3 and 12 change the core data model and what the player is served - the orchestrator reports them prominently but does not block (user waived the Level-5 pause and plan review, 2026-08-14; Fowler, Carmack, Jony, Palm and Player reviewed in their place). |
| Chosen strategy | Strangler fig at the derive seam: build `datasets/lexicon/` alongside `datasets/wordlists/master/`, cut over in row 12, retire the old layer in row 13. The live bank keeps serving throughout. (Fowler.) |
| Execution | autonomous orchestrator per docs/how-to/execute-a-plan.md. Parallel N = 2. Group A (rows 1 + 4) and group B (rows 7 + 8) are the only genuine parallel pairs; N = 2 buys two overlaps and no more. |
| Runtime environment | The full pipeline runs ON A DEVELOPER LAPTOP, a handful of times over the project's life - not in CI and not on a schedule (user-ruled 2026-08-14). CI runs type checks, tests and the fixture-pipeline gate only (row 11 decision 9); `daily.yml` gains no lexicon step. |

Measured baselines, all verified against committed artifacts:

| Quantity | Value | Read from |
| --- | --- | --- |
| Anagram set today | 163 words (~54 days at 3/day) | `datasets/wordlists/derived/anagram.json` counters |
| Anagram set after row 1 | 17,313 words (~15.8 years at 3/day) | `50000 - 13386 - 17329 - 1972` from the same counters |
| Distinct words seen / kept / discarded | 3,967,009 / 50,000 / 3,917,009 | `datasets/wordlists/master/words_ranked.json` counters |
| Proper nouns currently SERVED | `திமுக` (line 52), `ஸ்டாலின்` (line 63) | `datasets/wordlists/derived/anagram.json` |

Tamil script appears in this doc only as cited evidence from committed data. CLAUDE.md section 5's ASCII rule targets typography (curly quotes, em-dashes, non-ASCII symbols); all punctuation here is ASCII.

### Naming (user-ruled 2026-08-14)

| Surface | Name |
| --- | --- |
| The all-words artifact | `lexicon` (`datasets/lexicon/by-class/<wordClass>[-<length>][-<hex>].ndjson`, where `<hex>` is the lowercase 4-digit hex of the word's base first ezhuthu and `lexicon.meta.json` maps every hex to its ezhuthu) |
| The processing package | `wordsmith` (`backend/yen_tamizh_backend/wordsmith/`) |
| The LLM meaning / synonym pass | `llm_enrich` |
| The word `master` | Removed from every module, model, field, config key, source id, artifact path, test fixture and doc |

### Stage independence (user-ruled 2026-08-14)

Each stage is a separate module with its own CLI entry point, runs alone, is idempotent, and reads the previous stage's on-disk artifact rather than an in-process value. `pipeline.py` only sequences.

| Module | CLI | Reads | Writes |
| --- | --- | --- | --- |
| `wordsmith/extract.py` | `python -m yen_tamizh_backend.wordsmith.extract [--source ID]` | one raw source + its registry entry | `datasets/lexicon/cache/extracts/<source-id>.jsonl` |
| `wordsmith/stage.py` | `... .stage [--source ID] [--remove ID]` | extracts | STAGED zone of `datasets/lexicon/cache/lexicon.db` |
| `wordsmith/enrich.py` | `... .enrich [--signal NAME]` | STAGED zone | DERIVED zone (signals + `wordClass`) |
| `wordsmith/publish.py` | `... .publish [--format ndjson,csv,sqlite]` | both zones | `datasets/lexicon/*` |
| `wordsmith/pipeline.py` | `... .pipeline` | - | sequences the four |

### Output formats (user-ruled 2026-08-14, sized by Carmack)

One resolved row set, several renderings, selected by a config `outputs` list.

| Format | Role | Committed |
| --- | --- | --- |
| NDJSON, one file per `wordClass` | The reviewable truth. One row per line, streamed, per-line git diffs | Yes |
| `lexicon.meta.json` | Version, changelog, provenance, per-class counters | Yes |
| CSV | Themed and per-class slices for a spreadsheet | On demand |
| SQLite | Query convenience, rebuilt by one command | No - a binary blob cannot be reviewed in a diff |

Every word is committed at FULL FIDELITY. Two derived diagnostics - `wordhood` and `freqRank` - are omitted under the row 11 decision 7 principle; every fact a source asserted is published for every word in every class. Files partition by `wordClass`, then by ezhuthu `length` where a class exceeds the size target, then by base first ezhuthu where a cell still does: roughly 750-840 MB, none over 50 MiB. All three keys are immutable per word, so a refresh INSERTS and never reshuffles. File count is an output of the measured byte table, frozen at first publish, never a target.

The full rebuild is operator-only. CI runs type checks, tests, the fixture-pipeline integration gate, and a zero-network sha256-set drift check (row 11 decision 9).

### Documentation map - where each decision's rationale lands

Per CLAUDE.md Holy Law #4 and `docs/reference/documentation-structure.md`, a plan-doc carries terse tabular decisions as EXECUTION instructions; the RATIONALE lives on the living doc it impacts, as a `## Design rationale` / `## Rejected alternatives` section. Docs land in the row that makes the change - never as a docs-only PR. Every row's Definition of Done includes its doc target below.

| Doc | New? | Receives |
| --- | --- | --- |
| `docs/concepts/lexicon.md` | NEW concept | The vocabulary, defined once: lexicon, `wordClass` and its nine values, attestation vs observation, `spokenRatio`, `attestedBy`, why ezhuthu count is the length and `mathirai` (mora) is not. Every other doc links here rather than redefining. |
| `docs/architecture/lexicon/pipeline.md` | NEW subsystem | The four stages and their independence; why EXTRACT / STAGE / ENRICH / PUBLISH rather than one pass; the two store zones and why `delta == full` is false without them; why SQLite for STAGING and why it is never an output; why NDJSON as the committed format; why streaming; the partition dimensions and the stability argument; why the rebuild is operator-only. |
| `docs/architecture/lexicon/word-hood.md` | NEW subsystem | The eight signals and what each catches; the classification taxonomy; why inflected forms are KEPT but never SERVED; why frequency and word-hood are independent axes; why a scored classification rather than a filter. |
| `docs/architecture/contracts/schemas.md` | exists | The `lexicon` and `lexicon-sources` contracts; the omission principle for `wordhood` and `freqRank`; why `pos` unions while `gloss` resolves; why the enum is closed and the alias map is config; why no `tags` bag. |
| `docs/concepts/difficulty-and-scoring.md` | exists | Two-axis difficulty and why length alone is anti-correlated; the serving gates and their shipping defaults; the stratified draw. |
| `docs/concepts/core-loop.md` | exists | The hint ladder and its monotonicity; why `length` was deleted; why English is banned on a paid hint; the third answer state. |
| `docs/concepts/games.md` | exists | Which selection dimensions each Game uses; the recorded finding that a POS restriction helps none of the five, and why a verbs day is the hardest day by accident. |
| `docs/how-to/add-a-lexicon-source.md` | NEW how-to | Adding a source as a data change. Replaces `add-a-corpus-source.md`, deleted in row 13. |
| `docs/how-to/rebuild-the-lexicon.md` | NEW how-to | Running the stages singly or as a pipeline; the delta and remove operations; what a refresh commit contains. |
| `docs/how-to/enrich-the-lexicon.md` | NEW how-to | The `llm_enrich` pass, its provenance fields, and the human review loop. |
| `docs/how-to/generate-the-daily-bank.md` | exists | The no-rewrite-published-days rule and the `--rebake` escape. |
| `docs/how-to/add-a-derived-wordlist.md` | exists | The selection knobs after the cutover; removal of the co-anagram and word-final rules. |

Every `wordsmith` module opens with a docstring citing the doc that explains it, so a future agent reading the code finds the reasoning without searching. The existing `corpus/derive.py` already does this; the plan makes it a rule rather than a habit.

### Source inventory - every file this plan reads

Every row below was opened and counted on 2026-08-14; nothing here is inferred from a filename. Paths are relative to the predecessor repository root unless marked otherwise. Row 4 acquires exactly this list and nothing else.

#### A. Word-hood authorities (only these may assert that a surface is a word)

| # | Path | Rows | Fields present | Contributes |
| --- | --- | --- | --- | --- |
| A1 | `src/dictionary/master_dictionary.json` | 104,421 | `ta`, `en` (12,954 only), `grapheme_count`, `category`, `word_frequency` (52,764 only) | headword, gloss evidence, category, frequency evidence |
| A2 | `src/dictionary/raw/t1.json` | 56,856 | `tamil` (POS prefix + comma-separated Tamil glosses), `eng` (the English headword) | gloss evidence, POS, and SYNONYM SETS by grouping Tamil terms under one English headword |
| A3 | `src/dictionary/intermediate/ta_words_v1.json` | 355,275 | `data[]` (bare words) + metadata declaring `validation_method: ta_spellchecker (Nanool-based rules)` | grammar-validated word list - a ready-made orthotactic signal |
| A4 | `src/dictionary/intermediate/ta_words_huggingface.json` | 26,485 | `data[]` (bare words), plus a removal breakdown in metadata | independent attestation, modern vocabulary |
| A5 | `src/dictionary/raw/t2.json` | 36,082 (8,686 are underscore-joined phrases) | `data[].word` | attestation only, no counts |
| A6 | University of Madras Tamil Lexicon, DSAL (`dsal.uchicago.edu`) | ~104,000 | headword + English definition | the standard authority; 1930s literary Tamil, misses modern vocabulary. Acquired as a bulk download, not an API |
| A7 | Tamil Wiktionary via Wiktextract | varies | headword, POS, senses, synonyms | modern coverage the 1930s lexicon lacks. A DOWNLOADABLE JSONL DUMP (kaikki.org publishes the Tamil extract), read line-at-a-time by a plain stdlib reader - NOT an API, no key, no runtime call |

Neither A6 nor A7 is in the predecessor repository, and neither needs a paid key: both are bulk downloads a plain reader consumes. Row 4 records the exact fetch URL and sha256 it used, and if a download cannot be obtained the row reports BLOCKED rather than substituting a source - the STOP-AND-SURFACE rule in CLAUDE.md section 10.

#### B. Form evidence (labels a surface as a non-headword; never asserts word-hood)

| # | Path | Rows | Fields present | Contributes |
| --- | --- | --- | --- | --- |
| B1 | `src/dictionary/raw/Simple-verbs-01022021.txt` | 1,461,494 | one inflected verb form per line | direct `inflected` labels - the single largest classification win available |
| B2 | `src/dictionary/intermediate/verbs.txt` | 19,249 | one inflected verb form per line | same, smaller and cleaner |

#### C. Category and gloss (semantic metadata, never word-hood)

| # | Path | Rows | Fields present | Contributes |
| --- | --- | --- | --- | --- |
| C1 | `src/dictionary/intermediate/ta_vocabulary_clean.json` | 1,290 | `category`, `english`, `tamil` - all three present on 100 percent of rows, across **40** categories | the cleanest gloss+category pairing available, and the themed-round seed |

C1's 40 categories are TWO different things and must not be merged into one field. Counted 2026-08-14:

| Kind | Categories | Rows | Routes to |
| --- | --- | --- | --- |
| Part-of-speech labels | `Nouns` (622), `Verbs` (180), `Adjectives` (25) | **827 of 1,290 (64 percent)** | `pos`, NOT `categories` |
| Real semantic themes | 37 others | **463** | `categories` |

The real themes are small. Largest first: Emotions 35, Nature 34, Profession 25, Animals 23, Vegetables 22, Places 19, Spices 17, Relations 16, Fruits 14, Hospital 14, School 13, Birds 12, Space 12, Kitchen 12, Garden 12, Games 12, Hall 12, Hobby 11, Arts 11, Dresses And Accessories 10, Food 10, Functions 10, Symbols Shapes 9, Parts Of Plants 9, Transport 8, Bedroom 8, House 8, Bathroom 8, Reptiles 8, Types Of Plants 8, Insects 8, Aquatic Animals 7, Colours 7, Tools 7, Days 6, Flowers 4, Amphibians 2.

`Nouns` at 622 rows is the same trap as the old curated dictionary's blanket `nouns` tag, which was already dropped by `filters.dropCategories` for carrying no signal.

#### D. Frequency evidence (counts only; never word-hood)

The nine sources already registered in `config/corpus-sources.json`, ported in row 5.

| # | Path | Contributes |
| --- | --- | --- |
| D1 | `src/dictionary/raw/tamil-words-frequency.csv` (188 MB, 4,591,654 rows) | the richest single frequency signal |
| D2 | `words_and_frequency/words_and_frequency/frequency+words_in_ta_dedup.txt` | deduplicated web corpus |
| D3 | `words_and_frequency/words_and_frequency/frequency+words_in_wiki.txt` | Tamil Wikipedia |
| D4 | `words_and_frequency/words_and_frequency/frequency+words_in_Dinamalar_dataset_2009_2019.csv` | news |
| D5 | `words_and_frequency/words_and_frequency/frequency+words_in_Tamilmurasu_dataset_06_Jan_2011_06_Jan_2020.csv` | news |
| D6 | `words_and_frequency/words_and_frequency/frequency+words_in_sirukathaigal.com.html` | short stories |
| D7 | `words_and_frequency/words_and_frequency/frequency+words_in_solvanam.html` | literary magazine |
| D8 | `words_and_frequency/words_and_frequency/frequency+words_in_gurunithya.wordpress.com.html` | blog |
| D9 | `hermitdave/FrequencyWords` `content/2018/ta/ta_full.txt` (URL, not the old repo) | OpenSubtitles - spoken Tamil, dense in short everyday words |

#### E. Registered but disabled

| # | Path | Why |
| --- | --- | --- |
| E1 | `words_and_frequency/words_and_frequency/frequency+words_in_azhiyasudargal.html` | Its extraction stripped vowel signs and pulli, so its tokens are bare consonant skeletons. Stays registered and explained, never deleted. |

#### F. Excluded, with reasons

| Path | Why excluded |
| --- | --- |
| `src/dictionary/raw/t1_bkpup.json` | Byte-identical backup of A2. |
| `src/dictionary/intermediate/tamil_dict_01..12.json` | Chunked copies of A2; the whole file is A2. |
| `src/dictionary/intermediate/tamil_words_sorted_*.json`, `tamil_word_list_*.json`, `intermediate/archive/` (410 files, 183 MB) | Intermediate output of the legacy pipeline this plan replaces. Their input is D1. |
| `src/dictionary/intermediate/processing_log.json` | A log of the legacy run, not data. |
| `words_and_frequency.tar.bz2` (root, 6.11 MB) | Verified 2026-08-14 to contain exactly the same 8 files as the extracted `words_and_frequency/` directory. No unique data. |
| `data/puzzles/index.json` + `data/puzzles/2026/*.json` (30 days) | The OLD game's baked puzzle bank (`schemaVersion: 2`, `setNo`, `revealedPositions`). Superseded output, not a word source. See row 14 decision 17 for the one thing it does inform. |
| `data/wordlists/game_words_2..6_letter.json` | Already present as `datasets/wordlists/by-length/`, already ruled a reference signal not a filter. |
| `src/utils/` (11 py), `scripts/` (8 py) | Legacy pipeline code this plan replaces. |
| `frontend/wireframe_screens/` (7 png) | Design reference, not data. |
| `backend/`, `frontend/`, `docs/`, `schemas/`, `config/`, `TODO/` | The predecessor's own application, superseded by this repository. |

Sweep completed 2026-08-14 over every non-hidden directory in the predecessor repository. Every data-bearing file is in exactly one group above.

Note for row 4: the frequency sources live under a DOUBLED directory - `words_and_frequency/words_and_frequency/` - which the paths recorded in `config/corpus-sources.json` do not show.

### Destination columns - the target row, and what fills it today

Sparse is expected and is the point: the column exists from row 3, whatever evidence exists fills it, and `llm_enrich` plus later sources densify it without a schema change.

| Column | Filled by | Coverage available today | Density |
| --- | --- | --- | --- |
| `word` | every source | all | dense |
| `ezhuthu` | computed, Row 6 library | all | dense |
| `length` | computed - ezhuthu count, mei with pulli counts as ONE | all | dense |
| `wordClass` | computed from the signal map | all | dense |
| `wordhood` | computed, the eight signals | all | dense |
| `attestedBy` | A1-A7 | union of the authority lists | dense where attested |
| `frequency` | D1-D9, plus A1's `word_frequency` | 52,764 of A1; millions from D1-D9 | dense |
| `freqRank` | computed | every row with a frequency | dense |
| `translationEn` | A1 `en` (12,954), A2 `eng` read FORWARD (56,856), C1 `english` (1,290), A7, then `llm_enrich` | ~70k rows before enrichment | **sparse -> densified in row 10** |
| `definitionTa` | `llm_enrich` ONLY, conditioned on `definitionEn`, `translationEn`, `pos`, `synonymsTa` | zero attested - NO source in the inventory carries one | **authored, then human-reviewed** |
| `definitionEn` | A6 Madras Lexicon (~104k), A7 senses | ~104k | **STORE ONLY - never published** |
| `meaningSource` / `translationEnSource` | computed | tracks the two above | provenance |
| `pos` | A2's POS prefix, C1's POS-like categories (Verbs, Nouns, Adjectives), A7, B1/B2 as verb evidence | ~57k from A2; +1.46M verb labels from B1/B2 | **sparse on headwords** |
| `synonymsTa` | A2 grouped SIDEWAYS by (English headword, POS); A7 | ~56,856 English headwords yielding multi-term groups | **sparse** |
| `categories` | C1 (1,290 rows over 40 categories), A1's themed tags (trees, flowers, birds, animals) | ~1,290 clean plus A1's themed subset | **very sparse - never a gate** |

## 1. Status Reckoner

### The AGENT / OPERATOR split - what was authored, and what actually happened

Authored 2026-08-14 on the premise that a worktree-isolated worker could not reach ~265 MB of gitignored raw sources, so the plan was split into two phases with a gate between them.

**That premise was FALSE on the execution machine, and the gate is CLOSED (2026-08-15).** The orchestrator verified it before dispatching anything: the predecessor repository was present locally with every A1-A5 / B1-B2 / C1 / D1-D8 file, and all three network-only sources returned HTTP 200. The user authorized row 4 as an agent row. It ran, acquired 18 of 19 sources, and committed the fixtures. Rows 3 and 5-9 then ran against the real data.

| Phase | Rows | Actual outcome |
| --- | --- | --- |
| **A - agent-executable** | 1, 2, 3, 5, 6, 7, 8, 9, 13 | Rows 1, 2, 3, 5, 6, 7, 8, 9 DONE. Row 13 waits on row 12. |
| **GATE** | row 4 | CLOSED - premise false, run as an agent row, PR #15. A6 alone NOT ACQUIRED. |
| **B - operator-gated** | 4, 10, 11, 12, 14, 15 | Row 4 DONE. Rows 10-12 and 14-15 remain. Rows 10 and 11 need a user go-ahead on authoring scale and repo size - NOT on data availability, which is settled. |

Two obsolete clauses in the original framing are recorded here rather than silently deleted: there is NO paid model key anywhere in this plan (row 10 decision 1 makes the authoring agent the producer and `llm_enrich.py` a reader of a committed file), and the raw sources DO exist on the execution machine.

Rows 7 and 8 are listed in parallel-group B but are NOT parallelizable: row 7 creates `enrich.py` and `config/wordhood.json`, and its own decision text says row 8 extends both. They were serialized.

### Measured reality - these numbers SUPERSEDE the authored estimates

Every figure below was measured against the real staged store during execution, and each replaces an assumption the plan was authored against. A later row citing an authored estimate instead of one of these is wrong.

| Quantity | Authored estimate | MEASURED | Consequence |
| --- | --- | --- | --- |
| Distinct surfaces | 3,967,009 | **6,249,903** (+57.5%) | Row 11's artifact and every per-cell byte projection grow with it |
| Published lexicon size | ~750-840 MB | **~1.23 GiB** | More cells cross the 50 MiB target and split; the layout itself still holds |
| `headword` surfaces | not estimated | **49,873**, of which **27,999** are 3-6 ezhuthu | Row 12's floor is 6,000 served at 3-6 ezhuthu, so there is headroom before the four gates |
| Word-hood authorities | 7 (A1-A7) | **6** - A6 unobtainable; A7 is 13,773 rows, not open-ended | Row 12 decision 14's tier-1 composition rule exists because of this |
| Row 8 pruned query set | 2.5-3x cut | **1.52x** (4,115,457 of 6,249,903) | `neighbour` is NULL on 2,134,446 surfaces; NULL means "not asked", never zero |
| ENRICH wall clock / peak RSS | under 5 min / under 1.2 GB | **~20 min / ~2.1 GiB** | Both missed, measured and reported, never lowered. Acceptable because section 0 rules the pipeline runs on a developer laptop a handful of times - Holy Law #2's budget governs the player's phone at RUNTIME, not a build-time laptop |
| A2 synonym clique | not estimated | **445 MiB / 2,709,708 facts = 79% of all facts** | The dominant load in STAGE and PUBLISH |

### The documentation-structure / author-a-plan question - RESOLVED, no amendment needed

Raised during execution as a possible contradiction. It is not one (user-ruled 2026-08-15). `docs/reference/documentation-structure.md` says a plan-doc never carries rationale prose; `docs/how-to/author-a-plan.md` says every claim that drove a decision lives in a Decisions or Rejected-alternatives row. Both are correct, and they speak to different things: the plan-doc carries the trade-off as an EXECUTION instruction and is DELETED at closure, while the durable rationale lands on the living doc the decision impacts (Holy Law #4). That is exactly how this plan has been run - every row shipped its doc target in the same commit as its code. Neither doc requires an amendment; this entry exists so the question is not re-litigated.

| # | Row title | Phase | Depends-on | Parallel-group | Status | Worktree | PR | Subagent |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Delete `requireCoAnagram`; retain the multiset index; add the re-bake guard | A | - | A | DONE #13 | `../yen-tamizh-row1` (removed) | #13 | worker |
| 2 | Move `RelPath` / `SourceId` to `contracts/common.py` | A | 1 | - | DONE #14 | `../yen-tamizh-row2` (removed) | #14 | worker |
| 3 | `lexicon` + `lexicon-sources` contracts | A | 2, 4 | - | DONE #16 | `../yen-tamizh-lex3` (removed) | #16 | worker |
| 4 | Source acquisition + committed fixtures | B | - | A | DONE #15 | `../yen-tamizh-lex4` (removed) | #15 | worker |
| 5 | `wordsmith/extract.py` + `config/lexicon-sources.json` | A | 3, 4 | - | DONE #17 | `../yen-tamizh-lex5` (removed) | #17 | worker |
| 6 | `wordsmith/stage.py` - the delta store | A | 5 | - | DONE #18 | `../yen-tamizh-lex6` (kept as warm-cache donor) | #18 | worker |
| 7 | Word-hood exact signals (attestation, orthotactics, breadth) | A | 6 | B | DONE #19 | `../yen-tamizh-lex7` | #19 | worker |
| 8 | Word-hood inexact signals (n-gram, neighbour, Zipf) | A | 6 | B | DONE #20 | `../yen-tamizh-lex8` | #20 | worker |
| 9 | `wordsmith/wordhood.py` - the classifier | A | 7, 8 | - | DONE #21 | `../yen-tamizh-lex9` | #21 | worker |
| 10 | `wordsmith/llm_enrich.py` - meaning + synonym authoring | B | 9 | - | READY - operator gate (authoring batch + cost) | - | - | - |
| 11 | `wordsmith/publish.py` + `pipeline.py` | B | 10 | - | PENDING | - | - | - |
| 12 | Cut the derived layer over; real serving gates; two-axis difficulty | B | 1, 11 | - | PENDING | - | - | - |
| 13 | Retire the corpus layer; purge the retired `master` identifiers | A | 12 | - | PENDING | - | - | - |
| 14 | Rebuild the hint ladder; show a solved word's meaning | B | 13, 15 | - | PENDING | - | - | - |
| 15 | Themed selection: `categories` + `pos` | B | 13 | - | PENDING | - | - | - |

Rows 3 and 13 change `REGISTRY` in `backend/yen_tamizh_backend/contracts/__init__.py`; rows 1, 2, 12, 14 and 15 edit registered models and regenerate `schemas/` + `frontend/src/contracts/`. All seven hit the drift gate, so none is dispatched concurrently with another schema row.

## 2. Row #1 - Delete `requireCoAnagram`; retain the multiset index as `anagramFanOut`

- **Scope:** Remove the co-anagram selection rule and its counter bucket, repurpose its index into a recorded difficulty signal, and ship the regenerated anagram wordlist.

- **Files touched:**
  - `backend/yen_tamizh_backend/corpus/derive.py`
  - `backend/yen_tamizh_backend/scripts/rebuild_wordlists.py`
  - `backend/yen_tamizh_backend/contracts/derived_wordlists.py`, `game_wordlist.py`
  - `backend/tests/test_derive.py`
  - `config/derived-wordlists.json`
  - `datasets/wordlists/derived/anagram.json`
  - `schemas/derived-wordlists.schema.json`, `schemas/game-wordlist.schema.json`
  - `frontend/src/contracts/derived-wordlists.*`, `game-wordlist.*`
  - `docs/how-to/add-a-derived-wordlist.md`, `docs/architecture/contracts/schemas.md`

- **Acceptance gates:** `mypy backend` strict; `pytest backend`; `npm ci`; `npm run build`; `npm run test`; `npm run lint`; `npm run check`; `npm run test:e2e`; drift gate green; browser smoke per CLAUDE.md section 12.

- **Oracle:** The committed `anagram.json` byte-equals a fresh `rebuild_wordlists` run, its counters reconcile with the `withoutCoAnagram` bucket removed, `rowsKept` equals 17,313, and every row carries an `anagramFanOut` equal to the number of served rows sharing its ezhuthu multiset.

- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | `requireCoAnagram`, `_has_co_anagram` and the `withoutCoAnagram` counter are deleted. `group_by_multiset` and `multiset_key` are RETAINED and repurposed to record `anagramFanOut` on each row. The rule was wrong as a FILTER - it cut content 106x and selected for bound stems - but it was measuring the right thing, and the index is what row 14's "that is a word, but not today's" response needs. | Palm, revising the initial deletion |
  | 2 | The co-anagram doctrine is removed from `docs/architecture/contracts/schemas.md` and `docs/how-to/add-a-derived-wordlist.md` in this same commit - the rule and its written justification die together. | User |
  | 3 | `requireValidWordFinal` stays in THIS row. Its logic is not lost long-term: word-final legality becomes signal 2 in row 7, and the knob is deleted in row 12 once that signal feeds `wordClass`. Deleting it here would leave the served wordlist with no quality net for eleven rows - textbook expand-migrate-contract. | Fowler (Beck) |
  | 4 | This row does not fix the fragment problem. `அசுர` is a real ezhuthu string in the master and survives; only word-hood classification (row 9) removes it. Nor does it fix the proper-noun problem - `திமுக` and `ஸ்டாலின்` remain served until row 12. | Fowler + Palm |
  | 5 | `_SCHEMA_VERSION` in `derive.py` is date-stamped to the merge date with a `changelog` entry naming the removed and added fields. No read-side migration: the only readers are `scripts/rebuild_wordlists.py` and `scripts/generate_today.py`, and every committed artifact and config regenerates in the same commit. | Fowler, CLAUDE.md section 11 |
  | 6 | THE RE-BAKE GUARD LANDS HERE, not in row 12. `scripts/generate_today.py` calls `write_artifact` UNCONDITIONALLY on all seven dates, and `pick_words` shuffles over the candidate list - so the very next `daily.yml` cron tick after THIS row rewrites today through today+6 from a 106x larger list, including a day a player may be mid-session on. Deferring the guard eleven rows leaves that window open the whole time. `generate()` therefore skips any date whose file already exists unless `--rebake` is passed, while the bank index is still rebuilt from disk every run so it cannot drift. A test asserts that re-running after mutating the derived wordlist leaves every pre-existing day file byte-identical. Row 12 then references this guard rather than introducing it. | Fowler + Carmack, audit |
  | 7 | Row 1 ships first: a 106x content win from the existing master, fully reversible, which removes schedule pressure from every later row. | Fowler (Durov: ship the deletion first) |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Keep the rule as a filter | 106x content cost, and it actively selects for bound stems because fragments are what collide with real words. | User |
  | 2 | Delete the multiset machinery outright | It is the only index that can tell a player "that is a word, but not today's" instead of a flat red X. A player who forms a real Tamil word from the exact tiles and is told they are wrong concludes the game cheated, which is the fastest route to churn. | Player + Palm |
  | 3 | Delete `requireValidWordFinal` here as well | No replacement net exists until row 9, so the served wordlist would regress for eleven rows. | Fowler |

## 3. Row #2 - Move `RelPath` / `SourceId` to `contracts/common.py`

- **Scope:** Relocate the two shared field types out of the module row 13 deletes, with no behaviour change.

- **Files touched:**
  - `backend/yen_tamizh_backend/contracts/common.py`
  - `backend/yen_tamizh_backend/contracts/corpus_sources.py`, `derived_wordlists.py`, `game_wordlist.py`, `master_wordlist.py`
  - `backend/yen_tamizh_backend/contracts/__init__.py`
  - `backend/tests/**`

- **Acceptance gates:** `mypy backend` strict; `pytest backend`; drift gate green (schemas must regenerate byte-identically - this row changes no shape).

- **Oracle:** Every file under `schemas/` and `frontend/src/contracts/` regenerates byte-identically, proving the move is purely structural.

- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | `RelPath` and `SourceId` are shared vocabulary, not corpus vocabulary, and `contracts/corpus_sources.py` - which row 13 deletes - currently owns them while `derived_wordlists.py` and `game_wordlist.py` import them. Without this move row 13 leaves a dangling import and `mypy` fails. `contracts/common.py` already exists; this row extends it rather than creating it. `FreqBand` is deliberately NOT moved: it lives in `master_wordlist.py`, which row 13 also deletes, and row 12 decision 8 removes BOTH its usages (`DerivedSelection.bands`, `GameWord.freqBand`) first - so row 12's Oracle includes a zero-hit search for `FreqBand` outside `master_wordlist.py`, or row 13 fails `mypy` for exactly the reason this row exists. | Fowler, audit |
  | 2 | Structural only, its own commit, no shape change - which is exactly why the Oracle is byte-identical regeneration. | Fowler (Beck, two-hat) |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Fold the move into row 3 or row 13 | Mixes a structural move with a shape change, and the byte-identical Oracle - the cheapest possible proof that a move is safe - stops being available. | Fowler |

## 4. Row #3 - `lexicon` + `lexicon-sources` contracts

- **Scope:** Land the Pydantic models and generated schemas for the lexicon and its source registry, with no pipeline code that reads or writes them.

- **Files touched:**
  - `backend/yen_tamizh_backend/contracts/lexicon.py`, `lexicon_sources.py` (new)
  - `backend/yen_tamizh_backend/contracts/__init__.py`
  - `backend/tests/test_core_schemas.py`, `test_contracts.py`
  - `schemas/lexicon.schema.json`, `schemas/lexicon-sources.schema.json` (generated)
  - `frontend/src/contracts/lexicon.*`, `lexicon-sources.*` (generated)
  - `docs/architecture/contracts/schemas.md`
  - `docs/concepts/lexicon.md` (new - the vocabulary is MINTED by this row's contract, so defining it anywhere else would be one concept defined twice; Fowler ratified row 3 as its home)

- **Acceptance gates:** `mypy backend` strict; `pytest backend`; drift gate green; `npm run lint`; `npm run check`.

- **Oracle:** The counters model enforces `sum(count per wordClass) == counters.rows == the provenance-declared row count`, and requires a bucket for every value of the closed enum. Proven by a test that mutates one class count and asserts the model raises. This is the reconciliation that proves the plan's thesis: nothing is discarded. It reads `counters.rows`, NOT `len(words)` - the lexicon is streamed NDJSON with no in-memory row list (row 11 decision 5), so a document model carrying `words: list[...]` cannot exist.

- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | `LexiconEntry` row shape, `extra="forbid"`: `word`, `ezhuthu`, `length`, `wordClass`, `wordhood` (a name-keyed map over a closed `SignalName` enum), `attestedBy`, `frequency`, `spokenRatio`, `freqRank`, `compound`, `definitionTa`, `translationEn`, `synonymsTa`, `meaningSource`, `translationEnSource`, `pos`, `categories`, `categorySource`. Every sparse list column is OPTIONAL with `min_length=1`, never a defaulted empty list: `model_dump(exclude_none=True)` drops `None` but not `[]`, so defaulted empty lists would cost roughly 200 MB of nothing against the row-11 budget. | Fowler + user |
  | 2 | `wordClass` is a closed enum: `headword`, `inflected`, `colloquial`, `properNoun`, `loanword`, `boundStem`, `sandhiArtifact`, `suspectedTypo`, `unclassified`. Every word carries exactly one. | User |
  | 3 | `wordhood` is a NAME-KEYED MAP, not a fixed-arity object, so rows 7 and 8 can each land their own signals without a partially populated struct. | Fowler |
  | 4 | `sources` does not survive. `attestedBy` names only `role=authority` / `role=authored` sources and is what asserts word-hood; which scraper OBSERVED a surface decides nothing and stays in the store. | Fowler + user |
  | 5 | The lexicon carries NO `generatedAt`. Identity is content-addressed through `provenance[].sha256` plus the row count, so a rebuild byte-compares and a hand-edit is detectable. Git records when. | Fowler |
  | 6 | `meaningSource` (enum `attested` / `authored` / `reviewed`) covers the Tamil pair `definitionTa` + `synonymsTa` as ONE reviewable unit, because they compete for ONE display slot - row 14's `meaning` rung - so one provenance state describes what won. `translationEnSource` is the plain source id that won the English translation. Both are build-time provenance and are NEVER rendered to a player. | Fowler + Player |
  | 7 | `freqBand` is NOT carried on the lexicon. A rank-relative band over a population where thousands of rows have `frequency == 0` is a different filter wearing the same name; raw `frequency` plus an absolute floor replaces it (row 12). | Palm |
  | 8 | Migration class is build-time rewrite-in-place: date-stamp `version` plus a `changelog` entry, no read-side migration, because the only reader is `backend/`. | Fowler, CLAUDE.md section 11 |
  | 9 | `pos` is a LIST over a CLOSED `PartOfSpeech` enum, sorted and deduped. A list because a word genuinely holds several - `t1.json` ships `a.adv` on real entries, and a Tamil verbal noun is both. Closed because parts of speech are a fact about the language, not a tunable knob (Holy Law #6 governs knobs; this is the same category as `wordClass` and `FINAL_MEI`), and an open set means a mapping typo silently mints a tag no schema rejects and no selector matches. The enum's members are fixed by the row-4 census, never guessed from a sample. `properNoun` is NOT a member - it is a `wordClass`. One fact, one home. | Fowler |
  | 10 | `spokenRatio` (float 0-1) is published: source D9's share of the summed frequency against D1-D8. Row 11's `frequency` SUM would otherwise DESTROY the per-source split, and that split is the single best familiarity signal in the whole inventory - a word frequent in subtitles and rare in news is everyday spoken Tamil; frequent in news and absent from subtitles is written or formal. It delivers register, concreteness and child-vs-adult at once, from data already on disk, at zero authoring cost. | Palm |
  | 11 | `compound` (bool) is published as a SIGNAL, never a gate: a headword whose ezhuthu prefix and suffix are both independently attested headwords. Row 12 decision 5 currently asserts that long headwords are mostly compounds and therefore easier, and bets the whole difficulty curve on it; this field makes the claim measurable. Sandhi makes it noisy, which is exactly why it is a signal. Same status as `anagramFanOut`. | Palm |
  | 12 | `categorySource` (enum `attested` / `authored` / `reviewed`) is published, and is REQUIRED because a category renders as a PAID hint. A wrong gloss on the summary is embarrassing; a wrong category the player paid an attempt for and then reasoned from is the game lying and taking payment for it - the worst failure available in this plan. Without this field row 14's paid-hint suppression cannot be enforced. | Palm |
  | 13 | THREE meaning fields, not one, because they are three different facts with three different consumers: `translationEn` is a single English equivalent (a FACT, publishable verbatim); `definitionTa` is an explanatory Tamil phrase (row 14's paid rung and the summary's meaning line); `synonymsTa` is a same-language Tamil equivalent set (`orupporut panmozhi`, row 14's paid rung FIRST). The plan's single `gloss` collapsed all three, which is why row 14 decision 4 resolved through a "Tamil gloss" that no contract defined - the paid rung's second step had no field. A field name that does not state BOTH its language and its kind is how the collapse happened; all three names state both. `gloss` and `glossSource` are removed everywhere, on the same terms as `master`. | Fowler, on user challenge |
  | 15 | TWO contracts are exported, not one, because the artifact is a streamed NDJSON set with a sibling header. `Lexicon` is the META document (`version`, `changelog`, `provenance`, `counters`, the partition table) written to `lexicon.meta.json`. `LexiconEntry` is the ROW shape, one per NDJSON line, and it is NOT a `SchemaModel` - `contracts/base.py` forces every `SchemaModel` to carry `version` + `changelog`, which a data row must not. `Lexicon` therefore holds an optional `rowSchema` reference to `LexiconEntry` purely so Pydantic emits it into `schemas/lexicon.schema.json`'s `$defs`; without that reference the row shape would ship with NO schema at all, breaking Holy Law #3 and row 11's own \"artifacts validate against their schemas\" gate. | Fowler, audit |
  | 14 | An English DEFINITION is never a published column. It is a `definitionEn` fact in the STORE, read only by `llm_enrich`. This is where row 4 decision 2 finally cuts cleanly: a one-word TRANSLATION and a SYNONYM are single-term language facts published verbatim; a DEFINITION is a lexicographer's prose in either language, so it is retained as evidence and never republished. The retention rests on the STORE's COST MODEL, not on any one source's volume - a retained fact costs nothing to keep and one optional field to promote, while a dropped fact costs a full re-ingest to restore. A6 was NOT ACQUIRED (row 4; no bulk artifact exists), so A7's Tamil senses are the surviving attested producer: that changes the DENSITY of the evidence, not the decision. It is also chrome discipline: row 14 gives English one demoted tertiary line on the summary, and a 1930s definition sentence in a tertiary line is not a line, it is a paragraph. | Fowler + Jony |
  | 16 | `lexicon-sources` entries of kind `json-array` carry a REQUIRED `elementKind` over the closed set `object` / `string`, with NO default, and it MUST be absent on every other kind. Measured in row 4: A3 (355,275 rows) and A4 (26,485) hold BARE STRING array elements, which row 5 decision 6's inherited "elements must be objects" rule rejects outright - and A3 is signal 4 (`nannulValid`) in row 7, so it cannot be dropped. The object rule never existed because elements are objects; it existed because objects are SELF-TERMINATING - a proper prefix of a complete element is never itself a complete element, which is what makes a `raw_decode` failure mean "read more" instead of "silently wrong value" (`ingest.py`'s docstring names the truncated-NUMBER hazard). A JSON string has that property in full: `raw_decode('"abc')` raises `Unterminated string`. So the contract widens rather than relaxes. Validator, following the existing `_fields_match_the_kind` precedent (stray fields REJECTED, never ignored): `object` requires `rootKey` + `wordField`; `string` requires `rootKey` and forbids `wordField` / `countField` / `categoryField`. No default, because a defaulted `object` is exactly the silent assumption the truncation rule exists to prevent. This lands in ROW 3's initial mint, not row 5 - a contract reopened three rows after it shipped is a Holy Law #3 inversion, and this is the last cheap moment. | Fowler, on the row 4 finding |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | A single numeric word-hood score with no class | A score says how confident, not what KIND. Proper nouns and inflected forms are non-headwords for entirely different reasons, and one of them must never be served while the other is future lemmatizer input. | User |
  | 2 | Publish `senses[]` now | Only Wiktextract produces multi-sense and no Game reads meaning until row 14. This is the general rule for EVERY future enrichment dimension, not a one-off: the STORE retains every fact a source carried, so promoting any retained dimension to a published column is one optional field, one changelog entry, one PUBLISH re-run - zero re-ingest, zero read-side migration (decision 8). That IS the extensibility seam; no additional mechanism is needed. | Fowler |
  | 3 | Keep `generatedAt` for symmetry with `master-wordlist` | It is the master's defect: `ingest.py` fills it from `datetime.now(UTC)`, which already makes the master non-byte-comparable and leaks through `DerivedSource.generatedAt`. | Fowler |
  | 4 | Carry `freqBand` forward unchanged | Same knob values over a different population silently changes what the median served word feels like - a design decision disguised as a rename. | Palm |
  | 5 | Register the lexicon schemas in `frontend/src/contracts/index.ts` | Build-time surfaces the browser never fetches; an ajv validator would ship dead runtime bytes. Same precedent as the corpus and derived schemas, verified against `frontend/src/contracts/index.ts`. | Carmack + Fowler |
  | 6 | A config-declared open `pos` vocabulary | Buys a data-only edit for a set that changes roughly never, and pays for it by removing the only thing that catches `Nouns` vs `noun` vs `nouns`. The VOCABULARY is contract; the raw-tag MAPPING is config (row 5). | Fowler |
  | 7 | A generic `tags: dict[str, list[str]]` bag so future dimensions cost no contract change | Holy Law #3: a schema that validates nothing - a misspelled dimension passes, and a selector naming it silently matches zero rows. Holy Law #6 governs tunable KNOBS, not the data model; minting a persisted field is a section-11 event by design. And it buys nothing, because rejected alternative 2's seam already makes a new dimension one changelog entry with no re-ingest. Same ground the selector-function registry was rejected on. | Fowler |

## 5. Row #4 - Source acquisition + committed fixtures

- **Scope:** Land every lexicon source at its registry path with a recorded sha256 and a committed fixture slice.

- **Files touched:**
  - `datasets/lexicon/sources/README.md` (new)
  - `datasets/fixtures/lexicon/*.jsonl` (new)
  - `.gitignore`

- **Acceptance gates:** `pytest backend` fixture-shape tests; every source present at its declared path with a recorded sha256; raw bytes gitignored.

- **Oracle:** For every source in the inventory the recorded sha256 matches the bytes on disk, and every committed fixture is a byte-exact contiguous slice of its raw source, non-empty and valid in its declared encoding. The distinct POS-tag inventory of A2 (every prefix across all 56,856 rows) and A7 (every `pos` value) is COUNTED and recorded in the PR body - row 3's `PartOfSpeech` enum is fixed from that census, not from a sample. (Reader exercise belongs to row 5's Oracle; no reader exists yet.)

- **Acquisition list:** exactly groups A through E of the source inventory in section 0, and nothing else. Group F is explicitly not acquired.

- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Every source carries an explicit `role` in `authority` / `formEvidence` / `frequency` / `category` / `authored`. Only `authority` and `authored` can assert word-hood; `formEvidence` can only assert that a surface is NOT a headword. | Fowler |
  | 2 | No license gate. Tamil words, their meanings and their synonyms are public-domain facts about a language; a particular dictionary's edited prose is not. Extraction takes the FACT - headword, POS, synonym set, category - into the store, and row 11 never publishes a source's definition sentence verbatim. | User; internal consistency enforced by Fowler |
  | 3 | Raw source bytes stay gitignored; only fixtures and published artifacts are committed. Existing ~265 MB precedent. | Carmack |
  | 4 | A known-bad source stays registered and explained, never deleted - group E. | Fowler |
  | 5 | Group F is enumerated in the plan with a reason per entry, so a later reader does not re-litigate whether the 470 legacy shards were missed. | Fowler |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | A license audit gating the row | Words and meanings are public-domain language facts; the pipeline extracts facts rather than republishing prose, and a restricted source is simply superseded by the next authority. | User |
  | 2 | Commit the raw sources for reproducibility | Hundreds of MB of unreviewed third-party bytes. `origin` + `bytes` + `sha256` make a run provable without them. | Carmack |
  | 3 | Trust the old curated dictionary's `en` as translation truth | Measured unreliable: `ஏடு -> "almagest"`, `கயல் -> "dare"` (a carp), `புனல் -> "funnelled"` (water). A wrong meaning shown to a player reads as a broken game, not a wrong dictionary. Admitted at low precedence only. | Fowler + Player |

## 6. Row #5 - `wordsmith/extract.py` + `config/lexicon-sources.json`

- **Scope:** One reader per source kind, turning raw bytes into normalized observations and facts, one addressable extract file per source.

- **Files touched:**
  - `backend/yen_tamizh_backend/wordsmith/__init__.py`, `extract.py`, `readers.py` (new)
  - `config/lexicon-sources.json` (new)
  - `backend/tests/test_wordsmith_extract.py` (new)
  - `docs/how-to/add-a-lexicon-source.md` (new)
  - `docs/architecture/lexicon/pipeline.md` (new - NO row previously claimed this file though the section 0 doc map assigns it content; row 5 is the first row shipping a stage, so it lands here)

- **Acceptance gates:** `mypy backend` strict; `pytest backend` against real committed fixtures (no mocks, Holy Law #7); config validates against `lexicon-sources`.

- **Oracle:** Each reader over its real fixture is byte-deterministic across runs, and the extract is lossless: `rows out == rows in - counted parse rejects`. PLUS a CHUNK-INVARIANCE predicate: over the committed `spellcheck-wordlist.1x.json` and `huggingface-wordlist.1x.json` fixtures the yielded word sequence is IDENTICAL for `chunk in (1, 2, 3, 7, 64, 4096, 65536)` - `chunk=1` forces a split inside every element, and this is the test that would have caught the missing scalar-element property in the first place. A root array holding `12345` MUST raise, never coerce.

- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Output is `datasets/lexicon/cache/extracts/<source-id>.jsonl`, gitignored. Pure function of (source sha256, registry entry, extractor version). | Fowler |
  | 2 | EXTRACT never filters on word-hood or quality. The only transform is NFC normalization, which is canonicalization, not filtering. | User |
  | 3 | The skip check compares the source's on-disk sha256 against the one recorded in the header line of its OWN extract file. EXTRACT must not read `lexicon.json` - that file is PUBLISH's output and does not exist at this row; making stage 1 read stage 4's artifact is a cycle. The no-sibling-ledger ruling governs committed artifacts and does not reach a gitignored build cache. | Fowler |
  | 4 | Facts are typed `headword`, `translation`, `definitionEn`, `definitionTa`, `synonym`, `pos`, `category`, `graphemeCount`; observations are `(source_id, surface, count)`. `gloss` is not a fact type - it named three different things (row 3 decisions 13, 14). A2's reader emits TWO fact kinds from one row: `translation` read FORWARD (Tamil term -> its English headword) and `synonym` read SIDEWAYS (every Tamil term sharing one English headword), and the sideways grouping key is (`eng`, POS prefix), NEVER `eng` alone - or a noun sense and a verb sense collapse into one synonym set. | Fowler |
  | 5 | This row creates the whole `config/lexicon-sources.json` surface - `outputs`, `categoryAliases`, `posAliases`, per-source `precedence`, and per-source `sha256` + `bytes` - so no later row edits the file concurrently with another. The `sha256` field is what lets CI detect artifact drift with zero network and zero raw bytes: it asserts that the sha256 set declared in the registry equals the set recorded in the published provenance. | Fowler + Carmack |
  | 6 | Every reader is a GENERATOR over a bounded buffer, inherited unchanged from `corpus/ingest.py`: line-at-a-time for delimited sources, `JSONDecoder.raw_decode` over a sliding 64 KB buffer for JSON arrays, line-at-a-time for JSONL. No reader may call `json.load`, `read()` or `readlines()` on a source file. THE ELEMENT RULE IS RESTATED AS ITS ACTUAL PROPERTY: an element grammar is admissible iff it is SELF-TERMINATING - a proper prefix of a complete element is never itself a complete element. Admitted openers are therefore exactly `{` and `"`, selected by row 3 decision 16's `elementKind`; any other leading non-whitespace character raises immediately naming the root key, which is what turns "a number appeared" into a hard failure instead of a silently truncated value. `true` / `false` / `null` are refused even though they raise on truncation, because they cannot be a word. The chunk size becomes a reader PARAMETER (default 64 KiB) so the Oracle's chunk-invariance predicate can drive it. Memory is proven by a SCALING PREDICATE over the fixtures, measured with `tracemalloc.get_traced_memory()[1]` - a 10x fixture peaks within 1.2x of the 1x fixture - NOT by an absolute MB ceiling, which cannot fail over a small fixture, and NOT via `resource.getrusage`, which is POSIX-only and raises `ModuleNotFoundError` on the Windows machine that performs the real run. The absolute peak over the real corpus is an operator observation in the PR body, never a test. | Carmack + Fowler, audit; element rule corrected by Fowler on the row 4 finding |
  | 7 | The nine enabled entries in `config/corpus-sources.json` are ported here with `role: frequency`, retaining their `datasets/corpus/**` paths. `datasets/corpus/` is not deleted in row 13; only its registry moves. | Fowler |
  | 8 | Adding a source stays a data change: registry entry plus a re-run. Only an unseen source FORMAT costs a reader. | Fowler, Holy Law #6 |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | A separate NORMALIZE pass between EXTRACT and STAGE | Normalization is per-source and belongs in the reader that already knows the source's quirks; a shared pass needs a per-source switch, which is the same code in a worse place. | Fowler |
  | 2 | Extract straight into the store with no intermediate file | Delta ingest requires one source's contribution to be recomputable in isolation, and it breaks stage independence. | Fowler + user |

## 7. Row #6 - `wordsmith/stage.py` - the delta store

- **Scope:** The staging store that accumulates every extract, supporting atomic per-source replace and remove without touching another source's rows.

- **Files touched:**
  - `backend/yen_tamizh_backend/wordsmith/stage.py`, `store.py` (new)
  - `backend/tests/test_wordsmith_stage.py` (new)
  - `.gitignore`

- **Acceptance gates:** `mypy backend` strict; `pytest backend`; every store operation inside one transaction; measured distinct-surface count and projected rendered bytes reported in the PR body.

- **Oracle:** `delta == full` over the STAGED zone. A canonical dump (every table `ORDER BY` all columns, `rowid` excluded) of a store built by full rebuild is identical to one built by applying the same extracts one at a time in a shuffled order, and identical again after `--remove` then re-apply of any one source.

- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Substrate is stdlib `sqlite3` at `datasets/lexicon/cache/lexicon.db`, gitignored. Zero new dependency, zero shipped bytes (build-time only; Holy Law #1 constrains runtime); `INSERT ... ON CONFLICT DO UPDATE` and `DELETE WHERE source_id = ?` are exactly the two operations delta ingest requires. Bulk-load pragmas are NAMED, not defaulted: `journal_mode=WAL`, `synchronous=OFF`, `cache_size=-262144`, `temp_store=MEMORY`, `mmap_size=268435456`. Rows are fed by `executemany` over a generator, never a materialized list, and every index is created AFTER the bulk load. Without these an 8.2M-row load runs at 1-3k rows/s - 45 min to 2.3 h instead of under 6 min. `synchronous=OFF` is legitimate here and only here: the db is gitignored and rebuildable, and decision 7 puts the reproducibility anchor on the published artifact. | Fowler + Carmack |
  | 2 | The store has TWO ZONES. STAGED, written only by STAGE: `source(id, sha256, bytes, role, precedence, kind)`, `observation(source_id, surface, count)`, `fact(source_id, word, attr, value, ordinal)`, plus `stage_epoch(n)` bumped on every write. DERIVED, written only by ENRICH: `signal(word TEXT PRIMARY KEY, attested REAL, orthotactic REAL, breadth REAL, nannulValid REAL, knownVerbForm REAL, ngram REAL, neighbour REAL, zipf REAL)` - one row per surface, one COLUMN per signal - plus `classification(word, wordClass)` and `derived_epoch(n)`. The derived zone is a pure function of the staged zone, is dropped and recomputed whole on every ENRICH run, and carries no `source_id` because no signal is per-source. PUBLISH refuses to run when `derived_epoch != stage_epoch`. | Fowler + Carmack |
  | 3 | The signal table is WIDE, not EAV. The name-keyed `wordhood` map of row 3 decision 3 is the PUBLISHED shape; the store is wide because `signal(word, name, value)` at 3,967,009 surfaces x 8 signals is 31.7M rows and ~2.9 GB against 3.97M rows and ~360 MB, and it turns every whole-corpus aggregation into a GROUP BY over 31.7M rows. Rows 7 and 8 stay independent via `ALTER TABLE ADD COLUMN`, which is O(1) metadata in SQLite and free anyway because the zone is dropped and recomputed whole. | Carmack |
  | 4 | Without the zone split the `delta == full` Oracle is FALSE: four of the eight signals are whole-corpus functions, so a delta-built store would carry signals computed over a pre-delta fact set while a full rebuild carries signals over the complete one. Chasing incremental signal update is the wrong goal; recomputing the derived zone is cheap and provable. | Fowler |
  | 5 | `observation` conflict action is `SUM`, which is commutative. `REPLACE` is not and would make merge order matter. | Fowler |
  | 6 | Conflicts among `fact` rows are NOT resolved at merge time. Every fact carries its `source_id` and resolution happens at PUBLISH, which is what makes the staged zone commutative at all. | Hohpe (within Fowler) |
  | 7 | Replace and remove are one transaction each: `BEGIN IMMEDIATE; DELETE ... WHERE source_id=?; INSERT ...; COMMIT`. A corrected re-extraction is a replace; `--remove ID` is the removal entry point. | Fowler |
  | 8 | A SQLite file is not byte-deterministic (page layout, free-list state) and can never be the reproducibility anchor. The anchor is the published artifact. | Fowler |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Committed JSONL as the staging substrate | A one-row delta rewrites a 200 MB file, git history grows by the whole file on every refresh, and there is no upsert primitive. | Fowler |
  | 2 | Parquet | New heavy dependency with no build-time beneficiary, not git-diffable, no upsert. Holy Law #8 unanswered. | Fowler + Carmack |
  | 3 | DuckDB | Buys OLAP scan speed; the required operations are OLTP upsert and delete-by-source, which SQLite does with zero new dependency. | Fowler |
  | 4 | Plain Python dicts, no store | Every delta becomes a full re-merge of every extract - the destructive funnel with extra steps. Not restartable, not inspectable, breaks stage independence. | Fowler |
  | 5 | One zone, with signals namespaced by `source_id` | No signal IS per-source; four are whole-corpus aggregates. A fake `source_id` on a signal row would make `DELETE WHERE source_id=?` silently wrong. | Fowler |

## 8. Row #7 - Word-hood exact signals

- **Scope:** The five signals that are table lookups or store queries: dictionary attestation, orthotactic legality, source breadth, grammar validation, and known verb form.

- **Files touched:**
  - `backend/yen_tamizh_backend/wordsmith/signals_exact.py`, `enrich.py` (new - `enrich.py` is the ONLY writer to the derived zone and lands HERE, so this row's Oracle can be evaluated in its own row; row 8 extends it and row 9 adds the classifier)
  - `backend/yen_tamizh_backend/ezhuthu/word_shape.py` (extended with the orthotactic table)
  - `config/wordhood.json` (created here; rows 8 and 9 extend it)
  - `backend/tests/test_wordsmith_signals_exact.py` (new)

- **Acceptance gates:** `mypy backend` strict; `pytest backend`.

- **Oracle:** Every staged surface receives exactly these five signal values, and the orthotactic table is EXHAUSTIVE over the ezhuthu inventory - a coverage check of the same class as the existing `FINAL_MEI` set.

- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Signal `attested`: binary membership in an `authority` source's `headword` facts (sources A1-A7). | Fowler |
  | 2 | Signal `orthotactic`: Tamil's own rules - which ezhuthu may begin a word, which eight mei may end it, which mei clusters are legal. This is where the old `requireValidWordFinal` goes: a fact about Tamil asked once, not a preference re-asked by every Game. It lives in `ezhuthu/word_shape.py` because it is a fact about Tamil letters. | User + Fowler |
  | 3 | Signal `breadth`: count of distinct sources observing the surface. A real word appears across independent sources; a typo appears in one. | Fowler |
  | 4 | Signal `nannulValid`: membership in source A3, whose 355,275 words were validated by a Nannul-rules Tamil spellchecker. A ready-made grammar judgement already in hand - it costs a membership lookup and answers the user's grammar-compliance question directly. | Fowler |
  | 5 | Signal `knownVerbForm`: membership in sources B1 (1,461,494 inflected verb forms) and B2 (19,249). This is the single largest classification win available - it labels `inflected` by direct evidence rather than inference, and it is free. `formEvidence` sources can only assert NOT-a-headword; they never assert word-hood. | Fowler |
  | 6 | Signal `orthotactic` additionally flags GRANTHA characters - `ஜ ஷ ஸ ஹ` and the compounds `க்ஷ`, `ஸ்ரீ`. These are not among the 247 ezhuthu; they were added to write Sanskrit and foreign sounds, so their presence is positive evidence for `loanword` rather than a defect. Recording it as part of signal 2 costs one table lookup and gives the classifier its cheapest `loanword` discriminator. | User observation |
  | 7 | Every threshold lives in `config/wordhood.json`, never a Python literal. | Holy Law #6 |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Bundle all eight signals in one row | Four different risk profiles - a linguistic table, a statistical model, an all-pairs search, a classifier - which author-a-plan step 2 forbids bundling. | Fowler |
  | 2 | Infer verb inflection from morphological rules instead of using B1/B2 | 1.46M hand-collected forms are already on disk. Inferring what you can look up is a dependency and an error source bought for nothing. | Fowler, Holy Law #8 |

## 9. Row #8 - Word-hood inexact signals

- **Scope:** The three signals requiring a model or a search: ezhuthu n-gram perplexity, nearest-headword edit distance, Zipf residual.

- **Files touched:**
  - `backend/yen_tamizh_backend/wordsmith/signals_inexact.py`, `ngram.py`, `neighbours.py` (new)
  - `backend/tests/test_wordsmith_signals_inexact.py` (new)

- **Acceptance gates:** `mypy backend` strict; `pytest backend`; measured wall clock and peak RSS for the index build and the scoring pass reported in the PR body (targets: under 5 min, under 1.2 GB).

- **Oracle:** All three signal vectors are byte-deterministic across two runs over the same staged zone.

- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Signal `ngram`: a character-level model over EZHUTHU, trained only on `authority` headwords - never on the scraped corpus, or it learns the typos it is meant to detect. The trained model is recomputed from the staged zone on every run and is never a committed artifact. Measured cost: ~2 s to train, 20-40 s to score. | Fowler + Carmack |
  | 2 | Signal `neighbour` uses EZHUTHU-level edit distance via the Row 6 segmentation library. Code-point distance would call two words neighbours because they share a vowel sign. | Fowler |
  | 3 | The index is a HAND-WRITTEN SymSpell-style deletion neighbourhood (~120 lines of stdlib dict plus deletion generation). `maxEditDistance` lives in `config/wordhood.json` and is hard-asserted `<= 2` in code: at d=2 the index is 3.7M entries / ~1 GB and the run is ~30 min; at d=3 it is 9.3M entries / ~2 GB and 2-5 h. | Carmack |
  | 4 | The query set is PRUNED, not all 3.97M surfaces. A surface with `attested`, `knownVerbForm`, or `breadth >= 3` is skipped, because signal `neighbour`'s only consumer is `suspectedTypo`. That is a 2.5-3x cut at zero cost, since row 9 already sequences after row 7. Scoring runs under `multiprocessing.Pool` over rowid ranges (stdlib, ~3.5x on a 4-core runner). | Carmack |
  | 5 | `rapidfuzz>=3.10` is the ONE authorized new dependency, in `[project.optional-dependencies] wordsmith`, never in `[project.dependencies]`, so CI's `pip install -e ".[dev]"` never pulls it. Beneficiary: the signal `neighbour` verification pass, which drops from ~26 min of pure-Python Levenshtein to ~1 min. Byte cost: ~2 MB wheel, build-time only, ZERO shipped bytes. | Carmack, Holy Law #8 |
  | 6 | Signal `zipf` is explicitly the weakest and is recorded as a diagnostic; the classifier may weight it near zero. | Fowler |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | A BK-tree instead of a deletion neighbourhood | Not a peer option at this query volume: ~10k distance computations per query x 3.97M queries x ~40 us is roughly 44,000 CPU-hours. Categorically non-viable. | Carmack |
  | 2 | Naive all-pairs edit distance | ~4e11 comparisons; the row would never finish. | Fowler |
  | 3 | `symspellpy` off the shelf | Code-point oriented, and decision 2 requires ezhuthu-level distance - subclassing its internals is larger than the ~120 lines of deletion generation it would replace. | Carmack (Muratori) |
  | 4 | Commit the trained n-gram model | It is a pure function of the staged zone, so committing it creates a second thing to keep in sync for no benefit. | Fowler |

## 10. Row #9 - `wordsmith/wordhood.py` - the classifier

- **Scope:** Combine the eight signals into exactly one `wordClass` per surface, and write the derived zone.

- **Files touched:**
  - `backend/yen_tamizh_backend/wordsmith/wordhood.py`, `enrich.py` (new)
  - `config/wordhood.json` (new)
  - `backend/tests/test_wordsmith_wordhood.py` (new)
  - `datasets/fixtures/wordhood_golden.jsonl`, `wordhood_expected.jsonl` (new)

- **Acceptance gates:** `mypy backend` strict; `pytest backend`; ENRICH over an unchanged staged zone is idempotent, and ENRICH after a delta equals ENRICH after a full rebuild of the same source set.

- **Oracle:** Two hard predicates, both asserted in the test: (a) the classifier's output over the committed 200-row golden fixture byte-equals the committed expected-output file, so any change in classification is an explicit reviewed diff rather than a drifting number; (b) ZERO fixture rows hand-labelled `sandhiArtifact`, `suspectedTypo`, `boundStem` or `properNoun` are classified `headword` - headword precision on the fixture is 100 percent, because row 12 selects the served wordlist on exactly that class. Per-class recall is reported in the PR body as information, never as a gate.

- **Reference classification, drawn from real committed rows:**

  | `wordClass` | Real examples from `words_ranked.json` / `anagram.json` |
  | --- | --- |
  | `headword` | வாய்ப்பு, மோதிரம், தேவதை, தாழை, கணை |
  | `inflected` | குழந்தைகளை, கொடுத்தேன், நிகழ்ச்சிக்கு, சென்றால், மருத்துவமனையின் |
  | `colloquial` | போனா, சொல்லாம, பார்த்துட்டு |
  | `properNoun` | திமுக, ஸ்டாலின், ராமலிங்கம், விஜய்யின், ரெட்டியார் |
  | `loanword` | பிரான்ஸில், வித்யாலயா |
  | `boundStem` | அசுர |
  | `sandhiArtifact` | ஆய்வுப் |
  | `suspectedTypo` | அதற்க்கு |

- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Word-hood CLASSIFIES, it does not delete. Every surface keeps its row, its signal map and one `wordClass`, so a misclassification is a re-run of one stage rather than a re-ingest. | User |
  | 2 | `inflected` is assigned by DIRECT EVIDENCE first - `knownVerbForm` membership in B1/B2 - and only by inference where no evidence exists. 1.46M labelled forms are the cheapest accuracy in the plan. | Fowler |
  | 3 | `wordClass == unclassified` is a legal outcome of THIS row and the queue row 10 hands the LLM - but it is NEVER servable. Row 12's selection is an allow-list of classes, not a deny-list, so an unclassified word cannot reach a player by omission. | Player |
  | 4 | The high-value discovery case is a surface that is orthotactically clean, broad across sources, has a healthy n-gram score and is still UNATTESTED - that profile is a real modern word the dictionaries missed (`கம்ப்யூட்டர்`), not junk. It routes to `llm_enrich`, never to a discard. | User |
  | 5 | Every weight and threshold lives in `config/wordhood.json`. | Holy Law #6 |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Dictionary attestation alone as the verdict | A 1930s lexicon rejects `கம்ப்யூட்டர்`, and it would be wrong to. Attestation is one signal of eight. | User |
  | 2 | A frequency floor as the quality test | Frequency and word-hood are independent axes: `குழந்தைகளை` is high-frequency and not a headword; `அசுர` is low-frequency and not a word. This is the exact defect of the current pipeline. | User |
  | 3 | A per-class accuracy threshold as the Oracle | A metric is not a predicate - nothing can fail it. Byte-equality against a committed expected-output file plus 100 percent headword precision is deterministic and can fail. | Fowler |
  | 4 | A morphological analyzer to detect inflection properly | Heavy, imperfect dependency. Signals 1-5 separate inflected forms well enough, and the store keeps every surface so a later row can improve it with no re-ingest. | Fowler, Holy Law #8 |

## 11. Row #10 - `wordsmith/llm_enrich.py` - meaning + synonym authoring

- **Scope:** Batch-author Tamil meanings, Tamil synonyms, English translations, part-of-speech tags and categories, and commit the result as an ordinary lexicon source.

- **Files touched:**
  - `backend/yen_tamizh_backend/wordsmith/llm_enrich.py` (new)
  - `config/lexicon-sources.json`
  - `datasets/lexicon/sources/llm-authored/entries.jsonl` (new, committed)
  - `backend/tests/test_wordsmith_llm_enrich.py` (new)
  - `docs/how-to/enrich-the-lexicon.md` (new)

- **Acceptance gates:** `mypy backend` strict; `pytest backend` against a committed fixture; no network call in any test.

- **Oracle:** The committed `entries.jsonl` round-trips through `extract` + `stage` to byte-identical facts across two runs, and every row records `model`, `promptVersion` and date.

- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | The LLM is a SOURCE, not a stage, and NO PAID API CLIENT IS INVOLVED. The agent executing this plan authors the entries itself, in batches, during its own session, and commits the result as `entries.jsonl`. `llm_enrich.py` is therefore a READER AND VALIDATOR of that committed file - the same shape as any other source reader - not a network client. This removes the optional dependency, the key CI must not hold, and the lazy-import carve-out entirely. A model is not reproducible, so it can never sit inside a stage whose Oracle is byte-identity; a committed file is. | Fowler + user |
  | 2 | It authors EVERY published `definitionTa`, conditioned on the retained evidence where it exists (`definitionEn` from A6, A7's Tamil sense prose, `translationEn`, `pos`, `synonymsTa`) and unconditioned where it does not. This is what resolves row 4 decision 2: a TRANSLATION and a SYNONYM are single-term facts published verbatim from their source; a DEFINITION is prose in either language, retained as store evidence and never republished. NOTE, so it is not discovered in execution: NO source in the inventory supplies an attested `definitionTa` - A7's Tamil senses are prose - so `meaningSource` is `authored` on essentially every row until a human reviews it. That is exactly what decision 9's consumption-bounded review exists for, and what makes row 14's paid-hint suppression load-bearing rather than decorative. | Fowler |
  | 3 | Every authored row records `model`, `promptVersion` and date, so a re-run does not silently re-ask and get different answers. A re-ask is an explicit new file plus a `changelog` entry. This provenance is build-time only and is NEVER rendered to a player - an AI badge on some meanings makes a player distrust all of them. | Fowler + Player |
  | 4 | A word whose Tamil meaning cannot be authored confidently gets NO `definitionTa` rather than a hedged one. Row 12's `requireMeaning` gate then decides admission, and row 14's rendering rule decides whether an unreviewed one may be SOLD. A wrong meaning shown to a player reads as a broken game; a wrong meaning the player PAID an attempt for is worse. | Player |
  | 5 | Authored meanings are committed text with per-line diffs, so a bad batch is visible in review and revertible by one commit. | Fowler |
  | 6 | NO new dependency and no API key. `llm_enrich.py` imports nothing beyond stdlib plus the existing contracts: it reads the committed `entries.jsonl`, validates it, and emits facts. CI runs its tests against a committed fixture like every other reader. The earlier `[project.optional-dependencies] enrich` group is NOT created. | Fowler + user |
  | 7 | It authors `pos` on every row it touches. Dictionary POS covers ~57k of 3.97M surfaces and its overlap with the SERVED headword set is unmeasured; without authored POS, row 15's POS dimension may select nothing. Marginal cost is zero - a model authoring a meaning already determined the part of speech. Decision 4's rule binds unchanged: no confident tag means NO tag. | Fowler + Palm |
  | 8 | It authors `categories` from the CLOSED set of existing alias-normalized themes, never minting a new one - a theme is player-facing copy and minting one is a human decision. It is conditioned on the gloss, never on the Tamil string, so the model is not guessing from orthography. Authored categories land as `categorySource: authored` and CANNOT render as a paid hint or select a themed round until a human promotes them to `reviewed`. Free sources are exhausted first: A1's themed tags and A7's category system are attested and cost nothing. | Palm |
  | 9 | Human review is bounded by CONSUMPTION, not by volume: review only rows that can reach a player - having a category AND passing the serving gates. That is low thousands at most, and about 111 for `themed-nature` today. An afternoon, not a project. Review is PER-ROW, not per-field: a reviewed row becomes `categorySource: reviewed` AND `meaningSource: reviewed`. Without the second half nothing in the plan ever produces `meaningSource: reviewed`, and row 14 decision 19 - which makes `reviewed` the only sellable state - would silently reduce the hint ladder to one rung for every served word, a regression on today's two. | Palm + Fowler, audit |
  | 10 | Authoring is BOUNDED to the rows that can be served: `wordClass == headword` AND `minAttestations` AND `minFrequency` satisfied - the row 12 gates less `requireMeaning` itself. This row reports that count and the measured token cost in the PR body BEFORE the batch runs, and that figure is the baseline the section 0 3x-overrun trigger measures against. Without a bound, "authors every published meaning" is an unbounded spend against an estimate that appears nowhere. IT ALSO REPORTS, before the batch: (a) the ZERO-EVIDENCE subset - rows carrying none of `definitionEn`, `translationEn`, `pos`, `synonymsTa`, `categories`; (b) after authoring, the count that received no `definitionTa` under decision 4; and (c) the DECLINE COUNT - otherwise-servable rows that then fail `requireMeaning`, which is the size of row 12's relaxation lever 1 quantified in advance. If (c) drops the `requireMeaning`-passing set below row 12 decision 14's floor, that is a row-12 ESCALATION, never a silent pass. | Fowler + Palm, on the row 4 A6 finding |
  | 11 | AUTHORING IS EVIDENCE-TIERED, and the bottom tier is NOT AUTHORED. The row publishes an evidence census over its bounded set - E1 `definitionEn` or Tamil sense prose (A7 only, <= 13,773 rows); E2 `translationEn` + `pos`; E3 `translationEn` only; E4 an A2-read-sideways `synonymsTa` group only; E5 nothing but the Tamil string and its frequency. **E5 rows are not authored**: no translation, no POS, no synonym set and no sense prose means no `definitionTa`, so the row fails `requireMeaning` and is not served. This AMENDS decision 2's "unconditioned where it does not exist". The principle is already in the plan - decision 8 forbids authoring `categories` from the Tamil string because that is guessing from orthography - and it must bind HARDER on the field that reaches the player and gets SOLD as a paid rung, not softer. E5 is the bucket A6's absence inflated, and it is the bucket that produces inventions. The compensation is evidence already acquired but under-used: A2 read SIDEWAYS is real authoring evidence, not merely an extraction feature, and `spokenRatio` is register evidence at zero cost. Neither is a substitute for A6, which stays NOT ACQUIRED. | Palm |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Call the model live during PUBLISH, or from a paid API client in code | Destroys reproducibility, makes the build network-dependent, and puts a key in the repo's dependency surface. The authoring agent writes a committed file instead; `llm_enrich.py` only reads it. | Fowler + user |
  | 2 | Publish a source's definition SENTENCE verbatim, in either language | Contradicts row 4 decision 2 - a definition is the source's prose, not a language fact. A one-word translation and a synonym ARE facts and ship verbatim; the sentence stays in the store as authoring evidence. | Fowler |
  | 3 | Badge authored meanings in the UI | The moment some meanings carry an AI mark, a player distrusts all of them including the dictionary's. | Player |

## 12. Row #11 - `wordsmith/publish.py` + `pipeline.py`

- **Scope:** Resolve every word's facts into one published row, stream the configured renderings, and expose the sequencing entry point.

- **Files touched:**
  - `backend/yen_tamizh_backend/wordsmith/publish.py`, `resolve.py`, `pipeline.py` (new)
  - `backend/yen_tamizh_backend/corpus/artifact.py` (reused for SMALL artifacts only; moved in row 13)
  - `backend/tests/test_wordsmith_publish.py` (new)
  - `datasets/lexicon/by-class/<wordClass>.ndjson`, `datasets/lexicon/lexicon.meta.json` (new, committed)
  - `docs/how-to/rebuild-the-lexicon.md` (new)

- **Acceptance gates:** `mypy backend` strict; `pytest backend`; committed artifacts validate against their schemas; PUBLISH memory proven by the same `tracemalloc` scaling predicate as row 5 decision 6, never an absolute ceiling and never `resource`; INTEGRATION tier - `pipeline` run end to end over the committed fixture source set produces a byte-identical committed fixture lexicon, exercising all four stage boundaries with real fixtures (no mocks, Holy Law #7, CLAUDE.md section 13).

- **Oracle:** Re-publishing from an unchanged store is byte-identical; the per-class counters in `lexicon.meta.json` sum to the declared row count; every published row's `ezhuthu` rejoins to exactly its `word`.

- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Resolution rules, all config-declared: `frequency` = SUM over frequency-role sources; `spokenRatio` = D9's share of that sum; `attestedBy` = sorted authority sources carrying a `headword` fact; `pos` = UNION over every source carrying a `pos` fact, translated through `posAliases`, deduped and sorted; `synonymsTa` = UNION; `categories` = UNION normalized through `categoryAliases` so `Birds` and `birds` collapse; `translationEn` = highest-precedence source carrying a `translation` fact, because it occupies one display slot. `definitionTa` comes from row 10. `definitionEn` is never published. | Fowler, Holy Law #6 |
  | 2 | `pos` UNIONS while `translationEn` RESOLVES, and the difference is not arbitrary: a translation occupies ONE display slot so one source must win, whereas `pos` is a set-valued fact with no slot - a Tamil verbal noun is genuinely both, and precedence would delete whichever a lower-ranked source held. `formEvidence` sources B1/B2 contribute `pos: verb`; row 4 decision 1 restricts who may assert WORD-HOOD, and POS is not word-hood - which POS-labels ~1.46M `inflected` rows at zero cost. A wrong tag stays traceable through the store's per-fact `source_id`. Strictness (intersects vs equals) is a SELECTION knob in row 15, never a resolver behaviour. | Fowler |
  | 3 | A source's category value that names a PART OF SPEECH routes to `pos`, never to `categories`. C1's `Nouns` (622), `Verbs` (180) and `Adjectives` (25) are 64 percent of its rows and are not themes; leaving them in `categories` would make `Nouns` the largest "theme" in the lexicon, repeating the blanket-`nouns` mistake already corrected once. The POS-name set and the raw-tag map `posAliases` both live in `config/lexicon-sources.json` beside `categoryAliases`. A raw POS tag with no `posAliases` entry is a HARD PUBLISH FAILURE naming the tag and its row count - never dropped (a silent boundary drop is the defect this plan exists to remove) and never passed through (that defeats the closed enum). CLAUDE.md section 10: fail fast at the boundary. | Fowler + Palm |
  | 4 | Precedence is an explicit per-source integer, not the registry array order, so reordering the array for readability can never silently change a published value. | Fowler, Holy Law #6 |
  | 5 | PUBLISH STREAMS. The lexicon renders as NDJSON - one `json.dumps(row, ensure_ascii=False, sort_keys=True)` per line written straight to a temp handle from a `sqlite3` cursor, then `os.replace`. The handle is opened with `newline="\n"` and `encoding="utf-8"` EXPLICITLY: the operator runs Windows, where Python's default text mode translates `\n` to `\r\n`, which would break the byte-identity Oracle on the very machine that performs the real publish. Peak memory is one row. `render_document` is retained for the SMALL artifacts and is explicitly NOT used for the lexicon: it materializes the joined string three times over, ~12.6 GB at 3.97M rows - arithmetic about materializing the same content four times, not a property of any machine. The decisive reason is not memory: streaming is FEWER LINES than materializing, and row 5 decision 6 already forces generator-over-bounded-buffer at EXTRACT. The header (`version`, `changelog`, `provenance`, `counters`, the partition table) is the sibling `lexicon.meta.json`. | Carmack + Fowler |
  | 6 | EVERY word is published at FULL FIDELITY - no class carries a reduced row. Files partition by `wordClass`, and a class over the size target partitions further by ezhuthu `length` (decision 8). Measured: ~3.97M rows at ~212 B (the ~372 B row less `wordhood`) is ~750-840 MB across roughly 10-15 files. The earlier class-appropriate-fidelity rule is REVERSED: a `word`-only line for `inflected` would discard `frequency`, a SOURCE-ASSERTED fact recoverable only from gitignored raw bytes and a URL fetch. That is a real drop, and the directive is literal. NAMED CONSUMERS for the classes `derive.py` never reads, so a later size pass cannot mistake them for dead weight: the `inflected` files ARE Wordle's guess-accept list (a player typing an ordinary inflected Tamil form and being rejected concludes the game does not know Tamil, and agglutination makes that the common case), and the retained multiset index plus the `headword` files are what Word Ladder's build-time reachability graph is proven from - `docs/concepts/games.md` already commits to proving it. | User directive + Palm, audit |
  | 7 | Exactly two columns are omitted - `wordhood` and `freqRank` - under a stated PRINCIPLE, not case by case. A column is omitted only if BOTH: (a) it is a DERIVED DIAGNOSTIC of this pipeline, never a fact a source asserted about the word; and (b) omitting it cannot cost the project the fact - either it is recomputable from the COMMITTED ARTIFACT ALONE (`freqRank` is a sort of the published `frequency`), or the VERDICT it produced is published (`wordClass` IS `wordhood`'s verdict, and it is what every consumer reads). `wordhood` is additionally 160 B of a 372 B row - 43 percent of the artifact for eight floats nothing reads. The test is deliberately "from the committed artifact", NOT "from the sources": `frequency` is recomputable from D1-D9, so a source-based test would re-permit the `word`-only line the user rejected. | Carmack + Fowler |
  | 8 | Files partition by `wordClass`, then by ezhuthu `length` for any class over the size target, then by the word's BASE FIRST EZHUTHU for any cell still over it. The target is 50 MiB, not the 100 MiB hard block. All three keys are IMMUTABLE PER WORD, and that - not the byte figure - is the decision: `length` and the first ezhuthu are functions of the word itself, so a delta can only INSERT into a cell, never reshuffle one; only a changed `wordClass` moves a row, which is a real reviewable event. The base first ezhuthu is `segment(word)[0][0]` - the uyir / mei / aytham codepoint the first ezhuthu is built from, 31 values and about 35 counting the grantha consonants loanwords carry - rendered in the filename as lowercase 4-digit hex (`inflected-5-0b95.ndjson`) so every path stays ASCII, with `lexicon.meta.json` mapping every hex to its ezhuthu, row count and sha256. Because the first ezhuthu is the PRIMARY SORT KEY of decision 11's `word` ASC order, this is a RANGE partition aligned with the sort, not a hash partition: concatenating a cell's files in slug order reproduces the sorted cell exactly. The split applies PER CELL, only where the measured byte table says a cell overflows, never uniformly - a uniform split would mint hundreds of empty files. It is TERMINAL: no depth-2, no split-depth register, no reshuffle, because ~35-way fan-out takes the worst plausible cell (63-106 MB) to ~13-21 MB and single-digit-percent growth over a CLOSED source inventory never returns it to the target. This row MUST report the measured per-(`wordClass`, `length`) byte table in the PR body and freeze the layout from it, splitting PRE-EMPTIVELY at first publish every cell projected over 50 MiB, so no already-published cell is ever re-split later. | Carmack + Fowler, on user challenge |
  | 9 | The full rebuild is OPERATOR-ONLY. CI runs `mypy`, `pytest` and the fixture-pipeline integration gate, and nothing else; `daily.yml` gains no lexicon step. Raw sources are gitignored so CI has nothing to rebuild from, and a nightly rebuild would shift frequency sums and therefore the candidate list every night, making row 12's no-rewrite rule unenforceable in principle. CI's drift check is the zero-network sha256-set comparison from row 5 decision 5. | Carmack |
  | 10 | `pipeline.py` only sequences the four stages and holds no logic of its own, so each stage stays independently runnable. | User |
  | 11 | Row ORDER is defined, because dropping `freqRank` removes the total order both byte-identity Oracles relied on (`derive.py` says so in writing). Lexicon NDJSON rows sort by `word` ASC - the store's primary key, therefore total. Sorting by `word` rather than frequency is decision 7's own churn argument: a frequency sort reshuffles nearly every line on any source change, whereas a `word` sort makes a refresh INSERT lines in place, so the diff is the words that actually changed. Sorting by `word` is also what makes decision 8's third partition key free: the first ezhuthu IS this sort's primary key, so a sub-split is a range cut on an order that already exists rather than a new index. `derive.py` sorts `frequency` DESC then `word` ASC as the explicit tie-break replacing the removed rank. | Fowler + Carmack |
  | 12 | ~750-840 MB of committed lexicon is accepted: no file exceeds the block, the repo already commits ~265 MB, and a refresh is a handful-of-times event. The named consequence: every workflow that checks this repo out and never reads the lexicon adds a `sparse-checkout` excluding `datasets/lexicon/` in this same PR - one line PER CHECKOUT, not one line total. Git LFS is REJECTED: it makes the files unreviewable in a diff, which is the whole reason NDJSON beat SQLite, and it meters every CI checkout. | Fowler + Carmack |
  | 13 | WHAT THE PARTITION IS OPTIMISING FOR, stated so it is not mistaken for premature optimization. The browser NEVER reads these files; the only consumers are `derive.py` at build time, a human reading a diff, and git storage. So there is exactly ONE hard constraint - GitHub REJECTS any blob over 100 MiB, which is a wall, not a preference - and three soft goals: a diff a human can review, a read pattern that matches the consumer, and a layout that GROWS without reshuffling. `wordClass` then `length` serves all three, because `derive.py` asks for exactly "headwords of length 3-6" and that IS a cell address. Read locality is a `headword` property specifically, not an artifact-wide one: row 12 decision 1 serves `wordClass: ["headword"]`, so the only class `derive.py` ever reads is the small one that never sub-partitions, while the cells that DO overflow (`inflected`, `unclassified`) have no reader at all. The GROWTH goal is what selects the partition KEYS: every key must be immutable per word, or a refresh rewrites files it did not change. The 50 MiB target is headroom against the wall, not a performance number. File COUNT is an output of the measured byte table, never a goal. | Carmack + user challenge |
  | 14 | THE STABILITY ARGUMENT, worked through rather than asserted. Within a file rows sort by `word` ASC, so on a refresh: a new word INSERTS one line; a changed `frequency` or meaning rewrites one line IN PLACE; `length` and the first ezhuthu never change, because both are properties of the word itself; and only a changed `wordClass` moves a row BETWEEN files, which is two line changes and is precisely the semantic event a reviewer should see. There is exactly ONE event that rewrites a cell wholesale - decision 8's PRE-EMPTIVE split, applied once at first publish from the measured byte table and visible in the meta `changelog` as a layout change. It is not a growth mechanism; it is a layout freeze. This is the property that eliminated a fixed shard count: a hash modulus reshuffles the whole cell on the day it changes, which is the same churn a frequency sort would cause, arriving later and with less warning. | Fowler + Carmack |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | One `lexicon.json` holding every word at full fidelity | ~3.97M rows at ~372 B is ~1.48 GB, and GitHub hard-rejects any blob over 100 MiB. Partitioning by class then by ezhuthu length clears it at FULL fidelity (decisions 4 and 6); reducing per-row fidelity is not needed and was rejected by the user. | Carmack |
  | 1a | Class-appropriate fidelity - a `word`-only line for the bulk non-word classes | It discards `frequency`, a source-asserted fact recoverable only from gitignored raw bytes. `freqRank` is a sort of a published column; `frequency` is not. The two cases are not alike. | User + Fowler |
  | 1b | Publishing `pos` by precedence rather than union | Deletes a true fact - a verbal noun is both - because of a ranking that exists for a different purpose. | Fowler |
  | 2 | Use `render_document` for the lexicon | It materializes the row list, the joined string, the `replace` copy and the encode buffer simultaneously - ~12.6 GB peak. Its own comment sizes it for a 12 MB artifact. | Carmack |
  | 3 | Commit the SQLite file | A binary blob cannot be reviewed in a diff and bloats history on every rebuild. Rebuilt from the committed NDJSON by one command. | Fowler + user |
  | 4 | Rebuild the lexicon in CI or in `daily.yml` | The raw sources are gitignored, so CI has nothing to rebuild from, and nightly frequency drift would change already-published days. | Carmack |
  | 5 | Defer the size question to a STOP-AND-SURFACE at execution time | The escalation is guaranteed to fire - the numbers are already known - so it belongs in review, not after ten rows of work. | Carmack |
  | 6 | Partition by frequency band instead of `wordClass` + `length` | Frequencies change on every refresh, so words would MIGRATE between files constantly - the reshuffle that decisions 9 and 12 exist to prevent. | Carmack |
  | 7 | Partition by a hash of the word only | Stable, but it destroys both soft goals: no read locality for `derive.py`, and "what changed in headwords?" would span every file. The base first ezhuthu is equally stable AND is the sort's own primary key, so it costs nothing that the hash cost. | Carmack |
  | 8 | Sub-partition an oversized cell by a fixed hash modulus chosen at authoring time | The modulus is unfalsifiable at authoring time - nobody can know 2029's row count - and the day it changes every row in the cell moves, the exact reshuffle decisions 11 and 14 exist to prevent, deferred rather than avoided. It also inverts decision 13: headroom in the modulus means shipping that many small files today as a guess, making file count a goal. | Fowler, on user challenge |
  | 9 | Extendible hashing - a cell splits by consuming one more bit of `sha256(word)`, per-cell depth recorded in the meta | Correct engineering for UNBOUNDED growth; this artifact has a CLOSED source inventory and single-digit-percent growth a handful of times ever. It buys a split-depth register, recursive-split boundary conditions and a meta lookup before any address can be computed - all executed unattended. Ceremony with no named beneficiary. Named here as the escape hatch if the ESCALATE trigger ever fires. | Fowler (Durov) |
  | 10 | Append-only overflow files - `headword-4.ndjson`, then `headword-4.001.ndjson` | Growth is trivial, but the address stops being a pure function of the word: PUBLISH must read the PREVIOUS layout to place a row, so the artifact becomes a function of its own history and "re-publishing from an unchanged store is byte-identical" holds only when a prior artifact is present - a clean checkout would produce a different layout. Reproducibility, not sortedness, is what kills it. | Fowler |
  | 11 | A fixed row count per file | One insert shifts every subsequent row across a file boundary - the worst churn of any option here, and the one an executing agent is most likely to reach for. | Carmack |

## 13. Row #12 - Cut the derived layer over; real serving gates; two-axis difficulty

- **Scope:** Point the derived layer at the lexicon, gate what is SERVED as distinct from what is PRESENT, replace length-only difficulty, and regenerate.

- **Files touched:**
  - `backend/yen_tamizh_backend/wordsmith/derive.py` (moved from `corpus/`)
  - `backend/yen_tamizh_backend/generate/daily.py`, `generate/anagram.py`
  - `backend/yen_tamizh_backend/scripts/generate_today.py`
  - `backend/yen_tamizh_backend/contracts/derived_wordlists.py`, `game_wordlist.py`, `daily_generator.py`
  - `config/derived-wordlists.json`, `config/daily-generator.json`
  - `datasets/wordlists/derived/anagram.json`
  - `schemas/**`, `frontend/src/contracts/**` (generated)
  - `docs/how-to/add-a-derived-wordlist.md`, `docs/concepts/difficulty-and-scoring.md`, `docs/architecture/contracts/schemas.md`

- **Acceptance gates:** Full backend and frontend gates; browser smoke per CLAUDE.md section 12.

- **Oracle:** The regenerated `anagram.json` byte-equals a fresh re-derive; `அசுர`, `திமுக` and `ஸ்டாலின்` are all absent; every served row satisfies all four gates; a search for `FreqBand` outside `master_wordlist.py` returns zero hits; and no already-published bank day is rewritten (the guard itself landed in row 1).

- **The quality target this row is judged against**, because four gates asserted as sufficient with no measured target is an untestable claim. Player's tolerance, recorded: one unknown word in a day of three is the GOOD day - it is the one worth telling someone about; two of three is annoying; three of three twice in a week ends the streak and the habit. The gates are therefore tuned until a 30-day sample of baked days holds a MEDIAN of at most one word per day outside the top frequency quartile, and no day has three. That sample is run and reported in the PR body.

- **The serving gates** (PRESENT is everything; SERVED must satisfy all four). This table holds ADMISSION tests only; suppressing an unreviewed VALUE is a rendering rule in row 14, not an admission gate - gating admission on a category would cut the served set to the ~1,290 rows carrying one, which decision 4 forbids.

  | Gate | Shipping default | Why |
  | --- | --- | --- |
  | `wordClass` | `["headword"]` | Production vs recognition - see decision 1 |
  | `minAttestations` | `2`, PLUS the tier-1 composition rule (decision 14) | Single-authority headwords are where 1930s dead vocabulary and model inventions live |
  | `minFrequency` | `1` | A dictionary word appearing zero times in 3.9M words of modern Tamil is a museum piece. Does the most work of the four |
  | `requireMeaning` | `true` | A word whose Tamil meaning could not be authored is a word nobody should be served - it can carry neither the summary line nor the paid rung |

- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | `wordClass: ["headword"]` for the anagram, and the REASON is production vs recognition, not dictionary authority. The anagram asks the player to PRODUCE an exact ezhuthu sequence, so a word with unsettled orthography (`போனா` / `போனாள்`; `பார்த்துட்டு` / `பாத்துட்டு`) hands out tiles encoding one dialect's spelling and punishes every other. The reason is written into the set's `note` field, not just the value. `colloquial` belongs in `word-search` and `missing-letters`, where the player RECOGNISES a spelling instead of producing it. | Palm |
  | 2 | `properNoun` is never served, in any Game. This is a GOAL of the cutover, not a byproduct: the currently committed `anagram.json` serves `திமுக` (a political party) and `ஸ்டாலின்` (a sitting politician) in a game a child may play in Tamil Nadu. | Palm |
  | 3 | Selection is an ALLOW-LIST of classes, never a deny-list, so an `unclassified` word cannot reach a player by omission. | Player |
  | 4 | `categories` must NOT gate admission. Only 1,290 words carry one, so gating on it cuts 17,313 back to about a thousand and re-creates the scarcity this plan exists to remove. Categories are a selection dimension, never an admission test. | Palm |
  | 5 | Difficulty becomes two-axis, length x familiarity: easy = 3-4 ezhuthu, top frequency quartile; medium = 4-5, top half; hard = 5-6, anything above the floor. The overlap is deliberate. Length-only is now anti-correlated at both tails: long Tamil headwords are mostly compounds that decompose into recognisable chunks and are EASIER, while short rare words are brutal - so today's `easy: minLength 3, maxLength 3` forces the generator into the shortest words, and short Tamil words are disproportionately literary. The current easy bucket is the one most likely to serve a museum piece. A 3-ezhuthu answer also has only 6 arrangements against 3 attempts, so it is BRUTE-FORCEABLE by shuffling without the player ever knowing the word - a hollow win, not an unfair one. Raising the easy floor to 4 is what makes an easy solve mean something, and is why the bands overlap rather than tile. | Palm + Player |
  | 6 | `pick_words` draws frequency-STRATIFIED within each difficulty bucket, not a uniform shuffle. A uniform shuffle over 17k means the median served word is the median dictionary word, which is far rarer than the median word a person knows. Quartiles are computed over the SERVED set from the published `frequency`, never over all 3.97M surfaces - a lexicon-wide quartile is meaningless for difficulty. | Palm |
  | 7 | The cutover re-bake starts at `today + daysAhead + 1` and NEVER rewrites an already-published day. Not because of a leaderboard - because two players comparing "did you get today's?" is the shared ritual, and it breaks if one holds a precached day and the other a re-baked one. ONE exception, named rather than discovered: if an already-published day serves a `properNoun`, rewriting it is the lesser harm and the operator rewrites it deliberately. | Palm |
  | 8 | The no-rewrite rule is ENFORCED IN CODE and that guard ALREADY LANDED IN ROW 1 - this row only relies on it. `generate()` skips any date whose file exists unless `--rebake` is passed, while the index is still rebuilt from disk so it cannot drift. Without the guard, `write_artifact` overwrites today..today+`daysAhead` on every cron tick and the first `daily.yml` run after this cutover would rewrite seven already-published days. | Carmack |
  | 9 | With decision 8's guard in place NO service-worker cache-bust is needed, recorded so it is not re-litigated: `vite.config.ts` `globPatterns` excludes `json`, so no bank file is precached; the bank is runtime-cached `StaleWhileRevalidate`; every new day is a new URL and therefore a cache miss that fetches correct bytes on first open. | Carmack |
  | 10 | `requireValidWordFinal` and its `invalidWordFinal` counter bucket are deleted here, superseded by row 7's orthotactic signal. `DerivedSource.generatedAt` is dropped. `masterPath` -> `lexiconPath`; `DerivedCounters.masterRows` -> `lexiconRows`; `outsideBand` is deleted with the bands. THE LEDGER IS RESTATED, because removing buckets without restating it leaves the plan's integrity Oracle with no arithmetic: `lexiconRows - outsideLength - outsideClass - belowAttestations - belowFrequency - withoutMeaning - capped == rowsKept == len(words)`, one bucket per serving gate, in gate order. `GameWord.freqBand` is REPLACED by `frequency: int` - `FreqBand` lives in `master_wordlist.py`, which row 13 deletes, and `frequency` is what both `minFrequency` and decision 6's stratified draw actually read. `DerivedSource` becomes `{metaPath, version, sha256, rows}` where `sha256` digests `lexicon.meta.json`, which itself carries every cell's sha256 - so one digest still pins a partitioned input; `derive.py` resolves cells by READING `lexicon.meta.json`, never by globbing the directory. | Fowler + Carmack, audit |
  | 11 | Band-based selection is removed entirely, replaced by the absolute `minFrequency` floor plus the stratified draw. | Palm |
  | 12 | `difficulty_of` in `generate/anagram.py` is edited HERE, with the two-axis bands, not in row 14 - decision 5 is meaningless if the function that computes difficulty still reads length alone. `config/daily-generator.json`'s `difficulties` array gains the frequency-stratum bound alongside the length bound. | Carmack, audit |
  | 13 | `_SCHEMA_VERSION` is date-stamped with a `changelog` entry naming every removed and added field, in the same commit. | Fowler, CLAUDE.md section 11 |
  | 14 | `minAttestations: 2` HOLDS at six authorities, but "attested" is REDEFINED compositionally, because row 4 measured the pool: A6 was not acquired and A7 is only 13,773 rows. Split the six by what their unit IS. TIER 1 - LEXICOGRAPHIC (an ENTRY: headword plus at least one of gloss / definition / POS / synonym / category): A1 (104,421), A2 (56,856), A7 (13,773). TIER 2 - ENUMERATIVE (a STRING in a list): A3 (355,275), A4 (26,485), A5 (36,082). THE GATE: a row is served only if `len(attestedBy) >= 2` AND `attestedBy` contains AT LEAST ONE tier-1 source. Two bare wordlists is not enough - A3 alone is 3.4x A1 and will co-occur with nearly any orthographically legal string, so plain 2-of-6 collapses to "one wordlist plus a spellcheck"; worse, A3 membership is ALREADY signal 4 (`nannulValid`) feeding `wordClass` in row 7, so counting it again at the gate charges the same evidence twice. Riders: (a) `role=authored` NEVER counts toward the gate unless `meaningSource == reviewed` - the gate's own reason names "model inventions", and an unreviewed model row cannot be the evidence that a model row is real, while a human review under row 10 decision 9 IS an attestation act and does count; (b) a tier-1 attestation must be a SINGLE EZHUTHU-STRING unit - A2's comma-separated gloss cells and A5's 8,686 underscore-joined phrases attest the PHRASE, not the words inside it, and that is dropped at EXTRACT in row 5, not at the gate; (c) A1 counts tier-1 on EVERY row, not only its 12,954 rows carrying `en`, because tier-1-ness is a property of the source's FORMAT - otherwise the gate silently becomes "must carry an English gloss", a different gate wearing this one's name. | Palm, on the row 4 finding |
  | 15 | THE SERVED-SET FLOOR, stated in units that bind rather than as a fraction of row 1's 17,313: at least 6,000 served rows at 3-6 ezhuthu, AND no (difficulty bucket x frequency quartile) cell below 100 rows. Derivation: decision 5 gives three buckets and decision 6 draws frequency-stratified within each, so there are 12 cells; one word per bucket per day is ~365 rows per bucket per year and ~91 per cell per year, making 6,000 roughly five years of non-repeating play with every cell non-degenerate. A thin cell is what puts a museum piece on the board. If the measured number lands under the floor, the RELAXATION ORDER is fixed and never re-ordered: (1) run MORE of row 10 - `requireMeaning` gates on row 10's output, so the first answer to an undersized set is "author more meanings", not "lower a bar"; (2) raise the hard ceiling from 6 to 7 ezhuthu, since decision 5 already argues long headwords are compounds that decompose and are EASIER, so the ceiling was set for feel and widening it costs nothing on the familiarity axis; (3) drop decision 14's tier-1 composition rule back to plain 2-of-6, giving back word-hood precision that a later source can restore. NEVER `minFrequency: 0` - it is the gate doing the most work and the only one measured against Player's tolerance. NEVER admit `loanword` or `colloquial` - decision 1's reason binds identically, loanword orthography being no more settled than colloquial. If all three levers are spent and the set is still short, the answer is a NEW SOURCE acquired as a data change, not a lower bar. Parity with row 1's 17,313 is explicitly NOT a goal: it is a number no player can perceive, and it includes the two proper nouns this cutover exists to remove. | Palm |
  | 16 | A6's absence threatens EVIDENCE QUALITY, not served-set SIZE, and the plan records why so row 12 does not panic at it: A6's unique contribution over A1 is 1930s literary Tamil, which is exactly the vocabulary `minFrequency: 1` and the top-quartile stratified draw exist to REMOVE - a source whose distinctive rows are deleted by two downstream gates cannot be a size dependency. The sharper consequence: `minAttestations`' own written reason names "1930s dead vocabulary", and A6 WAS the 1930s lexicon, so losing it discharges half that gate's justification - the second reason decision 14 tightens compositionally rather than by raising the number. | Palm |
  | 17 | SIX MEASUREMENTS THIS ROW'S PR BODY MUST ADD, over and above the 30-day sample, the gate ledger, the byte-equal re-derive and the three named absences. (1) The ATTESTATION COMPOSITION HISTOGRAM of the served set - the `len(attestedBy)` distribution, and the count of served rows whose ONLY tier-1 leg is A7; A7 is 13,773 rows and deprecated upstream, so a large count means the served set has a single point of failure that will never refresh. (2) The A3-DEPENDENCY NUMBER - served rows that would fall below `minAttestations` if A3 stopped counting, which is what says whether decision 14's gate is doing real work or is a spellcheck in disguise, and which quantifies the reserve tightening lever before anyone needs it. (3) A MARGINAL GATE TABLE alongside the sequential ledger - rows removed by each gate IN ISOLATION. Keep the sequential ledger unchanged as the integrity Oracle; without the marginal table, "`minFrequency` does the most work of the four" stays an assertion, and this plan's own standard (row 15 decision 10) is that asserted counts get measured. (4) The 12-CELL OCCUPANCY TABLE (3 difficulty buckets x 4 frequency quartiles) plus the served total at 3-6 ezhuthu, which makes decision 15's floor a printed number rather than an inference. (5) The `compound` CORRELATION - share of served 5-6 ezhuthu rows with `compound == true` versus 3-4 ezhuthu; row 3 decision 11 published that field specifically to make decision 5's bet measurable, and THIS is the row that bets the whole difficulty curve on it, so if long headwords are not mostly compounds the hard bucket is mis-specified and must be re-tuned BEFORE the cutover ships. (6) The 30-day sample scored against `spokenRatio` AS WELL AS frequency quartile - "outside the top frequency quartile" is a leaky proxy for "unknown to the player", because a word frequent in news and absent from subtitles is formal written Tamil that reads as unknown while sitting in the top quartile; `spokenRatio` is already published, so reporting both costs one column and is what actually tests Player's tolerance. | Palm |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Admit `colloquial` to the anagram | Not patronising to exclude it - protective. Colloquial forms have no settled orthography, so the tile set silently encodes one dialect. Signal 5 will show exactly this: they are thin and single-source BECAUSE their spelling is unstable. | Palm |
  | 2 | Admit `inflected` | `குழந்தைகளை` hands the player `கள்` and `ளை` as visible suffix tiles, degrading the puzzle to "unscramble the stem, then bolt on the ending you already spotted". It also breaks uniqueness - a player forming `கொடுத்தாள்` from `கொடுத்தேன்`'s tiles produced real Tamil and got a red X. | Palm |
  | 3 | Ship the knobs at `null` / `false` and tune later | The defaults ARE the design decision; knobs landing unset is the failure mode. | Palm |
  | 4 | Keep length-only difficulty | Anti-correlated at both tails, and the easy bucket is the worst offender. | Palm |
  | 5 | Big-bang replacement of `corpus/` in one PR | Live consumer chain: derive -> daily bank -> the committed bank the player fetches. | Fowler |

## 14. Row #13 - Retire the corpus layer; purge the retired `master` identifiers

- **Scope:** Delete the superseded corpus ingest and its contracts, config, schemas and artifact, and remove every retired identifier.

- **Files touched:**
  - Delete: `backend/yen_tamizh_backend/corpus/` (whole package), `contracts/master_wordlist.py`, `contracts/corpus_sources.py`, `scripts/rebuild_wordlists.py`, `config/corpus-sources.json`, `datasets/wordlists/master/`, `schemas/master-wordlist.schema.json`, `schemas/corpus-sources.schema.json`, `docs/how-to/add-a-corpus-source.md`
  - Move: `corpus/artifact.py` -> `wordsmith/artifact.py`
  - `backend/yen_tamizh_backend/contracts/__init__.py`, `backend/tests/**`, `frontend/src/contracts/**`
  - `docs/architecture/contracts/schemas.md`, `docs/reference/documentation-structure.md`, `datasets/README.md`, `AGENTS.md`

- **Acceptance gates:** Full backend and frontend gates green with the deletions applied; no dangling doc link in `docs/`, `README.md`, `AGENTS.md`.

- **Oracle:** A repo-wide search returns zero hits for each retired identifier - `masterPath`, `masterRows`, `load_master`, `MasterWord`, `MasterWordlist`, `master-wordlist`, `master_dictionary`, `_MASTER`, `datasets/wordlists/master/`, `corpus-sources`, `CorpusSources` - outside `.git`.

- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | Structural only - no behaviour change lands with it. | Fowler (Beck, Tidy First) |
  | 2 | The Oracle enumerates RETIRED IDENTIFIERS, not the bare word. `master` is the git branch name and appears in CLAUDE.md section 8, `docs/how-to/ship-a-pr.md` and `docs/how-to/author-a-plan.md`; a bare grep can never return zero. The branch sense is out of scope. | Fowler |
  | 3 | `datasets/corpus/` is NOT deleted - only its registry moved, in row 5. The nine frequency sources still read from those paths. | Fowler |
  | 4 | EVERY import is traced before a delete. `scripts/generate_today.py` and `generate/daily.py` import from the packages this row removes; the row starts by listing every `from yen_tamizh_backend.corpus` and every `from yen_tamizh_backend.contracts.{master_wordlist,corpus_sources}` in the tree and re-points each one, then deletes. A delete that breaks an import the row never listed is the failure mode this decision exists to prevent. | Carmack, audit |
  | 5 | The `sparse-checkout` exclusion of `datasets/lexicon/` is applied to EVERY workflow that checks this repo out and does not read the lexicon - not just `daily.yml`. The row enumerates the checkouts in `.github/workflows/` and patches each; "one line" was wrong, it is one line PER CHECKOUT. | Carmack, audit |
  | 6 | `datasets/wordlists/by-length/` is retained unchanged as a reference signal - already ruled not a hard filter. | Palm (existing ruling) |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Keep the corpus layer alongside the lexicon | Two sources of truth for the word inventory, drifting on every refresh. The strangler fig must complete or it is duplication. | Fowler |
  | 2 | Bundle the retirement into row 12 | Mixes a behaviour change with a structural change in one commit. | Fowler (Beck two-hat) |

## 15. Row #14 - Rebuild the hint ladder; show a solved word's meaning

- **Scope:** Replace the fake `length` hint, ship a sequential three-rung ladder with the price disclosed before the tap, show a solved word's meaning on the summary, and answer a valid-but-wrong arrangement honestly.

- **Files touched:**
  - `backend/yen_tamizh_backend/contracts/game_wordlist.py`, `daily_generator.py`, `anagram_puzzle.py`
  - `backend/yen_tamizh_backend/generate/anagram.py`
  - `config/daily-generator.json`, `config/app-config.json`, `config/copy.json`
  - `frontend/src/games/anagram/AnagramGame.svelte`, `logic.ts`
  - `frontend/src/shell/DailySession.svelte`, `frontend/src/session/types.ts`, `frontend/src/session/SessionRunner.ts`
  - `schemas/**`, `frontend/src/contracts/**` (generated)
  - `docs/concepts/core-loop.md`, `docs/concepts/difficulty-and-scoring.md`, `docs/concepts/ui-shell.md`

- **Acceptance gates:** Full backend and frontend gates; browser smoke per CLAUDE.md section 12 including a solve-to-summary pass confirming the meaning renders and a deliberate valid-but-wrong arrangement confirming the third state.

- **Oracle:** A test asserts every baked puzzle's `hints` array has non-decreasing cost over its variable length and that no `meaning` hint occupies position 1; and every served word renders on the summary, with or without a meaning line.

- **The ladder** (sequential, not a chooser - `logic.ts` already walks it in order):

  | kind | returns | cost |
  | --- | --- | --- |
  | `length` | nothing - the tile count is already on screen | DELETED |
  | `category` | a bare Tamil tag, one word | 1 |
  | `first-ezhuthu` | one position | 2 |
  | `meaning` | a phrase - usually the whole answer | 3 |

- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | `length` is deleted. It charges cost 1 for a fact visible in the tile count; offering it as one of two hints short-changes the player. | Palm + Player |
  | 2 | NO hint chooser. The ladder is already monotonic and `logic.ts` already walks it in order, so a chooser would be three buttons reproducing one button's outcome. The real defect is that the price is shown AFTER purchase: the `-{cost}` badge in `font-mono text-warning` MOVES from the revealed pill to the button, so the next rung's price is disclosed before the tap. Net chrome added: zero. | Jony |
  | 3 | The pricing is legible in the SHAPE of what each rung returns - a tag, then a letter, then a phrase. That escalation is free and self-teaching, and it is why `category` must render as a bare one-word Tamil tag and never as the sentence "this is a bird". | Jony |
  | 4 | ENGLISH IS BANNED ON THE STAGE. The meaning rung resolves `synonymsTa` -> `definitionTa` -> the rung is OMITTED from the baked ladder entirely. There is no English fallback on a paid hint: a hint the player cannot read is a hint that stole score. A ladder that is sometimes two rungs is correct. | Jony + Player |
  | 5 | On the SUMMARY, English is acceptable as a second line only, never as the meaning line: `font-display` (not `font-tamil`), `text-base text-text-tertiary`, `lang="en"`. The typographic demotion is the statement, and `config/copy.json` already ships `-en` sibling slugs as precedent. | Jony |
  | 6 | Summary order top to bottom: check glyph + title, the existing score/solved/streak `<dl>`, THEN the word block, then home. Stats stay above because they are the glance and they hold the screenshot composition; the word block sits last because it is the dwell content and sitting above the exit button is what buys the read. Word `font-tamil text-xl font-semibold text-text-primary`; Tamil meaning `font-tamil text-base text-text-secondary`. Left-aligned in a centred container. | Jony |
  | 7 | A word with NO meaning renders as the word alone - collapsed row, no empty slot, no placeholder. An empty slot advertises a hole in the data. FAILED words still appear WITH their meanings: hiding the meaning of a word you lost punishes twice and destroys the "three words a day" claim. | Jony |
  | 8 | The third state is `text-warning` + the existing unused `anim-flip`, with NO glyph - a flip reads as reappraisal, a shake reads as rejection, and the `check` glyph stays success's exclusive mark. No new colour token, no new keyframe, no toast, no modal. It PERSISTS until the next tile placement, like the existing wrong message. | Jony |
  | 9 | The third state COSTS an attempt, and fires only on a NON-TERMINAL attempt - on the exhausting attempt the terminal out-of-attempts message wins, one message per moment. If it were free, shuffling until you hit any real word becomes a free probe for which ezhuthu group together and the attempts counter starts lying. The honesty is in the wording, not the accounting. | Jony |
  | 10 | `GameWord` gains `definitionTa`, `translationEn`, `synonymsTa` and `categories`. `AnagramPuzzle` gains exactly TWO new optional fields: `meaning` (an already-resolved display string) and `alsoValid` (a list of accepted alternative words). The arrays stay build-time - the generator resolves them into rendered text and the player downloads the text, not the inputs, the same rule as `build_item` dropping the per-item schema stamp. | Carmack + Jony |
  | 11 | `alsoValid` MUST be baked - `anagramFanOut` is a COUNT and the Game cannot detect the third state from a count, while runtime wordlist reads are forbidden, so an unbaked affordance could never fire. The partner WORDS are computed at BAKE time in `generate/daily.py`, which is the only place holding the whole `GameWordlist`: `build_day` groups `wordlist.words` by `multiset_key` once per run and passes the row's partners into `build_item` -> `build_puzzle`. `GameWord` does NOT carry the list - that would be thousands of duplicated word lists in a committed artifact. | Jony + Fowler, audit |
  | 12 | `config/app-config.json`'s `hints.perGame.anagram` moves 2 -> 3, or the ladder's third rung is never baked (`build_hints` does `spec.hints[:limit]`). | Carmack |
  | 13 | `build_hints` changes from "the first N configured hints" to "the first N hints this row can HONESTLY render" - a hint whose template names a field the row lacks is SKIPPED, not raised. Only ~1,290 words carry a category and row 12 decision 4 forbids categories from gating admission, so a raising template would `KeyError` on almost every served word. | Carmack |
  | 14 | `SessionResult` gains a per-item `solved` flag. Today it carries only counts and `puzzle.completed` carries no word, so the summary cannot tell a solved word from a lost one. The SHAPE is named so a worker does not invent one: `SessionResult.items` is an array of objects carrying `word` (string), `meaning` (optional string) and `solved` (boolean), produced by `SessionRunner`, the sole producer of `SessionResult`. The summary reads that array, NOT `SessionItem.payload`, which is typed `unknown`. | Jony, audit |
  | 15 | No new components. Hint button and pill extend in place; `feedback.tone` becomes a three-value union; the word block is added inline where the `<dl>` lives. No `SolvedWordList` extraction - there is exactly one summary in the app, and a generic component for one call site is the pre-create-for-later anti-pattern (CLAUDE.md section 10). | Jony |
  | 16 | No AI badge on any meaning, ever, and no model name or prompt version rendered. Marking some meanings makes a player distrust all of them. | Player |
  | 17 | The predecessor's baked bank (`data/puzzles/2026/*.json`) already shipped a `category` hint, and its text was `பெயர்ச்சொல்` - "noun". That is a POS label applied to most words and it narrows nothing, which is exactly the giveaway-in-reverse failure this row must avoid. The `category` rung renders a real theme tag or the rung is omitted; a POS value never reaches it, because row 11 decision 3 routes POS labels to `pos`. | Jony + Palm |
  | 18 | ON A THEMED DAY (row 15) the theme is announced FREE in the round header and the `category` rung is OMITTED from the baked ladder. Otherwise the rung is mispriced both ways: announced up front it returns a fact already on screen - the exact defect that deleted `length`; hidden until the summary, one purchase on word 1 narrows all three. There is a second leak the omission also closes - since `build_hints` skips a rung whose field is missing, a 3-rung ladder on a themed day and 2 on an ordinary one would ANNOUNCE the themed day before the player spent anything. | Palm |
  | 19 | An UNREVIEWED authored value is never SOLD. A `category` whose `categorySource` is not `reviewed`, and a `definitionTa` whose `meaningSource` is not `reviewed`, are skipped by `build_hints` rather than baked as a paid rung - they may still render free on the summary. This is a RENDERING rule, not an admission gate, and it rides decision 13's existing skip at zero new mechanism. | Palm + Fowler |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Keep `length` as a hint | The tiles are on the player's screen; charging for a countable fact reads as the game short-changing them. | Player |
  | 2 | A hint chooser showing all three rungs with prices | Three buttons to reproduce what a monotonic array already picks. A shop, not a game. | Jony |
  | 3 | English gloss as a paid hint fallback | Half-English in a Tamil-medium game, useless to a player who does not read English - which is half the reason a Tamil game exists. Omitting the rung is correct. | Jony + Player |
  | 4 | Show the meaning only as a paid hint | A wrong meaning that costs an attempt is the moment a player closes the app; free on the summary carries the same value at no risk. | Player |
  | 5 | Make the third state free | Shuffling tiles until any real word appears becomes a free probe, and the attempts counter starts lying. | Jony |
  | 6 | A "meaning unavailable" placeholder | Chrome that says nothing and advertises a hole in the data. | Jony |
  | 7 | A distinct visual treatment for the weaker `category` hint | The fix for a too-weak rung is DATA (bake a shorter ladder for that puzzle), not presentation. | Jony |

## 16. Row #15 - Themed `categories` selection

- **Scope:** Ship the category selection dimension and one themed derived set, as the Daily's variety mechanism.

- **Files touched:**
  - `backend/yen_tamizh_backend/wordsmith/derive.py`
  - `backend/yen_tamizh_backend/generate/daily.py`
  - `backend/yen_tamizh_backend/contracts/derived_wordlists.py`, `daily_generator.py`
  - `config/derived-wordlists.json`, `config/daily-generator.json`, `config/copy.json`
  - `datasets/wordlists/derived/themed-nature.json` (new)
  - `schemas/derived-wordlists.schema.json`, `frontend/src/contracts/**` (generated)
  - `docs/how-to/add-a-derived-wordlist.md`

- **Acceptance gates:** `mypy backend` strict; `pytest backend`; drift gate green.

- **Oracle:** The themed set equals EXACTLY the lexicon rows whose alias-normalized `categories` intersect the requested set and which satisfy the serving gates - no more, no fewer - and its counters reconcile against the lexicon row count.

- **Decisions:**

  | # | Decision | Authority |
  | --- | --- | --- |
  | 1 | A theme is the Daily's variety mechanism, not a Mode: three unrelated anagrams are a list, three sharing a theme are a round, and the summary can say the theme. That is a selection constraint on the existing generator and costs zero new engine. | Palm |
  | 2 | A themed Mode is NOT a Game - Word Search on Animals is still Word Search, adding no verb. It is deferred until after all four planned Games, and only then in a shape where the theme is a constraint the player must USE. `properNoun` is never a themed round: recall is not the verb, and the class exists for exclusion. | Palm |
  | 3 | THE THEMES ARE TINY, and the plan says so rather than discovering it in execution. After routing the POS labels to `pos` (row 11 decision 3), C1 leaves 463 rows across 37 themes: the largest is Emotions at 35, and Birds is 12, Colours 7, Flowers 4, Amphibians 2. A single-theme Daily at 3/day is **1 to 12 days**, not the 71 estimated before the categories were counted. | Palm, corrected by measurement |
  | 4 | A theme therefore ships as a MULTI-CATEGORY GROUP, never a single category: `themed-nature` unions Nature, Animals, Birds, Insects, Reptiles, Amphibians, Aquatic Animals, Types Of Plants, Parts Of Plants, Flowers - about 111 rows before the serving gates. The `categoryAliases` map in `config/lexicon-sources.json` is what makes a group nameable without a code change. | Palm |
  | 5 | Themed rounds stay OPPORTUNISTIC: the Daily runs a theme on the days a full themed playlist can be drawn, and an ordinary mixed day otherwise. A theme that cannot fill three slots is skipped, never padded with an off-theme word. | Palm |
  | 6 | Growing themes is a DATA change, not a code change - a new category source, or `llm_enrich` assigning categories to already-attested headwords. Neither costs a row here. | Fowler |
  | 7 | Tamil category display names are player-facing copy in `config/copy.json`, never baked into a dataset. The existing `category_ta` refusal still binds. | Fowler |
  | 8 | `pos` ships as a SELECTION dimension in THIS row, not its own, because it is the same mechanism as `categories` - a set-intersection predicate on a set-valued column - and two rows editing `DerivedSelection` would collide on the drift gate. `DerivedSelection` gains `pos`, meaning "keep rows whose `pos` INTERSECTS this set". A stricter "this POS and no other" knob waits for a Game that names it. | Fowler + Palm |
  | 9 | `pos` NEVER gates admission, identically to row 12 decision 4 for `categories`: its coverage on the served headword set is unmeasured, so gating could empty the set. A POS-selected set is OPPORTUNISTIC under decision 5. | Palm |
  | 10 | RECORDED CAUTION on a POS-selected day, with its magnitude explicitly UNMEASURED. The MECHANISM is real: Tamil verb roots skew short (`வா`, `போ` at 1 ezhuthu; `நட`, `படி`, `செய்` at 2), and the anagram needs 3-6, so a verbs-only day biases the generator toward the short end - which row 12 decision 5 identifies as the tail where rare literary words live. But the COUNT was asserted, not measured, and the user is right to challenge it: B2 alone holds 19,249 inflected verb forms, so the root inventory is in the thousands, and roots at 3-5 ezhuthu (`எழுது`, `தூங்கு`, `நடத்து`) plainly exist in quantity. The plan therefore does NOT rule a verbs day out. It requires the number before one ships: this row reports the count of `pos` containing verb, by ezhuthu length, over the SERVED set. If 3-5 ezhuthu verb headwords clear row 15 decision 12's 156-row target, a verbs day is viable and the caution is discharged. That is a measurement, and it belongs to the day a verbs day is designed. | Palm, corrected by user challenge |
  | 11 | A theme is legitimate only if it (a) excludes at least 90 percent of the servable set and (b) lets a player who knows the theme name five plausible candidates. `Birds` excludes 99.9 percent and passes; `Nouns` excludes roughly nothing and fails. Without this floor the next person with a large tag will ship a "nouns day". | Palm |
  | 12 | Growth target, so "grow the themes" is a finishable task: a theme group running one themed Daily per week without repeating inside a year needs 52 x 3 = 156 SERVED rows. `themed-nature` has about 111 before the four gates. That is the number row 10's authoring aims at. | Palm |
  | 13 | THE THEMED DAY NEEDS A MECHANISM, and it lands here or the row ships a dataset nothing reads. `build_day` fills a day from `app_config.daily.mix` keyed by `gameId`, and each `gameId` maps to exactly ONE `wordlist` path in `daily-generator.json` - so nothing would ever draw `themed-nature.json`. `GameGeneration` gains a `themes: [{wordlist, copySlug}]` sibling that `build_day` consults per date: on a date where a theme can fill every slot from its own wordlist it does, otherwise the day is ordinary. This is what row 14 decision 18's themed-day branch tests, which is why row 14 depends on THIS row. | Fowler + Carmack, audit |

- **Rejected alternatives:**

  | # | Option | Why rejected | Authority |
  | --- | --- | --- | --- |
  | 1 | Ship a themed Mode in the shell | Mixes a data row with a runtime row, and a themed Mode is a content skin rather than a Game. | Palm |
  | 2 | A `properNoun` themed round | Recall is not the verb, and the class exists for exclusion. | Palm |
  | 3 | Hand-curate the themed lists | Not reproducible, and drifts from the lexicon on every refresh. | Fowler |

## See also

- [`../docs/how-to/execute-a-plan.md`](../docs/how-to/execute-a-plan.md) - the orchestrator contract that runs this plan.
- [`../docs/how-to/author-a-plan.md`](../docs/how-to/author-a-plan.md) - the authoring procedure this doc follows.
- [`../docs/architecture/contracts/schemas.md`](../docs/architecture/contracts/schemas.md) - the living contract doc rows 1, 3, 12 and 13 update.
- [`20260725-yen-tamizh-build-roadmap-plan.md`](20260725-yen-tamizh-build-roadmap-plan.md) - the build roadmap this plan supersedes for the data layer.
