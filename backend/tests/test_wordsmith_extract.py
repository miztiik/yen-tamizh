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

import gc
import io
import json
import re
import shutil
import tracemalloc
from pathlib import Path
from typing import Any

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
from yen_tamizh_backend.wordsmith.readers import iter_json_array

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
    if source.kind == "jsonl":
        return len([line for line in raw.splitlines() if line.strip()])
    document: Any = json.loads(raw)
    array = document if source.rootKey is None else document[source.rootKey]
    return len(array)


# --------------------------------------------------------------------------
# 1. The registry is honest
# --------------------------------------------------------------------------


def test_the_registry_validates_and_carries_the_row_three_stamp() -> None:
    assert REGISTRY.version == "2026-08-16"
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


@pytest.mark.parametrize(
    "source", JSON_ARRAY_SOURCES, ids=lambda source: source.id
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
    sideways = _facts(text, "synonym")
    assert forward and sideways
    # Read forward: the row "n. <a>, <b>." gives both Tamil terms the same
    # English headword. Read sideways: each is the other's synonym.
    first = next(record for record in forward if record["value"] == "A B C")
    peers = {
        record["value"] for record in sideways if record["word"] == first["word"]
    }
    assert peers
    assert first["word"] not in peers


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
    assert _facts(text, "synonym") == []
    assert {record["value"] for record in _facts(text, "pos")} == {"noun", "verb"}


def test_a_group_flush_is_not_credited_to_the_row_that_ended_it(
    tmp_path: Path,
) -> None:
    # The synonym run closes when the English headword CHANGES, so its facts are
    # emitted while the NEXT row is being read. A row that produces nothing of
    # its own must still count as a parse reject - measured on the real source,
    # inferring "did this row produce anything" from the yields under-counted
    # the rejects by 8 of 15.
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
    assert _facts(result.out.read_text(encoding="utf-8"), "synonym")


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
