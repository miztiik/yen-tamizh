"""Shared identifier types and value objects for the core contracts.

The stable identifiers (``gameId``, ``modeId``, ``packId``, a difficulty bucket)
are lower-case slugs, per the guardrails identifier discipline: code references
them and they are never reformatted to match a label. Player-facing copy is a
separate surface (``config/copy.json``), never an identifier.

``Hint`` is the one value object shared by more than one contract (the
``puzzle-file`` items and the per-Game ``anagram-puzzle`` payload), so it is
defined once here rather than copied - a copy of a persisted shape is exactly
the drift the pipeline exists to prevent.

``SourceId`` and ``RelPath`` are shared FIELD vocabulary on the same terms: a
source slug and a repo-relative path are spoken by several build-time contracts,
so they live here with the other shared types rather than inside whichever
contract happened to declare them first.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

# A stable identifier slug: lower-case, digit- and hyphen-joined ("anagram",
# "word-ladder", "ta-core", "time-trial", "daily").
_SLUG = r"^[a-z][a-z0-9-]*$"

GameId = Annotated[str, StringConstraints(pattern=_SLUG)]
ModeId = Annotated[str, StringConstraints(pattern=_SLUG)]
PackId = Annotated[str, StringConstraints(pattern=_SLUG)]
DifficultyId = Annotated[str, StringConstraints(pattern=_SLUG)]
CopySlug = Annotated[str, StringConstraints(pattern=_SLUG)]

# A stable source identifier slug, matching the guardrails identifier discipline
# used by the core contracts: "wiki", "ta-dedup", "opensubtitles-ta".
SourceId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]*$")]

# A repo-relative POSIX path (CLAUDE.md section 2: no absolute paths, no drive
# letters, no backslashes in anything that leaves the process). The leading
# character class excludes "/" so an absolute path cannot match, and ":" is
# absent throughout so "C:/x" cannot match either.
RelPath = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._+-]+)*$")
]


class Hint(BaseModel):
    """One optional, honest hint: its kind, its text, and its score cost.

    ``text`` is per-puzzle generated DATA (the next honest step for this
    puzzle), not a static UI label - so it lives in the puzzle payload, not in
    ``config/copy.json``. A hint never sells a power-up (a project non-goal); it
    reveals the next honest step (core-loop.md).
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    text: str = Field(min_length=1)
    cost: int = Field(ge=0)
