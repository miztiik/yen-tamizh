"""Streaming readers, one per source KIND (Row 5).

Turns a registered source's raw bytes into elements, and nothing more: an
element is whatever the source's own format holds - a split line, a JSON object,
a bare JSON string, one page of a MediaWiki export. What an element MEANS is
``extract.py``'s job.

Every reader here is a GENERATOR over a bounded buffer. No reader calls
``json.load``, ``read()`` or ``readlines()`` on a source file, because the
largest registered source is 647 MB and peak memory must not track file size.
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

import csv
import json
import re
from collections.abc import Iterator
from typing import Any, TextIO
from xml.parsers import expat

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


def iter_delimited_quoted(
    handle: TextIO, source: LexiconSource
) -> Iterator[list[str]]:
    """Yield one RFC-4180 FIELD sequence at a time.

    The difference from ``iter_delimited`` is visible in real bytes rather than
    in taste: a quoted field may hold the delimiter, a doubled quote, or a
    NEWLINE, so a logical record is not a physical line. IndoWordNet's linked
    release has three records whose gloss spans two lines, and splitting those
    lines gives four field sequences of the wrong width instead of two records.

    ``csv.reader`` is the standard library's own incremental entry point and it
    streams: it pulls from the handle's line iterator and never holds more than
    the record being assembled. No quoting grammar is written here (Holy Law
    #8).

    A blank record is skipped for the same reason a blank line is above, and a
    short record is yielded rather than judged - deciding what a short record
    means is extraction's job.
    """
    if source.delimiter is None:
        raise ValueError(
            f"source {source.id!r}: kind 'delimited-quoted' needs a delimiter"
        )
    rows = csv.reader(handle, delimiter=source.delimiter)
    if source.hasHeader:
        next(rows, None)
    for row in rows:
        if not any(field.strip() for field in row):
            continue
        yield row


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


def iter_mediawiki_pages(
    handle: TextIO, namespace: int, chunk: int = DEFAULT_CHUNK
) -> Iterator[dict[str, str]]:
    """Yield one ``{title, ns, text}`` record per page in ``namespace``.

    A MediaWiki export interleaves articles with talk, template, category and
    project pages, so which pages are RECORDS is declared per source
    (``pageNamespace``) exactly as ``hasHeader`` declares that a delimited
    file's first line is not one.

    Written against ``xml.parsers.expat`` rather than ``ElementTree`` for one
    measured reason: a tree builder materializes every page it is handed, and
    the three largest pages in the first two thousand of the Tamil Wiktionary
    dump are a template listing and a village-pump archive - 226 KB, 346 KB and
    1,035 KB against a 23 KB largest ARTICLE. ``<ns>`` arrives before
    ``<revision>``, so a handler-driven parse can decline to accumulate the
    text of a page that is not a record at all, which is what keeps peak memory
    proportional to the largest RECORD instead of to the largest page. Expat is
    the parser either way; this is the incremental entry point to it, not a
    parser written here.
    """
    if chunk < 1:
        raise ValueError(f"chunk must be at least 1 byte, got {chunk}")
    wanted = str(namespace)
    parser = expat.ParserCreate()
    parser.buffer_text = True
    ready: list[dict[str, str]] = []
    page: dict[str, str] | None = None
    field: str | None = None
    buffer: list[str] = []
    capture_text = True

    def start(name: str, attributes: dict[str, str]) -> None:
        nonlocal page, field, buffer, capture_text
        if name == "page":
            page = {"title": "", "ns": "", "text": ""}
            field = None
            capture_text = True
            return
        if page is None:
            return
        if name in ("title", "ns") or (name == "text" and capture_text):
            field = name
            buffer = []

    def data(piece: str) -> None:
        if field is not None:
            buffer.append(piece)

    def end(name: str) -> None:
        nonlocal page, field, buffer, capture_text
        if page is None:
            return
        if name == "page":
            if page["ns"] == wanted:
                ready.append(page)
            page = None
            field = None
            buffer = []
            return
        if name != field:
            return
        page[name] = "".join(buffer)
        field = None
        buffer = []
        if name == "ns":
            capture_text = page["ns"] == wanted

    parser.StartElementHandler = start
    parser.CharacterDataHandler = data
    parser.EndElementHandler = end

    while True:
        piece = handle.read(chunk)
        try:
            parser.Parse(piece, not piece)
        except expat.ExpatError as error:
            raise ValueError(
                f"the MediaWiki export is not well formed at line {error.lineno}, "
                f"column {error.offset}: {expat.ErrorString(error.code)}"
            ) from error
        if ready:
            yield from ready
            ready.clear()
        if not piece:
            return


def read_elements(
    handle: TextIO, source: LexiconSource, chunk: int = DEFAULT_CHUNK
) -> Iterator[Any]:
    """Stream one source's elements through the reader its ``kind`` names."""
    if source.kind == "delimited":
        yield from iter_delimited(handle, source)
    elif source.kind == "delimited-quoted":
        yield from iter_delimited_quoted(handle, source)
    elif source.kind == "jsonl":
        yield from iter_jsonl(handle, source)
    elif source.kind == "mediawiki-xml":
        if source.pageNamespace is None:
            raise ValueError(
                f"source {source.id!r}: kind 'mediawiki-xml' needs a pageNamespace"
            )
        yield from iter_mediawiki_pages(handle, source.pageNamespace, chunk)
    else:
        if source.elementKind is None:
            raise ValueError(f"source {source.id!r}: json-array needs an elementKind")
        yield from iter_json_array(handle, source.rootKey, source.elementKind, chunk)
