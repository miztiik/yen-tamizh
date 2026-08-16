# The lexicon pipeline

**Last Updated**: 2026-08-17

How the Tamil lexicon is built: four stages, each runnable on its own, that turn
raw third-party dictionaries and frequency tables into the all-words artifact.
What the words mean - lexicon, `wordClass`, observation versus attestation - is
defined once in [../../concepts/lexicon.md](../../concepts/lexicon.md); the
typed shapes are in [../contracts/schemas.md](../contracts/schemas.md).

This is a **build-time** pipeline. It runs on a developer laptop a handful of
times over the project's life, never in production and never on a schedule
(Holy Law #1). CI runs its type checks and its tests over committed fixtures,
and nothing else.

## Four stages, not one pass

| Stage | Command | Reads | Writes |
| --- | --- | --- | --- |
| EXTRACT | `python -m yen_tamizh_backend.wordsmith.extract [--source ID]` | one raw source plus its registry entry | `datasets/lexicon/cache/extracts/<source-id>.jsonl` |
| STAGE | `... .stage [--source ID] [--remove ID]` | the extracts | the STAGED zone of `datasets/lexicon/cache/lexicon.db` |
| ENRICH | `... .enrich [--signal NAME] [--classify]` | the STAGED zone | the DERIVED zone: signals and `wordClass` |
| PUBLISH | `... .publish` | both zones | `datasets/lexicon/by-class/**`, `lexicon.meta.json`, `README.md` |
| REVIEW | `... .review` | both zones | `datasets/lexicon/review/*.ndjson` |

The first four are the pipeline, and `python -m yen_tamizh_backend.wordsmith.pipeline`
runs them in that order. REVIEW sits beside them: it is a REPORT over the
derived zone rather than a step that produces the next stage's input, so it is
deliberately not sequenced - an operator asks for it when they want to read the
residue.

Each stage reads the previous stage's ON-DISK artifact rather than an in-process
value, and `pipeline.py` only sequences them. That is what makes a stage
independently runnable, independently debuggable, and restartable after a crash
without redoing the stage before it. A single pass over 1.1 GB of sources would
have none of those properties: one bad row in the last source would cost the
whole run, and there would be no way to re-read ONE source without re-reading
all twenty-one.

The seam is also what makes DELTA ingest possible. A source's contribution has
to be recomputable in isolation before it can be replaced or removed in
isolation, and an addressable per-source extract file is the cheapest way to
make it so.

## EXTRACT

One reader per source KIND turns raw bytes into elements; one extractor per
source SHAPE turns an element into emissions. Two kinds of emission, and the
difference between them is the whole point of the layer:

- an **observation** is `(source, surface, count)` - this source saw this
  surface, this many times. It says nothing about word-hood.
- a **fact** is `(word, attr, value, ordinal)` - this source asserted this
  typed thing. The attributes are `headword`, `translation`, `definitionEn`,
  `definitionTa`, `synonym`, `glossPeer`, `pos`, `category`, `graphemeCount`
  and `wordClassEvidence`.

Only a source whose `role` is `authority` or `authored` emits a `headword` fact.
A frequency list observing a surface a million times still cannot say it is a
word, and the registry's `role` is what enforces that at the boundary rather
than three stages later.

### `synonym` and `glossPeer` are different claims

`synonymsTa` publishes a source-ASSERTED same-language equivalence: the
Wiktionary extract's `synonyms` links, the Tamil Wiktionary's synonym sections,
an IndoWordNet SYNSET, and an authored row. Three of those four name the
relation directly and the fourth is a set of words that share one SENSE.

The English-Tamil dictionary asserts no such thing, and the difference is worth
a second attribute rather than a footnote. Its Tamil column is a translation
LIST under one English headword, so reading it sideways groups words that share
an ENGLISH GLOSS - not a meaning. Measured on the real file, `beam` files some
twenty-five unrelated Tamil terms together, and one word accumulated seventy-one
"synonyms" that way. The clique is real evidence about meaning and it is the
largest fact set in the store, so it is kept and named for what it is:
`glossPeer`.

The distinction is STRUCTURAL rather than a filter at the far end. PUBLISH
builds `synonymsTa` out of `synonym` facts, so a clique cannot reach the field
by anyone forgetting an exclusion list, and `llm_enrich` still reads the clique
as the meaning evidence it genuinely is. Renaming the published FIELD instead -
`glossTa` - was rejected: a field whose only defence is that it is not lying is
a field to delete.

### EXTRACT never filters

Not on word-hood, not on quality, not on length. The only transform is
CANONICALIZATION, which maps two spellings of one thing onto one spelling and
loses nothing. There are three, and each belongs to the reader that knows the
source:

- **NFC**, everywhere, so the ezhuthu segmenter's two spellings of one cluster
  agree.
- **MediaWiki title spelling.** MediaWiki stores a title with underscores where
  the displayed title has spaces, and `[[foo bar]]` and `[[foo_bar]]` are the
  same page. Which spelling an export ships is a property of the export: the
  Tamil Wiktionary's title list uses underscores on 187,234 of its 410,074
  titles and never a space, while the content dump of the SAME wiki uses a space
  and never an underscore. Reading them as different strings staged every
  multi-word title twice and grew the store by 187,234 surfaces carrying no
  Tamil word that was not already there. Measured over the whole title list the
  mapping is a bijection - 410,074 distinct before and after - so it merges no
  title into another.
- **A bilingual dictionary's bracketed apparatus.** The English-Tamil
  dictionary annotates its Tamil side with a part-of-speech or register stamp in
  brackets - 10,079 occurrences over 183 distinct markers - and the bracket is
  the lexicographer's apparatus rather than part of the word. Only a BALANCED
  group is removed; an unmatched bracket is a marker the source's own extraction
  truncated, and guessing where it ended would invent a word rather than recover
  one. Both counts are printed by every run.

A surface a source showed us reaches the store even when it is obviously junk,
because the lexicon's thesis is that **ingest enriches and selection filters** -
and a word wrongly excluded should cost a selection knob, not a re-ingest over
hundreds of megabytes of gitignored bytes.

The one thing EXTRACT does refuse is a record it cannot parse at all - a line
with no column where the word should be, an element whose word field is not a
string. Those are COUNTED, never dropped silently:

```
rowsOut + parseRejects == rowsIn
```

is the stage's ledger, enforced before the extract file is renamed into place. A
row that loses only part of itself is a different event and gets its own
counters: `posUnparsed` for a row whose part-of-speech marker could not be read,
`posRejected` for a tag the registry routes to an explicit rejection reason.
Discarding a row's translations because its prefix was punctuation would be
filtering, and this stage does not filter.

### Everything streams

Peak memory must not track file size - the largest registered source is 647 MB
and the whole set is about 1.1 GB - so every reader is a generator over a
bounded buffer. No reader calls `json.load`, `read()` or `readlines()` on a
source file. Delimited sources are read a line at a time, JSONL a line at a
time, a JSON array one element at a time through the standard library's own
incremental entry point, `JSONDecoder.raw_decode`, over a sliding buffer, and a
MediaWiki export one page at a time through expat's handler interface.

A QUOTED delimited file is read a RECORD at a time through the standard
library's `csv` module, which is a separate reader kind rather than a flag,
because the two disagree on real bytes. In an RFC-4180 file a quoted field may
hold the delimiter, a doubled quote, or a newline, so a logical record is not a
physical line: three of IndoWordNet's 16,640 records span two lines each, and a
line-splitting reader turns those two records into four malformed rows. Making
it a flag on the existing kind would also silently re-read the twelve delimited
sources already staged.

The MediaWiki reader is the one place where a tree builder was refused rather
than simply not used. `ElementTree` materializes every page it is handed, and an
export's largest pages are not its articles: in the Tamil Wiktionary dump the
three biggest of the first two thousand are a template listing and a
village-pump archive, at 226 KB, 346 KB and 1,035 KB against a largest ARTICLE
of 23 KB. `<ns>` arrives before `<revision>`, so a handler-driven parse can
decline to accumulate the text of a page that is not a record at all - which is
what makes peak memory proportional to the largest RECORD rather than to the
largest page, and is worth a factor of forty-five here.

The buffer size is a PARAMETER, default 64 KiB, not a constant. That is what
lets the test suite drive a one-byte buffer through the readers and prove the
yielded sequence never changes - a split falls inside every single element at
that size, which is the case a whole-document parse can never fail on.

Nothing accumulates across a file except one bounded run: the English-Tamil
dictionary's synonym grouping, described below.

### The skip check reads its own header

An extract is a pure function of the source bytes, the registry entry and the
extractor version, so re-running over unchanged bytes should do nothing. The
check compares the source's on-disk sha256 against the one recorded in the
FIRST LINE of that source's OWN extract file.

It deliberately does not consult the published lexicon. That artifact is stage
four's output, it does not exist while stage one runs, and making stage one read
stage four's output is a cycle. The extract is written to a `.partial` file and
renamed only after the ledger reconciles, so a crashed run can never leave a
truncated file that the header check would then accept as current.

## STAGE

STAGE accumulates every extract into one store so that a source's contribution
can be REPLACED or REMOVED without touching another source's rows. The property
it exists to have is a single equation:

```
delta == full
```

The staged rows built by applying twenty-one extracts one at a time, in any order,
with any source removed and re-applied along the way, are exactly the rows a
full rebuild holds. Everything else in this stage is in service of that.

### The store has two zones

| Zone | Written by | Tables |
| --- | --- | --- |
| STAGED | STAGE | `source(id, sha256, bytes, role, precedence, kind)`, `observation(source_id, surface, count)`, `fact(source_id, word, attr, value, ordinal)` |
| DERIVED | ENRICH | `signal(word, attested, orthotactic, breadth, nannulValid, knownVerbForm, ngram, neighbour, zipf)`, `classification(word, wordClass)` |

Beside them sit two version stamps, `stage_epoch(n)` and `derived_epoch(n)`.

**Without the split the `delta == full` equation is simply false.** Four of the
eight word-hood signals are whole-corpus functions - an n-gram model trained on
every attested headword, a nearest-neighbour search over every surface, a
frequency residual, a breadth count. A delta-built store would carry signals
computed over a PRE-delta fact set while a full rebuild carried signals computed
over the complete one, and no amount of care in the merge would reconcile them.
So the derived zone is not merged at all: it is a pure function of the staged
zone, dropped and recomputed whole on every ENRICH run. Chasing incremental
signal update would be chasing the wrong goal - recomputing is cheap, and it is
provable.

The derived zone carries no `source_id`, because no signal IS per-source. A
fake one would make `DELETE WHERE source_id = ?` silently wrong.

### What makes the staged zone commutative

Three rules, none of them optional:

1. **Nothing is resolved at merge time.** Every fact keeps the `source_id` that
   asserted it, and two sources contradicting each other keep two rows.
   Resolution happens at PUBLISH, where precedence is known. A merge that
   picked a winner would depend on which source arrived first, which is exactly
   what the equation forbids.
2. **`observation` conflicts SUM.** A source naming one surface on two lines has
   observed it twice, and addition does not care which line came first.
   `REPLACE` would make merge order decide a count. Measured over the real
   sources: 8,225,706 observations collapse to 8,089,239 rows, so 136,467 of
   them meet this rule rather than merely passing by it.
3. **Replace and remove are one transaction each.** Delete the source's rows,
   insert the new ones, stamp the epoch - `BEGIN IMMEDIATE ... COMMIT`. A crash
   leaves the store holding either the old contribution or the new one, never
   half of each, and a corrupt extract found half-way through an apply rolls the
   whole apply back.

### The epoch guard

`stage_epoch` counts STAGE's writes. ENRICH stamps `derived_epoch` with the
staged version it computed over, and **PUBLISH refuses to run when the two
disagree** - that is the whole guard, and it is what stops a published artifact
carrying signals from a store that has moved on underneath them.

The stamp is a COUNTER rather than a digest of the staged content, and the
asymmetry is the reason. A counter can only ever claim the derived zone is stale
when it is not, which costs one recompute. A digest can claim the derived zone
is CURRENT when it is not - the extractor version is not part of the staged
content, so re-extracting with a changed extractor and re-staging would leave
any content digest unmoved - and that ships wrong data.

Being a counter makes the epoch PATH-DEPENDENT by design: a store that was
rebuilt, then had one source removed and re-applied, has written twice more than
one that was only rebuilt. That is the stamp working. It is also why the
canonical dump below covers every DATA table and neither version stamp: a
path-independence Oracle over a deliberately path-dependent counter would be
asserting that the guard is broken.

### The canonical dump

The instrument the equation is proved with. It reads every data table in both
zones - discovered from `sqlite_schema` rather than from a list, so a table a
later row adds is covered without anyone remembering - projects every column,
and orders by all of them. `rowid` is never selected and never ordered on,
because insertion order differs between a full build and a delta build BY
CONSTRUCTION; an implicit-order dump would compare the build path rather than
the result.

### Everything still streams

Rows reach `executemany` as a GENERATOR over the extract file, never a
materialized list. The largest extract is 445 MB and 2.7M facts, and reading it
into memory to insert it would trade away at stage two exactly the property
stage one was built to have. The file is read TWICE - once for observations,
once for facts - because two streaming passes cost seconds and one buffered pass
costs 445 MB.

The bulk-load pragmas are NAMED rather than defaulted: `journal_mode=WAL`,
`synchronous=OFF`, `cache_size=-262144`, `temp_store=MEMORY`,
`mmap_size=268435456`. Without them an 8.2M-row load runs at one to three
thousand rows a second - 45 minutes to over two hours. With them, and with every
secondary index created AFTER the load rather than maintained during it, the
measured real load is 278 seconds.

`synchronous=OFF` is legitimate here and only here: the store is gitignored and
rebuildable by one command, and the reproducibility anchor is the published
artifact, never this file.

## ENRICH

ENRICH reads the STAGED zone and writes the DERIVED one: one `signal` row per
staged surface, one column per word-hood signal. WHAT the signals are and what
each catches is [word-hood.md](word-hood.md); this section is the stage
mechanics.

### The zone is recomputed WHOLE, never merged

Four of the eight signals are whole-corpus functions, so a derived zone merged
from deltas would carry values computed over a pre-delta fact set. It is
therefore not merged at all: `signal` and `classification` are emptied and
rebuilt on every full run. A row left behind from an earlier population cannot
survive, which is what makes the zone a pure FUNCTION of the staged one rather
than a history of it.

### One pass over the population

The population is the union of every observed surface and every worded fact -
6,249,903 rows over the real sources. Each signal contributes a SQL EXPRESSION
to a single streamed `INSERT ... SELECT` rather than running its own update pass
over the whole table, and each prepares a small keyed temp table first so the
expression is a primary-key probe rather than a correlated scan. The signals
that cannot be written in SQL at all - `orthotactic` and `ngram` - run in the
same statement as deterministic user-defined functions.

Nothing materialises the population in Python.

### One signal runs after that pass, and it has to

`neighbour` is the exception, and the reason is structural rather than a matter
of cost: its query set is decided by `attested`, `knownVerbForm` and `breadth`,
which the population pass is still computing. It therefore declares no
expression, its column starts NULL, and it is filled afterwards - inside the
SAME transaction, so the derived zone is still one all-or-nothing rebuild. An
interrupted run leaves `signal` empty and `derived_epoch` behind `stage_epoch`,
which is the state PUBLISH already refuses.

The pass reads the `signal` table in primary-key PAGES rather than over one long
cursor, because it writes to the table it is reading and SQLite leaves the
behaviour of a cursor whose table is changing under it undefined. Paging also
caps what the pass holds at one page, whatever the query set's size.

It is the one stage that scores across processes. The deletion index is placed
in `multiprocessing.shared_memory` so there is one physical copy however many
workers there are, and results come back in the order the chunks went out - so
the column cannot depend on which worker finished first.

### `--signal NAME` recomputes one column

The development path: it updates one column over the population the zone already
holds, and refuses when there is no population to update. It deliberately does
NOT touch `derived_epoch` - the column is a pure function of the staged zone, so
recomputing it cannot make a current zone stale, and it cannot make a stale one
current either. The stamp is right wherever it already stood.

### The epoch is stamped at the end of a full run

`derived_epoch` takes the `stage_epoch` the run read. PUBLISH refuses when the
two disagree, so a published artifact can never carry signals from a store that
has moved on underneath them.

### A NULL is a fact, not a gap

All eight columns are written now, but two of them are deliberately not written
everywhere, and NULL is the answer rather than a hole: `zipf` is NULL for a
surface nobody counted, because a word with no frequency has no rank to sit off,
and `neighbour` is NULL for a surface its prune skipped, because nobody asked.
A measured zero says something different in both cases -
[word-hood.md](word-hood.md) says what.

### The classifier is the last step of the rebuild

Once the eight columns are written, one more streamed statement over the
`signal` table turns them into exactly one `wordClass` per surface. It runs
INSIDE the same transaction, so the derived zone stays a single all-or-nothing
rebuild and a store can never hold signals with no verdicts - a missing verdict
would read to Row 12's allow-list as "not served" rather than as the failure it
is.

It reads two things the signal columns do not carry, both from the staged zone
and both prepared as small keyed temp tables first: whether an authority gave
the surface a lexicographic ENTRY rather than a bare listing, and every
`wordClassEvidence` fact any source asserted about it. The cascade itself is a
pure function of a plain value, registered as a deterministic SQLite function -
so the same code classifies 6.25M surfaces here and 200 committed fixture rows
in CI.

`--classify` recomputes only the verdicts over the population the zone already
holds. It is the development path for the cascade and behaves exactly like
`--signal`: it refuses when there is no population, and it does not touch
`derived_epoch`.

### Configured source ids are checked before anything is computed

Two signals are membership in a NAMED source, and the name is config. A
misspelled id would produce a column of zeros - which reads exactly like a
signal that honestly found nothing - so ENRICH checks every configured id
against the store's `source` table and refuses to run rather than reporting a
silent all-negative. Fail fast at the boundary.

## REVIEW

ENRICH's verdicts live in a two-gigabyte gitignored SQLite file. That is the
right home for them and a useless one for a person: nobody opens a store to find
out why a word was refused, or how much work an enrichment pass still has in
front of it. REVIEW writes that state out under `datasets/lexicon/review/`, one
JSON object per line so a shell, an editor and a diff all read it. The files are
gitignored; a committed README in that directory says what each one is.

They are deliberately NOT under `datasets/lexicon/cache/`. That directory is
machine state one stage hands to the next, and a reader who finds a work queue
in it reasonably concludes the file is uninteresting and safe to delete. These
are WORKING MATERIAL: the residue a classifier could not place and the queue an
authoring pass works through. Same gitignore, different meaning, so a different
home.

| File | Answers | Carries |
| --- | --- | --- |
| `unclassified.ndjson` | which surfaces reached no verdict | all eight signals, so the residue can be sorted rather than counted |
| `not-a-word.ndjson` | which surfaces were refused, and by WHICH clause | `nonTamil`, `tooLong`, `repeatedEzhuthu`, `empty`, or `sourceDenied` |
| `enrichment-queue.ndjson` | which unclassified surfaces a tier-1 source already describes | the meanings, synonyms and translations it would work FROM |
| `headwords-without-a-meaning.ndjson` | which SERVABLE surfaces carry no Tamil definition | the translation, synonym, part of speech or gloss peers an authoring pass would work FROM |

**The enrichment queue is EMPTY over a current derived zone, and that is the
result rather than a broken query.** A tier-1 source that describes a surface
also attests it; an attested surface has an ENTRY; and an entry always reaches a
verdict, because the headword gate either admits it or one of the phase-3 arms
names why not. So the intersection is empty by construction. A row in that file
means one of two things, and both are worth knowing: a source described
something it did not list, or the derived zone is STALE. The 13,500-row version
of this set that Row 4b reported was the second case - it was measured after the
Tamil Wiktionary content was staged and before ENRICH had run again.

The queue that is actually left is the fourth file. Those surfaces passed the
word-hood gate and would still fail a meaning gate, so they are words the game
can select and cannot explain - which is the size of the authoring work, and a
different question from what the classifier could not place.

REVIEW writes nothing back. It is a REPORT over the derived zone, so re-running
it over an unchanged store rewrites the same bytes and a review dump can never
change a verdict. The refusal reason is computed by the CLASSIFIER's own
function rather than re-derived here, so a reviewed reason cannot disagree with
a published verdict.

## PUBLISH

The last stage reads both zones, resolves every published word's facts into one
row, and streams the result to `datasets/lexicon/`. Three artifacts land:
`by-class/<wordClass>/<hex>.ndjson` (the rows), `lexicon.meta.json` (the index),
and a generated `README.md` (the human ready-reckoner). None of them is ever
hand-edited.

### Retention is not publication

The store keeps every surface any source ever showed us and every fact anybody
asserted about them. The REPOSITORY commits the classes a player can actually be
served: `headword`, `properNoun`, `boundStem` and `colloquial`. Git history is
append-only, so a byte committed once is carried forever, which makes what to
publish a decision rather than a default.

What keeps the thesis honest is `counters.classified` - a per-class census of
the WHOLE population, committed beside the files. So a withheld class is on the
record in the repository at its real size, and "nothing was discarded, only
unpublished" is a statement a reader can check rather than one they have to take
on trust. `counters.published` counts what the files carry, and publication is
ALL-OR-NOTHING per class: a published count that is neither zero nor the
classified count means rows went missing between the classifier and the writer,
which is the one failure a per-class policy would otherwise hide.

`publishedClasses` is a knob in `config/lexicon-sources.json`, because which
classes are servable is a policy that can change without any code changing.

### The address is a pure function of the word

`partitionKeys` is `["wordClass", "baseEzhuthu"]`, declared IN the meta
document so a consumer learns the address from the artifact rather than from the
code that wrote it. Both keys are immutable per word:

- `wordClass` is the classifier's verdict, so only a re-classification moves a
  row between files - which is a reviewable semantic event, two line changes;
- the base ezhuthu is the letter the word's opening cluster is built on, and a
  word does not change what letter it starts with.

So a refresh INSERTS a line into a file that already exists. Nothing in PUBLISH
reads a previous artifact to decide where a row goes, which is what makes "a
clean checkout produces the same layout as a refresh" true.

### The file name is hex, and the hex is the BASE letter

A file is named for the code point of the letter its words OPEN on, as lowercase
4-digit hex: `0b85.ndjson` is `அ`, `0b95.ndjson` is `க`. A vowel sign or a pulli
is a combining mark riding on that letter, so `க`, `கா` and `கி` share one file -
exactly as a dictionary files them under one heading, and exactly as a reader
looking a word up expects.

Addressing the WHOLE opening ezhuthu instead was tried and withdrawn. It split
one letter across as many as thirteen files, put the `headword` class at 115 of
them, and served nobody: no consumer wants `ka` without `kaa`, and a word is not
filed under a different heading because its first vowel changed. The base letter
collapses those 115 to 22 and the artifact as a whole from 238 files to 53.

The padding is the point. A base character is ONE code point by construction, so
the key is a fixed four digits, and a fixed width makes ASCII filename order
equal code-point order - a directory listing is in the same order as the rows
inside the files, and a file's neighbours in `ls` are its neighbours in the sort.
One thing has to hold for that and PUBLISH ASSERTS it rather than assuming it:
every code point is in the **Basic Multilingual Plane**, because a five-digit
group would break the padding. Tamil satisfies it everywhere, which is exactly
why it is an assertion - an invariant nothing checks is a comment.

The NFC assertion the full-ezhuthu address needed is GONE, and its absence is
the measure of the simplification. A decomposed letter carries the same base
code point as a composed one, so the two now address the same file and there is
nothing left to refuse.

Hex rather than Tamil script or a romanization, and the rule underneath is **put
the IMMUTABLE identifier in the path and the CORRECTABLE label in data.** A code
point is fixed by an external standard; a romanization is a judgement call, and
correcting a judgement call must never rename a published file. Tamil script in
a path is also less legible than hex on the operator's own machine, because
git's default `core.quotepath` renders non-ASCII paths as octal escapes.

`ezhuthuIndex` on the meta document is where the letter is spelled out: each hex
key decodes ONCE to `{ezhuthu, roman, kind}`. `roman` is the base character's
ASCII label, so `0b95` is `ka` and `0b85` is `a`.

`maxPartitionBytes` (33 MiB, a third of GitHub's 100 MiB hard blob wall) is a
HARD BUILD ASSERTION, not a partition threshold. The layout is decided by the
address; this is what says out loud, naming the file and its byte count, that one
class has outgrown what one file should carry - and then the layout needs a
decision rather than a larger number.

### Row order, and what a refresh diff looks like

Rows sort by `word` ASC within a file. Because the base letter is that sort's own
leading key, the partition cut is a RANGE cut on an order that already exists:
concatenating a class's files in name order reproduces the sorted class exactly.

The stream is ordered by `(wordClass, base ezhuthu, word)` using the SAME
function that names the file, so each address arrives as one contiguous run and
the writer holds ONE open handle at a time. Ordering by `word` alone would very
nearly do it and would be wrong in a case nobody would notice for years: a
one-letter word sorts before every longer word starting with the same letter, and
a rare combining mark sorts between them.

On a refresh: a new word inserts one line, a changed frequency or meaning
rewrites one line in place, and only a changed `wordClass` moves a row between
files. That is the diff a reviewer wants - the words that actually changed.

### The resolution rules

STAGE resolves nothing: every fact keeps the `source_id` that asserted it, which
is what makes the staged zone commutative. PUBLISH is where contradictions are
settled, once, with the registry's precedence in hand.

| Column | Rule |
| --- | --- |
| `frequency` | SUM over the `frequency`-role corpora - a count is evidence that adds up, not a claim that competes |
| `spokenRatio` | the declared `spokenSources` share of that sum, to six places |
| `attestations` | how many sources allowed to assert word-hood carried a `headword` fact, counted DISTINCT on the source |
| `tier1Attestations` | of those, how many are `attestationTier: lexicographic` |
| `pos` | UNION, translated through `posAliases`, deduped and sorted |
| `synonymsTa` | UNION of ASSERTED synonymy only, excluding the word itself |
| `categories` | UNION, normalized through `categoryAliases` so `Birds` and `birds` collapse |
| `translationEn` | the winner of ONE display slot, by precedence, attested ahead of authored |
| `definitionTa` | an ORDERED UNION of every sense, in that same precedence order |

UNION for a set-valued fact with no display slot; PRECEDENCE for a fact that
occupies one. A Tamil verbal noun genuinely is both a noun and a verb, so
resolving `pos` by precedence would delete whichever a lower-ranked source held.
A translation can only be shown once, so exactly one source has to win it.

### A word has more than one meaning, and the row now says so

`definitionTa` is the third shape, and it exists because the second one was
losing data. A Tamil Wiktionary page lists every sense of its word under one
meaning block: `வாகை` carries three - the Albizia lebbeck tree, the garland a
victor wears, and victory itself. Resolving that as a single display slot
published the tree and threw the other two away, on a row whose own
`translationEn` was "crown" and whose `synonymsTa` already held `வெற்றி` - so
the Tamil and the English halves of one row described different senses.

Measured over the Tamil Wiktionary extract: 234,853 pages assert a sense,
350,398 senses in all, and **58,193 of those pages (24.8 percent) carry more than
one**. The single slot was discarding **115,545 senses**, and the widest pages
run to the extractor's own per-page bound of 24.

So the column is a LIST, ordered by exactly the rule that used to pick the
winner - attested ahead of authored, then precedence, then the source's own
sense order - and deduplicated on the text. Two consequences are worth stating:

- **element zero is what the single-slot rule published**, so the one meaning a
  hint spends is unchanged and no consumer has to be taught a new preference;
- **nothing is discarded**, so a later row that wants sense two can have it
  without a re-publish over 6.5 million surfaces.

It is the only list the row does NOT sort. Order is information here, and
sorting would put whichever sense happens to begin with the earliest code point
in front of a player. The contract enforces distinctness instead.

A sense also stops at the last Tamil it carries. The wiki closes a meaning line
with its own cross-reference apparatus - `வாகை`'s first sense ended `... (Albizia
lebbeck) ; siris`, where `siris` is a link to the English common name - delimited
from the sense by the same semicolon that separates two Tamil clauses, so the
cleaner could not see it as apparatus. A trailing fragment carrying no Tamil at
all is dropped; a binomial inside the sense's own clause stays, because a reader
looking up a tree wants it.

`synonymsTa` is the ASSERTED synonymy only. A2's sideways read - the words that
share an English gloss - is staged as `glossPeer` rather than `synonym` (Row 9b)
and never reaches the artifact: sharing a gloss is not meaning the same thing,
and the clique would have added 47 MiB of it.

`definitionEn` is never published. It is the one column the inventory carries
only as English prose, and the lexicon serves Tamil.

A raw POS tag with no `posAliases` entry is a HARD PUBLISH FAILURE naming the tag
and its row count - never dropped, because a silent boundary drop is the defect
this pipeline exists to remove, and never passed through, because that would
defeat the closed vocabulary.

### An attested meaning outranks an authored one

Row 4 decision 2a: a Tamil definition publishes VERBATIM from an attesting
source, and `llm_enrich` fills only what no source attests. The resolver puts
`role: authored` LAST in the single-slot ordering, ahead of precedence.

Stated as a RULE rather than as a precedence number on purpose. `llm-authored`
was registered at precedence 19 when 19 was last; two later rows appended
sources at 21 and 22, and those two are the biggest Tamil-definition sources in
the inventory. A precedence-only resolver would therefore have published an
authored gloss over a dictionary's - silently, as a side effect of appending a
row to a config file. The rule cannot be broken that way.

### The row carries facts and counts, and nothing else

`word`, `definitionTa`, `translationEn`, `synonymsTa`, `pos`, `categories`,
`frequency`, `length`, `wordClass`, `attestations`, `tier1Attestations`,
`spokenRatio` - in that order, which is the order they serialize in. Every
sparse column is OMITTED when absent - never an empty list, never a null -
because `model_dump(exclude_none=True)` drops `None` but keeps `[]`, so a
defaulted empty list would write an empty pair on every row lacking the fact.

**The order is the contract's field order, not a sort.** A row opens on the word
and what it MEANS and closes on the machine columns a selection gate answers
from; `attestations` and `tier1Attestations` are last because Row 12's serving
gate is their only consumer and it runs against the published artifact, so they
have to be there and nobody reads them by eye. Sorting the keys was just as
deterministic and opened every row on `attestations` with `word` buried eight
fields in. Pydantic returns fields in declaration order, so the contract IS the
order and a test pins the list.

What is NOT there, and why:

- **`attestedBy`** - a list of source slugs on every row, where what selection
  gates on is the COUNT. Two integers carry the gate; the names stay in the
  store, where a question about ONE word can be asked of it. Two integers rather
  than an integer and a flag because a boolean costs the same bytes on the line
  and says strictly less.
- **`ezhuthu`** - it is `segment(word)`, a pure function of a column that IS
  published. Measured at 66.5 B a row, but bytes are the smaller argument: a
  stored copy of a derived value is a DRIFT SURFACE, and the cheapest way not to
  have that disagreement is not to store it. `length` stays because selection
  reads it, and it is checked against the LIVE segmentation on every row - the
  same guarantee at a fortieth of the bytes.
- **`wordhood` and `freqRank`** - derived diagnostics of this pipeline rather
  than facts a source asserted. `wordClass` IS `wordhood`'s verdict and
  `freqRank` is a sort of the published `frequency`, so neither can cost the
  project a fact.
- **`meaningSource`, `translationEnSource`, `categorySource`, `compound`** - no
  reader. Provenance that describes a value nobody traces from the artifact is a
  column every row pays for and nothing spends.

### Everything streams, and the newline is named

One `json.dumps(row, ensure_ascii=False)` per line in the contract's own field
order, written straight from a `sqlite3` cursor to a temp handle, then
`os.replace`. Peak Python memory is one row whatever the population is.

The handle is opened with `newline="\n"` and `encoding="utf-8"` EXPLICITLY. The
operator runs Windows, where Python's default text mode translates `\n` to
`\r\n` - which would break the byte-identity Oracle on the very machine that
performs the real publish. `.gitattributes` pins the same thing from git's side,
so `core.autocrlf` cannot undo it on the next contributor's checkout.

Each file's sha256 is computed by reading the file BACK, so the digest is a
statement about the bytes on disk rather than about what the process meant to
write.

### The index is the only way in

A consumer resolves a file through `partitions[]` in `lexicon.meta.json`: no
globbing, no probe-and-fallback. Each entry carries `path`, `wordClass`,
`baseEzhuthu`, `rows`, `bytes` and `sha256`, and the model checks that the
declared population reconciles with `counters.published` class by class.

A file the previous publish wrote and this one no longer addresses is DELETED,
and an emptied class directory goes with it. Without that the directory and the
index disagree, and a reader that trusts the index alone would never notice.

`README.md` is generated from the same document, so the two cannot drift. It
carries no date: the artifact has no `generatedAt` for the reason a rebuild has
to byte-compare, and a wall clock in a generated file would defeat that on the
first re-run. Git records when.

### The full rebuild is operator-only

CI runs `mypy`, the tests, and the fixture-pipeline integration gate - which
drives all four stages over the committed byte-exact fixture slices and
byte-compares the result against `datasets/fixtures/lexicon-expected/`. Nothing
else. The raw sources are gitignored so CI has nothing to rebuild from, and a
nightly rebuild would shift frequency sums and therefore the candidate list every
night, making the no-rewrite rule on already-published puzzle days unenforceable
in principle.

## Design rationale

### The self-terminating element rule

This is the rule the `lexicon-sources` contract's `elementKind` exists to
express, and it is defined here rather than restated anywhere else.

Streaming a JSON array means handing a partial buffer to `raw_decode` and
deciding what a failure MEANS. There are only two possible readings - "the
element is truncated, read more" and "the element is malformed, fail" - and
picking the wrong one silently corrupts data. The property that makes the first
reading safe is:

> An element grammar is admissible if and only if it is **self-terminating**: a
> proper prefix of a complete element is never itself a complete element.

An object has it. `{"a": 1` cannot decode, so a decode failure over a buffer
that starts with `{` always means "read more".

A string has it in full. `"abc` raises `Unterminated string`, and so does
`"abc\` - there is no prefix of a complete JSON string that is itself a
complete JSON string, because the closing quote is what ends it.

A NUMBER does not have it, and that is the hazard the rule was written for.
`12345` split across a buffer boundary decodes as `123` - a complete, valid,
WRONG value, with no error anywhere. So the admitted openers are exactly `{`
and `"`, and any other leading non-whitespace character raises at once naming
the array it appeared in.

`true`, `false` and `null` are refused on the same line even though a truncated
one does raise, because none of them can be a word. Admitting them would only
postpone the failure to a stage that knows less about where it came from.

The corpus layer this supersedes stated the rule as "elements must be objects",
which is the CONSEQUENCE rather than the property. That mis-statement would have
rejected the two acquired sources that hold bare string elements, one of which
is the whole orthotactic signal. Stating the property instead widens the
contract without weakening it.

### `rootKey` is optional, and its absence is a claim

A json-array source names the key its array hangs under. One acquired source has
no key at all: the English-Tamil dictionary is 56,856 elements inside a bare
top-level `[`. So an ABSENT `rootKey` means "the document root is the array",
and the reader verifies that against the bytes - a document that opens with `{`
when no `rootKey` was declared raises immediately. The absence is an assertion
the reader checks, not a fallback it guesses.

### Synonyms are grouped over a run, not over the file

The English-Tamil dictionary is read twice from one row. Read FORWARD, each
Tamil term translates to the row's English headword. Read SIDEWAYS, the terms
filed under one English headword ARE equivalents of each other - a synonym set,
`orupporut panmozhi`.

The grouping key is (English headword, part of speech), never the headword
alone. Without the part of speech a noun sense and a verb sense of the same
English word collapse into a single set, and the lexicon would publish a verb as
a synonym of a noun.

The grouping is a RUN over the source's own sort order rather than a whole-file
index, because a whole-file group-by would cost peak memory proportional to the
source and break the streaming rule for the sake of one source. Measured over
all 56,856 rows: 54,928 distinct English headwords across 54,934 runs, so six
headwords recur non-adjacently and produce two smaller sets instead of one
merged one. Those six are recoverable at PUBLISH from the `translation` and
`pos` facts both halves already carry.

### The extract cache has no schema, and that is not an oversight

`datasets/lexicon/cache/` is gitignored build state, rebuildable from the
sources by one command. Holy Law #3 governs PERSISTED contracts - the save
format, level and puzzle data, config, the asset manifest - and the ruling that
a committed artifact carries its own provenance rather than a sibling ledger
does not reach a build cache either. What IS schema-backed is the registry the
stage reads, `config/lexicon-sources.json`, and the artifact stage four
publishes.

### A raw tag with no alias entry fails HERE

The registry's `posAliases` map must name every raw part-of-speech tag any
reader can produce. A tag with no entry raises at extract, naming the tag and
the source, rather than reaching a hard failure at publish. Failing fast at the
boundary means the stage that read the bytes, not the stage three steps later
that has lost the context; and the fix is one line of config either way. The
same holds for a category label in neither alias map.

### SQLite is the STAGING substrate, and it is never an output

The staging store needs exactly two operations - upsert a source's rows, and
delete a source's rows - over roughly 11.5 million rows, on a laptop, with no
new dependency. `INSERT ... ON CONFLICT DO UPDATE` and
`DELETE WHERE source_id = ?` are that, and they are in the standard library.
Holy Law #8 asks what a dependency buys; here the answer is nothing, because
the mature open-source option is already installed.

**The store is never an artifact.** A SQLite file is not byte-deterministic -
page layout and free-list state depend on the order rows arrived and on what was
deleted along the way - so it can never be the reproducibility anchor. The
anchor is the published lexicon. Which is also why the `delta == full` Oracle
compares a CANONICAL DUMP rather than file bytes: the equation is about rows,
and rows are the only thing about a database file that is well defined.

Committing it was rejected on the same ground the NDJSON artifact was chosen on:
a binary blob cannot be reviewed in a diff, and every rebuild would add its
whole weight to git history.

### The signal table is WIDE, while the published shape is a map

`wordhood` is published as a name-keyed map so that signals can land in separate
rows of work without either one shipping a half-populated object. The STORE is
the opposite shape - one row per surface, one COLUMN per signal - and the two
are not in tension, because they are optimising different things.

At the measured 6,249,903 surfaces the entity-attribute-value shape is 50 million
rows against 6.25 million, and it turns every whole-corpus aggregation - which is
what four of the eight signals ARE - into a `GROUP BY` over 50 million rows. The
independence the map buys is bought instead by `ALTER TABLE ADD COLUMN`, which is
O(1) metadata in SQLite and free in any case, because the derived zone is dropped
and recomputed whole.

## Rejected alternatives

| Option | Why rejected |
| --- | --- |
| A separate NORMALIZE pass between EXTRACT and STAGE | Normalization is per-source and belongs in the reader that already knows the source's quirks - which leading marker is a part of speech, which comma separates terms. A shared pass needs a per-source switch, which is the same code in a worse place. |
| Extract straight into the store with no intermediate file | Delta ingest requires one source's contribution to be recomputable in isolation, and reading raw bytes inside the staging step breaks stage independence. |
| A defaulted `elementKind` | A default is exactly the silent assumption the self-terminating rule exists to prevent: whichever value were chosen, the first source of the other kind would fail in the confusing way rather than the loud way. |
| An absolute megabyte ceiling as the memory proof | It cannot fail over a fixture, and a fixture is all CI has. The scaling predicate compares a 10x fixture's peak against its 1x sibling's, which a `json.load` reader fails by a factor of ten. |
| `resource.getrusage` for the memory measurement | POSIX-only. It raises on the Windows machine that performs the real run, so the gate would be untestable exactly where the run happens. `tracemalloc` is stdlib and cross-platform. |
| Reading the published lexicon to decide whether to skip a source | Stage one would depend on stage four's output, which does not exist the first time the pipeline runs. The extract's own header line carries the digest instead. |
| Emitting a source-level constant part of speech for the inflected-verb lists | The registry can name a FIELD that holds a tag; it cannot name a tag the whole file implies, and inventing one in code would put a semantic knob outside `config/`. The lists emit observations, and their `role` is what the classifier reads. |
| Committed JSONL as the staging substrate | A one-row delta rewrites a 200 MB file, git history grows by the whole file on every refresh, and there is no upsert primitive at all. |
| Parquet as the staging substrate | A new heavy dependency with no build-time beneficiary, not git-diffable, and still no upsert. Holy Law #8 unanswered. |
| DuckDB as the staging substrate | It buys OLAP scan speed. The required operations are OLTP upsert and delete-by-source, which SQLite does with zero new dependency. |
| Plain Python dicts and no store at all | Every delta becomes a full re-merge of every extract - the destructive funnel with extra steps. Not restartable, not inspectable, and it breaks stage independence. |
| One zone, with signals namespaced by `source_id` | No signal IS per-source; four are whole-corpus aggregates. A fake `source_id` on a signal row would make `DELETE WHERE source_id = ?` silently wrong. |
| A content digest instead of a write counter for `stage_epoch` | It can report the derived zone CURRENT when it is not: the extractor version is not part of the staged content, so a re-extraction that changes every fact can leave any digest over those facts' source rows unmoved. A counter's only failure mode is one unnecessary recompute. |
| Publishing every class at full fidelity | Roughly 900 MB of committed NDJSON, of which the six unpublished classes are the bulk, and git history is append-only so it would be carried forever. Retention is what the store is for; `counters.classified` is what keeps the withheld classes provable in the repository. |
| One file per class | `headword` alone would be a single large file, so "what changed in headwords?" spans one enormous blob and any growth walks toward the 100 MiB wall with no address to split on. The opening letter is free: it is already the sort's leading key. |
| A `length` component in the address | It makes a word's ADDRESS depend on the SIZE OF ITS CLASS the moment it is applied conditionally, and unconditionally it multiplies the file count for a key no consumer resolves on. `wordClass` plus the opening letter is the whole address. |
| The WHOLE first ezhuthu rather than its base letter (Row 11, withdrawn in Row 12a) | It was chosen to avoid "merging" `க` with `கா`, but that merge is what a dictionary does and what a reader wants: no consumer asks for `ka` without `kaa`. Measured, it split one letter across up to thirteen files - 115 for the `headword` class, 238 in the artifact - against 22 and 53 for the base letter, and it cost an NFC assertion that the base letter does not need. |
| Romanized or Tamil-script file names | A romanization is a judgement call and correcting one would RENAME published files; it is also case-significant in every ASCII scheme (`N`/`n`, `L`/`l`), which collides on NTFS and APFS. Tamil script in a path renders as octal escapes under git's default `core.quotepath`. The letter lives in `ezhuthuIndex` as correctable data instead. |
| Publishing `attestedBy` as the list of source names | Every row pays for a list of slugs so that selection can take its length. The two counts are the gate; the names are provenance, and provenance answers a question about ONE word, which is what the store is for. |
| Resolving `definitionTa` by precedence alone | `llm-authored` sits at precedence 19 and two later rows appended sources at 21 and 22 - the two biggest Tamil-definition sources in the inventory. Precedence alone would have published an authored gloss over a dictionary's as a side effect of appending a config row. Attested-before-authored is a rule, so it cannot be broken by ordering. |
| Keeping `definitionTa` a single display slot (Row 11, withdrawn in Row 12a) | It discarded 115,545 senses across the 234,853 ta.wiktionary pages that assert one, of which 24.8 percent assert more than one; 80,356 of those fall on rows the artifact actually publishes, taking it from 102,307 senses to 182,663. A dictionary page lists every sense of its word, and a slot that keeps the first published the tree and dropped the victory. |
| Joining the senses into one string | It fits the single slot but destroys the sense BOUNDARY, so no consumer can pick one - and the paid meaning hint would spend a player's attempt on a three-sense dump. |
| Keeping sense one in `definitionTa` and the rest in a new field | Two fields describing the same thing, with the first sense either duplicated in both or absent from one. A list says it once. |
| Sorting `definitionTa` like every other list | Order is information here: element zero is the sense a hint spends. Sorting would put whichever sense begins with the earliest code point in front of a player. |
| Splitting a file pre-emptively at a size threshold | The address is a pure function of the word; a threshold makes it a function of the artifact's own history, so a clean checkout could produce a different layout from a refresh and the byte-identity Oracle would hold only when a prior artifact is present. The 33 MiB figure survives as a build ASSERTION instead. |
| A wall-clock stamp in the generated README | The artifact has no `generatedAt` precisely so a rebuild byte-compares; a date in a file the same run generates would defeat that on the first re-run. Git records when. |


## See also

- [../../concepts/lexicon.md](../../concepts/lexicon.md) - the vocabulary this pipeline produces.
- [word-hood.md](word-hood.md) - the eight signals ENRICH computes and what each one catches.
- [../contracts/schemas.md](../contracts/schemas.md) - the `lexicon` and `lexicon-sources` contracts.
- [../../how-to/add-a-lexicon-source.md](../../how-to/add-a-lexicon-source.md) - adding a source as a data change.
- [../../how-to/rebuild-the-lexicon.md](../../how-to/rebuild-the-lexicon.md) - running the stages singly or as a pipeline, and what a refresh commit contains.
- [../../how-to/enrich-the-lexicon.md](../../how-to/enrich-the-lexicon.md) - the one source that is AUTHORED rather than acquired: its provenance fields, its evidence tiers and the human review loop.
- [../../../datasets/lexicon/sources/README.md](../../../datasets/lexicon/sources/README.md) - the acquisition ledger: every source's origin, bytes and sha256.
- [../../../CLAUDE.md](../../../CLAUDE.md) - Holy Law #1 (no runtime backend), #3 (contracts before logic), #6 (no hardcoding).
