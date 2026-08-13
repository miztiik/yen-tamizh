"""Bake the source glyph pack into the served, schema-valid glyph manifest.

Output is DETERMINISTIC - sorted keys, 2-space indent, trailing newline, ASCII,
LF on every OS - so re-baking is byte-stable and the committed
``frontend/public/assets/glyphs/index.json`` never drifts from source (proven by
``tests/test_glyphs.py``). Constructing the ``GlyphManifest`` model IS the schema
validation gate: an invalid ``viewBox``/``path``/id fails the bake loudly.

Run it with::

    python -m yen_tamizh_backend.glyphs.bake
"""

from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

from yen_tamizh_backend.contracts.glyph_manifest import GlyphManifest, GlyphShape

# The manifest's own date-stamp version + changelog (CLAUDE.md section 11). This
# is a CONSTANT, not date.today(): it records when the glyph pack's shape last
# changed, so a re-bake on any day is byte-identical. Bump it (and append a
# changelog entry) in the same commit that changes the pack.
_PACK_VERSION = "2026-08-13"
_CHANGELOG = [
    {
        "version": _PACK_VERSION,
        "change": "Initial essential UI glyph pack baked from assets/glyphs/.",
        "why": (
            "Row 10 needs a baked, schema-validated manifest the Glyph "
            "component resolves by id (Holy Law #10); placeholder-quality art "
            "for later polish."
        ),
    },
]


def _repo_root() -> Path:
    # bake.py -> glyphs -> yen_tamizh_backend -> backend -> <repo root>
    return Path(__file__).resolve().parents[3]


def _parse_glyph(svg_path: Path) -> tuple[str, GlyphShape]:
    """Read one source SVG's ``viewBox`` + single ``path`` d into a ``GlyphShape``."""
    root = ElementTree.parse(svg_path).getroot()  # noqa: S314 - trusted local source
    view_box = root.get("viewBox")
    if view_box is None:
        raise ValueError(f"{svg_path.name}: missing a viewBox attribute")
    # {*} matches the SVG namespace without hardcoding it.
    path_el = root.find(".//{*}path")
    if path_el is None:
        raise ValueError(f"{svg_path.name}: no <path> element")
    d = path_el.get("d")
    if not d:
        raise ValueError(f"{svg_path.name}: <path> has no d attribute")
    return svg_path.stem, GlyphShape(viewBox=view_box, path=d)


def build_manifest(source_dir: Path) -> GlyphManifest:
    """Build the validated ``GlyphManifest`` from every ``*.svg`` in ``source_dir``."""
    glyphs: dict[str, GlyphShape] = {}
    for svg_path in sorted(source_dir.glob("*.svg")):
        glyph_id, shape = _parse_glyph(svg_path)
        glyphs[glyph_id] = shape
    # Constructing the model validates every field against the glyph-manifest
    # contract (ids, viewBox pattern, non-empty path, at least one glyph).
    return GlyphManifest(version=_PACK_VERSION, changelog=_CHANGELOG, glyphs=glyphs)


def render(manifest: GlyphManifest) -> str:
    """Return the canonical JSON text for a manifest (deterministic)."""
    return json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"


def bake(source_dir: Path, out_path: Path) -> Path:
    """Bake ``source_dir`` into ``out_path`` (LF-forced); return ``out_path``."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # newline="\n" forces LF on every OS so the committed manifest is byte-stable.
    out_path.write_text(render(build_manifest(source_dir)), encoding="utf-8", newline="\n")
    return out_path


def main() -> None:
    root = _repo_root()
    out = bake(
        root / "assets" / "glyphs",
        root / "frontend" / "public" / "assets" / "glyphs" / "index.json",
    )
    # Paths leaving the process are relative + POSIX (CLAUDE.md section 2).
    print(f"baked {out.relative_to(root).as_posix()}")


if __name__ == "__main__":
    main()
