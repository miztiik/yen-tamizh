# Word-hood

**Last Updated**: 2026-08-15

How the pipeline decides what KIND of thing a Tamil surface is. The vocabulary -
what a `wordClass` is, why observation is not attestation, why `length` counts
ezhuthu - is defined once in [../../concepts/lexicon.md](../../concepts/lexicon.md);
the four stages that build the artifact are in [pipeline.md](pipeline.md). This
page is about the evidence and the verdict, and it does not restate either.

## The problem this layer exists to solve

The corpus layer before it had one quality test - frequency - and frequency
answers a different question. `kuzhandhaigalai` (a case-marked plural of
"children") is high-frequency and is not a headword; `asura` is low-frequency
and is not a word at all, only the stem of one. **Frequency and word-hood are
independent axes**, so no threshold on the first can ever be a filter for the
second, and a served wordlist cut on frequency will keep serving fragments and
inflections forever.

So word-hood is measured on its own evidence: eight named SIGNALS, combined into
exactly one `wordClass` per surface.

## Eight signals, in two rows of work

Five are LOOKUPS - a table or a store query. Three need a model or a search.
They are built separately because a linguistic table, a statistical model, an
all-pairs search and a classifier have four different risk profiles, and a row
that bundles them has no honest gate.

| Signal | What it asks | What it catches | Landed |
| --- | --- | --- | --- |
| `attested` | does an authority list this as a headword? | the dictionary verdict | Row 7 |
| `orthotactic` | is this a shape Tamil builds? | sandhi artifacts, transliterations, fragments, non-Tamil | Row 7 |
| `breadth` | how many distinct sources observed it? | a typo appears in one source, a word in many | Row 7 |
| `nannulValid` | did a Nannul-rules spellchecker pass it? | a grammar judgement already on disk | Row 7 |
| `knownVerbForm` | is it a collected inflected verb form? | inflection by direct evidence, not by inference | Row 7 |
| `ngram` | how likely is this ezhuthu sequence? | an unlikely sequence is a typo | Row 8 |
| `neighbour` | how close is the nearest headword? | a near-miss on a real word is a misspelling | Row 8 |
| `zipf` | does its frequency fit its rank? | a diagnostic, and deliberately the weakest | Row 8 |

`wordhood` is a NAME-KEYED MAP over those names rather than a fixed-arity
struct, which is what lets the two rows land independently without either
shipping a half-populated object. In the build-time store the same eight are one
COLUMN each; a signal a row has not computed yet is NULL, and NULL means **not
measured**, which is a different fact from a measured zero.

## The five exact signals

### `attested` - the dictionary verdict

Binary. One if any source whose `role` is `authority` or `authored` carried a
`headword` fact for the surface, zero otherwise. A frequency list observing a
surface a million times cannot make it one, and `formEvidence` sources can only
ever assert the NEGATIVE - a bulk list of inflected forms proves a surface is
not a headword and never that it is.

It is one signal of eight and never the verdict on its own. A 1930s lexicon
rejects `kambyuttar` (computer), and it would be wrong to.

### `orthotactic` - Tamil's own rules about word shape

Tamil constrains where each ezhuthu may stand. Three rules, each a fact about
the script rather than a preference any Game holds, and all three live in
`backend/yen_tamizh_backend/ezhuthu/word_shape.py` beside the word-final set
they generalise:

- **which ezhuthu may BEGIN a word** - any of the twelve uyir, and the twelve
  uyirmei forms of the ten consonants a Tamil word may open on. 132 of the 247
  are legal openings. A surface opening on a bare mei, on the aytham, or on one
  of the other eight consonants is a loanword or a fragment;
- **which ezhuthu may END a word** - a vowel-bearing ezhuthu, or one of eight
  mei. This is where the derived layer's `requireValidWordFinal` rule goes: a
  fact about Tamil asked ONCE here, rather than a preference each Game re-asks;
- **which mei may be followed by which consonant** - a cluster table stated over
  the three consonant classes (vallinam, mellinam, idaiyinam) the way the
  grammar states it. A mei followed by an independent vowel is refused outright,
  because Tamil writes a vowel after a consonant as a matra ON that consonant -
  that shape is a compound scraped without its space.

The signal is `1.0` minus the configured weight of each rule the surface breaks,
so a clean word scores 1 and one that breaks everything scores 0. A surface
holding anything that is not an ezhuthu - Latin, a digit, a space - scores zero
outright rather than by accumulated weights: it is not badly-shaped Tamil, it is
not Tamil.

**Grantha is recorded, never penalised.** The five grantha consonants were
borrowed to write Sanskrit and foreign sounds and are not among the 247, so
carrying one is positive evidence of a LOANWORD rather than a defect. The two
borrowed compounds, `ksha` and `shri`, need no entry of their own - each is a
sequence over that same set. `WordShape.hasGrantha` is the fact, and
`granthaPenalty` in config is what it costs, defaulted to zero.

A grantha letter can still fail the rule it actually breaks. `shri` opens on a
bare mei and no native Tamil word does, so its opening is illegal AND it carries
grantha - two independent facts, and keeping them apart is the point. A low
orthotactic score WITH grantha is a loanword; the same score WITHOUT one is
junk, and a single collapsed number could not tell them apart.

### `breadth` - how many sources saw it

The count of DISTINCT sources that observed the surface, stored raw rather than
normalised: it is read as a count downstream, and normalising it would make a
threshold depend on how many sources happen to be registered today.

Over the real store, 5,144,667 of 6,249,903 surfaces (82.3 percent) were seen by
exactly one source, and 330,984 by three or more. A real word appears across
independent sources; a typo appears in one.

### `nannulValid` - a grammar judgement already in hand

Binary membership in the spellcheck wordlist, whose 355,275 words were validated
by a Nannul-rules Tamil spellchecker. It costs a membership lookup and answers
the grammar-compliance question directly, which is the whole reason to prefer it
over inferring the same thing (Holy Law #8).

### `knownVerbForm` - inflection by evidence

Binary membership in the two collected verb-form lists - 1,461,494 and 19,249
inflected forms. This is the single largest classification win available: it
labels `inflected` by DIRECT evidence rather than by morphological inference,
and it is free. Over the real store it marks 1,428,258 surfaces, 22.9 percent of
everything staged.

Inferring inflection from morphological rules instead was rejected: 1.46M
hand-collected forms are already on disk, and inferring what you can look up is
a dependency and an error source bought for nothing.

## The three inexact signals

These three cannot be answered by a lookup. One needs a model fitted over the
corpus, one needs a search across every headword, and one needs the whole
frequency distribution before it can say anything about a single word.

All three read the same dictionary, and it is narrower than "every attested
headword": it is every attested headword that is **wholly Tamil** - every unit
of it an ezhuthu. See [the training set is filtered](#the-training-set-is-filtered-and-decision-1-is-the-reason)
below for why, and what it costs.

### `ngram` - how likely the ezhuthu sequence is

A character-level model where the CHARACTER is the ezhuthu. Tamil writes a vowel
after a consonant as a mark ON that consonant, so a code-point model would be
learning the spelling of a syllable rather than the sequence of syllables, and
the sequence is the thing the language actually constrains.

The score is the geometric mean of the per-ezhuthu probabilities - the
reciprocal of the model's perplexity on that word - so it lands in `(0, 1]` like
`orthotactic`, a three-ezhuthu word and a ten-ezhuthu one are comparable, and it
points the same way every other signal points: higher is more word-like.
Perplexity itself is unbounded and grows as a word gets WORSE, which is the
opposite polarity to the other seven and nothing a shared threshold could read.

It complements `orthotactic` rather than replacing it, and the difference is the
point. The letter rules say which shapes Tamil ALLOWS; the model says which
shapes Tamil actually USES. A surface can be perfectly legal and still deeply
improbable, and legal-but-improbable is exactly what a typo looks like.

The model is recomputed from the staged zone on every run and is never a
committed artifact. It is a pure function of that zone, so a committed copy
would be a second thing to keep in sync for no benefit.

### `neighbour` - how close the nearest real word is

The reciprocal of the ezhuthu edit distance to the nearest headword: one when a
headword is a single ezhuthu away, a half at two, zero when none is within
`maxEditDistance`. A surface that is one edit from a real word and is not itself
a real word is a misspelling of it.

**Distance is measured in ezhuthu, never in code points**, and the two really do
disagree. `கா` is one ezhuthu and two code points; `கக` is two ezhuthu and two
code points. A code-point metric puts them a single edit apart and would call
them near-misses; they are two whole syllables apart and no player would. It
cuts the other way too: `கா` and `பி` differ in both their consonant and their
vowel, so code points say two edits and ezhuthu says one, which is what it is.
Every word is therefore re-encoded so that one ezhuthu is one character, after
which an ordinary string edit distance IS an ezhuthu distance.

#### The query set is pruned, and that changes how the column reads

The signal's only consumer is the `suspectedTypo` verdict, so three kinds of
surface are not asked about at all: one an authority attested, one that is a
collected verb form, and one that `pruneBreadth` or more independent sources
agree on. None of them can be what the signal is looking for.

A skipped surface keeps a NULL, and **NULL is not zero here**. Zero means "we
looked as far as `maxEditDistance` and found nothing"; NULL means nobody asked.
A reader that treats the two the same will conclude that every attested headword
is maximally far from every other word, which is the opposite of true.

### `zipf` - whether a frequency fits its rank, and the weakest of the eight

Rank every surface by how often it was observed, fit `log10(f) = a - s*log10(r)`
through the corpus's own rank-frequency plot, and store how far each surface
falls off that line. The exponent is FITTED rather than assumed to be one,
because a scraped corpus is not a natural-language sample and pretending it obeys
the textbook constant would put the model's error into every residual.

It is explicitly a diagnostic. Frequency and word-hood are independent axes -
that is the founding observation of this whole layer - so a signal derived
purely from frequency cannot be strong evidence about word-hood, and the
classifier is free to weight it near zero. It is recorded because it is nearly
free once the frequencies are already in the store, and because "far off the
line" is a real hint about a scrape artifact that got counted a few times.

A surface with no counted occurrences gets a NULL, not a zero. A dictionary is a
word LIST rather than a count, so its surfaces arrive observed with a count of
zero - and zero occurrences is not a measured frequency, so there is no rank for
it to sit off. Storing zero would claim it sits exactly ON the line.

### The training set is filtered, and decision 1 is the reason

The plan says the model is trained "only on `authority` headwords - never on the
scraped corpus, or it learns the typos it is meant to detect". That was written
before anyone had measured the headwords: **128,648 of the 589,862 attested
headwords, 21.8 percent, contain a unit that is not an ezhuthu at all** - a Latin
transliteration, a digit, a compound scraped without its space.

Training an ezhuthu model on a set that is a fifth not-Tamil does the exact thing
decision 1 forbids, only more quietly: it teaches the model that transliterations
and spaceless compounds are normal Tamil, which inverts the signal on precisely
the surfaces it exists to flag. The training set is therefore the intersection -
attested AND wholly Tamil, **461,214 words** - and the same filter builds the
neighbour dictionary, because a dictionary of "real words" holding a scrape
artifact will happily report that some other scrape artifact is one edit from a
real word.

The filter is not a new judgement. It is `WordShape.hasNonTamil`, the same test
`orthotactic` already uses to score such a surface zero outright, so there is one
definition of "is this Tamil" in the codebase rather than two.

## What the signals actually measured

Over the real staged store - 6,249,903 distinct surfaces, 18 enabled sources:

| Signal | Measured | Marked positive | Share of measured |
| --- | ---: | ---: | ---: |
| `attested` | 6,249,903 | 589,862 | 9.4% |
| `orthotactic` > 0 | 6,249,903 | 5,600,039 | 89.6% |
| `breadth` >= 1 | 6,249,903 | 6,249,903 | 100% |
| `nannulValid` | 6,249,903 | 355,275 | 5.7% |
| `knownVerbForm` | 6,249,903 | 1,428,258 | 22.9% |
| `ngram` | 6,249,903 | 6,249,903 | 100% |
| `neighbour` | 4,115,457 | 2,582,136 | 62.7% |
| `zipf` | 4,551,338 | 1,864,878 | 41.0% |

The two columns whose MEASURED count is below the population are the two that
leave a deliberate NULL. `neighbour` was asked of 4,115,457 surfaces - the prune
skipped 2,134,446 - and of those asked, 1,143,387 have a headword one ezhuthu
away, 1,438,749 have one at two, and 1,533,321 have none within two. `zipf` is
measured for the 4,551,338 surfaces somebody actually counted.

The prune is a **1.52x** cut, not the 2.5-3x the plan predicted. The prediction
was sized against 3,967,009 surfaces; the store holds 6,249,903, and the three
exclusions are the same absolute sets whichever total you divide into. The
decision still pays for itself - 2.1M queries removed at no loss - but a reader
sizing the `suspectedTypo` queue should size it against 4.1M.

`ngram` marks every surface positive because its floor is the smoothing mass
rather than zero: it is a probability, and no sequence has probability zero under
a smoothed model. What separates surfaces is the MAGNITUDE, not the sign, which
is the one respect in which it does not read like the seven others.

The orthotactic score falls in five buckets under the committed weights, and the
shape of that distribution is the layer's first honest look at its own corpus:

| Score | Surfaces | What broke |
| ---: | ---: | --- |
| 1.00 | 4,057,164 | nothing |
| 0.75 | 1,236,084 | one of the ending or the clusters |
| 0.50 | 224,727 | the opening, or both of the other two |
| 0.25 | 82,064 | the opening plus one more |
| 0.00 | 649,864 | not Tamil at all, or every rule |

The three inexact signals cost more to compute and are worth stating with their
own inputs, because each number is a decision someone can check:

| What | Measured |
| --- | ---: |
| Attested headwords | 589,862 |
| ... of which wholly Tamil, and so the dictionary | 461,214 |
| ... dropped as not-Tamil | 128,648 (21.8%) |
| Distinct ezhuthu in the dictionary | 307 |
| Trigrams the model actually saw | 198,966 |
| Deletion-index entries at `maxEditDistance` 2 | 13,248,728 |

## Why a scored classification and not a filter

Word-hood CLASSIFIES; it does not delete. Every surface keeps its row, its
signal map and one `wordClass`, so a misclassification costs a re-run of one
stage rather than a re-ingest over hundreds of megabytes of gitignored bytes.
That is the same bargain the whole lexicon makes - **ingest enriches, selection
filters** - applied to the verdict itself.

It also keeps the interesting case reachable. A surface that is orthotactically
clean, broad across sources, and still UNATTESTED is not junk: that profile is a
real modern word the dictionaries missed. A filter would delete it. A
classification routes it onward.

## Why inflected forms are KEPT but never SERVED

Tamil is agglutinative, so most of what a scraper sees is inflected, and
`knownVerbForm` alone marks nearly a quarter of the store. Deleting those rows
would throw away the single most useful asset the corpus has: an inflected form
is exactly what a guess-ACCEPTANCE list is made of, because a player typing a
Tamil word will type an inflected one. It is also the input a future lemmatizer
needs.

But it is never an ANSWER. Selection is an ALLOW-LIST over `wordClass` values,
never a deny-list, so a class nobody named - including `unclassified` - can
never reach a player by omission.

## Design rationale

- **The letter rules are contract; only the weights are config.** Which ezhuthu
  may open a word is a fact about Tamil, in the same category as the `wordClass`
  set and the part-of-speech vocabulary, so it lives in the ezhuthu library and
  is tested exhaustively over the whole 247-ezhuthu inventory. What a broken
  rule COSTS is a tunable judgement, so it lives in `config/wordhood.json` and
  never as a Python literal (Holy Law #6). The line is the same one the corpus
  registry draws between a reader and a knob. (User + Fowler.)
- **The table was authored from the grammar and then reconciled against the
  real store.** Running it over every attested headword rejected 2.1 percent of
  multi-attested openings, 1.4 percent of endings and 1.3 percent of cluster
  sets - and every rejection inspected was a Sanskrit cluster, an English
  transliteration, or a compound scraped without its space. A linguistic table
  nobody measured is a table nobody can trust. (Fowler.)
- **The signal is a score, not a bit.** Three defects are not interchangeable: a
  surface that cannot even OPEN like a Tamil word is a loanword or a fragment,
  while one that merely ends wrong is usually a sandhi artifact. A classifier
  that wants to tell those apart needs them priced apart, which is why the
  opening carries the heaviest default weight. (Fowler.)
- **`granthaPenalty` defaults to zero, and it is still a knob.** Pricing grantha
  as damage would tell the classifier the opposite of what the fact means, so
  the default is neutral - but leaving the number out of config entirely would
  put a judgement in a Python constant where nobody reviews it. (User + Fowler.)
- **Membership signals name their source in config, and ENRICH checks the name
  against the store.** WHICH list carries the Nannul verdict is a fact about the
  inventory we happen to have acquired, not about the language, so it is config.
  A misspelled id would otherwise produce a column of zeros, and a column of
  zeros reads exactly like a signal that honestly found nothing - so the stage
  refuses to run rather than reporting a silent all-negative. (Fowler.)
- **A membership signal reads BOTH emissions.** A source is registered as a word
  list, and whether its extractor emitted an observation, a fact, or both is a
  detail of its shape - the two verb-form sources emit observations only, the
  spellchecker emits both. A signal that read one table would silently answer
  zero for the other kind. (Fowler.)
- **The dictionary is attested AND wholly Tamil, which is narrower than the
  plan said.** Decision 1's stated intent is that the model must never learn
  the typos it exists to detect. Once 21.8 percent of the attested headwords
  turned out to hold a Latin letter, a digit or a scraped compound, following
  the LETTER of "only authority headwords" would have served that intent worse
  than following its INTENT. Both counts are reported, so the size of the filter
  is visible rather than implied. (Row 8, on Row 7's measurement.)
- **The index is a candidate GENERATOR and every candidate is verified.** The
  deletion neighbourhood is stored as one sorted array of `crc32(variant) << 20
  | word id`, because a dictionary of several million strings costs more than a
  gigabyte in object headers before it holds a single character. A 32-bit hash
  collides occasionally; a collision costs one wasted distance computation and
  can never produce a wrong answer, because the answer is the VERIFIED distance
  rather than the fact of a match. (Carmack.)
- **The one optional dependency cannot change an output.** `rapidfuzz` is
  declared in `[project.optional-dependencies]` and never in the project's
  dependencies, so CI installs the pipeline without it and takes the pure Python
  verification path. Both paths return the same number and a test asserts it -
  otherwise a store enriched on a developer's machine and one enriched in CI
  could disagree, and the row's determinism Oracle would be a lie.
  (Carmack, Holy Law #8.)
- **The scoring pass is deterministic whatever the scheduling.** A surface's
  score is a pure function of the surface and the index; chunks come back in the
  order they went out; and the minimum over a candidate set is taken with no
  early exit that could depend on which candidate was inspected first. Scoring
  with one process and with twelve writes the same column, and a test asserts
  that too. (Carmack + Fowler.)

## Rejected alternatives

| Option | Why rejected | Authority |
| --- | --- | --- |
| Dictionary attestation alone as the verdict | A 1930s lexicon rejects `kambyuttar`, and it would be wrong to. Attestation is one signal of eight. | User |
| A frequency floor as the quality test | Frequency and word-hood are independent axes - one is high-frequency and not a headword, the other low-frequency and not a word. This is the exact defect of the pipeline being replaced. | User |
| Infer verb inflection from morphological rules | 1.46M hand-collected forms are already on disk. Inferring what you can look up is a dependency and an error source bought for nothing. | Fowler, Holy Law #8 |
| Bundle all eight signals in one row | Four different risk profiles - a linguistic table, a statistical model, an all-pairs search, a classifier. | Fowler |
| A ninth `grantha` signal column | The published `wordhood` map and the store both carry eight names, and minting a ninth would change a contract to persist a fact that is a pure function of the surface - recomputable by the classifier for free from `WordShape.hasGrantha`. | Fowler |
| A pair-by-pair cluster table over all 324 mei-consonant pairs | The grammar states the rule over three consonant CLASSES, and a pair-by-pair table is the same facts with 324 more places to be wrong. | Fowler |
| A BK-tree instead of a deletion neighbourhood | Not a peer option at this query volume - roughly ten thousand distance computations per query across millions of queries is tens of thousands of CPU-hours. Categorically non-viable. | Carmack |
| Naive all-pairs edit distance | Hundreds of billions of comparisons; the row would never finish. | Fowler |
| `symspellpy` off the shelf | Code-point oriented, and ezhuthu-level distance is the whole point - subclassing its internals is larger than the deletion generation it would replace. | Carmack |
| Committing the trained n-gram model | It is a pure function of the staged zone, so a committed copy is a second thing to keep in sync for no benefit. | Fowler |
| Storing perplexity rather than its reciprocal | Unbounded, and it gets LARGER as a word gets worse - the opposite polarity to every other signal, and nothing a threshold could be shared across. | Row 8 |
| Code-point edit distance | Two words that differ by a whole syllable differ by several code points, and two that merely share a vowel sign look adjacent. Both errors are real and they point opposite ways. | Fowler |
| Querying every surface instead of pruning | The signal's only consumer is `suspectedTypo`, and an attested headword cannot be one. Skipping them costs nothing and is the difference between a pass that finishes and one that does not. | Carmack |
| Zero rather than NULL for a surface nobody queried | "We looked and found nothing" and "nobody asked" are different facts, and the store already has a way to keep them apart. Collapsing them would make every attested headword look maximally far from every real word. | Row 8 |
| A fixed Zipf exponent of one | A scraped corpus is not a natural-language sample, and assuming the textbook constant puts the model's own error into every residual. Fitting it costs two accumulator passes. | Row 8 |

## See also

- [pipeline.md](pipeline.md) - the four stages, and where ENRICH sits.
- [../../concepts/lexicon.md](../../concepts/lexicon.md) - `wordClass`, attestation, and the vocabulary.
- [../contracts/schemas.md](../contracts/schemas.md) - the `wordhood` config contract.
- [../../concepts/config.md](../../concepts/config.md) - where the knobs live.
