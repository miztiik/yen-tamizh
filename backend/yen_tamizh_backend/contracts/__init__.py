"""The evolutionary contract pipeline: Pydantic is the single source of truth.

The Pydantic models under this package are authoritative for every persisted
shape in yen-tamizh (CLAUDE.md sections 1a, 3, 11). ``export.py`` writes each
registered model to a flat ``schemas/<name>.schema.json`` (date-stamp
``version`` + ``changelog``, draft 2020-12, relative ``$id``); the frontend's
``scripts/gen-contracts.mjs`` derives TypeScript types + ajv validators from
those schemas. A CI drift gate regenerates both and fails on any diff, so the
schema, the types, and the validators can never drift from the models.

``REGISTRY`` is the explicit list of models the exporter walks. Later rows
append their models here (Row 7: app-config, event-envelope, save, puzzle-file,
bank-index, anagram-puzzle).
"""

from __future__ import annotations

from yen_tamizh_backend.contracts.base import ChangelogEntry, SchemaModel
from yen_tamizh_backend.contracts.example import Example
from yen_tamizh_backend.contracts.glyph_manifest import GlyphManifest, GlyphShape

# Explicit registry (not auto-discovery) so the exporter's output set is
# deterministic and reviewed. Export sorts by name; order here is not load-bearing.
REGISTRY: tuple[type[SchemaModel], ...] = (Example, GlyphManifest)

__all__ = [
    "REGISTRY",
    "ChangelogEntry",
    "Example",
    "GlyphManifest",
    "GlyphShape",
    "SchemaModel",
]
