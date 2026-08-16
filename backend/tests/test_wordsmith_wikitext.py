"""Tests for the Tamil Wiktionary wikitext parser (Row 4b).

Real markup throughout, no mocks (Holy Law #7). The snippets below are the
shapes the dump actually uses, reduced to the smallest form that still carries
the convention under test, and every Tamil string is written as ``\\uXXXX``
escapes so the file stays ASCII and no decomposed literal can silently match
nothing.

What is proven:

1. **A section marker opens a block and a part-of-speech stamp does not.** The
   two look identical in the markup - both are ``{{...}}`` - and confusing them
   loses the synonym list that follows the stamp on the same line.
2. **A list of single Tamil words is a synonym set; a phrase is not.** A
   wikilinked stem inside an inflected phrase is not an equivalent of the word.
3. **What cannot be read is COUNTED.** Wikitext has conventions rather than a
   grammar, so the parser's promise is that every line it looked at inside a
   harvested block is either harvested or counted as skipped.
4. **A pointer is not an entry.** A redirect page asserts nothing.
"""

from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

import pytest

from yen_tamizh_backend.wordsmith.wikitext import (
    MAX_VALUES,
    POS_TAGS,
    clean,
    parse_page,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = (
    _REPO_ROOT / "datasets" / "fixtures" / "lexicon" / "ta-wiktionary-content.1x.xml"
)

# The markers, in the dump's own spelling.
MEANING = "\u0baa\u0bca\u0bb0\u0bc1\u0bb3\u0bcd"  # porul
EXPLAIN = "\u0bb5\u0bbf\u0bb3\u0b95\u0bcd\u0b95\u0bae\u0bcd"  # vilakkam
TRANSLATION = "\u0bae\u0bca\u0bb4\u0bbf\u0baa\u0bc6\u0baf\u0bb0\u0bcd\u0baa\u0bcd\u0baa\u0bc1"
ENGLISH = "\u0b86\u0b99\u0bcd\u0b95\u0bbf\u0bb2\u0bae\u0bcd"  # aangilam
SYNONYMS = "\u0b92\u0ba4\u0bcd\u0ba4 \u0b9a\u0bca\u0bb1\u0bcd\u0b95\u0bb3\u0bcd"
LITERARY = "\u0b87\u0bb2\u0b95\u0bcd\u0b95\u0bbf\u0baf\u0bae\u0bc8"  # ilakkiyamai
IMAGE = "\u0baa\u0b9f\u0bbf\u0bae\u0bae\u0bcd"  # padimam
NOUN_STAMP = "\u0baa\u0bc6"  # pe - the noun abbreviation
NOUN = "\u0baa\u0bc6\u0baf\u0bb0\u0bcd\u0b9a\u0bcd\u0b9a\u0bca\u0bb2\u0bcd"  # peyarcchol
VERB = "\u0bb5\u0bbf\u0ba9\u0bc8\u0b9a\u0bcd\u0b9a\u0bca\u0bb2\u0bcd"  # vinaicchol

# The words.
FIRE = "\u0ba4\u0bc0"  # thee
FLAME = "\u0ba8\u0bc6\u0bb0\u0bc1\u0baa\u0bcd\u0baa\u0bc1"  # neruppu
POVERTY = "\u0ba4\u0bb0\u0bbf\u0ba4\u0bcd\u0ba4\u0bbf\u0bb0\u0bae\u0bcd"  # tarittiram
WANT = "\u0b8f\u0bb4\u0bcd\u0bae\u0bc8"  # ezhmai
NEED = "\u0bb5\u0bb1\u0bc1\u0bae\u0bc8"  # varumai
RIPEN = "\u0bae\u0bc1\u0ba4\u0bbf\u0bb0\u0bcd"  # mutir
FRUIT = "\u0b95\u0bbe\u0baf\u0bcd"  # kaay
POD = "\u0ba8\u0bc6\u0bb1\u0bcd\u0bb1\u0bc1"  # netru
HINDI_SOME = "\u0915\u0941\u091b"  # kuch, Devanagari


# --------------------------------------------------------------------------
# 1. Blocks
# --------------------------------------------------------------------------


def test_a_meaning_marker_opens_a_block_on_the_same_line() -> None:
    facts = parse_page(FIRE, "{{PAGENAME}}{{" + MEANING + "}}  = [[" + FLAME + "]]")
    assert facts.definitions == [FLAME]
    assert facts.synonyms == [FLAME]


def test_a_part_of_speech_stamp_does_not_close_a_meaning_block() -> None:
    # The stamp sits INSIDE the meaning line in the dump's commonest layout, so
    # treating it as a section marker would drop every synonym after it.
    page = (
        "{{" + MEANING + "}}'''{{PAGENAME}}''' {{" + NOUN_STAMP + "}} - "
        "[[" + WANT + "]], [[" + NEED + "]]"
    )
    facts = parse_page(POVERTY, page)
    assert facts.synonyms == [WANT, NEED]
    assert facts.pos == [NOUN]


def test_a_section_marker_closes_the_meaning_block() -> None:
    page = "\n".join(
        [
            "{{" + MEANING + "}}",
            "# " + WANT,
            "{{" + LITERARY + "}}",
            "# " + NEED,
        ]
    )
    facts = parse_page(POVERTY, page)
    assert facts.definitions == [WANT], "a literary citation is not a definition"


def test_a_heading_named_for_a_language_is_not_a_translation_arm() -> None:
    # "==aangilam==" opens the English ENTRY of an English-titled page;
    # "{{aangilam}}" marks the English side of a translation list. Same word.
    heading = parse_page(POVERTY, f"=={ENGLISH}==\n: [[poverty]]")
    template = parse_page(
        POVERTY, "{{" + TRANSLATION + "}}\n{{" + ENGLISH + "}}\n:* [[poverty]]"
    )
    assert heading.translations == []
    assert template.translations == ["poverty"]


def test_a_numbered_lead_line_is_a_sense_and_a_starred_one_is_not() -> None:
    page = "\n".join(["'''{{PAGENAME}}''' {{" + NOUN + "}}", "# " + WANT, "* " + NEED])
    facts = parse_page(POVERTY, page)
    assert facts.definitions == [WANT]
    assert facts.pos == [NOUN]


# --------------------------------------------------------------------------
# 2. Synonyms
# --------------------------------------------------------------------------


def test_a_comma_list_of_single_tamil_words_is_a_synonym_set() -> None:
    facts = parse_page(POVERTY, "{{" + MEANING + "}} [[" + WANT + "]], " + NEED + ".")
    assert facts.synonyms == [WANT, NEED]


def test_a_phrase_that_merely_links_its_stems_is_not_a_synonym_set() -> None:
    # "mutirntu kaayntha kaay" links two stems it inflects. Harvesting them
    # would call a dried nut a synonym of ripen.
    page = (
        "{{" + MEANING + "}}\n#[[" + RIPEN + "]]\u0ba8\u0bcd\u0ba4\u0bc1 "
        "[[" + FRUIT + "]]\u0ba8\u0bcd\u0ba4 [[" + FRUIT + "]]"
    )
    facts = parse_page(POD, page)
    assert facts.definitions
    assert facts.synonyms == []


def test_a_synonym_section_yields_its_terms() -> None:
    facts = parse_page(POVERTY, f"==={SYNONYMS}===\n* [[{WANT}]], [[{NEED}]]")
    assert facts.synonyms == [WANT, NEED]


def test_a_word_is_never_its_own_synonym_or_its_own_definition() -> None:
    facts = parse_page(
        POVERTY, "{{" + MEANING + "}} [[" + POVERTY + "]], [[" + WANT + "]]"
    )
    assert POVERTY not in facts.synonyms
    assert POVERTY not in facts.definitions


# --------------------------------------------------------------------------
# 3. Translations
# --------------------------------------------------------------------------


def test_only_the_latin_values_of_a_translation_list_are_taken() -> None:
    page = "\n".join(
        [
            "{{" + TRANSLATION + "}}",
            f"* '''[[poverty]]''' - <small>([[{ENGLISH}]])</small>",
            f"* '''[[{HINDI_SOME}]]''' - <small>([[hindi]])</small>",
        ]
    )
    facts = parse_page(POVERTY, page)
    assert facts.translations == ["poverty"]


def test_a_translation_line_may_name_its_own_language_first() -> None:
    facts = parse_page(
        POVERTY, f"==={TRANSLATION}\u0b95\u0bb3\u0bcd===\n* {ENGLISH} - "
        "[[pride]],[[contempt]]"
    )
    assert facts.translations == ["pride", "contempt"]


# --------------------------------------------------------------------------
# 4. What cannot be read is counted
# --------------------------------------------------------------------------


def test_a_redirect_asserts_nothing() -> None:
    facts = parse_page(FIRE, "#REDIRECT [[" + FLAME + "]]")
    assert facts.is_empty()
    assert facts.harvested == 0


def test_a_bracketed_stamp_is_skipped_rather_than_read_as_a_meaning() -> None:
    facts = parse_page(POVERTY, "{{" + MEANING + "}}\n:*(" + NOUN_STAMP + ")\n:*.")
    assert facts.definitions == []
    assert facts.skipped == 1, "the stamp line must be counted, not dropped"


def test_an_empty_placeholder_line_is_neither_harvested_nor_counted() -> None:
    # A line that reduces to NOTHING at all never reached a fact and never lost
    # one either: it is markup, not content.
    facts = parse_page(POVERTY, "{{" + MEANING + "}}\n:*\n:\n#")
    assert facts.harvested == 0
    assert facts.skipped == 0


def test_a_language_arm_with_no_latin_value_is_counted(
) -> None:
    facts = parse_page(POVERTY, "{{" + TRANSLATION + "}}\n* [[" + HINDI_SOME + "]]")
    assert facts.translations == []
    assert facts.skipped == 1


# --------------------------------------------------------------------------
# 5. Cleaning
# --------------------------------------------------------------------------


def test_an_image_link_is_dropped_even_when_its_caption_holds_a_link() -> None:
    segment = f"[[{IMAGE}:X.jpg|thumb|right|120px|a [[{WANT}]] caption]] {NEED}"
    assert clean(segment) == NEED


def test_a_reference_and_a_comment_never_reach_the_text() -> None:
    assert clean(f"{WANT}<ref>a citation</ref>") == WANT
    assert clean(f"<!-- an editor note -->{WANT}") == WANT


def test_an_external_link_keeps_its_label_and_loses_its_url() -> None:
    assert clean(f"[http://example.org/x {WANT}]") == WANT


# --------------------------------------------------------------------------
# 6. Over the committed fixture
# --------------------------------------------------------------------------


def _fixture_pages() -> list[tuple[str, str]]:
    root = ElementTree.fromstring(_FIXTURE.read_text(encoding="utf-8"))
    return [
        (page.findtext("{*}title") or "", page.findtext("{*}revision/{*}text") or "")
        for page in root.findall("{*}page")
        if page.findtext("{*}ns") == "0"
    ]


FIXTURE_PAGES = _fixture_pages()


def test_the_fixture_holds_the_records_the_ledger_claims() -> None:
    assert len(FIXTURE_PAGES) == 50


@pytest.mark.parametrize(
    "title,text", FIXTURE_PAGES, ids=[str(index) for index in range(len(FIXTURE_PAGES))]
)
def test_every_fixture_page_parses_within_its_own_bounds(title: str, text: str) -> None:
    facts = parse_page(title, text)
    for values in (facts.definitions, facts.synonyms, facts.translations):
        assert len(values) <= MAX_VALUES
        assert len(set(values)) == len(values)
        assert all(value.strip() == value and value for value in values)
    assert set(facts.pos) <= set(POS_TAGS)
    assert title not in facts.synonyms
    assert title not in facts.definitions
    # A page that produced a fact must have harvested a line to produce it from.
    if not facts.is_empty() and not facts.pos:
        assert facts.harvested > 0


def test_the_parse_is_deterministic_over_the_whole_fixture() -> None:
    first = [parse_page(title, text) for title, text in FIXTURE_PAGES]
    again = [parse_page(title, text) for title, text in FIXTURE_PAGES]
    assert first == again


def test_the_fixture_yields_all_four_kinds_of_fact() -> None:
    parsed = [parse_page(title, text) for title, text in FIXTURE_PAGES]
    assert sum(len(facts.definitions) for facts in parsed) > 0
    assert sum(len(facts.synonyms) for facts in parsed) > 0
    assert sum(len(facts.translations) for facts in parsed) > 0
    assert sum(len(facts.pos) for facts in parsed) > 0
    assert sum(facts.skipped for facts in parsed) > 0, (
        "a parser over real markup that never counts a miss is not counting"
    )
