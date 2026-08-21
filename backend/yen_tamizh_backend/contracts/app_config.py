"""The tunable-knob contract (app-config).

app-config is the main config surface (config.md): a bundle-shipped,
rewrite-in-place file both runtimes read - the frontend at play time and
``backend/`` at build time. Every knob ships a sane default so a fresh clone
runs on the committed config (Holy Law #6). Player-facing text is NOT here; it
lives in ``config/copy.json`` (the identifier-and-copy split, guardrails).
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import (
    DifficultyId,
    GameId,
    JourneyId,
    ModeId,
)


class DailyConfig(BaseModel):
    """The Daily playlist: how long a day is, and which Games fill it (modes.md).

    ``games`` is a RING rather than a set. A day takes the ``playlistLength``
    window that starts at its own date, so every Game reaches a player without
    any day holding all of them - which is what keeps the Daily a burst rather
    than a sitting. The order of the ring is therefore a real knob: it decides
    which Games co-occur, not which comes first (that is ``dailyRank``, in
    ``config/daily-generator.json``).

    ``games`` must be at least as long as the playlist, so an ordinary day can
    never deal the same Game twice.

    ``themedGames`` is the ring a THEMED day draws from, and it is deliberately
    allowed to be SHORTER than the playlist. The two rings answer different
    questions: an ordinary day's claim is variety of GAMES, so it never repeats
    one; a themed day's claim is that its WORDS belong together, so it holds
    only the Games that theme can honestly fill and repeats one rather than
    reaching for a Game whose slots the theme cannot fill without padding.
    """

    model_config = ConfigDict(extra="forbid")

    playlistLength: int = Field(ge=1)
    games: list[GameId] = Field(min_length=1)
    themedGames: list[GameId] = Field(min_length=1)

    @model_validator(mode="after")
    def _the_rings_are_usable(self) -> Self:
        for name, ring in (("games", self.games), ("themedGames", self.themedGames)):
            if len(set(ring)) != len(ring):
                raise ValueError(f"daily.{name} has a repeated Game: {ring}")
        if len(self.games) < self.playlistLength:
            raise ValueError(
                f"daily.games has {len(self.games)} Games for a playlist of "
                f"{self.playlistLength}: an ordinary day would deal one twice"
            )
        return self


class HintsConfig(BaseModel):
    """Hint availability: a global switch and a per-Game allowance."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool
    perGame: dict[GameId, int]


class InfiniteConfig(BaseModel):
    """Infinite mode: the anti-repeat LRU window and the default difficulty."""

    model_config = ConfigDict(extra="forbid")

    lruWindow: int = Field(ge=0)
    defaultDifficulty: DifficultyId


class TimeTrialConfig(BaseModel):
    """Time Trial mode: the run duration in seconds."""

    model_config = ConfigDict(extra="forbid")

    durationSec: int = Field(ge=1)


class UiConfig(BaseModel):
    """UI shell: which Modes are live, the default Mode, theme, and Journey.

    ``defaultJourney`` is the id of the path the Journey Mode opens - the stem
    of a file under ``datasets/journeys/``. It is a knob rather than a constant
    in the Mode for the reason every asset path in this repo is (Holy Law #6):
    a Journey is content, more than one can ship at once, and which one a player
    lands on is a curation decision that must not need a code change. It is
    REQUIRED rather than optional-with-a-default, because a default would put
    the name of one particular content file inside the schema.
    """

    model_config = ConfigDict(extra="forbid")

    enabledModes: list[ModeId] = Field(min_length=1)
    defaultMode: ModeId
    defaultTheme: str = Field(min_length=1)
    defaultJourney: JourneyId


class AppConfig(SchemaModel):
    """The tunable knobs both runtimes read; a fresh clone runs on the defaults."""

    daily: DailyConfig
    hints: HintsConfig
    infinite: InfiniteConfig
    timeTrial: TimeTrialConfig
    ui: UiConfig
