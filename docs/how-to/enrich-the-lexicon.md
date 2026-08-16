# Enrich the lexicon

**Last Updated**: 2026-08-16

How the Tamil meanings, synonyms, English translations, parts of speech and themes that a player eventually reads get written, reviewed and committed. The four stages this feeds are in [../architecture/lexicon/pipeline.md](../architecture/lexicon/pipeline.md); what the words mean is [../concepts/lexicon.md](../concepts/lexicon.md); which surfaces are word-hood-eligible in the first place is [../architecture/lexicon/word-hood.md](../architecture/lexicon/word-hood.md).

## The model is a source, not a stage

A dictionary's Tamil sense text is a lexicographer's prose, and prose is retained as build-time evidence and never republished ([../concepts/lexicon.md](../concepts/lexicon.md)). So every published `definitionTa` is **authored** - written by the agent executing the pipeline, from the evidence the store already holds - and the result is committed as an ordinary lexicon source at `datasets/lexicon/sources/llm-authored/entries.jsonl`.

There is no API client anywhere in the pipeline, no key, and no new dependency. `wordsmith/llm_enrich.py` reads and validates that committed file; it never calls a model. This is not squeamishness about network access - it is what makes the pipeline reproducible at all. A model asked the same question twice may answer differently, so it can never sit inside a stage whose Oracle is byte-identity. A committed file can: the same bytes produce the same facts on every run, on every machine, forever, and a bad batch is visible in a per-line diff and revertible by one commit.

The file is therefore raw INPUT, exactly like the twenty-one acquired sources, which is why it has no generated JSON Schema. What makes a source trustworthy here is its reader failing loudly at the boundary, and `llm_enrich.py` is that reader. It is the ONE source whose bytes are committed rather than gitignored, so it also has no acquisition ledger row and no fixture slice - the real file is always on disk and is what the tests exercise.

## Attested Tamil sense evidence now exists, and it changes the INPUT rather than the rule

Until row 4b no acquired source supplied a Tamil definition at all, so authoring worked from an English gloss and a part of speech and reasoned back into Tamil. The Tamil Wiktionary content dump (`ta-wiktionary-content`) ends that: 92,731 of its 98,107 wholly Tamil single-token titles carry a Tamil sense, and 77,558 of the 137,991 headwords now have a `definitionTa` fact in the store against 6,269 before - a factor of twelve.

The no-verbatim rule is not weakened by it. A wiki sense line is still a person's sentence, so it is retained as evidence and an authored meaning is written FROM it; what changed is that the evidence is now in the language the meaning has to be written in. Concretely:

| Fact | What it is | Where it goes |
| --- | --- | --- |
| `definitionTa` from a wiki page | one editor's sentence about the word | store-only evidence, the best authoring input the project has |
| `synonym` from a wiki page | a Tamil equivalent - a fact about the language, not a sentence | publishable, and SENSE-SCOPED by the page it came from |
| `pos` from a wiki page | a part of speech | publishable; 67,232 headwords gained one |
| `translation` from a wiki page | a free-text English list, one editor at a time | last in precedence, so it loses the single display slot to every curated dictionary |

The synonym line is the one worth dwelling on, because the column it feeds was the weakest thing in the lexicon. The English-Tamil dictionary is read SIDEWAYS - every Tamil term filed under one English headword becomes an equivalent of every other - which groups by an English word and therefore mixes senses freely; it produced up to a thousand "synonyms" for one entry. A wiki synonym is scoped to the PAGE, which is scoped to the word, so it is the first sense-scoped synonym evidence in the inventory. Where the two disagree, the sideways read is the one to distrust.

## Running it

```
cd backend
python -m yen_tamizh_backend.wordsmith.llm_enrich
```

Validates the committed file against `config/lexicon-sources.json` and prints what the batch asserts. It exits non-zero naming the line and the rule any inadmissible row broke. After changing the file, record its new `bytes` and `sha256` in the registry in the same commit - EXTRACT re-verifies the digest on every run and refuses to proceed on a mismatch.

From there the file flows through the ordinary stages: `extract` turns each line into facts, `stage` merges them into the store, `publish` resolves them into the lexicon.

## The shape of one line

One JSON object per line, UTF-8 Tamil written as real characters rather than escapes - a human has to review these in a diff. Lines are sorted by `word` ascending and each word appears once, so a later batch INSERTS lines rather than reshuffling the file.

| Field | Required | What it is |
| --- | --- | --- |
| `word` | yes | The Tamil surface, NFC-normalized, no whitespace |
| `definitionTa` | no | An explanatory Tamil phrase - the summary line and the paid meaning rung |
| `synonymsTa` | no | Tamil equivalents, sorted, never containing the word itself |
| `translationEn` | no | One English equivalent |
| `pos` | no | Parts of speech from the closed `PartOfSpeech` vocabulary, sorted |
| `categories` | no | Themes from the closed alias-normalized set, sorted |
| `model` | yes | Which model authored the row |
| `promptVersion` | yes | The date-stamp of the authoring instructions on THIS page |
| `authoredOn` | yes | When the row was written |

Every optional field is omitted rather than emptied: an empty list is a value that says nothing, and the reader refuses one.

`pos` and `categories` bypass `posAliases` and `categoryAliases` deliberately. Those maps exist to translate a third-party source's own orthography into the closed vocabularies; an authored row writes the closed vocabularies natively, so there is nothing to translate, and the validator rather than a map is what refuses anything outside them.

## The provenance fields are never rendered

`model`, `promptVersion` and `authoredOn` are build-time provenance. They are not published columns and no Game renders them. An "AI-written" mark on some meanings makes a player distrust all of them, including the dictionary's, so there is no badge, no model name and no prompt version anywhere a player can see.

What they buy is diffability: a re-ask under revised instructions is a new batch with a new `promptVersion`, distinguishable from an earlier one without re-reading either.

## The evidence tiers - and the one that is not authored

Authoring is bounded to the rows that can actually be SERVED: `wordClass == headword`, with the attestation and frequency gates already satisfied. Within that set, what evidence a row carries decides whether it can be authored at all:

| Tier | Evidence the store holds |
| --- | --- |
| E1 | A Tamil sense from the wiki, an English definition, or a dictionary's Tamil sense prose |
| E2 | An English translation AND a part of speech |
| E3 | An English translation only |
| E4 | Only a synonym group, read sideways out of the English-Tamil dictionary |
| E5 | Nothing but the Tamil string and its frequency |

**E5 rows are not authored.** No translation, no part of speech, no synonym set and no sense prose means there is nothing to author FROM, and writing a meaning anyway is guessing from orthography. The lexicon already forbids that for themes, where a wrong guess costs a player one paid hint; it must bind harder on the meaning, which is both the summary line and the most expensive rung on the ladder.

Measured over the bounded set before row 4b, E3, E4 and E5 were all EMPTY, and that was structural rather than lucky: the word-hood classifier only calls a surface a headword when a tier-1 authority listed it as an entry, and those authorities each also supply either a definition or a translation. Row 4b moves the distribution rather than the rule - a wiki sense is E1 evidence, so tens of thousands of rows that would have been authored from an English gloss alone can now be authored from a Tamil one.

## Cross-validate before you author

Having several dictionaries is only worth something if they are COMBINED. Taking whichever source happens to answer first, authoring from that, and reporting the union is not lexicography - it is a lucky draw wearing a citation.

So authoring reads the store PER WORD and PER SOURCE, not per attribute. Every candidate arrives carrying every fact every source holds about it:

| Evidence | Where it comes from |
| --- | --- |
| `definitionTa` | the Tamil Wiktionary's own sense lines and explanation sections |
| `translation` | the English-Tamil dictionary read forward, the curated dictionary's own English column, and the wiki's translation arm |
| `synonym` | the bilingual dictionary read SIDEWAYS - every Tamil term sharing an English headword and part-of-speech prefix - and the wiki's own synonym sections, which are sense-scoped and therefore the more trustworthy of the two |
| `definitionEn` | Wiktextract's sense prose |
| `pos` | any of the lexicographic authorities |
| `category` | the themed vocabulary |
| `frequency`, `spokenRatio` | the nine frequency corpora, summed and split |

**Where the sources DISAGREE, record it - a disagreement is a signal, not noise.** Two authorities giving a word two unrelated English glosses is usually a genuine homograph, and the meaning that gets authored has to name the sense the frequency evidence supports rather than silently averaging them. A gloss that no other source recognises, on a word every corpus attests, is more often a defect in that one source than a rare sense; the sideways synonym read is the usual culprit, because grouping by an English headword mixes senses freely.

Cross-validation is also what makes the no-hedge rule operable rather than aspirational. One source asserting a meaning is a claim; two independent authorities agreeing on it is the confidence the rule asks for, and a candidate whose sources cannot be reconciled is declined rather than averaged.

## The priority order

Author in this order and stop at the budget. It is a priority order rather than a preference because every rung above the next carries strictly more player-visible value per row.

1. **3-6 ezhuthu headwords passing the serving gates.** They are the only rows a Game can serve today, so they carry all of the player-visible value. Everything else is inventory.
2. **Highest frequency first.** Selection draws frequency-stratified, and the top quartile is the vocabulary a player actually holds. Frequency-first ordering also buys the most coverage per row authored: the head of the distribution is short.
3. **Best evidence tier first** - E1, then E2, then E3 and E4. A row with sense prose can be authored faster and more accurately than one with a bare translation, so the same effort buys more meanings and fewer declines.
4. **Then 7-10 ezhuthu, same ordering**, if budget remains.

## Defer, never drop

A candidate this pass did not author is DEFERRED, never dropped. It keeps every fact the store holds about it, it stays in the store, and the next pass finds it exactly where this one left it. Nothing is deleted to make a coverage number look better.

The distinction is the whole reason EXTRACT and STAGE never filter: the store is the retention layer, and what is SERVED is a decision taken downstream against gates that can be re-run. A deferred word costs nothing but the row it already occupies; a dropped word costs a re-acquisition of gitignored bytes and a full re-run to recover. So a batch reports its deferred count BY BAND alongside its authored count, and both are first-class outputs.

A DECLINE is different from a defer and is also reported: a decline is a candidate that was read, weighed against its evidence, and refused because no meaning could be authored confidently. The commonest cause is a form whose only available sense is a grammatical relation to another word.

## The no-hedge rule

A word whose Tamil meaning cannot be authored confidently gets NO `definitionTa` rather than a hedged one. The row still exists, still carries whatever else is known about it, and simply fails the `requireMeaning` serving gate - so nobody is ever shown it.

This is not caution for its own sake. A wrong meaning on the summary screen reads as a broken game. A wrong meaning the player PAID an attempt for, and then reasoned from, is the game lying and charging for it.

The rule has a second edge worth stating, because it is where most declines actually come from: a form whose only available sense is a grammatical relation to another word - "the adverbial participle of X" - has no meaning to author. Restating the grammar tells a player nothing about which word to build, so those rows are declined too, and the effect is that a large family of inflected forms the classifier let through as headwords never reaches a player.

## The review loop

Review is bounded by CONSUMPTION, not by volume: only rows that can reach a player need it. Review is PER-ROW, not per-field - a reviewed row becomes `categorySource: reviewed` AND `meaningSource: reviewed` together, because a human who checked the meaning read the theme on the same line.

Until a human reviews a row:

- its authored values may still render FREE on the summary screen;
- they may NOT be sold as a paid hint;
- and its authored attestation does not count toward the attestation gate. An unreviewed model row cannot be the evidence that a model row is real.

A human review is itself an attestation act, which is what flips all three.

## Authoring instructions - `promptVersion` 2026-08-16

This section IS the prompt. Changing it means date-stamping a new `promptVersion` and recording it on the rows written under it. The `2026-08-15` revision is what the first batch was written under; `2026-08-16` adds rules 2, 9 and 10 - cross-validation across every authority, the disagreement rule, and the explicit defer.

1. Author only within the bounded set, in the priority order above. Those are the rows a player can actually be served.
2. Read EVERY source's facts for the word before writing anything, not the first one that answers. Where two authorities agree, the meaning is settled. Where they disagree, decide which sense the frequency evidence supports and author THAT sense; do not blend them.
3. Condition on the retained evidence - the English definition, the translation, the part of speech, the synonym group. Never on the shape of the Tamil string.
4. Write `definitionTa` as an explanatory Tamil PHRASE, not a sentence and not a single word. It should let a Tamil speaker who does not know the word arrive at it.
5. Never let the meaning contain the word it explains, and never list a word as its own synonym. Both hand over the whole puzzle.
6. Take `synonymsTa` only from terms that share the SENSE being defined. The sideways read of a bilingual dictionary groups by the English headword, so it mixes senses freely and most of what it offers is wrong for any one of them.
7. Give `pos` on every row you touch. Dictionary POS covers a small minority of surfaces, and without authored POS the part-of-speech selection dimension has almost nothing to work with.
8. Give `categories` only when a theme in the closed set genuinely applies, and choose it from the GLOSS rather than the Tamil string. Never mint a theme - a theme is player-facing copy and minting one is a human decision.
9. If you are not confident, omit the field, and if no field can be written confidently, DECLINE the row. A decline is a first-class outcome and is reported as a number, not hidden.
10. Whatever the batch does not reach is DEFERRED, not dropped. Report the deferred count by band. The store keeps every one of them for the next pass.

## See also

- [../architecture/lexicon/pipeline.md](../architecture/lexicon/pipeline.md) - the four stages and why the authored file is an input rather than a stage.
- [../architecture/lexicon/word-hood.md](../architecture/lexicon/word-hood.md) - which surfaces are eligible to be authored at all.
- [../concepts/lexicon.md](../concepts/lexicon.md) - `meaningSource`, `categorySource`, and why a definition is never republished verbatim.
- [add-a-lexicon-source.md](add-a-lexicon-source.md) - registering any other source, all of which are acquired rather than authored.
- [../../CLAUDE.md](../../CLAUDE.md) - Holy Law #1 (no runtime backend, so no API client), #7 (no mocks), #8 (no new dependency without a named beneficiary).
