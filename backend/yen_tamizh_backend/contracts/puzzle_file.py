"""The Daily playlist contract (puzzle-file).

A puzzle-file is one day's committed playlist (modes.md): an ordered list of
items, each naming its Game, Pack, and difficulty and carrying that Game's own
puzzle ``payload``. The payload is an OPEN object: every Game validates its slice
against its own schema (e.g. anagram-puzzle), so Games evolve independently and
puzzle-file never becomes a mega-schema (Fowler, schemas.md). Bundle-shipped and
rewrite-in-place - a new build replaces it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import DifficultyId, GameId, Hint, PackId

# The playlist date (modes.md: Daily is calendar-bound), stored as YYYY-MM-DD.
_DATE = r"^\d{4}-\d{2}-\d{2}$"


class PuzzleItem(BaseModel):
    """One playlist entry: a Game + Pack + difficulty and its open payload."""

    model_config = ConfigDict(extra="forbid")

    gameId: GameId
    packId: PackId
    difficulty: DifficultyId
    payload: dict[str, Any]
    hints: list[Hint] | None = None


class PuzzleFile(SchemaModel):
    """One day's committed, ordered playlist of puzzle items."""

    date: str = Field(pattern=_DATE)
    items: list[PuzzleItem] = Field(min_length=1)
