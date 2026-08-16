# Word-hood

**Last Updated**: 2026-08-16

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
| `attested` | 6,569,694 | 913,295 | 13.9% |
| `orthotactic` > 0 | 6,569,694 | 5,612,420 | 85.4% |
| `breadth` >= 1 | 6,569,694 | 6,569,694 | 100% |
| `nannulValid` | 6,569,694 | 355,275 | 5.4% |
| `knownVerbForm` | 6,569,694 | 1,428,258 | 21.7% |
| `ngram` | 6,569,694 | 6,569,694 | 100% |
| `neighbour` | 4,112,531 | 2,587,590 | 62.9% |
| `zipf` | 4,551,338 | 1,864,878 | 41.0% |

The two columns whose MEASURED count is below the population are the two that
leave a deliberate NULL. `neighbour` was asked of 4,112,531 surfaces - the prune
skipped 2,457,163 - and of those asked, 1,150,327 have a headword one ezhuthu
away, 1,437,263 have one at two, and 1,524,941 have none within two. `zipf` is
measured for the 4,551,338 surfaces somebody actually counted.

The prune is a **1.60x** cut, not the 2.5-3x the plan predicted. The prediction
was sized against 3,967,009 surfaces; the store holds 6,569,694, and the three
exclusions are the same absolute sets whichever total you divide into. The
decision still pays for itself - 2.4M queries removed at no loss - but a reader
sizing the `suspectedTypo` queue should size it against 4.1M.

`ngram` marks every surface positive because its floor is the smoothing mass
rather than zero: it is a probability, and no sequence has probability zero under
a smoothed model. What separates surfaces is the MAGNITUDE, not the sign, which
is the one respect in which it does not read like the seven others.

The orthotactic score falls in five buckets under the committed weights, and the
shape of that distribution is the layer's first honest look at its own corpus:

| Score | Surfaces | What broke |
| ---: | ---: | --- |
| 1.00 | 4,068,656 | nothing |
| 0.75 | 1,236,239 | one of the ending or the clusters |
| 0.50 | 225,404 | the opening, or both of the other two |
| 0.25 | 82,121 | the opening plus one more |
| 0.00 | 957,274 | not Tamil at all, or every rule |

The three inexact signals cost more to compute and are worth stating with their
own inputs, because each number is a decision someone can check:

| What | Measured |
| --- | ---: |
| Attested headwords | 913,295 |
| ... of which wholly Tamil, and so the dictionary | 476,319 |
| ... dropped as not-Tamil | 436,976 (47.8%) |
| Distinct ezhuthu in the dictionary | 321 |
| Trigrams the model actually saw | 207,758 |
| Deletion-index entries at `maxEditDistance` 2 | 13,612,854 |

Nearly half the attested headwords are now dropped from the training set, up
from a fifth, and the cause is the title list: a Wiktionary page title is often
a multi-word phrase or a romanization, and a space is not an ezhuthu. That is
the filter doing its job - the model is trained on Tamil words, not on the
inventory's packaging.

### What the classifier actually decided

Over 6,569,694 surfaces, with the Row 9 column beside it so the two corrections
can be read off:

| `wordClass` | Row 9 | Row 9a | Share | Decided by |
| --- | ---: | ---: | ---: | --- |
| `headword` | 49,873 | 137,991 | 2.10% | a tier-1 entry, a clean shape and no grantha |
| `inflected` | 1,428,139 | 1,425,408 | 21.70% | the collected verb forms, plus the dictionary plural tags |
| `colloquial` | 1 | 1 | 0.00% | the single surface any source tagged a contraction |
| `properNoun` | 1,185 | 1,074 | 0.02% | the Wiktionary name tag |
| `loanword` | 602,744 | 601,832 | 9.16% | grantha, an illegal opening, or a cluster Tamil does not build |
| `boundStem` | 101 | 1 | 0.00% | the affix tags |
| `sandhiArtifact` | 449,031 | 448,943 | 6.83% | an ending no Tamil word has |
| `suspectedTypo` | 1,213,915 | 267,970 | 4.08% | improbable and one edit from a real word |
| `notAWord` | - | 949,378 | 14.45% | the shape precondition |
| `unclassified` | 2,824,705 | 2,737,096 | 41.66% | nothing decided it |

Both columns are measured over the SAME store, so every difference is one of the
two corrections and nothing else.

**`suspectedTypo` fell by 945,945 and `notAWord` took 949,378.** Almost the whole
of the old `suspectedTypo` bucket was surfaces that are not Tamil at all rather
than misspellings of Tamil - an accusation the class was never meant to carry.
What is left is the class as defined: improbable, unattested, and one ezhuthu
from a real word.

**`boundStem` fell from 101 to 1.** All hundred were Wiktionary affix entries
carried with their notation hyphen - `-kaL`, `-ththu` - and a hyphen is not an
ezhuthu, so the string is not a Tamil word whatever the morpheme is. The
`wordClassEvidence` fact is still in the store for a later row that wants to read
affixes as affixes; what changed is that the VERDICT now describes the string.

**`unclassified` fell by 87,609**, and every one of them is the entry-test fix:
the curated dictionary's headwords that Row 9 demoted for want of a
part-of-speech column.

**`headword` is 137,991**, and the arithmetic behind it is worth writing down
because every step is a decision someone can check:

| Step | Surfaces |
| --- | ---: |
| a headword fact from any authority | 913,295 |
| ... from a TIER-1 source - an ENTRY | 262,026 |
| ... less entries the shape precondition rejects | -119,130 |
| ... less entries carrying grantha, which go to `loanword` | -2,822 |
| ... less entries breaking a letter rule | -572 |
| shape-clean entries | 139,502 |
| ... less those carrying an asserted `wordClassEvidence` class | -1,511 |
| `headword` | 137,991 |

The largest subtraction is the two biggest dictionaries' Tamil columns carrying
multi-word glosses and page titles rather than words. Of the 137,991 headwords,
**85,314 are 3-6 ezhuthu**, against Row 12's floor of 6,000 served.

**3,483 of the entries are also collected verb forms**, and every one of them
stays a headword: a generated paradigm table necessarily contains the citation
form, so phase 2 running before phase 3 is what keeps Tamil's verbs in the
dictionary.

#### The one escape, recorded rather than hidden

Trusting a tier-1 source's listing is what recovers the 87,611 headwords the
curated dictionary carries with nothing else said about them - and the same
trust admits `asura`, the stem of `asuran`, which that dictionary also lists.
Nothing in the store separates the two: `asura` and a real classical headword
like `aqkaram` have the same attestation, breadth, shape and n-gram profile, and
the morphological rule that would tell them apart ("begins with an attested
headword and is longer") was measured in Row 9 and rejected for costing a real
headword. The trade is 87,611 real dictionary headwords against one stem, and it
is taken deliberately. The golden fixture pins the escape by name, so a SECOND
one cannot arrive unnoticed, and Row 12's `requireHumanGloss` gate is the
backstop that keeps it off a player's screen.

**`colloquial` is one row and `boundStem` is one.** Neither has an evidence
producer worth the name, and neither can be inferred from the eight signals,
because a colloquial form is orthotactically perfect and a bound stem is
indistinguishable from a short rare word. They are honest zeroes rather than
hidden ones.

**`unclassified` is 42 percent, and most of it is inflection.** A sample drawn
from the discovery profile was, without exception, agglutinated verb and
participle forms that the bulk verb lists happen not to contain - not modern
words the dictionaries missed. The enrichment queue should therefore be sized
and read as a queue of FORMS with some discoveries in it, not the other way
round. 83,295 surfaces meet the discovery profile exactly.

The 581 is worth stating plainly: **`granthaPenalty` is zero but grantha is
still a verdict, so no word written with a grantha consonant can reach the served
set** while the selection excludes `loanword`. That is a deliberate consequence
of Row 7 decision 6 and not a side effect, but it is a visible vocabulary gap and
the number is small enough to reconsider on purpose.

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

## The verdict: how eight signals become one class

The nine classes are in
[../../concepts/lexicon.md](../../concepts/lexicon.md#wordclass---what-kind-of-thing-a-surface-is)
and are not restated here. What follows is how a surface reaches exactly one of
them.

**It is an ordered CASCADE, not a weighted score.** Ten classes are not ten
points on a line - a proper noun and an inflected form are non-headwords for
entirely unrelated reasons - so there is nothing for a weighted sum to be a sum
OF. A cascade also has a property a score does not: every verdict traces to the
ONE rule that produced it, which is what makes a misclassification a reviewable
diff rather than a tuning session.

Five phases, and the order is the design.

### Phase 0 - is this a word at all?

A PRECONDITION, weighed before every signal and before every source assertion.
Three rejections, each a threshold in `config/wordhood.json` under
`classifier.notAWord`, and each with a real producer measured over the store:

| Rejection | Knob | Surfaces |
| --- | --- | ---: |
| holds a unit that is not an ezhuthu | `rejectNonTamil` | 616,175 |
| longer than any Tamil word runs | `maxEzhuthu` (25) | 25,464 |
| one character repeated | `minDistinctEzhuthu` (2) | 180 |

Together that is **641,819 surfaces, 10.3 percent of the store**, and before
this phase existed every one of them wore a real class: repeated aytham as
`loanword`, leading-dot and leading-hyphen strings as `inflected` and
`boundStem`, and a scraped paragraph of 1,212 ezhuthu as `suspectedTypo`. It
also collapsed the (`wordClass`, `length`) cell count from **509 to 140**, which
is the number Row 11's layout has to be decided against.

**It runs before phase 1 on purpose.** A statement about the STRING outranks a
statement about the word it is not: a scraped paragraph a source tagged as a
name is still a scraped paragraph, and letting the tag win is precisely how junk
comes to wear a real class.

**`notAWord` is a CONFIDENT NEGATIVE and stays distinct from `unclassified`.**
That class is the enrichment queue - a verdict ABSENT, which a later pass may
fill - while this one is a verdict REACHED. Collapsing them would leave the
layer with no counter for how much junk the corpus carries and no honest size
for the work remaining, which are the only two numbers that say whether the
classifier is working. `notAWord` is also non-servable by construction, because
Row 12's allow-list is `["headword"]`.

The three thresholds are knobs rather than constants because none of them is a
fact about Tamil. Tamil compounds freely, so no grammar bounds a word's length -
what is bounded is the length past which every surface inspected was a scrape
that lost its spaces. `minDistinctEzhuthu` applies only above one ezhuthu, since
a one-ezhuthu word obviously holds one distinct ezhuthu and is ordinary Tamil.
And `rejectNonTamil` is the one clause a project could reasonably turn off: with
it false the Row 9 behaviour returns and such a surface is judged by orthography
into `suspectedTypo`, which is why that arm of phase 3 is still there.

### Phase 1 - what a source SAID

A `wordClassEvidence` fact is an ASSERTION, not an inference, so nothing below
is allowed to overrule it. Row 3 built the alias map precisely so a raw source
tag that names no part of speech would land here instead of being thrown away,
and it pays for itself immediately: the Wiktionary extract tags 1,185 surfaces
`name`, which is the cheapest proper-noun evidence in the whole inventory and
the reason `staalin` can never be served.

When two sources assert different classes, `evidencePriority` in config decides,
and it is validated to rank every value exactly once - a partial ranking would
leave an assertion with no defined winner and the verdict would then depend on
the order SQLite returned the facts in. It is ordered by how specific and how
irreversible the claim is: `notAWord` first, then `properNoun`, then the three
that say the string is not a whole word, then the two register claims, then
`inflected`, which says only that this is a form of something else. Over the
real store just five surfaces carry more than one distinct evidence value, so
the ranking is a correctness property rather than a frequently-exercised path.

#### The `notAWord` veto - when a source says the unit is a LETTER

`notAWord` is the one evidence value that is a DENIAL rather than a description,
and it is ranked first because it answers a different question from every other
value: not what KIND of word this is, but whether it is a word at all.

It reaches the store from the one place a source can state it. The registry
routes a raw part-of-speech tag to a `reject` reason, and one of those reasons
is `notAWord` - "the source itself says the unit is not a word (a script
character, a symbol), so extracting a headword fact from it would assert what
the source denied". That sentence was in the contract from Row 3 and the code
did not implement it: EXTRACT suppressed only the `pos` fact, and the `headword`
fact went out regardless. The pipeline asserted exactly what the source denied,
and the visible consequence was that the letter `அ` - the first letter of the
Tamil alphabet - published as a headword with a meaning attached.

So the rejection now emits `wordClassEvidence: notAWord`, and the denial vetoes
every other source's bare `headword` listing. Another authority merely LISTING
the same single letter is not an answer to the dictionary that looked at it and
called it a character.

**The word ONLY is load-bearing.** The denial stands only when it is everything
that source said about the surface. The Wiktionary extract files the vowel `ஆ`
as a character in one row and as a noun in another, and the noun has to win -
so a `notAWord` row is dropped when the SAME source also asserted a part of
speech for the SAME word. Asking per SOURCE rather than per store is what makes
that possible while leaving the cross-source veto intact: one source's denial is
not answered by another source's bare listing, and that is the case the veto
exists for.

The test is applied in the derived zone, not at extraction. EXTRACT records what
a row SAID; whether a denial stands is a judgement over everything the source
said, which is the same division of labour that puts `attestationTier` in the
registry and reads it at classification time.

**It is not a length rule, and it must not become one.** `நீ`, `தீ`, `பூ` and
`வா` are all one-ezhuthu Tamil words. What removes `அ` is a lexicographer's
verdict about `அ`, and the only surfaces affected are the ones a source
explicitly refused.

### Phase 2 - the headword gate, which must be EARNED

`headword` is the only class Row 12 serves, so it is the only class whose test
is a conjunction. A surface is a headword when an authority gave it an ENTRY,
its shape breaks no rule, it carries no grantha, and its orthotactic score
clears the configured floor.

#### Attestation is not an entry, and an entry is a property of the SOURCE

`docs/concepts/lexicon.md` defines an attestation as "this authority lists this
as an ENTRY", and over the acquired inventory those turned out to be two
different events. Nine sources may assert word-hood. Five of them are
LEXICOGRAPHIC - their unit is an entry, and somebody decided the string was a
word before saying anything about it. Four are ENUMERATIVE - their unit is a
bare string in a list:

| Source | Tier | Rows | Emits |
| --- | --- | ---: | --- |
| `ta-wiktionary-content` | lexicographic | 265,020 described pages | headword, definitionTa, synonym, pos, translation |
| `en-ta-dictionary` | lexicographic | 161,929 words | headword, pos, translation, synonym |
| `master-dictionary` | lexicographic | 104,073 words | headword, translation (12,905), category, graphemeCount |
| `wiktextract-ta` | lexicographic | 11,103 words | headword, pos, definitionEn, synonym |
| `llm-authored` | lexicographic | 6,269 words | headword, definitionTa, translationEn, pos, synonym, category |
| `ta-wiktionary-titles` | enumerative | 410,074 titles | headword |
| `spellcheck-wordlist` | enumerative | 355,275 words | headword |
| `old-wordlist` | enumerative | 36,068 words | headword |
| `huggingface-wordlist` | enumerative | 26,485 words | headword |

The two Wiktionary sources are the same wiki and the opposite tiers, which is
the clearest statement of what the tier means. The title list ships the string;
the content dump ships what somebody said about the string. Because the
difference is in the BYTES rather than in the provenance, the content source
enforces its own tier row by row: it emits a `headword` fact only for a page
that carries a sense, a synonym, a gloss or a part of speech, so 145,054 of its
410,074 pages are observed and attested by nobody.

Among what the four lists list: a political party, a sitting politician, a bound
stem that is not a word, and a great many case-marked nouns. **Attestation alone
would rule every one of them a headword** - which is exactly the outcome Row 12
decision 2 exists to prevent, arrived at by a different route.

So an ENTRY is **tier-1 attestation**: a headword fact from a source whose
declared `attestationTier` is `lexicographic`. The tier is declared per SOURCE
in `config/lexicon-sources.json`, required on every role that may assert
word-hood and forbidden on every role that may not, so registering the next
authority forces the ruling rather than inheriting one silently.

##### Why the first version of this test was wrong

Row 9 asked the question per ROW: a headword fact AND a describing fact from the
SAME source, with `pos` as the shipped default. It admitted every reference
headword and none of the reference non-words, so it looked right. The
measurement said otherwise.

Only three sources emit a `pos` fact at all. `master-dictionary` - the
predecessor project's entire curated dictionary, 104,073 headwords - emits
**zero**, because its part-of-speech column was a blanket `nouns` stamp on
99.81 percent of its rows, verbs included, and Row 5 correctly rejected it at
EXTRACT as `notAPosLabel`. So the per-row rule demoted **86,249 of that
dictionary's headwords (82.6 percent) to `unclassified`** and kept 10,300.

The defect is not the threshold, it is the QUESTION. What a source's unit IS
cannot be recovered from one row of it, and the largest lexicographic source
describes only part of what it lists - so asking per row punished a real
dictionary for one unusable COLUMN. Asking per source is also the honest reading
of what the classifier needs: whether a lexicographer stood behind this string,
not whether the particular field the classifier likes survived extraction.

| Rule | Entries | On the reference rows |
| --- | ---: | --- |
| a headword fact from any authority | 913,297 | admits the party, the stem and the inflections |
| ... and a describing fact from the same source (Row 9) | 163,561 | admits none of them, and drops 86,249 real dictionary headwords |
| ... from a TIER-1 source (Row 9a) | 268,297 | admits none of them, and keeps them |

### Phase 3 - the reasons a surface is NOT a headword

In evidence-strength order, and each rule reads the fact that actually decides
it rather than a number the facts were collapsed into:

| Test | Verdict | Why here |
| --- | --- | --- |
| `knownVerbForm` | `inflected` | Direct evidence: a collected, labelled form. Decision 2's cheapest accuracy. |
| `hasNonTamil` | `suspectedTypo` | Only reachable with `rejectNonTamil` off; with it on, phase 0 has already ruled. |
| `hasGrantha` | `loanword` | The five grantha consonants exist to write sounds Tamil does not have. |
| ends illegally | `sandhiArtifact` | The sandhi signature: the doubling that belonged to the NEXT word. |
| opens illegally, or a bad cluster | `loanword` | Row 7's reconciliation found these rejections are Sanskrit clusters, English transliterations and spaceless compounds. |

**An entry outranks bulk form evidence**, which is why phase 2 runs first. A
generated paradigm table necessarily contains the citation form, so a rule that
let `knownVerbForm` win would delete every verb headword in the language from
the served set. 2,239 surfaces are both an entry and a collected form, and every
one of them is a lexicographer's decision against a table's by-product.

**`granthaPenalty` is zero and grantha is still a verdict**, because the two
answer different questions. The penalty prices grantha inside the SHAPE score,
where it is not a defect; the classifier reads `hasGrantha` as evidence about
ORIGIN. Keeping one fact answering two questions is exactly why Row 7 exposed it
rather than folding it into the score.

### Phase 4 - the residue, where the honest answer is "not yet"

A surface that is orthotactically clean, corroborated by several independent
sources, sits above the n-gram floor and is still unattested goes to
`unclassified`, which IS the enrichment queue - never to an accusation and never
to a discard. That is decision 4, and it is written as its own rule rather than
left to fall out of Row 8's prune: the prune already skips most of these, but
making a correctness guarantee a side effect of a performance knob is how it
gets deleted later by someone tuning the knob.

`minNgram` is measured, not chosen. At **0.03** it sits at the tenth percentile
of the surfaces that already have a dictionary entry and a clean shape, and at
the ninetieth percentile of the surfaces that are not Tamil at all - so nine in
ten real headwords clear it and nine in ten non-Tamil strings do not.

What is left is `suspectedTypo`: unattested, not passed by the spellchecker,
IMPROBABLE, and with a real word one ezhuthu away. All four clauses earn their
place. A near neighbour alone is not evidence of a slip - an agglutinative
language generates real forms one ezhuthu apart by the thousand, and the profile
without the n-gram ceiling accuses ordinary Tamil like `maanilangkaLiloo` and
`veLichchamaayirukkitrathu` alongside genuine slips like `paatraikaLiil`. The
separation is clean in the corpus: over a sample drawn from the profile the real
slips score 0.003 to 0.017 and the false accusations 0.08 to 0.15. This is
exactly what the n-gram signal was built for - the letter rules say which shapes
Tamil ALLOWS, the model says which it USES, and legal-but-improbable is what a
typo looks like.

**NULL is excluded before the neighbour comparison.** `neighbour` is NULL for
every surface Row 8's prune never queried, and reading NULL as zero-distance
would accuse every attested headword in the store. A MEASURED zero is not a typo
either - it means the search ran and found no real word within its radius, which
is evidence against.

Everything else is `unclassified`.

### What the classifier deliberately does NOT read

**`zipf` is never consulted.** Frequency and word-hood are independent axes -
the founding observation of this whole layer - so a rule keyed on a frequency
residual would re-import the exact defect the lexicon exists to remove. It stays
in the signal map because it is one of the eight and a reader comparing a record
to the store should find it there, and a test asserts that no value of it,
including NULL, can change any verdict.

**No morphological analyzer, and no suffix table either.** Inflection is
assigned from the 1.46M collected verb forms and the 2,125 surfaces a
dictionary tagged as plurals - direct evidence, both. Inferring the rest was
tried on paper and rejected: the cheapest candidate rule, "this surface begins
with an attested headword and is longer", labels `vaayppu` an inflection of
`vaay`, and `vaayppu` is one of this layer's own reference headwords. A rule
that costs a real headword to catch an inflected form is trading the class Row
12 serves for a class it does not.

## Design rationale

- **The verdict is an ordered cascade, not a weighted score.** Ten classes are
  not ten points on a line, so there is nothing for a sum to be a sum of - and
  a cascade lets every verdict be traced to the one rule that produced it, which
  is what turns a misclassification into a reviewable diff. The classes that
  cost the most to get wrong are decided by the strongest evidence and decided
  first. (Fowler.)
- **"Not a word at all" is a verdict, and it is the FIRST one.** Before it
  existed the classifier had nowhere to put 641,819 scrape artifacts, so they
  wore real classes and every count downstream was wrong by ten percent. It is
  a precondition rather than a rule in phase 3 because a statement about the
  STRING outranks a statement about the word it is not - otherwise a source tag
  on a scraped paragraph decides the paragraph is a proper noun. It is NOT a
  reject at EXTRACT, which would corrupt Row 5's `rowsOut + parseRejects ==
  rowsIn` ledger where a reject means "I could not READ this record", and NOT a
  filter at PUBLISH, which would leave the store polluted and make every future
  consumer re-derive the same predicate. (Fowler, Row 9a.)
- **`notAWord` stays distinct from `unclassified`.** One is a confident negative
  and the other is an absent verdict, and they are the only two counters that
  say whether this layer is working: how much junk came in, and how much real
  work is left. A single "not served" bucket would answer neither, and the
  allow-list already stops both from reaching a player. (Fowler, Row 9a.)
- **An ENTRY is a property of the SOURCE, asked once, not of the ROW.**
  Requiring a describing fact from the same row's source read well and measured
  badly: the largest curated dictionary's part-of-speech column was a blanket
  `nouns` stamp, correctly rejected at extract, so 82.6 percent of its 104,073
  headwords were demoted to `unclassified` for want of a column that had nothing
  to do with whether a lexicographer stood behind the word. What a source's unit
  IS cannot be recovered from one row of it. The tier is declared in
  `config/lexicon-sources.json` rather than in code or in a list of ids
  somewhere else (Holy Law #6), required exactly on the roles that may assert
  word-hood, so registering the next authority forces the ruling. (Row 9a, on
  Row 12 decision 14's tier split.)
- **The tier is read from the registry, never from the store.** It is a
  JUDGEMENT the derived zone applies to evidence rather than part of the
  evidence, so re-ruling a source costs a config edit and a `--classify` re-run
  - not a re-stage of its bytes. Mirroring it into the `source` table beside
  `role` was the alternative, and it would have made every re-ruling a
  re-ingestion. (Row 9a.)
- **Attestation is not an entry, and the gate reads the stronger of the two.**
  Four of the eight sources that may assert word-hood are bare word LISTS, and
  between them they attest a political party, a bound stem and a great many
  case-marked nouns. Requiring a lexicographic source admits every one of this
  layer's reference headwords and none of its reference non-words. (Row 9, on
  Rows 3 and 5's fact model; corrected by Row 9a.)
- **The classifier recomputes the SHAPE rather than reading the score.** The
  `orthotactic` column is one number and three different defects are collapsed
  into it, while the classes they imply are different: an illegal ending is a
  sandhi artifact and an illegal opening is a borrowing. Row 7 kept those facts
  apart on `WordShape` for this reader and exposed `hasGrantha` rather than
  persisting a ninth signal column, so the classifier calls `analyse` once per
  surface and reads all five. The score is still read where a single number is
  what the question wants - the headword floor and the discovery profile.
  (Row 9, on Row 7's rejected ninth signal.)
- **Grantha is a verdict even though its penalty is zero.** The penalty prices
  grantha inside the SHAPE score, where it is not a defect; the classifier reads
  the same fact as evidence about ORIGIN. One fact answering two questions is
  precisely why Row 7 recorded it instead of folding it into the score, and
  collapsing them would make `granthaPenalty` the only way to express either.
  (Row 9, on Row 7 decision 6.)
- **A lexicographic entry outranks bulk form evidence.** `role: formEvidence`
  can only assert a negative, but a GENERATED paradigm table necessarily
  contains the citation form, so a rule that let it win would delete every verb
  headword in the language. 2,239 surfaces are both, and phase 2 running before
  phase 3 is what keeps them. (Row 9.)
- **Decision 4's protection is a rule, not a side effect.** Row 8's prune
  already skips a surface several independent sources agree on, so a broad
  unattested word arrives with a NULL neighbour and cannot be accused anyway.
  Writing the discovery profile out as its own rule costs three comparisons and
  means the guarantee survives somebody tuning `pruneBreadth`. (Fowler.)
- **`minNgram` was measured against the corpus, not chosen.** At 0.03 it is the
  tenth percentile of the surfaces that already have an entry and a clean shape
  and the ninetieth percentile of the surfaces that are not Tamil at all, so it
  separates the two populations rather than expressing a preference. A threshold
  nobody measured is a threshold nobody can defend. (Row 9, on Row 7's
  reconciliation discipline.)
- **The cascade is a pure function of a plain value.** It takes a `Surface` -
  eight signals, an entry flag and the asserted evidence - and returns a class,
  with no connection, no store and no fixture-only path. That is what lets the
  Oracle run in CI over 200 committed rows while the same code classifies 6.25M
  in SQLite as a deterministic user-defined function. A classifier that could
  only be exercised against a 1.8 GB gitignored store would have no regression
  gate at all. (Fowler.)

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
| A weighted score over the eight signals, thresholded into classes | The classes are not ordered, so a sum has nothing to be a sum of - and a score cannot say WHICH evidence produced a verdict, which is what a review of a misclassification needs. | Fowler |
| `attested` alone as the headword gate | Three of the six authority sources are bare word lists. It would serve a political party, a sitting politician, a bound stem and every case-marked noun a spellchecker happens to contain - the exact content bug this plan exists to fix. | Row 9 |
| A per-SOURCE tier list instead of a per-ROW entry test | The largest lexicographic source also lists inflected forms, so tier-1-ness as a property of the source's format admits them. Row 12's admission gate can count sources; a word-hood verdict has to read the row. | Row 9 |
| A per-class accuracy threshold as the Oracle | A metric is not a predicate - nothing can fail it. Byte-equality against a committed expected-output file plus 100 percent headword precision is deterministic and can fail. | Fowler |
| A morphological analyzer to detect inflection properly | Heavy, imperfect dependency. The collected forms label inflection by evidence, and the store keeps every surface so a later row can improve it with no re-ingest. | Fowler, Holy Law #8 |
| "Begins with an attested headword" as an inflection rule | It labels `vaayppu` an inflection of `vaay`, and `vaayppu` is one of this layer's own reference headwords. A rule that costs a real headword to catch an inflected form trades away the only class that is served. | Row 9 |
| Reading `zipf` anywhere in the cascade | Frequency and word-hood are independent axes. A rule keyed on a frequency residual re-imports the exact defect the lexicon exists to remove. | User |
| Deleting a surface the classifier cannot place | Word-hood classifies; it does not delete. `unclassified` is a legal verdict and the queue the enrichment pass reads, and selection is an allow-list so it can never be served by omission. | User + Player |

## See also

- [pipeline.md](pipeline.md) - the four stages, and where ENRICH sits.
- [../../concepts/lexicon.md](../../concepts/lexicon.md) - `wordClass`, attestation, and the vocabulary.
- [../contracts/schemas.md](../contracts/schemas.md) - the `wordhood` config contract.
- [../../concepts/config.md](../../concepts/config.md) - where the knobs live.
