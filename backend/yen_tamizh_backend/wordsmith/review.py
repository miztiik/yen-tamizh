"""REVIEW - the intermediate artifacts a human reads between runs (Row 9b).

ENRICH's verdicts live in a 2 GB gitignored SQLite file. That is the right home
for them and a useless one for a person: nobody opens a store to find out why a
word was refused, or how long the queue of work an enrichment pass still has in
front of it is. This stage writes that state out as three files under
``<lexiconRoot>/cache/review/``, in the same gitignored cache the extracts
already live in, one JSON object per line so a shell, an editor and a diff all
read them.

It is DERIVED and it is a REPORT. It writes nothing back to the store, so a
review dump can never change a verdict, and it is a pure function of the derived
zone - re-running it over an unchanged store rewrites the same bytes.

Four questions, four files:

- ``unclassified.ndjson`` - the surfaces the cascade could reach no verdict
  about, with all eight signals beside each, so the residue can be sorted and
  inspected rather than counted.
- ``not-a-word.ndjson`` - the surfaces the precondition refused, with WHICH
  clause refused each. The reason is recomputed by the classifier's own
  function, so a reviewed reason cannot disagree with a published verdict.
- ``enrichment-queue.ndjson`` - surfaces still unclassified that a tier-1
  MEANING source nevertheless describes. Over a CURRENT derived zone this file
  is EMPTY, and its emptiness is the point: a tier-1 source that describes a
  surface also attests it, an attested surface has an entry, and an entry always
  reaches a verdict. A row here means a source described something it did not
  list, or that the derived zone is stale - which is exactly how the 13,500-row
  version of this set was measured before ENRICH was re-run.
- ``headwords-without-a-meaning.ndjson`` - the queue that IS the work: surfaces
  the classifier ruled servable that carry no Tamil definition. They pass the
  word-hood gate and would still fail a meaning gate, so this is the set an
  authoring pass works through, ordered by the store's own order and carrying
  the evidence it would work FROM.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from yen_tamizh_backend.contracts.lexicon_sources import LexiconSources
from yen_tamizh_backend.contracts.wordhood import Wordhood
from yen_tamizh_backend.ezhuthu import analyse
from yen_tamizh_backend.wordsmith.enrich import load_config
from yen_tamizh_backend.wordsmith.extract import load_registry, render
from yen_tamizh_backend.wordsmith.stage import store_path
from yen_tamizh_backend.wordsmith.store import SIGNAL_COLUMNS, open_store, quoted
from yen_tamizh_backend.wordsmith.wordhood import not_a_word_reason, tier_one_sources

REVIEW_DIRECTORY: Final = "review"

# The attributes that make a surface WORTH enriching: somebody wrote down what
# it means or what it is equivalent to. A part of speech alone does not qualify
# - it narrows nothing for a player and cannot become a hint.
MEANING_ATTRS: Final[tuple[str, ...]] = ("definitionTa", "synonym", "translation")

# What each file is called and what it answers. Named here so the CLI's summary
# and the files it wrote cannot drift apart.
UNCLASSIFIED_FILE: Final = "unclassified.ndjson"
NOT_A_WORD_FILE: Final = "not-a-word.ndjson"
QUEUE_FILE: Final = "enrichment-queue.ndjson"
MEANINGLESS_FILE: Final = "headwords-without-a-meaning.ndjson"

# The class a meaning is owed to. Row 12 serves this one, so a row in it that
# carries no Tamil definition is a word the game can select and cannot explain.
SERVED_CLASS: Final = "headword"


@dataclass(slots=True)
class ReviewRun:
    """What one review pass wrote, in the order it wrote it."""

    root: Path
    files: list[tuple[str, int]] = field(default_factory=list)

    def note(self) -> str:
        written = " ".join(f"{name}={rows}" for name, rows in self.files)
        return f"{self.root.as_posix()}: {written}"


def _write(path: Path, rows: Iterator[dict[str, Any]]) -> int:
    """Stream one report to disk, counting what it held.

    Written to a ``.partial`` and renamed, on the same rule EXTRACT follows: an
    interrupted run must not leave a half file that reads like a short queue.
    """
    partial = path.with_suffix(path.suffix + ".partial")
    written = 0
    with partial.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(render(row))
            written += 1
    partial.replace(path)
    return written


def _signal_row(record: tuple[Any, ...]) -> dict[str, Any]:
    word = str(record[0])
    row: dict[str, Any] = {"word": word, "length": len(analyse(word).ezhuthu)}
    for column, value in zip(SIGNAL_COLUMNS, record[1:], strict=True):
        row[column] = value
    return row


def _signal_select(where: str) -> str:
    columns = ", ".join(f"s.{quoted(name)}" for name in SIGNAL_COLUMNS)
    return (
        f"SELECT s.word, {columns} FROM signal AS s "
        f"JOIN classification AS c ON c.word = s.word "
        f"WHERE c.wordClass = ? {where} ORDER BY s.word"
    )


def unclassified(conn: sqlite3.Connection) -> Iterator[dict[str, Any]]:
    """Every surface with no verdict, carrying all eight signals."""
    for record in conn.execute(_signal_select(""), ("unclassified",)):
        yield _signal_row(record)


def not_a_word(
    conn: sqlite3.Connection, config: Wordhood
) -> Iterator[dict[str, Any]]:
    """Every refused surface, with the clause that refused it.

    ``sourceDenied`` is the reason no threshold produces: the string itself
    breaks none of the three shape rules, and a lexicographic source said in so
    many words that the unit is a character rather than a word.
    """
    for record in conn.execute(
        "SELECT word FROM classification WHERE wordClass = ? ORDER BY word",
        ("notAWord",),
    ):
        word = str(record[0])
        yield {
            "word": word,
            "reason": not_a_word_reason(analyse(word), config) or "sourceDenied",
        }


def enrichment_queue(
    conn: sqlite3.Connection, registry: LexiconSources
) -> Iterator[dict[str, Any]]:
    """Unclassified surfaces a tier-1 meaning source already describes.

    The join is against the TIER-1 sources rather than against every source,
    because the question is not "did anybody ever mention this string" - the
    frequency tables mention everything - but "has a lexicographer already said
    what it means". What comes back is what a later enrichment pass would work
    through, in the store's own order, with the meanings it would work FROM.
    """
    sources = tier_one_sources(registry)
    source_slots = ",".join("?" for _ in sources)
    attr_slots = ",".join("?" for _ in MEANING_ATTRS)
    statement = (
        f"SELECT f.word, f.source_id, f.attr, f.value FROM fact AS f "
        f"JOIN classification AS c ON c.word = f.word "
        f"WHERE c.wordClass = 'unclassified' "
        f"  AND f.source_id IN ({source_slots}) "
        f"  AND f.attr IN ({attr_slots}) "
        f"ORDER BY f.word, f.attr, f.source_id, f.ordinal"
    )
    current: str | None = None
    row: dict[str, Any] = {}

    def finished(record: dict[str, Any]) -> dict[str, Any]:
        record["sources"] = sorted(record["sources"])
        return record

    for word, source_id, attr, value in conn.execute(
        statement, (*sources, *MEANING_ATTRS)
    ):
        if word != current:
            if current is not None:
                yield finished(row)
            current = str(word)
            row = {"word": current, "sources": []}
        if source_id not in row["sources"]:
            row["sources"].append(str(source_id))
        row.setdefault(str(attr), []).append(str(value))
    if current is not None:
        yield finished(row)


def headwords_without_a_meaning(conn: sqlite3.Connection) -> Iterator[dict[str, Any]]:
    """Servable surfaces that carry no Tamil definition, with what they DO carry.

    The classifier ruled these words. A meaning gate would then refuse them, so
    every row here is a word the game can select and cannot explain - which is
    the actual size of the authoring work, and a different question from what
    the classifier could not place.

    ``evidence`` is what an authoring pass would work FROM: an English
    translation, a same-language synonym, a part of speech, or the terms the
    bilingual dictionary filed alongside it. A row with an empty ``evidence``
    has nothing to author from and is the bottom tier Row 10 declines.
    """
    statement = (
        "SELECT c.word, f.attr, f.value FROM classification AS c "
        "LEFT JOIN fact AS f ON f.word = c.word "
        "  AND f.attr IN ('translation', 'synonym', 'pos', 'glossPeer') "
        "WHERE c.wordClass = ? AND NOT EXISTS ("
        "  SELECT 1 FROM fact AS m WHERE m.word = c.word AND m.attr = 'definitionTa'"
        ") ORDER BY c.word, f.attr, f.value"
    )
    current: str | None = None
    row: dict[str, Any] = {}
    for word, attr, value in conn.execute(statement, (SERVED_CLASS,)):
        if word != current:
            if current is not None:
                yield row
            current = str(word)
            row = {"word": current, "length": len(analyse(current).ezhuthu)}
        if attr is None:
            continue
        values = row.setdefault(str(attr), [])
        if value not in values:
            values.append(str(value))
    if current is not None:
        yield row


def review(registry: LexiconSources, config: Wordhood, db: Path) -> ReviewRun:
    """Write all four reports beside the store they describe."""
    root = db.parent / REVIEW_DIRECTORY
    root.mkdir(parents=True, exist_ok=True)
    run = ReviewRun(root=root)
    conn = open_store(db)
    try:
        run.files.append(
            (UNCLASSIFIED_FILE, _write(root / UNCLASSIFIED_FILE, unclassified(conn)))
        )
        run.files.append(
            (NOT_A_WORD_FILE, _write(root / NOT_A_WORD_FILE, not_a_word(conn, config)))
        )
        run.files.append(
            (QUEUE_FILE, _write(root / QUEUE_FILE, enrichment_queue(conn, registry)))
        )
        run.files.append(
            (
                MEANINGLESS_FILE,
                _write(root / MEANINGLESS_FILE, headwords_without_a_meaning(conn)),
            )
        )
    finally:
        conn.close()
    return run


def _repo_root() -> Path:
    # review.py -> wordsmith -> yen_tamizh_backend -> backend -> <repo root>
    return Path(__file__).resolve().parents[3]


def main() -> None:
    root = _repo_root()
    parser = argparse.ArgumentParser(
        description="Write the reviewable intermediate files beside the store."
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
        help="the word-hood knobs the refusal reasons are read from",
    )
    parser.add_argument("--db", type=Path, default=None, help="the store to read")
    args = parser.parse_args()

    registry = load_registry(args.registry)
    path = store_path(registry, root) if args.db is None else args.db
    run = review(registry, load_config(args.config), path)
    for name, rows in run.files:
        print(f"{(run.root / name).as_posix()}: {rows} rows")


if __name__ == "__main__":
    main()


__all__ = [
    "MEANINGLESS_FILE",
    "MEANING_ATTRS",
    "NOT_A_WORD_FILE",
    "QUEUE_FILE",
    "REVIEW_DIRECTORY",
    "SERVED_CLASS",
    "ReviewRun",
    "UNCLASSIFIED_FILE",
    "enrichment_queue",
    "headwords_without_a_meaning",
    "not_a_word",
    "review",
    "unclassified",
]
