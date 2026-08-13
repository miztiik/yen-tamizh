"""The anagram Game's puzzle-payload contract (anagram-puzzle).

anagram is the proven starter Game (games.md): unscramble ezhuthu tiles into the
target word. This is the per-Game ``payload`` schema a puzzle-file item carries;
its ``tiles`` are ezhuthu strings ALREADY segmented by the generator (Row 13) via
the shared ezhuthu library - segmentation is not this schema's job. Per-Game
payload schemas keep Games evolving independently (Fowler, schemas.md).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import Hint

# One ezhuthu tile is a non-empty grapheme-cluster string (core-loop.md), produced
# by the shared ezhuthu segmentation library at generation time.
Ezhuthu = Annotated[str, StringConstraints(min_length=1)]


class AnagramPuzzle(SchemaModel):
    """One anagram puzzle: a target word, its scrambled ezhuthu tiles, and rules."""

    word: str = Field(min_length=1)
    tiles: list[Ezhuthu] = Field(min_length=1)
    reveal: int | None = Field(default=None, ge=0)
    timeLimitSec: int = Field(ge=0)
    attempts: int = Field(ge=1)
    hints: list[Hint] | None = None
