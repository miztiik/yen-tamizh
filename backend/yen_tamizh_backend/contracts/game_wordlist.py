"""The per-Game derived wordlist contract (Row 9).

A ``game-wordlist`` is what one Game's generator draws its words from: the
subset of the ranked master (Row 8) that the Game's selection knobs keep. It is
a BUILD ARTIFACT - regenerated in full by ``rebuild_wordlists``, never hand
edited - and it is not served: the game downloads the puzzles the daily engine
bakes (Row 13), not the wordlist they were baked from.

The document is a pure function of its inputs. There is deliberately no
wall-clock ``generatedAt`` field: a timestamp would make two runs over the same
master produce different bytes, which is the opposite of what a reproducible
derived artifact means. ``source`` pins the exact master the rows came from -
its path, its schema version, its own ``generatedAt``, its sha256, and its row
count - and git history records when the file changed (CLAUDE.md section 5).

``counters`` is the integrity Oracle, enforced by the model itself:
``masterRows - outsideLength - outsideBand - invalidWordFinal - capped ==
rowsKept == len(words)``. Every master row is accounted for by exactly one
outcome, so a selection bug cannot quietly drop words.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import GameId
from yen_tamizh_backend.contracts.corpus_sources import RelPath
from yen_tamizh_backend.contracts.derived_wordlists import DerivedSelection
from yen_tamizh_backend.contracts.master_wordlist import FreqBand

_ISO_INSTANT = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
_SHA256 = r"^[0-9a-f]{64}$"
_DATESTAMP = r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?$"


class GameWordHints(BaseModel):
    """The honest, derivable hint material for one word.

    Both fields are recomputed from ``ezhuthu`` on every rebuild and validated
    against it, so precomputing them cannot drift - the same bargain
    ``MasterWord.length`` makes in the master list.

    A category hint is deliberately absent. The master's category tags are
    English source labels, and a Tamil category name is player-facing COPY,
    which lives in ``config/copy.json`` and never inside a dataset. Inventing
    Tamil category strings here would be a dishonest field.
    """

    model_config = ConfigDict(extra="forbid")

    firstEzhuthu: str = Field(min_length=1)
    length: int = Field(ge=1)


class GameWord(BaseModel):
    """One word a Game may build a puzzle from.

    ``anagramFanOut`` counts how many SERVED rows share this row's ezhuthu
    multiset, including the row itself - so a word whose tiles spell nothing
    else carries ``1``, never ``0``. It is a recorded signal, not an admission
    test: a Game that knows a submitted arrangement is a different served word
    can answer "that is a word, but not today's" instead of a flat rejection,
    which is the difference between a player learning something and a player
    concluding the game cheated.
    """

    model_config = ConfigDict(extra="forbid")

    word: str = Field(min_length=1)
    ezhuthu: list[str] = Field(min_length=1)
    freqBand: FreqBand
    anagramFanOut: int = Field(ge=1)
    hints: GameWordHints | None = None

    @model_validator(mode="after")
    def _row_is_self_consistent(self) -> Self:
        # Segmentation is non-destructive (Row 6), so a row whose parts do not
        # rebuild its word is corrupt and must never reach a generator.
        if "".join(self.ezhuthu) != self.word:
            raise ValueError(f"ezhuthu does not rejoin to {self.word!r}")
        if self.hints is None:
            return self
        if self.hints.firstEzhuthu != self.ezhuthu[0]:
            raise ValueError(
                f"hints.firstEzhuthu {self.hints.firstEzhuthu!r} != "
                f"{self.ezhuthu[0]!r} for {self.word!r}"
            )
        if self.hints.length != len(self.ezhuthu):
            raise ValueError(
                f"hints.length {self.hints.length} != ezhuthu count "
                f"{len(self.ezhuthu)} for {self.word!r}"
            )
        return self


class DerivedSource(BaseModel):
    """The exact master wordlist a derived set was cut from."""

    model_config = ConfigDict(extra="forbid")

    path: RelPath
    version: str = Field(pattern=_DATESTAMP)
    generatedAt: str = Field(pattern=_ISO_INSTANT)
    sha256: str = Field(pattern=_SHA256)
    rows: int = Field(ge=1)


class DerivedCounters(BaseModel):
    """The reconciliation ledger for one derive run (no silent drops)."""

    model_config = ConfigDict(extra="forbid")

    masterRows: int = Field(ge=0)
    outsideLength: int = Field(ge=0)
    outsideBand: int = Field(ge=0)
    invalidWordFinal: int = Field(default=0, ge=0)
    capped: int = Field(ge=0)
    rowsKept: int = Field(ge=0)

    @model_validator(mode="after")
    def _counters_reconcile(self) -> Self:
        accounted = (
            self.outsideLength
            + self.outsideBand
            + self.invalidWordFinal
            + self.capped
            + self.rowsKept
        )
        if accounted != self.masterRows:
            raise ValueError(
                f"outsideLength {self.outsideLength} + outsideBand "
                f"{self.outsideBand} + invalidWordFinal {self.invalidWordFinal} + "
                f"capped {self.capped} + rowsKept {self.rowsKept} != masterRows "
                f"{self.masterRows}"
            )
        return self


class GameWordlist(SchemaModel):
    """One Game's derived wordlist, with the master and selection that made it."""

    gameId: GameId
    source: DerivedSource
    selection: DerivedSelection
    counters: DerivedCounters
    words: list[GameWord]

    @model_validator(mode="after")
    def _rows_kept_matches_the_words(self) -> Self:
        if self.counters.rowsKept != len(self.words):
            raise ValueError(
                f"counters.rowsKept {self.counters.rowsKept} != {len(self.words)} words"
            )
        if self.counters.masterRows != self.source.rows:
            raise ValueError(
                f"counters.masterRows {self.counters.masterRows} != source.rows "
                f"{self.source.rows}"
            )
        return self

    @model_validator(mode="after")
    def _fan_out_matches_the_served_rows(self) -> Self:
        # Recomputed rather than trusted, like every other derived field here:
        # a stale fan-out would have a Game tell a player their arrangement is
        # another word when this set no longer serves one.
        served: dict[tuple[str, ...], int] = {}
        for row in self.words:
            key = tuple(sorted(row.ezhuthu))
            served[key] = served.get(key, 0) + 1
        for row in self.words:
            expected = served[tuple(sorted(row.ezhuthu))]
            if row.anagramFanOut != expected:
                raise ValueError(
                    f"anagramFanOut {row.anagramFanOut} != {expected} served rows "
                    f"sharing the ezhuthu of {row.word!r}"
                )
        return self
