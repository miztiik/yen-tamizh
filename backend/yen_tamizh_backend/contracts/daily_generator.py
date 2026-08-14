"""The daily puzzle ENGINE's registry contract (Row 13).

``config/daily-generator.json`` is what the build-time daily generator reads.
It is deliberately a SEPARATE surface from ``config/app-config.json``: the app
config is runtime framing the browser ships with (how many items a day holds,
which Modes are enabled), while this file holds the knobs that decide how a word
becomes a puzzle - attempts, time limit, revealed head start, hint costs, and
which ezhuthu lengths count as which difficulty.

That split is the corpus-versus-puzzle boundary drawn one layer lower: the
generator CONSUMES a derived wordlist (Row 9) and PRODUCES puzzle files, and it
must be tunable without touching either the words above it or the runtime below
it. Adding a second Game's generator is a DATA change here (another ``games``
entry) plus the Game's own payload builder - never a rewrite of the day loop.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import DifficultyId, GameId, PackId, RelPath


class DifficultyBand(BaseModel):
    """One difficulty bucket: the ezhuthu lengths it covers and its id.

    Difficulty is derived from the word's ezhuthu count because that is the only
    honest difficulty signal the derived set carries; a 3-ezhuthu scramble has 6
    arrangements and a 6-ezhuthu one has 720. Where the cuts fall is a
    game-balance number, so it lives here rather than in Python (Holy Law #6).
    """

    model_config = ConfigDict(extra="forbid")

    id: DifficultyId
    minLength: int = Field(ge=1)
    maxLength: int = Field(ge=1)

    @model_validator(mode="after")
    def _band_is_coherent(self) -> Self:
        if self.minLength > self.maxLength:
            raise ValueError(
                f"minLength {self.minLength} must be <= maxLength {self.maxLength}"
            )
        return self


class HintSpec(BaseModel):
    """One offered hint: its kind, its wording, and what revealing it costs.

    ``template`` is a Python format string over the wordlist row's honest hint
    fields (``{firstEzhuthu}``, ``{length}``). The rendered TEXT is per-puzzle
    data and ships inside the puzzle payload, but the WORDING is player-facing
    copy - so it lives in config, not in a Python literal, and the generator
    only fills in the values.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    template: str = Field(min_length=1)
    cost: int = Field(ge=0)


class GameGeneration(BaseModel):
    """How one Game turns a wordlist row into a playable puzzle."""

    model_config = ConfigDict(extra="forbid")

    gameId: GameId
    packId: PackId
    wordlist: RelPath
    attempts: int = Field(ge=1)
    timeLimitSec: int = Field(ge=0)
    # How many leading ezhuthu the puzzle starts with already placed. 0 keeps the
    # scramble whole; a positive value is the gentlest honest difficulty dial.
    reveal: int = Field(ge=0)
    difficulties: list[DifficultyBand] = Field(min_length=1)
    hints: list[HintSpec] = Field(default_factory=list)

    @model_validator(mode="after")
    def _difficulty_ids_are_distinct(self) -> Self:
        ids = [band.id for band in self.difficulties]
        if len(set(ids)) != len(ids):
            raise ValueError(f"difficulties has a repeated id: {ids}")
        kinds = [hint.kind for hint in self.hints]
        if len(set(kinds)) != len(kinds):
            raise ValueError(f"hints has a repeated kind: {kinds}")
        return self


class DailyGenerator(SchemaModel):
    """The daily engine's knobs: where the bank lands and how a day is filled."""

    # Where the baked bank is written, relative to the repo root. It lives under
    # frontend/public/ so the game reads it same-origin from its own bundle
    # (Holy Law #1) - never from a CDN.
    bankDir: RelPath
    # How many days AHEAD of the run date to bake. The player's calendar day is
    # local, the cron's is UTC, and a phone that is hours ahead must still find
    # today in the bank - plus a pre-baked run keeps the game playable offline
    # across midnight.
    daysAhead: int = Field(ge=0)
    games: list[GameGeneration] = Field(min_length=1)

    @model_validator(mode="after")
    def _games_are_distinct(self) -> Self:
        ids = [entry.gameId for entry in self.games]
        if len(set(ids)) != len(ids):
            raise ValueError(f"games has a repeated gameId: {ids}")
        return self
