"""The derived-wordlist registry contract (Row 9).

``config/derived-wordlists.json`` is the declarative registry the derive step
reads. It is the whole extensibility story for the DERIVED layer, mirroring what
``config/corpus-sources.json`` is for the corpus layer: adding another Game's
wordlist is a DATA change here plus a re-run of ``rebuild_wordlists`` - never a
code rewrite, and never a change to the corpus above it or to the daily puzzle
engine below it (corpus -> derived per-Game sets -> daily puzzles).

The selection knobs live here rather than as literals in ``corpus/derive.py``
because they are tunable game-balance numbers (Holy Law #6): which ezhuthu
lengths make a good puzzle and which frequency bands a player actually knows are
design decisions, and a designer must be able to move them without touching
Python. What stays in code is the MECHANISM that interprets them. A Game whose
set needs a predicate these knobs cannot express is the one case that costs code
- the same line the corpus layer draws at an unseen source FORMAT.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import GameId
from yen_tamizh_backend.contracts.corpus_sources import RelPath
from yen_tamizh_backend.contracts.master_wordlist import FreqBand


class DerivedSelection(BaseModel):
    """Which master words a derived set keeps. Every knob is tunable data.

    ``minLength`` / ``maxLength`` count EZHUTHU, not code points - the unit every
    Game plays in (Row 6). ``bands`` names the ``freqBand`` values a player is
    expected to know. ``requireCoAnagram`` keeps only words whose ezhuthu
    multiset is shared with at least one other master word, which is what
    guarantees an unscramble has real tension. ``maxWords`` caps the committed
    artifact (``null`` means uncapped); a derived set is a build artifact in git,
    so an uncapped one is an unbounded commit.

    This model is shared: the registry declares it and the emitted wordlist
    echoes back the selection that produced it, so a reviewer reading a diff can
    see which knob moved. Defining it once is why the two cannot disagree.
    """

    model_config = ConfigDict(extra="forbid")

    minLength: int = Field(ge=1)
    maxLength: int = Field(ge=1)
    bands: list[FreqBand] = Field(min_length=1)
    requireCoAnagram: bool = False
    maxWords: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _selection_is_coherent(self) -> Self:
        if self.minLength > self.maxLength:
            raise ValueError(
                f"minLength {self.minLength} must be <= maxLength {self.maxLength}"
            )
        if len(set(self.bands)) != len(self.bands):
            raise ValueError(f"bands has a repeated entry: {self.bands}")
        return self


class DerivedSet(BaseModel):
    """One registered per-Game derived set: who consumes it and where it lands."""

    model_config = ConfigDict(extra="forbid")

    gameId: GameId
    out: RelPath
    selection: DerivedSelection
    note: str | None = None


class DerivedWordlists(SchemaModel):
    """The registry: one master in, one derived set out per registered Game."""

    masterPath: RelPath
    sets: list[DerivedSet] = Field(min_length=1)

    @model_validator(mode="after")
    def _sets_are_distinct(self) -> Self:
        # A repeated gameId or output path means one set silently overwrites
        # another - a whole Game's wordlist vanishing without an error.
        for field_name in ("gameId", "out"):
            seen = [getattr(entry, field_name) for entry in self.sets]
            if len(set(seen)) != len(seen):
                raise ValueError(f"derived sets have a repeated {field_name}")
        return self
