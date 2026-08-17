"""The daily puzzle ENGINE's registry contract (Row 13).

``config/daily-generator.json`` is what the build-time daily generator reads.
It is deliberately a SEPARATE surface from ``config/app-config.json``: the app
config is runtime framing the browser ships with (how many items a day holds,
which Modes are enabled), while this file holds the knobs that decide how a word
becomes a puzzle - attempts, time limit, revealed head start, hint costs, and
which ezhuthu lengths at which familiarity count as which difficulty.

That split is the lexicon-versus-puzzle boundary drawn one layer lower: the
generator CONSUMES a derived wordlist (Row 9) and PRODUCES puzzle files, and it
must be tunable without touching either the words above it or the runtime below
it. Adding a second Game's generator is a DATA change here (another ``games``
entry) plus the Game's own payload builder - never a rewrite of the day loop.

A Game may also register THEMED wordlists beside its ordinary one. That is the
Daily's variety mechanism and it is data too: a themed day draws every slot from
one theme's own derived set, and which themes exist is a registry edit rather
than a branch in the day loop.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import (
    QUARTILES,
    CopySlug,
    DifficultyId,
    GameId,
    PackId,
    RelPath,
)


class DifficultyBand(BaseModel):
    """One difficulty bucket: the ezhuthu lengths and the familiarity it covers.

    Difficulty is TWO-AXIS - length and familiarity - because length alone is
    anti-correlated at both tails. A long Tamil headword is usually a compound
    that decomposes into recognisable chunks and is EASIER than its ezhuthu
    count suggests, while a short rare word is brutal; a length-only easy bucket
    therefore forces the generator into the shortest words, which are
    disproportionately literary. A 3-ezhuthu answer also has only six
    arrangements against three attempts, so it is brute-forceable by shuffling
    without the player ever recognising the word.

    ``maxStratum`` is the coarsest frequency quarter the band admits, 1 being
    the most familiar quarter of the SERVED set. Bands deliberately OVERLAP on
    length and tile on familiarity: what separates easy from hard is mostly how
    well the player knows the word, not how many tiles it has.

    Where the cuts fall is a game-balance number, so it lives here rather than
    in Python (Holy Law #6).
    """

    model_config = ConfigDict(extra="forbid")

    id: DifficultyId
    minLength: int = Field(ge=1)
    maxLength: int = Field(ge=1)
    maxStratum: int = Field(ge=1, le=QUARTILES)

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


class ThemedSet(BaseModel):
    """One themed wordlist this Game may run a whole day from.

    A theme is the Daily's VARIETY mechanism, not a Mode and not a Game: three
    unrelated anagrams are a list, three sharing a theme are a round. It costs no
    new engine - it is one derived set cut on the ``categories`` dimension, and
    ``wordlist`` is where that set landed.

    ``copySlug`` names the theme's player-facing Tamil label in
    ``config/copy.json``. The SLUG travels in the baked day, never the label: a
    Tamil category name is copy, and copy never gets baked into a dataset where
    it could only be changed by a rebuild.

    A themed day is OPPORTUNISTIC. The day runs a theme only when a whole
    playlist can be drawn from that theme's own wordlist without repeating a
    word the bank has already served; otherwise the day is ordinary. A theme is
    never padded out with an off-theme word, because the round's whole claim is
    that the three words belong together.
    """

    model_config = ConfigDict(extra="forbid")

    wordlist: RelPath
    copySlug: CopySlug


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
    # The themed sets this Game may run a whole day from. Empty is the normal
    # state and means this Game never runs a themed day.
    themes: list[ThemedSet] = Field(default_factory=list)

    @model_validator(mode="after")
    def _difficulty_ids_are_distinct(self) -> Self:
        ids = [band.id for band in self.difficulties]
        if len(set(ids)) != len(ids):
            raise ValueError(f"difficulties has a repeated id: {ids}")
        kinds = [hint.kind for hint in self.hints]
        if len(set(kinds)) != len(kinds):
            raise ValueError(f"hints has a repeated kind: {kinds}")
        slugs = [theme.copySlug for theme in self.themes]
        if len(set(slugs)) != len(slugs):
            raise ValueError(f"themes has a repeated copySlug: {slugs}")
        paths = [theme.wordlist for theme in self.themes] + [self.wordlist]
        if len(set(paths)) != len(paths):
            # A theme pointing at the ordinary set would make every day themed
            # and say so in the header, which is a lie about the round.
            raise ValueError(f"themes has a repeated wordlist: {paths}")
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
    # How often the Daily MAY run a themed round: every Nth date, counted on the
    # proleptic Gregorian day number so the cadence is a pure function of the
    # date and needs no phase knob. 0 turns themed days off entirely.
    #
    # A cadence is needed because "themed whenever a theme can fill the day" is
    # not the same design at 429 servable themed rows as it was at the ~30 the
    # theme was sized for: without it the Daily would be the same theme every day
    # for months, which is the opposite of the variety a theme exists to add.
    themeEveryNDays: int = Field(ge=0)
    games: list[GameGeneration] = Field(min_length=1)

    @model_validator(mode="after")
    def _games_are_distinct(self) -> Self:
        ids = [entry.gameId for entry in self.games]
        if len(set(ids)) != len(ids):
            raise ValueError(f"games has a repeated gameId: {ids}")
        return self
