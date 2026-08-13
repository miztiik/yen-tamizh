"""Golden-corpus + property tests for the ezhuthu twin (Row 6).

Loads the shared golden corpus ``datasets/fixtures/ezhuthu_golden.jsonl`` (the
same file the TypeScript twin's vitest suite loads) and asserts this Python
implementation segments every row identically. Because both twins assert against
the same expected split, ``segment_py(word) == golden == segment_ts(word)`` for
every row - the cross-language parity Oracle. Also asserts the round-trip
property ``"".join(segment(w)) == w``.

Real fixtures, no mocks (Holy Law #7).
"""

from __future__ import annotations

import json
from pathlib import Path

from yen_tamizh_backend.ezhuthu import classify, segment

_GOLDEN = (
    Path(__file__).resolve().parents[2]
    / "datasets"
    / "fixtures"
    / "ezhuthu_golden.jsonl"
)


def _load_golden() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with _GOLDEN.open(encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def test_golden_corpus_has_enough_rows() -> None:
    assert len(_load_golden()) >= 20


def test_golden_corpus_segmentation() -> None:
    for row in _load_golden():
        word = row["word"]
        expected = row["ezhuthu"]
        assert isinstance(word, str)
        assert isinstance(expected, list)
        assert segment(word) == expected, f"segmentation mismatch for {word!r}"


def test_golden_corpus_round_trip() -> None:
    for row in _load_golden():
        word = row["word"]
        assert isinstance(word, str)
        assert "".join(segment(word)) == word


# Extra property words beyond the golden corpus, incl. decomposed (NFD) forms
# written as explicit escapes so the intent is unambiguous.
_PROPERTY_WORDS = [
    "",  # empty input
    "abc123",  # pure ASCII
    "\u0b95\u0bc6\u0bbe",  # NFD ko (ka + e-sign + aa-sign)
    "\u0b95\u0bc6\u0bd7",  # NFD kau (ka + e-sign + au-length)
    "\u0b92\u0bd7",  # NFD au vowel (o + au-length)
    "\u0bbe",  # a leading combining mark on its own
    "\u0ba4\u0bae\u0bbf\u0bb4\u0bcd 2024",  # tamizh + space + digits
]


def test_property_round_trip_extra() -> None:
    for word in _PROPERTY_WORDS:
        assert "".join(segment(word)) == word


def test_nfd_two_part_matra_is_one_cluster() -> None:
    # ko written decomposed (three code points) must be a single ezhuthu.
    assert segment("\u0b95\u0bc6\u0bbe") == ["\u0b95\u0bc6\u0bbe"]
    assert classify("\u0b95\u0bc6\u0bbe") == "uyirmei"


def test_nfd_au_vowel_is_one_uyir() -> None:
    # au vowel written decomposed (o + au-length) is a single uyir.
    assert segment("\u0b92\u0bd7") == ["\u0b92\u0bd7"]
    assert classify("\u0b92\u0bd7") == "uyir"


def test_classify_kinds() -> None:
    assert classify("\u0b85") == "uyir"  # a
    assert classify("\u0b94") == "uyir"  # au
    assert classify("\u0b83") == "aytham"  # aytham
    assert classify("\u0b95") == "uyirmei"  # ka (bare consonant, inherent /a/)
    assert classify("\u0b95\u0bcd") == "mei"  # k (consonant + pulli)
    assert classify("\u0b95\u0bbe") == "uyirmei"  # kaa
    assert classify("\u0b95\u0bcb") == "uyirmei"  # koo (two-part matra)
    assert classify("\u0bb7") == "uyirmei"  # Grantha ssa
    assert classify("1") == "other"
    assert classify(" ") == "other"
    assert classify("") == "other"
