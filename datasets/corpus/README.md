# Corpus sources (raw, not committed)

**Last Updated**: 2026-08-13

This directory holds the raw Tamil word sources the corpus ingest streams. The
bytes are **gitignored** - they are hundreds of megabytes of third-party word
lists, and only the derived artifact
[`../wordlists/master/words_ranked.json`](../wordlists/master/words_ranked.json)
is committed.

## Layout

One directory per registered source id, matching the `path` of that source in
[`../../config/corpus-sources.json`](../../config/corpus-sources.json):

```
datasets/corpus/<source-id>/source.<ext>
```

## Repopulating

Every source's `origin` is recorded in the registry, and the exact bytes each run
consumed are recorded as `bytes` + `sha256` in the `provenance` block at the top
of the generated master wordlist - so a later run can prove it read the same
file. Fetch each `origin` back into its `path` and re-run:

```
python -m yen_tamizh_backend.corpus.ingest
```

Sources whose `origin` is a `yen-tamizh_OLD/...` path come from the predecessor
repository; sources whose `origin` is a URL can be fetched directly.

## See also

- [`../../docs/how-to/add-a-corpus-source.md`](../../docs/how-to/add-a-corpus-source.md) - adding a source in three steps.
- [`../README.md`](../README.md) - what `datasets/` is for.
