"""A minimal demonstrator contract that exercises the pipeline end to end.

``Example`` is NOT a real game contract - the named schemas (app-config, save,
puzzle-file, bank-index, event-envelope, anagram-puzzle) are Row 7's. It exists
so the pipeline (Pydantic -> JSON Schema -> TS types + ajv validators) and its
CI drift gate have a real, stable model to generate from, and a real payload to
accept/reject on both sides of the frontend boundary. Keep it small and stable;
Row 7 adds the real models alongside it rather than replacing it.
"""

from __future__ import annotations

from pydantic import Field

from yen_tamizh_backend.contracts.base import SchemaModel


class Example(SchemaModel):
    """Demonstrator payload: a non-empty label and a non-negative count."""

    label: str = Field(min_length=1)
    count: int = Field(ge=0)
