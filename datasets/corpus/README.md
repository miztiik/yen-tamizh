# Corpus sources (raw, not committed)

**Last Updated**: 2026-08-17

This directory holds raw Tamil word sources the lexicon pipeline streams. The
bytes are **gitignored** - they are hundreds of megabytes of third-party word
lists - and only the published lexicon under [`../lexicon/`](../lexicon/) is
committed.

The directory predates the lexicon layer: it was the retired corpus ingest's
source root, and the eleven sources already sitting here kept their paths when
the registry moved. New sources land under `datasets/lexicon/sources/<id>/`.

## Layout

One directory per registered source id, matching the `path` that source declares
in [`../../config/lexicon-sources.json`](../../config/lexicon-sources.json):

```
datasets/corpus/<source-id>/source.<ext>
```

## Repopulating

Every source's `origin` is recorded in the registry, and the exact bytes each run
consumed are recorded as `bytes` + `sha256` in the acquisition ledger - so a
later run can prove it read the same file. Fetch each `origin` back into its
`path` and re-run the pipeline
([`../../docs/how-to/rebuild-the-lexicon.md`](../../docs/how-to/rebuild-the-lexicon.md)).

Sources whose `origin` is a `yen-tamizh_OLD/...` path come from the predecessor
repository; sources whose `origin` is a URL can be fetched directly.

## See also

- [`../lexicon/sources/README.md`](../lexicon/sources/README.md) - the acquisition ledger: every source, its bytes, and its sha256.
- [`../../docs/how-to/add-a-lexicon-source.md`](../../docs/how-to/add-a-lexicon-source.md) - adding a source as a data change.
- [`../README.md`](../README.md) - what `datasets/` is for.
