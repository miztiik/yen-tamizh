"""Tests for the row-4 lexicon source acquisition: the ledger and its fixtures.

Real files throughout, no mocks (Holy Law #7).

The raw sources are gitignored, so this module is split in two. Everything that
reads a COMMITTED file - the ledger table, the fixtures, and the sha256 values the
corpus ingest already recorded in the master wordlist - runs everywhere, CI
included. The checks that need the raw bytes SKIP when the source is absent,
because a gate that cannot pass in CI is a broken gate rather than a finding.

Four things are proven:

1. **The ledger is well formed** - one row per source, a closed set of roles, and
   either a complete record or an explicit NOT ACQUIRED marker.
2. **The fixtures exist and are honest** - both scales for every acquired source,
   non-empty, valid UTF-8, valid in their declared format, and the 10x fixture
   holds exactly ten times the records of the 1x.
3. **The slices are byte-exact** - a fixture is always ``raw[:k] + raw[len - m:]``,
   proven against the 10x fixture in CI and against the raw source locally.
4. **The ledger agrees with the committed master wordlist** - the ten sha256
   values the corpus ingest recorded in August 2026 still describe these bytes.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_LEDGER = _REPO_ROOT / "datasets" / "lexicon" / "sources" / "README.md"
_FIXTURES = _REPO_ROOT / "datasets" / "fixtures" / "lexicon"
_MASTER = _REPO_ROOT / "datasets" / "wordlists" / "master" / "words_ranked.json"

_ROLES = frozenset({"authority", "formEvidence", "frequency", "category", "authored"})
_NOT_ACQUIRED = "NOT ACQUIRED"
_ABSENT = "-"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_LINE_FORMATS = frozenset({".csv", ".txt", ".jsonl"})


class LedgerRow:
    """One parsed row of the acquisition ledger in the sources README."""

    def __init__(self, cells: list[str]) -> None:
        self.number = cells[0]
        self.id = cells[1]
        self.role = cells[2]
        self.origin = cells[3]
        self.path = cells[4]
        self.raw_bytes = cells[5]
        self.records = cells[6]
        self.sha256 = cells[7].strip("`")
        self.status = cells[8]

    @property
    def acquired(self) -> bool:
        return self.status != _NOT_ACQUIRED

    @property
    def suffix(self) -> str:
        return Path(self.path).suffix

    def fixture(self, scale: str) -> Path:
        return _FIXTURES / f"{self.id}.{scale}{self.suffix}"

    def source(self) -> Path:
        return _REPO_ROOT / self.path

    def __repr__(self) -> str:
        return f"<LedgerRow {self.number} {self.id}>"


def _read_ledger() -> list[LedgerRow]:
    rows: list[LedgerRow] = []
    for line in _LEDGER.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 9 or not re.fullmatch(r"[A-F]\d+", cells[0]):
            continue
        rows.append(LedgerRow(cells))
    return rows


LEDGER = _read_ledger()
ACQUIRED = [row for row in LEDGER if row.acquired]


def _count_records(data: bytes, suffix: str) -> int:
    if suffix in _LINE_FORMATS:
        return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)
    document: Any = json.loads(data.decode("utf-8"))
    if isinstance(document, list):
        return len(document)
    arrays = [value for value in document.values() if isinstance(value, list)]
    return len(arrays[0])


def _decompose(small: bytes, large: bytes) -> tuple[int, int]:
    """The ``k, m`` for which ``small == large[:k] + large[len(large) - m:]``.

    Raises ``AssertionError`` when no such split exists - which is exactly the
    failure "this fixture is not a byte-exact slice of that file".
    """
    limit = min(len(small), len(large))
    head = 0
    while head < limit and small[head] == large[head]:
        head += 1
    tail = len(small) - head
    assert tail >= 0
    assert small == large[:head] + (large[len(large) - tail :] if tail else b"")
    return head, tail


@pytest.mark.parametrize("row", LEDGER, ids=lambda row: row.number)
def test_every_ledger_row_is_complete_or_explicitly_not_acquired(row: LedgerRow) -> None:
    assert row.role in _ROLES, f"{row.id} carries an unknown role {row.role!r}"
    fields = (row.path, row.raw_bytes, row.records, row.sha256)
    if not row.acquired:
        assert all(field == _ABSENT for field in fields), (
            f"{row.id} is marked NOT ACQUIRED but still records bytes"
        )
        return
    assert all(field != _ABSENT for field in fields), f"{row.id} is missing a field"
    assert _SHA256.fullmatch(row.sha256), f"{row.id} has a malformed sha256"
    assert int(row.raw_bytes) > 0
    assert int(row.records) > 0
    assert not row.path.startswith("/") and "\\" not in row.path, (
        f"{row.id} records a non-relative or non-POSIX path"
    )


def test_the_ledger_covers_every_inventory_group() -> None:
    groups = {row.number[0] for row in LEDGER}
    assert groups == {"A", "B", "C", "D", "E"}, "group F must not be acquired"
    assert len(LEDGER) == 21
    assert len({row.id for row in LEDGER}) == 21


@pytest.mark.parametrize("row", ACQUIRED, ids=lambda row: row.number)
def test_both_fixture_scales_exist_and_decode(row: LedgerRow) -> None:
    for scale in ("1x", "10x"):
        fixture = row.fixture(scale)
        assert fixture.is_file(), f"{fixture.name} is missing"
        data = fixture.read_bytes()
        assert data, f"{fixture.name} is empty"
        data.decode("utf-8")


@pytest.mark.parametrize("row", ACQUIRED, ids=lambda row: row.number)
def test_the_ten_x_fixture_holds_ten_times_the_records(row: LedgerRow) -> None:
    one = _count_records(row.fixture("1x").read_bytes(), row.suffix)
    ten = _count_records(row.fixture("10x").read_bytes(), row.suffix)
    assert one > 0
    assert ten == one * 10, f"{row.id}: {ten} records at 10x against {one} at 1x"
    assert ten <= int(row.records)


@pytest.mark.parametrize("row", ACQUIRED, ids=lambda row: row.number)
def test_the_one_x_fixture_is_a_byte_exact_slice_of_the_ten_x(row: LedgerRow) -> None:
    """Runs with no raw bytes: both scales were cut from the same source prefix."""
    one = row.fixture("1x").read_bytes()
    ten = row.fixture("10x").read_bytes()
    head, tail = _decompose(one, ten)
    assert head > 0
    if row.suffix in _LINE_FORMATS:
        assert tail == 0, f"{row.id}: a line fixture must be a pure prefix"


@pytest.mark.parametrize("row", ACQUIRED, ids=lambda row: row.number)
def test_the_raw_source_matches_its_recorded_sha256(row: LedgerRow) -> None:
    source = row.source()
    if not source.is_file():
        pytest.skip(f"{row.path} is gitignored and absent - repopulate to run this check")
    digest = hashlib.sha256()
    size = 0
    with source.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
            size += len(chunk)
    assert size == int(row.raw_bytes), f"{row.id} is {size} bytes, ledger says {row.raw_bytes}"
    assert digest.hexdigest() == row.sha256, f"{row.id} sha256 disagrees with the ledger"


@pytest.mark.parametrize("row", ACQUIRED, ids=lambda row: row.number)
def test_each_fixture_is_a_byte_exact_slice_of_its_raw_source(row: LedgerRow) -> None:
    source = row.source()
    if not source.is_file():
        pytest.skip(f"{row.path} is gitignored and absent - repopulate to run this check")
    raw = source.read_bytes()
    for scale in ("1x", "10x"):
        _decompose(row.fixture(scale).read_bytes(), raw)


def test_the_ledger_agrees_with_the_committed_master_wordlist() -> None:
    """The corpus ingest recorded ten of these hashes; they must still hold."""
    provenance: list[dict[str, Any]] = json.loads(_MASTER.read_text(encoding="utf-8"))[
        "provenance"
    ]
    ledger = {row.id: row for row in ACQUIRED}
    compared = 0
    for entry in provenance:
        row = ledger.get(str(entry["id"]))
        if row is None:
            continue
        compared += 1
        assert row.sha256 == entry["sha256"], f"{row.id} drifted from the ingested bytes"
        assert int(row.raw_bytes) == int(entry["bytes"]), f"{row.id} byte count drifted"
        assert row.path == entry["path"], f"{row.id} moved away from its ingested path"
    assert compared == 11, f"expected 11 shared sources, compared {compared}"
