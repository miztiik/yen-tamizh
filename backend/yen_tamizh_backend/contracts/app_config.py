"""The tunable-knob contract (app-config).

app-config is the main config surface (config.md): a bundle-shipped,
rewrite-in-place file both runtimes read - the frontend at play time and
``backend/`` at build time. Every knob ships a sane default so a fresh clone
runs on the committed config (Holy Law #6). Player-facing text is NOT here; it
lives in ``config/copy.json`` (the identifier-and-copy split, guardrails).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import DifficultyId, GameId, ModeId


class DailyConfig(BaseModel):
    """The Daily playlist: how many items and the per-Game mix (modes.md)."""

    model_config = ConfigDict(extra="forbid")

    playlistLength: int = Field(ge=1)
    mix: dict[GameId, int]


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
    """UI shell: which Modes are live, and the default Mode and theme."""

    model_config = ConfigDict(extra="forbid")

    enabledModes: list[ModeId] = Field(min_length=1)
    defaultMode: ModeId
    defaultTheme: str = Field(min_length=1)


class AppConfig(SchemaModel):
    """The tunable knobs both runtimes read; a fresh clone runs on the defaults."""

    daily: DailyConfig
    hints: HintsConfig
    infinite: InfiniteConfig
    timeTrial: TimeTrialConfig
    ui: UiConfig
