# The Lexicon

**Last Updated**: 2026-08-14

The vocabulary of the word layer, defined once. Every other doc links here rather than restating a term. What the words are FOR is [core-loop.md](core-loop.md) and [games.md](games.md); how they are SELECTED is [difficulty-and-scoring.md](difficulty-and-scoring.md); the persisted shapes are in [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md).

## What a lexicon is here

The **lexicon** is the all-words artifact: every Tamil surface any registered source ever showed us keeps a row, keeps a class, and keeps every fact a source asserted about it. It is not a served set and it is not a filtered set. Selection happens later and downstream, over the lexicon, on named gates.

That is a deliberate reversal of the corpus layer it supersedes. The corpus ingest was a destructive funnel - millions of distinct surfaces in, fifty thousand words out - and every surface it rejected became unrecoverable without re-reading hundreds of megabytes of gitignored source bytes. The lexicon inverts the responsibility: **ingest ENRICHES, selection FILTERS**. Nothing is discarded, so recovering a word that was wrongly excluded is a change to a selection knob rather than a re-ingest.

Because nothing is discarded, the artifact needs an integrity ledger that proves it. Its per-class counters reconcile: every published row lands under exactly one `wordClass`, the buckets sum to the declared row count, and the files on disk declare the same population class by class. A row lost between the classifier and the writer cannot validate.

## Length is measured in ezhuthu

A word's `length` is its count of **ezhuthu** (எழுத்து) - Tamil grapheme clusters, the unit a player sees on a tile - never code points and never bytes. A mei (a consonant carrying the pulli, புள்ளி, Unicode U+0BCD) counts as ONE full ezhuthu.

**`mathirai` (மாத்திரை) is not length.** Mathirai is a mora, a PROSODIC unit from Tamil prosody, and using it for length would silently change what a "four-letter word" means. The segmentation itself is the shared ezhuthu library (`backend/yen_tamizh_backend/ezhuthu/`, mirrored in `frontend/src/tamil/ezhuthu.ts`), never re-implemented, and every lexicon row is validated against it: a row whose declared `length` is not what `segment(word)` counts is rejected by the contract. The published row carries the COUNT and not the list of ezhuthu - the list is a pure function of the word, and a stored copy of a derived value is a place for the two to disagree.

## Attestation is not observation

Two different things a source can tell us, and only one of them is evidence of word-hood:

- An **observation** is "this scraper saw this surface, this many times". A frequency list observes. Observing a surface says nothing about whether it is a word - a misspelling in five news corpora is observed five times and is still a misspelling.
- An **attestation** is "this authority lists this as an entry". A dictionary attests.

Only sources with `role: authority` or `role: authored` can assert word-hood. A published row carries `attestations` - how many of them listed it - and `tier1Attestations`, how many of those were LEXICOGRAPHIC rather than a bare listing. Two counts rather than the list of names: what selection gates on is how many and how good, and WHICH source said it is a question about one word, which the build-time store answers. A scraper that merely observed a surface decides nothing and is counted in neither.

`role: formEvidence` is the third case and it can only assert a NEGATIVE: a bulk list of inflected verb forms proves a surface is not a headword, never that it is one.

## `wordClass` - what KIND of thing a surface is

Every row carries exactly one `wordClass`, from a closed set of ten. A closed set rather than a numeric score, because a score says how CONFIDENT we are and not what KIND of thing this is - and proper nouns and inflected forms are both non-headwords for entirely different reasons. One of them must never be served; the other is future lemmatizer input.

| Value | What it means |
| --- | --- |
| `headword` | A dictionary entry form. The only class the Games serve. |
| `inflected` | A grammatical form of some headword (a case-marked noun, a conjugated verb). Kept in full, never served as an answer - but it is what a Wordle-style guess-acceptance list is made of, because Tamil agglutination makes an inflected guess the common case. |
| `colloquial` | A spoken-register form, including contractions. Real Tamil, not dictionary Tamil. |
| `properNoun` | A name - a person, a place, an organisation. Never served: a player who is shown a sitting politician's name as "a Tamil word" has been handed general knowledge, not language. |
| `loanword` | A borrowed surface carried in Tamil script. |
| `boundStem` | A morpheme that cannot stand alone - a prefix, a suffix, an interfix, or a stem stripped of its ending. This is the class that catches the junk the old co-anagram rule actively selected for: fragments are exactly what collide with real words. |
| `sandhiArtifact` | A tokenization casualty - the euphonic doubling belonging to the NEXT word got attached to this one. |
| `suspectedTypo` | Present in the sources, rejected by orthography or by every authority. |
| `notAWord` | Not a Tamil word at all: a string carrying something that is not an ezhuthu, longer than any word runs, or one character repeated. A CONFIDENT NEGATIVE about the string itself. |
| `unclassified` | The classifier could not reach a verdict. |

`notAWord` and `unclassified` are the two ends of one axis and are deliberately kept apart. `notAWord` is a verdict REACHED - the shape pass looked at the string and ruled; `unclassified` is a verdict ABSENT - the enrichment queue, where a later pass may still find a real word. Collapsing them would hide both how much junk the corpus carries and how much work is left, which are the only two counters that say whether the classifier is working.

Selection is an ALLOW-LIST over these values, never a deny-list, so `unclassified` can never be served by omission.

## `wordhood` - the signals behind the verdict

`wordhood` is the classifier's evidence: eight named signals, `attested`, `orthotactic`, `breadth`, `nannulValid`, `knownVerbForm`, `ngram`, `neighbour` and `zipf`. What each one catches, and how they combine into the verdict, belongs to the classifier's own doc and is not restated here.

The published artifact carries none of them, because `wordClass` IS their verdict and the verdict is what every consumer reads. They live in the build-time store, where the review reports expose them for a human to sort the residue by.

## Frequency, and the register it hides

`frequency` is the SUM of a surface's counts over every frequency-role source. Summing is what makes the number comparable across the whole lexicon - and it is also what destroys the per-source split, which is the single most useful familiarity signal in the inventory.

`spokenRatio` (0-1) is what survives of that split: the subtitle corpus's share of the summed frequency. A word frequent in subtitles and rare in news is everyday spoken Tamil; a word frequent in news and absent from subtitles is written or formal. That is register, concreteness and child-vs-adult vocabulary at once, from data already on disk.

There is deliberately no frequency BAND on the lexicon. A rank-relative band computed over a population where thousands of rows have `frequency == 0` is a different filter wearing an old name; the raw count plus an absolute floor at selection time replaces it.

## Meaning: three fields, three facts

A single "gloss" collapsed three different facts with three different consumers, so there are three named fields and each name states both its language and its kind:

- **`translationEn`** - one English equivalent. A fact, publishable verbatim.
- **`definitionTa`** - an explanatory Tamil phrase.
- **`synonymsTa`** - a same-language Tamil equivalent set (ஒருபொருட் பன்மொழி, *orupporut panmozhi*). A Tamil meaning is preferred over an English one everywhere a player can see it.

An English DEFINITION is never a published column. A one-word translation, a synonym and a Tamil definition are what a Tamil speaker can read; an English definition is a lexicographer's prose in the wrong language for this game. It is retained as build-time evidence for the authoring pass and never republished.

A Tamil definition publishes VERBATIM from whichever attesting source carried it, and the authoring pass fills only what no source attests - so an ATTESTED meaning always outranks an AUTHORED one. That ranking is a rule in the resolver rather than a precedence number, because appending a source to the registry must not be able to promote the authoring pass over a dictionary by accident.

The published row carries no provenance STAMP on any of those. Which source a meaning came from is a question about one word, and the store is where a per-fact `source_id` answers it; a stamp on 139,000 rows would be a column every row pays for and nothing spends. None of it was ever going to be rendered to a player anyway: an "AI-written" badge on some meanings makes a player distrust all of them.

## `pos` and `categories` are different questions

`pos` is a part of speech - a fact about the LANGUAGE, from a closed vocabulary. `categories` are themes (birds, flowers, colours) - a fact about the WORLD, from an open one that a source supplies.

A source label naming a part of speech routes to `pos`, never to `categories`, however the source filed it. The one curated themed source files `Nouns`, `Verbs` and `Adjectives` as "categories", and they are 64 percent of its rows; leaving them there would make `Nouns` the largest theme in the lexicon.

Categories are very sparse and are never an admission gate.

## What is committed, and what is only retained

The store keeps every surface and every fact. The REPOSITORY commits the classes a player can be served - `headword`, `properNoun`, `boundStem` and `colloquial` - one file per (`wordClass`, first ezhuthu) under `datasets/lexicon/by-class/`, indexed by `lexicon.meta.json`.

Retention is not publication, and the meta document is what keeps the difference honest: `counters.classified` is a per-class census of the WHOLE population, committed beside the files, so a withheld class is on the record in the repository at its real size. `counters.published` counts what the files carry, and a class is published whole or withheld whole - a partial count would mean rows lost rather than rows withheld.

## See also

- [../architecture/lexicon/pipeline.md](../architecture/lexicon/pipeline.md) - the four stages that build this artifact.
- [../architecture/lexicon/word-hood.md](../architecture/lexicon/word-hood.md) - the eight signals, what each catches, and how a `wordClass` is reached.
- [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) - the `lexicon` and `lexicon-sources` contracts and their shape decisions.
- [core-loop.md](core-loop.md) - what a player does with a word.
- [games.md](games.md) - which selection dimensions each Game uses.
- [difficulty-and-scoring.md](difficulty-and-scoring.md) - the serving gates and the difficulty axes.
- [principles.md](principles.md) - the project-level design principles this layer serves.
