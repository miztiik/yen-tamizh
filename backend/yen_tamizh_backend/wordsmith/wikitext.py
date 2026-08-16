"""The Tamil Wiktionary wikitext shape (Row 4b).

One source in the registry ships MediaWiki markup rather than a table, and
markup is a SHAPE rather than a format: ``readers.py`` streams the pages,
``extract.py`` decides what a page asserts, and this module is the only place
that knows what ta.wiktionary's own editing conventions look like. It is the
same split ``_A2_POS_SPELLINGS`` draws for the English-Tamil dictionary, one
size larger.

Every Tamil marker below is written as ``\\uXXXX`` escapes with an ASCII gloss
beside it. Two reasons, both learned: the repository's prose is ASCII, and a
Tamil literal typed into a source file can arrive decomposed, which would make
a marker silently match nothing. The escapes are exact code points taken from
the dump.

The parse is deliberately CONSERVATIVE and COUNTED. A page is a sequence of
BLOCKS, each opened by a section template or a heading; only four block kinds
are harvested, and a line inside one of them that reduces to nothing is counted
rather than dropped, so ``harvested + skipped`` accounts for every line the
parser looked at. Wikitext has no grammar to be complete against - what it has
is conventions, and an unrecognised one must cost a counted miss, never an
invented fact.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal, cast

# --------------------------------------------------------------------------
# The markers. Block kinds first: what a section of a page IS.
# --------------------------------------------------------------------------

BlockKind = Literal["lead", "meaning", "explain", "translation", "synonym", "other"]

_MEANING = "\u0baa\u0bca\u0bb0\u0bc1\u0bb3\u0bcd"  # porul - meaning
_EXPLAIN = "\u0bb5\u0bbf\u0bb3\u0b95\u0bcd\u0b95\u0bae\u0bcd"  # vilakkam - explanation

# Section name -> what the section holds. A name NOT in this table is inline
# noise the cleaner strips, which is why the parts of speech live in their own
# table below: a POS stamp sits INSIDE a meaning line and must not close it.
_BLOCKS: dict[str, BlockKind] = {
    _MEANING: "meaning",
    _EXPLAIN: "explain",
    # mozhipeyarppu / -kal / -alaic ceer - translation, translations, "add one"
    "\u0bae\u0bca\u0bb4\u0bbf\u0baa\u0bc6\u0baf\u0bb0\u0bcd\u0baa\u0bcd\u0baa\u0bc1": "translation",
    "\u0bae\u0bca\u0bb4\u0bbf\u0baa\u0bc6\u0baf\u0bb0\u0bcd\u0baa\u0bcd\u0baa\u0bc1\u0b95\u0bb3\u0bcd": "translation",
    "\u0bae\u0bca\u0bb4\u0bbf\u0baa\u0bc6\u0baf\u0bb0\u0bcd\u0baa\u0bcd\u0baa\u0bc1\u0b95\u0bb3\u0bc8\u0b9a\u0bcd\u0b9a\u0bc7\u0bb0\u0bcd": "other",
    # aangilam / aang / aangi / aangilam-heading - the English arm of one
    "\u0b86\u0b99\u0bcd\u0b95\u0bbf\u0bb2\u0bae\u0bcd": "translation",
    "\u0b86\u0b99\u0bcd": "translation",
    "\u0b86\u0b99\u0bcd\u0b95\u0bbf": "translation",
    "\u0b86\u0b99\u0bcd\u0b95\u0bbf\u0bb2": "translation",
    "\u0b86\u0b99\u0bcd\u0ba4\u0bb2\u0bc8": "translation",
    # otta sorkal and its four spellings - synonyms
    "\u0b92\u0ba4\u0bcd\u0ba4 \u0b9a\u0bca\u0bb1\u0bcd\u0b95\u0bb3\u0bcd": "synonym",
    "\u0b92\u0ba4\u0bcd\u0ba4\u0b9a\u0bcd\u0b9a\u0bca\u0bb2\u0bcd": "synonym",
    "\u0b92\u0ba4\u0bcd\u0ba4\u0b9a\u0bcd\u0b9a\u0bca\u0bb1\u0bcd\u0b95\u0bb3\u0bcd": "synonym",
    "\u0b92\u0ba4\u0bcd\u0ba4\u0b9a\u0bca\u0bb2\u0bcd": "synonym",
    "\u0b92\u0ba4\u0bcd\u0ba4 \u0b95\u0bb0\u0bc1\u0ba4\u0bcd\u0ba4\u0bc1\u0bb3\u0bcd\u0bb3 \u0b9a\u0bca\u0bb1\u0bcd\u0b95\u0bb3\u0bcd": "synonym",
    # Everything below CLOSES a harvest block and contributes nothing: usage,
    # literary citation, grammar note, word family, pronunciation, sources,
    # examples, etymology, other languages, related words, formatting.
    "\u0baa\u0baf\u0ba9\u0bcd\u0baa\u0bbe\u0b9f\u0bc1": "other",  # payanpaadu
    "\u0b87\u0bb2\u0b95\u0bcd\u0b95\u0bbf\u0baf\u0bae\u0bc8": "other",  # ilakkiyamai
    "\u0b87\u0bb2\u0b95\u0bcd\u0b95\u0bbf\u0baf\u0bae\u0bcd": "other",  # ilakkiyam
    "\u0b87\u0bb2\u0b95\u0bcd\u0b95\u0ba3\u0bae\u0bc8": "other",  # ilakkanamai
    "\u0bb5\u0bb0\u0bbf\u0baf\u0bae\u0bc8": "other",  # variyamai
    "\u0b9a\u0bca\u0bb2\u0bcd \u0bb5\u0bb3\u0baa\u0bcd\u0baa\u0b95\u0bc1\u0ba4\u0bbf": "other",  # sol valappakuthi
    "\u0b9a\u0bca\u0bb2\u0bcd\u0bb5\u0bb3\u0bae\u0bcd": "other",  # solvalam
    "\u0b9a\u0bca\u0bb2\u0bcd\u0bb5\u0bb3\u0baa\u0bcd \u0baa\u0b95\u0bc1\u0ba4\u0bbf": "other",  # solvalap pakuthi
    "\u0b9a\u0bca\u0bb1\u0bcd\u0b95\u0bc1\u0bb5\u0bc8": "other",  # sorkuvai
    "\u0b92\u0bb2\u0bbf\u0baa\u0bcd\u0baa\u0bc1": "other",  # olippu
    "\u0b92\u0bb2\u0bbf\u0b95\u0bcd\u0b95\u0bcb\u0baa\u0bcd\u0baa\u0bc1": "other",  # olikkoppu
    "\u0baa\u0bb2\u0bc1\u0b95\u0bcd\u0b95\u0bb2\u0bcd": "other",  # palukkal
    "\u0b89\u0b9a\u0bbe\u0ba4\u0bcd\u0ba4\u0bc1\u0ba3\u0bc8": "other",  # usaaththunai
    "\u0bae\u0bc7\u0bb1\u0bcd\u0b95\u0bcb\u0bb3\u0bcd": "other",  # merkol
    "\u0bae\u0bc7\u0bb1\u0bcd\u0b95\u0bcb\u0bb3\u0bcd\u0b95\u0bb3\u0bcd": "other",  # merkolkal
    "\u0b86\u0ba4\u0bbe\u0bb0\u0bae\u0bcd": "other",  # aadhaaram
    "\u0b86\u0ba4\u0bbe\u0bb0\u0b99\u0bcd\u0b95\u0bb3\u0bcd": "other",  # aadhaarangal
    "\u0b86\u0ba4\u0bbe": "other",  # aadhaa
    "\u0ba4\u0bae\u0bbf\u0bb4\u0bcd\u0b86\u0ba4\u0bbe\u0bb0\u0b99\u0bcd\u0b95\u0bb3\u0bcd": "other",
    "\u0b86\u0b99\u0bcd\u0b86\u0ba4\u0bbe\u0bb0\u0bae\u0bcd": "other",
    "\u0b86\u0b99\u0bcd\u0b95\u0bbf\u0bb2 \u0b86\u0ba4\u0bbe\u0bb0\u0b99\u0bcd\u0b95\u0bb3\u0bcd": "other",
    "\u0b8e. \u0b95\u0bbe.": "other",  # e. kaa. - for example
    "\u0b8e.\u0b95\u0bbe": "other",
    "\u0b8e\u0b9f\u0bc1\u0ba4\u0bcd\u0ba4\u0bc1\u0b95\u0bcd\u0b95\u0bbe\u0b9f\u0bcd\u0b9f\u0bc1": "other",
    "\u0b9a\u0bca\u0bb1\u0bcd\u0bb1\u0bca\u0b9f\u0bb0\u0bcd \u0b8e\u0b9f\u0bc1\u0ba4\u0bcd\u0ba4\u0bc1\u0b95\u0bcd\u0b95\u0bbe\u0b9f\u0bcd\u0b9f\u0bc1": "other",
    "\u0b9a\u0bca\u0bb1\u0bcd\u0baa\u0bbf\u0bb1\u0baa\u0bcd\u0baa\u0bbf\u0baf\u0bb2\u0bcd": "other",
    "\u0b9a\u0bca\u0bb1\u0bcd\u0baa\u0bbf\u0bb1\u0baa\u0bcd\u0baa\u0bc1": "other",
    "\u0b9a\u0bca\u0bb1\u0bcd\u0ba4\u0bcb\u0bb1\u0bcd\u0bb1\u0bae\u0bcd": "other",
    "\u0baa\u0bbf\u0bb1\u0bae\u0bca\u0bb4\u0bbf\u0b95\u0bb3\u0bbf\u0bb2\u0bcd": "other",
    "\u0ba4\u0bca\u0b9f\u0bb0\u0bcd\u0baa\u0bc1\u0b9f\u0bc8\u0baf\u0b9a\u0bcd \u0b9a\u0bca\u0bb1\u0bcd\u0b95\u0bb3\u0bcd": "other",
    "\u0ba4\u0bca\u0b9f\u0bb0\u0bcd\u0baa\u0bc1\u0b9f\u0bc8\u0baf\u0b9a\u0bcd\u0b9a\u0bca\u0bb1\u0bcd\u0b95\u0bb3\u0bcd": "other",
    "\u0ba8\u0bc0\u0bb2\u0b85\u0b9f\u0bbf\u0b95\u0bcd\u0b95\u0bcb\u0b9f\u0bc1": "other",
    "\u0b85\u0b9f\u0bbf\u0b95\u0bcd\u0b95\u0bcb\u0b9f\u0bbf\u0b9f\u0bc1": "other",
    "\u0ba4\u0bae\u0bbf\u0bb4\u0bbf\u0bb2\u0bcd \u0bb5\u0bbf\u0bb3\u0b95\u0bcd\u0b95\u0bb5\u0bc1\u0bae\u0bcd": "other",
    "\u0bb5\u0bbf\u0bb0\u0bbf\u0bb5\u0bbe\u0b95\u0bcd\u0b95\u0bc1\u0b95": "other",
    "\u0bae\u0bca\u0bb4\u0bbf": "other",  # mozhi|xx - a language section
    "\u0b9a\u0bbf\u0bb1\u0bc1-\u0bae\u0bca\u0bb4\u0bbf": "other",
    "\u0ba4\u0bae\u0bbf\u0bb4\u0bcd": "other",  # tamizh
    "\u0ba4\u0bae\u0bbf": "other",  # tami
    "\u0b9a\u0bca\u0bb2\u0bcd": "other",  # sol - "word:" heading
}

# A HEADING carrying one of these names is a LANGUAGE SECTION, not a
# translation arm: "==aangilam==" opens the English entry of an English-titled
# page, while "{{aangilam}}" marks the English side of a translation list. Same
# word, opposite meaning, told apart by the form it is written in.
_HEADING_IS_A_LANGUAGE = frozenset(
    {
        "\u0b86\u0b99\u0bcd\u0b95\u0bbf\u0bb2\u0bae\u0bcd",
        "\u0b86\u0b99\u0bcd",
        "\u0b86\u0b99\u0bcd\u0b95\u0bbf",
        "\u0b86\u0b99\u0bcd\u0b95\u0bbf\u0bb2",
        "\u0b86\u0b99\u0bcd\u0ba4\u0bb2\u0bc8",
    }
)

# Raw part-of-speech tags, keyed by every spelling the wiki uses for them. The
# VALUE is the tag ``config/lexicon-sources.json`` routes through posAliases -
# the vocabulary is contract, the mapping is config, and this table is only the
# source's own orthography. Ambiguous one-letter stamps are deliberately absent.
_POS_NOUN = "\u0baa\u0bc6\u0baf\u0bb0\u0bcd\u0b9a\u0bcd\u0b9a\u0bca\u0bb2\u0bcd"  # peyarcchol
_POS_VERB = "\u0bb5\u0bbf\u0ba9\u0bc8\u0b9a\u0bcd\u0b9a\u0bca\u0bb2\u0bcd"  # vinaicchol
_POS_ADJECTIVE = "\u0b89\u0bb0\u0bbf\u0b9a\u0bcd\u0b9a\u0bca\u0bb2\u0bcd"  # uricchol
_POS_PARTICLE = "\u0b87\u0b9f\u0bc8\u0b9a\u0bcd\u0b9a\u0bca\u0bb2\u0bcd"  # idaicchol
_POS_NUMERAL = "\u0b8e\u0ba3\u0bcd"  # en - numeral
_POS_ADVERB = "\u0bb5\u0bbf\u0ba9\u0bc8\u0baf\u0bc1\u0bb0\u0bbf\u0b9a\u0bcd\u0b9a\u0bca\u0bb2\u0bcd"

POS_TAGS: tuple[str, ...] = (
    _POS_NOUN,
    _POS_VERB,
    _POS_ADJECTIVE,
    _POS_PARTICLE,
    _POS_NUMERAL,
    _POS_ADVERB,
)

_POS_SPELLINGS: dict[str, str] = {
    _POS_NOUN: _POS_NOUN,
    "\u0baa\u0bc6\u0baf\u0bb0\u0bcd\u0b9a\u0bcd\u0b9a\u0bca\u0bb1\u0bcd\u0b95\u0bb3\u0bcd": _POS_NOUN,
    "\u0baa\u0bc6": _POS_NOUN,  # pe - the noun abbreviation
    _POS_VERB: _POS_VERB,
    "\u0bb5\u0bbf\u0ba9\u0bc8\u0b9a\u0bcd\u0b9a\u0bca\u0bb1\u0bcd\u0b95\u0bb3\u0bcd": _POS_VERB,
    "\u0bb5\u0bbf": _POS_VERB,  # vi - the verb abbreviation
    "\u0bb5\u0bbf\u0ba9\u0bc8": _POS_VERB,
    _POS_ADJECTIVE: _POS_ADJECTIVE,
    "\u0b89\u0bb0\u0bbf\u0b9a\u0bcd\u0b9a\u0bca\u0bb1\u0bcd\u0b95\u0bb3\u0bcd": _POS_ADJECTIVE,
    _POS_PARTICLE: _POS_PARTICLE,
    "\u0b87\u0b9f\u0bc8\u0b9a\u0bcd\u0b9a\u0bca\u0bb1\u0bcd\u0b95\u0bb3\u0bcd": _POS_PARTICLE,
    _POS_NUMERAL: _POS_NUMERAL,
    _POS_ADVERB: _POS_ADVERB,
}

# Link namespaces that are never content: category, image, file, template.
_LINK_NAMESPACES = (
    "\u0baa\u0b95\u0bc1\u0baa\u0bcd\u0baa\u0bc1",  # pakuppu - category
    "\u0baa\u0b9f\u0bbf\u0bae\u0bae\u0bcd",  # padimam - image
    "\u0baa\u0b9f\u0bae\u0bcd",  # padam - picture
    "\u0bb5\u0bbe\u0bb0\u0bcd\u0baa\u0bcd\u0baa\u0bc1\u0bb0\u0bc1",  # vaarppuru - template
    "file",
    "image",
    "media",
    "category",
)

_CATEGORY_PREFIXES = ("\u0baa\u0b95\u0bc1\u0baa\u0bcd\u0baa\u0bc1", "category")

# One page may not contribute more values than this to any one column. A bound
# against a single malformed page, not a quality filter: a vandalised or
# auto-generated page can list hundreds of links in a meaning block, and a
# store row is not the place to discover that.
MAX_VALUES = 24

# A translation is a word or a short phrase. Past this it is a sentence, and a
# sentence in the English column is a gloss the reader mis-split.
MAX_TRANSLATION = 64

_TAMIL_BLOCK = "\u0b80-\u0bff"
_TAMIL_TOKEN = re.compile(f"^[{_TAMIL_BLOCK}]+$")
_HAS_TAMIL = re.compile(f"[{_TAMIL_BLOCK}]")
_LATIN_VALUE = re.compile(r"^[A-Za-z][A-Za-z '\-.]*$")

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_REFERENCE = re.compile(r"<ref\b[^>]*/>|<ref\b[^>]*>.*?</ref>", re.S | re.I)
_TAG = re.compile(r"</?[A-Za-z][^<>]{0,200}>")
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_EXTERNAL_LINK = re.compile(r"\[(?:https?|ftp)://\S*\s*([^\]]*)\]")
_WIKI_LINK = re.compile(r"\[\[([^\[\]|]*)(?:\|([^\[\]]*))?\]\]")
_BOLD_ITALIC = re.compile(r"'{2,5}")
_HEADING = re.compile(r"^\s*(=+)\s*(.*?)\s*=+\s*$")
_RULE = re.compile(r"^\s*-{4,}\s*$")
# A redirect is a pointer, not an entry: MediaWiki puts the magic word at the
# very start of the page. Its one line would otherwise read as a numbered sense
# and turn "see the other spelling" into a definition.
_REDIRECT = re.compile(r"^\s*#\s*redirect\b", re.I)
# One level of nesting is enough: "{{audio|ta-{{PAGENAME}}.ogg|...}}" is the
# deepest shape the dump uses around a section marker.
_MARKER = re.compile(r"\{\{\s*([^{}|\n]*?)\s*(?:\|(?:[^{}]|\{\{[^{}]*\}\})*)?\}\}")
_LIST_PREFIX = re.compile(r"^[#*:;=\-\s.]+")
_TRAILING = re.compile(r"[\s.,;:\-]+$")
# "aangilam - pride, contempt": a translation line may name its language first.
_LANGUAGE_PREFIX = re.compile(r"^[^A-Za-z]*?[\u0b80-\u0bff][^A-Za-z]*?-\s*(.+)$")
_WHITESPACE = re.compile(r"\s+")
# "(pe)", "(tami), (pe)": a bracketed register or part-of-speech stamp written
# as plain text rather than as a template. A line that is nothing but those
# says what KIND of word this is, never what it means.
_PARENTHETICAL = re.compile(r"\([^()]*\)")
_CATEGORY_LINK = re.compile(
    r"\[\[\s*(?:"
    + "|".join(re.escape(prefix) for prefix in _CATEGORY_PREFIXES)
    + r")\s*:\s*([^\[\]|]+?)\s*(?:\|[^\[\]]*)?\]\]",
    re.I,
)


@dataclass(slots=True)
class PageFacts:
    """What one page asserts about its own title, plus what was not readable.

    ``skipped`` counts lines inside a HARVESTED block that reduced to nothing a
    fact could be made of. It is the counted miss the module docstring promises:
    ``harvested + skipped`` is every line the parser looked at, so a convention
    this parser does not know shows up as a number rather than as silence.
    """

    definitions: list[str] = field(default_factory=list)
    synonyms: list[str] = field(default_factory=list)
    translations: list[str] = field(default_factory=list)
    pos: list[str] = field(default_factory=list)
    harvested: int = 0
    skipped: int = 0

    def is_empty(self) -> bool:
        return not (
            self.definitions or self.synonyms or self.translations or self.pos
        )


def _marker_name(raw: str) -> str:
    """One template or heading name, reduced to the form the tables are keyed on.

    Three reductions, each answering a real family in the dump: a trailing digit
    run (``solvalam3``, ``olippu1``), a suffix after a hyphen
    (``peyarcchol-pakuppu``, ``aadhaarangal-mozhi``), and the ``=xx=`` language
    stamps. Anything still unrecognised is left alone and treated as inline
    noise, which loses a fact rather than inventing one.
    """
    name = raw.strip()
    if len(name) > 2 and name.startswith("=") and name.endswith("="):
        return "\u0bae\u0bca\u0bb4\u0bbf"  # a language stamp is a language section
    return name


def _lookup(name: str, table: Mapping[str, str]) -> str | None:
    if name in table:
        return table[name]
    trimmed = name.rstrip("0123456789")
    if trimmed != name and trimmed in table:
        return table[trimmed]
    head = name.split("-", 1)[0]
    if head != name and head in table:
        return table[head]
    return None


def _block_of(name: str, heading: bool) -> BlockKind | None:
    reduced = _marker_name(name)
    if heading and reduced in _HEADING_IS_A_LANGUAGE:
        return "other"
    found = _lookup(reduced, _BLOCKS)
    return None if found is None else cast(BlockKind, found)


def _pos_of(name: str) -> str | None:
    return _lookup(name.strip(), _POS_SPELLINGS)


def _drop_link(target: str) -> bool:
    head = target.split(":", 1)[0].strip().lower() if ":" in target else ""
    return head in _LINK_NAMESPACES


def clean(segment: str) -> str:
    """Reduce one wikitext segment to the plain text a reader would see."""
    text = _COMMENT.sub(" ", segment)
    text = _REFERENCE.sub(" ", text)
    for _ in range(3):
        reduced = _TEMPLATE.sub(" ", text)
        if reduced == text:
            break
        text = reduced
    text = _EXTERNAL_LINK.sub(r" \1 ", text)
    # Innermost first: an image link may carry a caption that is itself a link,
    # and an unresolved outer link would leave the image's own name in the text.
    for _ in range(3):
        reduced = _WIKI_LINK.sub(
            lambda match: (
                ""
                if _drop_link(match.group(1))
                else (match.group(2) if match.group(2) is not None else match.group(1))
            ),
            text,
        )
        if reduced == text:
            break
        text = reduced
    text = _TAG.sub(" ", text)
    text = _BOLD_ITALIC.sub("", text)
    text = text.replace("{", " ").replace("}", " ").replace("[", " ").replace("]", " ")
    text = _LIST_PREFIX.sub("", text)
    text = _TRAILING.sub("", text)
    return _WHITESPACE.sub(" ", text).strip()


def _parts(text: str) -> list[str]:
    return [
        stripped
        for piece in re.split(r"[,;]", text)
        if (stripped := _TRAILING.sub("", piece.strip()).strip())
    ]


def _tamil_terms(text: str, title: str) -> list[str]:
    """The Tamil terms of a line that is entirely a list of single words.

    A wikilinked word inside a PHRASE is not a synonym: ``mutirnthu kaayntha
    kaay`` links two stems it inflects, and harvesting them would call a dried
    nut a synonym of ripen. So the whole line must reduce to single Tamil
    tokens separated by list punctuation before any of them counts.
    """
    parts = _parts(text)
    if not parts or not all(_TAMIL_TOKEN.match(part) for part in parts):
        return []
    return [part for part in parts if part != title]


def _harvest_meaning(text: str, title: str, facts: PageFacts) -> None:
    if not _HAS_TAMIL.search(text) or not _PARENTHETICAL.sub("", text).strip(" .,;:-"):
        facts.skipped += 1
        return
    facts.harvested += 1
    if text != title:
        facts.definitions.append(text)
    facts.synonyms.extend(_tamil_terms(text, title))


def _harvest_translation(text: str, facts: PageFacts) -> None:
    # A translation line names its own language, on either side of the value:
    # "aangilam - pride, contempt" and "poverty - (aangilam)" are both common.
    text = _PARENTHETICAL.sub(" ", text)
    named = _LANGUAGE_PREFIX.match(text)
    if named is not None:
        text = named.group(1)
    values = [
        part
        for part in _parts(text)
        if len(part) <= MAX_TRANSLATION and _LATIN_VALUE.match(part)
    ]
    if not values:
        facts.skipped += 1
        return
    facts.harvested += 1
    facts.translations.extend(values)


def _harvest_synonyms(text: str, title: str, facts: PageFacts) -> None:
    terms = _tamil_terms(text, title)
    if not terms:
        facts.skipped += 1
        return
    facts.harvested += 1
    facts.synonyms.extend(terms)


def _ordered(values: list[str], limit: int) -> list[str]:
    """First-seen order, deduped, bounded by ``limit``."""
    seen: dict[str, None] = {}
    for value in values:
        if value and value not in seen:
            seen[value] = None
        if len(seen) >= limit:
            break
    return list(seen)


def parse_page(title: str, text: str) -> PageFacts:
    """Everything one ta.wiktionary page asserts about its own title."""
    facts = PageFacts()
    if _REDIRECT.match(text):
        return facts
    block: BlockKind = "lead"
    for line in text.splitlines():
        heading = _HEADING.match(line)
        if heading is not None:
            block = _block_of(clean(heading.group(2)), heading=True) or "other"
            continue
        if _RULE.match(line):
            block = "lead"
            continue
        cursor = 0
        for marker in _MARKER.finditer(line):
            name = marker.group(1)
            found = _block_of(name, heading=False)
            tag = _pos_of(name)
            if tag is not None:
                facts.pos.append(tag)
            if found is None:
                continue
            _consume(line[cursor : marker.start()], block, title, facts)
            block = found
            cursor = marker.end()
        _consume(line[cursor:], block, title, facts, whole=cursor == 0)
    for category in _CATEGORY_LINK.finditer(text):
        tag = _pos_of(category.group(1))
        if tag is not None:
            facts.pos.append(tag)
    facts.definitions = _ordered(facts.definitions, MAX_VALUES)
    facts.synonyms = _ordered(facts.synonyms, MAX_VALUES)
    facts.translations = _ordered(facts.translations, MAX_VALUES)
    facts.pos = _ordered(facts.pos, len(POS_TAGS))
    return facts


def _consume(
    segment: str,
    block: BlockKind,
    title: str,
    facts: PageFacts,
    whole: bool = False,
) -> None:
    """Route one segment of one line to the harvester its block names.

    ``whole`` says the segment is a complete line that carried no marker, which
    is the only case where the LEAD block harvests: a numbered line before any
    section template is Wiktionary's own sense list, and the star and colon
    lines beside it are pronunciation, images and word families.
    """
    if block == "other":
        return
    if block == "lead":
        if not whole or not segment.lstrip().startswith("#"):
            return
        text = clean(segment)
        if text:
            _harvest_meaning(text, title, facts)
        return
    text = clean(segment)
    if not text:
        return
    if block in ("meaning", "explain"):
        _harvest_meaning(text, title, facts)
    elif block == "translation":
        _harvest_translation(text, facts)
    else:
        _harvest_synonyms(text, title, facts)
