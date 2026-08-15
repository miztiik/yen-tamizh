"""ENRICH - stage 3 of the wordsmith pipeline (Row 7).

Reads the STAGED zone and writes the DERIVED one: one ``signal`` row per staged
surface, one column per word-hood signal. The stage is explained in
``docs/architecture/lexicon/pipeline.md``; what the signals mean is
``docs/architecture/lexicon/word-hood.md``.

Three properties hold this stage together, and Row 6 built the store so they
could:

1. **The derived zone is dropped and recomputed WHOLE.** Four of the eight
   signals are whole-corpus functions, so a zone merged from deltas would carry
   values computed over a pre-delta fact set. Recomputing is cheap and provable;
   incremental signal update would be neither.
2. **One pass over the population.** The population is the union of every
   observed surface and every worded fact - 6.25M rows over the real sources -
   and every signal contributes a SQL expression to ONE streamed
   ``INSERT ... SELECT`` rather than its own update pass over the whole table.
3. **``derived_epoch`` is stamped with the ``stage_epoch`` the run read.**
   PUBLISH refuses to run when the two disagree, so a published artifact can
   never carry signals from a store that has moved on underneath them.

Row 7 fills five of the eight columns; ``ngram``, ``neighbour`` and ``zipf``
stay NULL until Row 8 appends its signals to ``SIGNALS``. That is deliberate and
it is what a NULL means here: not measured yet, as against a measured zero.
"""

from __future__ import annotations

import argparse
import sqlite3
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from yen_tamizh_backend.contracts.lexicon import SignalName
from yen_tamizh_backend.contracts.wordhood import Wordhood
from yen_tamizh_backend.wordsmith.extract import load_registry
from yen_tamizh_backend.wordsmith.signals_exact import (
    EXACT_SIGNALS,
    Signal,
    SignalContext,
    configured_sources,
)
from yen_tamizh_backend.wordsmith.stage import store_path
from yen_tamizh_backend.wordsmith.store import (
    DERIVED_TABLES,
    SIGNAL_COLUMNS,
    derived_epoch,
    open_store,
    quoted,
    set_derived_epoch,
    stage_epoch,
    staged_sources,
    transaction,
)

# Row 8 appends its three inexact signals here. The order is the order the
# columns are written in, and nothing else depends on it.
SIGNALS: tuple[Signal, ...] = EXACT_SIGNALS

# Every staged surface: what was OBSERVED, plus every word a source asserted a
# fact about. The union rather than the observation table alone, because a
# source that only ever asserts facts is a source whose words would otherwise
# never reach the derived zone at all.
POPULATION_SQL = (
    "SELECT surface AS word FROM observation UNION SELECT word FROM fact"
)


@dataclass(slots=True)
class SignalResult:
    """One signal's preparation, timed. The write itself is shared."""

    name: SignalName
    seconds: float

    def note(self) -> str:
        return f"{self.name}: prepared in {self.seconds:.1f}s"


@dataclass(slots=True)
class EnrichRun:
    """What one ENRICH invocation did."""

    signals: list[SignalResult] = field(default_factory=list)
    rows: int = 0
    stageEpoch: int = 0
    derivedEpoch: int = 0
    writeSeconds: float = 0.0
    seconds: float = 0.0

    def notes(self) -> list[str]:
        return [result.note() for result in self.signals]


def load_config(path: Path) -> Wordhood:
    """Load and validate ``config/wordhood.json``."""
    return Wordhood.model_validate_json(path.read_text(encoding="utf-8"))


def selected(only: str | None) -> tuple[Signal, ...]:
    """The signals this run computes, or a failure naming the ones there are."""
    if only is None:
        return SIGNALS
    wanted = tuple(signal for signal in SIGNALS if signal.name == only)
    if not wanted:
        known = ", ".join(signal.name for signal in SIGNALS)
        raise ValueError(f"no signal {only!r} - have: {known}")
    return wanted


def check_configured_sources(conn: sqlite3.Connection, config: Wordhood) -> None:
    """Refuse to run when a configured source id is not in the store.

    Fail fast at the boundary. A misspelled id would otherwise produce a column
    of zeros, which reads exactly like a signal that honestly found nothing.
    """
    staged = set(staged_sources(conn))
    missing = [name for name in configured_sources(config) if name not in staged]
    if missing:
        raise ValueError(
            f"config/wordhood.json names {', '.join(missing)}, which "
            f"{'is' if len(missing) == 1 else 'are'} not staged - the store "
            f"holds: {', '.join(sorted(staged)) or 'nothing'}"
        )


def _prepare(ctx: SignalContext, signals: Iterable[Signal]) -> list[SignalResult]:
    results: list[SignalResult] = []
    for signal in signals:
        started = time.perf_counter()
        signal.prepare(ctx)
        results.append(
            SignalResult(name=signal.name, seconds=time.perf_counter() - started)
        )
    return results


def _rebuild(conn: sqlite3.Connection, signals: tuple[Signal, ...]) -> int:
    """Drop the derived zone and recompute it whole, in one transaction."""
    columns = ", ".join(quoted(signal.name) for signal in signals)
    expressions = ", ".join(signal.expression.format(word="w.word") for signal in signals)
    with transaction(conn):
        for table in DERIVED_TABLES:
            conn.execute(f"DELETE FROM {quoted(table)}")
        cursor = conn.execute(
            f"INSERT INTO signal (word, {columns}) "
            f"SELECT w.word, {expressions} FROM ({POPULATION_SQL}) AS w"
        )
        rows = cursor.rowcount
        set_derived_epoch(conn, stage_epoch(conn))
    return rows


def _recompute(conn: sqlite3.Connection, signal: Signal) -> int:
    """Recompute ONE column over the population the zone already holds.

    Deliberately does not touch ``derived_epoch``. The column is a pure function
    of the staged zone, so recomputing it cannot make a current zone stale, and
    it cannot make a stale one current either - the stamp is right wherever it
    already stood.
    """
    row = conn.execute("SELECT count(*) FROM signal").fetchone()
    if row is None or int(row[0]) == 0:
        raise ValueError(
            "the derived zone is empty - run ENRICH with no --signal first, so "
            "there is a population to recompute a column over"
        )
    column = quoted(signal.name)
    expression = signal.expression.format(word='"signal"."word"')
    with transaction(conn):
        cursor = conn.execute(f"UPDATE signal SET {column} = {expression}")
        return cursor.rowcount


def enrich(config: Wordhood, db: Path, only: str | None = None) -> EnrichRun:
    """Recompute the derived zone, or one signal's column within it."""
    signals = selected(only)
    conn = open_store(db)
    started = time.perf_counter()
    run = EnrichRun()
    try:
        check_configured_sources(conn, config)
        run.signals = _prepare(SignalContext(conn=conn, config=config), signals)
        write_started = time.perf_counter()
        if only is None:
            run.rows = _rebuild(conn, signals)
        else:
            run.rows = _recompute(conn, signals[0])
        run.writeSeconds = time.perf_counter() - write_started
        run.stageEpoch = stage_epoch(conn)
        run.derivedEpoch = derived_epoch(conn)
    finally:
        conn.close()
    run.seconds = time.perf_counter() - started
    return run


def distribution(conn: sqlite3.Connection) -> dict[str, tuple[int, int]]:
    """Per column: how many rows carry a value, and how many carry a positive.

    The measurement the run is reported against. A signal whose positives are
    zero has either found nothing or been wired to nothing, and only the first
    of those is news.
    """
    measured: dict[str, tuple[int, int]] = {}
    for column in SIGNAL_COLUMNS:
        name = quoted(column)
        row = conn.execute(
            f"SELECT count({name}), count(CASE WHEN {name} > 0 THEN 1 END) FROM signal"
        ).fetchone()
        if row is None:
            raise ValueError(f"counting {column} returned no row")
        measured[column] = (int(row[0]), int(row[1]))
    return measured


def _repo_root() -> Path:
    # enrich.py -> wordsmith -> yen_tamizh_backend -> backend -> <repo root>
    return Path(__file__).resolve().parents[3]


def main() -> None:
    root = _repo_root()
    parser = argparse.ArgumentParser(
        description="Compute the word-hood signals into the store's derived zone."
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=root / "config" / "lexicon-sources.json",
        help="the lexicon source registry, which says where the store lives",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "config" / "wordhood.json",
        help="the word-hood knobs to read",
    )
    parser.add_argument("--db", type=Path, default=None, help="the store to write")
    parser.add_argument(
        "--signal",
        default=None,
        help="recompute only this signal's column, over the existing population",
    )
    args = parser.parse_args()

    registry = load_registry(args.registry)
    path = store_path(registry, root) if args.db is None else args.db
    run = enrich(load_config(args.config), path, args.signal)
    for note in run.notes():
        print(note)
    print(
        f"signal rows={run.rows} written in {run.writeSeconds:.1f}s "
        f"stageEpoch={run.stageEpoch} derivedEpoch={run.derivedEpoch}"
    )

    conn = open_store(path)
    try:
        for column, (measured, positive) in distribution(conn).items():
            print(f"  {column}: measured={measured} positive={positive}")
    finally:
        conn.close()
    print(f"enriched in {run.seconds:.1f}s -> {path}")


if __name__ == "__main__":
    main()
