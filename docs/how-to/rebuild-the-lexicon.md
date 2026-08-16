# Rebuild the lexicon

**Last Updated**: 2026-08-16

How to run the `wordsmith` pipeline: the whole thing, one stage, or one source.
Why it is four stages is [../architecture/lexicon/pipeline.md](../architecture/lexicon/pipeline.md);
what the words mean is [../concepts/lexicon.md](../concepts/lexicon.md).

This is an **operator** path. It reads roughly 1.1 GB of gitignored third-party
sources and takes the better part of an hour on a developer laptop. It never
runs in CI and never on a schedule - CI runs the type checks, the tests, and the
fixture-pipeline gate that drives the same four stages over committed fixture
slices.

Every command below runs from `backend/`. Nothing needs installing: the package
is on `sys.path` because that is the working directory.

```bash
cd backend
```

## Before anything: get the sources

The raw bytes are gitignored, so a fresh clone has none of them.
[`../../datasets/lexicon/sources/README.md`](../../datasets/lexicon/sources/README.md)
is the acquisition ledger - every source's origin, destination path, byte count
and sha256. Copy the predecessor-repo files and download the network ones to the
`path` each row names. EXTRACT re-verifies every digest against
`config/lexicon-sources.json` on each run, so a wrong or truncated file fails
loudly rather than quietly producing a thinner lexicon.

`madras-lexicon` is permanently **NOT ACQUIRED** - no bulk artifact exists - and
is deliberately absent from the registry rather than faked.

## The whole pipeline

```bash
python -m yen_tamizh_backend.wordsmith.pipeline
```

EXTRACT, then STAGE, then ENRICH, then PUBLISH. Useful flags:

| Flag | Effect |
| --- | --- |
| `--force` | re-extract every source even when its bytes are unchanged |
| `--workers N` | processes for the neighbour search (default: every core) |
| `--db PATH` | a store somewhere other than the registry's own cache |
| `--root PATH` | a repository root other than this one |

`pipeline` only sequences. Every stage below is runnable on its own, and that is
the property to lean on - a failure in stage three costs stage three.

## One stage at a time

### EXTRACT - raw bytes to per-source facts

```bash
python -m yen_tamizh_backend.wordsmith.extract
python -m yen_tamizh_backend.wordsmith.extract --source ta-wiktionary-content
python -m yen_tamizh_backend.wordsmith.extract --force
```

Writes `datasets/lexicon/cache/extracts/<source-id>.jsonl`. A source whose bytes
match the digest in its own extract's header line is SKIPPED, so a re-run after
one new source costs one source.

### STAGE - facts into the delta store

```bash
python -m yen_tamizh_backend.wordsmith.stage
python -m yen_tamizh_backend.wordsmith.stage --source indowordnet-ta
python -m yen_tamizh_backend.wordsmith.stage --remove azhiyasudargal
```

Applies one extract per source into the STAGED zone of
`datasets/lexicon/cache/lexicon.db`, in its own transaction. Applying a source
twice is the same as applying it once, and applying them in any order gives the
same store - which is what makes `--source` a real delta rather than a shortcut.

`--remove ID` deletes one source's contribution whole. Use it when a source is
retired or when its bytes changed shape; then re-extract and re-stage it.

Both operations bump `stage_epoch`, which puts the derived zone BEHIND. PUBLISH
refuses to run in that state, so a re-stage always costs an ENRICH.

### ENRICH - signals and the word-hood verdict

```bash
python -m yen_tamizh_backend.wordsmith.enrich
python -m yen_tamizh_backend.wordsmith.enrich --signal orthotactic
python -m yen_tamizh_backend.wordsmith.enrich --classify
```

A full run drops the DERIVED zone and recomputes it whole - all eight signals
and every `wordClass` - then stamps `derived_epoch`. It is the long stage.

`--signal NAME` recomputes ONE column in place over a populated zone. It does
not touch `derived_epoch`, because a column that is a pure function of the
staged zone cannot make a current zone stale nor a stale one current.

`--classify` re-runs only the classification pass. That is the command for a
`config/wordhood.json` edit or a re-ruled `attestationTier`: the tier is read
from the REGISTRY, not from the store, so re-ruling a source is a config edit
plus a `--classify` - never a re-stage.

### PUBLISH - the committed artifact

```bash
python -m yen_tamizh_backend.wordsmith.publish
```

Writes three things under `datasets/lexicon/`:

- `by-class/<wordClass>/<hex>.ndjson` - one file per (class, first ezhuthu),
  rows sorted by `word` ASC;
- `lexicon.meta.json` - the index: provenance, both counter families, one
  `partitions[]` entry per file with its `sha256`, and `ezhuthuIndex` decoding
  every hex key to its letter;
- `README.md` - the generated ready-reckoner. Never hand-edit it; PUBLISH
  rewrites it from the meta document on every run.

It refuses to run when the derived zone is behind the staged one, when a source
was staged from bytes the registry no longer declares, when a fact carries a
value no closed vocabulary admits, or when a file crosses `maxPartitionBytes`.
Each refusal names what to fix.

Only `headword`, `properNoun`, `boundStem` and `colloquial` are committed. The
store still holds everything, and `counters.classified` in the meta document
carries a per-class census of the whole population so the withheld classes are
provable in the repository. Which classes publish is `publishedClasses` in
`config/lexicon-sources.json`.

## REVIEW - reading the residue

```bash
python -m yen_tamizh_backend.wordsmith.review
```

Writes four NDJSON reports into `datasets/lexicon/review/` - gitignored, with a
committed README saying what each is. It is a REPORT: it writes nothing back to
the store, so running it can never change a verdict. It is deliberately not part
of the `pipeline` sequence.

Run ENRICH first if the store has been re-staged. A report over a stale derived
zone describes a lexicon that no longer exists.

## What a refresh commit contains

A refresh is a data change, and the diff is the review. Stage exactly:

- `datasets/lexicon/by-class/**` - the changed rows;
- `datasets/lexicon/lexicon.meta.json` - the index, whose per-file `sha256` is
  what proves the rows were not hand-edited;
- `datasets/lexicon/README.md` - regenerated with them;
- `config/lexicon-sources.json` - only if a source's bytes, digest or registry
  entry changed;
- `datasets/lexicon/sources/README.md` - only if the acquisition ledger changed.

Nothing else. `git status --porcelain` must show no `.db`, no extract cache, no
raw source and no review report - all four are gitignored, and seeing one staged
means an ignore rule was bypassed.

Read the diff before committing. Because rows sort by `word` within a stable
address, a healthy refresh looks like inserted lines and edited lines, and a row
moving BETWEEN files is a re-classification - a real semantic event worth a
second look.

## When the fixture expectation changes

The integration gate runs all four stages over the committed fixture slices and
byte-compares the result against `datasets/fixtures/lexicon-expected/`. Any
legitimate change to what the pipeline produces - a new source, an edited
authored batch, a classifier rule - changes that expectation too. Regenerate it
with the one command that owns it, never by hand:

```bash
python -m yen_tamizh_backend.scripts.rebuild_lexicon_fixture --workspace ../.tmp_fixture
```

Then read the diff, and commit it in the same change that caused it.

## See also

- [../architecture/lexicon/pipeline.md](../architecture/lexicon/pipeline.md) - the four stages and why the layout is this one.
- [../architecture/lexicon/word-hood.md](../architecture/lexicon/word-hood.md) - the eight signals and the classification cascade.
- [../concepts/lexicon.md](../concepts/lexicon.md) - what a `wordClass` is and what attestation means.
- [add-a-lexicon-source.md](add-a-lexicon-source.md) - registering a new source as a data change.
- [enrich-the-lexicon.md](enrich-the-lexicon.md) - the authored source and its review loop.
- [../../datasets/lexicon/sources/README.md](../../datasets/lexicon/sources/README.md) - the acquisition ledger.
