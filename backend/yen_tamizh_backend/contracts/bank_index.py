"""The generated-bank index contract (bank-index).

bank-index is the manifest of which days the build-time generator has baked into
the puzzle bank and how many items each holds (overview.md). It is a build-time,
rewrite-in-place surface: each generator run rewrites it. The ``days`` list may
be empty (a fresh bank).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from yen_tamizh_backend.contracts.base import SchemaModel

# A baked day (overview.md), stored as YYYY-MM-DD.
_DATE = r"^\d{4}-\d{2}-\d{2}$"


class BankDay(BaseModel):
    """One baked day in the bank: its date and how many items it holds."""

    model_config = ConfigDict(extra="forbid")

    date: str = Field(pattern=_DATE)
    itemCount: int = Field(ge=0)


class BankIndex(SchemaModel):
    """The index of every day baked into the puzzle bank."""

    days: list[BankDay]
