# Generate the daily bank

**Last Updated**: 2026-08-13

How today's puzzles get made, and what to do when you need to bake, re-bake, or
back-fill a day. The generator is the DAILY PUZZLE ENGINE: it consumes a per-Game
derived wordlist and produces committed puzzle files.

```
datasets/corpus/**  ->  master wordlist  ->  per-Game sets  ->  daily puzzles
   (raw sources)         (add-a-corpus-      (add-a-derived-     (this page)
                          source.md)          wordlist.md)
```

The engine never re-ingests, re-ranks, or re-derives. Refreshing the words is the
two pages above; this page never changes because they did.

## The one command

```
python -m yen_tamizh_backend.scripts.generate_today
```

It bakes the run date (today, UTC) plus the look-ahead in
[`../../config/daily-generator.json`](../../config/daily-generator.json), and
writes:

- `frontend/public/bank/<YYYY>/<YYYY-MM-DD>.json` - one day's playlist, a
  [`puzzle-file`](../../schemas/puzzle-file.schema.json);
- `frontend/public/bank/index.json` - the manifest of every baked day, a
  [`bank-index`](../../schemas/bank-index.schema.json).

Pass a date to re-bake or back-fill one:

```
python -m yen_tamizh_backend.scripts.generate_today 2026-08-13
```

It prints one pipeline event per generated puzzle plus a `bank.updated` line, as
JSON on stdout:

```
{"data": {"date": "2026-08-13", "gameId": "anagram", "outputPath": "frontend/public/bank/2026/2026-08-13.json"}, "level": "info", "name": "puzzle.generated", "src": "generate_today"}
```

Commit whatever it wrote. The bank lives inside `frontend/public/` so the game
reads it same-origin from its own bundle and it works offline - there is no CDN
and no runtime backend (Holy Law #1).

## Re-running is safe

A day is a pure function of its date: selection is a seeded shuffle over the
derived wordlist, so re-running any date rewrites the same bytes and leaves the
working tree clean. That is the determinism Oracle, and it is also the hand-edit
gate - `backend/tests/test_generate.py` re-bakes the committed bank and compares
it byte for byte, so an edited day file fails the suite.

Two consequences worth knowing:

- **A word is not served twice.** Words already used on OTHER days in the bank
  are skipped. The target day's own file is ignored while collecting them, which
  is exactly what keeps a re-run idempotent instead of self-poisoning.
- **Order matters across days, not within a run.** Days are baked oldest first,
  so back-filling a date that sits BEFORE existing days can change what those
  later days would pick if they were re-baked. Bake forward.

## The knobs

`config/daily-generator.json` is the engine's registry, validated against
[`../../schemas/daily-generator.schema.json`](../../schemas/daily-generator.schema.json):

| Knob | Meaning |
| --- | --- |
| `bankDir` | Where the bank is written. Inside `frontend/public/` so it ships with the bundle. |
| `daysAhead` | How many days past the run date to bake. |
| `games[].wordlist` | The derived set this Game draws from - the engine's ONLY word input. |
| `games[].attempts` | Tries before a puzzle ends honestly (no purchase, no timer). |
| `games[].timeLimitSec` | `0` means untimed; time pressure belongs to a Mode, not to the mechanic. |
| `games[].reveal` | How many leading ezhuthu start already placed. `0` keeps the scramble whole. |
| `games[].difficulties` | Ezhuthu-length bands mapped to difficulty slugs. |
| `games[].hints` | Each offered hint's `kind`, `cost`, and Tamil `template` over the row's honest fields (`{firstEzhuthu}`, `{length}`). |

How many items a day holds and which Games fill them are NOT here - they are
`daily.playlistLength` and `daily.mix` in
[`../../config/app-config.json`](../../config/app-config.json), because the shell
reads the same numbers. A mix that does not sum to the playlist length is an
error, not a short day. How many hints a day bakes is `hints.perGame` there too,
so the switch the shell reads is the switch the generator obeys.

## Why the bank is baked days ahead

The cron runs on UTC; a player's calendar day is their own. A phone in Chennai is
on tomorrow's date five and a half hours before UTC agrees, and a player who has
been offline since yesterday still needs today. Baking a window of days removes
that whole class of "no puzzle today" - it costs a few KB, and the game reads the
newest day at or before the player's local date, never a future one.

The trade is that a determined player can read the next few days out of the
bundle. That matters in a game with a leaderboard; this one has none.

## In CI

[`../../.github/workflows/daily.yml`](../../.github/workflows/daily.yml) runs the
same command at 00:05 UTC (and on demand), then commits
`frontend/public/bank/**` only if something changed. The push to `main` triggers
the existing deploy workflow; the daily job never deploys anything itself.

## See also

- [add-a-derived-wordlist.md](add-a-derived-wordlist.md) - the layer above: the words this engine draws from.
- [`../concepts/modes.md`](../concepts/modes.md) - what Daily is, and the streak it ticks.
- [`../architecture/contracts/schemas.md`](../architecture/contracts/schemas.md) - the `daily-generator`, `puzzle-file`, and `bank-index` decisions.
- [`../../CLAUDE.md`](../../CLAUDE.md) - Holy Law #1 (static-first), #6 (no hardcoding), section 11 (schema versioning).
