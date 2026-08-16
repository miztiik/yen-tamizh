"""PUBLISH - the committed lexicon, its meta index and its ready-reckoner (Row 11).

The last of the four stages. It reads both zones of the store, resolves every
published word's facts into one row (``resolve.py``), and streams the result to
``datasets/lexicon/by-class/<wordClass>/<hex>.ndjson`` beside the sibling index
``datasets/lexicon/lexicon.meta.json`` and a generated ``README.md``. The policy,
the address and the two counter families are argued in
``docs/architecture/lexicon/pipeline.md``; running it is
``docs/how-to/rebuild-the-lexicon.md``.

**Retention is not publication.** The store keeps all 6.5M surfaces and every
fact any source asserted about them; the repository commits the classes a player
can actually be served. Git history is append-only, so a byte committed once is
a byte carried forever - which makes what to publish a decision rather than a
default. What keeps the thesis honest is ``counters.classified``: a per-class
census of the WHOLE population, committed beside the files, so the withheld
classes are on the record at their real size.

**The address is a pure function of the word.** ``wordClass`` is the
classifier's verdict and the first ezhuthu is the word's own opening letter, so a
refresh INSERTS a line into a file that already exists and only a changed verdict
ever moves a row. Nothing here reads a previous artifact to decide where a row
goes: a clean checkout produces the same layout as a refresh.

**The address is hex, and the hex is zero-padded in 4-digit groups.** That is
what makes ASCII filename order equal code-point order, so ``ls`` order is row
order and a file's neighbours in a listing are its neighbours in the sort. Two
things have to hold for that alignment and both are ASSERTED rather than assumed:
the key is NFC (a decomposed letter would mint a second file for a letter that
already has one) and every code point is in the Basic Multilingual Plane (a
5-digit group would break the padding). Tamil satisfies both everywhere, which is
exactly why they must be assertions - an invariant nothing checks is a comment.

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
import unicodedata
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
from yen_tamizh_backend.ezhuthu import classify, ezhuthu_roman
from yen_tamizh_backend.wordsmith.extract import load_registry, sha256_of
from yen_tamizh_backend.wordsmith.resolve import (
    ResolutionError,
    check_the_closed_vocabularies,
    first_ezhuthu,
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
README_NAME: Final = "README.md"
SUFFIX: Final = ".ndjson"

_WORD_CLASSES: Final[tuple[WordClass, ...]] = get_args(WordClass)

# The highest code point a 4-digit hex group can spell. Tamil is entirely below
# it, which is why the check is an assertion and not a branch.
_BMP_CEILING: Final = 0xFFFF


class PublishError(ValueError):
    """PUBLISH refuses to write, and the message says exactly why."""


@dataclass(frozen=True, slots=True)
class WrittenPartition:
    """One file this run wrote, measured from the bytes that landed on disk."""

    path: Path
    relative: str
    wordClass: str
    firstEzhuthu: str
    ezhuthu: str
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


def partition_hex(ezhuthu: str) -> str:
    """One whole ezhuthu as lowercase 4-digit hex per code point.

    An NFC Tamil letter is a base character plus at most one combining mark, so
    the key is four or eight digits and the padding keeps filename order equal to
    code-point order. Both preconditions are checked here, at the boundary where
    a file is about to be named after the result.
    """
    if unicodedata.normalize("NFC", ezhuthu) != ezhuthu:
        raise PublishError(
            f"the first ezhuthu {ezhuthu!r} is not NFC-normalized, so it would be "
            f"addressed differently from the same letter written normally and the "
            f"artifact would carry two files for one letter"
        )
    wide = [point for point in ezhuthu if ord(point) > _BMP_CEILING]
    if wide:
        raise PublishError(
            f"the first ezhuthu {ezhuthu!r} holds U+{ord(wide[0]):X}, above the "
            f"Basic Multilingual Plane - a five-digit group would break the "
            f"zero-padding that makes filename order equal code-point order"
        )
    if len(ezhuthu) > 2:
        raise PublishError(
            f"the first ezhuthu {ezhuthu!r} is {len(ezhuthu)} code points; a "
            f"normalized Tamil letter is one or two, so this surface carries a "
            f"mark sequence no letter has"
        )
    return "".join(f"{ord(point):04x}" for point in ezhuthu)


def partition_path(directory: Path, word_class: str, hex_key: str) -> Path:
    """One directory per class, one file per letter inside it."""
    return directory / word_class / f"{hex_key}{SUFFIX}"


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
    ezhuthu: str,
    rows: Iterable[LexiconEntry],
    ceiling: int,
) -> WrittenPartition:
    hex_key = partition_hex(ezhuthu)
    path = partition_path(directory, word_class, hex_key)
    path.parent.mkdir(parents=True, exist_ok=True)
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
        firstEzhuthu=hex_key,
        ezhuthu=ezhuthu,
        rows=count,
        bytes=size,
        sha256=digest,
    )


def _write_partitions(
    rows: Iterator[LexiconEntry], directory: Path, repo_root: Path, ceiling: int
) -> list[WrittenPartition]:
    # The stream is ordered by (wordClass, first ezhuthu, word) using the SAME
    # function that names the file, so each address is one contiguous run - which
    # is what lets the writer hold ONE open handle rather than one per file.
    directory.mkdir(parents=True, exist_ok=True)
    return [
        _write_partition(directory, repo_root, word_class, ezhuthu, group, ceiling)
        for (word_class, ezhuthu), group in groupby(
            rows, key=lambda row: (row.wordClass, first_ezhuthu(row.word))
        )
    ]


def _remove_stale(directory: Path, written: Iterable[WrittenPartition]) -> list[str]:
    """Delete files a previous publish wrote that this one no longer addresses.

    Without this the directory and the meta index disagree, and a reader that
    resolves a file from the index alone - no globbing, no probe-and-fallback -
    would never notice. Emptied class directories go too, so a withdrawn class
    leaves no trace that reads like an empty one.
    """
    keep = {cell.path.resolve() for cell in written}
    stale = sorted(
        path
        for path in directory.rglob(f"*{SUFFIX}")
        if path.resolve() not in keep
    )
    for path in stale:
        path.unlink()
    for child in sorted(directory.iterdir()):
        if child.is_dir() and not any(child.iterdir()):
            child.rmdir()
    return [path.relative_to(directory).as_posix() for path in stale]


def _census(conn: sqlite3.Connection, table: str, column: str) -> dict[str, int]:
    counted: dict[str, int] = dict.fromkeys(_WORD_CLASSES, 0)
    for name, rows in conn.execute(
        f"SELECT {column}, count(*) FROM {table} GROUP BY {column}"
    ):
        if name not in counted:
            raise PublishError(f"the store holds an unknown wordClass {name!r}")
        counted[str(name)] = int(rows)
    return counted


def _scalar(conn: sqlite3.Connection, sql: str, *values: object) -> int:
    row = conn.execute(sql, values).fetchone()
    if row is None:
        raise PublishError(f"{sql!r} returned no row")
    return int(row[0])


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


def _ezhuthu_index(written: Iterable[WrittenPartition]) -> dict[str, dict[str, str]]:
    letters = {cell.firstEzhuthu: cell.ezhuthu for cell in written}
    index: dict[str, dict[str, str]] = {}
    for hex_key in sorted(letters):
        letter = letters[hex_key]
        try:
            roman = ezhuthu_roman(letter)
        except ValueError as failure:
            raise PublishError(
                f"a published file is addressed by {hex_key} ({letter!r}), which "
                f"the ezhuthu inventory cannot spell: {failure} - a published "
                f"class has admitted a surface that does not open on a Tamil "
                f"letter"
            ) from failure
        index[hex_key] = {
            "ezhuthu": letter,
            "roman": roman,
            "kind": classify(letter),
        }
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
                    "firstEzhuthu": cell.firstEzhuthu,
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


def render_readme(document: Lexicon) -> str:
    """The human ready-reckoner: which letter is in which file, and how many.

    Generated, never hand-written, because it restates the meta index and two
    statements of the same fact drift. It carries no date: the artifact has no
    ``generatedAt`` for the reason a rebuild has to byte-compare, and a wall
    clock in a generated file would defeat that on the first re-run. Git records
    when.
    """
    index = document.ezhuthuIndex
    lines = [
        "# The published lexicon",
        "",
        "GENERATED by the PUBLISH stage - do not edit. Re-run",
        "`python -m yen_tamizh_backend.wordsmith.publish` to refresh it, and see",
        "[`../../docs/how-to/rebuild-the-lexicon.md`](../../docs/how-to/rebuild-the-lexicon.md).",
        "",
        "One file per (`wordClass`, first ezhuthu). The file name is the letter's",
        "Unicode code points as lowercase 4-digit hex, so a directory listing is in",
        "the same order as the rows inside it. The letter itself and its ASCII",
        f"spelling live in [`{META_NAME}`]({META_NAME}) and in the tables below -",
        "as data a correction can edit, never as a path a correction would rename.",
        "",
        "## What is published",
        "",
        "| wordClass | classified | published | files |",
        "| --- | ---: | ---: | ---: |",
    ]
    files_by_class: dict[str, int] = {}
    for cell in document.partitions:
        files_by_class[cell.wordClass] = files_by_class.get(cell.wordClass, 0) + 1
    for name in sorted(document.counters.classified.byClass):
        classified = document.counters.classified.byClass[name]
        published = document.counters.published.byClass[name]
        state = f"{published:,}" if published else "withheld"
        lines.append(
            f"| `{name}` | {classified:,} | {state} | {files_by_class.get(name, 0)} |"
        )
    lines.extend(
        [
            f"| **total** | **{document.counters.classified.rows:,}** | "
            f"**{document.counters.published.rows:,}** | "
            f"**{len(document.partitions)}** |",
            "",
            "A withheld class is still counted here at its real size: the store keeps",
            "every surface, and the repository commits the ones a player can be served.",
        ]
    )
    for word_class in sorted(files_by_class):
        lines.extend(
            [
                "",
                f"## {word_class}",
                "",
                "| file | ezhuthu | roman | kind | words |",
                "| --- | --- | --- | --- | ---: |",
            ]
        )
        for cell in document.partitions:
            if cell.wordClass != word_class:
                continue
            letter = index[cell.firstEzhuthu]
            path = f"{BY_CLASS}/{word_class}/{cell.firstEzhuthu}{SUFFIX}"
            lines.append(
                f"| [`{cell.firstEzhuthu}{SUFFIX}`]({path}) | {letter.ezhuthu} | "
                f"{letter.roman} | {letter.kind} | {cell.rows:,} |"
            )
    lines.extend(
        [
            "",
            "## See also",
            "",
            f"- [`{META_NAME}`]({META_NAME}) - the index every consumer resolves a "
            "file through.",
            "- [`../../docs/concepts/lexicon.md`](../../docs/concepts/lexicon.md) - "
            "what a `wordClass` is and what attestation means.",
            "- [`../../docs/architecture/lexicon/pipeline.md`]"
            "(../../docs/architecture/lexicon/pipeline.md) - the four stages and "
            "why the layout is this one.",
            "",
        ]
    )
    return "\n".join(lines)


def _write_text(path: Path, body: str) -> None:
    partial = path.with_name(f"{path.name}.partial")
    partial.write_text(body, encoding="utf-8", newline="\n")
    partial.replace(path)


def publish(
    registry: LexiconSources, repo_root: Path, db: Path | None = None
) -> PublishRun:
    """Write the committed lexicon, its meta index and its ready-reckoner."""
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
    root.mkdir(parents=True, exist_ok=True)
    _write_text(root / META_NAME, render_meta(document))
    _write_text(root / README_NAME, render_readme(document))
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
