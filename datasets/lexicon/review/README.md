# Lexicon review reports (regenerated, not committed)

**Last Updated**: 2026-08-16

This directory is where the REVIEW stage writes the state of the lexicon out as
something a person can read. The files are **gitignored** - they run to hundreds
of megabytes and every one of them is a pure function of the store - and only
this README is committed.

They are deliberately NOT under [`../cache/`](../cache/). That directory is
machine state one pipeline stage hands to the next, and a reader who finds a
work queue in it reasonably concludes the file is uninteresting and safe to
delete. These are working material: the residue a classifier could not place and
the queue an enrichment pass works through.

Regenerate them with:

```bash
cd backend
python -m yen_tamizh_backend.wordsmith.review
```

REVIEW reads the store's derived zone and writes nothing back, so running it can
never change a verdict. It is not part of the `pipeline` sequence for that
reason - it is a report an operator asks for, not a step that produces the next
stage's input. Run ENRICH first if the store has been re-staged since the last
run; a report over a stale derived zone describes a lexicon that no longer
exists.

## The files

| file | what it holds | why it is worth reading |
| --- | --- | --- |
| `unclassified.ndjson` | every surface the cascade reached no verdict about, with all eight word-hood signals beside it | the residue, sortable by any signal - this is where a missing rule shows up as a cluster |
| `not-a-word.ndjson` | every surface the `notAWord` precondition refused, with WHICH clause refused it | the reason is recomputed by the classifier's own function, so a reviewed reason can never disagree with a published verdict |
| `enrichment-queue.ndjson` | surfaces still unclassified that a tier-1 meaning source nevertheless describes | over a CURRENT derived zone this file is EMPTY, and its emptiness is the point: a tier-1 source that describes a surface also attests it, so it has an entry and the cascade always reaches a verdict. A row here means a source described something it did not list - or that the derived zone is stale |
| `headwords-without-a-meaning.ndjson` | surfaces the classifier ruled servable that carry no Tamil definition | the queue that IS the work. Each row carries the evidence an authoring pass would work FROM |

## See also

- [`../../../docs/architecture/lexicon/pipeline.md`](../../../docs/architecture/lexicon/pipeline.md) - the four stages and where REVIEW sits beside them.
- [`../../../docs/how-to/rebuild-the-lexicon.md`](../../../docs/how-to/rebuild-the-lexicon.md) - running the stages singly or as a pipeline.
- [`../../../docs/architecture/lexicon/word-hood.md`](../../../docs/architecture/lexicon/word-hood.md) - the signals and the cascade these reports expose.
