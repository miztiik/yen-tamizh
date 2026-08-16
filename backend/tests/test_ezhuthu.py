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

import pytest

from yen_tamizh_backend.ezhuthu import (
    EZHUTHU_INVENTORY,
    FINAL_MEI,
    classify,
    ends_like_a_word,
    ezhuthu_roman,
    is_a_letter,
    is_word_final,
    segment,
)

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


# --------------------------------------------------------------------------
# Word shape - which ezhuthu may END a Tamil word (Row 13's quality rule)
# --------------------------------------------------------------------------


def test_a_vowel_bearing_ezhuthu_always_ends_a_word() -> None:
    assert is_word_final("\u0b85")  # a (uyir)
    assert is_word_final("\u0b95")  # ka (uyirmei)
    assert is_word_final("\u0b95\u0bbe")  # kaa


def test_only_the_eight_mei_end_a_word() -> None:
    for final in FINAL_MEI:
        assert is_word_final(final), final
    assert not is_word_final("\u0b95\u0bcd")  # k
    assert not is_word_final("\u0ba4\u0bcd")  # th
    assert not is_word_final("\u0baa\u0bcd")  # p
    assert not is_word_final("\u0bb1\u0bcd")  # tr
    assert not is_word_final("\u0bb8\u0bcd")  # Grantha sa (loanword tail)


def test_ends_like_a_word_rejects_the_corpus_noise_it_was_written_for() -> None:
    # atharku-k: the euphonic doubling of the NEXT word, scraped onto this one.
    atharkuk = "\u0b85\u0ba4\u0bb1\u0bcd\u0b95\u0bc1\u0b95\u0bcd"
    # atharkku: the same ezhuthu in the wrong order - the misspelling that made
    # the pair look like a legitimate anagram (Row 13 Player finding).
    atharkku = "\u0b85\u0ba4\u0bb1\u0bcd\u0b95\u0bcd\u0b95\u0bc1"
    assert not ends_like_a_word(segment(atharkuk))
    assert ends_like_a_word(segment(atharkku))  # ends in a vowel, kept by shape
    # vaasal (doorway) and maram (tree) are real words and must survive.
    assert ends_like_a_word(segment("\u0bb5\u0bbe\u0b9a\u0bb2\u0bcd"))
    assert ends_like_a_word(segment("\u0bae\u0bb0\u0bae\u0bcd"))


def test_an_empty_segmentation_is_not_a_word() -> None:
    assert not ends_like_a_word([])


def test_every_ezhuthu_spells_uniquely_in_ascii() -> None:
    # The romanization is COMPOSED - the base letter plus the vowel its sign
    # writes - rather than tabulated, so 247 spellings need no 247 entries. A
    # collision would make two letters indistinguishable in the published index.
    spelled = [ezhuthu_roman(unit) for unit in EZHUTHU_INVENTORY]
    assert len(spelled) == 247
    assert len(set(spelled)) == 247
    assert all(label.isascii() and label.isalpha() for label in spelled)
    assert ezhuthu_roman("\u0b85") == "a"
    assert ezhuthu_roman("\u0b95") == "ka"  # the inherent vowel
    assert ezhuthu_roman("\u0b95\u0bbe") == "kaa"
    assert ezhuthu_roman("\u0b95\u0bcd") == "k"  # a mei writes no vowel
    assert ezhuthu_roman("\u0b83") == "aytham"  # a name, not a sound


def test_a_cluster_is_not_always_a_letter() -> None:
    # Segmentation is non-destructive and TOTAL: it attaches every combining
    # mark to whatever precedes it, so a legacy-encoding artifact comes back as
    # one cluster. This is the predicate that says it is not a letter.
    assert all(is_a_letter(unit) for unit in EZHUTHU_INVENTORY)
    for artifact in (
        "\u0b93\u0bbe\u0bcd",  # an independent vowel wearing a sign and a pulli
        "\u0b95\u0bbe\u0bbf",  # a consonant carrying two vowel signs
        "\u0b95\u0bcd\u0bbf",  # a mei with a vowel sign stuck on it
        "a",
    ):
        assert segment(artifact) == [artifact]
        assert not is_a_letter(artifact)
        with pytest.raises(ValueError):
            ezhuthu_roman(artifact)
