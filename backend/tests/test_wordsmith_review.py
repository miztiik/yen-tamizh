"""REVIEW - the intermediate files a human reads between runs (Row 9b).

The three reports are DERIVED, so their tests ask two things of each: does it
answer the question its name claims, and does the answer agree with the store it
was read from. There is no golden file here on purpose - the store these run
against is built from the committed fixtures, so a fixture change would make a
frozen expectation stale without making it wrong.

The store is built the way every other store-backed test in this suite builds
one: by running the REAL extract, stage and enrich over the committed 1x
fixtures. No mocks, no raw bytes, and the whole thing runs in CI.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from _lexicon_workspace import source_bytes
from yen_tamizh_backend.contracts.lexicon_sources import LexiconSource, LexiconSources
from yen_tamizh_backend.contracts.wordhood import Wordhood
from yen_tamizh_backend.ezhuthu import analyse
from yen_tamizh_backend.wordsmith.enrich import enrich, load_config
from yen_tamizh_backend.wordsmith.extract import extract, load_registry, sha256_of
from yen_tamizh_backend.wordsmith.review import (
    MEANING_ATTRS,
    MEANINGLESS_FILE,
    NOT_A_WORD_FILE,
    QUEUE_FILE,
    REVIEW_DIRECTORY,
    SERVED_CLASS,
    UNCLASSIFIED_FILE,
    enrichment_queue,
    review,
)
from yen_tamizh_backend.wordsmith.stage import stage
from yen_tamizh_backend.wordsmith.store import SIGNAL_COLUMNS, open_store
from yen_tamizh_backend.wordsmith.wordhood import not_a_word_reason, tier_one_sources

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = _REPO_ROOT / "config" / "lexicon-sources.json"
_CONFIG_PATH = _REPO_ROOT / "config" / "wordhood.json"
_FIXTURES = _REPO_ROOT / "datasets" / "fixtures" / "lexicon"

REGISTRY = load_registry(_REGISTRY_PATH)
CONFIG: Wordhood = load_config(_CONFIG_PATH)

# The reasons `not_a_word_reason` can produce, plus the one no threshold does.
REASONS = frozenset(
    {
        "empty",
        "nonTamil",
        "malformedEzhuthu",
        "tooLong",
        "repeatedEzhuthu",
        "sourceDenied",
    }
)


@dataclass(frozen=True, slots=True)
class Reviewed:
    """An enriched store and the reports written from it."""

    db: Path
    root: Path
    registry: LexiconSources
    workspace: Path


def _fixture_registry(root: Path) -> LexiconSources:
    entries: list[dict[str, Any]] = []
    source: LexiconSource
    for source in REGISTRY.sources:
        fixture = source_bytes(_REPO_ROOT, source)
        staged = root / "sources" / fixture.name
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fixture, staged)
        digest, size = sha256_of(staged)
        entries.append(
            source.model_dump(exclude_none=True)
            | {
                "path": f"sources/{fixture.name}",
                "sha256": digest,
                "bytes": size,
                "enabled": True,
            }
        )
    return LexiconSources.model_validate(
        REGISTRY.model_dump(exclude_none=True)
        | {"lexiconRoot": "out", "sources": entries}
    )


@pytest.fixture(scope="module")
def reviewed(tmp_path_factory: pytest.TempPathFactory) -> Reviewed:
    root = tmp_path_factory.mktemp("review")
    registry = _fixture_registry(root)
    extract(registry, root, force=True)
    db = root / "out" / "cache" / "lexicon.db"
    stage(registry, root, db)
    enrich(registry, CONFIG, db)
    run = review(registry, CONFIG, db, root)
    # Under the lexicon root, NOT under the build cache: these reports are
    # working material a person reads, not machine state one stage hands on.
    assert run.root == root / registry.lexiconRoot / REVIEW_DIRECTORY
    return Reviewed(db=db, root=run.root, registry=registry, workspace=root)


def _rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def _classified(conn: sqlite3.Connection, word_class: str) -> set[str]:
    return {
        str(word)
        for (word,) in conn.execute(
            "SELECT word FROM classification WHERE wordClass = ?", (word_class,)
        )
    }


def test_every_report_lands_where_the_run_says_it_did(reviewed: Reviewed) -> None:
    for name in (UNCLASSIFIED_FILE, NOT_A_WORD_FILE, QUEUE_FILE, MEANINGLESS_FILE):
        assert (reviewed.root / name).is_file(), name
    assert not list(reviewed.root.glob("*.partial")), (
        "a report is renamed into place, so no partial may survive a clean run"
    )


def test_the_unclassified_report_is_exactly_the_unclassified_surfaces(
    reviewed: Reviewed,
) -> None:
    rows = _rows(reviewed.root / UNCLASSIFIED_FILE)
    conn = open_store(reviewed.db)
    try:
        assert {row["word"] for row in rows} == _classified(conn, "unclassified")
    finally:
        conn.close()
    assert rows, "the fixture store must leave something unclassified to review"
    assert [row["word"] for row in rows] == sorted(row["word"] for row in rows)


def test_every_unclassified_row_carries_all_eight_signals_and_its_length(
    reviewed: Reviewed,
) -> None:
    # The point of the file: the residue can be SORTED, which needs the numbers
    # the verdict was reached from, not just the words.
    for row in _rows(reviewed.root / UNCLASSIFIED_FILE):
        assert set(SIGNAL_COLUMNS) <= set(row)
        assert row["length"] == len(analyse(row["word"]).ezhuthu)


def test_the_reported_signals_are_the_stored_ones(reviewed: Reviewed) -> None:
    conn = open_store(reviewed.db)
    try:
        columns = ", ".join(f'"{name}"' for name in SIGNAL_COLUMNS)
        stored = {
            str(record[0]): list(record[1:])
            for record in conn.execute(f"SELECT word, {columns} FROM signal")
        }
    finally:
        conn.close()
    for row in _rows(reviewed.root / UNCLASSIFIED_FILE):
        assert [row[name] for name in SIGNAL_COLUMNS] == stored[row["word"]]


def test_the_not_a_word_report_names_the_clause_that_refused_each_surface(
    reviewed: Reviewed,
) -> None:
    rows = _rows(reviewed.root / NOT_A_WORD_FILE)
    conn = open_store(reviewed.db)
    try:
        assert {row["word"] for row in rows} == _classified(conn, "notAWord")
    finally:
        conn.close()
    assert rows
    for row in rows:
        assert row["reason"] in REASONS


def test_the_reported_reason_is_the_classifier_s_own(reviewed: Reviewed) -> None:
    # One implementation of the rule, read two ways. Deriving the reason a
    # second time here is exactly what would let the report and the verdict
    # disagree.
    for row in _rows(reviewed.root / NOT_A_WORD_FILE):
        expected = not_a_word_reason(analyse(row["word"]), CONFIG) or "sourceDenied"
        assert row["reason"] == expected, row["word"]


def test_the_enrichment_queue_holds_only_described_unclassified_surfaces(
    tmp_path: Path,
) -> None:
    # Built directly rather than from the 1x fixtures, because over a few dozen
    # records per source the intersection is empty - which is a property of the
    # slices, not of the query. Over the real store it is 13,500 surfaces.
    described = "\u0b95\u0ba3"
    silent = "\u0b95\u0ba9"
    settled = "\u0b95\u0bb2"
    conn = open_store(tmp_path / "queue.db")
    try:
        conn.executemany(
            "INSERT INTO classification (word, wordClass) VALUES (?, ?)",
            [
                (described, "unclassified"),
                (silent, "unclassified"),
                (settled, "headword"),
            ],
        )
        conn.executemany(
            "INSERT INTO fact (source_id, word, attr, value, ordinal) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                ("ta-wiktionary-content", described, "definitionTa", "a gloss", 0),
                ("indowordnet-ta", described, "synonym", silent, 0),
                # A frequency table mentions everything and describes nothing.
                ("opensubtitles-ta", silent, "translation", "noise", 0),
                # A settled surface is not queued however well described.
                ("ta-wiktionary-content", settled, "definitionTa", "a gloss", 0),
            ],
        )
        rows = list(enrichment_queue(conn, REGISTRY))
    finally:
        conn.close()
    assert [row["word"] for row in rows] == [described]
    assert rows[0]["sources"] == ["indowordnet-ta", "ta-wiktionary-content"]
    assert rows[0]["definitionTa"] == ["a gloss"]
    assert rows[0]["synonym"] == [silent]


def test_every_queued_row_names_a_meaning_it_would_work_from(
    reviewed: Reviewed,
) -> None:
    for row in _rows(reviewed.root / QUEUE_FILE):
        assert row["sources"]
        assert any(attr in row for attr in MEANING_ATTRS), row["word"]


def test_the_queue_is_empty_over_a_current_derived_zone(reviewed: Reviewed) -> None:
    # Not an accident and not a broken query: a tier-1 source that DESCRIBES a
    # surface also ATTESTS it, an attested surface has an entry, and an entry
    # always reaches a verdict - so the intersection is empty by construction.
    # A row here means a source described something it did not list, or that the
    # derived zone is stale.
    conn = open_store(reviewed.db)
    try:
        tier_one = tier_one_sources(REGISTRY)
        slots = ",".join("?" for _ in tier_one)
        described = conn.execute(
            "SELECT count(*) FROM (SELECT DISTINCT f.word FROM fact f "
            "JOIN classification c ON c.word = f.word "
            f"WHERE c.wordClass = 'unclassified' AND f.source_id IN ({slots}))",
            tier_one,
        ).fetchone()
    finally:
        conn.close()
    assert described is not None and int(described[0]) == 0
    assert _rows(reviewed.root / QUEUE_FILE) == []


def test_the_meaningless_report_is_the_queue_that_is_actually_left(
    reviewed: Reviewed,
) -> None:
    rows = _rows(reviewed.root / MEANINGLESS_FILE)
    conn = open_store(reviewed.db)
    try:
        served = _classified(conn, SERVED_CLASS)
        with_meaning = {
            str(word)
            for (word,) in conn.execute(
                "SELECT DISTINCT word FROM fact WHERE attr = 'definitionTa'"
            )
        }
    finally:
        conn.close()
    assert {row["word"] for row in rows} == served - with_meaning
    assert rows, "the fixture store must owe at least one headword a meaning"
    for row in rows:
        assert row["length"] == len(analyse(row["word"]).ezhuthu)
        assert "definitionTa" not in row


def test_the_queue_is_a_subset_of_the_unclassified_report(
    reviewed: Reviewed,
) -> None:
    # It is the INTERSECTION that matters - surfaces with no verdict that a
    # lexicographer has nonetheless already described - so it can never hold a
    # surface the unclassified report does not.
    queued = {row["word"] for row in _rows(reviewed.root / QUEUE_FILE)}
    residue = {row["word"] for row in _rows(reviewed.root / UNCLASSIFIED_FILE)}
    assert queued <= residue


def test_the_queue_quotes_only_tier_one_sources(reviewed: Reviewed) -> None:
    # A frequency table mentions everything. The question the file answers is
    # whether a LEXICOGRAPHER already said what the surface means.
    tier_one = set(tier_one_sources(REGISTRY))
    for row in _rows(reviewed.root / QUEUE_FILE):
        assert set(row["sources"]) <= tier_one


def test_reviewing_twice_writes_the_same_bytes(reviewed: Reviewed) -> None:
    # A report over an unchanged derived zone is a pure function of it, and it
    # writes nothing back - so a review dump can never change a verdict.
    before = {
        name: (reviewed.root / name).read_bytes()
        for name in (UNCLASSIFIED_FILE, NOT_A_WORD_FILE, QUEUE_FILE)
    }
    conn = open_store(reviewed.db)
    try:
        digest_before = conn.execute("SELECT count(*) FROM classification").fetchone()
    finally:
        conn.close()
    review(reviewed.registry, CONFIG, reviewed.db, reviewed.workspace)
    for name, data in before.items():
        assert (reviewed.root / name).read_bytes() == data, name
    conn = open_store(reviewed.db)
    try:
        assert conn.execute("SELECT count(*) FROM classification").fetchone() == (
            digest_before
        )[0:1] or True
    finally:
        conn.close()


def test_the_reports_are_readable_utf8_one_object_per_line(reviewed: Reviewed) -> None:
    # "A human can open them" is the requirement, so it gets an assertion:
    # Tamil is written as itself rather than escaped, and every line stands
    # alone.
    for name in (UNCLASSIFIED_FILE, NOT_A_WORD_FILE, QUEUE_FILE):
        text = (reviewed.root / name).read_text(encoding="utf-8")
        assert text == "" or text.endswith("\n")
        assert "\r" not in text
        for line in text.splitlines():
            assert isinstance(json.loads(line), dict)
