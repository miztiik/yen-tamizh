"""The ezhuthu n-gram model behind the ``ngram`` signal (Row 8).

A character-level model where the CHARACTER is the ezhuthu, not the code point.
Tamil writes a vowel after a consonant as a mark ON that consonant, so a
code-point model would be learning the spelling of a syllable rather than the
sequence of syllables - which is the thing that is actually constrained.

WHAT the signal catches, and why the training set is filtered the way it is, is
``docs/architecture/lexicon/word-hood.md``. This module is only the model.

Three properties it has to have, and each one costs a design decision:

1. **It is trained only on headwords an authority attested, and only on the
   ones that are wholly Tamil.** Training on the scraped corpus would teach it
   the typos it exists to flag; training on every attested headword would do
   the same more quietly, because 21.8 percent of them carry a Latin letter, a
   digit or a scrape artifact.
2. **It is recomputed from the staged zone on every run and never committed.**
   It is a pure function of that zone, so a committed copy is a second thing to
   keep in sync for no benefit.
3. **It is deterministic.** Counts are integers, the smoothed probabilities are
   a fixed arithmetic expression over them, and a word's score sums its
   log-probabilities in sequence order. Nothing depends on dictionary order or
   on how many words happened to be trained on first.

The score is reported as the geometric-mean per-ezhuthu probability - the
reciprocal of the perplexity - so it lands in ``(0, 1]`` like ``orthotactic``,
is comparable between a three-ezhuthu word and a ten-ezhuthu one, and points the
same way as every other signal: higher is more word-like.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Final

from yen_tamizh_backend.ezhuthu import segment

# Sentinels for the two word boundaries. They are separate symbols because they
# constrain different things - which ezhuthu may OPEN a word is a different rule
# from which may END one - and a single shared boundary symbol would blur the
# two into one distribution. Neither can collide with an ezhuthu: both are
# control characters, and segmentation never emits one from Tamil text.
START: Final = "\x02"
END: Final = "\x03"

# Every ezhuthu the training set never used. A surface holding Latin, a digit or
# a scrape artifact maps every one of those units here, which is what makes such
# a surface score near zero instead of raising.
UNKNOWN: Final = "\x04"

Ngram = tuple[str, ...]


@dataclass(frozen=True, slots=True)
class NgramModel:
    """A smoothed n-gram model over ezhuthu, ready to score.

    The log-probabilities are precomputed at training time rather than derived
    per call: the signal runs over 6.25M surfaces, so the scoring path is a
    dictionary probe and an addition and nothing else.
    """

    order: int
    smoothing: float
    vocabulary: int
    words: int
    units: int
    # The ezhuthu the training set actually used. A unit outside it is folded
    # to UNKNOWN at scoring time, which is what lets a surface holding Latin or
    # a digit be SCORED - very low - rather than raise.
    alphabet: frozenset[str]
    # log10 P(unit | context) for every n-gram the training set actually saw.
    logProbability: Mapping[Ngram, float]
    # log10 P(an unseen unit | context), for every context it saw.
    unseenUnit: Mapping[Ngram, float]
    # log10 P(anything | a context it never saw): the uniform fallback.
    unseenContext: float

    def note(self) -> str:
        return (
            f"order={self.order} words={self.words} units={self.units} "
            f"vocabulary={self.vocabulary} ngrams={len(self.logProbability)}"
        )


def _padded(order: int, body: tuple[str, ...]) -> tuple[str, ...]:
    return (START,) * (order - 1) + body + (END,)


@dataclass(frozen=True, slots=True)
class _Counts:
    ngram: dict[Ngram, int]
    context: dict[Ngram, int]
    alphabet: set[str]
    words: int
    units: int


def _count(training: Iterable[str], order: int) -> _Counts:
    ngram: dict[Ngram, int] = {}
    context: dict[Ngram, int] = {}
    alphabet: set[str] = set()
    words = 0
    units = 0
    for word in training:
        body = tuple(segment(word))
        if not body:
            continue
        words += 1
        units += len(body)
        alphabet.update(body)
        padded = _padded(order, body)
        for index in range(order - 1, len(padded)):
            key = padded[index - order + 1 : index + 1]
            ngram[key] = ngram.get(key, 0) + 1
            head = key[:-1]
            context[head] = context.get(head, 0) + 1
    return _Counts(
        ngram=ngram, context=context, alphabet=alphabet, words=words, units=units
    )


def train(training: Iterable[str], order: int, smoothing: float) -> NgramModel:
    """Fit the model over ``training``, one word at a time.

    ``training`` is streamed rather than listed: it arrives from a store cursor
    over several hundred thousand headwords, and the counts are all that has to
    survive the pass.
    """
    if order < 2:
        raise ValueError(f"order must be at least 2 to model a sequence, not {order}")
    if smoothing <= 0.0:
        raise ValueError(f"smoothing must be positive, not {smoothing}")
    counts = _count(training, order)
    if not counts.words:
        raise ValueError("the n-gram training set is empty - nothing to fit")
    # END is predictable and UNKNOWN has to be reachable, so both sit in the
    # vocabulary the smoothing mass is spread over. START never is: it is only
    # ever context, never a prediction.
    vocabulary = len(counts.alphabet) + 2
    mass = smoothing * vocabulary
    logProbability = {
        key: math.log10((value + smoothing) / (counts.context[key[:-1]] + mass))
        for key, value in counts.ngram.items()
    }
    unseenUnit = {
        key: math.log10(smoothing / (total + mass))
        for key, total in counts.context.items()
    }
    return NgramModel(
        order=order,
        smoothing=smoothing,
        vocabulary=vocabulary,
        words=counts.words,
        units=counts.units,
        logProbability=logProbability,
        unseenUnit=unseenUnit,
        unseenContext=math.log10(1.0 / vocabulary),
        alphabet=frozenset(counts.alphabet),
    )


def score(model: NgramModel, word: str) -> float:
    """How likely ``word``'s ezhuthu sequence is, in ``(0, 1]``.

    The geometric mean of the per-ezhuthu probabilities - one over the model's
    perplexity on this word - so that length does not decide the answer and a
    long clean word does not score below a short broken one.
    """
    body = tuple(segment(word))
    if not body:
        return 0.0
    alphabet = model.alphabet
    folded = tuple(unit if unit in alphabet else UNKNOWN for unit in body)
    padded = _padded(model.order, folded)
    total = 0.0
    predictions = 0
    for index in range(model.order - 1, len(padded)):
        key = padded[index - model.order + 1 : index + 1]
        found = model.logProbability.get(key)
        if found is None:
            found = model.unseenUnit.get(key[:-1], model.unseenContext)
        total += found
        predictions += 1
    return math.pow(10.0, total / predictions)
