# How to add a corpus source

**Last Updated**: 2026-08-13

Adding another Tamil word source to the corpus is a **data change plus a re-run**
- never a code rewrite, and never a change to a Game or to the daily puzzle
engine. This page is the three steps.

The corpus and the daily puzzle are different layers. The ingest produces one
artifact, `datasets/wordlists/master/words_ranked.json`; the per-Game derived
sets read that; the daily puzzle engine reads those. A corpus refresh stops at
the first layer.

```
datasets/corpus/**  ->  master wordlist  ->  per-Game sets  ->  daily puzzles
   (raw sources)         (this page)          (Row 9)            (Row 13)
```

## The three steps

### 1. Put the file at `datasets/corpus/<id>/`

Pick a lower-case slug id (`opensubtitles-ta`, `ta-dedup`) and drop the file in:

```
datasets/corpus/<id>/source.<ext>
```

The raw bytes are gitignored - only the derived master wordlist is committed
(see [`../../datasets/corpus/README.md`](../../datasets/corpus/README.md)).

### 2. Add an entry to `config/corpus-sources.json`

The registry is schema-validated against
[`../../schemas/corpus-sources.schema.json`](../../schemas/corpus-sources.schema.json),
so a typo fails the run instead of being silently ignored.

For a `word,count` (or `word count`) text file:

```json
{
  "id": "my-source",
  "name": "Human-readable source name, recorded in provenance",
  "origin": "https://example.org/tamil-words.txt",
  "kind": "delimited",
  "path": "my-source/source.txt",
  "delimiter": ",",
  "hasHeader": false,
  "wordColumn": 0,
  "countColumn": 1
}
```

For a JSON document holding an array of records:

```json
{
  "id": "my-dictionary",
  "name": "Human-readable source name",
  "origin": "https://example.org/dictionary.json",
  "kind": "json-array",
  "path": "my-dictionary/source.json",
  "rootKey": "data",
  "wordField": "ta",
  "countField": "word_frequency",
  "categoryField": "category"
}
```

Then append a `changelog` entry and set `version` to today, like every schema-
backed file ([`../../CLAUDE.md`](../../CLAUDE.md) section 11).

Fields that apply to the other `kind` are **rejected**, not ignored: a
`rootKey` on a `delimited` source fails validation, because a knob that silently
does nothing is a lie in the config.

A source with `"enabled": false` is skipped without its bytes being read. Use it
(with a `note`) to keep a known-bad source registered and explained rather than
deleted - `azhiyasudargal` is registered that way because the extraction that
produced it stripped its vowel signs.

### 3. Re-run the ingest

```
python -m yen_tamizh_backend.corpus.ingest
```

It rewrites `datasets/wordlists/master/words_ranked.json` and prints the
per-source and total counters. Commit the regenerated artifact with the registry
edit.

## When you DO need code

Exactly one case: a source whose format is neither `delimited` nor
`json-array` - a fixed-width table, XML, a spreadsheet. Add a reader to
`backend/yen_tamizh_backend/corpus/ingest.py` and a member to `SourceKind` in
`backend/yen_tamizh_backend/contracts/corpus_sources.py`. Everything else -
another frequency list, another dictionary, a different column order, a
different root key - is the two steps above.

## Tuning what gets kept

`filters` and `bands` in the same registry file are the ingest's knobs
(Holy Law #6 - no hardcoded thresholds):

| Knob | Meaning |
| --- | --- |
| `minLength` / `maxLength` | Bounds on a word's **ezhuthu** count, not its code points. |
| `minTotalFrequency` | The merged-frequency floor. The long tail of a news corpus is typos, proper nouns, and one-off inflections. |
| `maxWords` | Cap on the committed artifact; `null` means uncapped. |
| `dropCategories` | Source category tags to suppress. |
| `bands.commonMaxPercentile` / `bands.midMaxPercentile` | Where `freqBand` cuts fall, as fractions of the ranked list. |

## Checking the result

The generated file opens with its own provenance and counters, so `head` tells
you what a run did:

- `provenance[]` - per source: `name`, `origin`, `bytes`, `sha256`, `rowsIn`,
  `rowsKept`.
- `counters` - the reconciliation ledger, which the contract itself enforces:
  `rowsIn - rejected - duplicates == distinct` and
  `distinct - belowFrequencyFloor - capped == rowsKept`. A silent drop cannot
  validate.

`backend/tests/test_corpus.py` re-checks that ledger and every row's ezhuthu
segmentation against the committed artifact.

After a refresh, re-run the derived sets too - they are cut from the master and
would otherwise be stale (see [add-a-derived-wordlist.md](add-a-derived-wordlist.md)).

## See also

- [add-a-derived-wordlist.md](add-a-derived-wordlist.md) - the layer below: cutting a Game's wordlist out of the master.
- [`../architecture/contracts/schemas.md`](../architecture/contracts/schemas.md) - the contract pipeline and the `corpus-sources` / `master-wordlist` decisions.
- [`../../datasets/corpus/README.md`](../../datasets/corpus/README.md) - the raw-source directory and how to repopulate it.
- [`../../CLAUDE.md`](../../CLAUDE.md) - Holy Law #3 (contracts before logic), #6 (no hardcoding), section 11 (schema versioning).
