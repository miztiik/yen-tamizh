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
from yen_tamizh_backend.contracts.common import (
    CopySlug,
    DifficultyId,
    GameId,
    Hint,
    PackId,
)

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
    """One day's committed, ordered playlist of puzzle items.

    ``theme`` is present only on a THEMED day - the day whose every item was
    drawn from one theme's wordlist - and it carries the theme's copy SLUG, not
    its Tamil label. The label is player-facing copy in ``config/copy.json``,
    which the shell already reads, so baking the words would freeze copy into a
    committed artifact that only a rebuild could correct. Its absence is the
    ordinary day, which is why it is optional rather than nullable-and-required:
    an ordinary day says nothing about themes at all.
    """

    date: str = Field(pattern=_DATE)
    theme: CopySlug | None = None
    items: list[PuzzleItem] = Field(min_length=1)
