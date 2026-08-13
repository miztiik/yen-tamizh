"""The baked glyph-manifest contract (Row 10 design system).

All icons in yen-tamizh are vector glyphs referenced by id from a generated
manifest - never inline SVG, never a hardcoded path (Holy Law #10). ``backend/``
bakes the source glyph pack under ``assets/glyphs/`` into the served bundle at
``frontend/public/assets/glyphs/index.json`` (see ``glyphs/bake.py``); the
frontend's ``Glyph`` component resolves a glyph by its id from that manifest.

The manifest is a rewrite-in-place persisted surface (shipped fresh in every
bundle, never migrated) with its own schema. Like every contract it carries a
date-stamp ``version`` + ``changelog`` via ``SchemaModel`` (CLAUDE.md section 11).
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from yen_tamizh_backend.contracts.base import SchemaModel

# An SVG ``viewBox``: four space-separated numbers "minX minY width height".
_VIEWBOX = r"^-?\d+(\.\d+)?(\s+-?\d+(\.\d+)?){3}$"

# A glyph id is a lower-case slug (referenced by id, per guardrails identifier
# discipline): "back", "close", "settings".
GlyphId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]*$")]


class GlyphShape(BaseModel):
    """One glyph's renderable geometry: a ``viewBox`` and a single ``path`` d."""

    model_config = ConfigDict(extra="forbid")

    viewBox: str = Field(pattern=_VIEWBOX)
    path: str = Field(min_length=1)


class GlyphManifest(SchemaModel):
    """The baked index of every UI glyph, keyed by its lower-case slug id."""

    glyphs: dict[GlyphId, GlyphShape] = Field(min_length=1)
