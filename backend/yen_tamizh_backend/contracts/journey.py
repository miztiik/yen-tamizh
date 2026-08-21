"""The Journey definition contract (journey).

A Journey is a hand-authored, ordered PATH of nodes (journeys.md): the player
walks it one node at a time, clearing a node unlocks the next, and the winding
path drawn on the Journey screen is that list rendered. This is the persisted
shape of one such path, and it is the whole Mode - a new Journey is a new file
under ``datasets/journeys/``, never new code (Fowler + Palm).

Three shape decisions, each closing a way a Journey could stop being data:

- **A node CARRIES its puzzle.** ``payload`` is the same open object a
  ``puzzle-file`` item carries, validated by the Game's own schema (the ruling
  that keeps puzzle-file from becoming a mega-schema). It rides the node because
  the alternative is worse in both directions: generating a puzzle in the
  browser would be runtime compute the static contract forbids (Holy Law #1),
  and pointing at a second baked file would make a Journey two artifacts that
  can disagree about how many nodes it has. One file is playable on its own,
  which is what lets "drop a JSON file" be literally true.
- **``unlockRule`` is a closed two-member vocabulary, and the first node must be
  ``open``.** A path whose every node waits for another node has no entrance and
  can never be started, so that is a contract error rather than a screen the
  player stares at. Everything else is ``previous-complete`` - the rule the map
  draws and the save answers. A third rule (clear N of the last M, spend a key,
  wait for tomorrow) is not modelled because nothing authors one; it would be a
  vocabulary with no reader, and adding one later is an additive change to this
  enum.
- **``titleTa`` is camelCase like every other field in this repo.** The name is
  the Tamil TITLE of the path and it is data rather than copy: unlike a Mode's
  name, which is one string the whole app shares and therefore lives in
  ``config/copy.json``, a Journey's title arrives with the Journey and a copy
  map would need an entry minted for every file dropped - which is exactly the
  redeploy the data-defined ruling exists to avoid.

``theme`` is a design-system palette name (the ``[data-theme]`` axis in
``app.css``), which is what makes a path feel like a place rather than a list.
It is the same vocabulary ``ui.defaultTheme`` speaks, so a Journey can only ask
for a palette the design system already ships.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import (
    DifficultyId,
    GameId,
    JourneyId,
    PackId,
)

# A stable identifier slug, the same discipline the core contracts use for every
# other identifier: lower-case, digit- and hyphen-joined.
_SLUG = r"^[a-z][a-z0-9-]*$"

NodeId = Annotated[str, StringConstraints(pattern=_SLUG)]

# Why a node is reachable. "open" needs nothing; "previous-complete" waits for
# the node immediately before it in `nodes` to be recorded complete in the save.
UnlockRule = Literal["open", "previous-complete"]


class JourneyNode(BaseModel):
    """One level of the path: which Game, how hard, when it opens, and its board.

    ``gameId``/``packId``/``difficulty``/``payload`` are deliberately the same
    four fields a ``puzzle-file`` item carries, because a node IS one item - the
    difference between a Journey and a Daily is which order they are met in and
    what decides that, not what a puzzle is.
    """

    model_config = ConfigDict(extra="forbid")

    id: NodeId
    gameId: GameId
    packId: PackId
    difficulty: DifficultyId
    unlockRule: UnlockRule
    payload: dict[str, Any]


class Journey(SchemaModel):
    """One curated path: its title, its palette, and its nodes in walking order."""

    id: JourneyId
    titleTa: str = Field(min_length=1)
    theme: str = Field(min_length=1)
    nodes: list[JourneyNode] = Field(min_length=1)

    @model_validator(mode="after")
    def _the_path_can_be_walked(self) -> Self:
        """A path needs an entrance, and every node needs its own address.

        The node id is what the save records and what the map keys its state on,
        so two nodes sharing one would make clearing either of them clear both -
        a progression bug that would look like a rendering bug.
        """
        ids = [node.id for node in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError(f"journey {self.id!r} repeats a node id: {ids}")
        if self.nodes[0].unlockRule != "open":
            raise ValueError(
                f"journey {self.id!r} opens on {self.nodes[0].unlockRule!r}: the "
                "first node must be 'open' or the path can never be entered"
            )
        return self
