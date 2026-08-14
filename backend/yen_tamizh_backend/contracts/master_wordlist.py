"""The ranked master wordlist contract (Row 8).

The master wordlist is the CORPUS layer's single output: every Tamil word the
ingest kept, segmented into ezhuthu (Row 6), ranked by merged frequency, and
banded. It lives in ``datasets/`` and is NEVER served - the game reads only the
per-Game sets derived from it (Row 9) and the puzzles the daily engine bakes
from those (Row 13). Keeping the layers apart is what lets a corpus refresh land
without rebuilding a Game.

The document carries its own provenance and ingest counters rather than a
sibling ``provenance.json``: a separate file describing the same run is a second
source of truth that can go stale, and embedding it makes the traceability
schema-validated by the same drift gate. The counters are the integrity Oracle -
``rowsIn - rejected - duplicates == distinct`` and
``distinct - belowFrequencyFloor - capped == rowsKept == len(words)`` - so a
silent drop cannot hide.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import RelPath, SourceId

# Rank-percentile bands, cut where config/corpus-sources.json says (Row 8).
FreqBand = Literal["common", "mid", "rare"]

_ISO_INSTANT = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
_SHA256 = r"^[0-9a-f]{64}$"


class MasterWord(BaseModel):
    """One ranked corpus word.

    ``length`` counts EZHUTHU, not code points: the ezhuthu is the unit every
    Game plays in, and a 3-ezhuthu word can be 5 code points long.
    """

    model_config = ConfigDict(extra="forbid")

    word: str = Field(min_length=1)
    ezhuthu: list[str] = Field(min_length=1)
    length: int = Field(ge=1)
    freqRank: int = Field(ge=1)
    freqBand: FreqBand
    sources: list[SourceId] = Field(min_length=1)
    category: list[str] | None = None

    @model_validator(mode="after")
    def _ezhuthu_rejoins_to_the_word(self) -> Self:
        # The integrity Oracle, enforced by the contract itself: segmentation is
        # non-destructive (Row 6), so a row whose parts do not rebuild its word
        # is corrupt and must never reach a derived set.
        if "".join(self.ezhuthu) != self.word:
            raise ValueError(f"ezhuthu does not rejoin to {self.word!r}")
        if self.length != len(self.ezhuthu):
            raise ValueError(
                f"length {self.length} != ezhuthu count {len(self.ezhuthu)} "
                f"for {self.word!r}"
            )
        return self


class SourceProvenance(BaseModel):
    """What one enabled source contributed, and which bytes it contributed from.

    ``sha256`` + ``bytes`` identify the exact input, so a later run can prove it
    read the same file. The user waived license classification for plain word
    lists; ``name`` + ``origin`` are the traceability record.
    """

    model_config = ConfigDict(extra="forbid")

    id: SourceId
    name: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    path: RelPath
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=_SHA256)
    rowsIn: int = Field(ge=0)
    rowsKept: int = Field(ge=0)


class IngestCounters(BaseModel):
    """The reconciliation ledger for one ingest run (no silent drops)."""

    model_config = ConfigDict(extra="forbid")

    rowsIn: int = Field(ge=0)
    rejected: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    distinct: int = Field(ge=0)
    belowFrequencyFloor: int = Field(ge=0)
    capped: int = Field(ge=0)
    rowsKept: int = Field(ge=0)

    @model_validator(mode="after")
    def _counters_reconcile(self) -> Self:
        if self.rowsIn - self.rejected - self.duplicates != self.distinct:
            raise ValueError(
                f"rowsIn {self.rowsIn} - rejected {self.rejected} - duplicates "
                f"{self.duplicates} != distinct {self.distinct}"
            )
        if self.distinct - self.belowFrequencyFloor - self.capped != self.rowsKept:
            raise ValueError(
                f"distinct {self.distinct} - belowFrequencyFloor "
                f"{self.belowFrequencyFloor} - capped {self.capped} != rowsKept "
                f"{self.rowsKept}"
            )
        return self


class MasterWordlist(SchemaModel):
    """Every kept corpus word, ranked and banded, with its ingest provenance."""

    generatedAt: str = Field(pattern=_ISO_INSTANT)
    provenance: list[SourceProvenance] = Field(min_length=1)
    counters: IngestCounters
    words: list[MasterWord]

    @model_validator(mode="after")
    def _rows_kept_matches_the_words(self) -> Self:
        if self.counters.rowsKept != len(self.words):
            raise ValueError(
                f"counters.rowsKept {self.counters.rowsKept} != {len(self.words)} words"
            )
        return self
