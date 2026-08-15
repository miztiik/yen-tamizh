# Enrich the lexicon

**Last Updated**: 2026-08-15

How the Tamil meanings, synonyms, English translations, parts of speech and themes that a player eventually reads get written, reviewed and committed. The four stages this feeds are in [../architecture/lexicon/pipeline.md](../architecture/lexicon/pipeline.md); what the words mean is [../concepts/lexicon.md](../concepts/lexicon.md); which surfaces are word-hood-eligible in the first place is [../architecture/lexicon/word-hood.md](../architecture/lexicon/word-hood.md).

## The model is a source, not a stage

No source in the inventory supplies an attested Tamil definition. A dictionary's Tamil sense text is a lexicographer's prose, and prose is retained as build-time evidence and never republished ([../concepts/lexicon.md](../concepts/lexicon.md)). So every published `definitionTa` is **authored** - written by the agent executing the pipeline, from the evidence the store already holds - and the result is committed as an ordinary lexicon source at `datasets/lexicon/sources/llm-authored/entries.jsonl`.

There is no API client anywhere in the pipeline, no key, and no new dependency. `wordsmith/llm_enrich.py` reads and validates that committed file; it never calls a model. This is not squeamishness about network access - it is what makes the pipeline reproducible at all. A model asked the same question twice may answer differently, so it can never sit inside a stage whose Oracle is byte-identity. A committed file can: the same bytes produce the same facts on every run, on every machine, forever, and a bad batch is visible in a per-line diff and revertible by one commit.

The file is therefore raw INPUT, exactly like the nineteen acquired sources, which is why it has no generated JSON Schema. What makes a source trustworthy here is its reader failing loudly at the boundary, and `llm_enrich.py` is that reader. It is the ONE source whose bytes are committed rather than gitignored, so it also has no acquisition ledger row and no fixture slice - the real file is always on disk and is what the tests exercise.

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
| E1 | An English definition, or Tamil sense prose |
| E2 | An English translation AND a part of speech |
| E3 | An English translation only |
| E4 | Only a synonym group, read sideways out of the English-Tamil dictionary |
| E5 | Nothing but the Tamil string and its frequency |

**E5 rows are not authored.** No translation, no part of speech, no synonym set and no sense prose means there is nothing to author FROM, and writing a meaning anyway is guessing from orthography. The lexicon already forbids that for themes, where a wrong guess costs a player one paid hint; it must bind harder on the meaning, which is both the summary line and the most expensive rung on the ladder.

Measured over the current bounded set, E3, E4 and E5 are all EMPTY, and that is structural rather than lucky. The word-hood classifier only calls a surface a headword when one source supplied both a headword fact and a describing fact, and the two sources that can do that both also supply either a definition or a translation. So today every authorable row is E1 or E2, and the E5 rule has nothing to exclude. That will change the moment a bare-word-list source is promoted, which is exactly when the rule earns its place.

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

## Authoring instructions - `promptVersion` 2026-08-15

This section IS the prompt. Changing it means date-stamping a new `promptVersion` and recording it on the rows written under it.

1. Author only within the bounded set, highest frequency first. Those are the rows a player can actually be served.
2. Condition on the retained evidence - the English definition, the translation, the part of speech, the synonym group. Never on the shape of the Tamil string.
3. Write `definitionTa` as an explanatory Tamil PHRASE, not a sentence and not a single word. It should let a Tamil speaker who does not know the word arrive at it.
4. Never let the meaning contain the word it explains, and never list a word as its own synonym. Both hand over the whole puzzle.
5. Take `synonymsTa` only from terms that share the SENSE being defined. The sideways read of a bilingual dictionary groups by the English headword, so it mixes senses freely and most of what it offers is wrong for any one of them.
6. Give `pos` on every row you touch. Dictionary POS covers a small minority of surfaces, and without authored POS the part-of-speech selection dimension has almost nothing to work with.
7. Give `categories` only when a theme in the closed set genuinely applies, and choose it from the GLOSS rather than the Tamil string. Never mint a theme - a theme is player-facing copy and minting one is a human decision.
8. If you are not confident, omit the field. A decline is a first-class outcome and is reported as a number, not hidden.

## See also

- [../architecture/lexicon/pipeline.md](../architecture/lexicon/pipeline.md) - the four stages and why the authored file is an input rather than a stage.
- [../architecture/lexicon/word-hood.md](../architecture/lexicon/word-hood.md) - which surfaces are eligible to be authored at all.
- [../concepts/lexicon.md](../concepts/lexicon.md) - `meaningSource`, `categorySource`, and why a definition is never republished verbatim.
- [add-a-lexicon-source.md](add-a-lexicon-source.md) - registering any other source, all of which are acquired rather than authored.
- [../../CLAUDE.md](../../CLAUDE.md) - Holy Law #1 (no runtime backend, so no API client), #7 (no mocks), #8 (no new dependency without a named beneficiary).
