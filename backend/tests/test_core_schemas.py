"""Contract-tier tests for the Row 7 core schemas.

Real fixtures, no mocks (Holy Law #7). For each of the six core contracts (plus
copy) the Pydantic model ACCEPTS the shared valid fixture and REJECTS the shared
malformed one - the SAME bytes the frontend ajv test loads
(``frontend/src/contracts/core-schemas.test.ts``), so accept/reject is proven on
both sides of the boundary (the contract Oracle). The committed config files must
validate too, and the derived-key helper is unit-tested.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from yen_tamizh_backend.contracts import (
    AnagramPuzzle,
    AppConfig,
    BankIndex,
    Copy,
    EventEnvelope,
    PuzzleFile,
    Save,
)
from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.save import compute_day_key

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _REPO_ROOT / "datasets" / "fixtures" / "contracts"
_CONFIG = _REPO_ROOT / "config"

# Each core contract paired with its fixture stem. The stems match the shared
# datasets/fixtures/contracts/<stem>_{valid,invalid}.json the frontend loads.
_CORE: tuple[tuple[type[SchemaModel], str], ...] = (
    (AppConfig, "app-config"),
    (EventEnvelope, "event-envelope"),
    (Save, "save"),
    (PuzzleFile, "puzzle-file"),
    (BankIndex, "bank-index"),
    (AnagramPuzzle, "anagram-puzzle"),
    (Copy, "copy"),
)


def _load(path: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return data


@pytest.mark.parametrize(("model", "stem"), _CORE)
def test_model_accepts_valid_fixture(model: type[SchemaModel], stem: str) -> None:
    # Oracle acceptance half: the shared valid fixture validates against Pydantic.
    model.model_validate(_load(_FIXTURES / f"{stem}_valid.json"))


@pytest.mark.parametrize(("model", "stem"), _CORE)
def test_model_rejects_malformed_fixture(model: type[SchemaModel], stem: str) -> None:
    # Oracle rejection half: the SAME malformed bytes the frontend ajv test
    # rejects are rejected here too (missing/mistyped required field).
    with pytest.raises(ValidationError):
        model.model_validate(_load(_FIXTURES / f"{stem}_invalid.json"))


def test_app_config_file_validates() -> None:
    # The committed defaults must satisfy the schema (a fresh clone runs on them).
    AppConfig.model_validate(_load(_CONFIG / "app-config.json"))


def test_copy_file_validates() -> None:
    Copy.model_validate(_load(_CONFIG / "copy.json"))


def test_compute_day_key_joins_value_fields() -> None:
    # The derived key is rebuilt from its value fields, never trusted from storage.
    assert (
        compute_day_key("2026-08-13", "daily", "anagram", "ta-core")
        == "2026-08-13|daily|anagram|ta-core"
    )
