# How to add a derived wordlist

**Last Updated**: 2026-08-19

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
different populations**, and the selection knobs on this page - plus the two
serving rules and the curated deny-list below them - are the whole difference.

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

Every knob except `maxWords`, `categories` and `pos` is **required**. The
defaults ARE the design decision, so a registry entry that forgot to say what it
serves fails to validate rather than quietly serving everything. The last two are
the SELECTION DIMENSIONS below, and they are optional because absent has to mean
"not applied".

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
anagram: rowsKept=31055 outsideLength=63443 outsideClass=1076
  outsideCategories=0 outsidePos=0
  belowAttestations=17776 belowFrequency=38020 withoutMeaning=10812
  obscene=4 participial=1065 denylisted=186 capped=0
  sharedFanOut=510 lengths[3:5845 4:9995 5:9055 6:6160]
  strata[q1:7764 q2:7764 q3:7764 q4:7763]
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

Three admission tests are not knobs and are not per-set: the two `servingRules`
and the curated deny-list, all of which run after every gate above. See
[the serving rules](#the-serving-rules-a-participle-and-an-obscenity) and
[the deny-list](#the-deny-list-and-how-to-grow-it) below.

## The two selection dimensions, and the themed set they cut

`categories` and `pos` are a different kind of knob. Each keeps the rows whose
own set-valued column INTERSECTS the one named - a row tagged both `birds` and
`animals` is inside a selection naming either - and each is charged to its own
ledger bucket (`outsideCategories`, `outsidePos`).

**Neither may ever gate admission.** Both are optional and absent means the
dimension is not applied at all. Of 162,361 published headwords only 2,569 carry
any category, so a set that named one by accident would collapse from tens of
thousands of rows to a few hundred - re-creating exactly the scarcity the lexicon
exists to remove. How far `pos` reaches over the served set is likewise a
measurement, not an assumption.

A set that DOES name one is a **themed set**: the same serving gates as the
ordinary set, narrowed. The theme narrows; it never relaxes. That is what lets a
themed day be drawn without a second look at whether its words were servable.

```json
{
  "gameId": "themed-nature",
  "out": "datasets/wordlists/derived/themed-nature.json",
  "selection": {
    "...": "the ordinary set's gates, unchanged",
    "categories": ["animals", "birds", "flowers", "insects", "nature"]
  }
}
```

Three rules keep a theme worth having:

- **A theme is a GROUP of categories, never one.** The single categories are
  tiny: over the published headwords, `nature` is 144 rows, `birds` 97,
  `reptiles` 17, `amphibians` 2 - and that is before the gates. A single-category
  Daily at three words a day would run out in days. `themed-nature` unions ten of
  them and keeps 429 rows after the gates, which is 143 themed days.
- **A theme must EXCLUDE almost everything.** The floor is 90 percent of the
  servable set; `themed-nature` excludes 98.7 percent. A player told the round is
  about nature can name five plausible candidates before seeing a tile, and that
  is only true because the tag rules almost everything out. A tag like "nouns"
  excludes nothing, narrows nothing, and is not a theme.
- **The tags are DATA.** The categories named here are the normalized values of
  `categoryAliases` in
  [`../../config/lexicon-sources.json`](../../config/lexicon-sources.json), so
  widening a theme, renaming a tag, or folding a new source's labels into an
  existing theme is a config edit and a re-run. Growing a theme is likewise data
  - another category source, or authored categories on already-attested
  headwords - and neither costs code.

A themed set is not drawn by itself: the Game that uses it registers it under
`games[].themes` in
[`../../config/daily-generator.json`](../../config/daily-generator.json), and the
day loop runs it on the days it can fill a whole playlist. See
[generate-the-daily-bank.md](generate-the-daily-bank.md).

The Tamil name a player reads for a theme is copy in
[`../../config/copy.json`](../../config/copy.json), keyed by the theme's
`copySlug`. A category name is never baked into a dataset.

## The serving rules: a participle and an obscenity

Two exclusions need no curation, because the published data already carries the
signal. They live under `servingRules` in
[`../../config/derived-wordlists.json`](../../config/derived-wordlists.json),
hang off the REGISTRY for the same reason `denylistPath` does, and are charged
after every gate above and before the deny-list.

### `participialSuffixes` - a peyareccham is not a headword

Tamil derives an adjective from almost any noun or verb, so `mozhi` (language)
gives `mozhiyaana` (linguistic) and `thavaRu` (fault) gives `thavaRillaadha`
(faultless). Those are INFLECTED forms; a dictionary lists the stem. Word-hood's
`inflected` rule cannot reach them - it labels inflection from the two collected
verb-form lists, which is direct evidence and therefore only as wide as those
lists - so a participial adjective they happen not to contain arrives with a
tier-1 listing, a clean shape, and nothing to demote it. Four of them were dealt
as Daily answers.

A suffix is written the way Tamil actually builds one, because the ending is not
a fixed string: the suffix rewrites the stem's last ezhuthu when it lands.

| Field | Meaning |
| --- | --- |
| `tail` | The literal ezhuthu the surface ends in. |
| `linkVowel` | The matra the ezhuthu immediately BEFORE `tail` must carry - the `aa` of every `-aana` form, the `u` of every `-ulla` one. This is what makes the match a claim about morphology rather than about a run of letters. |
| `minStemEzhuthu` | How many ezhuthu must remain in front of the whole pattern. Without it the rule takes `vaan` (sky) and `kolla`. |

Three endings ship, and between them they removed **1,065** of the 32,122 rows
the set served on 2026-08-19: `-aana` (721 rows), `-aadha` (218, including every
`-illaadha` compound), and `-ulla` (124). Every match was read by hand and none
is a surface a Tamil dictionary lists as a headword.

Two shapes were measured and REJECTED, and they are the guard rails for the next
suffix somebody proposes:

- **Requiring the stripped stem to be an attested headword.** It sounds stricter
  and is weaker. Sandhi rewrites the stem, so undoing it means guessing which of
  several spellings the writer started from, and each miss keeps a participle on
  the board: the guess left 186 of the 1,063 served matches there, `mozhiyaana`
  and `thavaRillaadha` among them.
- **The `-iya` ending.** It matches 202 served rows, and they include `indhiya`,
  `dhesiya`, `ilakkiya`, `pudhiya`, `siRiya`, `periya`, `ariya` and `iniya` -
  ordinary vocabulary a dictionary lists. Deleting real words is the worse
  defect, so the ending is not registered.

### `obscenityMarkers` - the source already said so

A daily puzzle for casual players must not deal an obscenity as the answer, and
nothing has to be curated to prevent it: Tamil lexicography writes the judgement
into the gloss as a usage label. The rule refuses any row whose FIRST sense
carries one of the named labels.

Sense zero only, and the marker is the whole LABEL rather than its stem. Both
narrowings were measured:

- a bare `aabaasa` substring matches 12 served rows and exactly one of them is an
  obscenity - the other eleven are words like `aruvaruppu` (disgust) whose gloss
  merely DISCUSSES coarse speech;
- reading every sense rather than sense zero adds `vanmai` (harshness) and
  `theettu`, whose twelfth and second senses discuss it.

The two labels that ship - `aabaasa-c-chol` and `vasai-c-chol` - remove **four**
rows between them, and the removal is on SERVING only: each word keeps its
published class and its published facts, exactly as a denied word does.

## The deny-list, and how to grow it

One exclusion is not derivable from the lexicon at all, and it runs last: the
curated list in
[`../../config/served-denylist.json`](../../config/served-denylist.json),
schema-validated against
[`../../schemas/served-denylist.schema.json`](../../schemas/served-denylist.schema.json)
and named by the registry's `denylistPath`. It applies to EVERY set, because
what makes a word unservable is true of every Game.

The lexicon knows what a word IS; it does not know what makes a PUZZLE. Tamil's
highest-frequency surfaces are its grammar, and since frequency is one axis of
difficulty they land in the EASY band - the band a player meets most. A Daily
whose answer is "and" or "this" is not a word puzzle. Beside them sit the
personal names and newspaper mastheads a news corpus makes frequent, each with a
real dictionary sense, so nothing upstream can tell them from vocabulary.

```json
{
  "note": "why this list exists, and which words were reviewed and KEPT",
  "functionWords": [{ "word": "...", "reason": "quotative particle" }],
  "properNouns": [{ "word": "...", "reason": "given name" }]
}
```

Adding a word is a data edit plus the same re-run:

1. Put it in `functionWords` if it is grammar rather than vocabulary, or in
   `properNouns` if a corpus made a name frequent. The split is not decoration -
   the first judgement is stable for the life of the language, the second
   follows whichever corpora are staged, so a reviewer needs to know which
   argument an entry is making before deciding whether it still holds.
2. Write a short `reason`. It is never rendered; it is for the reviewer deciding
   whether the NEXT proposed entry belongs, which is the only thing between a
   curated list and a list that grows by feel. Where the word carries a real
   dictionary sense that is not what its frequency counts, say so.
3. Keep both arrays sorted by `word` and deduped - across each other as well as
   within themselves. The contract refuses anything else.
4. Append a `changelog` entry, set `version` to today, and re-run
   `rebuild_wordlists`. `denylisted` in the ledger says how many words the list
   ALONE removed.

Three rules keep the list honest:

- **Whole words only.** The match is exact, never a prefix or a substring.
  Tamil agglutinates, so a stem match would take dozens of real words per entry.
- **The lexicon is untouched.** Every denied word is real Tamil, is attested,
  and stays in `datasets/lexicon/`. The exclusion is on SERVING, so a dictionary
  lookup, a frequency study, or a future Game where the player RECOGNISES rather
  than produces a spelling loses nothing.
- **Name the word, never a rule.** A part-of-speech filter was measured and
  rejected: `pos` is a UNION across 21 sources, so `appa` (father) and `arasu`
  (government) both carry `interjection`, and the rule would have deleted real
  vocabulary. The `note` lists the 27 words reviewed and deliberately KEPT -
  read it before adding anything that merely looks grammatical.

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
  `lexiconRows - outsideClass - outsideCategories - outsidePos - outsideLength -
  belowAttestations - belowFrequency - withoutMeaning - obscene - participial -
  denylisted - capped == rowsKept == len(words)`.

Every published lexicon row is accounted for under exactly one heading, in the
order the identity is read, and a row that fails several gates is charged to the
first that stopped it. That is what makes "this gate does the most work" a
measurement rather than an assertion - and what stops a selection bug from
quietly dropping words. The two dimension buckets read first, so a themed
ledger says how far the theme reaches and then what each gate removed from
inside it; on an ordinary set both are 0. `obscene` and `participial` read after
every automatic gate, `obscene` first of the two because it is the graver
refusal; `denylisted` reads LAST, so its number is what hand curation ALONE
removed once everything derivable had run.

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
another length range, another evidence threshold, another cap, another theme -
is the two steps above. This is the same line the lexicon layer draws at an
unseen source FORMAT.

## See also

- [`../concepts/lexicon.md`](../concepts/lexicon.md) - the layer above: what a word class, an attestation and a frequency mean.
- [`../concepts/difficulty-and-scoring.md`](../concepts/difficulty-and-scoring.md) - why the gates are set where they are, and the two-axis difficulty they feed.
- [generate-the-daily-bank.md](generate-the-daily-bank.md) - the layer below: turning these words into committed puzzles.
- [`../architecture/contracts/schemas.md`](../architecture/contracts/schemas.md) - the contract pipeline and the `derived-wordlists` / `game-wordlist` / `served-denylist` decisions.
- [`../concepts/games.md`](../concepts/games.md) - the Games these sets feed.
- [`../../CLAUDE.md`](../../CLAUDE.md) - Holy Law #3 (contracts before logic), #6 (no hardcoding), section 11 (schema versioning).
