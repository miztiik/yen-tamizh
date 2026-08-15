"""The nearest-headword search behind the ``neighbour`` signal (Row 8).

A hand-written SymSpell-style deletion neighbourhood over the attested
headwords, plus the pass that scores a pruned query set against it. WHY the
query set is pruned and what that means for reading the signal is
``docs/architecture/lexicon/word-hood.md``; this module is the search.

Four things decide the shape of the code here:

1. **Distance is measured in EZHUTHU, never in code points.** Two Tamil words
   that differ by one whole syllable differ by several code points, and two
   that merely share a vowel sign look adjacent to a code-point metric. Every
   word is therefore re-encoded so that ONE ezhuthu is ONE character, after
   which any ordinary string edit distance is already an ezhuthu distance.
2. **The index is ONE sorted array of machine integers**, not a dictionary of
   strings. At ``maxEditDistance = 2`` the deletion neighbourhood runs to
   millions of entries, and a ``dict[str, list[int]]`` of that size costs well
   over a gigabyte in object headers alone. A packed ``array('q')`` of
   ``crc32(variant) << 20 | word id``, sorted, is twelve bytes an entry and is
   binary-searched with ``bisect``.
3. **The index is a CANDIDATE GENERATOR and every candidate is verified.** A
   32-bit hash collides now and then; a collision costs one wasted distance
   computation and can never produce a wrong answer, because the answer is the
   verified distance rather than the fact of a match.
4. **The scoring pass is deterministic whatever the scheduling.** A word's
   score is a pure function of the word and the index, results come back in
   input order, and the minimum over the candidate set is taken without an
   early exit that could depend on iteration order.
"""

from __future__ import annotations

import atexit
import multiprocessing
import os
import sqlite3
from array import array
from bisect import bisect_left
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from multiprocessing.pool import Pool
from multiprocessing.shared_memory import SharedMemory
from typing import Any, Final
from zlib import crc32

from yen_tamizh_backend.ezhuthu import analyse, segment

try:  # pragma: no cover - the absent branch is what CI exercises
    from rapidfuzz.distance import Levenshtein as _imported_levenshtein
except ModuleNotFoundError:
    _LEVENSHTEIN: Any | None = None
else:
    _LEVENSHTEIN = _imported_levenshtein

# Whether the optional verification accelerator is installed. It is declared in
# `[project.optional-dependencies] wordsmith` and NEVER in `[project]`
# dependencies, so CI installs the pipeline without it and takes the pure
# Python path below. Both paths return the same number - a test asserts it.
RAPIDFUZZ: Final[bool] = _LEVENSHTEIN is not None

# One ezhuthu, one character. The private use area is used because nothing else
# does: no Tamil text, no source, and no published artifact ever carries one, so
# an encoded word can never be confused with a real surface.
_FOREIGN: Final = "\ue000"
_ALPHABET_START: Final = 0xE001
_ALPHABET_LIMIT: Final = 0xF8FF

# The word id lives in the low bits of each packed entry, so sorting the array
# by its integer value sorts primarily by hash and keeps one hash's ids
# contiguous. Twenty bits is 1,048,576 headwords against the 461,214 the real
# store holds; the build asserts the headroom rather than assuming it.
_ID_BITS: Final = 20
_ID_MASK: Final = (1 << _ID_BITS) - 1

# The largest edit distance the deletion neighbourhood is viable at. Stated here
# and mirrored by the config schema, so neither a hand-edited config file nor a
# directly constructed model can ask for the two-to-five-hour run: at two the
# index is millions of entries and the pass is minutes, at three it is two and a
# half times as many entries and hours.
MAX_EDIT_DISTANCE: Final = 2

# How many surfaces one read of the store hands to the scoring pass. Large
# enough that the per-page seek and the pool round trip disappear, small enough
# that a page is tens of megabytes rather than the whole query set. A machine
# constant like the store's bulk pragmas, not a tunable judgement.
PAGE: Final = 200_000


class Foreign(Exception):
    """Raised when a word needs more distinct ezhuthu than the encoding has."""


@dataclass(frozen=True, slots=True)
class Headwords:
    """The encoded headwords as one blob, so a worker carries megabytes.

    A candidate is decoded on demand rather than held as 400,000-odd separate
    string objects: only a handful are ever looked at per query, and the blob
    plus its offsets is a twentieth of the memory the list would cost in each
    worker process.
    """

    blob: bytes
    offsets: array[int]

    def __len__(self) -> int:
        return len(self.offsets) - 1

    def __getitem__(self, index: int) -> str:
        return self.blob[self.offsets[index] : self.offsets[index + 1]].decode("utf-8")


@dataclass(frozen=True, slots=True)
class NeighbourIndex:
    """A deletion neighbourhood over the headwords, ready to query."""

    alphabet: dict[str, str]
    maxDistance: int
    headwords: Headwords
    # Sorted (crc32(deletion variant) << _ID_BITS | word id).
    packed: Sequence[int]

    def note(self) -> str:
        return (
            f"headwords={len(self.headwords)} entries={len(self.packed)} "
            f"alphabet={len(self.alphabet)} maxDistance={self.maxDistance}"
        )


def build_alphabet(units: Iterable[str]) -> dict[str, str]:
    """Assign one private-use character per ezhuthu, in sorted order.

    Sorted so the assignment is a pure function of the set: two runs over the
    same headwords build the same encoding, which is half of why two runs
    produce the same signal vector.
    """
    ordered = sorted(set(units))
    if len(ordered) > _ALPHABET_LIMIT - _ALPHABET_START + 1:
        raise Foreign(f"{len(ordered)} distinct ezhuthu will not fit the encoding")
    return {unit: chr(_ALPHABET_START + index) for index, unit in enumerate(ordered)}


def encode(ezhuthu: Sequence[str], alphabet: dict[str, str]) -> str:
    """Re-write a segmented word so one ezhuthu is one character.

    A unit the headwords never used becomes the single FOREIGN character. That
    is safe rather than lossy: distances are only ever measured against
    headwords, no headword contains it, so a foreign unit mismatches every
    dictionary character exactly as a distinct one would.
    """
    return "".join([alphabet.get(unit, _FOREIGN) for unit in ezhuthu])


def deletion_variants(word: str, max_distance: int) -> set[str]:
    """``word`` and every string reachable from it by up to ``max_distance``
    deletions.

    A set rather than a list: a word with a repeated ezhuthu reaches the same
    variant by deleting either copy, and indexing it twice would only cost
    memory.
    """
    variants = {word}
    frontier = {word}
    for _ in range(max_distance):
        nxt: set[str] = set()
        for value in frontier:
            for index in range(len(value)):
                nxt.add(value[:index] + value[index + 1 :])
        nxt -= variants
        variants |= nxt
        frontier = nxt
    return variants


def bounded_distance(left: str, right: str, limit: int) -> int:
    """Levenshtein distance, or ``limit + 1`` once it is certain to exceed it.

    The same answer ``rapidfuzz`` gives for the same ``score_cutoff``, so which
    of the two ran cannot change a stored value. Words are a handful of ezhuthu
    long, so a full row-at-a-time table with a per-row cutoff is both simpler
    and faster here than a banded one.
    """
    if abs(len(left) - len(right)) > limit:
        return limit + 1
    if left == right:
        return 0
    previous = list(range(len(right) + 1))
    for row, unit in enumerate(left, start=1):
        current = [row]
        best = row
        for column, other in enumerate(right, start=1):
            value = min(
                previous[column] + 1,
                current[column - 1] + 1,
                previous[column - 1] + (unit != other),
            )
            current.append(value)
            if value < best:
                best = value
        if best > limit:
            return limit + 1
        previous = current
    return previous[-1] if previous[-1] <= limit else limit + 1


def distance(left: str, right: str, limit: int) -> int:
    """The verified ezhuthu distance, through rapidfuzz when it is installed."""
    if _LEVENSHTEIN is None:
        return bounded_distance(left, right, limit)
    return int(_LEVENSHTEIN.distance(left, right, score_cutoff=limit))


def _packed_entries(words: Sequence[str], max_distance: int) -> Iterator[int]:
    for word_id, word in enumerate(words):
        for variant in deletion_variants(word, max_distance):
            yield (crc32(variant.encode("utf-8")) << _ID_BITS) | word_id


def build_index(headwords: Iterable[str], max_distance: int) -> NeighbourIndex:
    """Build the deletion neighbourhood over ``headwords``.

    ``max_distance`` is asserted here and not only in the config schema, because
    the arithmetic is what makes it a hard limit rather than a preference: a
    typo in a config file must fail rather than quietly cost an afternoon.
    """
    if not 1 <= max_distance <= MAX_EDIT_DISTANCE:
        raise ValueError(
            f"maxEditDistance is {max_distance}; the deletion neighbourhood is "
            f"only viable up to {MAX_EDIT_DISTANCE}"
        )
    surfaces = sorted({word for word in headwords if word})
    alphabet = build_alphabet(unit for word in surfaces for unit in segment(word))
    encoded = sorted({encode(segment(word), alphabet) for word in surfaces})
    del surfaces
    if len(encoded) > _ID_MASK:
        raise ValueError(
            f"{len(encoded)} headwords will not fit the {_ID_BITS}-bit word id"
        )
    blob = bytearray()
    offsets = array("q", [0])
    for word in encoded:
        blob += word.encode("utf-8")
        offsets.append(len(blob))
    entries = list(_packed_entries(encoded, max_distance))
    entries.sort()
    packed = array("q", entries)
    del entries
    return NeighbourIndex(
        alphabet=alphabet,
        maxDistance=max_distance,
        headwords=Headwords(blob=bytes(blob), offsets=offsets),
        packed=packed,
    )


def candidates(encoded: str, index: NeighbourIndex) -> set[int]:
    """Every headword id whose deletion neighbourhood meets ``encoded``'s."""
    packed = index.packed
    size = len(packed)
    found: set[int] = set()
    for variant in deletion_variants(encoded, index.maxDistance):
        key = crc32(variant.encode("utf-8")) << _ID_BITS
        position = bisect_left(packed, key)
        while position < size and (packed[position] >> _ID_BITS) == (key >> _ID_BITS):
            found.add(packed[position] & _ID_MASK)
            position += 1
    return found


def nearest(word: str, index: NeighbourIndex) -> int:
    """The ezhuthu distance from ``word`` to the nearest headword.

    ``maxDistance + 1`` when no headword is that close - "further than we
    looked", which is a different answer from "we did not look".
    """
    limit = index.maxDistance
    encoded = encode(segment(word), index.alphabet)
    if not encoded:
        return limit + 1
    best = limit + 1
    headwords = index.headwords
    for word_id in candidates(encoded, index):
        # No early exit above zero: the minimum over the candidate set must not
        # depend on the order the set happens to iterate in.
        found = distance(encoded, headwords[word_id], limit)
        if found < best:
            best = found
            if best == 0:
                break
    return best


def closeness(word: str, index: NeighbourIndex) -> float:
    """How close the nearest headword is, as the reciprocal of its distance.

    One when a headword is a single ezhuthu away, a half at two, and zero when
    none is within ``maxEditDistance``. Higher means "more like a misspelling of
    a real word", which is the only thing this signal is read for.
    """
    found = nearest(word, index)
    if found > index.maxDistance:
        return 0.0
    return 1.0 / max(found, 1)


def is_fully_tamil(word: str) -> bool:
    """Whether every unit of ``word`` is an ezhuthu.

    The same test ``orthotactic`` uses to score a surface zero outright, reused
    rather than restated: a surface holding a Latin letter, a digit or a space
    is not badly-shaped Tamil, and it has no business in a Tamil dictionary.
    """
    return not analyse(word).hasNonTamil


# --------------------------------------------------------------------------
# The scoring pass
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Worker:
    """What one process needs to score: the index, and its shared segment."""

    index: NeighbourIndex
    shared: SharedMemory


_STATE: _Worker | None = None


def _buffer(shared: SharedMemory) -> memoryview[int]:
    view = shared.buf
    if view is None:  # pragma: no cover - only reachable after close()
        raise RuntimeError("the shared index segment is no longer mapped")
    return view


def _detach() -> None:
    """Drop the view onto shared memory before the process tears it down.

    Without this the interpreter closes the mapping while a memoryview still
    exports a pointer into it, and every worker prints a BufferError from its
    finaliser on the way out.
    """
    global _STATE
    state = _STATE
    if state is None:
        return
    _STATE = None
    shared = state.shared
    del state
    shared.close()


def _attach(
    name: str,
    entries: int,
    alphabet: dict[str, str],
    headwords: Headwords,
    max_distance: int,
) -> None:
    """Wire one pool worker to the index the parent already built.

    The packed array is read out of shared memory rather than pickled to each
    worker: it is the one large structure, and handing every process its own
    copy would multiply the run's memory by the number of cores.
    """
    global _STATE
    shared = SharedMemory(name=name)
    packed = _buffer(shared)[: entries * 8].cast("q")
    _STATE = _Worker(
        index=NeighbourIndex(
            alphabet=alphabet,
            maxDistance=max_distance,
            headwords=headwords,
            packed=packed,
        ),
        shared=shared,
    )
    atexit.register(_detach)


def _score_chunk(words: list[str]) -> list[float]:
    state = _STATE
    if state is None:
        raise RuntimeError("this worker was never handed an index")
    index = state.index
    return [closeness(word, index) for word in words]


def _chunks(words: list[str], count: int) -> list[list[str]]:
    """Split one page into ``count`` slices of near-equal size, in order."""
    if count <= 1:
        return [words]
    size = max(1, -(-len(words) // count))
    return [words[start : start + size] for start in range(0, len(words), size)]


def worker_count(requested: int | None) -> int:
    """How many processes to score with: what was asked, or what there is."""
    if requested is not None:
        if requested < 1:
            raise ValueError(f"workers must be at least 1, not {requested}")
        return requested
    return os.cpu_count() or 1


def _page(
    conn: sqlite3.Connection, predicate: str, values: tuple[object, ...], after: str
) -> list[str]:
    rows = conn.execute(
        f"SELECT word FROM signal WHERE {predicate} AND word > ? "
        f"ORDER BY word LIMIT {PAGE}",
        (*values, after),
    ).fetchall()
    return [str(row[0]) for row in rows]


def score_population(
    conn: sqlite3.Connection,
    index: NeighbourIndex,
    predicate: str,
    values: tuple[object, ...],
    workers: int,
) -> int:
    """Score every surface the prune predicate admits, and write the column.

    Read in primary-key pages rather than over one long cursor: the pass writes
    to the same table it reads, and SQLite leaves the behaviour of a cursor
    whose table is being modified under it undefined. Paging by ``word >`` also
    caps the memory the pass holds at one page, whatever the query set's size.
    """
    if workers > 1:
        return _score_in_parallel(conn, index, predicate, values, workers)
    written = 0
    after = ""
    while True:
        page = _page(conn, predicate, values, after)
        if not page:
            return written
        scored = [closeness(word, index) for word in page]
        conn.executemany(
            "UPDATE signal SET neighbour = ? WHERE word = ?",
            zip(scored, page, strict=True),
        )
        written += len(page)
        after = page[-1]


def _score_in_parallel(
    conn: sqlite3.Connection,
    index: NeighbourIndex,
    predicate: str,
    values: tuple[object, ...],
    workers: int,
) -> int:
    packed = array("q", index.packed)
    shared = SharedMemory(create=True, size=max(8, len(packed) * 8))
    pool: Pool | None = None
    try:
        _buffer(shared)[: len(packed) * 8] = packed.tobytes()
        pool = multiprocessing.Pool(
            processes=workers,
            initializer=_attach,
            initargs=(
                shared.name,
                len(packed),
                index.alphabet,
                index.headwords,
                index.maxDistance,
            ),
        )
        written = 0
        after = ""
        while True:
            page = _page(conn, predicate, values, after)
            if not page:
                return written
            # `map` and not `imap_unordered`: the results come back in the order
            # the chunks went out, so what lands in the column cannot depend on
            # which worker finished first.
            scored = [
                value
                for part in pool.map(_score_chunk, _chunks(page, workers))
                for value in part
            ]
            conn.executemany(
                "UPDATE signal SET neighbour = ? WHERE word = ?",
                zip(scored, page, strict=True),
            )
            written += len(page)
            after = page[-1]
    finally:
        if pool is not None:
            pool.close()
            pool.join()
        shared.close()
        shared.unlink()
