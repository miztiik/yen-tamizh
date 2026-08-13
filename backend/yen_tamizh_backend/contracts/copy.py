"""The player-facing copy contract (copy).

``config/copy.json`` holds display text keyed by a stable slug (config.md):
button labels, Mode and Game display titles, and the like. It is deliberately
separate from app-config so a translation or a wording change never touches an
identifier or a line of code (the identifier-and-copy split, guardrails).
``strings`` may be empty; entries are added as the UI rows introduce their
labels. Like every config surface it carries ``version`` + ``changelog`` (CLAUDE.md
section 11) and runs through the same pipeline as app-config, so there is one
source of truth and no hand-authored second schema (Fowler).
"""

from __future__ import annotations

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import CopySlug


class Copy(SchemaModel):
    """The slug -> display-text map for all player-facing copy."""

    strings: dict[CopySlug, str]
