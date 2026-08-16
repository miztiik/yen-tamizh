# How to add a lexicon source

**Last Updated**: 2026-08-17

Adding another Tamil dictionary, word list or frequency table is a **data change
plus a re-run** - a registry entry and a command, never a code rewrite. Only an
unseen source FORMAT costs code. This page is the four steps.

How the pipeline that reads these sources works, and why it is four stages, is
[../architecture/lexicon/pipeline.md](../architecture/lexicon/pipeline.md); this
page does not restate it.

## 1. Put the bytes where the ledger says

```
datasets/lexicon/sources/<source-id>/source.<ext>
```

Pick a lower-case slug id (`en-ta-dictionary`, `wiktextract-ta`). Keep the
source's real extension - a CSV is a `.csv` and a JSON Lines dump is a `.jsonl`,
so the reader meets the format it will really meet.

The raw bytes are **gitignored**. Record the source in the acquisition ledger,
[`../../datasets/lexicon/sources/README.md`](../../datasets/lexicon/sources/README.md),
with its origin, byte count and sha256, and commit a `1x` and a `10x` fixture
slice under `datasets/fixtures/lexicon/`. A test parses that ledger, so the
numbers in it cannot go stale silently.

### If the origin is compressed, put the DECOMPRESSED file at `path`

A fixture must be a byte-exact contiguous slice of the file the reader reads,
and a truncated gzip member is not a readable gzip file, so an archive on disk
could never have an honest `1x` fixture. Decompress it, put the plain file at
`path`, and record BOTH digests in the ledger - the archive's and the
decompressed file's - so the chain from what the publisher serves to what the
pipeline reads stays verifiable. The registry's `bytes` and `sha256` always
describe the file at `path`, because that is the file EXTRACT hashes on every
run.

### Cut the fixture in RECORDS, not in lines

The `10x` fixture holds exactly ten times the RECORDS of the `1x`, and a record
is whatever the source's reader counts. For a line format that is a line; for a
MediaWiki export it is a page in the declared namespace, not a physical page.
The distinction is not pedantry: counting physical pages in the Tamil Wiktionary
dump would have put its largest page - a one-megabyte village-pump archive - in
the `10x` slice and not the `1x`, and the reader's memory predicate would then
have been measuring a discussion page rather than a dictionary entry.

### Pin a dated URL, and send a real User-Agent

A `latest` URL is a moving target: the same path serves different bytes next
month, so a recorded sha256 goes stale with nothing in the repository having
changed. Check whether the publisher also offers a dated artifact and prefer it;
if only `latest` exists, record the dump date beside the digest and say in the
ledger that the URL is not stable.

A GitHub-hosted file has the same problem with a different name. A
`raw.githubusercontent.com` URL naming a BRANCH serves whatever that branch
holds today, so pin the COMMIT SHA instead - `.../IWN-En/e48e64b.../data/...`
rather than `.../IWN-En/main/data/...`. It is the same rule as the dated dump
and it costs one API call to resolve.

Some publishers refuse an anonymous fetch. `dumps.wikimedia.org` answers **HTTP
403** to Python's default `urllib` User-Agent and 200 to a descriptive one:

```
User-Agent: yen-tamizh-lexicon/1.0 (build-time corpus tooling)
```

A fetch that must be shaped a particular way belongs in the ledger next to the
origin, so that repopulating the sources is a documented procedure rather than a
rediscovery.

## 2. Add an entry to `config/lexicon-sources.json`

The registry is validated against
[`../../schemas/lexicon-sources.schema.json`](../../schemas/lexicon-sources.schema.json),
so a typo fails the run instead of being silently ignored. Fields that belong to
another `kind` are **rejected**, not ignored: a knob that silently does nothing
is a lie in the config.

Every entry carries an `id`, a `name`, an `origin`, a `role`, a `kind`, a
repo-relative `path`, its `bytes` and `sha256`, and a unique `precedence`.

### `role` - what the source is allowed to assert

| role | May assert |
| --- | --- |
| `authority` | that a surface IS a word (a `headword` fact), plus whatever else it carries |
| `authored` | the same, for values the enrichment pass wrote |
| `formEvidence` | only that a surface is NOT a headword |
| `category` | themes; never word-hood |
| `frequency` | counts; never word-hood |
| `encyclopedic` | nothing - it observes its surfaces and says a string names an ENTITY somebody wrote an article about |

Get this wrong and a scraper's long tail of typos becomes dictionary Tamil. The
distinction is [../concepts/lexicon.md](../concepts/lexicon.md)'s observation
versus attestation, and `role` is where it is declared.

`encyclopedic` is the one role that asserts NOTHING, and the reason it exists
rather than being folded into `authority` is arithmetic: an authority emits a
`headword` fact per row, so filing the Tamil Wikipedia's 237,541 article titles
there would have added one to the `attestations` count Row 12's serving gate
reads, for every place name in Tamil Nadu. Its claim is about the WORLD rather
than about the language, so `attestationTier` is forbidden on it too.

### `precedence` - who wins a single-slot value

An integer, unique across every source, **lower wins**. It decides the one
English translation a word gets published with; it does not decide `pos`, which
unions, or `categories`, which union too. Set it by how much you would trust
this source's one-word English gloss over the others'.

### `kind` - which reader streams the bytes

For a `word,count` (or `word count`) text file:

```json
{
  "id": "my-frequency-list",
  "name": "Human-readable name, recorded in provenance",
  "origin": "https://example.org/tamil-words.txt",
  "role": "frequency",
  "kind": "delimited",
  "path": "datasets/lexicon/sources/my-frequency-list/source.txt",
  "bytes": 123456,
  "sha256": "...",
  "precedence": 19,
  "delimiter": ",",
  "hasHeader": false,
  "wordColumn": 0,
  "countColumn": 1
}
```

A one-word-per-line list is that same kind with a `delimiter` the file never
contains - a tab, conventionally - so every line yields the whole line as one
column. Pick that character deliberately. A separator that DOES occur splits a
row the source meant as one thing: the Tamil Wiktionary dump writes a space as
an underscore, and splitting there would have attested the first word of every
multi-word page. A multi-word row is one surface, not several, and EXTRACT
stages it whole. (That underscore is also CANONICALIZED back to a space, because
it is MediaWiki's stored spelling of the same title the content dump writes with
a space - see `docs/architecture/lexicon/pipeline.md`.)

For a delimited file whose fields are RFC-4180 QUOTED - IndoWordNet's linked
release is one - the kind is `delimited-quoted` and the knobs are the same four:

```json
{
  "id": "my-quoted-table",
  "kind": "delimited-quoted",
  "delimiter": "\t",
  "hasHeader": true,
  "wordColumn": 8
}
```

Choose it whenever a field may be wrapped in double quotes, because then a field
may legally hold the delimiter, a doubled quote, or a NEWLINE - which means a
record is not a line. Three of IndoWordNet's 16,640 records span two physical
lines, and the plain `delimited` reader turns those two records into four
malformed rows rather than failing, which is the worst of both. If you are not
sure, count logical rows with `csv.reader` and compare against the line count:
if they differ, the file is quoted.

For a JSON document holding an array of records:

```json
{
  "id": "my-dictionary",
  "kind": "json-array",
  "rootKey": "data",
  "elementKind": "object",
  "wordField": "ta",
  "countField": "word_frequency",
  "categoryField": "category",
  "posField": "pos"
}
```

For one JSON object per line:

```json
{ "id": "my-dump", "kind": "jsonl", "wordField": "word", "posField": "pos" }
```

For a MediaWiki export - a wiki's own XML dump of its pages:

```json
{ "id": "my-wiki", "kind": "mediawiki-xml", "pageNamespace": 0 }
```

### `pageNamespace`, and why there is no default

`pageNamespace` is REQUIRED on every `mediawiki-xml` source and forbidden on
every other. A dump interleaves articles with talk pages, templates, categories
and project discussion, and which of them are this source's RECORDS is a fact
about the export rather than about the format - the same thing `hasHeader` says
about a delimited file's first line. A default of `0` would be a guess about
somebody else's dump, so there is none.

The record is the PAGE, so no field mapping applies and setting one is rejected:
the reader already knows the export's own element names. What it yields is
`{title, ns, text}`, and what the markup MEANS is an extractor's job - the Tamil
Wiktionary's conventions live in `wordsmith/wikitext.py`, beside the reader
rather than inside it.

A page outside the declared namespace is not counted as a parse reject, because
it is not a record that failed to parse - it is not a record. Its text is never
even accumulated, which is what keeps peak memory proportional to the largest
ARTICLE rather than to the largest page: in the Tamil Wiktionary dump those
differ by a factor of 45.

### Which `elementKind` to write

`elementKind` is REQUIRED on every `json-array` source, forbidden on every other
kind, and has no default.

- `"object"` - the array holds `{ ... }`. Also set `wordField`.
- `"string"` - the array holds bare `"..."` words. No field mapping applies, and
  setting one is rejected.

There is no member for a bare number, and there never will be: a number is not
self-terminating, so a truncated one decodes to a wrong value instead of raising
([the rule](../architecture/lexicon/pipeline.md#the-self-terminating-element-rule)).
Choosing wrong is safe in the loud way - the reader raises naming the array and
the character it found.

**Omit `rootKey` when the document ROOT is the array.** Absence is a claim the
reader checks against the bytes, not a fallback.

## 3. Register every raw tag the source uses

`posAliases` must have an entry for every part-of-speech tag your source can
emit, and `categoryAliases` for every category label. A tag with no entry
**raises at extract**, naming the tag - never dropped, and never passed through,
which would defeat the closed `pos` vocabulary.

An alias routes a tag one of three ways, and exactly one:

```json
"n.pl":        { "pos": ["noun"], "wordClassEvidence": ["inflected"] },
"name":        { "wordClassEvidence": ["properNoun"] },
"proverb":     { "reject": "multiWordUnit" }
```

- **`pos`** when the tag names a part of speech Tamil has. The vocabulary is
  closed and lives in the contract; check it before inventing a mapping. Tamil
  has postpositions, not prepositions.
- **`wordClassEvidence`** when the tag says what KIND of surface this is - a
  name, a bound morpheme, a contraction. Evidence is the classifier's input,
  never its verdict, which is why `headword` is not among the values.
- **`reject`** with a named reason - `notAWord`, `multiWordUnit`,
  `noTamilCounterpart`, `notAPosLabel` - when the tag yields no part of speech.
  A rejected tag is COUNTED and reported, which is what makes it different from
  a drop.

Do NOT enumerate parse garbage here. A row with no marker at all, or a marker
that is only punctuation or a page reference, is a counted parse reject in the
reader, where the stage's own ledger accounts for it. `notAPosLabel` is for a
value that genuinely RECURS in a structured field and names no part of speech -
the curated master dictionary's blanket `nouns` stamp, which it puts on 99.8
percent of its rows including verbs, is the one on file.

Count the tags over the WHOLE source before writing the map. A fixture is a head
slice, not a sample, and a distribution inferred from one will be wrong.

## 4. Re-run EXTRACT

```
python -m yen_tamizh_backend.wordsmith.extract --source my-dictionary
```

It writes `datasets/lexicon/cache/extracts/my-dictionary.jsonl` (gitignored) and
prints the ledger:

```
my-dictionary: rowsIn=1290 rowsOut=1290 parseRejects=0 observations=1290 facts=2580 posUnparsed=0 posRejected=0
```

`rowsOut + parseRejects` must equal `rowsIn`; the stage refuses to write the file
otherwise. A run with no `--source` does every enabled source, and skips any
whose extract already matches the source digest - pass `--force` to override.

## 5. Re-run STAGE

```
python -m yen_tamizh_backend.wordsmith.stage --source my-dictionary
```

This is the step that makes adding a source a DATA change rather than a rebuild:
the store replaces that one source's rows and touches nobody else's, so the
other eighteen sources are not re-read.

```
my-dictionary: observations=1290->1121 surfaces facts=2580 epoch=19 0.1s
```

`observations` is what the extract held; `surfaces` is what the store holds after
same-source duplicates are summed, so the two differ exactly when the source
named one surface more than once.

Three more things this command can do:

- `--remove my-dictionary` deletes that source's whole contribution, in one
  transaction. It is the entry point for retiring a source, and it is also how
  you check that a source is contributing what you think it is.
- `--rebuild` deletes the store first, so the run is a full rebuild. It should
  never be necessary - a delta and a full rebuild produce identical rows, which
  is the property [the pipeline doc](../architecture/lexicon/pipeline.md) calls
  `delta == full` - but it is the fastest way to prove that on your own machine.
- A corrected re-extraction needs no special handling. Re-running EXTRACT and
  then STAGE for that source IS the correction, because an apply replaces.

Then re-run the stages below it.

## When you DO need code

Two cases, and only two:

1. **An unseen FORMAT** - a fixed-width table, a spreadsheet. Add a reader
   to `backend/yen_tamizh_backend/wordsmith/readers.py` and a member to
   `LexiconSourceKind` in the contract.
2. **Facts the four field mappings cannot name.** `wordField`, `countField`,
   `categoryField` and `posField` cover a flat record. A source whose
   translations live in a differently named field, or whose senses nest inside
   an array, needs an extractor in `extract.py` - subclass `SourceExtractor` and
   override `extra_facts`. Seven of the twenty-three registered sources do.

IndoWordNet needed both, and it is the worked example for each. Its file is an
RFC-4180 quoted TSV, which no existing reader could see, so it added the
`delimited-quoted` kind. And its record is a SYNSET - a concept, the Tamil words
that express it, a Tamil gloss, a part of speech and a Princeton WordNet link -
which is five meanings across five columns where the registry names one column
per mapping, so it overrides `feed` outright. `wordColumn` is still read from
the registry, because that is the column the surfaces come from; the other four
column indexes live in the extractor, exactly as the English-Tamil dictionary's
marker grammar does.

A source whose bytes are MARKUP needs both, and they stay separate: the reader
knows the file format, the extractor knows what a record asserts, and a third
module knows the markup's own conventions. `wikitext.py` is that third module
for the Tamil Wiktionary, and its rule is that an unrecognised convention costs
a COUNTED miss rather than an invented fact - the stage prints how many lines it
could not read beside its seven-field tally.

Another frequency list, another dictionary, a different column order, a
different root key, a source with no root key at all: all of those are the four
steps above.

## Disabling a source, and sources that do not exist

A source with `"enabled": false` is skipped without its bytes being read. Use it,
with a `note`, to keep a known-bad source registered and explained rather than
deleted - `azhiyasudargal` is registered that way because the extraction that
produced it stripped its vowel signs.

A source that was SOUGHT and never obtained gets no registry entry at all. Every
entry must carry a real `path`, `bytes` and `sha256`, and inventing a digest for
bytes nobody has is a lie in a file whose whole purpose is provenance. It stays
in the acquisition ledger with its status and the URLs that were tried, which is
where "we looked, and here is what happened" belongs - `madras-lexicon` is
recorded there.

## See also

- [../architecture/lexicon/pipeline.md](../architecture/lexicon/pipeline.md) - the four stages, and why the readers stream.
- [../concepts/lexicon.md](../concepts/lexicon.md) - observation versus attestation, `wordClass`, `pos` versus `categories`.
- [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) - the `lexicon-sources` contract and its shape decisions.
- [`../../datasets/lexicon/sources/README.md`](../../datasets/lexicon/sources/README.md) - the acquisition ledger.
- [`../../CLAUDE.md`](../../CLAUDE.md) - Holy Law #3 (contracts before logic), #6 (no hardcoding), section 11 (schema versioning).
