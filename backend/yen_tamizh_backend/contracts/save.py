"""The browser-owned save contract (save) and its derived-key helper.

save is the one MIGRATING persisted surface (schemas.md): written by one version
of the game and read by a later one, so it carries read-side migrations (the
reader lands in Row 11). Its ``dayKey`` is a DERIVED key -
``date|modeId|gameId|packId`` - RECOMPUTED on read from those value fields, never
trusted from storage (the guardrails derived-key rule); a stale or tampered
stored key must never decide which day's progress loads. ``compute_day_key`` is
that single recompute; the TypeScript twin lands with the reader in Row 11.

``perMode`` is keyed by a stable ``modeId``; each Mode's per-mode state has its
own shape and validates against its own slice as the Mode's reader lands, so the
value is left open here (the save schema fixes only that progress is keyed by
modeId, not each Mode's internal record).
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import ModeId

# A calendar day (core-loop.md: the daily reset is a fixed UTC boundary), stored
# as YYYY-MM-DD.
_DATE = r"^\d{4}-\d{2}-\d{2}$"


def compute_day_key(date: str, mode_id: str, game_id: str, pack_id: str) -> str:
    """Rebuild the save ``dayKey`` from its value fields (never trust storage).

    The key is ``date|modeId|gameId|packId``; the reader recomputes it on every
    read so a stale or tampered stored key can never select the wrong day.
    """
    return f"{date}|{mode_id}|{game_id}|{pack_id}"


class Save(SchemaModel):
    """Today's progress, streak, and last-played day; browser-local only."""

    dayKey: str = Field(min_length=1)
    streak: int = Field(ge=0)
    lastPlayed: str = Field(pattern=_DATE)
    # The last day the streak was TICKED, which is not the last day played: a
    # day counts once it is COMPLETED, and re-completing it must not tick again
    # (Palm - one tick per day, never per item). Optional so a save written
    # before Row 13 still loads; absent means "the streak has not ticked yet".
    lastStreakDay: str | None = Field(default=None, pattern=_DATE)
    perMode: dict[ModeId, dict[str, Any]]
    seenInfiniteIds: list[str]
