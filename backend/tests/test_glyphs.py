"""Tests for the Row 10 glyph bake (source SVGs -> the served glyph manifest).

Real fixtures, no mocks (Holy Law #7). Proven here:

1. The baked manifest validates against the ``glyph-manifest`` contract - the
   model is constructed from real source SVGs and re-validated.
2. The bake is DETERMINISTIC and the committed
   ``frontend/public/assets/glyphs/index.json`` equals a fresh bake (a staleness
   guard: if it fails, re-run ``python -m yen_tamizh_backend.glyphs.bake``).
3. Malformed source SVGs fail the bake loudly (fail-fast at the boundary).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from yen_tamizh_backend.contracts.glyph_manifest import GlyphManifest
from yen_tamizh_backend.glyphs.bake import bake, build_manifest, render

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_DIR = _REPO_ROOT / "assets" / "glyphs"
_COMMITTED = _REPO_ROOT / "frontend" / "public" / "assets" / "glyphs" / "index.json"

# The essential UI glyph pack this row ships (placeholder-quality art).
_ESSENTIAL_IDS = {"back", "check", "close", "hint", "settings", "share", "star"}


def test_build_manifest_validates_against_the_contract() -> None:
    manifest = build_manifest(_SOURCE_DIR)
    # Re-validating the dumped payload proves it satisfies the schema exactly.
    GlyphManifest.model_validate(manifest.model_dump(mode="json"))
    assert set(manifest.glyphs) == _ESSENTIAL_IDS
    for shape in manifest.glyphs.values():
        assert shape.viewBox
        assert shape.path


def test_render_is_deterministic() -> None:
    assert render(build_manifest(_SOURCE_DIR)) == render(build_manifest(_SOURCE_DIR))


def test_committed_manifest_matches_a_fresh_bake(tmp_path: Path) -> None:
    # Drift/staleness guard: the committed served manifest equals a fresh bake.
    fresh = render(build_manifest(_SOURCE_DIR))
    committed = _COMMITTED.read_text(encoding="utf-8")
    assert committed == fresh, (
        "frontend/public/assets/glyphs/index.json is stale - re-run "
        "`python -m yen_tamizh_backend.glyphs.bake`"
    )
    # And baking to a fresh location reproduces the same bytes.
    out = bake(_SOURCE_DIR, tmp_path / "index.json")
    assert out.read_text(encoding="utf-8") == fresh


def test_committed_manifest_is_valid_json_matching_the_model() -> None:
    payload = json.loads(_COMMITTED.read_text(encoding="utf-8"))
    manifest = GlyphManifest.model_validate(payload)
    assert _ESSENTIAL_IDS.issubset(manifest.glyphs)


def test_bake_rejects_a_source_without_a_viewbox(tmp_path: Path) -> None:
    (tmp_path / "bad.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0 L1 1"/></svg>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="viewBox"):
        build_manifest(tmp_path)


def test_bake_rejects_a_source_without_a_path(tmp_path: Path) -> None:
    (tmp_path / "bad.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"></svg>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="path"):
        build_manifest(tmp_path)


def test_bake_rejects_a_malformed_viewbox(tmp_path: Path) -> None:
    (tmp_path / "bad.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="oops" >'
        '<path d="M0 0 L1 1"/></svg>',
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        build_manifest(tmp_path)
