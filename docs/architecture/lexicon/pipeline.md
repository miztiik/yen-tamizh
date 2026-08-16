# The lexicon pipeline

**Last Updated**: 2026-08-16

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
| PUBLISH | `... .publish` | both zones | `datasets/lexicon/by-class/*.ndjson` + `lexicon.meta.json` |

Each stage reads the previous stage's ON-DISK artifact rather than an in-process
value, and `pipeline.py` only sequences them. That is what makes a stage
independently runnable, independently debuggable, and restartable after a crash
without redoing the stage before it. A single pass over 450 MB of sources would
have none of those properties: one bad row in the last source would cost the
whole run, and there would be no way to re-read ONE source without re-reading
all nineteen.

The seam is also what makes DELTA ingest possible. A source's contribution has
to be recomputable in isolation before it can be replaced or removed in
isolation, and an addressable per-source extract file is the cheapest way to
make it so.

All four stages exist. `python -m yen_tamizh_backend.wordsmith.pipeline` runs
them in order and holds no logic of its own.

## EXTRACT

One reader per source KIND turns raw bytes into elements; one extractor per
source SHAPE turns an element into emissions. Two kinds of emission, and the
difference between them is the whole point of the layer:

- an **observation** is `(source, surface, count)` - this source saw this
  surface, this many times. It says nothing about word-hood.
- a **fact** is `(word, attr, value, ordinal)` - this source asserted this
  typed thing. The attributes are `headword`, `translation`, `definitionEn`,
  `definitionTa`, `synonym`, `pos`, `category`, `graphemeCount` and
  `wordClassEvidence`.

Only a source whose `role` is `authority` or `authored` emits a `headword` fact.
A frequency list observing a surface a million times still cannot say it is a
word, and the registry's `role` is what enforces that at the boundary rather
than three stages later.

### EXTRACT never filters

Not on word-hood, not on quality, not on length. The only transform is NFC
normalization, which is canonicalization rather than cleaning. A surface a
source showed us reaches the store even when it is obviously junk, because the
lexicon's thesis is that **ingest enriches and selection filters** - and a word
wrongly excluded should cost a selection knob, not a re-ingest over hundreds of
megabytes of gitignored bytes.

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

Peak memory must not track file size - the largest registered source is 188 MB
and the whole set is about 450 MB - so every reader is a generator over a
bounded buffer. No reader calls `json.load`, `read()` or `readlines()` on a
source file. Delimited sources are read a line at a time, JSONL a line at a
time, and a JSON array one element at a time through the standard library's own
incremental entry point, `JSONDecoder.raw_decode`, over a sliding buffer.

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

The staged rows built by applying nineteen extracts one at a time, in any order,
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

## PUBLISH

PUBLISH reads both zones, resolves every published word's facts into one row,
and streams the result to `datasets/lexicon/by-class/*.ndjson` beside the
sibling index `datasets/lexicon/lexicon.meta.json`. Running it - singly or as
part of the whole pipeline - is
[../../how-to/rebuild-the-lexicon.md](../../how-to/rebuild-the-lexicon.md).

### Retention is not publication

The store keeps every surface any source ever showed us, and every fact any
source asserted about it. The REPOSITORY commits the classes a player can
actually be served: `headword`, `properNoun`, `boundStem` and `colloquial`.

The two are different questions and the pipeline answers them in different
places. **Retention** is what the lexicon's thesis is about - ingest enriches,
selection filters, and a word wrongly excluded should cost a selection knob
rather than a re-ingest over hundreds of megabytes of gitignored bytes. That
property lives in the store, and it is untouched by what gets committed.
**Publication** is a separate decision, and it is a decision rather than a
default because git history is append-only: a byte committed once is carried
forever, and the classes this policy withholds are 6.4 million rows of scrape
artifacts, inflected forms and unreviewed surfaces with no consumer.

What keeps the thesis honest is that the withheld classes are still on the
record, at their real size, in the repository - see the two counter families
below. The published set is declared as `publishedClasses` in
`config/lexicon-sources.json`, so changing the policy is a config edit plus a
re-publish, never a code change (Holy Law #6).

### The address is a pure function of the word

A published file is addressed by `wordClass` then by the word's BASE FIRST
EZHUTHU, rendered as a lowercase 4-digit hex code point:
`headword-0b95.ndjson`. That is the whole address - two keys, both immutable per
word - and the immutability is the decision rather than any byte figure:

- the base first ezhuthu is `segment(word)[0][0]`, which is always `word[0]`, so
  it is a property of the word itself and can never change;
- `wordClass` is the classifier's verdict, so it changes only when the verdict
  does - which is two line changes and precisely the semantic event a reviewer
  should see.

So a refresh INSERTS a line into a file that already exists, and never
reshuffles one. Nothing in PUBLISH reads a previous artifact to decide where a
row goes, which is what makes a clean checkout produce the same layout as a
refresh.

Within a file, rows sort by `word` ASC. Because the address is the word's first
code point and SQLite's default collation orders text by its UTF-8 bytes - which
for every code point is code-point order - the sort and the partition cut are
the SAME order. Concatenating a class's files in hex order reproduces the sorted
class exactly, so the split is invisible to a consumer.

Filenames stay hex and never carry the Tamil letter or a romanization. Tamil
script in a path is disqualified by CLAUDE.md section 5 and by git's default
`core.quotepath`, which renders non-ASCII paths as octal escapes. A
romanization is disqualified because it is a JUDGEMENT CALL, and correcting a
judgement call must not rename a published file: the repo's own ASCII spellings
contain two case-only collisions (`N` and `n`, `L` and `l`) that would collide
on case-insensitive filesystems. The rule underneath is **put the immutable
identifier in the path and the correctable label in the data**.

### The meta index, and what a reader may rely on

`lexicon.meta.json` is the index, and it is where legibility is answered. It
carries:

- `partitionKeys` - the ordered address `["wordClass", "baseFirstEzhuthu"]`,
  declared IN the artifact so the address function does not live only in the
  code that wrote it. The contract pins it, so changing the layout is a contract
  change rather than a quiet one.
- `partitions[]` - ONE ENTRY PER FILE, with `path`, `wordClass`,
  `baseFirstEzhuthu`, `rows`, `bytes` and `sha256`.
- `ezhuthuIndex` - each hex decoded ONCE to `{ezhuthu, roman, kind}`. This is
  where a human reads which letter a file holds. The Tamil character and its
  ASCII spelling are spelled out as correctable data in a JSON value a reviewer
  already opens, so fixing a romanization is a one-line diff plus a changelog
  entry rather than a rename.
- `version`, `changelog` and `provenance` - every staged source, with the exact
  `sha256` and byte count its rows were built from.

**Resolution contract.** To read a class, select every `partitions[]` entry with
that `wordClass`, order by `baseFirstEzhuthu` ASC, and concatenate. There is NO
globbing and NO probe-and-fallback: a reader resolves a file from this table
alone. That is why the model refuses a partition whose hex the index cannot
decode, an index entry no file uses, and a `partitions[]` set that disagrees
with the directory - a no-globbing reader is structurally blind to a file
written but not registered, or registered but not written.

### The counters come in TWO families

```
counters.classified   every wordClass, over the WHOLE population the store holds
counters.published    every wordClass, over what the files actually carry
```

One family could not have said both things. `classified` is the census that
proves nothing was destroyed: the withheld classes are named, counted and
committed, so "the store retains everything" is checkable from the repository
rather than asserted in a document. `published` is what the partition table must
reconcile against.

The rule binding them is enforced by the contract: **publication is
all-or-nothing per class**. A published count is either zero, or exactly the
classified count. A count that is neither is rows LOST between the classifier
and the writer - the one failure a per-class policy would otherwise hide, since
a partial count looks exactly like a partial policy.

### Resolution: union, precedence, and sum

STAGE deliberately resolves nothing, so that the staged zone stays commutative.
PUBLISH is where the contradiction is settled, once, with the registry's
precedence in hand. Three shapes of rule, and the differences are not arbitrary:

| Column | Rule |
| --- | --- |
| `pos`, `synonymsTa`, `categories`, `attestedBy` | **UNION**, deduped and sorted |
| `translationEn`, `definitionTa` | **PRECEDENCE** - the lowest per-source integer wins |
| `frequency` | **SUM** over the frequency-role corpora |
| `spokenRatio` | the declared `spokenSources` share of that sum |

A set-valued fact with no display slot UNIONS, because a Tamil verbal noun
genuinely is both a noun and a verb and precedence would delete whichever a
lower-ranked source held. A fact that occupies ONE display slot RESOLVES,
because exactly one can be shown - and the winner is decided by an explicit
per-source integer, never by the order the registry array happens to be written
in, so reordering it for readability can never change a published value. A count
SUMS, because evidence adds up rather than competing.

`definitionEn` is never published. The lexicon takes the FACT a source asserted;
a dictionary's edited prose is its own.

Two things are omitted under one stated principle rather than case by case. A
column is omitted only if BOTH (a) it is a derived value of this pipeline rather
than a fact a source asserted, and (b) omitting it cannot cost the project the
fact - either it is recomputable from the COMMITTED ARTIFACT ALONE, or the
verdict it produced is published. `wordhood` goes because `wordClass` IS its
verdict; `freqRank` goes because it is a sort of the published `frequency`; and
`ezhuthu` goes because it is `segment(word)`, a pure function of a published
column. The test is deliberately "from the committed artifact" and not "from the
sources": `frequency` is recomputable from the frequency corpora, and a
source-based test would re-permit a word-only line.

### A raw value outside a closed vocabulary fails the publish

The tag maps translate a source's own orthography at EXTRACT, so a `pos` or
`category` value reaching the store outside the closed vocabulary means the
store was staged under a registry that has since changed. PUBLISH refuses,
naming the value AND its row count, over the whole store rather than only the
published rows - a bad tag on a withheld class still means the registry is
wrong. Never dropped, because a silent boundary drop is the defect this pipeline
exists to remove; never passed through, because that defeats the closed enum.

### PUBLISH streams, and its line endings are named

One `json.dumps(row, ensure_ascii=False, sort_keys=True)` per line, written
straight from a cursor to a handle opened with an EXPLICIT `newline="\n"` and
`encoding="utf-8"`. Peak memory is one row.

The explicit newline is not decoration. The operator runs Windows, where
Python's default text mode translates every `\n` into `\r\n` - so the default
would make the same store publish different bytes on the machine that performs
the real publish than in CI, breaking the byte-identity Oracle exactly where it
matters most. `.gitattributes` pins the same thing on the checkout side.

Each file is written to a `.partial` and renamed into place, then hashed by
READING IT BACK, so the `sha256` in the index is a statement about the bytes on
disk rather than about what the process meant to write. A file a previous
publish wrote that this one no longer addresses is deleted, because otherwise
the directory and the index disagree and a no-globbing reader would never
notice.

### The size ceiling is an assertion, not a threshold

`maxPartitionBytes` (33 MiB, one third of GitHub's 100 MiB hard blob wall) is
checked after every file is written, and PUBLISH fails naming the file and its
byte count. It does NOT choose the layout - the address does. It is the line
that says out loud that one file has outgrown what the address can hold, so the
answer is a decision rather than a larger number.

### The full rebuild is operator-only

CI runs the type checks, the tests, and the fixture-pipeline integration gate -
all four stages over the committed byte-exact fixture slices, byte-compared
against a committed expectation. It never runs the real rebuild: the raw sources
are gitignored so CI has nothing to rebuild from, and a scheduled rebuild would
shift the frequency sums and therefore the candidate list every night, which
would make the daily bank's no-rewrite rule unenforceable in principle.

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
| One `lexicon.json` holding every word | 6.5 million rows at the measured widths is over a gigabyte, and GitHub hard-rejects any blob over 100 MiB. The wall is a wall, not a preference. |
| Publishing every class at reduced fidelity - a word-only line for the bulk classes | It discards `frequency`, a fact a source ASSERTED and one recoverable only from gitignored raw bytes. That is a real drop, and it is a different thing from omitting a value the artifact can recompute from itself. |
| Partitioning by frequency band, or by a hash of the word | Frequencies change on every refresh, so words would migrate between files constantly - the reshuffle the immutable address exists to prevent. A hash is stable but destroys read locality and makes "what changed in headwords?" span every file, while the first code point is equally stable AND is the sort's own key. |
| An ezhuthu `length` key beside the class | It addresses nothing at the measured 139,067 published rows, and a partition key that is sometimes present is worse than one that is always there - a word's ADDRESS would depend on the SIZE of its class, which is a property of the artifact rather than of the word. |
| Publishing `ezhuthu` alongside `word` | It is `segment(word)`, so the omission principle covers it - and a stored copy of a derived value is a drift surface as well as 35.4 B a row. `length` stays because it is what selection reads and because checking it against the live segmentation catches a corrupt row at a fortieth of the bytes. |
| A romanized or Tamil-script filename | ISO 15919 is diacritic-based and so not ASCII; the repo's own ASCII spellings collide on case (`N`/`n`, `L`/`l`) on case-insensitive filesystems; and Tamil script in a path is CLAUDE.md section 5 plus git's octal-escaped `core.quotepath` output. The letter is spelled out in `ezhuthuIndex` instead, where correcting it is a one-line diff. |
| A single `counters` family over the published rows only | The withheld classes would exist only in a gitignored store, so "nothing was discarded" would be a claim rather than a check. Two families make it arithmetic. |
| `render_document` for the lexicon | It materialises the row list, the joined string, the `replace` copy and the encode buffer at once. Its own comment sizes it for a 12 MB artifact; this one is 76.8 MiB and the store it streams from holds 6.5 million rows. |
| Rebuilding the lexicon in CI or in `daily.yml` | The raw sources are gitignored, so CI has nothing to rebuild from, and nightly frequency drift would change already-published days. |


## See also

- [../../concepts/lexicon.md](../../concepts/lexicon.md) - the vocabulary this pipeline produces.
- [word-hood.md](word-hood.md) - the eight signals ENRICH computes and what each one catches.
- [../contracts/schemas.md](../contracts/schemas.md) - the `lexicon` and `lexicon-sources` contracts.
- [../../how-to/add-a-lexicon-source.md](../../how-to/add-a-lexicon-source.md) - adding a source as a data change.
- [../../how-to/rebuild-the-lexicon.md](../../how-to/rebuild-the-lexicon.md) - running the stages singly or as one pipeline, and what a refresh commit contains.
- [../../how-to/enrich-the-lexicon.md](../../how-to/enrich-the-lexicon.md) - the one source that is AUTHORED rather than acquired: its provenance fields, its evidence tiers and the human review loop.
- [../../../datasets/lexicon/sources/README.md](../../../datasets/lexicon/sources/README.md) - the acquisition ledger: every source's origin, bytes and sha256.
- [../../../CLAUDE.md](../../../CLAUDE.md) - Holy Law #1 (no runtime backend), #3 (contracts before logic), #6 (no hardcoding).
