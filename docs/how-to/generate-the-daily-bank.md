# Generate the daily bank

**Last Updated**: 2026-08-21

How today's puzzles get made, and what to do when you need to bake, re-bake, or
back-fill a day. The generator is the DAILY PUZZLE ENGINE: it consumes a per-Game
derived wordlist and produces committed puzzle files.

```
datasets/lexicon/**  ->  published lexicon  ->  per-Game sets  ->  daily puzzles
  (raw sources in)       (add-a-lexicon-       (add-a-derived-     (this page)
                          source.md)            wordlist.md)
```

The engine never re-ingests, re-ranks, or re-derives. Refreshing the words is the
two pages above; this page never changes because they did.

## The one command

```
python -m yen_tamizh_backend.scripts.generate_today
```

It bakes the run date (today, UTC) plus the look-ahead in
[`../../config/daily-generator.json`](../../config/daily-generator.json), skips
any of those dates the bank already holds, and writes:

- `frontend/public/bank/<YYYY>/<YYYY-MM-DD>.json` - one day's playlist, a
  [`puzzle-file`](../../schemas/puzzle-file.schema.json);
- `frontend/public/bank/index.json` - the manifest of every baked day, a
  [`bank-index`](../../schemas/bank-index.schema.json).

Pass a date to back-fill from one:

```
python -m yen_tamizh_backend.scripts.generate_today 2026-08-13
```

It prints one pipeline event per generated puzzle plus a `bank.updated` line, as
JSON on stdout:

```
{"data": {"date": "2026-08-13", "gameId": "anagram", "outputPath": "frontend/public/bank/2026/2026-08-13.json"}, "level": "info", "name": "puzzle.generated", "src": "generate_today"}
```

The `bank.updated` line lists both what it `generated` and what it `skipped`, so
a cron tick that had nothing new to bake says so instead of looking idle.

Commit whatever it wrote. The bank lives inside `frontend/public/` so the game
reads it same-origin from its own bundle and it works offline - there is no CDN
and no runtime backend (Holy Law #1).

## A published day is never rewritten

**A date whose file already exists is skipped.** A day is a pure function of its
date AND of the derived wordlist it drew from, so the moment that wordlist
changes, re-running the generator would produce a DIFFERENT puzzle for a day
that has already shipped - including, on any given night, a day a player is
part-way through. That is the same class of break as a save that no longer
loads: the bank the player already has must keep meaning what it meant.

The cron re-runs the generator over the whole look-ahead window every night, so
without the guard every wordlist change would silently rewrite up to a week of
published days. With it, a run bakes only the dates the bank does not have yet,
and new words reach players through the days baked from here on.

Two consequences worth knowing:

- **The index is rebuilt from disk on every run**, skipped days included, so it
  can never fall behind the days it lists.
- **Published days are history, not a rebuildable artifact.** Once the wordlist
  moves, no command reproduces yesterday's bytes. `backend/tests/test_generate.py`
  therefore asserts that a re-run over the committed bank moves nothing, rather
  than that it reproduces it.

### `--rebake`, the escape hatch

```
python -m yen_tamizh_backend.scripts.generate_today 2026-08-13 --rebake
```

Rewrites the dates in the run even if they already exist. Use it when changing
published days is the point - a bad word to pull, a payload shape to migrate -
and never in the cron. Review the resulting diff before committing: every day it
touches is a day some player may already be playing.

**The line to draw is TODAY, not the last commit.** A day at or before today's
date is played or in play and is history; a day after it has never been served
and is safe to rewrite. Row 12a rebaked 2026-08-17 onward - thirteen days -
because the lexicon underneath them had changed, and left 2026-08-13 through
2026-08-16 byte-for-byte alone. A test that spans the bank must DERIVE that span
from disk rather than pin it, or it goes red the night the cron adds a day.

## Some days are themed

Three unrelated anagrams are a list; three that share a theme are a round. That
is the Daily's variety mechanism, and it costs no new engine - a theme is one
more derived set, cut on the `categories` dimension
([add-a-derived-wordlist.md](add-a-derived-wordlist.md)), registered under the
Game that draws it.

A date runs a theme when BOTH hold:

1. The cadence allows it. `themeEveryNDays` is counted on the date's own day
   number, so which dates qualify is a pure function of the date - no phase knob,
   no reference to when the bank was first baked, and the same answer on every
   machine. `0` turns themed days off.
2. One registered theme can fill the WHOLE day from its own wordlist, without
   repeating a word the bank has already served, with every difficulty band it
   needs non-empty and every row it draws actually BUILDABLE by the Game holding
   it. Every Game in `daily.themedGames` must register that same theme, or the
   day would be partly off-theme while announcing a theme.

That second condition is why a themed day has its OWN ring. A theme's set is a
few hundred rows, which is thin enough that a Game can register it and still be
unable to fill a slot from it - measured over `themed-nature`'s 429 rows, the
crossword solver builds four boards from the 28 easy rows and none at all from
the 14 medium ones. If the ordinary ring decided a themed day's shape, widening
it to five Games would have turned every themed day off in silence. So
`daily.games` says what an ordinary day holds and `daily.themedGames` says what a
themed day holds, and the themed ring may be SHORTER than the playlist: an
ordinary day claims variety of Games and never repeats one, a themed day claims
its words belong together and repeats a Game rather than reaching for one the
theme cannot fill.

Otherwise the day is ordinary. **A theme that cannot fill the day is skipped, not
padded** - a round whose third word is off-theme has broken the only promise the
round made. Which theme runs on a date with more than one candidate is seeded by
the date, and a theme that cannot fill that date does not block another that can.

A themed day records its theme's `copySlug`, never its Tamil name:

```json
{ "date": "2026-08-30", "theme": "theme-nature", "items": [ ... ] }
```

The label lives in [`../../config/copy.json`](../../config/copy.json), which the
shell already reads. A baked label would be copy frozen into a build artifact,
correctable only by a rebake of a day that has already shipped. An ordinary day
carries no `theme` key at all.

A theme's own wordlist is cut with the SAME serving gates as the ordinary set, so
a themed day can never serve a word an ordinary day could not - the theme
narrows the selection, it never relaxes it.

## Re-running is safe

A date is a pure function of its date, its wordlist, and the rest of the bank it
is baked into, so baking one twice from the same inputs writes the same bytes and
leaves the working tree clean. That is the determinism Oracle, and it is what
makes `--rebake` predictable rather than a roll of the dice.

Three more consequences:

- **A word is not served twice - EVERY word, not just the one the day picked.**
  The ledger is every word a baked payload asks the player for: a scramble's
  answer, a search board's targets, a crossword's entries, a ladder's rungs. It
  holds what the bank served on other days AND what this day's earlier boards
  already asked for, so no two boards - on one morning or two months apart - ask
  for the same word. The target day's own file is ignored while collecting the
  across-day half, which is exactly what keeps a re-bake idempotent instead of
  self-poisoning.
- **A board short of fresh words repeats rather than shipping short.** Three
  Games draw more words than the day loop picked, and each degrades in the shape
  its own mechanic allows: a search board tops its companions up from words the
  bank served, a ladder steps onto a served rung only when no fresh neighbour can
  finish the climb, and a crossword - whose answers interlock, so it cannot
  degrade one word at a time - re-solves its whole mask with the ledger set
  aside. A five-word grid holding four words would be a broken board and a cron
  that fails is worse than either. Measured over 180 baked days, the ladder is
  the only Game the graph ever forces: 75 climbs clean, 7 repeating one rung,
  and an exhaustive search finds an all-fresh climb for none of those 7.
- **Order matters across days, not within a run.** Days are baked oldest first,
  so back-filling a date that sits BEFORE existing days reads the later days'
  answers as already served, and re-baking a whole WINDOW in place moves the
  ledger under each day as it goes. Bake forward: delete the future days you
  want rewritten and let the guard bake them fresh, rather than forcing a window
  with `--rebake`.

## The knobs

`config/daily-generator.json` is the engine's registry, validated against
[`../../schemas/daily-generator.schema.json`](../../schemas/daily-generator.schema.json):

| Knob | Meaning |
| --- | --- |
| `bankDir` | Where the bank is written. Inside `frontend/public/` so it ships with the bundle. |
| `daysAhead` | How many days past the run date to bake. |
| `themeEveryNDays` | How often the Daily MAY run a themed round, counted on the day number so it needs no phase. `0` turns themed days off. |
| `games[].wordlist` | The derived set this Game draws from - the engine's ONLY word input on an ordinary day. |
| `games[].themes` | The themed sets this Game may run a WHOLE day from: each a `wordlist` path and the `copySlug` naming its Tamil label in `config/copy.json`. Empty means this Game never runs a themed day. |
| `games[].attempts` | Tries before a puzzle ends honestly (no purchase, no timer). |
| `games[].timeLimitSec` | `0` means untimed; time pressure belongs to a Mode, not to the mechanic. |
| `games[].reveal` | How many leading ezhuthu start already placed. `0` keeps the scramble whole. Read by the anagram; a Game that places nothing ignores it. The wordle pins it at `0` deliberately - the first ezhuthu is the strongest fact on that board and its own ladder refuses to sell it. |
| `games[].choiceCount` | How many ezhuthu the choice bank holds, for the Games that offer one. Defaults to 8. It is a balance number, not a layout preference: there is no Tamil keyboard, so the bank is how a hidden ezhuthu is entered at all, and its size IS the odds a player who knows nothing still guesses right inside `attempts`. The wordle never reads it: its keyboard is a composer over the closed 247-ezhuthu inventory, which is a fact about Tamil rather than a per-puzzle knob. |
| `games[].gridRows` / `games[].gridCols` | The board a Game that HIDES words in a grid lays them out on. Both default to 8, and the 8 is a phone measurement: a cell has to hold the widest ezhuthu legibly at 36px, and eight of those with a 4px gutter is 316px against the 328px a 360px screen leaves after its margins. Rows follow columns because a square is the only shape whose diagonals are as long as its sides. Games with no grid never read either. |
| `games[].difficulties` | The difficulty bands, each bounding TWO axes: an ezhuthu-length range and a `maxStratum` familiarity ceiling. A day deals its slots these bands in order and draws frequency-stratified within one; a word no band claims is never drawn. See [`../concepts/difficulty-and-scoring.md`](../concepts/difficulty-and-scoring.md). The wordle's three bands are all the same width and separate on familiarity alone, which is the only honest axis left once a Game pins its length. |
| `games[].dailyRank` | Where this Game sits on the DAY's ramp. A day's Games are dealt in ascending rank, so the lightest board opens the day on its easiest band and the heaviest closes it on its hardest. Defaults to 0. It is a declared design order rather than a derived one, because what makes a board heavy is how many answers it asks for AND whether the player can lose it, and no single column says both. |
| `games[].difficulties[].blanks` | How many ezhuthu the band HIDES, for the Games whose mechanic hides letters. Defaults to 1, and must be less than the band's `minLength` or its shortest word would have nothing showing. |
| `games[].difficulties[].targets` | How many WORDS the band hides, for the Games whose board holds more than one. Defaults to 1, which is what every other Game deals. On a search grid it is the main difficulty dial, because length is not one there - a longer word covers more cells and is easier to spot. A band asking for more cells than the grid has, or for words longer than its longest line, fails to validate. |
| `games[].difficulties[].grid` | The crossword's MASK - one string per row, `.` for a square a word runs through and `#` for a blocked one. It is the crossword's difficulty dial for the same reason `targets` is the search board's: what makes a grid harder is how many answers it asks for and how much of each one the crossings give away. It is a band's own field because those two things are exactly what a band may change, and it is validated before anything fills it - rectangular, every run fillable by the band's own words, every length the band admits really occurring, every entry crossing another, and the whole board connected. `gridRows` and `gridCols` are read as the ceiling it must fit inside. Games with no crossings never read it. |
| `games[].hints` | Each offered hint's `kind`, `cost`, and Tamil `template` over the fields THAT Game may sell. `{category}` and `{meaning}` are common; `{firstEzhuthu}` is the anagram's alone. A missing-letters board has already printed every ezhuthu it is not hiding, and a wordle player can buy the same fact with a guess that answers five other positions at the same time. The word-search sells NOTHING - it prints the words it is asking for, so every rung would name a fact on the screen - and its list is empty. A template naming a field outside its Game's vocabulary fails the bake. |

How long a day is and which Games fill it are NOT here - they are
`daily.playlistLength`, `daily.games` and `daily.themedGames` in
[`../../config/app-config.json`](../../config/app-config.json), because the shell
reads the same numbers. `daily.games` is a RING and a day takes the window that
starts at its own date, so a ring shorter than the playlist is refused by the
contract rather than dealing an ordinary day the same Game twice. How many hints
a day bakes is `hints.perGame` there too, so the switch the shell reads is the
switch the generator obeys.

## Why the bank is baked days ahead

The cron runs on UTC; a player's calendar day is their own. A phone in Chennai is
on tomorrow's date five and a half hours before UTC agrees, and a player who has
been offline since yesterday still needs today. Baking a window of days removes
that whole class of "no puzzle today" - it costs a few KB, and the game reads the
newest day at or before the player's local date, never a future one.

The trade is that a determined player can read the next few days out of the
bundle. That matters in a game with a leaderboard; this one has none.

## Adding a Game to the bake

Three things, and none of them is the day loop:

1. A derived set for it - a registry entry in
   [`../../config/derived-wordlists.json`](../../config/derived-wordlists.json)
   plus a re-run of `rebuild_wordlists` (see
   [add-a-derived-wordlist.md](add-a-derived-wordlist.md)).
2. A `games` entry here, naming that wordlist and the Game's own knobs.
3. A payload builder under `backend/yen_tamizh_backend/generate/`, registered in
   `daily.BUILDERS` as a pair: how to INDEX one served set (the only place a
   Game may learn about words other than the one it is building), and how to
   turn one row into that Game's validated payload. A Game that needs to know
   nothing about the other served words registers a `prepare` that returns
   nothing, which is what the wordle does; a Game whose board holds SEVERAL
   words takes the row the loop picked as its anchor and draws the rest from
   the index, which is what the word-search and the crossword do. Every builder
   is handed the day's LEDGER as its last argument - every word the bank has
   already asked for - and a builder that draws extra words must draw them
   against it, with a documented fallback for the case where it cannot. A
   builder that can be handed a row it cannot use raises
   `generate.Unbuildable`, and the loop deals the next candidate from the same
   band rather than failing the day - which today only the crossword needs,
   because only an interlocked board can refuse a word.

Five Games are registered this way today, and none of them cost an edit to
`puzzle-file` or to the day loop.

Then it can be named in `daily.games`. A `gameId` in either ring with no
registered builder fails loudly rather than baking a silently short day. Adding
it to `daily.themedGames` is a SEPARATE decision and needs its own evidence: a
themed day only runs when every Game on that ring registers the same theme AND
can build from it, so a Game added there without a theme it can actually fill
turns themed rounds off rather than failing anything.

## In CI

[`../../.github/workflows/daily.yml`](../../.github/workflows/daily.yml) runs the
same command at 00:05 UTC (and on demand), then commits
`frontend/public/bank/**` only if something changed. Under the guard, "something
changed" now means one new day at the far end of the look-ahead window, never a
rewrite of the days already there. The push to `main` triggers the existing
deploy workflow; the daily job never deploys anything itself.

## See also

- [add-a-derived-wordlist.md](add-a-derived-wordlist.md) - the layer above: the words this engine draws from.
- [`../concepts/modes.md`](../concepts/modes.md) - what Daily is, and the streak it ticks.
- [`../architecture/contracts/schemas.md`](../architecture/contracts/schemas.md) - the `daily-generator`, `puzzle-file`, and `bank-index` decisions.
- [`../../CLAUDE.md`](../../CLAUDE.md) - Holy Law #1 (static-first), #6 (no hardcoding), section 11 (schema versioning).
