# The lexicon pipeline

**Last Updated**: 2026-08-15

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
| ENRICH | `... .enrich [--signal NAME]` | the STAGED zone | the DERIVED zone: signals and `wordClass` |
| PUBLISH | `... .publish [--format ...]` | both zones | `datasets/lexicon/*` |

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

EXTRACT is the only stage that exists today. STAGE, ENRICH and PUBLISH document
themselves here as they land.

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

## See also

- [../../concepts/lexicon.md](../../concepts/lexicon.md) - the vocabulary this pipeline produces.
- [../contracts/schemas.md](../contracts/schemas.md) - the `lexicon` and `lexicon-sources` contracts.
- [../../how-to/add-a-lexicon-source.md](../../how-to/add-a-lexicon-source.md) - adding a source as a data change.
- [../../../datasets/lexicon/sources/README.md](../../../datasets/lexicon/sources/README.md) - the acquisition ledger: every source's origin, bytes and sha256.
- [../../../CLAUDE.md](../../../CLAUDE.md) - Holy Law #1 (no runtime backend), #3 (contracts before logic), #6 (no hardcoding).
