"""Streaming Tamil corpus ingest -> the ranked master wordlist (Row 8).

This is the CORPUS layer, and only the corpus layer. It reads the sources named
in ``config/corpus-sources.json``, keeps the real Tamil words, merges their
frequencies, ranks and bands them, and writes ONE artifact:
``datasets/wordlists/master/words_ranked.json``. It generates no puzzles, writes
nothing into ``frontend/public/``, and knows nothing about any Game - the daily
puzzle engine (Row 13) is a separate process reading the per-Game sets derived
from this file (Row 9). A corpus refresh must never rebuild a Game.

Adding a source is a DATA change (see docs/how-to/add-a-corpus-source.md):

1. Put the file at ``datasets/corpus/<id>/<file>``.
2. Add an entry to ``config/corpus-sources.json``.
3. Re-run ``python -m yen_tamizh_backend.corpus.ingest``.

Every input is read as a STREAM - line by line for ``delimited`` sources, and
one array element at a time for ``json-array`` sources, whose reader hands
buffered text to the standard library's own ``JSONDecoder.raw_decode`` rather
than reinventing a JSON parser. Peak memory is one chunk plus one record, so a
193 MB corpus costs no more to read than a 500 KB one.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from yen_tamizh_backend.contracts.base import ChangelogEntry
from yen_tamizh_backend.contracts.corpus_sources import CorpusSource, CorpusSources
from yen_tamizh_backend.contracts.master_wordlist import (
    IngestCounters,
    MasterWord,
    MasterWordlist,
    SourceProvenance,
)
from yen_tamizh_backend.corpus import rank
from yen_tamizh_backend.wordsmith.artifact import render_document, sha256_of, write_artifact
from yen_tamizh_backend.ezhuthu import classify, segment

# 64 KB keeps the JSON reader's working set small while still swallowing any
# single dictionary entry whole.
_CHUNK = 1 << 16

# Ezhuthu kinds that make a string a Tamil WORD. Anything else - a digit, a
# space, punctuation, a Latin letter, U+0BD0 om - disqualifies the whole token.
_WORD_KINDS = frozenset({"uyir", "mei", "uyirmei", "aytham"})

_SCHEMA_VERSION = "2026-08-13"
_CHANGELOG = [
    ChangelogEntry(
        version=_SCHEMA_VERSION,
        change="Initial ranked master wordlist emitted by the corpus ingest.",
        why="Row 8 corpus layer - the single source the derived per-Game sets read.",
    )
]


@dataclass(slots=True)
class _Accumulated:
    """The in-memory merge state for one distinct word (compact on purpose).

    ``source_bits`` is a bitmask over the enabled sources' registry positions
    rather than a list of ids: at a few million distinct words, a list per word
    is hundreds of megabytes of duplicated strings.
    """

    total: int
    source_bits: int
    categories: frozenset[str]


@dataclass(slots=True)
class _SourceTally:
    rows_in: int = 0
    rows_kept: int = 0


@dataclass(slots=True)
class _Record:
    """One raw record as read from a source, before normalization."""

    word: str
    count: int
    categories: tuple[str, ...] = ()


@dataclass(slots=True)
class IngestResult:
    """The ingest's output plus a human-readable run summary."""

    wordlist: MasterWordlist
    notes: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------
# Readers. One per source `kind`; both are generators, so nothing is buffered
# beyond the current chunk. A new FORMAT is the one change that needs code:
# add a reader here and a member to `SourceKind` in the contract.
# --------------------------------------------------------------------------


def _read_delimited(handle: TextIO, source: CorpusSource) -> Iterator[_Record]:
    """Stream ``word<delim>count`` records, one per line."""
    assert source.delimiter is not None and source.wordColumn is not None
    rows = iter(handle)
    if source.hasHeader:
        next(rows, None)
    for line in rows:
        stripped = line.strip()
        if not stripped:
            continue
        columns = stripped.split(source.delimiter)
        if source.wordColumn >= len(columns):
            yield _Record(word="", count=0)
            continue
        count = 0
        if source.countColumn is not None and source.countColumn < len(columns):
            raw_count = columns[source.countColumn].strip()
            if raw_count.isdigit():
                count = int(raw_count)
        yield _Record(word=columns[source.wordColumn].strip(), count=count)


def _read_json_array(handle: TextIO, source: CorpusSource) -> Iterator[_Record]:
    """Stream the objects of the array held under ``rootKey``."""
    assert source.rootKey is not None and source.wordField is not None
    for element in _iter_json_objects(handle, source.rootKey):
        raw_word = element.get(source.wordField)
        if not isinstance(raw_word, str):
            yield _Record(word="", count=0)
            continue
        count = 0
        if source.countField is not None:
            raw_count = element.get(source.countField)
            if isinstance(raw_count, int) and not isinstance(raw_count, bool):
                count = max(raw_count, 0)
        categories: tuple[str, ...] = ()
        if source.categoryField is not None:
            raw_categories = element.get(source.categoryField)
            if isinstance(raw_categories, list):
                categories = tuple(c for c in raw_categories if isinstance(c, str))
        yield _Record(word=raw_word, count=count, categories=categories)


def _iter_json_objects(handle: TextIO, root_key: str) -> Iterator[dict[str, Any]]:
    """Yield each object of ``"<root_key>": [ ... ]`` without loading the file.

    The array is located textually (its key always precedes it in a generated
    corpus file), then the standard library's own incremental entry point,
    ``JSONDecoder.raw_decode``, parses one element at a time out of a sliding
    buffer. Elements must be objects - a truncated object always raises, which
    is what makes "decode failed" a reliable signal for "read more", whereas a
    truncated number could decode to a wrong value.
    """
    decoder = json.JSONDecoder()
    marker = re.compile(re.escape(json.dumps(root_key)) + r"\s*:\s*\[")
    tail = len(root_key) + 16
    buffer = ""
    while True:
        found = marker.search(buffer)
        if found is not None:
            buffer = buffer[found.end() :]
            break
        chunk = handle.read(_CHUNK)
        if not chunk:
            raise ValueError(f"no array found under key {root_key!r}")
        buffer = buffer[-tail:] + chunk
    while True:
        buffer = buffer.lstrip(" \t\r\n,")
        if buffer.startswith("]"):
            return
        if buffer.startswith("{"):
            try:
                element, end = decoder.raw_decode(buffer)
            except ValueError:
                pass
            else:
                buffer = buffer[end:]
                yield element
                continue
        elif buffer:
            raise ValueError(f"array under {root_key!r} holds a non-object element")
        chunk = handle.read(_CHUNK)
        if not chunk:
            raise ValueError(f"unterminated JSON array under key {root_key!r}")
        buffer += chunk


_READERS = {
    "delimited": _read_delimited,
    "json-array": _read_json_array,
}


def read_source(path: Path, source: CorpusSource) -> Iterator[_Record]:
    """Stream one source's records through the reader its ``kind`` names."""
    reader = _READERS[source.kind]
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        yield from reader(handle, source)


# --------------------------------------------------------------------------
# Normalization + acceptance
# --------------------------------------------------------------------------


def normalize(raw: str) -> str:
    """NFC-normalize and trim a raw token (NFC so the ezhuthu twins agree)."""
    return unicodedata.normalize("NFC", raw.strip())


def accept(word: str, min_length: int, max_length: int) -> list[str] | None:
    """Return the word's ezhuthu if it is a Tamil word of a wanted length.

    Acceptance is delegated entirely to the Row 6 ezhuthu library: every unit
    must classify as Tamil, so digits, Latin text, punctuation, and the ``_``
    joins in the older phrase lists all fall out without a bespoke code-point
    table that could drift from the segmenter.
    """
    if not word:
        return None
    ezhuthu = segment(word)
    if not min_length <= len(ezhuthu) <= max_length:
        return None
    if any(classify(unit) not in _WORD_KINDS for unit in ezhuthu):
        return None
    return ezhuthu


# --------------------------------------------------------------------------
# Ingest
# --------------------------------------------------------------------------


def ingest(registry: CorpusSources, repo_root: Path) -> IngestResult:
    """Run every enabled source through the pipeline into a master wordlist."""
    corpus_root = repo_root / registry.corpusRoot
    enabled = [source for source in registry.sources if source.enabled]
    if not enabled:
        raise ValueError("corpus registry has no enabled source")

    accumulated: dict[str, _Accumulated] = {}
    tallies: dict[str, _SourceTally] = {source.id: _SourceTally() for source in enabled}
    rows_in = rejected = duplicates = 0
    drop_categories = frozenset(registry.filters.dropCategories)

    for position, source in enumerate(enabled):
        bit = 1 << position
        tally = tallies[source.id]
        path = corpus_root / source.path
        for record in read_source(path, source):
            rows_in += 1
            tally.rows_in += 1
            word = normalize(record.word)
            if accept(word, registry.filters.minLength, registry.filters.maxLength) is None:
                rejected += 1
                continue
            tally.rows_kept += 1
            categories = frozenset(record.categories) - drop_categories
            previous = accumulated.get(word)
            if previous is None:
                accumulated[word] = _Accumulated(
                    total=record.count, source_bits=bit, categories=categories
                )
                continue
            duplicates += 1
            previous.total += record.count
            previous.source_bits |= bit
            if categories:
                previous.categories |= categories

    entries = [
        rank.CorpusEntry(
            word=word,
            total=state.total,
            sources=[
                source.id
                for position, source in enumerate(enabled)
                if state.source_bits & (1 << position)
            ],
            categories=sorted(state.categories),
        )
        for word, state in accumulated.items()
    ]
    ordered = rank.order(entries)
    above_floor, below_floor = rank.apply_floor(
        ordered, registry.filters.minTotalFrequency
    )
    selected, capped = rank.apply_cap(above_floor, registry.filters.maxWords)

    total = len(selected)
    words: list[MasterWord] = []
    for position, entry in enumerate(selected, start=1):
        ezhuthu = segment(entry.word)
        words.append(
            MasterWord(
                word=entry.word,
                ezhuthu=ezhuthu,
                length=len(ezhuthu),
                freqRank=position,
                freqBand=rank.band_for(position, total, registry.bands),
                sources=entry.sources,
                category=entry.categories or None,
            )
        )

    provenance: list[SourceProvenance] = []
    for source in enabled:
        sha256, size = sha256_of(corpus_root / source.path)
        provenance.append(
            SourceProvenance(
                id=source.id,
                name=source.name,
                origin=source.origin,
                path=f"{registry.corpusRoot}/{source.path}",
                bytes=size,
                sha256=sha256,
                rowsIn=tallies[source.id].rows_in,
                rowsKept=tallies[source.id].rows_kept,
            )
        )

    wordlist = MasterWordlist(
        version=_SCHEMA_VERSION,
        changelog=_CHANGELOG,
        generatedAt=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        provenance=provenance,
        counters=IngestCounters(
            rowsIn=rows_in,
            rejected=rejected,
            duplicates=duplicates,
            distinct=len(accumulated),
            belowFrequencyFloor=below_floor,
            capped=capped,
            rowsKept=len(words),
        ),
        words=words,
    )
    notes = [
        f"{entry.id}: rowsIn={entry.rowsIn} rowsKept={entry.rowsKept} "
        f"bytes={entry.bytes}"
        for entry in provenance
    ]
    return IngestResult(wordlist=wordlist, notes=notes)


# --------------------------------------------------------------------------
# Rendering + CLI
# --------------------------------------------------------------------------


def render(wordlist: MasterWordlist) -> str:
    """Render the artifact deterministically: pretty header, one word per line."""
    return render_document(wordlist.model_dump(mode="json", exclude_none=True), "words")


def _repo_root() -> Path:
    # ingest.py -> corpus -> yen_tamizh_backend -> backend -> <repo root>
    return Path(__file__).resolve().parents[3]


def load_registry(path: Path) -> CorpusSources:
    """Load and validate ``config/corpus-sources.json``."""
    return CorpusSources.model_validate_json(path.read_text(encoding="utf-8"))


def main() -> None:
    root = _repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=root / "config" / "corpus-sources.json",
        help="the corpus source registry to read",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=root / "datasets" / "wordlists" / "master" / "words_ranked.json",
        help="where to write the ranked master wordlist",
    )
    args = parser.parse_args()

    result = ingest(load_registry(args.registry), root)
    write_artifact(args.out, render(result.wordlist))

    for note in result.notes:
        print(note)
    counters = result.wordlist.counters
    print(
        f"rowsIn={counters.rowsIn} rejected={counters.rejected} "
        f"duplicates={counters.duplicates} distinct={counters.distinct} "
        f"belowFrequencyFloor={counters.belowFrequencyFloor} "
        f"capped={counters.capped} rowsKept={counters.rowsKept}"
    )
    # Paths leaving the process are relative + POSIX (CLAUDE.md section 2).
    print(f"wrote {args.out.resolve().relative_to(root).as_posix()}")


if __name__ == "__main__":
    main()
