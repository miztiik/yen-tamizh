"""The wordsmith store - the substrate STAGE and ENRICH write into (Row 6).

One stdlib ``sqlite3`` file at ``datasets/lexicon/cache/lexicon.db``, gitignored
and rebuildable from the extracts by one command. Why SQLite, why it is never an
output, and why the store has two zones is
``docs/architecture/lexicon/pipeline.md``; what the rows MEAN - observation
versus attestation, what a fact is - is ``docs/concepts/lexicon.md``.

TWO ZONES, and the split is what makes ``delta == full`` true at all:

- **STAGED**, written only by STAGE: ``source``, ``observation``, ``fact``.
  Every row carries the ``source_id`` that asserted it, nothing is resolved at
  merge time, and the whole zone is therefore COMMUTATIVE - the same set of
  extracts produces the same rows whatever order they arrive in.
- **DERIVED**, written only by ENRICH (row 7 onward): ``signal`` and
  ``classification``. Four of the eight signals are whole-corpus functions, so
  a delta-built derived zone would carry values computed over a pre-delta fact
  set. It is therefore not merged at all: it is dropped and recomputed whole,
  and ``stage_epoch`` / ``derived_epoch`` are what let PUBLISH refuse a store
  whose derived zone is behind its staged one.

The two epoch tables are the store's VERSION STAMPS rather than its content:
``stage_epoch`` counts writes, so it is path-dependent BY DESIGN - that is the
only way it can be certain to notice a write. ``canonical_dump`` therefore dumps
every DATA table, in both zones, and the epochs get their own predicates.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# Bumped whenever this file's shape changes in a way that makes an existing
# store unreadable. The store is a rebuildable cache, so there is no migration:
# the stamp exists so a stale file fails loudly instead of half-working.
STORE_VERSION: Final = "2026-08-15"

# Named, not defaulted. Without them an 8.2M-row load runs at 1-3k rows/s.
# `synchronous=OFF` is legitimate HERE AND ONLY HERE: this file is gitignored
# and rebuildable, and the reproducibility anchor is the published artifact -
# a SQLite file is not byte-deterministic (page layout, free-list state) and
# could never be one.
BULK_PRAGMAS: Final[tuple[tuple[str, str], ...]] = (
    ("journal_mode", "WAL"),
    ("synchronous", "OFF"),
    ("cache_size", "-262144"),
    ("temp_store", "MEMORY"),
    ("mmap_size", "268435456"),
)

STAGED_TABLES: Final[tuple[str, ...]] = ("source", "observation", "fact")
DERIVED_TABLES: Final[tuple[str, ...]] = ("signal", "classification")
EPOCH_TABLES: Final[tuple[str, ...]] = ("stage_epoch", "derived_epoch")

# The eight word-hood signals, one COLUMN each rather than one ROW each. At
# ~3.97M surfaces the EAV shape is 31.7M rows and ~2.9 GB against ~360 MB, and
# it turns every whole-corpus aggregation into a GROUP BY over 31.7M rows. Rows
# 7 and 8 stay independent through `ALTER TABLE ADD COLUMN`, which is O(1)
# metadata in SQLite and free anyway because the zone is recomputed whole.
SIGNAL_COLUMNS: Final[tuple[str, ...]] = (
    "attested",
    "orthotactic",
    "breadth",
    "nannulValid",
    "knownVerbForm",
    "ngram",
    "neighbour",
    "zipf",
)

_SIGNAL_DDL = ",\n    ".join(f'"{name}" REAL' for name in SIGNAL_COLUMNS)

# No foreign keys. They would cost a parent lookup on each of ~11.6M inserts to
# enforce what the apply transaction already guarantees: a source's rows are
# written and deleted together with its `source` row, inside one transaction.
_SCHEMA: Final[tuple[str, ...]] = (
    # ---- STAGED zone -----------------------------------------------------
    """
    CREATE TABLE IF NOT EXISTS source (
        id          TEXT    NOT NULL,
        sha256      TEXT    NOT NULL,
        bytes       INTEGER NOT NULL,
        role        TEXT    NOT NULL,
        precedence  INTEGER NOT NULL,
        kind        TEXT    NOT NULL,
        PRIMARY KEY (id)
    ) WITHOUT ROWID
    """,
    # WITHOUT ROWID because the primary key IS the access path: a rowid table
    # would keep a second full copy of (source_id, surface) as an autoindex.
    # `source_id` leads so a per-source delete is a range scan and so one
    # source's rows load into one contiguous key range.
    """
    CREATE TABLE IF NOT EXISTS observation (
        source_id   TEXT    NOT NULL,
        surface     TEXT    NOT NULL,
        count       INTEGER NOT NULL,
        PRIMARY KEY (source_id, surface)
    ) WITHOUT ROWID
    """,
    # Deliberately no uniqueness constraint: facts are not resolved at merge
    # time (that happens at PUBLISH, which is what keeps this zone
    # commutative), and a unique index would have to be maintained DURING the
    # bulk load, which is the cost the pragmas above exist to avoid.
    """
    CREATE TABLE IF NOT EXISTS fact (
        source_id   TEXT    NOT NULL,
        word        TEXT    NOT NULL,
        attr        TEXT    NOT NULL,
        value       TEXT    NOT NULL,
        ordinal     INTEGER NOT NULL
    )
    """,
    # ---- DERIVED zone ----------------------------------------------------
    f"""
    CREATE TABLE IF NOT EXISTS signal (
        word TEXT NOT NULL,
        {_SIGNAL_DDL},
        PRIMARY KEY (word)
    ) WITHOUT ROWID
    """,
    """
    CREATE TABLE IF NOT EXISTS classification (
        word      TEXT NOT NULL,
        wordClass TEXT NOT NULL,
        PRIMARY KEY (word)
    ) WITHOUT ROWID
    """,
    # ---- version stamps --------------------------------------------------
    "CREATE TABLE IF NOT EXISTS stage_epoch (n INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS derived_epoch (n INTEGER NOT NULL)",
)

# Created AFTER the bulk load, never during it, and dropped again before the
# next one. Maintaining these while ~11.6M rows stream in is the difference
# between minutes and hours.
_INDEXES: Final[tuple[tuple[str, str], ...]] = (
    ("idx_fact_source", "CREATE INDEX idx_fact_source ON fact(source_id)"),
    ("idx_fact_word", "CREATE INDEX idx_fact_word ON fact(word)"),
    (
        "idx_observation_surface",
        "CREATE INDEX idx_observation_surface ON observation(surface)",
    ),
)

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True, slots=True)
class StoreStats:
    """What the staged zone currently holds, measured rather than projected."""

    sources: int
    observations: int
    facts: int
    distinctSurfaces: int
    distinctFactWords: int
    distinctWords: int

    def note(self) -> str:
        return (
            f"sources={self.sources} observations={self.observations} "
            f"facts={self.facts} distinctSurfaces={self.distinctSurfaces} "
            f"distinctFactWords={self.distinctFactWords} "
            f"distinctWords={self.distinctWords}"
        )


def quoted(name: str) -> str:
    """Quote one SQLite identifier, refusing anything that is not one.

    Table and column names reach the SQL text by interpolation because SQLite
    cannot bind them; they come from ``sqlite_schema`` rather than from a user,
    and this check is what keeps that true even if a later row adds a table.
    """
    if not _IDENTIFIER.match(name):
        raise ValueError(f"{name!r} is not a bare SQLite identifier")
    return f'"{name}"'


def connect(path: Path) -> sqlite3.Connection:
    """Open the store with the bulk-load pragmas named and applied."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None turns OFF the driver's implicit transaction handling
    # so `transaction()` below is the only thing that opens one - which is what
    # makes "one store operation, one transaction" checkable rather than hoped.
    conn = sqlite3.connect(path, isolation_level=None)
    for pragma, value in BULK_PRAGMAS:
        conn.execute(f"PRAGMA {pragma} = {value}")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """Create both zones and seed the version stamps. Idempotent."""
    with transaction(conn):
        for statement in _SCHEMA:
            conn.execute(statement)
        for table in EPOCH_TABLES:
            conn.execute(
                f"INSERT INTO {quoted(table)} (n) SELECT 0 "
                f"WHERE NOT EXISTS (SELECT 1 FROM {quoted(table)})"
            )


def open_store(path: Path) -> sqlite3.Connection:
    """Connect to the store at ``path``, creating it if it is not there yet."""
    conn = connect(path)
    create_schema(conn)
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """One store operation, one transaction.

    ``BEGIN IMMEDIATE`` rather than a deferred begin: the write lock is taken
    up front, so a concurrent writer fails at the start of the operation rather
    than half-way through it.
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    conn.commit()


# --------------------------------------------------------------------------
# Version stamps
# --------------------------------------------------------------------------


def _epoch(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT n FROM {quoted(table)}").fetchone()
    if row is None:
        raise ValueError(f"{table} holds no row - the store schema is incomplete")
    return int(row[0])


def stage_epoch(conn: sqlite3.Connection) -> int:
    """The staged zone's version: how many times STAGE has written."""
    return _epoch(conn, "stage_epoch")


def derived_epoch(conn: sqlite3.Connection) -> int:
    """The staged version the derived zone was last computed over."""
    return _epoch(conn, "derived_epoch")


def bump_stage_epoch(conn: sqlite3.Connection) -> int:
    """Record that STAGE wrote. Call INSIDE the caller's transaction.

    A counter rather than a digest of the staged content, and the asymmetry is
    the point: a counter can only ever claim the derived zone is stale when it
    is not, which costs one recompute. A content digest can claim the derived
    zone is CURRENT when it is not - the extractor version is not part of the
    staged content - and that ships wrong data.
    """
    conn.execute("UPDATE stage_epoch SET n = n + 1")
    return stage_epoch(conn)


def set_derived_epoch(conn: sqlite3.Connection, n: int) -> None:
    """Stamp the derived zone with the staged version it was computed over."""
    conn.execute("UPDATE derived_epoch SET n = ?", (n,))


def derived_is_current(conn: sqlite3.Connection) -> bool:
    """Whether the derived zone was computed over the staged zone as it stands.

    The guard PUBLISH refuses on. A fresh store answers True, and correctly so:
    an empty derived zone IS the right function of an empty staged zone.
    """
    return derived_epoch(conn) == stage_epoch(conn)


# --------------------------------------------------------------------------
# Indexes
# --------------------------------------------------------------------------


def drop_indexes(conn: sqlite3.Connection) -> None:
    """Remove the secondary indexes so a bulk load does not maintain them."""
    with transaction(conn):
        for name, _ in _INDEXES:
            conn.execute(f"DROP INDEX IF EXISTS {quoted(name)}")


def create_indexes(conn: sqlite3.Connection) -> None:
    """Rebuild the secondary indexes after a bulk load."""
    with transaction(conn):
        for name, statement in _INDEXES:
            conn.execute(f"DROP INDEX IF EXISTS {quoted(name)}")
            conn.execute(statement)


def index_names(conn: sqlite3.Connection) -> list[str]:
    """The secondary indexes currently on the store, sorted."""
    rows = conn.execute(
        "SELECT name FROM sqlite_schema WHERE type = 'index' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [str(row[0]) for row in rows]


# --------------------------------------------------------------------------
# The canonical dump - the instrument the `delta == full` Oracle is proved with
# --------------------------------------------------------------------------


def data_tables(conn: sqlite3.Connection) -> list[str]:
    """Every DATA table in the store, in both zones, discovered not listed.

    Discovered from ``sqlite_schema`` so a table a later row adds is covered
    without anyone remembering to add it here. The two ``*_epoch`` version
    stamps are the only exclusion, and it is a structural rule rather than a
    per-case one: they count WRITES, so they are path-dependent by design and a
    path-independence Oracle over them would be asserting the guard is broken.
    """
    rows = conn.execute(
        "SELECT name FROM sqlite_schema WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [str(row[0]) for row in rows if str(row[0]) not in EPOCH_TABLES]


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """One table's declared columns, in declaration order."""
    rows = conn.execute(f"PRAGMA table_info({quoted(table)})").fetchall()
    return [str(row[1]) for row in rows]


def iter_canonical_dump(conn: sqlite3.Connection) -> Iterator[str]:
    """Stream the store's content in an order that depends only on content.

    Every data table, every column, ``ORDER BY`` all of them, and ``rowid``
    never selected - because insertion order differs between a full rebuild and
    a delta build BY CONSTRUCTION, so any implicit-order dump would compare the
    build path rather than the result.
    """
    for table in data_tables(conn):
        columns = table_columns(conn, table)
        projection = ", ".join(quoted(column) for column in columns)
        yield f"# {table}({','.join(columns)})"
        cursor = conn.execute(
            f"SELECT {projection} FROM {quoted(table)} ORDER BY {projection}"
        )
        for row in cursor:
            yield json.dumps(list(row), ensure_ascii=False, separators=(",", ":"))


def canonical_dump(conn: sqlite3.Connection) -> str:
    """The whole canonical dump as text. For stores small enough to hold."""
    return "".join(f"{line}\n" for line in iter_canonical_dump(conn))


def canonical_digest(conn: sqlite3.Connection) -> str:
    """The canonical dump's sha256, so a real store can be compared too."""
    digest = hashlib.sha256()
    for line in iter_canonical_dump(conn):
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


# --------------------------------------------------------------------------
# Measurement
# --------------------------------------------------------------------------


def _scalar(conn: sqlite3.Connection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    if row is None:
        raise ValueError(f"{sql!r} returned no row")
    return int(row[0])


def store_stats(conn: sqlite3.Connection) -> StoreStats:
    """Measured counts over the staged zone.

    ``distinctWords`` is the union of observed surfaces and worded facts - the
    population PUBLISH will render one row per - and it is the number this row's
    sizing is reported against.
    """
    return StoreStats(
        sources=_scalar(conn, "SELECT count(*) FROM source"),
        observations=_scalar(conn, "SELECT count(*) FROM observation"),
        facts=_scalar(conn, "SELECT count(*) FROM fact"),
        distinctSurfaces=_scalar(conn, "SELECT count(DISTINCT surface) FROM observation"),
        distinctFactWords=_scalar(conn, "SELECT count(DISTINCT word) FROM fact"),
        distinctWords=_scalar(
            conn,
            "SELECT count(*) FROM ("
            "SELECT surface AS w FROM observation UNION SELECT word FROM fact)",
        ),
    )


def staged_sources(conn: sqlite3.Connection) -> list[str]:
    """The source ids currently staged, sorted."""
    rows = conn.execute("SELECT id FROM source ORDER BY id").fetchall()
    return [str(row[0]) for row in rows]
