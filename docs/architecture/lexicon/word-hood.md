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

## What the signals actually measured

Over the real staged store - 6,249,903 distinct surfaces, 18 enabled sources:

| Signal | Marked positive | Share |
| --- | ---: | ---: |
| `attested` | 589,862 | 9.4% |
| `orthotactic` > 0 | 5,600,039 | 89.6% |
| `breadth` >= 1 | 6,249,903 | 100% |
| `nannulValid` | 355,275 | 5.7% |
| `knownVerbForm` | 1,428,258 | 22.9% |

The orthotactic score falls in five buckets under the committed weights, and the
shape of that distribution is the layer's first honest look at its own corpus:

| Score | Surfaces | What broke |
| ---: | ---: | --- |
| 1.00 | 4,057,164 | nothing |
| 0.75 | 1,236,084 | one of the ending or the clusters |
| 0.50 | 224,727 | the opening, or both of the other two |
| 0.25 | 82,064 | the opening plus one more |
| 0.00 | 649,864 | not Tamil at all, or every rule |

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

## Rejected alternatives

| Option | Why rejected | Authority |
| --- | --- | --- |
| Dictionary attestation alone as the verdict | A 1930s lexicon rejects `kambyuttar`, and it would be wrong to. Attestation is one signal of eight. | User |
| A frequency floor as the quality test | Frequency and word-hood are independent axes - one is high-frequency and not a headword, the other low-frequency and not a word. This is the exact defect of the pipeline being replaced. | User |
| Infer verb inflection from morphological rules | 1.46M hand-collected forms are already on disk. Inferring what you can look up is a dependency and an error source bought for nothing. | Fowler, Holy Law #8 |
| Bundle all eight signals in one row | Four different risk profiles - a linguistic table, a statistical model, an all-pairs search, a classifier. | Fowler |
| A ninth `grantha` signal column | The published `wordhood` map and the store both carry eight names, and minting a ninth would change a contract to persist a fact that is a pure function of the surface - recomputable by the classifier for free from `WordShape.hasGrantha`. | Fowler |
| A pair-by-pair cluster table over all 324 mei-consonant pairs | The grammar states the rule over three consonant CLASSES, and a pair-by-pair table is the same facts with 324 more places to be wrong. | Fowler |

## See also

- [pipeline.md](pipeline.md) - the four stages, and where ENRICH sits.
- [../../concepts/lexicon.md](../../concepts/lexicon.md) - `wordClass`, attestation, and the vocabulary.
- [../contracts/schemas.md](../contracts/schemas.md) - the `wordhood` config contract.
- [../../concepts/config.md](../../concepts/config.md) - where the knobs live.
