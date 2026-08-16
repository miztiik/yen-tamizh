"""The word-hood knobs (Row 7): what each signal's evidence is WORTH.

``config/wordhood.json`` is what ENRICH reads. It holds the tunable half of the
word-hood layer and nothing else - the letter rules themselves are facts about
Tamil and live in ``backend/yen_tamizh_backend/ezhuthu/word_shape.py``, because
a fact about the script is not a knob (Holy Law #6 governs knobs; this is the
same line the part-of-speech vocabulary draws against its alias map).

What the signals ARE, and what each one catches, is
``docs/architecture/lexicon/word-hood.md``.

Two kinds of entry, and the split is deliberate:

- **weights** decide what an orthotactic defect costs;
- **source lists** name which registered source carries a ready-made judgement.
  They are ids rather than roles because "which list holds the Nannul verdict"
  is a fact about the inventory we happen to have acquired, not about the
  language - and an id that is not staged is a typo that would otherwise
  produce an all-zero signal in silence, so ENRICH checks it against the store.

Row 8 added the two sections the inexact signals need, and one of those knobs is
not like the others: ``maxEditDistance`` is capped in the SCHEMA as well as in
the code, because raising it is not a tuning decision. At two the deletion
neighbourhood is millions of entries and the pass is minutes; at three it is two
and a half times as many entries and hours, so the ceiling belongs where a
hand-edited file cannot step over it.

Row 9 added the ``classifier`` section - the order the classifier resolves
contradictory source assertions in, what makes a listing an ENTRY, and the two
profiles that separate a modern word the dictionaries missed from a misspelling.
"""

from __future__ import annotations

from typing import Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yen_tamizh_backend.contracts.base import ChangelogEntry, SchemaModel
from yen_tamizh_backend.contracts.common import SourceId
from yen_tamizh_backend.contracts.lexicon_sources import WordClassEvidence

# The initial mint. The file that will carry this schema is written by hand, so
# the date-stamp and its first changelog entry live here: two writers of one
# schema picking their own dates is the drift CLAUDE.md section 11 exists to
# stop. Migration class is build-time rewrite-in-place.
WORDHOOD_VERSION = "2026-08-16T22:00"
WORDHOOD_CHANGELOG = (
    ChangelogEntry(
        version=WORDHOOD_VERSION,
        change="Ranked notAWord first in classifier.evidencePriority.",
        why=(
            "Row 9b - a lexicographic source routing a surface's only "
            "part-of-speech verdict to reject notAWord has DENIED that the "
            "unit is a word, and the priority list must rank every evidence "
            "value exactly once. First, because it is the only value that "
            "answers whether this is a word at all rather than what KIND of "
            "word it is: a letter of the alphabet is not a proper noun with an "
            "unusual shape, and no other source's bare headword listing "
            "outweighs the dictionary that looked at it and said it is a "
            "character."
        ),
    ),
    ChangelogEntry(
        version="2026-08-16",
        change=(
            "Replaced classifier.entryAttrs with classifier.notAWord - the "
            "maximum ezhuthu length, the minimum distinct ezhuthu, and whether "
            "a non-Tamil unit rejects the surface outright."
        ),
        why=(
            "Row 9a - what makes a listing an ENTRY is now the source's "
            "declared attestationTier rather than a describing fact from the "
            "same row, so entryAttrs had no reader left and a knob nothing "
            "reads is a lie in the config. The notAWord precondition needs "
            "three thresholds, and every one of them is a tunable judgement "
            "rather than a fact about Tamil (Holy Law #6)."
        ),
    ),
    ChangelogEntry(
        version="2026-08-15T16:00",
        change=(
            "Added the classifier section: entryAttrs, evidencePriority, "
            "headwordMinOrthotactic, and the discovery and typo profiles."
        ),
        why=(
            "Row 9 - the classifier turns the eight signals into one wordClass, "
            "and which evidence outranks which, what makes a listing an entry, "
            "and where the discovery and typo profiles sit are all tunable "
            "judgements rather than facts about Tamil (Holy Law #6)."
        ),
    ),
    ChangelogEntry(
        version="2026-08-15T14:00",
        change=(
            "Added the ngram section (model order and smoothing) and the "
            "neighbour section (maxEditDistance, capped at 2, and the breadth "
            "at which a surface stops being queried)."
        ),
        why=(
            "Row 8 - the three inexact word-hood signals need a model order, a "
            "smoothing constant, a search radius and a prune threshold, and "
            "every one of those is a tunable judgement rather than a fact "
            "about Tamil (Holy Law #6)."
        ),
    ),
    ChangelogEntry(
        version="2026-08-15",
        change=(
            "Initial word-hood config: the orthotactic weights and the source "
            "lists behind the nannulValid and knownVerbForm signals."
        ),
        why=(
            "Row 7 - the five exact word-hood signals need thresholds, and "
            "every threshold is config rather than a Python literal "
            "(Holy Law #6), which makes the file a persisted surface and so a "
            "schema (Holy Law #3)."
        ),
    ),
)

# The deletion neighbourhood's ceiling, mirrored from
# ``wordsmith/neighbours.py`` so the schema refuses what the code refuses. Two
# statements of one number rather than an import, because a contract module
# reaching into a pipeline module for a bound would invert the dependency.
MAX_EDIT_DISTANCE = 2

_EVIDENCE_CLASSES: tuple[WordClassEvidence, ...] = get_args(WordClassEvidence)


class OrthotacticWeights(BaseModel):
    """What each orthotactic defect costs the signal's score.

    The score is ``1.0`` minus the weights of the rules a surface breaks, so a
    clean word scores 1 and one that breaks everything scores 0. Three weights
    rather than one, because the defects are not interchangeable: a surface that
    cannot even OPEN like a Tamil word is a loanword or a fragment, while one
    that merely ends wrong is usually a sandhi artifact, and a classifier that
    wants to tell those apart needs them priced apart.

    ``granthaPenalty`` defaults to zero on purpose. Grantha letters were
    borrowed to write Sanskrit and foreign sounds, so carrying one is positive
    evidence of a LOANWORD rather than a defect, and pricing it as damage would
    tell the classifier the opposite of what the fact means. It is a knob rather
    than a constant so that judgement stays reviewable in config.
    """

    model_config = ConfigDict(extra="forbid")

    initialWeight: float = Field(ge=0.0, le=1.0)
    finalWeight: float = Field(ge=0.0, le=1.0)
    clusterWeight: float = Field(ge=0.0, le=1.0)
    granthaPenalty: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _defects_cannot_cost_more_than_the_whole_score(self) -> Self:
        # Rejected rather than clamped: a configuration whose weights overrun
        # the score silently flattens every defective surface onto zero, and
        # then no threshold downstream can tell them apart again.
        total = self.initialWeight + self.finalWeight + self.clusterWeight
        if total > 1.0:
            raise ValueError(
                f"the three orthotactic weights sum to {total}, which is more "
                f"than the score they are subtracted from"
            )
        return self


class NgramSettings(BaseModel):
    """How the ezhuthu sequence model is fitted (Row 8).

    ``order`` is how much context a prediction sees. Two is a bigram and models
    almost nothing about Tamil's cluster rules; five over a 250-ezhuthu alphabet
    is mostly unseen contexts falling back to the smoothing mass, which measures
    the model rather than the word. Three is the default and the range is closed
    around what is defensible.

    ``smoothing`` is the count added to every possible continuation before the
    probabilities are taken. It has to be positive: at zero a single ezhuthu the
    dictionary never happened to follow makes the whole word impossible, and an
    impossible word has no comparable score.
    """

    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=2, le=5)
    smoothing: float = Field(gt=0.0, le=1.0)


class NeighbourSettings(BaseModel):
    """How far the nearest-headword search looks, and what it skips (Row 8).

    ``maxEditDistance`` is capped at two by the schema itself. It is the one
    knob here whose ceiling is not a preference: the deletion neighbourhood
    grows two and a half times and the pass grows from minutes to hours at
    three, so a config typo has to fail on load rather than run all afternoon.
    The pipeline asserts the same bound again before it builds anything.

    ``pruneBreadth`` is the number of distinct sources at which a surface stops
    being queried at all. The signal's only consumer is the ``suspectedTypo``
    verdict, and a surface several independent sources agree on is not one - so
    querying it would buy nothing and cost the largest pass in the stage.
    """

    model_config = ConfigDict(extra="forbid")

    maxEditDistance: int = Field(ge=1, le=MAX_EDIT_DISTANCE)
    pruneBreadth: int = Field(ge=1)


class DiscoveryProfile(BaseModel):
    """What a modern word the dictionaries MISSED looks like (Row 9).

    A surface that is orthotactically clean, seen by several independent
    sources, sits well under the sequence model and is still unattested is not
    junk - that profile is a real word the acquired dictionaries are simply too
    old or too thin to hold. It goes to the enrichment queue, and the reason the
    profile is written down at all is that it must never be read as a
    misspelling on the way there.
    """

    model_config = ConfigDict(extra="forbid")

    minOrthotactic: float = Field(ge=0.0, le=1.0)
    minBreadth: int = Field(ge=1)
    minNgram: float = Field(gt=0.0, le=1.0)


class TypoProfile(BaseModel):
    """What a misspelling looks like (Row 9).

    ``minNeighbour`` is the reciprocal edit distance at which a real word is
    close enough that this surface is probably a slip of it: one means a
    headword exactly one ezhuthu away, a half means two. There is deliberately
    no breadth bound here - the neighbour signal is only MEASURED where Row 8's
    prune admitted the surface, so a widely-seen surface arrives carrying NULL
    and the profile cannot fire on it. Restating the bound would let the two
    drift apart.

    ``maxNgram`` is the other half, and it is what stops the profile accusing
    ordinary Tamil. A near neighbour ALONE is not evidence of a slip: an
    agglutinative language generates real forms one ezhuthu apart by the
    thousand. What a typo also is, is IMPROBABLE - and the sequence model is the
    signal that says so. It is a separate knob from the discovery floor even
    where the two happen to share a value, because they answer different
    questions and tuning one must not silently move the other.
    """

    model_config = ConfigDict(extra="forbid")

    minNeighbour: float = Field(gt=0.0, le=1.0)
    maxNgram: float = Field(gt=0.0, le=1.0)


class NotAWordProfile(BaseModel):
    """What makes a surface not a Tamil word at all (Row 9a).

    The classifier's PRECONDITION, weighed before any signal and before any
    source assertion. A statement about the STRING outranks a statement about
    the word it is not: a scraped paragraph tagged as a name is still a scraped
    paragraph, and letting the tag win is how junk comes to wear a real class.

    All three are thresholds rather than facts about Tamil, so all three are
    config (Holy Law #6). The letter rules that say which shapes Tamil BUILDS
    stay in ``ezhuthu/word_shape.py``; these say when a string is not a
    candidate for those rules to judge.

    ``maxEzhuthu`` is a length ceiling. Tamil compounds freely, so there is no
    grammatical bound to appeal to - what is bounded is the length beyond which
    every surface inspected was a scrape that lost its spaces, and the longest
    in the real store runs to 1,212 ezhuthu.

    ``minDistinctEzhuthu`` applies only to a surface of more than one ezhuthu:
    a one-ezhuthu word obviously holds one distinct ezhuthu and is a perfectly
    ordinary Tamil word. What it rejects is the same character repeated - a
    keyboard artifact or a run of the aytham, never a word.

    ``rejectNonTamil`` is what a unit that is not an ezhuthu at all - Latin, a
    digit, a space, punctuation - costs. It is a knob rather than a constant
    because it is the one clause that could reasonably be turned off: a project
    that wanted to keep transliterations as their own class would set it false
    and get the Row 9 behaviour back, where such a surface is judged by
    orthography and lands in ``suspectedTypo``.
    """

    model_config = ConfigDict(extra="forbid")

    maxEzhuthu: int = Field(ge=1)
    minDistinctEzhuthu: int = Field(ge=1)
    rejectNonTamil: bool


class ClassifierSettings(BaseModel):
    """How the eight signals become exactly one ``wordClass`` (Row 9).

    ``evidencePriority`` orders the classes a source may assert when two sources
    assert different ones. It must be a permutation of the whole evidence
    vocabulary - a partial list would leave an assertion with no rank, and the
    verdict would then depend on which fact SQLite happened to return first.

    What makes a listing an ENTRY is NOT here. It is the asserting source's
    declared ``attestationTier`` in ``config/lexicon-sources.json``, because
    what a source's unit IS is a property of the source and cannot be recovered
    from one row of it (Row 9a).
    """

    model_config = ConfigDict(extra="forbid")

    evidencePriority: list[WordClassEvidence]
    headwordMinOrthotactic: float = Field(ge=0.0, le=1.0)
    notAWord: NotAWordProfile
    discovery: DiscoveryProfile
    typo: TypoProfile

    @model_validator(mode="after")
    def _evidence_priority_ranks_every_class(self) -> Self:
        # Rejected rather than defaulted: an unranked assertion has no defined
        # winner, and a classifier whose verdict depends on row order is not a
        # classifier.
        if sorted(self.evidencePriority) != sorted(_EVIDENCE_CLASSES):
            raise ValueError(
                "evidencePriority must rank every wordClassEvidence value "
                f"exactly once - got {self.evidencePriority}"
            )
        return self


class Wordhood(SchemaModel):
    """The word-hood layer's knobs. Read by ENRICH, never by the browser."""

    orthotactic: OrthotacticWeights
    ngram: NgramSettings
    neighbour: NeighbourSettings
    classifier: ClassifierSettings
    # The sources whose membership IS the signal. Each list needs at least one
    # entry, because a signal with no producer is a column of zeros wearing a
    # name - the same reason the corpus layer refused to publish a `pos` field
    # nothing on disk could fill.
    nannulSources: list[SourceId] = Field(min_length=1)
    verbFormSources: list[SourceId] = Field(min_length=1)

    @model_validator(mode="after")
    def _source_lists_are_sets(self) -> Self:
        for field, values in (
            ("nannulSources", self.nannulSources),
            ("verbFormSources", self.verbFormSources),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"{field} names a source twice: {values}")
        return self
