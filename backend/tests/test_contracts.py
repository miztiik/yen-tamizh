"""Contract-tier tests for the evolutionary contract pipeline (Row 5).

Real fixtures, no mocks (Holy Law #7). Two things are proven:

1. Pydantic validation - the ``Example`` demonstrator accepts a valid payload
   and REJECTS a malformed one. These are the SAME fixtures the frontend ajv
   test loads (``datasets/fixtures/contracts/example_{valid,invalid}.json``), so
   the rejection is proven on both sides of the boundary - the Oracle's
   rejection half.
2. Export determinism + drift - re-rendering every registered schema is
   byte-stable and equals the bytes committed under ``schemas/`` (the drift-gate
   Oracle, backend half).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from yen_tamizh_backend.contracts import REGISTRY, ChangelogEntry, Example, Lexicon
from yen_tamizh_backend.contracts.export import render

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _REPO_ROOT / "datasets" / "fixtures" / "contracts"
_SCHEMAS = _REPO_ROOT / "schemas"


def _load_fixture(name: str) -> dict[str, object]:
    data: dict[str, object] = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
    return data


def test_example_accepts_valid_fixture() -> None:
    model = Example.model_validate(_load_fixture("example_valid.json"))
    assert model.label == "demo"
    assert model.count >= 0


def test_example_rejects_malformed_fixture() -> None:
    # example_invalid.json is missing the required "label" and has count < 0.
    with pytest.raises(ValidationError):
        Example.model_validate(_load_fixture("example_invalid.json"))


def test_version_must_equal_newest_changelog_entry() -> None:
    entry = ChangelogEntry(version="2026-08-13", change="init", why="demo")
    with pytest.raises(ValidationError):
        Example(version="2026-08-12", changelog=[entry], label="x", count=1)


def test_changelog_requires_at_least_one_entry() -> None:
    with pytest.raises(ValidationError):
        Example(version="2026-08-13", changelog=[], label="x", count=1)


def test_version_rejects_non_datestamp() -> None:
    entry = ChangelogEntry(version="2026-08-13", change="init", why="demo")
    with pytest.raises(ValidationError):
        Example(version="1", changelog=[entry], label="x", count=1)


def test_schema_name_is_kebab_case() -> None:
    assert Example.schema_name() == "example"


def test_json_schema_is_draft_2020_12_with_relative_id() -> None:
    schema = Example.json_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == "example.schema.json"


def test_render_is_deterministic() -> None:
    for model in REGISTRY:
        assert render(model) == render(model)


def test_committed_schemas_match_models() -> None:
    # Drift-gate Oracle (backend half): the committed bytes equal a fresh render.
    # If this fails, run `python -m yen_tamizh_backend.contracts.export`.
    for model in REGISTRY:
        committed = (_SCHEMAS / f"{model.schema_name()}.schema.json").read_text(
            encoding="utf-8"
        )
        assert committed == render(model), (
            f"{model.schema_name()}.schema.json is stale - re-run the exporter"
        )


def test_lexicon_row_shape_reaches_the_schema_through_the_meta_document() -> None:
    # LexiconEntry is not a SchemaModel, so the exporter never walks it directly.
    # Lexicon.rowSchema is the reference that carries it into $defs; without it
    # the row shape - one line per word, 3.97M of them - would ship with no
    # schema at all, which is a Holy Law #3 break the drift gate cannot see.
    schema = Lexicon.json_schema()
    entry = schema["$defs"]["LexiconEntry"]
    assert entry["additionalProperties"] is False
    assert "wordClass" in entry["required"]
    # And the stamp a data row must NOT carry.
    assert "version" not in entry["properties"]
    assert "changelog" not in entry["properties"]
