# Rebuild the lexicon

**Last Updated**: 2026-08-16

How to run the four lexicon stages - singly, or as one pipeline - and what a
refresh commit contains. WHY the pipeline is shaped this way is
[../architecture/lexicon/pipeline.md](../architecture/lexicon/pipeline.md); what
the words mean is [../concepts/lexicon.md](../concepts/lexicon.md).

This is an OPERATOR path. It runs on a developer laptop a handful of times over
the project's life, never in CI and never on a schedule: the raw sources are
gitignored, so CI has nothing to rebuild from, and a nightly rebuild would shift
the frequency sums and therefore the served candidate list every night.

## Before you start

- Run every command with the working directory set to `backend/`. The package is
  not installed; the working directory is what puts it on `sys.path`.
- The raw sources must be on disk under `datasets/lexicon/sources/` and
  `datasets/corpus/`. They are gitignored; repopulate them from the ledger in
  [`datasets/lexicon/sources/README.md`](../../datasets/lexicon/sources/README.md),
  which records each source's origin, byte count and sha256.
- The store at `datasets/lexicon/cache/lexicon.db` is gitignored and rebuildable.
  Copying one from another worktree is the cheapest way to skip the stages you
  are not changing - the file is a plain SQLite database and a copy takes
  seconds.

## The whole pipeline

```
python -m yen_tamizh_backend.wordsmith.pipeline
```

EXTRACT, then STAGE, then ENRICH, then PUBLISH. Add `--force` to re-extract
every source even when its bytes are unchanged. Budget the better part of an
hour: ENRICH is about twenty minutes of it and PUBLISH about a minute.

## One stage at a time

Each stage reads the previous stage's ON-DISK artifact, so any stage can be
re-run on its own without redoing the one before it.

| Stage | Command | Writes |
| --- | --- | --- |
| EXTRACT | `python -m yen_tamizh_backend.wordsmith.extract` | `datasets/lexicon/cache/extracts/<id>.jsonl` |
| STAGE | `python -m yen_tamizh_backend.wordsmith.stage` | the store's STAGED zone |
| ENRICH | `python -m yen_tamizh_backend.wordsmith.enrich` | the store's DERIVED zone |
| PUBLISH | `python -m yen_tamizh_backend.wordsmith.publish` | `datasets/lexicon/by-class/*.ndjson` + `lexicon.meta.json` |

## Delta: one source changed

Adding, replacing or re-acquiring a single source does not need a full rebuild.
The staged zone is per-source and commutative, so one source's rows can be
replaced in isolation:

```
python -m yen_tamizh_backend.wordsmith.extract --source <source-id>
python -m yen_tamizh_backend.wordsmith.stage   --source <source-id>
python -m yen_tamizh_backend.wordsmith.enrich
python -m yen_tamizh_backend.wordsmith.publish
```

ENRICH is NOT optional here, and it is not a delta. Four of the eight word-hood
signals are whole-corpus functions, so the derived zone is dropped and
recomputed whole - and PUBLISH refuses a store whose derived zone is behind its
staged one rather than publishing signals computed over a store that has since
moved.

Registering the source itself is a data change in
`config/lexicon-sources.json`; see
[add-a-lexicon-source.md](add-a-lexicon-source.md).

## Remove: one source retired

```
python -m yen_tamizh_backend.wordsmith.stage --remove <source-id>
python -m yen_tamizh_backend.wordsmith.enrich
python -m yen_tamizh_backend.wordsmith.publish
```

`--remove` deletes that source's observations and facts in one transaction and
stamps the epoch. Removing a source from the registry without removing it from
the store leaves its rows behind, and PUBLISH will refuse: it checks that every
staged source is one the registry still names.

## Development paths

```
python -m yen_tamizh_backend.wordsmith.enrich --signal <name>
python -m yen_tamizh_backend.wordsmith.enrich --classify
```

Both recompute one thing over the population the derived zone already holds, and
neither touches `derived_epoch` - the column or the verdict is a pure function
of the staged zone, so recomputing it cannot make a current zone stale, nor a
stale one current. Both refuse when there is no population to update.

Re-ruling a source's `role`, `precedence`, `attestationTier` or membership of
`spokenSources` is a config edit plus `--classify` and a re-publish. It is never
a re-stage: those are properties PUBLISH and the classifier read from the
REGISTRY, not from the store's copy.

## What PUBLISH refuses

Each of these is a loud failure with the offending name in the message, never a
silent drop:

- the derived zone is behind the staged zone - run ENRICH;
- the store holds a source the registry no longer names, or a source staged from
  bytes whose sha256 the registry no longer declares - re-extract and re-stage
  it;
- a `pos` or `category` value no closed vocabulary admits, named with its row
  count - register it in `config/lexicon-sources.json` with a destination or an
  explicit reject reason, then re-extract and re-stage;
- an output file over `maxPartitionBytes`, named with its byte count;
- a registry declaring an output format this stage does not write.

## What a refresh commit contains

```
datasets/lexicon/by-class/<wordClass>-<hex>.ndjson   the changed files only
datasets/lexicon/lexicon.meta.json                   always
```

The address is a pure function of the word, so a refresh INSERTS lines into
files that already exist and never reshuffles one. Expect:

- **a new word** - one inserted line, in `word` ASC position;
- **a changed frequency or meaning** - one line rewritten in place;
- **a changed `wordClass`** - two line changes, one file losing a row and
  another gaining it. That is a real semantic event and the diff is where it
  gets reviewed;
- **`lexicon.meta.json`** - every file's `rows`, `bytes` and `sha256` move
  whenever its content does, and the counters move with the population.

Read the diff. Nothing else in the repository is a better record of what a
source change actually did.

Do NOT stage `datasets/lexicon/cache/`, `datasets/lexicon/sources/` (except the
one committed authored file) or `datasets/corpus/`. All three are gitignored,
and `git status --porcelain` should show no `.db` and no raw source before you
commit.

## Regenerating the fixture expectation

CI cannot run the real rebuild, so the integration gate runs all four stages
over the committed byte-exact fixture slices and byte-compares the result
against `datasets/fixtures/lexicon-expected/`. When a stage's output changes
legitimately - a new source, a new authored batch, a classifier rule - that
expectation is regenerated by one command and never hand-edited:

```
python -m yen_tamizh_backend.scripts.rebuild_lexicon_fixture --workspace <scratch-dir>
```

Then read the diff: a change there is a change to what the pipeline produces.

## See also

- [../architecture/lexicon/pipeline.md](../architecture/lexicon/pipeline.md) - the four stages and why each is shaped as it is.
- [add-a-lexicon-source.md](add-a-lexicon-source.md) - registering a source as a data change.
- [enrich-the-lexicon.md](enrich-the-lexicon.md) - authoring the one source that is written rather than acquired.
- [../architecture/lexicon/word-hood.md](../architecture/lexicon/word-hood.md) - the eight signals and the classifier cascade.
- [../concepts/lexicon.md](../concepts/lexicon.md) - the vocabulary.
