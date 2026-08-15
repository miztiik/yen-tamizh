"""STAGE - stage 2 of the wordsmith pipeline (Row 6).

Accumulates every extract into the store, one source at a time, so that a
source's contribution can be REPLACED or REMOVED without touching another
source's rows. The stage is explained in
``docs/architecture/lexicon/pipeline.md``; the store's two zones and its
transaction rules are ``store.py``.

The property this stage exists to have:

    delta == full

The staged zone built by applying nineteen extracts one at a time, in any
order, with any source removed and re-applied along the way, holds exactly the
rows a full rebuild holds. Three things buy it, and none of them is optional:

1. Every row carries the ``source_id`` that asserted it, and NOTHING is
   resolved at merge time. Resolution happens at PUBLISH, where precedence is
   known; a merge that picked a winner would depend on who arrived first.
2. ``observation`` conflicts SUM, which is commutative. ``REPLACE`` is not, and
   would make merge order decide a count.
3. Replace and remove are ONE TRANSACTION each - delete the source's rows,
   insert the new ones, stamp the epoch - so a crash leaves the store holding
   either the old contribution or the new one, never half of each.

Everything streams. Rows are handed to ``executemany`` as a GENERATOR over the
extract file, never a materialized list: the largest extract is 445 MB and
2.7M facts, and reading it into memory to insert it would trade the whole
streaming property of stage 1 away at stage 2.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yen_tamizh_backend.contracts.lexicon_sources import LexiconSource, LexiconSources
from yen_tamizh_backend.wordsmith.extract import load_registry
from yen_tamizh_backend.wordsmith.store import (
    bump_stage_epoch,
    create_indexes,
    drop_indexes,
    open_store,
    stage_epoch,
    staged_sources,
    store_stats,
    transaction,
)

# One row per fact, no conflict target: a fact is evidence, and two sources
# asserting the same thing is two pieces of evidence.
_FACT_INSERT = "INSERT INTO fact (source_id, word, attr, value, ordinal) VALUES (?,?,?,?,?)"

# SUM, because it is commutative: a source that names one surface on two lines
# has observed it twice, and which line arrived first must not change the total.
_OBSERVATION_UPSERT = (
    "INSERT INTO observation (source_id, surface, count) VALUES (?,?,?) "
    "ON CONFLICT (source_id, surface) DO UPDATE SET count = count + excluded.count"
)

_SOURCE_INSERT = (
    "INSERT INTO source (id, sha256, bytes, role, precedence, kind) VALUES (?,?,?,?,?,?)"
)


@dataclass(frozen=True, slots=True)
class ExtractHeader:
    """The first line of an extract: which bytes it was made from, by whom."""

    sourceId: str
    role: str
    kind: str
    path: str
    bytes: int
    sha256: str
    precedence: int
    extractorVersion: str


@dataclass(slots=True)
class ApplyTally:
    """What one apply moved, counted while streaming rather than afterwards.

    ``surfaces`` is smaller than ``observations`` exactly when a source named
    one surface on more than one line, which is the case the SUM conflict
    action exists for.
    """

    observations: int = 0
    facts: int = 0
    surfaces: int = 0


@dataclass(slots=True)
class ApplyResult:
    """One source's staging, for the run summary."""

    id: str
    epoch: int
    seconds: float
    tally: ApplyTally = field(default_factory=ApplyTally)

    def note(self) -> str:
        tally = self.tally
        return (
            f"{self.id}: observations={tally.observations}"
            f"->{tally.surfaces} surfaces facts={tally.facts} "
            f"epoch={self.epoch} {self.seconds:.1f}s"
        )


@dataclass(slots=True)
class RemoveResult:
    """One source's removal, for the run summary."""

    id: str
    epoch: int
    observations: int
    facts: int

    def note(self) -> str:
        return (
            f"{self.id}: removed observations={self.observations} "
            f"facts={self.facts} epoch={self.epoch}"
        )


# --------------------------------------------------------------------------
# Reading an extract
# --------------------------------------------------------------------------


def _record(line: str, path: Path, number: int) -> dict[str, Any]:
    try:
        record: Any = json.loads(line)
    except ValueError as error:
        raise ValueError(f"{path.name} line {number} is not JSON: {error}") from error
    if not isinstance(record, dict):
        raise ValueError(f"{path.name} line {number} is not an extract record")
    return record


def read_header(path: Path) -> ExtractHeader:
    """The extract's header line, or a failure naming what is wrong with it."""
    if not path.exists():
        raise FileNotFoundError(
            f"no extract at {path.name} - run "
            f"`python -m yen_tamizh_backend.wordsmith.extract --source {path.stem}` first"
        )
    with path.open("r", encoding="utf-8") as handle:
        first = handle.readline()
    if not first.strip():
        raise ValueError(f"{path.name} is empty - the extract never completed")
    record = _record(first, path, 1)
    if record.get("record") != "header":
        raise ValueError(f"{path.name} does not begin with a header record")
    try:
        return ExtractHeader(
            sourceId=str(record["sourceId"]),
            role=str(record["role"]),
            kind=str(record["kind"]),
            path=str(record["path"]),
            bytes=int(record["bytes"]),
            sha256=str(record["sha256"]),
            precedence=int(record["precedence"]),
            extractorVersion=str(record["extractorVersion"]),
        )
    except KeyError as error:
        raise ValueError(f"{path.name} header is missing {error}") from error


def _iter_records(
    path: Path, wanted: str, tally_field: str, tally: ApplyTally
) -> Iterator[dict[str, Any]]:
    """Stream one record kind out of an extract, reconciling against its summary.

    The extract's own summary line says how many of each record it holds, and a
    pass that does not reach that number is reading a truncated file. Checking
    it HERE, inside the generator ``executemany`` is draining, means the failure
    lands inside the apply transaction and rolls the whole thing back.
    """
    seen_summary = False
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if number == 1 or not line.strip():
                continue
            record = _record(line, path, number)
            kind = record.get("record")
            if kind == wanted:
                setattr(tally, tally_field, getattr(tally, tally_field) + 1)
                yield record
            elif kind == "summary":
                seen_summary = True
                declared = int(record[tally_field])
                counted = int(getattr(tally, tally_field))
                if declared != counted:
                    raise ValueError(
                        f"{path.name} declares {declared} {tally_field} and holds "
                        f"{counted} - the extract is truncated or was hand-edited"
                    )
            elif kind not in ("observation", "fact"):
                raise ValueError(
                    f"{path.name} line {number} is a {kind!r} record, which this "
                    f"stage does not know how to read"
                )
    if not seen_summary:
        raise ValueError(
            f"{path.name} has no summary record - the extract never completed"
        )


def iter_observations(
    path: Path, source_id: str, tally: ApplyTally
) -> Iterator[tuple[str, str, int]]:
    """``(source_id, surface, count)`` rows, streamed."""
    for record in _iter_records(path, "observation", "observations", tally):
        yield source_id, str(record["surface"]), int(record["count"])


def iter_facts(
    path: Path, source_id: str, tally: ApplyTally
) -> Iterator[tuple[str, str, str, str, int]]:
    """``(source_id, word, attr, value, ordinal)`` rows, streamed."""
    for record in _iter_records(path, "fact", "facts", tally):
        yield (
            source_id,
            str(record["word"]),
            str(record["attr"]),
            str(record["value"]),
            int(record["ordinal"]),
        )


# --------------------------------------------------------------------------
# The two store operations
# --------------------------------------------------------------------------


def _delete_source(conn: sqlite3.Connection, source_id: str) -> tuple[int, int]:
    observations = conn.execute(
        "DELETE FROM observation WHERE source_id = ?", (source_id,)
    ).rowcount
    facts = conn.execute("DELETE FROM fact WHERE source_id = ?", (source_id,)).rowcount
    conn.execute("DELETE FROM source WHERE id = ?", (source_id,))
    return observations, facts


def apply_extract(
    conn: sqlite3.Connection, path: Path, source: LexiconSource
) -> ApplyResult:
    """Replace one source's whole contribution, in one transaction.

    The extract is read TWICE - once for observations, once for facts - rather
    than once into two lists. Two streaming passes over a file cost seconds; one
    pass into memory costs the 445 MB the largest extract weighs.
    """
    header = read_header(path)
    if header.sourceId != source.id:
        raise ValueError(
            f"{path.name} is the extract of {header.sourceId!r}, not {source.id!r}"
        )
    if header.sha256 != source.sha256:
        raise ValueError(
            f"the extract of {source.id!r} was made from bytes hashing "
            f"{header.sha256}, but the registry records {source.sha256} - "
            f"re-run EXTRACT for this source before staging it"
        )
    started = time.perf_counter()
    tally = ApplyTally()
    with transaction(conn):
        _delete_source(conn, source.id)
        conn.execute(
            _SOURCE_INSERT,
            (
                header.sourceId,
                header.sha256,
                header.bytes,
                header.role,
                header.precedence,
                header.kind,
            ),
        )
        conn.executemany(_OBSERVATION_UPSERT, iter_observations(path, source.id, tally))
        conn.executemany(_FACT_INSERT, iter_facts(path, source.id, tally))
        # A range scan of this source's own key prefix, not a table scan: the
        # observation primary key leads with `source_id`.
        row = conn.execute(
            "SELECT count(*) FROM observation WHERE source_id = ?", (source.id,)
        ).fetchone()
        tally.surfaces = int(row[0])
        epoch = bump_stage_epoch(conn)
    return ApplyResult(
        id=source.id, epoch=epoch, seconds=time.perf_counter() - started, tally=tally
    )


def remove_source(conn: sqlite3.Connection, source_id: str) -> RemoveResult:
    """Remove one source's whole contribution, in one transaction.

    The "is it staged?" check happens INSIDE the transaction, so there is no
    window between asking and deleting.
    """
    with transaction(conn):
        staged = staged_sources(conn)
        if source_id not in staged:
            raise ValueError(
                f"{source_id!r} is not staged - the store holds: "
                f"{', '.join(staged) or 'nothing'}"
            )
        observations, facts = _delete_source(conn, source_id)
        epoch = bump_stage_epoch(conn)
    return RemoveResult(
        id=source_id, epoch=epoch, observations=observations, facts=facts
    )


# --------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------


@dataclass(slots=True)
class StageRun:
    """What one STAGE invocation did."""

    applied: list[ApplyResult] = field(default_factory=list)
    removed: list[RemoveResult] = field(default_factory=list)
    seconds: float = 0.0

    def notes(self) -> list[str]:
        return [result.note() for result in self.removed] + [
            result.note() for result in self.applied
        ]


def extract_path(registry: LexiconSources, repo_root: Path, source_id: str) -> Path:
    return repo_root / registry.lexiconRoot / "cache" / "extracts" / f"{source_id}.jsonl"


def store_path(registry: LexiconSources, repo_root: Path) -> Path:
    return repo_root / registry.lexiconRoot / "cache" / "lexicon.db"


def stage(
    registry: LexiconSources,
    repo_root: Path,
    db: Path | None = None,
    only: str | None = None,
    remove: str | None = None,
) -> StageRun:
    """Stage every enabled source, or replace one, or remove one.

    The secondary indexes are dropped for the whole apply and rebuilt once at
    the end, rather than per source: rebuilding them nineteen times during a
    full load would cost more than maintaining them ever saved.
    """
    if only is not None and remove is not None:
        raise ValueError("--source replaces and --remove removes; pick one")
    path = store_path(registry, repo_root) if db is None else db
    conn = open_store(path)
    started = time.perf_counter()
    run = StageRun()
    try:
        if remove is not None:
            run.removed.append(remove_source(conn, remove))
        else:
            drop_indexes(conn)
            for source in _wanted(registry, only):
                run.applied.append(
                    apply_extract(
                        conn, extract_path(registry, repo_root, source.id), source
                    )
                )
            create_indexes(conn)
    finally:
        conn.close()
    run.seconds = time.perf_counter() - started
    return run


def _wanted(registry: LexiconSources, only: str | None) -> list[LexiconSource]:
    wanted = [
        source
        for source in registry.sources
        if source.enabled and (only is None or source.id == only)
    ]
    if only is not None and not wanted:
        known = ", ".join(source.id for source in registry.sources)
        raise ValueError(f"no enabled source {only!r} in the registry - have: {known}")
    if not wanted:
        raise ValueError("the lexicon registry has no enabled source")
    return wanted


def _repo_root() -> Path:
    # stage.py -> wordsmith -> yen_tamizh_backend -> backend -> <repo root>
    return Path(__file__).resolve().parents[3]


def main() -> None:
    root = _repo_root()
    parser = argparse.ArgumentParser(
        description="Stage the lexicon extracts into the wordsmith store."
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=root / "config" / "lexicon-sources.json",
        help="the lexicon source registry to read",
    )
    parser.add_argument("--db", type=Path, default=None, help="the store to write")
    parser.add_argument("--source", default=None, help="stage only this source id")
    parser.add_argument("--remove", default=None, help="remove this source id")
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="delete the store first, so the run is a full rebuild",
    )
    args = parser.parse_args()

    registry = load_registry(args.registry)
    path = store_path(registry, root) if args.db is None else args.db
    if args.rebuild:
        for suffix in ("", "-wal", "-shm"):
            path.with_name(path.name + suffix).unlink(missing_ok=True)

    run = stage(registry, root, path, args.source, args.remove)
    for note in run.notes():
        print(note)

    conn = open_store(path)
    try:
        print(f"store: {store_stats(conn).note()} stageEpoch={stage_epoch(conn)}")
    finally:
        conn.close()
    print(f"staged in {run.seconds:.1f}s -> {path}")


if __name__ == "__main__":
    main()
