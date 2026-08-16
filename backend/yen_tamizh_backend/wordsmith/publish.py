"""PUBLISH - the committed lexicon and its meta index (Row 11).

The last of the four stages. It reads both zones of the store, resolves every
published word's facts into one row (``resolve.py``), and streams the result to
``datasets/lexicon/by-class/<wordClass>-<hex>.ndjson`` beside the sibling index
``datasets/lexicon/lexicon.meta.json``. The policy, the address and the two
counter families are argued in ``docs/architecture/lexicon/pipeline.md``;
running it is ``docs/how-to/rebuild-the-lexicon.md``.

**Retention is not publication.** The store keeps all 6.5M surfaces and every
fact any source asserted about them; the repository commits the classes a player
can actually be served. Git history is append-only, so a byte committed once is
a byte carried forever - which makes what to publish a decision rather than a
default. What keeps the thesis honest is ``counters.classified``: a per-class
census of the WHOLE population, committed beside the files, so the withheld
classes are on the record at their real size.

**The address is a pure function of the word.** ``wordClass`` is the
classifier's verdict and the base first ezhuthu is the word's own first code
point, so a refresh INSERTS a line into a file that already exists and only a
changed verdict ever moves a row. Nothing here reads a previous artifact to
decide where a row goes: a clean checkout produces the same layout as a refresh.

**Everything streams.** One ``json.dumps`` per line, written straight from a
cursor to a handle opened with an EXPLICIT ``newline="\\n"`` - the operator runs
Windows, where Python's default text mode would turn every line ending into
CRLF and break the byte-identity Oracle on the very machine that performs the
real publish. Peak memory is one row.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from itertools import groupby
from pathlib import Path
from typing import Any, Final, TextIO, get_args

from yen_tamizh_backend.contracts.lexicon import (
    LEXICON_CHANGELOG,
    LEXICON_VERSION,
    PARTITION_KEYS,
    Lexicon,
    LexiconEntry,
    WordClass,
)
from yen_tamizh_backend.contracts.lexicon_sources import LexiconSources
from yen_tamizh_backend.ezhuthu import BASE_ROMAN, classify
from yen_tamizh_backend.wordsmith.extract import load_registry, sha256_of
from yen_tamizh_backend.wordsmith.resolve import (
    ResolutionError,
    check_the_closed_vocabularies,
    prepare,
    stream,
)
from yen_tamizh_backend.wordsmith.stage import store_path
from yen_tamizh_backend.wordsmith.store import connect, derived_is_current

# The one format this stage writes. A registry declaring another is a claim
# nothing honours, so it fails rather than being quietly ignored.
NDJSON: Final = "ndjson"

BY_CLASS: Final = "by-class"
META_NAME: Final = "lexicon.meta.json"
SUFFIX: Final = ".ndjson"

_WORD_CLASSES: Final[tuple[WordClass, ...]] = get_args(WordClass)


class PublishError(ValueError):
    """PUBLISH refuses to write, and the message says exactly why."""


@dataclass(frozen=True, slots=True)
class WrittenPartition:
    """One file this run wrote, measured from the bytes that landed on disk."""

    path: Path
    relative: str
    wordClass: str
    baseFirstEzhuthu: str
    rows: int
    bytes: int
    sha256: str


@dataclass
class PublishRun:
    """What one PUBLISH invocation did, for the operator's report."""

    partitions: list[WrittenPartition] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    classified: dict[str, int] = field(default_factory=dict)
    published: dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0

    @property
    def rows(self) -> int:
        return sum(cell.rows for cell in self.partitions)

    @property
    def bytes(self) -> int:
        return sum(cell.bytes for cell in self.partitions)

    def notes(self) -> list[str]:
        largest = max(self.partitions, key=lambda cell: cell.bytes, default=None)
        lines = [
            f"files={len(self.partitions)} rows={self.rows} bytes={self.bytes}",
            f"classified={sum(self.classified.values())} published={self.rows}",
        ]
        if largest is not None:
            lines.append(f"largest={largest.relative} bytes={largest.bytes}")
        if self.removed:
            lines.append(f"removed stale: {', '.join(self.removed)}")
        return lines


def lexicon_root(registry: LexiconSources, repo_root: Path) -> Path:
    return repo_root / registry.lexiconRoot


def partition_name(word_class: str, base_hex: str) -> str:
    return f"{word_class}-{base_hex}{SUFFIX}"


def base_hex(word: str) -> str:
    """The lowercase 4-digit hex of the word's base first ezhuthu.

    ``segment(word)[0][0]`` is always ``word[0]``: a cluster starts at the
    character it starts at, and every combining mark attaches to what precedes
    it. So the address needs no segmentation pass - which also means the sort by
    ``word`` ASC and the partition cut are the same order, and concatenating a
    class's files in hex order reproduces the sorted class exactly.
    """
    return f"{ord(word[0]):04x}"


def render(row: LexiconEntry) -> str:
    """One published line. Sorted keys, no ASCII escaping, no trailing space."""
    return (
        json.dumps(
            row.model_dump(exclude_none=True), ensure_ascii=False, sort_keys=True
        )
        + "\n"
    )


def write_rows(handle: TextIO, rows: Iterable[LexiconEntry]) -> int:
    """Stream rows into an open handle. Holds one row, whatever the count."""
    written = 0
    for row in rows:
        handle.write(render(row))
        written += 1
    return written


def _write_partition(
    directory: Path,
    repo_root: Path,
    word_class: str,
    hex_key: str,
    rows: Iterable[LexiconEntry],
    ceiling: int,
) -> WrittenPartition:
    path = directory / partition_name(word_class, hex_key)
    partial = path.with_name(f"{path.name}.partial")
    # newline="\n" and encoding="utf-8" are NAMED, never defaulted: the default
    # text mode on Windows writes CRLF, which would make the same store publish
    # different bytes on the operator's machine than in CI.
    with partial.open("w", encoding="utf-8", newline="\n") as handle:
        count = write_rows(handle, rows)
    partial.replace(path)
    # Hashed by reading the file back, so the digest is a statement about the
    # bytes on disk rather than about what this process meant to write.
    digest, size = sha256_of(path)
    if size > ceiling:
        raise PublishError(
            f"{path.name} is {size} bytes, over the configured "
            f"maxPartitionBytes of {ceiling} - one file has outgrown what the "
            f"address can hold, so the layout needs a decision rather than a "
            f"larger number"
        )
    return WrittenPartition(
        path=path,
        relative=path.relative_to(repo_root).as_posix(),
        wordClass=word_class,
        baseFirstEzhuthu=hex_key,
        rows=count,
        bytes=size,
        sha256=digest,
    )


def _write_partitions(
    rows: Iterator[LexiconEntry], directory: Path, repo_root: Path, ceiling: int
) -> list[WrittenPartition]:
    # The stream arrives ordered by (wordClass, word) and the hex is a function
    # of word[0], so each address is one contiguous run - which is what lets the
    # writer hold ONE open handle rather than one per file.
    directory.mkdir(parents=True, exist_ok=True)
    written: list[WrittenPartition] = []
    for (word_class, hex_key), group in groupby(
        rows, key=lambda row: (row.wordClass, base_hex(row.word))
    ):
        written.append(
            _write_partition(
                directory, repo_root, word_class, hex_key, group, ceiling
            )
        )
    return written


def _remove_stale(directory: Path, written: Iterable[WrittenPartition]) -> list[str]:
    """Delete files a previous publish wrote that this one no longer addresses.

    Without this the directory and the meta index disagree, and a reader that
    resolves a file from the index alone - no globbing, no probe-and-fallback -
    would never notice.
    """
    keep = {cell.path.name for cell in written}
    stale = sorted(
        path.name for path in directory.glob(f"*{SUFFIX}") if path.name not in keep
    )
    for name in stale:
        (directory / name).unlink()
    return stale


def _census(conn: sqlite3.Connection, table: str, column: str) -> dict[str, int]:
    counted: dict[str, int] = dict.fromkeys(_WORD_CLASSES, 0)
    for name, rows in conn.execute(
        f"SELECT {column}, count(*) FROM {table} GROUP BY {column}"
    ):
        if name not in counted:
            raise PublishError(f"the store holds an unknown wordClass {name!r}")
        counted[str(name)] = int(rows)
    return counted


def _provenance(
    conn: sqlite3.Connection, registry: LexiconSources
) -> list[dict[str, Any]]:
    declared = {source.id: source for source in registry.sources}
    rows: list[dict[str, Any]] = []
    for source_id, digest, size in conn.execute(
        "SELECT id, sha256, bytes FROM source ORDER BY id"
    ):
        source = declared[str(source_id)]
        if source.sha256 != digest or source.bytes != size:
            raise PublishError(
                f"source {source_id!r} was staged from bytes the registry no "
                f"longer declares ({digest} of {size} B staged, "
                f"{source.sha256} of {source.bytes} B registered) - re-extract "
                f"and re-stage it before publishing"
            )
        rows.append(
            {
                "id": source.id,
                "name": source.name,
                "origin": source.origin,
                "path": source.path,
                "bytes": int(size),
                "sha256": str(digest),
                "observations": _scalar(
                    conn,
                    "SELECT count(*) FROM observation WHERE source_id = ?",
                    source.id,
                ),
                "facts": _scalar(
                    conn, "SELECT count(*) FROM fact WHERE source_id = ?", source.id
                ),
            }
        )
    return rows


def _scalar(conn: sqlite3.Connection, sql: str, *values: object) -> int:
    row = conn.execute(sql, values).fetchone()
    if row is None:
        raise PublishError(f"{sql!r} returned no row")
    return int(row[0])


def _ezhuthu_index(written: Iterable[WrittenPartition]) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for cell in sorted({cell.baseFirstEzhuthu for cell in written}):
        letter = chr(int(cell, 16))
        roman = BASE_ROMAN.get(letter)
        if roman is None:
            raise PublishError(
                f"a published file is addressed by U+{cell.upper()} ({letter!r}), "
                f"which is not a base character the ezhuthu inventory knows - a "
                f"published class has admitted a surface that is not Tamil"
            )
        index[cell] = {"ezhuthu": letter, "roman": roman, "kind": classify(letter)}
    return index


def _meta_document(
    conn: sqlite3.Connection,
    registry: LexiconSources,
    written: list[WrittenPartition],
    classified: dict[str, int],
    published: dict[str, int],
) -> Lexicon:
    return Lexicon.model_validate(
        {
            "version": LEXICON_VERSION,
            "changelog": [entry.model_dump() for entry in LEXICON_CHANGELOG],
            "partitionKeys": list(PARTITION_KEYS),
            "provenance": _provenance(conn, registry),
            "counters": {
                "classified": {
                    "rows": sum(classified.values()),
                    "byClass": classified,
                },
                "published": {"rows": sum(published.values()), "byClass": published},
            },
            "partitions": [
                {
                    "path": cell.relative,
                    "wordClass": cell.wordClass,
                    "baseFirstEzhuthu": cell.baseFirstEzhuthu,
                    "rows": cell.rows,
                    "bytes": cell.bytes,
                    "sha256": cell.sha256,
                }
                for cell in written
            ],
            "ezhuthuIndex": _ezhuthu_index(written),
        }
    )


def render_meta(document: Lexicon) -> str:
    """The meta index as committed: indented, Tamil unescaped, LF, one trailing.

    Field order rather than sorted keys, because the model's order is the order
    a reader wants - what this is, where it came from, what it counts, where it
    lives - and it is just as deterministic.
    """
    payload = document.model_dump(exclude_none=True)
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def publish(
    registry: LexiconSources, repo_root: Path, db: Path | None = None
) -> PublishRun:
    """Write the committed lexicon and its meta index from the store."""
    unsupported = [name for name in registry.outputs if name != NDJSON]
    if unsupported:
        raise PublishError(
            f"the registry declares output format(s) {', '.join(unsupported)}, "
            f"which this stage does not write - a declared output nothing "
            f"produces is a claim rather than a knob"
        )
    path = store_path(registry, repo_root) if db is None else db
    if not path.exists():
        raise PublishError(f"there is no store at {path.as_posix()} to publish from")
    root = lexicon_root(registry, repo_root)
    conn = connect(path)
    started = time.perf_counter()
    run = PublishRun()
    try:
        if not derived_is_current(conn):
            raise PublishError(
                "the derived zone is behind the staged one, so the signals and "
                "verdicts were computed over a store that has since moved - run "
                "ENRICH before publishing"
            )
        check_the_closed_vocabularies(conn, registry)
        prepare(conn, registry)
        run.classified = _census(conn, "classification", "wordClass")
        run.partitions = _write_partitions(
            stream(conn), root / BY_CLASS, repo_root, registry.maxPartitionBytes
        )
        run.removed = _remove_stale(root / BY_CLASS, run.partitions)
        run.published = dict.fromkeys(_WORD_CLASSES, 0)
        for cell in run.partitions:
            run.published[cell.wordClass] += cell.rows
        document = _meta_document(
            conn, registry, run.partitions, run.classified, run.published
        )
    finally:
        conn.close()
    meta = root / META_NAME
    meta.parent.mkdir(parents=True, exist_ok=True)
    partial = meta.with_name(f"{META_NAME}.partial")
    partial.write_text(render_meta(document), encoding="utf-8", newline="\n")
    partial.replace(meta)
    run.seconds = time.perf_counter() - started
    return run


def _repo_root() -> Path:
    # publish.py -> wordsmith -> yen_tamizh_backend -> backend -> <repo root>
    return Path(__file__).resolve().parents[3]


def main() -> None:
    root = _repo_root()
    parser = argparse.ArgumentParser(
        description="Write the committed lexicon and its meta index."
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=root / "config" / "lexicon-sources.json",
        help="the lexicon source registry, which says what to publish and where",
    )
    parser.add_argument("--db", type=Path, default=None, help="the store to read")
    parser.add_argument(
        "--root", type=Path, default=root, help="the repository root to write under"
    )
    args = parser.parse_args()

    registry = load_registry(args.registry)
    try:
        run = publish(registry, args.root, args.db)
    except (PublishError, ResolutionError) as failure:
        raise SystemExit(str(failure)) from failure
    for note in run.notes():
        print(note)
    for name in _WORD_CLASSES:
        published = run.published.get(name, 0)
        classified = run.classified.get(name, 0)
        state = "published" if published else "withheld"
        print(f"  {name}: classified={classified} {state}={published}")
    print(f"published in {run.seconds:.1f}s")


if __name__ == "__main__":  # pragma: no cover - operator entry point
    main()
