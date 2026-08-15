"""Streaming readers, one per source KIND (Row 5).

Turns a registered source's raw bytes into elements, and nothing more: an
element is whatever the source's own format holds - a split line, a JSON object,
a bare JSON string. What an element MEANS is ``extract.py``'s job.

Every reader here is a GENERATOR over a bounded buffer. No reader calls
``json.load``, ``read()`` or ``readlines()`` on a source file, because the
largest registered source is 188 MB and peak memory must not track file size.
The buffer size is a PARAMETER rather than a constant so the chunk-invariance
predicate in ``backend/tests/test_wordsmith_extract.py`` can drive a split
through the middle of every element.

The element rule for ``json-array`` is that an element grammar must be
SELF-TERMINATING - a proper prefix of a complete element is never itself a
complete element - so a ``raw_decode`` failure reliably means "read more"
instead of "silently wrong value". That admits exactly ``{`` and ``"``; the
reasoning is in ``docs/architecture/lexicon/pipeline.md``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any, TextIO

from yen_tamizh_backend.contracts.lexicon_sources import ElementKind, LexiconSource

# 64 KiB: big enough to swallow any single record whole (A7's are ~6 KB), small
# enough that a 188 MB source costs no more to read than a 500 KB one.
DEFAULT_CHUNK = 1 << 16

# The self-terminating openers, keyed by the contract's `elementKind`. There is
# no third entry, because no other JSON grammar has the property.
_OPENERS: dict[ElementKind, str] = {"object": "{", "string": '"'}

# Whitespace, element separators, and a UTF-8 BOM decoded as a character.
_SKIPPABLE = " \t\r\n,\ufeff"


def iter_delimited(handle: TextIO, source: LexiconSource) -> Iterator[list[str]]:
    """Yield one split line at a time.

    A blank line is not a record and is skipped; a header line is consumed when
    the registry declares one. Everything else - including a line with too few
    columns - is yielded, because deciding what a short line means is
    extraction's job and this reader must not filter.
    """
    if source.delimiter is None:
        raise ValueError(f"source {source.id!r}: kind 'delimited' needs a delimiter")
    rows = iter(handle)
    if source.hasHeader:
        next(rows, None)
    for line in rows:
        stripped = line.strip()
        if not stripped:
            continue
        yield stripped.split(source.delimiter)


def iter_jsonl(handle: TextIO, source: LexiconSource) -> Iterator[Any]:
    """Yield one decoded JSON value per line.

    A line is self-terminating by construction - the newline ends it - so this
    reader needs no sliding buffer, only the guarantee that it never holds more
    than one line.
    """
    for number, line in enumerate(handle, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            yield json.loads(stripped)
        except ValueError as error:
            raise ValueError(
                f"source {source.id!r}: line {number} is not valid JSON: {error}"
            ) from error


def iter_json_array(
    handle: TextIO,
    root_key: str | None,
    element_kind: ElementKind,
    chunk: int = DEFAULT_CHUNK,
) -> Iterator[Any]:
    """Yield the elements of one JSON array without loading the document.

    ``root_key`` names the key the array hangs under; ``None`` asserts that the
    document ROOT is the array. The standard library's own incremental entry
    point, ``JSONDecoder.raw_decode``, parses one element at a time out of a
    sliding buffer - no JSON parser is reinvented here.

    An element that does not open with this ``element_kind``'s character raises
    at once, naming the array, because that is what turns "a bare number
    appeared" into a hard failure rather than a silently truncated value.
    ``true`` / ``false`` / ``null`` are refused on the same line even though a
    truncated one raises, because none of them can be a word.
    """
    if chunk < 1:
        raise ValueError(f"chunk must be at least 1 byte, got {chunk}")
    opener = _OPENERS[element_kind]
    decoder = json.JSONDecoder()
    where = f"under key {root_key!r}" if root_key is not None else "at the document root"
    buffer = ""

    if root_key is None:
        while True:
            buffer = buffer.lstrip(_SKIPPABLE)
            if buffer.startswith("["):
                buffer = buffer[1:]
                break
            if buffer:
                raise ValueError(
                    f"the document root is {buffer[0]!r}, not the array the registry "
                    f"declares by omitting rootKey"
                )
            piece = handle.read(chunk)
            if not piece:
                raise ValueError("no array found at the document root")
            buffer += piece
    else:
        marker = re.compile(re.escape(json.dumps(root_key)) + r"\s*:\s*\[")
        # Keep enough of the previous read that a marker straddling two chunks
        # still matches, and no more - this is what bounds the search.
        keep = len(root_key) + 16
        while True:
            found = marker.search(buffer)
            if found is not None:
                buffer = buffer[found.end() :]
                break
            piece = handle.read(chunk)
            if not piece:
                raise ValueError(f"no array found under key {root_key!r}")
            buffer = buffer[-keep:] + piece

    while True:
        buffer = buffer.lstrip(_SKIPPABLE)
        if buffer.startswith("]"):
            return
        if buffer.startswith(opener):
            try:
                element, end = decoder.raw_decode(buffer)
            except ValueError:
                pass  # A truncated element: read more, never guess.
            else:
                buffer = buffer[end:]
                yield element
                continue
        elif buffer:
            raise ValueError(
                f"the array {where} holds an element opening with {buffer[0]!r}; "
                f"elementKind {element_kind!r} admits only {opener!r}, the one "
                f"self-terminating grammar - a proper prefix of it is never "
                f"itself a complete element"
            )
        piece = handle.read(chunk)
        if not piece:
            raise ValueError(f"unterminated JSON array {where}")
        buffer += piece


def read_elements(
    handle: TextIO, source: LexiconSource, chunk: int = DEFAULT_CHUNK
) -> Iterator[Any]:
    """Stream one source's elements through the reader its ``kind`` names."""
    if source.kind == "delimited":
        yield from iter_delimited(handle, source)
    elif source.kind == "jsonl":
        yield from iter_jsonl(handle, source)
    else:
        if source.elementKind is None:
            raise ValueError(f"source {source.id!r}: json-array needs an elementKind")
        yield from iter_json_array(handle, source.rootKey, source.elementKind, chunk)
