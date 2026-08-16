"""Tests for the wordsmith EXTRACT stage (Row 5).

Real committed fixtures throughout, no mocks (Holy Law #7). The raw sources are
gitignored, so anything that needs their bytes SKIPS when they are absent - a
gate that cannot pass in CI is a broken gate, not a finding.

Four things are proven:

1. **The registry is honest** - every entry agrees with the row-4 acquisition
   ledger byte for byte, every raw tag any reader can produce has an alias
   entry, and the two sources with no readable bytes are represented the way
   their situation actually is.
2. **Each reader is deterministic and lossless** - a second run over the same
   fixture produces identical bytes, and ``rowsOut + parseRejects == rowsIn``
   against a record count computed by an INDEPENDENT parse (``json.loads`` of
   the whole document, which the streaming reader may never do).
3. **The element rule holds** - the yielded sequence is identical for every
   buffer size from one byte upward, and an array holding a bare number raises
   instead of coercing.
4. **Peak memory does not track file size** - a 10x fixture peaks within 1.2x
   of its 1x sibling, measured with ``tracemalloc`` rather than an absolute
   ceiling that a small fixture could never breach.
"""

from __future__ import annotations

import csv
import gc
import io
import json
import re
import shutil
import tracemalloc
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import pytest

from _lexicon_workspace import source_bytes
from yen_tamizh_backend.contracts.lexicon_sources import LexiconSource, LexiconSources
from yen_tamizh_backend.wordsmith.extract import (
    EXTRACTOR_VERSION,
    Observation,
    Tally,
    emit,
    emit_from,
    extract,
    extract_source,
    load_registry,
    normalize,
    sha256_of,
)
from yen_tamizh_backend.wordsmith.llm_enrich import AUTHORED_SOURCE_ID
from yen_tamizh_backend.wordsmith.readers import iter_delimited_quoted, iter_json_array

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = _REPO_ROOT / "config" / "lexicon-sources.json"
_LEDGER = _REPO_ROOT / "datasets" / "lexicon" / "sources" / "README.md"
_FIXTURES = _REPO_ROOT / "datasets" / "fixtures" / "lexicon"

REGISTRY = load_registry(_REGISTRY_PATH)
SOURCES = list(REGISTRY.sources)
# Every source EXCEPT the authored one, which is not acquired: its bytes are
# committed, so it has no ledger row and no 1x / 10x fixture pair to slice.
ACQUIRED = [source for source in SOURCES if source.id != AUTHORED_SOURCE_ID]

# The chunk sizes the Oracle names. One byte forces a split inside every
# element, which is the case a whole-document parse can never fail on.
CHUNKS = (1, 2, 3, 7, 64, 4096, 65536)

# Small enough that both fixture scales reach the reader's steady state: at a
# larger buffer a 9 KB fixture fits in two reads and never gets there, so the
# ratio would measure warm-up rather than growth.
SCALING_CHUNK = 2048

# The whole-file census row 4 recorded, and the only tags any reader can emit.
# An entry missing from `posAliases` is a hard failure at extract, so this list
# is what keeps the config exhaustive as sources change.
A7_POS_TAGS = (
    "noun", "verb", "name", "adj", "adv", "pron", "num", "character", "suffix",
    "intj", "particle", "postp", "proverb", "phrase", "conj", "det", "prefix",
    "symbol", "interfix", "contraction",
)
A2_POS_TAGS = (
    "n", "a", "v", "n.pl", "adv", "int", "pron", "prep", "conj", "a.adv",
    "art", "rel",
)
C1_POS_TAGS = ("Nouns", "Verbs", "Adjectives")
A1_CATEGORY_TAGS = ("nouns", "trees", "flowers", "birds", "animals")


def _ledger_rows() -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line in _LEDGER.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| "):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 9 or not re.fullmatch(r"[A-F]\d+", cells[0]):
            continue
        rows[cells[1]] = {
            "number": cells[0],
            "role": cells[2],
            "origin": cells[3],
            "path": cells[4],
            "bytes": cells[5],
            "sha256": cells[7].strip("`"),
            "status": cells[8],
        }
    return rows


LEDGER = _ledger_rows()


def fixture_for(source: LexiconSource, scale: str) -> Path:
    """The committed bytes for one source at one scale.

    A fixture slice exists because a raw source is gitignored. The authored
    source is not gitignored, so it has no slice at either scale and is only
    ever exercised against its real file - which is why the ten-times predicate
    below is parametrized over ACQUIRED.
    """
    if source.id == AUTHORED_SOURCE_ID:
        return source_bytes(_REPO_ROOT, _FIXTURES, source)
    return _FIXTURES / f"{source.id}.{scale}{Path(source.path).suffix}"


def probe(
    source: LexiconSource, scale: str, workspace: Path
) -> tuple[LexiconSource, LexiconSources, Path]:
    """A registry entry pointing at a committed fixture, inside ``workspace``.

    The fixture is copied rather than referenced so every output lands in the
    temporary tree, and the entry is re-VALIDATED rather than patched in place,
    so a probe is always a legal registry entry.
    """
    fixture = fixture_for(source, scale)
    staged = workspace / "sources" / fixture.name
    staged.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(fixture, staged)
    digest, size = sha256_of(staged)
    entry = LexiconSource.model_validate(
        source.model_dump(exclude_none=True)
        | {
            "path": f"sources/{fixture.name}",
            "sha256": digest,
            "bytes": size,
            "enabled": True,
        }
    )
    registry = LexiconSources.model_validate(
        REGISTRY.model_dump(exclude_none=True)
        | {"lexiconRoot": "out", "sources": [entry.model_dump(exclude_none=True)]}
    )
    return entry, registry, staged


def count_records(source: LexiconSource, path: Path) -> int:
    """The record count from an INDEPENDENT whole-document parse.

    This is the half of the losslessness Oracle the streaming reader is not
    allowed to compute for itself.
    """
    raw = path.read_text(encoding="utf-8")
    if source.kind == "delimited":
        lines = [line for line in raw.splitlines() if line.strip()]
        return max(len(lines) - 1, 0) if source.hasHeader else len(lines)
    if source.kind == "delimited-quoted":
        # A whole-document parse, which is exactly what the streaming reader is
        # not allowed to be - and what makes the count independent of it. A
        # quoted field may hold a newline, so a record is not a line.
        rows = [
            row
            for row in csv.reader(io.StringIO(raw), delimiter=source.delimiter or "\t")
            if any(field.strip() for field in row)
        ]
        return max(len(rows) - 1, 0) if source.hasHeader else len(rows)
    if source.kind == "jsonl":
        return len([line for line in raw.splitlines() if line.strip()])
    if source.kind == "mediawiki-xml":
        root = ElementTree.fromstring(raw)
        return len(
            [
                page
                for page in root.findall("{*}page")
                if page.findtext("{*}ns") == str(source.pageNamespace)
            ]
        )
    document: Any = json.loads(raw)
    array = document if source.rootKey is None else document[source.rootKey]
    return len(array)


# --------------------------------------------------------------------------
# 1. The registry is honest
# --------------------------------------------------------------------------


def test_the_registry_validates_and_carries_the_row_three_stamp() -> None:
    assert REGISTRY.version == "2026-08-16T22:00"
    assert REGISTRY.changelog[0].version == REGISTRY.version
    assert REGISTRY.lexiconRoot == "datasets/lexicon"
    assert REGISTRY.outputs == ["ndjson"]


@pytest.mark.parametrize("source", ACQUIRED, ids=lambda source: source.id)
def test_every_entry_agrees_with_the_acquisition_ledger(source: LexiconSource) -> None:
    row = LEDGER[source.id]
    assert source.role == row["role"]
    assert source.path == row["path"]
    assert source.bytes == int(row["bytes"])
    assert source.sha256 == row["sha256"]
    assert source.origin == row["origin"]


def test_the_authored_source_is_committed_rather_than_acquired() -> None:
    # The ledger records ACQUISITION - where third-party bytes came from and
    # what they hashed to when they were fetched. The authored source was not
    # fetched from anywhere, so a ledger row would be describing an event that
    # never happened. Its bytes are in the repository instead, which is a
    # stronger check than a recorded digest: the digest is verified against the
    # real file on every run.
    entry = next(source for source in SOURCES if source.id == AUTHORED_SOURCE_ID)
    assert entry.id not in LEDGER
    assert entry.role == "authored"
    path = _REPO_ROOT / entry.path
    digest, size = sha256_of(path)
    assert size == entry.bytes
    assert digest == entry.sha256


def test_every_acquired_ledger_source_is_registered_and_the_unacquired_one_is_not() -> (
    None
):
    registered = {source.id for source in ACQUIRED}
    acquired = {name for name, row in LEDGER.items() if row["status"] != "NOT ACQUIRED"}
    assert registered == acquired
    # A6 has no bytes, so it has no path and no digest to record. It stays in
    # the ledger, which is where "sought and not found" belongs; a registry
    # entry would have to invent a sha256, and an invented digest is a lie.
    assert LEDGER["madras-lexicon"]["status"] == "NOT ACQUIRED"
    assert "madras-lexicon" not in registered


def test_the_known_bad_source_is_registered_and_disabled() -> None:
    # E1 differs from A6 in the one way that matters: its bytes exist, so it can
    # be described truthfully and switched off.
    entry = next(source for source in SOURCES if source.id == "azhiyasudargal")
    assert entry.enabled is False
    assert entry.note is not None
    assert all(source.enabled for source in SOURCES if source.id != "azhiyasudargal")


def test_precedence_is_a_total_order_over_every_source() -> None:
    ranks = [source.precedence for source in SOURCES]
    assert sorted(ranks) == list(range(len(SOURCES)))


@pytest.mark.parametrize(
    "tag", sorted(set(A7_POS_TAGS + A2_POS_TAGS + C1_POS_TAGS + A1_CATEGORY_TAGS[:1]))
)
def test_every_censused_pos_tag_has_an_alias_entry(tag: str) -> None:
    assert tag in REGISTRY.posAliases


@pytest.mark.parametrize("label", A1_CATEGORY_TAGS[1:])
def test_every_censused_category_label_routes(label: str) -> None:
    assert label in REGISTRY.categoryAliases or label in REGISTRY.posAliases


def test_no_alias_routes_a_category_source_to_word_hood() -> None:
    # `wordClassEvidence` is deliberately narrower than `wordClass`: posAliases
    # is config, so on the wider type one line here would let a category source
    # assert that a surface is a headword.
    for alias in REGISTRY.posAliases.values():
        assert "headword" not in (alias.wordClassEvidence or ())


# --------------------------------------------------------------------------
# 2. Determinism and losslessness, over every committed fixture
# --------------------------------------------------------------------------


@pytest.mark.parametrize("source", SOURCES, ids=lambda source: source.id)
def test_a_reader_is_byte_deterministic_across_runs(
    source: LexiconSource, tmp_path: Path
) -> None:
    entry, registry, _ = probe(source, "1x", tmp_path)
    first = extract_source(entry, registry, tmp_path, force=True)
    once = first.out.read_bytes()
    again = extract_source(entry, registry, tmp_path, force=True)
    assert again.out.read_bytes() == once
    assert first.tally == again.tally


@pytest.mark.parametrize("source", ACQUIRED, ids=lambda source: source.id)
@pytest.mark.parametrize("scale", ["1x", "10x"])
def test_the_extract_is_lossless(
    source: LexiconSource, scale: str, tmp_path: Path
) -> None:
    entry, registry, staged = probe(source, scale, tmp_path)
    result = extract_source(entry, registry, tmp_path, force=True)
    tally = result.tally
    assert tally.rowsOut + tally.parseRejects == tally.rowsIn
    assert tally.rowsIn == count_records(entry, staged)


@pytest.mark.parametrize("source", SOURCES, ids=lambda source: source.id)
def test_the_extract_file_is_a_header_then_records_then_a_summary(
    source: LexiconSource, tmp_path: Path
) -> None:
    entry, registry, _ = probe(source, "1x", tmp_path)
    result = extract_source(entry, registry, tmp_path, force=True)
    lines = result.out.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    summary = json.loads(lines[-1])
    assert header["record"] == "header"
    assert header["sha256"] == entry.sha256
    assert header["extractorVersion"] == EXTRACTOR_VERSION
    assert header["role"] == entry.role
    assert summary["record"] == "summary"
    assert summary["rowsIn"] == result.tally.rowsIn
    counted = {"observation": 0, "fact": 0}
    for line in lines[1:-1]:
        record = json.loads(line)
        assert record["record"] in counted
        counted[record["record"]] += 1
    assert counted["observation"] == summary["observations"]
    assert counted["fact"] == summary["facts"]


@pytest.mark.parametrize("source", SOURCES, ids=lambda source: source.id)
def test_only_an_authority_asserts_word_hood(
    source: LexiconSource, tmp_path: Path
) -> None:
    entry, registry, _ = probe(source, "1x", tmp_path)
    result = extract_source(entry, registry, tmp_path, force=True)
    headwords = sum(
        1
        for line in result.out.read_text(encoding="utf-8").splitlines()[1:-1]
        if json.loads(line).get("attr") == "headword"
    )
    # `authored` sits beside `authority` here and nowhere else: row 4 decision 1
    # lets exactly those two roles assert word-hood. What keeps the authored
    # source from being a way to smuggle one in is row 12's gate, which refuses
    # to count an authored attestation until a human has reviewed the row.
    if entry.role in ("authority", "authored"):
        assert headwords > 0
    else:
        assert headwords == 0


def test_the_run_skips_a_source_whose_extract_is_already_current(
    tmp_path: Path,
) -> None:
    source = next(entry for entry in SOURCES if entry.id == "wiki")
    entry, registry, _ = probe(source, "1x", tmp_path)
    first = extract_source(entry, registry, tmp_path)
    assert first.skipped is False
    assert extract_source(entry, registry, tmp_path).skipped is True
    # The check is against the extract's OWN header, so corrupting the recorded
    # digest is enough to make the stage run again - no other stage's artifact
    # is consulted, which is what keeps stage 1 free of a cycle.
    lines = first.out.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    header["sha256"] = "0" * 64
    first.out.write_text(
        "\n".join([json.dumps(header)] + lines[1:]) + "\n", encoding="utf-8"
    )
    assert extract_source(entry, registry, tmp_path).skipped is False


def test_a_source_whose_bytes_no_longer_match_the_registry_raises(
    tmp_path: Path,
) -> None:
    source = next(entry for entry in SOURCES if entry.id == "wiki")
    entry, registry, staged = probe(source, "1x", tmp_path)
    staged.write_text("mismatched,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="registry records"):
        extract_source(entry, registry, tmp_path)


def test_a_disabled_source_is_never_read(tmp_path: Path) -> None:
    source = next(entry for entry in SOURCES if entry.id == "azhiyasudargal")
    entry, registry, _ = probe(source, "1x", tmp_path)
    off = LexiconSource.model_validate(
        entry.model_dump(exclude_none=True) | {"enabled": False}
    )
    registry = LexiconSources.model_validate(
        registry.model_dump(exclude_none=True)
        | {"sources": [off.model_dump(exclude_none=True)]}
    )
    with pytest.raises(ValueError, match="no enabled source"):
        extract(registry, tmp_path)


# --------------------------------------------------------------------------
# 3. The self-terminating element rule
# --------------------------------------------------------------------------

JSON_ARRAY_SOURCES = [source for source in SOURCES if source.kind == "json-array"]
# Every reader that takes a buffer size, not only the JSON ones: the property
# is the reader's, and a new streaming reader inherits the predicate rather
# than being trusted.
BUFFERED_SOURCES = [
    source for source in SOURCES if source.kind in ("json-array", "mediawiki-xml")
]


@pytest.mark.parametrize(
    "source", BUFFERED_SOURCES, ids=lambda source: source.id
)
def test_the_yielded_sequence_is_identical_at_every_buffer_size(
    source: LexiconSource, tmp_path: Path
) -> None:
    entry, registry, staged = probe(source, "1x", tmp_path)
    expected: list[str] | None = None
    for chunk in CHUNKS:
        tally = Tally()
        surfaces = [
            emission.surface
            for emission in emit(staged, entry, registry, tally, chunk)
            if isinstance(emission, Observation)
        ]
        if expected is None:
            expected = surfaces
            assert expected
        assert surfaces == expected, f"buffer size {chunk} changed the sequence"


def _array(text: str, root_key: str | None, kind: str) -> list[Any]:
    return list(iter_json_array(io.StringIO(text), root_key, kind, chunk=1))  # type: ignore[arg-type]


def test_a_root_array_of_strings_reads_at_one_byte_a_time() -> None:
    assert _array('["a", "b]c", "d"]', None, "string") == ["a", "b]c", "d"]


def test_a_bare_number_element_raises_rather_than_coercing() -> None:
    with pytest.raises(ValueError, match="self-terminating"):
        _array("[12345]", None, "string")
    with pytest.raises(ValueError, match="self-terminating"):
        _array('{"data": [12345]}', "data", "object")


@pytest.mark.parametrize("literal", ["true", "false", "null"])
def test_the_json_literals_are_refused_even_though_they_raise_on_truncation(
    literal: str,
) -> None:
    # They cannot be a word, so admitting them would only postpone the failure.
    with pytest.raises(ValueError, match="self-terminating"):
        _array(f"[{literal}]", None, "string")


def test_a_document_whose_root_is_not_an_array_raises() -> None:
    with pytest.raises(ValueError, match="document root"):
        _array('{"data": ["a"]}', None, "string")


def test_a_missing_root_key_raises_rather_than_yielding_nothing() -> None:
    with pytest.raises(ValueError, match="no array found under key"):
        _array('{"other": ["a"]}', "data", "string")


def test_an_unterminated_array_raises() -> None:
    with pytest.raises(ValueError, match="unterminated"):
        _array('["a", "b"', None, "string")


# --------------------------------------------------------------------------
# 4. Peak memory does not track file size
# --------------------------------------------------------------------------


def _peak_bytes(path: Path, source: LexiconSource, registry: LexiconSources) -> int:
    """Peak traced bytes for reading one document, the I/O layer excluded.

    The document is loaded into a ``StringIO`` BEFORE tracing starts, for one
    measured reason: CPython's own ``TextIOWrapper`` allocates a decode block
    that grows to about 64 KiB, which at fixture scale is larger than
    everything this stage holds. Measured against a file handle, a bare
    ``while handle.read(4096)`` loop that discards every byte shows the same
    145 KB -> 192 KB growth the reader does, so the number would be the
    interpreter's, not the reader's. Fed from memory, only what the reader
    allocates is traced - and a reader that called ``json.load`` would peak at
    document size and fail this by a factor of ten.
    """
    handle = io.StringIO(path.read_text(encoding="utf-8"))
    gc.collect()
    tracemalloc.start()
    tracemalloc.reset_peak()
    tally = Tally()
    for _ in emit_from(handle, source, registry, tally, SCALING_CHUNK):
        pass
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return peak


@pytest.mark.parametrize("source", ACQUIRED, ids=lambda source: source.id)
def test_a_ten_times_larger_fixture_peaks_within_a_fifth_more(
    source: LexiconSource,
) -> None:
    small = fixture_for(source, "1x")
    large = fixture_for(source, "10x")
    small_peak = _peak_bytes(small, source, REGISTRY)
    large_peak = _peak_bytes(large, source, REGISTRY)
    assert large.stat().st_size > small.stat().st_size
    assert large_peak <= small_peak * 1.2, (
        f"{source.id}: peak grew from {small_peak} to {large_peak} bytes while the "
        f"input grew {small.stat().st_size} -> {large.stat().st_size}"
    )


# --------------------------------------------------------------------------
# 5. The per-source readers
# --------------------------------------------------------------------------


def _facts(text: str, attr: str) -> list[dict[str, Any]]:
    return [
        record
        for line in text.splitlines()[1:-1]
        if (record := json.loads(line)).get("attr") == attr
    ]


def test_the_english_tamil_dictionary_reads_forward_and_sideways(
    tmp_path: Path,
) -> None:
    source = next(entry for entry in SOURCES if entry.id == "en-ta-dictionary")
    entry, registry, _ = probe(source, "1x", tmp_path)
    text = extract_source(entry, registry, tmp_path, force=True).out.read_text(
        encoding="utf-8"
    )
    forward = _facts(text, "translation")
    sideways = _facts(text, "glossPeer")
    assert forward and sideways
    # Read forward: the row "n. <a>, <b>." gives both Tamil terms the same
    # English headword. Read sideways: each shares that English gloss with the
    # other - co-membership of a translation list, which is NOT synonymy and so
    # is never a `synonym` fact.
    first = next(record for record in forward if record["value"] == "A B C")
    peers = {
        record["value"] for record in sideways if record["word"] == first["word"]
    }
    assert peers
    assert first["word"] not in peers
    assert _facts(text, "synonym") == [], (
        "a bilingual dictionary read sideways asserts no same-language "
        "equivalence, so it must produce no synonym fact"
    )


def test_the_synonym_key_is_the_headword_AND_the_part_of_speech(
    tmp_path: Path,
) -> None:
    # Two senses of one English headword, one noun and one verb. Grouping on the
    # headword alone would make them synonyms of each other, which they are not.
    source = next(entry for entry in SOURCES if entry.id == "en-ta-dictionary")
    staged = tmp_path / "sources" / "split.json"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(
        json.dumps(
            [
                {"tamil": "-1 n. \u0b85\u0b9f\u0bc8.", "eng": "bank"},
                {"tamil": "-2 v. \u0b86\u0b9f\u0bc1.", "eng": "bank"},
            ]
        ),
        encoding="utf-8",
    )
    digest, size = sha256_of(staged)
    entry = LexiconSource.model_validate(
        source.model_dump(exclude_none=True)
        | {"path": "sources/split.json", "sha256": digest, "bytes": size}
    )
    registry = LexiconSources.model_validate(
        REGISTRY.model_dump(exclude_none=True)
        | {"lexiconRoot": "out", "sources": [entry.model_dump(exclude_none=True)]}
    )
    text = extract_source(entry, registry, tmp_path, force=True).out.read_text(
        encoding="utf-8"
    )
    assert _facts(text, "glossPeer") == []
    assert {record["value"] for record in _facts(text, "pos")} == {"noun", "verb"}


def test_a_group_flush_is_not_credited_to_the_row_that_ended_it(
    tmp_path: Path,
) -> None:
    # The gloss-peer run closes when the English headword CHANGES, so its facts
    # are emitted while the NEXT row is being read. A row that produces nothing
    # of its own must still count as a parse reject - measured on the real
    # source, inferring "did this row produce anything" from the yields
    # under-counted the rejects by 8 of 15.
    source = next(entry for entry in SOURCES if entry.id == "en-ta-dictionary")
    staged = tmp_path / "sources" / "boundary.json"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(
        json.dumps(
            [
                {"tamil": "n. \u0b85\u0b9f\u0bc8, \u0b86\u0b9f\u0bc1.", "eng": "one"},
                {"tamil": "-1.0", "eng": "two"},
            ]
        ),
        encoding="utf-8",
    )
    digest, size = sha256_of(staged)
    entry = LexiconSource.model_validate(
        source.model_dump(exclude_none=True)
        | {"path": "sources/boundary.json", "sha256": digest, "bytes": size}
    )
    registry = LexiconSources.model_validate(
        REGISTRY.model_dump(exclude_none=True)
        | {"lexiconRoot": "out", "sources": [entry.model_dump(exclude_none=True)]}
    )
    result = extract_source(entry, registry, tmp_path, force=True)
    assert result.tally.rowsIn == 2
    assert result.tally.rowsOut == 1
    assert result.tally.parseRejects == 1
    assert _facts(result.out.read_text(encoding="utf-8"), "glossPeer")


def test_the_blanket_category_tag_yields_no_part_of_speech(tmp_path: Path) -> None:
    # The curated master dictionary stamps `nouns` on 99.8 percent of its rows,
    # verbs included, so it is registered as a reject and counted rather than
    # published as a fact about the language.
    source = next(entry for entry in SOURCES if entry.id == "master-dictionary")
    entry, registry, _ = probe(source, "1x", tmp_path)
    result = extract_source(entry, registry, tmp_path, force=True)
    text = result.out.read_text(encoding="utf-8")
    assert _facts(text, "pos") == []
    assert result.tally.posRejected == result.tally.rowsIn
    assert {record["value"] for record in _facts(text, "category")} <= {
        "animals",
        "birds",
        "flowers",
        "trees",
    }


def test_wiktionary_senses_become_definitions_and_synonyms(tmp_path: Path) -> None:
    source = next(entry for entry in SOURCES if entry.id == "wiktextract-ta")
    entry, registry, _ = probe(source, "1x", tmp_path)
    text = extract_source(entry, registry, tmp_path, force=True).out.read_text(
        encoding="utf-8"
    )
    # A gloss is a lexicographer's prose, so it is store-only evidence and never
    # a published one-word translation.
    assert _facts(text, "definitionEn")
    assert _facts(text, "synonym")
    assert _facts(text, "translation") == []


def test_an_unregistered_raw_tag_fails_at_extract_not_at_publish(
    tmp_path: Path,
) -> None:
    source = next(entry for entry in SOURCES if entry.id == "wiktextract-ta")
    staged = tmp_path / "sources" / "unknown.jsonl"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(
        json.dumps({"word": "\u0b85\u0b9f\u0bc8", "pos": "romanization"}) + "\n",
        encoding="utf-8",
    )
    digest, size = sha256_of(staged)
    entry = LexiconSource.model_validate(
        source.model_dump(exclude_none=True)
        | {"path": "sources/unknown.jsonl", "sha256": digest, "bytes": size}
    )
    registry = LexiconSources.model_validate(
        REGISTRY.model_dump(exclude_none=True)
        | {"lexiconRoot": "out", "sources": [entry.model_dump(exclude_none=True)]}
    )
    with pytest.raises(ValueError, match="no entry in posAliases"):
        extract_source(entry, registry, tmp_path, force=True)


def test_normalization_is_nfc_and_nothing_else() -> None:
    decomposed = "\u0b95\u0bcd\u0bb7"
    assert normalize(f"  {decomposed}  ") == decomposed
    assert normalize("\u0b85\u0bc8") == "\u0b85\u0bc8"


def test_the_wiktionary_dump_reads_only_its_declared_namespace(
    tmp_path: Path,
) -> None:
    source = next(entry for entry in SOURCES if entry.id == "ta-wiktionary-content")
    entry, registry, staged = probe(source, "1x", tmp_path)
    # The 1x fixture holds 200 physical pages and 50 in the main namespace. The
    # tally counts the records, so the other 150 are not rejects - they are not
    # this source's records at all, which is what pageNamespace declares.
    assert staged.read_text(encoding="utf-8").count("<page>") == 200
    result = extract_source(entry, registry, tmp_path, force=True)
    assert result.tally.rowsIn == 50
    assert result.tally.rowsOut == 50
    assert result.tally.parseRejects == 0


def test_the_wiktionary_dump_emits_senses_synonyms_and_parts_of_speech(
    tmp_path: Path,
) -> None:
    source = next(entry for entry in SOURCES if entry.id == "ta-wiktionary-content")
    entry, registry, _ = probe(source, "1x", tmp_path)
    result = extract_source(entry, registry, tmp_path, force=True)
    text = result.out.read_text(encoding="utf-8")
    for attr in ("definitionTa", "synonym", "translation", "pos"):
        assert _facts(text, attr), f"no {attr} fact from the 1x fixture"
    # The counted miss: a markup reader reports what it could not read.
    assert "unreadableLines=" in result.extra
    assert "pagesWithoutFacts=" in result.extra


def test_a_wiktionary_page_that_says_nothing_is_observed_but_not_attested(
    tmp_path: Path,
) -> None:
    # The row-by-row half of the tier-1 claim. `lexicographic` says the bytes
    # carry an editorial act; a page with no sense, synonym, gloss or part of
    # speech carries none, so it must not attest word-hood.
    source = next(entry for entry in SOURCES if entry.id == "ta-wiktionary-content")
    entry, registry, _ = probe(source, "1x", tmp_path)
    result = extract_source(entry, registry, tmp_path, force=True)
    records = [
        json.loads(line)
        for line in result.out.read_text(encoding="utf-8").splitlines()[1:-1]
    ]
    observed = {
        record["surface"] for record in records if record["record"] == "observation"
    }
    attested = {
        record["word"] for record in records if record.get("attr") == "headword"
    }
    described = {
        record["word"]
        for record in records
        if record.get("attr") in ("definitionTa", "synonym", "translation", "pos")
    }
    assert attested == described
    assert attested < observed, "every page attested itself, so the gate does nothing"


# --------------------------------------------------------------------------
# 5b. Row 9b - canonicalization, the gloss clique, and the source's own denial
# --------------------------------------------------------------------------

# aa (U+0B86), aatu (U+0B86 U+0B9F U+0BC1) and a two-word title.
_AA = "\u0b86"
_AATU = "\u0b86\u0b9f\u0bc1"


def test_a_mediawiki_title_is_read_in_one_spelling_whichever_the_export_ships(
    tmp_path: Path,
) -> None:
    # The SAME wiki ships underscores in its title list and spaces in its
    # content dump. Reading them as two strings staged 187,234 multi-word titles
    # twice for no new Tamil word.
    source = next(entry for entry in SOURCES if entry.id == "ta-wiktionary-titles")
    staged = tmp_path / "sources" / "titles.txt"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(
        f"page_title\n{_AA}_{_AATU}\n{_AATU}\n", encoding="utf-8", newline="\n"
    )
    digest, size = sha256_of(staged)
    entry = LexiconSource.model_validate(
        source.model_dump(exclude_none=True)
        | {"path": "sources/titles.txt", "sha256": digest, "bytes": size}
    )
    registry = LexiconSources.model_validate(
        REGISTRY.model_dump(exclude_none=True)
        | {"lexiconRoot": "out", "sources": [entry.model_dump(exclude_none=True)]}
    )
    text = extract_source(entry, registry, tmp_path, force=True).out.read_text(
        encoding="utf-8"
    )
    surfaces = {
        record["surface"]
        for line in text.splitlines()[1:-1]
        if (record := json.loads(line)).get("record") == "observation"
    }
    assert surfaces == {f"{_AA} {_AATU}", _AATU}
    assert not any("_" in surface for surface in surfaces)


def test_a_bracketed_marker_is_stripped_from_a_tamil_term_and_counted(
    tmp_path: Path,
) -> None:
    # "(pe.) <word>" is a part-of-speech stamp, not part of the word. A term
    # that is NOTHING but a stamp reduces to nothing and is counted, never
    # emitted as a surface. The stamp sits on a LATER comma piece here because
    # that is where the real file carries it: a bracket opening the very first
    # piece is inside the leading ASCII marker the splitter already removes.
    source = next(entry for entry in SOURCES if entry.id == "en-ta-dictionary")
    marker = "\u0baa\u0bc6."  # pe. - the noun stamp
    staged = tmp_path / "sources" / "brackets.json"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(
        json.dumps(
            [{"tamil": f"n. {_AATU}, ({marker}) {_AA}, ({marker})", "eng": "one"}]
        ),
        encoding="utf-8",
    )
    digest, size = sha256_of(staged)
    entry = LexiconSource.model_validate(
        source.model_dump(exclude_none=True)
        | {"path": "sources/brackets.json", "sha256": digest, "bytes": size}
    )
    registry = LexiconSources.model_validate(
        REGISTRY.model_dump(exclude_none=True)
        | {"lexiconRoot": "out", "sources": [entry.model_dump(exclude_none=True)]}
    )
    result = extract_source(entry, registry, tmp_path, force=True)
    text = result.out.read_text(encoding="utf-8")
    surfaces = {
        record["surface"]
        for line in text.splitlines()[1:-1]
        if (record := json.loads(line)).get("record") == "observation"
    }
    assert surfaces == {_AATU, _AA}
    assert "parentheticalsStripped=2" in result.extra
    assert "emptiedByStrip=1" in result.extra


def test_an_unbalanced_bracket_is_left_alone(tmp_path: Path) -> None:
    # A marker the source's own extraction truncated. Guessing where it ended
    # would invent a word rather than recover one, and the classifier's own
    # precondition already refuses a surface carrying punctuation.
    source = next(entry for entry in SOURCES if entry.id == "en-ta-dictionary")
    staged = tmp_path / "sources" / "unbalanced.json"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(
        json.dumps([{"tamil": f"n. {_AATU}, ({_AA}", "eng": "one"}]), encoding="utf-8"
    )
    digest, size = sha256_of(staged)
    entry = LexiconSource.model_validate(
        source.model_dump(exclude_none=True)
        | {"path": "sources/unbalanced.json", "sha256": digest, "bytes": size}
    )
    registry = LexiconSources.model_validate(
        REGISTRY.model_dump(exclude_none=True)
        | {"lexiconRoot": "out", "sources": [entry.model_dump(exclude_none=True)]}
    )
    result = extract_source(entry, registry, tmp_path, force=True)
    text = result.out.read_text(encoding="utf-8")
    surfaces = {
        record["surface"]
        for line in text.splitlines()[1:-1]
        if (record := json.loads(line)).get("record") == "observation"
    }
    assert surfaces == {_AATU, f"({_AA}"}
    assert "parentheticalsStripped=0" in result.extra


def test_a_rejected_not_a_word_tag_emits_the_source_s_denial(tmp_path: Path) -> None:
    # The registry routes `character` to reject notAWord, and the contract says
    # that means the source denied word-hood. Before Row 9b only the pos fact
    # was suppressed and the headword fact went out anyway, so the pipeline
    # asserted exactly what the source denied.
    source = next(entry for entry in SOURCES if entry.id == "wiktextract-ta")
    staged = tmp_path / "sources" / "letters.jsonl"
    staged.parent.mkdir(parents=True, exist_ok=True)
    staged.write_text(
        json.dumps({"word": _AA, "pos": "character"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    digest, size = sha256_of(staged)
    entry = LexiconSource.model_validate(
        source.model_dump(exclude_none=True)
        | {"path": "sources/letters.jsonl", "sha256": digest, "bytes": size}
    )
    registry = LexiconSources.model_validate(
        REGISTRY.model_dump(exclude_none=True)
        | {"lexiconRoot": "out", "sources": [entry.model_dump(exclude_none=True)]}
    )
    result = extract_source(entry, registry, tmp_path, force=True)
    text = result.out.read_text(encoding="utf-8")
    assert [record["value"] for record in _facts(text, "wordClassEvidence")] == [
        "notAWord"
    ]
    assert _facts(text, "pos") == []
    assert result.tally.posRejected == 1


# --------------------------------------------------------------------------
# 5c. Row 9b - the quoted delimited reader and the synset extractor
# --------------------------------------------------------------------------

_IWN = next(entry for entry in SOURCES if entry.id == "indowordnet-ta")


def _iwn_record(
    iwn_id: str, category: str, english: str, synset: str, gloss: str, link: str
) -> str:
    return "\t".join(
        (iwn_id, category, "1", category, english, "an english gloss", "h", "hg",
         synset, gloss, link)
    )


def test_a_quoted_field_may_hold_the_delimiter_a_quote_and_a_newline() -> None:
    # The property that makes this a separate reader kind rather than a flag.
    # The plain reader sees four malformed lines here; there are two records.
    document = (
        "a\tb\n"
        'one\t"holds\ta tab, a ""quote"" and\na newline"\n'
        "two\tplain\n"
    )
    rows = list(iter_delimited_quoted(io.StringIO(document), _IWN))
    assert rows == [
        ["one", 'holds\ta tab, a "quote" and\na newline'],
        ["two", "plain"],
    ]
    assert len(document.splitlines()) == 4, "the fixture really does span lines"


def test_the_quoted_reader_holds_only_the_record_it_is_assembling() -> None:
    # The same streaming predicate every other reader carries, stated over the
    # committed fixture: a 10x document must not peak at ten times the 1x one.
    def peak(path: Path) -> int:
        # The document is loaded and the handle built OUTSIDE the traced window:
        # measured from inside, the peak is the document, which is the one thing
        # a streaming reader is not responsible for.
        handle = io.StringIO(path.read_text(encoding="utf-8"))
        gc.collect()
        tracemalloc.start()
        for _ in iter_delimited_quoted(handle, _IWN):
            pass
        measured = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        return measured

    one = peak(fixture_for(_IWN, "1x"))
    ten = peak(fixture_for(_IWN, "10x"))
    assert ten <= one * 1.2, f"peak grew from {one} to {ten} with the document"


def _iwn_extract(records: list[str], tmp_path: Path) -> str:
    staged = tmp_path / "sources" / "synsets.tsv"
    staged.parent.mkdir(parents=True, exist_ok=True)
    header = "\t".join(
        (
            "iwn_id", "iwn_category", "english_id", "english_category",
            "english_synset_words", "english_gloss", "hindi_synset",
            "hindi_gloss", "tamil_synset", "tamil_gloss", "type_link",
        )
    )
    staged.write_text(
        "\n".join([header, *records]) + "\n", encoding="utf-8", newline="\n"
    )
    digest, size = sha256_of(staged)
    entry = LexiconSource.model_validate(
        _IWN.model_dump(exclude_none=True)
        | {"path": "sources/synsets.tsv", "sha256": digest, "bytes": size}
    )
    registry = LexiconSources.model_validate(
        REGISTRY.model_dump(exclude_none=True)
        | {"lexiconRoot": "out", "sources": [entry.model_dump(exclude_none=True)]}
    )
    return extract_source(entry, registry, tmp_path, force=True).out.read_text(
        encoding="utf-8"
    )


def test_a_synset_is_a_sense_scoped_synonym_set(tmp_path: Path) -> None:
    # The whole reason this source was acquired: the words in one record are
    # equivalents of each other IN ONE SENSE, asserted by the source, so they
    # are `synonym` facts rather than the `glossPeer` a translation list gives.
    text = _iwn_extract(
        [
            _iwn_record(
                "1", "NOUN", "fire", f"{_AATU}, {_AA}", "a tamil gloss||an example",
                "Direct",
            )
        ],
        tmp_path,
    )
    synonyms = {
        (record["word"], record["value"]) for record in _facts(text, "synonym")
    }
    assert synonyms == {(_AATU, _AA), (_AA, _AATU)}
    assert _facts(text, "glossPeer") == []
    assert {record["value"] for record in _facts(text, "definitionTa")} == {
        "a tamil gloss"
    }
    assert {record["value"] for record in _facts(text, "pos")} == {"noun"}
    assert {record["value"] for record in _facts(text, "translation")} == {"fire"}


def test_a_hypernym_link_yields_no_translation(tmp_path: Path) -> None:
    # `type_link` says how the Tamil synset was joined to the Princeton one. On
    # a hypernym link the English words name a BROADER concept, so publishing
    # them as the translation would assert an equivalence the source declined
    # to assert. Everything the source DID assert still lands.
    text = _iwn_extract(
        [
            _iwn_record(
                "1", "NOUN", "animal", _AATU, "a tamil gloss||an example",
                "Hypernymy",
            )
        ],
        tmp_path,
    )
    assert _facts(text, "translation") == []
    assert {record["value"] for record in _facts(text, "definitionTa")} == {
        "a tamil gloss"
    }
    assert {record["word"] for record in _facts(text, "headword")} == {_AATU}


def test_a_multiword_synset_member_is_read_with_its_space(tmp_path: Path) -> None:
    # The release writes a multi-word expression with underscores, the Princeton
    # convention it inherits with the synset ids.
    text = _iwn_extract(
        [
            _iwn_record(
                "1", "VERB", "run", f"{_AATU}_{_AA}", "a tamil gloss||an example",
                "Direct",
            )
        ],
        tmp_path,
    )
    assert {record["word"] for record in _facts(text, "headword")} == {
        f"{_AATU} {_AA}"
    }


# --------------------------------------------------------------------------
# 6. Against the real sources, when they are on disk
# --------------------------------------------------------------------------


@pytest.mark.parametrize("source", SOURCES, ids=lambda source: source.id)
def test_the_registered_digest_still_describes_the_raw_bytes(
    source: LexiconSource,
) -> None:
    path = _REPO_ROOT / source.path
    if not path.exists():
        pytest.skip(f"{source.path} is gitignored and not on disk")
    digest, size = sha256_of(path)
    assert digest == source.sha256
    assert size == source.bytes


def test_the_quoted_source_really_does_hold_a_record_that_spans_two_lines() -> None:
    # The measurement that justifies the reader kind, asserted against the real
    # bytes: 16,640 logical records over 16,642 physical lines.
    path = _REPO_ROOT / _IWN.path
    if not path.exists():
        pytest.skip(f"{_IWN.path} is gitignored and not on disk")
    raw = path.read_bytes()
    with path.open("r", encoding="utf-8", newline="") as handle:
        records = sum(1 for _ in iter_delimited_quoted(handle, _IWN))
    assert records == 16639, "records, after the header the registry declares"
    assert raw.count(b"\n") == 16642
    assert records + 1 < raw.count(b"\n"), (
        "a line-splitting reader would see more records than there are"
    )
