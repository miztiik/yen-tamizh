"""Tests for the wordsmith STAGE stage and its store (Row 6).

Real committed fixtures throughout, no mocks (Holy Law #7). Every extract these
tests stage is produced by running the REAL extractor over the byte-exact
fixture slices under ``datasets/fixtures/lexicon/``, so the whole suite runs in
CI with no raw sources on disk; the one check that wants the operator's real
1.2 GB extract cache skips cleanly when it is absent.

The row's whole point is one predicate:

    delta == full

A canonical dump of a store built by full rebuild is IDENTICAL to one built by
applying the same extracts one at a time in a shuffled order, and identical
again after removing and re-applying any one source. Everything else here
either supports that claim or guards the properties it rests on: one
transaction per operation, SUM on observation conflicts, no resolution at merge
time, and a version stamp that notices every write.
"""

from __future__ import annotations

import hashlib
import json
import random
import shutil
import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from _lexicon_workspace import source_bytes
from yen_tamizh_backend.contracts.lexicon_sources import LexiconSource, LexiconSources
from yen_tamizh_backend.wordsmith.extract import (
    extract,
    header_of,
    load_registry,
    render,
    sha256_of,
)
from yen_tamizh_backend.wordsmith.stage import (
    apply_extract,
    extract_path,
    read_header,
    remove_source,
    stage,
    store_path,
)
from yen_tamizh_backend.wordsmith.store import (
    BULK_PRAGMAS,
    DERIVED_TABLES,
    EPOCH_TABLES,
    SIGNAL_COLUMNS,
    STAGED_TABLES,
    canonical_digest,
    canonical_dump,
    create_indexes,
    data_tables,
    derived_epoch,
    derived_is_current,
    drop_indexes,
    index_names,
    open_store,
    stage_epoch,
    staged_sources,
    store_stats,
    table_columns,
    transaction,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = _REPO_ROOT / "config" / "lexicon-sources.json"
_FIXTURES = _REPO_ROOT / "datasets" / "fixtures" / "lexicon"
_GITIGNORE = _REPO_ROOT / ".gitignore"

REGISTRY = load_registry(_REGISTRY_PATH)
SOURCES = list(REGISTRY.sources)

# A real shuffle over source order, seeded so a failure is reproducible, and
# more than one of them so the Oracle proves COMMUTATIVITY rather than one
# lucky ordering.
SHUFFLE_SEEDS = (20260815, 7, 99991, 2718281, 31337)


@dataclass(frozen=True, slots=True)
class Workspace:
    """Nineteen real extracts, made from the committed fixtures, in one tree."""

    registry: LexiconSources
    root: Path

    def source(self, source_id: str) -> LexiconSource:
        return next(entry for entry in self.registry.sources if entry.id == source_id)

    def extract(self, source_id: str) -> Path:
        return extract_path(self.registry, self.root, source_id)


@pytest.fixture(scope="session")
def workspace(tmp_path_factory: pytest.TempPathFactory) -> Workspace:
    """Extract every committed fixture once, and let each test stage its own store."""
    root = tmp_path_factory.mktemp("wordsmith")
    entries: list[dict[str, Any]] = []
    for source in SOURCES:
        fixture = source_bytes(_REPO_ROOT, _FIXTURES, source)
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
                # The one known-bad source is disabled in the real registry.
                # Here it is staged like any other, because a store that can
                # hold it is a store that can drop it again.
                "enabled": True,
            }
        )
    registry = LexiconSources.model_validate(
        REGISTRY.model_dump(exclude_none=True) | {"lexiconRoot": "out", "sources": entries}
    )
    extract(registry, root, force=True)
    return Workspace(registry=registry, root=root)


def dump_of(db: Path) -> str:
    conn = open_store(db)
    try:
        return canonical_dump(conn)
    finally:
        conn.close()


def epochs_of(db: Path) -> tuple[int, int]:
    conn = open_store(db)
    try:
        return stage_epoch(conn), derived_epoch(conn)
    finally:
        conn.close()


def build_full(workspace: Workspace, db: Path) -> Path:
    """One run that applies every source: the reference build."""
    stage(workspace.registry, workspace.root, db)
    return db


def traced(conn: sqlite3.Connection, action: Callable[[], None]) -> list[str]:
    """Every SQL statement one operation issues, in order."""
    seen: list[str] = []
    conn.set_trace_callback(seen.append)
    try:
        action()
    finally:
        conn.set_trace_callback(None)
    return seen


def write_extract(
    path: Path, source: LexiconSource, records: Sequence[dict[str, Any]]
) -> Path:
    """A hand-written extract in the REAL extract format.

    Written through the extractor's own header and line renderers, so a test
    that needs a shape the fixtures happen not to contain - one source naming a
    surface twice, two sources contradicting each other - gets a genuine
    artifact rather than a mock of one.
    """
    summary = {
        "record": "summary",
        "rowsIn": len(records),
        "rowsOut": len(records),
        "parseRejects": 0,
        "observations": sum(1 for r in records if r["record"] == "observation"),
        "facts": sum(1 for r in records if r["record"] == "fact"),
        "posUnparsed": 0,
        "posRejected": 0,
    }
    lines = [header_of(source, source.sha256, source.bytes), *records, summary]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(render(line) for line in lines), encoding="utf-8", newline="\n"
    )
    return path


def observation(surface: str, count: int) -> dict[str, Any]:
    return {"record": "observation", "surface": surface, "count": count}


def fact(word: str, attr: str, value: str, ordinal: int = 0) -> dict[str, Any]:
    return {"record": "fact", "word": word, "attr": attr, "value": value, "ordinal": ordinal}


# --------------------------------------------------------------------------
# 1. The store has two zones, and the schema says so
# --------------------------------------------------------------------------


def test_a_fresh_store_carries_both_zones_and_no_secondary_indexes(
    tmp_path: Path,
) -> None:
    conn = open_store(tmp_path / "lexicon.db")
    try:
        assert set(data_tables(conn)) == set(STAGED_TABLES) | set(DERIVED_TABLES)
        # Every index is created after the bulk load, so a store that has never
        # been loaded has none at all.
        assert index_names(conn) == []
    finally:
        conn.close()


def test_the_signal_table_is_wide_one_column_per_signal(tmp_path: Path) -> None:
    conn = open_store(tmp_path / "lexicon.db")
    try:
        assert table_columns(conn, "signal") == ["word", *SIGNAL_COLUMNS]
        assert table_columns(conn, "classification") == ["word", "wordClass"]
        # No `source_id` anywhere in the derived zone: no signal IS per-source,
        # and a fake one would make `DELETE WHERE source_id = ?` silently wrong.
        for table in DERIVED_TABLES:
            assert "source_id" not in table_columns(conn, table)
    finally:
        conn.close()


def test_both_epochs_start_at_zero_and_a_fresh_derived_zone_is_current(
    tmp_path: Path,
) -> None:
    conn = open_store(tmp_path / "lexicon.db")
    try:
        assert (stage_epoch(conn), derived_epoch(conn)) == (0, 0)
        # Correct, not a loophole: an empty derived zone IS the right function
        # of an empty staged zone.
        assert derived_is_current(conn) is True
    finally:
        conn.close()


def test_the_bulk_load_pragmas_are_applied_not_merely_named(tmp_path: Path) -> None:
    expected = {
        "journal_mode": "wal",
        "synchronous": 0,
        "cache_size": -262144,
        "temp_store": 2,
        "mmap_size": 268435456,
    }
    conn = open_store(tmp_path / "lexicon.db")
    try:
        assert [name for name, _ in BULK_PRAGMAS] == list(expected)
        for pragma, want in expected.items():
            row = conn.execute(f"PRAGMA {pragma}").fetchone()
            assert row is not None and row[0] == want, pragma
    finally:
        conn.close()


# --------------------------------------------------------------------------
# 2. Every store operation is one transaction
# --------------------------------------------------------------------------


def test_every_store_operation_runs_in_exactly_one_transaction(
    workspace: Workspace, tmp_path: Path
) -> None:
    source = workspace.source("themed-vocabulary")
    conn = open_store(tmp_path / "lexicon.db")

    def apply() -> None:
        apply_extract(conn, workspace.extract(source.id), source)

    def remove() -> None:
        remove_source(conn, source.id)

    try:
        operations: dict[str, Callable[[], None]] = {
            "drop_indexes": lambda: drop_indexes(conn),
            "apply": apply,
            "create_indexes": lambda: create_indexes(conn),
            "remove": remove,
        }
        for name, operation in operations.items():
            statements = traced(conn, operation)
            assert statements.count("BEGIN IMMEDIATE") == 1, name
            assert statements.count("COMMIT") == 1, name
            assert statements[0] == "BEGIN IMMEDIATE", name
            assert statements[-1] == "COMMIT", name
    finally:
        conn.close()


def test_a_failure_mid_apply_leaves_the_store_exactly_as_it_was(
    workspace: Workspace, tmp_path: Path
) -> None:
    db = build_full(workspace, tmp_path / "lexicon.db")
    before, epochs_before = dump_of(db), epochs_of(db)

    source = workspace.source("themed-vocabulary")
    truncated = tmp_path / "truncated.jsonl"
    records = [observation("\u0b95", 1), fact("\u0b95", "category", "birds")]
    write_extract(truncated, source, records)
    # A real truncation: the summary declares more facts than the file holds,
    # which is what a crashed writer leaves behind.
    lines = truncated.read_text(encoding="utf-8").splitlines()
    summary = json.loads(lines[-1])
    summary["facts"] = 99
    lines[-1] = json.dumps(summary, ensure_ascii=False, separators=(",", ":"))
    truncated.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    conn = open_store(db)
    try:
        with pytest.raises(ValueError, match="declares 99 facts"):
            apply_extract(conn, truncated, source)
    finally:
        conn.close()

    assert dump_of(db) == before
    assert epochs_of(db) == epochs_before


def test_a_stale_extract_is_refused_before_anything_is_written(
    workspace: Workspace, tmp_path: Path
) -> None:
    db = build_full(workspace, tmp_path / "lexicon.db")
    before, epochs_before = dump_of(db), epochs_of(db)
    source = workspace.source("wiki")
    moved = LexiconSource.model_validate(
        source.model_dump(exclude_none=True) | {"sha256": "0" * 64}
    )
    conn = open_store(db)
    try:
        with pytest.raises(ValueError, match="re-run EXTRACT"):
            apply_extract(conn, workspace.extract(source.id), moved)
    finally:
        conn.close()
    assert dump_of(db) == before
    assert epochs_of(db) == epochs_before


def test_removing_a_source_that_is_not_staged_changes_nothing(
    workspace: Workspace, tmp_path: Path
) -> None:
    db = build_full(workspace, tmp_path / "lexicon.db")
    before, epochs_before = dump_of(db), epochs_of(db)
    conn = open_store(db)
    try:
        with pytest.raises(ValueError, match="is not staged"):
            remove_source(conn, "madras-lexicon")
    finally:
        conn.close()
    assert dump_of(db) == before
    assert epochs_of(db) == epochs_before


# --------------------------------------------------------------------------
# 3. The merge rules the Oracle rests on
# --------------------------------------------------------------------------


def test_observation_conflicts_sum_within_a_source(
    workspace: Workspace, tmp_path: Path
) -> None:
    source = workspace.source("wiki")
    twice = write_extract(
        tmp_path / "twice.jsonl",
        source,
        [observation("\u0b95\u0b9f\u0bb2", 3), observation("\u0b95\u0b9f\u0bb2", 4)],
    )
    conn = open_store(tmp_path / "lexicon.db")
    try:
        result = apply_extract(conn, twice, source)
        assert result.tally.observations == 2
        assert result.tally.surfaces == 1
        row = conn.execute("SELECT count FROM observation").fetchone()
        assert row is not None and row[0] == 7
    finally:
        conn.close()


def test_facts_are_not_resolved_at_merge_time(
    workspace: Workspace, tmp_path: Path
) -> None:
    """Two sources contradicting each other both keep their row.

    Resolution happens at PUBLISH, where precedence is known. A merge that
    picked a winner here would depend on which source arrived first, and that
    is exactly what `delta == full` forbids.
    """
    first, second = workspace.source("wiki"), workspace.source("dinamalar")
    word = "\u0b95\u0b9f\u0bb2"
    a = write_extract(tmp_path / "a.jsonl", first, [fact(word, "pos", "noun")])
    b = write_extract(tmp_path / "b.jsonl", second, [fact(word, "pos", "verb")])
    conn = open_store(tmp_path / "lexicon.db")
    try:
        apply_extract(conn, a, first)
        apply_extract(conn, b, second)
        rows = conn.execute(
            "SELECT source_id, value FROM fact ORDER BY source_id"
        ).fetchall()
        assert [(str(row[0]), str(row[1])) for row in rows] == [
            ("dinamalar", "verb"),
            ("wiki", "noun"),
        ]
    finally:
        conn.close()


def test_applying_one_source_leaves_every_other_source_untouched(
    workspace: Workspace, tmp_path: Path
) -> None:
    db = build_full(workspace, tmp_path / "lexicon.db")
    others = {
        source.id: _rows_for(db, source.id)
        for source in workspace.registry.sources
        if source.id != "wiki"
    }
    stage(workspace.registry, workspace.root, db, only="wiki")
    for source_id, rows in others.items():
        assert _rows_for(db, source_id) == rows, source_id


def test_removing_a_source_removes_exactly_its_rows(
    workspace: Workspace, tmp_path: Path
) -> None:
    db = build_full(workspace, tmp_path / "lexicon.db")
    others = {
        source.id: _rows_for(db, source.id)
        for source in workspace.registry.sources
        if source.id != "wiki"
    }
    stage(workspace.registry, workspace.root, db, remove="wiki")
    conn = open_store(db)
    try:
        assert "wiki" not in staged_sources(conn)
    finally:
        conn.close()
    assert _rows_for(db, "wiki") == ([], [])
    for source_id, rows in others.items():
        assert _rows_for(db, source_id) == rows, source_id


def _rows_for(db: Path, source_id: str) -> tuple[list[Any], list[Any]]:
    conn = open_store(db)
    try:
        observations = conn.execute(
            "SELECT surface, count FROM observation WHERE source_id = ? "
            "ORDER BY surface, count",
            (source_id,),
        ).fetchall()
        facts = conn.execute(
            "SELECT word, attr, value, ordinal FROM fact WHERE source_id = ? "
            "ORDER BY word, attr, value, ordinal",
            (source_id,),
        ).fetchall()
        return observations, facts
    finally:
        conn.close()


# --------------------------------------------------------------------------
# 4. The canonical dump - the Oracle's instrument, tested as one
# --------------------------------------------------------------------------


def test_the_canonical_dump_covers_every_table_except_the_two_version_stamps(
    tmp_path: Path,
) -> None:
    conn = open_store(tmp_path / "lexicon.db")
    try:
        every = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        }
        assert every - set(data_tables(conn)) == set(EPOCH_TABLES)
        # Every column of every dumped table appears in the dump's own header.
        dump = canonical_dump(conn)
        for table in data_tables(conn):
            columns = ",".join(table_columns(conn, table))
            assert f"# {table}({columns})" in dump
    finally:
        conn.close()


def test_the_canonical_dump_orders_by_content_and_never_by_insertion(
    tmp_path: Path,
) -> None:
    rows = [
        ("wiki", "\u0b95", "pos", "noun", 0),
        ("dinamalar", "\u0b9a", "category", "birds", 1),
        ("wiki", "\u0b95", "pos", "verb", 0),
    ]
    dumps: list[str] = []
    for order in (rows, list(reversed(rows))):
        conn = open_store(tmp_path / f"{len(dumps)}.db")
        try:
            with transaction(conn):
                conn.executemany("INSERT INTO fact VALUES (?,?,?,?,?)", order)
            dumps.append(canonical_dump(conn))
            tables = len(data_tables(conn))
        finally:
            conn.close()
    assert dumps[0] == dumps[1]
    assert dumps[0].count("\n") == tables + len(rows)


def test_the_canonical_digest_agrees_with_the_dump(
    workspace: Workspace, tmp_path: Path
) -> None:
    db = build_full(workspace, tmp_path / "lexicon.db")
    conn = open_store(db)
    try:
        assert canonical_digest(conn) == hashlib.sha256(
            canonical_dump(conn).encode("utf-8")
        ).hexdigest()
    finally:
        conn.close()


# --------------------------------------------------------------------------
# 5. THE ORACLE: delta == full over the staged zone
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", SHUFFLE_SEEDS)
def test_delta_equals_full_over_a_shuffled_apply_order(
    workspace: Workspace, tmp_path: Path, seed: int
) -> None:
    order = [source.id for source in workspace.registry.sources]
    shuffled = list(order)
    random.Random(seed).shuffle(shuffled)
    assert shuffled != order, f"seed {seed} did not actually shuffle the order"

    full = dump_of(build_full(workspace, tmp_path / "full.db"))

    delta = tmp_path / "delta.db"
    for source_id in shuffled:
        stage(workspace.registry, workspace.root, delta, only=source_id)

    assert dump_of(delta) == full, f"delta != full for shuffle seed {seed}: {shuffled}"


def test_delta_equals_full_after_removing_and_re_applying_any_one_source(
    workspace: Workspace, tmp_path: Path
) -> None:
    db = build_full(workspace, tmp_path / "lexicon.db")
    baseline = dump_of(db)
    for source in workspace.registry.sources:
        stage(workspace.registry, workspace.root, db, remove=source.id)
        assert dump_of(db) != baseline, f"removing {source.id} changed nothing"
        stage(workspace.registry, workspace.root, db, only=source.id)
        assert dump_of(db) == baseline, f"re-applying {source.id} did not restore it"


def test_re_applying_an_unchanged_extract_changes_only_the_version_stamp(
    workspace: Workspace, tmp_path: Path
) -> None:
    db = build_full(workspace, tmp_path / "lexicon.db")
    before, (staged_before, _) = dump_of(db), epochs_of(db)
    stage(workspace.registry, workspace.root, db, only="wiki")
    assert dump_of(db) == before
    assert epochs_of(db)[0] == staged_before + 1


# --------------------------------------------------------------------------
# 6. The version stamps rows 7-11 depend on
# --------------------------------------------------------------------------


def test_the_stage_epoch_advances_on_every_write(
    workspace: Workspace, tmp_path: Path
) -> None:
    db = tmp_path / "lexicon.db"
    run = stage(workspace.registry, workspace.root, db)
    # One bump per source applied, and nothing else in the run bumps it.
    assert [result.epoch for result in run.applied] == list(
        range(1, len(run.applied) + 1)
    )
    assert epochs_of(db)[0] == len(workspace.registry.sources)

    stage(workspace.registry, workspace.root, db, remove="wiki")
    assert epochs_of(db)[0] == len(workspace.registry.sources) + 1
    stage(workspace.registry, workspace.root, db, only="wiki")
    assert epochs_of(db)[0] == len(workspace.registry.sources) + 2


def test_a_staged_write_puts_the_derived_zone_behind_the_staged_one(
    workspace: Workspace, tmp_path: Path
) -> None:
    db = build_full(workspace, tmp_path / "lexicon.db")
    conn = open_store(db)
    try:
        # ENRICH lands in row 7; this is the guard it will stamp and PUBLISH
        # will refuse on.
        assert derived_is_current(conn) is False
        assert derived_epoch(conn) == 0 < stage_epoch(conn)
    finally:
        conn.close()


def test_a_stage_write_never_touches_the_derived_zone(
    workspace: Workspace, tmp_path: Path
) -> None:
    db = build_full(workspace, tmp_path / "lexicon.db")
    conn = open_store(db)
    try:
        for table in DERIVED_TABLES:
            row = conn.execute(f"SELECT count(*) FROM {table}").fetchone()
            assert row is not None and row[0] == 0, table
    finally:
        conn.close()


# --------------------------------------------------------------------------
# 7. The store is build state, and the run reports what it holds
# --------------------------------------------------------------------------


def test_the_store_lives_in_the_gitignored_build_cache() -> None:
    path = store_path(REGISTRY, _REPO_ROOT).relative_to(_REPO_ROOT).as_posix()
    assert path == "datasets/lexicon/cache/lexicon.db"
    ignored = _GITIGNORE.read_text(encoding="utf-8").splitlines()
    # A directory pattern covers the database and both of its WAL sidecars,
    # which never exist as tracked paths for git to be asked about separately.
    assert "datasets/lexicon/cache/" in ignored


def test_a_full_run_reports_what_the_store_holds(
    workspace: Workspace, tmp_path: Path
) -> None:
    db = tmp_path / "lexicon.db"
    run = stage(workspace.registry, workspace.root, db)
    assert len(run.applied) == len(workspace.registry.sources)
    conn = open_store(db)
    try:
        stats = store_stats(conn)
        assert stats.sources == len(workspace.registry.sources)
        assert stats.observations == sum(
            result.tally.surfaces for result in run.applied
        )
        assert stats.facts == sum(result.tally.facts for result in run.applied)
        # The population PUBLISH renders one row per is the union of the two.
        assert stats.distinctWords >= max(
            stats.distinctSurfaces, stats.distinctFactWords
        )
        # The indexes are back after the load, and only after it.
        assert index_names(conn) == [
            "idx_fact_source",
            "idx_fact_word",
            "idx_observation_surface",
        ]
    finally:
        conn.close()


def test_an_extract_with_no_summary_is_refused(
    workspace: Workspace, tmp_path: Path
) -> None:
    source = workspace.source("wiki")
    path = write_extract(tmp_path / "crashed.jsonl", source, [observation("\u0b95", 1)])
    lines = path.read_text(encoding="utf-8").splitlines()[:-1]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    conn = open_store(tmp_path / "lexicon.db")
    try:
        with pytest.raises(ValueError, match="no summary record"):
            apply_extract(conn, path, source)
    finally:
        conn.close()


def test_an_extract_of_another_source_is_refused(
    workspace: Workspace, tmp_path: Path
) -> None:
    conn = open_store(tmp_path / "lexicon.db")
    try:
        with pytest.raises(ValueError, match="is the extract of"):
            apply_extract(conn, workspace.extract("wiki"), workspace.source("dinamalar"))
    finally:
        conn.close()


# --------------------------------------------------------------------------
# 8. The operator's real extract cache, when it is on this machine
# --------------------------------------------------------------------------


def test_the_real_extract_cache_agrees_with_the_registry() -> None:
    """The real 1.2 GB cache is gitignored, so this skips in CI.

    Only the header line of each extract is read - the full load is an operator
    action reported in the PR body, never a test, because a test that needs
    1.2 GB of gitignored bytes cannot pass where the suite actually runs.
    """
    enabled = [source for source in SOURCES if source.enabled]
    missing = [
        source.id
        for source in enabled
        if not extract_path(REGISTRY, _REPO_ROOT, source.id).exists()
    ]
    if missing:
        pytest.skip(f"no extract cache for {len(missing)} of {len(enabled)} sources")
    for source in enabled:
        header = read_header(extract_path(REGISTRY, _REPO_ROOT, source.id))
        assert header.sourceId == source.id
        assert header.sha256 == source.sha256
        assert header.role == source.role
        assert header.kind == source.kind
        assert header.precedence == source.precedence
