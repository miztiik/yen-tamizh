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

Rows 8 and 9 extend this file with their own sections; the exact signals of
Row 7 own what is here.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yen_tamizh_backend.contracts.base import ChangelogEntry, SchemaModel
from yen_tamizh_backend.contracts.common import SourceId

# The initial mint. The file that will carry this schema is written by hand, so
# the date-stamp and its first changelog entry live here: two writers of one
# schema picking their own dates is the drift CLAUDE.md section 11 exists to
# stop. Migration class is build-time rewrite-in-place.
WORDHOOD_VERSION = "2026-08-15"
WORDHOOD_CHANGELOG = (
    ChangelogEntry(
        version=WORDHOOD_VERSION,
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


class Wordhood(SchemaModel):
    """The word-hood layer's knobs. Read by ENRICH, never by the browser."""

    orthotactic: OrthotacticWeights
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
