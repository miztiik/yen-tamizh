# How to add a derived wordlist

**Last Updated**: 2026-08-14

A derived wordlist is one Game's slice of the ranked master corpus - the words
its generator is allowed to build puzzles from. Adding one is a **data change
plus a re-run**, never a code rewrite, and never a change to the corpus above it
or to the daily puzzle engine below it.

```
datasets/corpus/**  ->  master wordlist  ->  per-Game sets  ->  daily puzzles
   (raw sources)         (add-a-corpus-source.md)  (this page)     (Row 13)
```

Derived sets are **build artifacts**. They are regenerated in full by one
command, they are a pure function of the master plus the registry, and they are
never hand edited - a hand edit fails `backend/tests/test_derive.py`, which
re-derives the committed file and compares it byte for byte.

## The two steps

### 1. Add an entry to `config/derived-wordlists.json`

The registry is schema-validated against
[`../../schemas/derived-wordlists.schema.json`](../../schemas/derived-wordlists.schema.json),
so a typo fails the run instead of being silently ignored.

```json
{
  "gameId": "wordle",
  "out": "datasets/wordlists/derived/wordle.json",
  "note": "Why these knobs, in one sentence a designer can argue with.",
  "selection": {
    "minLength": 5,
    "maxLength": 5,
    "bands": ["common", "mid"],
    "requireValidWordFinal": true,
    "maxWords": 2000
  }
}
```

Then append a `changelog` entry and set `version` to today, like every schema-
backed file ([`../../CLAUDE.md`](../../CLAUDE.md) section 11).

Two sets may not share a `gameId` or an `out` path: a collision would mean one
Game's wordlist silently overwrites another's.

### 2. Re-run the rebuild

```
python -m yen_tamizh_backend.scripts.rebuild_wordlists
```

ONE command regenerates ALL derived sets, so none is left cut from a stale
master. It prints what each set kept, why the rest went, how many of its rows
share their tiles with another served row, and its length spread:

```
anagram: rowsKept=17313 outsideLength=13386 outsideBand=17329
  invalidWordFinal=1972 capped=0 sharedFanOut=93
  lengths[3:3305 4:5286 5:5044 6:3678]
  -> datasets/wordlists/derived/anagram.json
```

Commit the regenerated artifacts with the registry edit.

## The selection knobs

The knobs are config, not code, because which lengths make a good puzzle and
which words a player actually knows are tunable game-balance numbers
(Holy Law #6):

| Knob | Meaning |
| --- | --- |
| `minLength` / `maxLength` | Bounds on a word's **ezhuthu** count, not its code points. |
| `bands` | Which `freqBand` values to keep. `common` + `mid` are the ranks a Tamil speaker knows; `rare` is the tail of the ranked list - a dictionary lookup rather than a guess. |
| `requireValidWordFinal` | Keep only words that END the way a Tamil word ends. |
| `maxWords` | Cap on the committed artifact; `null` means uncapped. A derived set lives in git, so an uncapped one is an unbounded commit. |

Rows are emitted in master rank order (most common first), which is a total
order because `freqRank` is unique - so a Game wanting an easier slice can take
it off the front, and the bytes are reproducible without a tie-break.

## The anagram fan-out signal

Every emitted row carries `anagramFanOut`: how many rows of THIS set share its
ezhuthu multiset, counting itself. A word whose tiles spell nothing else in the
set carries `1`, never `0`.

It is recorded, never used to admit or reject. What it buys is a decent answer
to a player who rearranges the tiles into a different real word: a Game can say
"that is a word, but not today's" instead of a flat red X, and a player who
formed real Tamil and was told they were simply wrong concludes the game
cheated.

It is counted over the SERVED rows - after every filter and after the cap -
because a partner nobody is served cannot be the word a Game offers back. The
contract recomputes it on read (`GameWordlist` validates each row against the
set's own grouping), so a stale count cannot survive a rebuild or a hand edit.

The signal is thin by construction: Tamil has 247 ezhuthu against English's 26
letters, so multiset collisions are rare. On the anagram set, 93 of 17,313 rows
have any partner at all. That is a fact about the language, and it is exactly
why fan-out is a signal rather than a filter - see
[`../architecture/contracts/schemas.md`](../architecture/contracts/schemas.md)
for the rule this replaced and what it cost.

## The word-final rule

`requireValidWordFinal` keeps only words that end the way a Tamil word ends: on
a vowel-bearing ezhuthu, or on one of the eight mei consonants that may close a
word. Everything else is corpus noise of two kinds - a sandhi artifact, where
the euphonic doubling belonging to the NEXT word was scraped onto this one, and
a transliterated loanword that kept its final stop. Neither is a word a Tamil
speaker would accept as a puzzle ANSWER. On the anagram set the rule removes
1,972 rows.

It is the only content-quality net the served set has, so it stays on until word
hood is classified from dictionary attestation rather than from orthography.

The table of legal word-final ezhuthu lives in the ezhuthu library
(`backend/yen_tamizh_backend/ezhuthu/word_shape.py`) because it is a fact about
Tamil letters; only the switch is config, because whether a Game wants it is a
selection decision.

## When you DO need code

Exactly one case: a Game whose selection needs a predicate these knobs cannot
express - "words sharing at least three ezhuthu with another entry", say, for a
crossword's interlock. Add the predicate and its knob to
`backend/yen_tamizh_backend/corpus/derive.py` and
`backend/yen_tamizh_backend/contracts/derived_wordlists.py`. Everything else -
another length range, another band mix, another cap - is the two steps above.
This is the same line the corpus layer draws at an unseen source FORMAT.

## Checking the result

The generated file opens with its own source, selection, and counters, so `head`
tells you what a run did:

- `source` - the exact master the rows came from: `path`, `version`,
  `generatedAt`, `sha256`, `rows`. There is deliberately no wall-clock stamp on
  the derived file; a timestamp would make two runs over one master produce
  different bytes, and git already records when a file changed.
- `selection` - the knobs that produced it, so a reviewer reading a diff can see
  which one moved.
- `counters` - the reconciliation ledger, which the contract itself enforces:
  `masterRows - outsideLength - outsideBand - invalidWordFinal - capped ==
  rowsKept == len(words)`. Every master row is accounted for under exactly one
  heading, so a selection bug cannot quietly drop words.

## See also

- [add-a-corpus-source.md](add-a-corpus-source.md) - the layer above: growing the master list.
- [generate-the-daily-bank.md](generate-the-daily-bank.md) - the layer below: turning these words into committed puzzles.
- [`../architecture/contracts/schemas.md`](../architecture/contracts/schemas.md) - the contract pipeline and the `derived-wordlists` / `game-wordlist` decisions.
- [`../concepts/games.md`](../concepts/games.md) - the Games these sets feed.
- [`../../CLAUDE.md`](../../CLAUDE.md) - Holy Law #3 (contracts before logic), #6 (no hardcoding), section 11 (schema versioning).
