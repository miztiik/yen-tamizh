"""The per-Game derived wordlist contract (Row 9; cut over to the lexicon in row 12).

A ``game-wordlist`` is what one Game's generator draws its words from: the
subset of the published lexicon (row 11) that the Game's serving gates keep. It
is a BUILD ARTIFACT - regenerated in full by ``rebuild_wordlists``, never hand
edited - and it is not served: the game downloads the puzzles the daily engine
bakes (Row 13), not the wordlist they were baked from.

The document is a pure function of its inputs. There is deliberately no
wall-clock ``generatedAt`` field anywhere in it - not on the document and not on
``source`` either: a timestamp would make two runs over the same lexicon produce
different bytes, which is the opposite of what a reproducible derived artifact
means. ``source`` pins the exact lexicon the rows came from by CONTENT - the
meta document's path, its schema version, its sha256 and its published row count
- and git history records when the file changed (CLAUDE.md section 5). One
digest still pins a partitioned input, because ``lexicon.meta.json`` itself
carries the sha256 of every published file.

``counters`` is the integrity Oracle, enforced by the model itself, with one
bucket per serving gate::

    lexiconRows - outsideLength - outsideClass - belowAttestations
                - belowFrequency - withoutMeaning - capped == rowsKept
                == len(words)

Every published lexicon row is accounted for by exactly one outcome, so a
selection bug cannot quietly drop words and a gate cannot quietly do nothing.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import QUARTILES, GameId, RelPath
from yen_tamizh_backend.contracts.derived_wordlists import DerivedSelection

_SHA256 = r"^[0-9a-f]{64}$"
_DATESTAMP = r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?$"


class GameWordHints(BaseModel):
    """The honest, derivable hint material for one word.

    Both fields are recomputed from ``ezhuthu`` on every rebuild and validated
    against it, so precomputing them cannot drift.

    A category hint is deliberately absent. Only about 1,290 lexicon rows carry
    a category at all, and a Tamil category name is player-facing COPY, which
    lives in ``config/copy.json`` and never inside a dataset. Inventing Tamil
    category strings here would be a dishonest field.
    """

    model_config = ConfigDict(extra="forbid")

    firstEzhuthu: str = Field(min_length=1)
    length: int = Field(ge=1)


class GameWord(BaseModel):
    """One word a Game may build a puzzle from.

    ``frequency`` is the lexicon's raw count, carried through unchanged. It is
    what ``minFrequency`` gates on and what the difficulty curve reads, and it
    replaces the old rank-relative band: a band computed over a population where
    thousands of rows appear zero times is a different filter wearing the same
    name.

    ``frequencyStratum`` is which quarter of THIS SET the row's frequency puts
    it in, 1 being the most familiar. It is computed over the SERVED rows and
    nothing wider - a quartile taken over millions of lexicon surfaces would say
    nothing about the words a player is actually offered. It is the second axis
    of difficulty: length alone is anti-correlated at both tails, because long
    Tamil headwords are mostly compounds that decompose while short rare words
    are brutal.

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
    frequency: int = Field(ge=0)
    frequencyStratum: int = Field(ge=1, le=QUARTILES)
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
    """The exact lexicon a derived set was cut from, pinned by content.

    ``metaPath`` names ``lexicon.meta.json`` rather than the directory of
    published files, and ``sha256`` digests that one document - which itself
    carries the sha256 of every partition, so a single digest still pins a
    partitioned input. ``rows`` is the lexicon's PUBLISHED row count, which is
    what the ledger reconciles against.
    """

    model_config = ConfigDict(extra="forbid")

    metaPath: RelPath
    version: str = Field(pattern=_DATESTAMP)
    sha256: str = Field(pattern=_SHA256)
    rows: int = Field(ge=1)


class DerivedCounters(BaseModel):
    """The reconciliation ledger for one derive run - one bucket per gate.

    The buckets are listed in the order the identity is read, and a row that
    fails more than one gate is counted under the first one that stopped it.
    ``outsideClass`` comes off the lexicon's own partition table rather than
    from reading those files: selection is an allow-list, so the derived layer
    opens only the classes it serves, and the classes it will not serve are
    counted from what the meta document declares about them.
    """

    model_config = ConfigDict(extra="forbid")

    lexiconRows: int = Field(ge=0)
    outsideLength: int = Field(ge=0)
    outsideClass: int = Field(ge=0)
    belowAttestations: int = Field(ge=0)
    belowFrequency: int = Field(ge=0)
    withoutMeaning: int = Field(ge=0)
    capped: int = Field(ge=0)
    rowsKept: int = Field(ge=0)

    @model_validator(mode="after")
    def _counters_reconcile(self) -> Self:
        accounted = (
            self.outsideLength
            + self.outsideClass
            + self.belowAttestations
            + self.belowFrequency
            + self.withoutMeaning
            + self.capped
            + self.rowsKept
        )
        if accounted != self.lexiconRows:
            raise ValueError(
                f"outsideLength {self.outsideLength} + outsideClass "
                f"{self.outsideClass} + belowAttestations {self.belowAttestations} "
                f"+ belowFrequency {self.belowFrequency} + withoutMeaning "
                f"{self.withoutMeaning} + capped {self.capped} + rowsKept "
                f"{self.rowsKept} != lexiconRows {self.lexiconRows}"
            )
        return self


class GameWordlist(SchemaModel):
    """One Game's derived wordlist, with the lexicon and selection that made it."""

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
        if self.counters.lexiconRows != self.source.rows:
            raise ValueError(
                f"counters.lexiconRows {self.counters.lexiconRows} != source.rows "
                f"{self.source.rows}"
            )
        return self

    @model_validator(mode="after")
    def _strata_are_the_quartiles_of_this_set(self) -> Self:
        # Recomputed rather than trusted, like every other derived field here.
        # The order is frequency descending with the word as the tie-break, so
        # it is total and the strata are reproducible; a value-based cut would
        # collapse whenever a frequency repeats, which on the rare tail it does
        # thousands of times.
        total = len(self.words)
        if total == 0:
            return self
        order = sorted(self.words, key=lambda row: (-row.frequency, row.word))
        for position, row in enumerate(order):
            expected = position * QUARTILES // total + 1
            if row.frequencyStratum != expected:
                raise ValueError(
                    f"frequencyStratum {row.frequencyStratum} != {expected} for "
                    f"{row.word!r} at position {position} of {total} served rows"
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
