# How to add a derived wordlist

**Last Updated**: 2026-08-16

A derived wordlist is one Game's SERVED slice of the published
[lexicon](../concepts/lexicon.md) - the words its generator is allowed to build
puzzles from. Adding one is a **data change plus a re-run**, never a code
rewrite, and never a change to the lexicon above it or to the daily puzzle
engine below it.

```
datasets/lexicon/**  ->  published lexicon  ->  per-Game sets  ->  daily puzzles
  (the wordsmith pipeline)                        (this page)      (Row 13)
```

The lexicon is everything the pipeline knows: every surface any source ever
showed us, with its class and every fact asserted about it. A derived wordlist is
the far smaller set a player is actually asked to spell. **PRESENT and SERVED are
different populations**, and the selection knobs on this page are the whole
difference.

Derived sets are **build artifacts**. They are regenerated in full by one
command, they are a pure function of the lexicon plus the registry, and they are
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
    "wordClasses": ["headword"],
    "minLength": 5,
    "maxLength": 5,
    "minAttestations": 2,
    "minTier1Attestations": 1,
    "minFrequency": 1,
    "requireMeaning": true,
    "maxWords": 2000
  }
}
```

Every knob except `maxWords` is **required**. The defaults ARE the design
decision, so a registry entry that forgot to say what it serves fails to
validate rather than quietly serving everything.

Then append a `changelog` entry and set `version` to today, like every schema-
backed file ([`../../CLAUDE.md`](../../CLAUDE.md) section 11).

Two sets may not share a `gameId` or an `out` path: a collision would mean one
Game's wordlist silently overwrites another's.

### 2. Re-run the rebuild

```
python -m yen_tamizh_backend.scripts.rebuild_wordlists
```

ONE command regenerates ALL derived sets, so none is left cut from a stale
lexicon. It prints what each set kept, which gate stopped the rest, how many of
its rows share their tiles with another served row, and its length and
familiarity spread:

```
anagram: rowsKept=32310 outsideLength=63443 outsideClass=1076
  belowAttestations=17776 belowFrequency=38020 withoutMeaning=10812 capped=0
  sharedFanOut=514 lengths[3:5965 4:10287 5:9484 6:6574]
  strata[q1:8078 q2:8077 q3:8078 q4:8077]
  -> datasets/wordlists/derived/anagram.json
```

Commit the regenerated artifacts with the registry edit.

## The four serving gates

These are the admission tests. They are config, not code, because how much
evidence a word needs before a player is asked to spell it is a tunable
game-balance judgement (Holy Law #6). Their design rationale - and the player
tolerance they are tuned against - is in
[`../concepts/difficulty-and-scoring.md`](../concepts/difficulty-and-scoring.md).

| Knob | Meaning |
| --- | --- |
| `wordClasses` | An **allow-list** of lexicon word classes. Never a deny-list, so a word the classifier could not place cannot reach a player by omission. The contract narrows what may ever appear here, so `properNoun`, `unclassified`, `notAWord`, `suspectedTypo`, `sandhiArtifact`, `boundStem`, `inflected` and `loanword` are not one config edit away from a player. |
| `minAttestations` | How many word-hood authorities must have called this surface a word. |
| `minTier1Attestations` | How many of those must have been a DICTIONARY rather than a bare list. Two bare wordlists agreeing is not evidence - a spellchecker list is several times the size of the largest dictionary and co-occurs with nearly any orthographically legal string. |
| `minFrequency` | The absolute floor on how often the word occurs. A dictionary word appearing zero times in modern Tamil is a museum piece; this gate does the most work of the four. |
| `requireMeaning` | Keep only words carrying a Tamil meaning, so the game can say what the answer meant once the player has solved it. |

Two more knobs shape the set without judging a word:

| Knob | Meaning |
| --- | --- |
| `minLength` / `maxLength` | Bounds on a word's **ezhuthu** count, not its code points. |
| `maxWords` | Cap on the committed artifact; `null` means uncapped. A derived set lives in git, so an uncapped one is an unbounded commit. The cap trims from the RARE end, because rows come out most frequent first. |

There is deliberately **no category knob**. Only about 1,290 lexicon rows carry a
category, so gating admission on one would cut the served set to roughly a
thousand rows and re-create the scarcity the lexicon exists to remove. A category
is a selection dimension for a themed round, never an admission test.

## The ledger, and why it has one bucket per gate

The generated file opens with its source, selection, and counters, so `head`
tells you what a run did:

- `source` - the exact lexicon the rows came from: the META document's path, its
  `version`, its `sha256`, and its published row count. One digest still pins a
  partitioned input, because `lexicon.meta.json` itself carries the sha256 of
  every published file. There is deliberately no wall-clock stamp anywhere in a
  derived file; a timestamp would make two runs over one lexicon produce
  different bytes, and git already records when a file changed.
- `selection` - the knobs that produced it, so a reviewer reading a diff can see
  which one moved.
- `counters` - the reconciliation ledger, which the contract itself enforces:
  `lexiconRows - outsideLength - outsideClass - belowAttestations -
  belowFrequency - withoutMeaning - capped == rowsKept == len(words)`.

Every published lexicon row is accounted for under exactly one heading, in the
order the identity is read, and a row that fails several gates is charged to the
first that stopped it. That is what makes "this gate does the most work" a
measurement rather than an assertion - and what stops a selection bug from
quietly dropping words.

`outsideClass` is read off the lexicon's own partition table rather than counted
line by line: selection is an allow-list, so the derived layer opens only the
files of the classes it serves.

## Every row carries two derived signals

`frequencyStratum` is which quarter of THIS SET the row's frequency puts it in, 1
being the most familiar. It is the second axis of difficulty, and it is computed
over the served rows after every gate and after the cap - a quartile over
millions of lexicon surfaces would say nothing about the words a player is
offered.

`anagramFanOut` is how many rows of THIS set share its ezhuthu multiset, counting
itself. A word whose tiles spell nothing else in the set carries `1`, never `0`.

Both are recorded, never used to admit or reject, and the contract **recomputes
both on read** (`GameWordlist` validates every row against the set's own ordering
and grouping), so a stale or hand-edited value cannot survive a rebuild.

What fan-out buys is a decent answer to a player who rearranges the tiles into a
different real word: a Game can say "that is a word, but not today's" instead of
a flat red X, and a player who formed real Tamil and was told they were simply
wrong concludes the game cheated. The signal is thin by construction - Tamil has
247 ezhuthu against English's 26 letters, so multiset collisions are rare. That
is a fact about the language, and it is exactly why fan-out is a signal rather
than a filter; see
[`../architecture/contracts/schemas.md`](../architecture/contracts/schemas.md)
for the rule this replaced and what it cost.

## How the files are resolved

The derived layer reads `lexicon.meta.json` and opens the partition files that
document's own table names. It **never globs** the published directory: a glob
would serve whatever happened to be on disk, including a file the meta document
does not vouch for, which is exactly how a class the selection never named would
reach a player. A `wordClasses` entry naming a class the lexicon does not publish
is a loud error, because a selection that silently serves nothing looks identical
to one that works.

## When you DO need code

Exactly one case: a Game whose selection needs a predicate these knobs cannot
express - "words sharing at least three ezhuthu with another entry", say, for a
crossword's interlock. Add the predicate and its knob to
`backend/yen_tamizh_backend/wordsmith/derive.py` and
`backend/yen_tamizh_backend/contracts/derived_wordlists.py`. Everything else -
another length range, another evidence threshold, another cap - is the two steps
above. This is the same line the lexicon layer draws at an unseen source FORMAT.

## See also

- [`../concepts/lexicon.md`](../concepts/lexicon.md) - the layer above: what a word class, an attestation and a frequency mean.
- [`../concepts/difficulty-and-scoring.md`](../concepts/difficulty-and-scoring.md) - why the gates are set where they are, and the two-axis difficulty they feed.
- [generate-the-daily-bank.md](generate-the-daily-bank.md) - the layer below: turning these words into committed puzzles.
- [`../architecture/contracts/schemas.md`](../architecture/contracts/schemas.md) - the contract pipeline and the `derived-wordlists` / `game-wordlist` decisions.
- [`../concepts/games.md`](../concepts/games.md) - the Games these sets feed.
- [`../../CLAUDE.md`](../../CLAUDE.md) - Holy Law #3 (contracts before logic), #6 (no hardcoding), section 11 (schema versioning).
