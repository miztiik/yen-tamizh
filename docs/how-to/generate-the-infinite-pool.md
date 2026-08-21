# Generate the Infinite pool

**Last Updated**: 2026-08-21

How the endless Mode's puzzles get made. There is no runtime generator (Holy Law
#1), so "endless" is spelled out in advance: every board the Infinite stream can
ever deal is baked into the bundle before it ships.

```
datasets/lexicon/**  ->  published lexicon  ->  per-Game sets  ->  the pool
  (raw sources in)       (add-a-lexicon-       (add-a-derived-     (this page)
                          source.md)            wordlist.md)
```

The boards are built by the SAME registry the [daily bank](generate-the-daily-bank.md)
uses, so a Game gets a pool the moment it is registered - there is no second
generator per Game and nothing on this page to change when one is added.

## The one command

```
python -m yen_tamizh_backend.scripts.generate_infinite
```

It bakes a pool for every Game in `daily.games` and writes, per Game:

- `frontend/public/pool/<gameId>/<NNNNN>.json` - one board per file, the same
  payload shape the Daily bakes into a day's item;
- `frontend/public/pool/<gameId>/index.json` - the manifest, a
  [`pool-index`](../../schemas/pool-index.schema.json).

Bake one Game while iterating:

```
python -m yen_tamizh_backend.scripts.generate_infinite --game wordle
```

It prints one `pool.generated` line per Game and a closing `pool.updated`, as
JSON on stdout:

```
{"data": {"byBand": {"easy": 100, "hard": 100, "medium": 100}, "bytes": 163162, "gameId": "anagram", "indexBytes": 13812, "items": 300, "outputPath": "frontend/public/pool/anagram"}, "level": "info", "name": "pool.generated", "src": "generate_infinite"}
```

## When to re-run it

Whenever an INPUT moves: a rebuilt derived wordlist, a changed difficulty band, a
new Game in the ring, or a different `poolPerBand`. Unlike the bank there is no
re-bake guard and there is no cron - a day is a promise about a DATE that a
player may be part-way through, while a pool is content, and the run that changes
it is the run that meant to.

A Game's directory is REBUILT rather than merged, so boards left over from a
larger previous pool are removed rather than shipped unindexed.

Re-running with unchanged inputs rewrites the same bytes: a pool is seeded by its
Game's name, never by a date, so item `00042` of a Game stays the same board
across releases. That is also the hand-edit gate - a board edited by hand is
reverted by the next run - and `backend/tests/test_infinite.py` is what proves
the committed bytes are the generator's own.

## The two knobs

Both live in [`../../config/daily-generator.json`](../../config/daily-generator.json):

| Knob | What it decides |
| --- | --- |
| `poolDir` | Where the pool lands. Under `frontend/public/` so the game reads it same-origin from its own bundle. |
| `poolPerBand` | How many boards to bake per Game per difficulty band. A CEILING, not a quota. |

`poolPerBand` is a ceiling because a band can run out: the word-ladder's hard
band stops at 65 of 100, since its reachability graph holds only that many
four-rung climbs it has not already used. A short band is the honest outcome -
the alternative is padding the pool with a board it has already dealt under
another id, which is the one thing an anti-repeat stream must not do.

## What it costs

At the shipped `poolPerBand` of 100: **1,765 boards, 1,371,555 bytes of boards
and 81,384 of index**. None of it is precached and none of it is fetched in bulk
- a player downloads one 13.8 KB index (1.3 KB compressed) to start a stream and
then 387 to 1,565 bytes a board. The reasoning behind the number, and the
alternatives measured against it, live in
[../concepts/modes.md](../concepts/modes.md).

## See also

- [../concepts/modes.md](../concepts/modes.md) - the Infinite Mode and its anti-repeat rule.
- [generate-the-daily-bank.md](generate-the-daily-bank.md) - the same builders, framed by a calendar.
- [add-a-derived-wordlist.md](add-a-derived-wordlist.md) - the layer above, where the words come from.
- [../architecture/runtime/stack-and-bundle.md](../architecture/runtime/stack-and-bundle.md) - why the pool is runtime-cached and never precached.
