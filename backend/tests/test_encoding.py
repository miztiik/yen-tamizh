"""The encoding contract for every committed text artifact.

`.gitattributes` pins what git STORES and `.editorconfig` pins what an editor
WRITES; neither can fail a build. This module is the fence that can: it reads
the bytes actually on disk and asserts the properties every reader downstream
assumes - strict UTF-8, no BOM, LF, NFC, BMP.

The properties are checked over the FILE TEXT rather than over parsed JSON
strings. That is both cheaper and stronger: if the whole decoded document is
NFC then so is every string in it, and a defect in a key or a comment is caught
too rather than only one in a value.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterator
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# Every committed artifact whose bytes a reader depends on. Raw third-party
# slices are excluded below rather than here, so adding a directory of generated
# output to this list is the whole cost of covering it.
_COVERED: tuple[str, ...] = (
    "config/*.json",
    "schemas/*.schema.json",
    "datasets/fixtures/*.jsonl",
    "datasets/fixtures/lexicon-expected/**/*.ndjson",
    "datasets/lexicon/by-class/**/*.ndjson",
    "datasets/lexicon/lexicon.meta.json",
    "datasets/lexicon/sources/llm-authored/entries.jsonl",
    "datasets/journeys/*.json",
    "datasets/wordlists/derived/*.json",
    "frontend/public/bank/**/*.json",
)

# Byte-exact slices of raw sources. Row 4's claim is that a fixture is a
# contiguous slice of its source, so these carry whatever the publisher wrote -
# CRLF, legacy normalization and all - and `.gitattributes` marks them `-text`.
_EXCLUDED_PREFIX = "datasets/fixtures/lexicon/"

# The Tamil block escaped as JSON. Its presence means a writer was flipped back
# to `ensure_ascii=True`, which is the regression this file exists to catch.
_ESCAPED_TAMIL = "\\u0b"

# The one file that must NOT store Tamil as script. Its Tamil strings are lookup
# KEYS - raw tags this repo matches a source's own vocabulary against - so an
# editor silently normalizing a decomposed literal would not corrupt a value, it
# would make an alias match nothing and drop the fact without an error. That is
# the single case where an escape buys something a reader's convenience does not
# outweigh, and the file says so itself in its own notes.
_ESCAPES_ARE_CORRECT: frozenset[str] = frozenset({"config/lexicon-sources.json"})


def _covered_files() -> list[Path]:
    found: list[Path] = []
    for pattern in _COVERED:
        found.extend(_REPO_ROOT.glob(pattern))
    return sorted(
        path
        for path in found
        if path.is_file()
        and not path.relative_to(_REPO_ROOT).as_posix().startswith(_EXCLUDED_PREFIX)
    )


_FILES = _covered_files()


def _rel(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def _ids() -> list[str]:
    return [_rel(path) for path in _FILES]


def _each() -> Iterator[Path]:
    yield from _FILES


def test_the_glob_set_actually_matches_something() -> None:
    # Guards the whole module: a renamed directory would otherwise turn every
    # test below into a silent pass over an empty list.
    assert len(_FILES) > 100, f"only {len(_FILES)} files matched - has a path moved?"


@pytest.mark.parametrize("path", _each(), ids=_ids())
def test_decodes_as_strict_utf8_without_a_bom(path: Path) -> None:
    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), f"{_rel(path)} starts with a UTF-8 BOM"
    raw.decode("utf-8")  # raises UnicodeDecodeError on any other encoding


@pytest.mark.parametrize("path", _each(), ids=_ids())
def test_line_endings_are_lf_and_the_file_ends_in_exactly_one(path: Path) -> None:
    raw = path.read_bytes()
    assert b"\r" not in raw, f"{_rel(path)} contains a carriage return"
    assert raw.endswith(b"\n"), f"{_rel(path)} has no trailing newline"
    assert not raw.endswith(b"\n\n"), f"{_rel(path)} ends in a blank line"


@pytest.mark.parametrize("path", _each(), ids=_ids())
def test_text_is_nfc_normalized(path: Path) -> None:
    # The segmenter treats a decomposed cluster as the same ezhuthu, but the
    # published address, the multiset key and every byte comparison are over the
    # code points - so two spellings of one word would silently be two words.
    text = path.read_text(encoding="utf-8")
    assert unicodedata.normalize("NFC", text) == text, f"{_rel(path)} is not NFC"


@pytest.mark.parametrize("path", _each(), ids=_ids())
def test_every_code_point_is_in_the_basic_multilingual_plane(path: Path) -> None:
    # An astral code point is a surrogate pair in JS and one unit in Python, so
    # the two twins would disagree on length for the same string.
    text = path.read_text(encoding="utf-8")
    astral = {char for char in text if ord(char) > 0xFFFF}
    assert not astral, f"{_rel(path)} holds astral code points: {sorted(astral)}"


@pytest.mark.parametrize("path", _each(), ids=_ids())
def test_tamil_is_stored_as_script_rather_than_escapes(path: Path) -> None:
    if _rel(path) in _ESCAPES_ARE_CORRECT:
        pytest.skip("escapes are load-bearing here - the Tamil strings are lookup keys")
    text = path.read_text(encoding="utf-8")
    assert _ESCAPED_TAMIL not in text, (
        f"{_rel(path)} escapes Tamil as \\uXXXX. Every writer in this repo emits "
        "ensure_ascii=False; an escaped file is unreadable to the people who have "
        "to judge whether its content is right."
    )
