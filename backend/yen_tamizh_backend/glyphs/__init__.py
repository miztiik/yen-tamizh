"""Build-time glyph bake: source SVGs -> the served, schema-valid manifest.

The source glyph pack lives under ``assets/glyphs/*.svg`` (raw art, never read by
the game). ``bake.py`` extracts each glyph's ``viewBox`` + ``path`` and writes a
deterministic ``frontend/public/assets/glyphs/index.json`` that validates against
the ``glyph-manifest`` schema. The frontend's ``Glyph`` component resolves a glyph
by its id from that manifest (Holy Law #10). Run it with::

    python -m yen_tamizh_backend.glyphs.bake

Import the bake helpers from ``yen_tamizh_backend.glyphs.bake`` directly; this
package ``__init__`` re-exports nothing so ``python -m ...glyphs.bake`` does not
double-import the module.
"""

from __future__ import annotations
