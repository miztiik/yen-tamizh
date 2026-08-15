"""EXTRACT - stage 1 of the wordsmith pipeline (Row 5).

Turns one registered source's raw bytes into normalized OBSERVATIONS and FACTS
and writes them to one addressable file per source:
``datasets/lexicon/cache/extracts/<source-id>.jsonl``, gitignored. The stage is
explained in ``docs/architecture/lexicon/pipeline.md``; the vocabulary it speaks
- observation versus attestation, what a fact is - is defined once in
``docs/concepts/lexicon.md``.

Two rules bound everything here:

1. **EXTRACT never filters.** Not on word-hood, not on quality, not on length.
   The only transform is NFC normalization, which is canonicalization. A surface
   the sources showed us reaches the store even when it is obviously junk,
   because the whole point of the lexicon is that selection filters and ingest
   does not.
2. **EXTRACT is streaming.** Peak memory must not track file size - the largest
   registered source is 188 MB - so every reader is a generator over a bounded
   buffer (``readers.py``) and nothing accumulates across the file except one
   dictionary run, which the source's own sort order bounds.

What a source may ASSERT is bounded by its ``role``: only ``authority`` and
``authored`` emit a ``headword`` fact. A frequency list observing a surface a
million times still says nothing about whether it is a word.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import unicodedata
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, TextIO, cast

from yen_tamizh_backend.contracts.lexicon_sources import LexiconSource, LexiconSources
from yen_tamizh_backend.wordsmith.llm_enrich import (
    AUTHORED_SOURCE_ID,
    authored_facts,
    parse_entry,
    themes_of,
)
from yen_tamizh_backend.wordsmith.readers import DEFAULT_CHUNK, read_elements

# Bumped whenever this module would produce different bytes from the same input.
# It sits in every extract's header line beside the source digest, so the skip
# check answers "is this cache still current?" rather than merely "does a file
# exist?".
EXTRACTOR_VERSION = "2026-08-15"

# The typed facts a source can assert about a surface. ``definitionTa`` has no
# producer on disk - no acquired source carries one - and is named here because
# ``llm_enrich`` writes it later through the same channel.
FactKind = Literal[
    "headword",
    "translation",
    "definitionEn",
    "definitionTa",
    "synonym",
    "pos",
    "category",
    "graphemeCount",
    "wordClassEvidence",
]

# A2's leading part-of-speech marker, longest spelling first so "n. pl." is
# never read as "n." and "a.adv" is never read as "a.". This is the source's own
# orthography, so it lives in the reader that knows the source; what the
# canonical tag on the right MEANS is config (``posAliases``).
_A2_POS_SPELLINGS: tuple[tuple[str, str], ...] = (
    ("n. pl.", "n.pl"),
    ("n.pl.", "n.pl"),
    ("n.pl", "n.pl"),
    ("a.adv", "a.adv"),
    ("conj.", "conj"),
    ("adv.", "adv"),
    ("int.", "int"),
    ("art.", "art"),
    ("rel.", "rel"),
    ("prep", "prep"),
    ("pron", "pron"),
    ("n.", "n"),
    ("a.", "a"),
    ("v.", "v"),
)

_HASH_CHUNK = 1 << 16


def normalize(raw: str) -> str:
    """NFC-normalize and trim one raw token.

    NFC because the ezhuthu segmenter's two spellings of the same cluster must
    agree; trimming because leading and trailing whitespace is never part of a
    surface. Nothing else is touched - this is canonicalization, not cleaning.
    """
    return unicodedata.normalize("NFC", raw.strip())


@dataclass(slots=True, frozen=True)
class Observation:
    """One source saw one surface, this many times. Says nothing about word-hood."""

    surface: str
    count: int


@dataclass(slots=True, frozen=True)
class Fact:
    """One source asserted one typed thing about one word."""

    word: str
    attr: FactKind
    value: str
    ordinal: int


Emission = Observation | Fact


@dataclass(slots=True)
class Tally:
    """One source's extraction ledger.

    ``rowsOut + parseRejects == rowsIn`` is the losslessness Oracle: a record
    that produced nothing is COUNTED, never silently dropped. Each extractor
    keeps this ledger itself rather than the caller inferring it from whether
    anything was yielded - the English-Tamil reader closes a synonym run when
    the English headword CHANGES, so an inferring caller would credit the
    previous run's facts to the row that ended it. ``posUnparsed`` and
    ``posRejected`` are reported beside it because a row can lose its part of
    speech while keeping every other fact, and that is a different event from
    losing the row.
    """

    rowsIn: int = 0
    rowsOut: int = 0
    parseRejects: int = 0
    observations: int = 0
    facts: int = 0
    posUnparsed: int = 0
    posRejected: int = 0

    def reconciles(self) -> bool:
        return self.rowsOut + self.parseRejects == self.rowsIn


@dataclass(slots=True)
class SourceResult:
    """What one source's extraction did, for the run summary."""

    id: str
    path: str
    bytes: int
    sha256: str
    out: Path
    tally: Tally = field(default_factory=Tally)
    skipped: bool = False

    def note(self) -> str:
        if self.skipped:
            return f"{self.id}: skipped (extract already current)"
        tally = self.tally
        return (
            f"{self.id}: rowsIn={tally.rowsIn} rowsOut={tally.rowsOut} "
            f"parseRejects={tally.parseRejects} observations={tally.observations} "
            f"facts={tally.facts} posUnparsed={tally.posUnparsed} "
            f"posRejected={tally.posRejected}"
        )


# --------------------------------------------------------------------------
# Alias routing. A raw source tag reaches its destination through config, never
# through a branch in this file: the VOCABULARY is contract, the MAPPING is
# `config/lexicon-sources.json`.
# --------------------------------------------------------------------------


def _route_pos(
    tag: str, word: str, registry: LexiconSources, source_id: str, tally: Tally
) -> Iterator[Fact]:
    """Route one raw POS tag through ``posAliases``.

    A tag with no entry RAISES here rather than at publish. Fowler's rule is
    that failing fast at the boundary means extract, not three stages later, and
    the message names the tag so the fix is one line of config.
    """
    alias = registry.posAliases.get(tag)
    if alias is None:
        raise ValueError(
            f"source {source_id!r}: raw POS tag {tag!r} has no entry in "
            f"posAliases - register it with a destination or an explicit reject "
            f"reason, because a tag with nowhere to go is the silent drop the "
            f"registry exists to prevent"
        )
    if alias.reject is not None:
        tally.posRejected += 1
        return
    for ordinal, part in enumerate(alias.pos or ()):
        yield Fact(word=word, attr="pos", value=part, ordinal=ordinal)
    for ordinal, evidence in enumerate(alias.wordClassEvidence or ()):
        yield Fact(
            word=word, attr="wordClassEvidence", value=evidence, ordinal=ordinal
        )


def _route_category(
    label: str,
    word: str,
    ordinal: int,
    registry: LexiconSources,
    source_id: str,
    tally: Tally,
) -> Iterator[Fact]:
    """Route one raw category label.

    ``posAliases`` is consulted FIRST, because a source label naming a part of
    speech is a fact about the language however the source filed it - the one
    curated themed source files ``Nouns`` as a category, and leaving it there
    would make ``Nouns`` the largest theme in the lexicon.
    """
    if label in registry.posAliases:
        yield from _route_pos(label, word, registry, source_id, tally)
        return
    theme = registry.categoryAliases.get(label)
    if theme is None:
        raise ValueError(
            f"source {source_id!r}: category label {label!r} is in neither "
            f"posAliases nor categoryAliases - a label with no destination is "
            f"a silent drop"
        )
    yield Fact(word=word, attr="category", value=theme, ordinal=ordinal)


# --------------------------------------------------------------------------
# Extractors. One per source SHAPE: the generic one is driven entirely by the
# registry's field mappings, and a source carrying facts those four mappings
# cannot name gets a subclass. See docs/how-to/add-a-lexicon-source.md.
# --------------------------------------------------------------------------


class SourceExtractor:
    """Turns one element into emissions, using only the registry's mappings."""

    def __init__(self, source: LexiconSource, registry: LexiconSources) -> None:
        self.source = source
        self.registry = registry
        self.asserts_wordhood = source.role in ("authority", "authored")

    def feed(self, element: Any, tally: Tally) -> Iterator[Emission]:
        word = self._surface(element)
        if not word:
            tally.parseRejects += 1
            return
        tally.rowsOut += 1
        yield Observation(surface=word, count=self._count(element))
        if self.asserts_wordhood:
            yield Fact(word=word, attr="headword", value=word, ordinal=0)
        yield from self._categories(element, word, tally)
        yield from self._pos(element, word, tally)
        yield from self.extra_facts(element, word)

    def flush(self, tally: Tally) -> Iterator[Emission]:
        """Emissions that only exist once a run of related elements has ended."""
        return iter(())

    def extra_facts(self, element: Any, word: str) -> Iterator[Fact]:
        """Facts the four registry field mappings cannot name. None by default."""
        return iter(())

    # -- the four registry-driven mappings ---------------------------------

    def _surface(self, element: Any) -> str:
        source = self.source
        if source.kind == "delimited":
            columns: Sequence[str] = element
            if source.wordColumn is None or source.wordColumn >= len(columns):
                return ""
            return normalize(columns[source.wordColumn])
        if source.elementKind == "string":
            return normalize(element) if isinstance(element, str) else ""
        if not isinstance(element, dict) or source.wordField is None:
            return ""
        raw = element.get(source.wordField)
        return normalize(raw) if isinstance(raw, str) else ""

    def _count(self, element: Any) -> int:
        source = self.source
        if source.kind == "delimited":
            columns: Sequence[str] = element
            if source.countColumn is None or source.countColumn >= len(columns):
                return 0
            raw = columns[source.countColumn].strip()
            return int(raw) if raw.isdigit() else 0
        if source.countField is None or not isinstance(element, dict):
            return 0
        raw_count = element.get(source.countField)
        if isinstance(raw_count, bool) or not isinstance(raw_count, int):
            return 0
        return max(raw_count, 0)

    def _categories(self, element: Any, word: str, tally: Tally) -> Iterator[Fact]:
        source = self.source
        if source.categoryField is None or not isinstance(element, dict):
            return
        raw = element.get(source.categoryField)
        labels = raw if isinstance(raw, list) else [raw]
        ordinal = 0
        for label in labels:
            if not isinstance(label, str) or not label.strip():
                continue
            for fact in _route_category(
                label.strip(), word, ordinal, self.registry, source.id, tally
            ):
                yield fact
                if fact.attr == "category":
                    ordinal += 1

    def _pos(self, element: Any, word: str, tally: Tally) -> Iterator[Fact]:
        source = self.source
        if source.posField is None or not isinstance(element, dict):
            return
        raw = element.get(source.posField)
        if not isinstance(raw, str) or not raw.strip():
            tally.posUnparsed += 1
            return
        yield from _route_pos(raw.strip(), word, self.registry, source.id, tally)


class _MasterDictionaryExtractor(SourceExtractor):
    """A1: also carries an English translation and its own grapheme count."""

    def extra_facts(self, element: Any, word: str) -> Iterator[Fact]:
        if not isinstance(element, dict):
            return
        english = element.get("en")
        if isinstance(english, str) and english.strip():
            yield Fact(
                word=word, attr="translation", value=normalize(english), ordinal=0
            )
        graphemes = element.get("grapheme_count")
        if isinstance(graphemes, int) and not isinstance(graphemes, bool):
            yield Fact(
                word=word, attr="graphemeCount", value=str(graphemes), ordinal=0
            )


class _ThemedVocabularyExtractor(SourceExtractor):
    """C1: a curated theme plus a clean one-word English pairing."""

    def extra_facts(self, element: Any, word: str) -> Iterator[Fact]:
        if not isinstance(element, dict):
            return
        english = element.get("english")
        if isinstance(english, str) and english.strip():
            yield Fact(
                word=word, attr="translation", value=normalize(english), ordinal=0
            )


class _WiktextractExtractor(SourceExtractor):
    """A7: senses carry English DEFINITIONS and Tamil synonyms.

    Wiktionary's own ``categories`` are maintenance buckets ("Pages with 1
    entry"), not themes, so no ``categoryField`` is registered for this source
    and none is read here. A gloss is a lexicographer's prose, so it lands as
    ``definitionEn`` - store-only evidence - and never as a ``translation``.
    """

    def extra_facts(self, element: Any, word: str) -> Iterator[Fact]:
        if not isinstance(element, dict):
            return
        senses = element.get("senses")
        ordinal = 0
        synonyms: list[str] = []
        for entry in senses if isinstance(senses, list) else ():
            if not isinstance(entry, dict):
                continue
            glosses = entry.get("glosses")
            for gloss in glosses if isinstance(glosses, list) else ():
                if isinstance(gloss, str) and gloss.strip():
                    yield Fact(
                        word=word,
                        attr="definitionEn",
                        value=normalize(gloss),
                        ordinal=ordinal,
                    )
                    ordinal += 1
            synonyms.extend(_synonym_words(entry.get("synonyms")))
        synonyms.extend(_synonym_words(element.get("synonyms")))
        for position, synonym in enumerate(sorted(set(synonyms) - {word})):
            yield Fact(word=word, attr="synonym", value=synonym, ordinal=position)


def _synonym_words(raw: Any) -> Iterator[str]:
    for entry in raw if isinstance(raw, list) else ():
        if isinstance(entry, dict):
            value = entry.get("word")
            if isinstance(value, str) and value.strip():
                yield normalize(value)


class _EnTaDictionaryExtractor(SourceExtractor):
    """A2: one English headword, one part of speech, several Tamil terms.

    Read FORWARD each Tamil term translates to the row's English headword. Read
    SIDEWAYS the terms filed under one (English headword, part of speech) are
    equivalents of each other - a synonym set. The part of speech is half the
    key: without it a noun sense and a verb sense of the same English word
    collapse into one set.

    The grouping is a RUN over the source's own sort order, not a whole-file
    index. Measured on all 56,856 rows: 54,928 distinct English headwords in
    54,934 runs, so six repeat non-adjacently and produce two smaller sets
    instead of one. That costs a streaming reader; a whole-file group-by would
    cost peak memory proportional to the source.
    """

    def __init__(self, source: LexiconSource, registry: LexiconSources) -> None:
        super().__init__(source, registry)
        self._english: str | None = None
        self._groups: dict[str | None, list[str]] = {}

    def feed(self, element: Any, tally: Tally) -> Iterator[Emission]:
        if not isinstance(element, dict):
            tally.parseRejects += 1
            return
        english = element.get("eng")
        tamil = element.get("tamil")
        if not isinstance(english, str) or not isinstance(tamil, str):
            tally.parseRejects += 1
            return
        if english != self._english:
            yield from self._close_run()
            self._english = english
        tag, terms = _split_a2_entry(tamil)
        if not terms:
            tally.parseRejects += 1
            return
        tally.rowsOut += 1
        if tag is None:
            tally.posUnparsed += 1
        translation = normalize(english)
        group = self._groups.setdefault(tag, [])
        for term in terms:
            yield Observation(surface=term, count=0)
            yield Fact(word=term, attr="headword", value=term, ordinal=0)
            yield Fact(word=term, attr="translation", value=translation, ordinal=0)
            if tag is not None:
                yield from _route_pos(tag, term, self.registry, self.source.id, tally)
            if term not in group:
                group.append(term)

    def flush(self, tally: Tally) -> Iterator[Emission]:
        yield from self._close_run()

    def _close_run(self) -> Iterator[Fact]:
        for terms in self._groups.values():
            if len(terms) < 2:
                continue
            ordered = sorted(set(terms))
            for term in ordered:
                peers = [peer for peer in ordered if peer != term]
                for position, peer in enumerate(peers):
                    yield Fact(
                        word=term, attr="synonym", value=peer, ordinal=position
                    )
        self._groups = {}


def _split_a2_entry(tamil: str) -> tuple[str | None, list[str]]:
    """Split one A2 ``tamil`` value into its POS tag and its Tamil terms.

    The value is a leading ASCII marker - an optional homograph index, a part of
    speech, sometimes an editorial parenthetical or a page reference - followed
    by a comma-separated Tamil list. The marker ends at the first non-ASCII
    character, which is a property of the data rather than a guess: the Tamil
    side is Tamil.

    A row whose marker holds no part of speech (2,700 of 56,856, of which 2,525
    have no marker at all) keeps every other fact and loses only its ``pos``.
    Discarding its translations because its prefix was punctuation would be
    EXTRACT filtering, which this stage does not do.
    """
    cut = len(tamil)
    for index, character in enumerate(tamil):
        if ord(character) > 0x7F:
            cut = index
            break
    head = tamil[:cut].lstrip()
    if head[:1] == "-" and head[1:2].isdigit():
        head = head.lstrip("-0123456789").lstrip()
    tag: str | None = None
    for spelling, canonical in _A2_POS_SPELLINGS:
        if head.startswith(spelling):
            tag = canonical
            break
    terms = [
        normalized
        for piece in tamil[cut:].split(",")
        if (normalized := normalize(piece).rstrip(".").strip())
    ]
    return tag, terms


class _AuthoredEntriesExtractor(SourceExtractor):
    """The authored source: meanings, synonyms, translations, POS and themes.

    Its bytes are written by the agent executing the pipeline rather than
    acquired from a third party, so unlike every other reader this one may hold
    the file to a shape: ``llm_enrich`` validates each row and raises naming the
    line and the rule it broke. A row this reader accepts is one a reviewer
    could have checked in the diff.

    The row's ``pos`` and ``categories`` bypass ``posAliases`` and
    ``categoryAliases`` deliberately. Those maps translate a third-party
    source's own orthography into the closed vocabularies; an authored row
    writes the closed vocabularies natively, and the validator - not a map - is
    what refuses anything outside them.
    """

    def __init__(self, source: LexiconSource, registry: LexiconSources) -> None:
        super().__init__(source, registry)
        self._themes = themes_of(registry)
        self._previous: str | None = None
        self._line = 0

    def feed(self, element: Any, tally: Tally) -> Iterator[Emission]:
        self._line += 1
        entry = parse_entry(
            element, self._themes, f"{self.source.path}:{self._line}", self._previous
        )
        self._previous = entry.word
        tally.rowsOut += 1
        yield Observation(surface=entry.word, count=0)
        if self.asserts_wordhood:
            yield Fact(word=entry.word, attr="headword", value=entry.word, ordinal=0)
        for attr, value, ordinal in authored_facts(entry):
            yield Fact(
                word=entry.word,
                attr=cast(FactKind, attr),
                value=value,
                ordinal=ordinal,
            )


_EXTRACTORS: dict[str, type[SourceExtractor]] = {
    "master-dictionary": _MasterDictionaryExtractor,
    "themed-vocabulary": _ThemedVocabularyExtractor,
    "wiktextract-ta": _WiktextractExtractor,
    "en-ta-dictionary": _EnTaDictionaryExtractor,
    AUTHORED_SOURCE_ID: _AuthoredEntriesExtractor,
}


def extractor_for(source: LexiconSource, registry: LexiconSources) -> SourceExtractor:
    """The extractor for one source: the generic one unless its shape needs more."""
    return _EXTRACTORS.get(source.id, SourceExtractor)(source, registry)


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------


def emit_from(
    handle: TextIO,
    source: LexiconSource,
    registry: LexiconSources,
    tally: Tally,
    chunk: int = DEFAULT_CHUNK,
) -> Iterator[Emission]:
    """Stream one open source's emissions, filling ``tally`` as it goes.

    Split out from ``emit`` so the memory predicate can hand it a handle over
    an already-loaded document: CPython's own text-I/O layer allocates a 64 KiB
    decode block of its own, which at fixture scale is larger than everything
    this stage holds and would otherwise be the thing being measured.
    """
    extractor = extractor_for(source, registry)
    for element in read_elements(handle, source, chunk):
        tally.rowsIn += 1
        yield from extractor.feed(element, tally)
    yield from extractor.flush(tally)


def emit(
    path: Path,
    source: LexiconSource,
    registry: LexiconSources,
    tally: Tally,
    chunk: int = DEFAULT_CHUNK,
) -> Iterator[Emission]:
    """Stream one source file's emissions."""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        yield from emit_from(handle, source, registry, tally, chunk)


def sha256_of(path: Path) -> tuple[str, int]:
    """A file's digest and size, read in chunks.

    Local rather than borrowed from ``corpus/artifact.py``: the corpus layer is
    retired in row 13 and a new package must not be wired to it on the way out.
    """
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while piece := handle.read(_HASH_CHUNK):
            digest.update(piece)
            size += len(piece)
    return digest.hexdigest(), size


def render(payload: dict[str, Any]) -> str:
    """One extract line: compact, deterministic, and its own record type."""
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def header_of(source: LexiconSource, digest: str, size: int) -> dict[str, Any]:
    """The first line of an extract: what was read, and by which extractor."""
    return {
        "record": "header",
        "sourceId": source.id,
        "role": source.role,
        "kind": source.kind,
        "path": source.path,
        "bytes": size,
        "sha256": digest,
        "precedence": source.precedence,
        "extractorVersion": EXTRACTOR_VERSION,
    }


def is_current(out: Path, digest: str) -> bool:
    """Whether ``out`` was already produced from these bytes by this extractor.

    The comparison is against the extract's OWN header line. It deliberately
    does not consult the published lexicon: that is stage 4's output and does
    not exist yet, and making stage 1 read stage 4's artifact is a cycle.
    """
    if not out.exists():
        return False
    with out.open("r", encoding="utf-8") as handle:
        first = handle.readline()
    if not first.strip():
        return False
    try:
        header: Any = json.loads(first)
    except ValueError:
        return False
    return (
        isinstance(header, dict)
        and header.get("record") == "header"
        and header.get("sha256") == digest
        and header.get("extractorVersion") == EXTRACTOR_VERSION
    )


def extract_source(
    source: LexiconSource,
    registry: LexiconSources,
    repo_root: Path,
    chunk: int = DEFAULT_CHUNK,
    force: bool = False,
) -> SourceResult:
    """Extract one source into ``<lexiconRoot>/cache/extracts/<id>.jsonl``."""
    path = repo_root / source.path
    if not path.exists():
        raise FileNotFoundError(
            f"source {source.id!r} is not at {source.path} - the raw bytes are "
            f"gitignored; see datasets/lexicon/sources/README.md to repopulate them"
        )
    digest, size = sha256_of(path)
    if digest != source.sha256:
        raise ValueError(
            f"source {source.id!r} at {source.path} hashes to {digest}, but the "
            f"registry records {source.sha256}. Record the new value and say why "
            f"in the same commit - every downstream artifact points at the old one"
        )
    out = repo_root / registry.lexiconRoot / "cache" / "extracts" / f"{source.id}.jsonl"
    result = SourceResult(
        id=source.id, path=source.path, bytes=size, sha256=digest, out=out
    )
    if not force and is_current(out, digest):
        result.skipped = True
        return result

    out.parent.mkdir(parents=True, exist_ok=True)
    # Written aside and renamed, so a crashed run never leaves a truncated file
    # that the header check would then accept as current.
    staging = out.with_name(out.name + ".partial")
    tally = result.tally
    with staging.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(header_of(source, digest, size)))
        for emission in emit(path, source, registry, tally, chunk):
            if isinstance(emission, Observation):
                tally.observations += 1
                handle.write(
                    render(
                        {
                            "record": "observation",
                            "surface": emission.surface,
                            "count": emission.count,
                        }
                    )
                )
            else:
                tally.facts += 1
                handle.write(
                    render(
                        {
                            "record": "fact",
                            "word": emission.word,
                            "attr": emission.attr,
                            "value": emission.value,
                            "ordinal": emission.ordinal,
                        }
                    )
                )
        handle.write(
            render(
                {
                    "record": "summary",
                    "rowsIn": tally.rowsIn,
                    "rowsOut": tally.rowsOut,
                    "parseRejects": tally.parseRejects,
                    "observations": tally.observations,
                    "facts": tally.facts,
                    "posUnparsed": tally.posUnparsed,
                    "posRejected": tally.posRejected,
                }
            )
        )
    if not tally.reconciles():
        staging.unlink(missing_ok=True)
        raise ValueError(
            f"source {source.id!r}: {tally.rowsOut} rows out plus "
            f"{tally.parseRejects} parse rejects is not {tally.rowsIn} rows in"
        )
    os.replace(staging, out)
    return result


def extract(
    registry: LexiconSources,
    repo_root: Path,
    only: str | None = None,
    chunk: int = DEFAULT_CHUNK,
    force: bool = False,
) -> list[SourceResult]:
    """Extract every enabled source, or just the one ``only`` names."""
    wanted = [
        source
        for source in registry.sources
        if source.enabled and (only is None or source.id == only)
    ]
    if only is not None and not wanted:
        known = ", ".join(source.id for source in registry.sources)
        raise ValueError(f"no enabled source {only!r} in the registry - have: {known}")
    if not wanted:
        raise ValueError("the lexicon registry has no enabled source")
    return [
        extract_source(source, registry, repo_root, chunk, force) for source in wanted
    ]


def load_registry(path: Path) -> LexiconSources:
    """Load and validate ``config/lexicon-sources.json``."""
    return LexiconSources.model_validate_json(path.read_text(encoding="utf-8"))


def _repo_root() -> Path:
    # extract.py -> wordsmith -> yen_tamizh_backend -> backend -> <repo root>
    return Path(__file__).resolve().parents[3]


def main() -> None:
    root = _repo_root()
    parser = argparse.ArgumentParser(description="Extract one lexicon source, or all.")
    parser.add_argument(
        "--registry",
        type=Path,
        default=root / "config" / "lexicon-sources.json",
        help="the lexicon source registry to read",
    )
    parser.add_argument("--source", default=None, help="extract only this source id")
    parser.add_argument(
        "--chunk",
        type=int,
        default=DEFAULT_CHUNK,
        help="reader buffer size in bytes (default 64 KiB)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-extract even when the cached extract matches the source digest",
    )
    args = parser.parse_args()

    for result in extract(
        load_registry(args.registry), root, args.source, args.chunk, args.force
    ):
        print(result.note())


if __name__ == "__main__":
    main()
