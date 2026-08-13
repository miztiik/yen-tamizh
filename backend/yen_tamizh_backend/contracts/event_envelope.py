"""The telemetry event envelope (event-envelope).

Every event on the one bus is a flat, serializable payload with this fixed
envelope (telemetry.md). The bus is local only - events log to the console in
dev and ring-buffer in memory in production; there is no network sink (Holy Law
#1). ``name`` is constrained to the canonical event catalog, so an unregistered
name is rejected at the boundary (Row 11's logger refuses one).

The envelope carries BOTH ``v`` - a lightweight per-event version a reader uses
to evolve its parsing (telemetry.md) - AND the schema-discipline ``version`` +
``changelog`` from ``SchemaModel`` (CLAUDE.md section 11): ``v`` evolves the
runtime record, ``version``/``changelog`` stamp the schema shape.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from yen_tamizh_backend.contracts.base import SchemaModel

# The canonical event catalog (telemetry.md). A logger refuses any name outside
# this set; extending telemetry means adding a name here first.
EventName = Literal[
    "puzzle.started",
    "puzzle.attempt.submitted",
    "puzzle.hint.used",
    "puzzle.completed",
    "puzzle.abandoned",
    "mode.session.started",
    "mode.session.completed",
    "streak.updated",
    "pipeline.stage.started",
    "pipeline.stage.completed",
    "pipeline.stage.failed",
    "puzzle.generated",
    "bank.updated",
]

# Standard log severities for the ``level`` field.
EventLevel = Literal["debug", "info", "warn", "error"]


class EventEnvelope(SchemaModel):
    """One structured telemetry event; ``name`` is from the canonical catalog.

    ``ctx`` (stable context: modeId, gameId, packId, day) and ``data`` (the
    event-specific payload) are open objects on purpose: their keys vary by
    event, so pinning them would force a schema bump every time a Game emits a
    new context key - which fights the "a Game is observable for free" design.
    The fixed, typed part is the envelope; ``ctx`` and ``data`` are the open part.
    """

    ts: int = Field(ge=0)
    src: str = Field(min_length=1)
    v: int = Field(ge=1)
    session: str = Field(min_length=1)
    name: EventName
    level: EventLevel
    ctx: dict[str, Any]
    data: dict[str, Any]
