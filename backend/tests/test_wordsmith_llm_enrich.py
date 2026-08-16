"""Tests for the authored lexicon source (Row 10).

The committed ``datasets/lexicon/sources/llm-authored/entries.jsonl`` IS the
fixture. That is not a shortcut: the file is real input to the pipeline, it is
in the repository, and holding a second sliced copy of it under
``datasets/fixtures/lexicon/`` would be two versions of the same bytes waiting
to disagree. Every other source needs a slice because its raw bytes are
gitignored; this one does not.

Five things are proven here:

1. The committed file is admissible - the real reader accepts every line, and
   every line carries the ``model`` / ``promptVersion`` / date provenance.
2. The validator REFUSES each way a batch can go wrong, one test per rule, so a
   bad batch fails at the boundary rather than reaching a player.
3. The ORACLE: the file round-trips through EXTRACT and STAGE to byte-identical
   facts across two independent runs.
4. Nothing here touches the network, and the module cannot: it imports no
   networking library at all.
5. Peak memory does not track file size - the reader holds one entry.

No mocks (Holy Law #7), no network (the row's own acceptance gate).
"""

from __future__ import annotations

import gc
import hashlib
import io
import json
import sqlite3
import tracemalloc
from pathlib import Path
from typing import Any, get_args

import pytest

from yen_tamizh_backend.contracts.lexicon import PartOfSpeech
from yen_tamizh_backend.contracts.lexicon_sources import LexiconSource, LexiconSources
from yen_tamizh_backend.ezhuthu import segment
from yen_tamizh_backend.wordsmith import llm_enrich
from yen_tamizh_backend.wordsmith.extract import (
    Fact,
    Observation,
    Tally,
    emit_from,
    extract_source,
    load_registry,
    sha256_of,
)
from yen_tamizh_backend.wordsmith.llm_enrich import (
    AUTHORED_SOURCE_ID,
    AUTHORED_SOURCE_PATH,
    AuthoredEntry,
    AuthoredEntryError,
    authored_facts,
    parse_entry,
    read_entries,
    themes_of,
)
from yen_tamizh_backend.wordsmith.stage import stage
from yen_tamizh_backend.wordsmith.store import open_store

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENTRIES = _REPO_ROOT / AUTHORED_SOURCE_PATH
REGISTRY = load_registry(_REPO_ROOT / "config" / "lexicon-sources.json")
THEMES = themes_of(REGISTRY)
SOURCE = next(entry for entry in REGISTRY.sources if entry.id == AUTHORED_SOURCE_ID)
ENTRIES = list(read_entries(_ENTRIES, THEMES))

# One valid row, used as the base every rejection test mutates so each test
# changes exactly the thing it is about.
VALID: dict[str, Any] = {
    "word": "\u0bae\u0bb0\u0bae\u0bcd",
    "pos": ["noun"],
    "translationEn": "tree",
    "definitionTa": "\u0b85\u0b9f\u0bbf\u0bae\u0bb0\u0bae\u0bc1\u0bae\u0bcd "
    "\u0b95\u0bbf\u0bb3\u0bc8\u0b95\u0bb3\u0bc1\u0bae\u0bcd \u0b95\u0bca\u0ba3\u0bcd"
    "\u0b9f \u0ba4\u0bbe\u0bb5\u0bb0\u0bae\u0bcd",
    "synonymsTa": ["\u0bb5\u0bbf\u0bb0\u0bc1\u0b9f\u0bcd\u0b9a\u0bae\u0bcd"],
    "categories": ["types-of-plants"],
    "model": "claude-opus-5",
    "promptVersion": "2026-08-15",
    "authoredOn": "2026-08-15",
}


def _valid(**overrides: Any) -> dict[str, Any]:
    payload = dict(VALID)
    for key, value in overrides.items():
        if value is None:
            payload.pop(key, None)
        else:
            payload[key] = value
    return payload


def _facts_of_source(db: Path, source_id: str) -> list[tuple[str, str, str, int]]:
    conn = open_store(db)
    try:
        return list(
            conn.execute(
                "SELECT word, attr, value, ordinal FROM fact WHERE source_id = ?"
                " ORDER BY word, attr, ordinal, value",
                (source_id,),
            )
        )
    finally:
        conn.close()


def _staged(root: Path, label: str) -> Path:
    """Extract and stage the committed authored source into a fresh store."""
    workspace = root / label
    (workspace / "sources").mkdir(parents=True)
    staged_path = workspace / "sources" / _ENTRIES.name
    staged_path.write_bytes(_ENTRIES.read_bytes())
    digest, size = sha256_of(staged_path)
    entry = LexiconSource.model_validate(
        SOURCE.model_dump(exclude_none=True)
        | {"path": f"sources/{staged_path.name}", "sha256": digest, "bytes": size}
    )
    registry = LexiconSources.model_validate(
        REGISTRY.model_dump(exclude_none=True)
        | {
            "lexiconRoot": "out",
            "sources": [entry.model_dump(exclude_none=True)],
            # This one-source workspace carries no frequency corpus, and the
            # registry refuses to name a spoken source it does not carry.
            "spokenSources": [],
        }
    )
    extract_source(entry, registry, workspace, force=True)
    stage(registry, workspace)
    return workspace / "out" / "cache" / "lexicon.db"


# --------------------------------------------------------------------------
# 1. The committed batch is admissible
# --------------------------------------------------------------------------


def test_the_committed_file_is_not_empty_and_every_line_validates() -> None:
    # `read_entries` raises on the first inadmissible line, so reaching here at
    # all is the assertion; the count guards against an empty file passing.
    assert len(ENTRIES) > 0


def test_the_registry_entry_matches_the_committed_bytes() -> None:
    digest, size = sha256_of(_ENTRIES)
    assert SOURCE.sha256 == digest
    assert SOURCE.bytes == size
    assert SOURCE.role == "authored"
    assert SOURCE.kind == "jsonl"
    assert SOURCE.wordField == "word"
    # No field mapping for pos or categories: an authored row writes the closed
    # vocabularies natively, so there is no raw orthography to translate.
    assert SOURCE.posField is None
    assert SOURCE.categoryField is None


def test_every_row_records_the_model_the_prompt_version_and_a_date() -> None:
    for entry in ENTRIES:
        assert entry.model
        assert entry.promptVersion
        assert entry.authoredOn
        assert len(entry.promptVersion) == 10
        assert len(entry.authoredOn) == 10


def test_the_file_is_sorted_by_word_and_each_word_appears_once() -> None:
    words = [entry.word for entry in ENTRIES]
    assert words == sorted(words)
    assert len(set(words)) == len(words)


def test_every_authored_theme_is_one_the_registry_already_normalizes_to() -> None:
    used = {theme for entry in ENTRIES for theme in entry.categories}
    assert used <= THEMES
    assert used, "a batch that authored no theme leaves row 15 with nothing to select"


def test_every_authored_part_of_speech_is_in_the_closed_vocabulary() -> None:
    used = {part for entry in ENTRIES for part in entry.pos}
    assert used <= llm_enrich.PARTS_OF_SPEECH
    assert llm_enrich.PARTS_OF_SPEECH == frozenset(get_args(PartOfSpeech))


def test_no_authored_word_carries_a_non_tamil_or_multi_word_surface() -> None:
    for entry in ENTRIES:
        assert " " not in entry.word
        assert "".join(segment(entry.word)) == entry.word


def test_an_authored_meaning_is_never_the_word_it_explains() -> None:
    # A definition that repeats the answer is the whole puzzle, given away.
    for entry in ENTRIES:
        assert entry.definitionTa != entry.word
        assert entry.word not in entry.synonymsTa


def test_the_command_line_validator_accepts_the_committed_file() -> None:
    assert llm_enrich.main(["--repo-root", str(_REPO_ROOT)]) == 0


def test_the_module_imports_nothing_that_could_reach_the_network() -> None:
    # The row's acceptance gate is "no network call in any test". The stronger
    # guarantee is that the reader has no way to make one, and the cheapest
    # honest check of that is its own source text.
    source = (
        Path(llm_enrich.__file__).read_text(encoding="utf-8").splitlines()
    )
    imports = [line for line in source if line.startswith(("import ", "from "))]
    banned = ("urllib", "http", "socket", "requests", "httpx", "ssl", "asyncio")
    for line in imports:
        assert not any(name in line for name in banned), line


# --------------------------------------------------------------------------
# 2. The validator refuses each way a batch can go wrong
# --------------------------------------------------------------------------


def test_a_well_formed_row_parses() -> None:
    entry = parse_entry(VALID, THEMES, "probe:1")
    assert entry.word == VALID["word"]
    assert entry.pos == ("noun",)
    assert entry.categories == ("types-of-plants",)


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (_valid(cost=3), "unknown key"),
        (_valid(word=None), "missing word"),
        (_valid(word=" x "), "padded word"),
        (_valid(word="two words"), "whitespace in the word"),
        (_valid(model=None), "missing model"),
        (_valid(promptVersion="v1"), "prompt version is not a date"),
        (_valid(authoredOn="15-08-2026"), "date in the wrong order"),
        (_valid(pos=["gerund"]), "part of speech outside the vocabulary"),
        (_valid(pos=["verb", "noun"]), "unsorted pos"),
        (_valid(pos=[]), "empty list rather than an omitted key"),
        (_valid(categories=["hedgehogs"]), "a minted theme"),
        (_valid(categories=["nature", "animals"]), "unsorted categories"),
        (_valid(synonymsTa=[VALID["word"]]), "the word as its own synonym"),
        (_valid(definitionTa=""), "an empty meaning"),
        (
            _valid(pos=None, translationEn=None, definitionTa=None,
                   synonymsTa=None, categories=None),
            "a row that authors nothing",
        ),
        ([VALID], "an array rather than an object"),
    ],
    ids=lambda value: value if isinstance(value, str) else "payload",
)
def test_the_validator_refuses_an_inadmissible_row(payload: Any, reason: str) -> None:
    with pytest.raises(AuthoredEntryError):
        parse_entry(payload, THEMES, "probe:1")


def test_a_repeated_or_out_of_order_word_is_refused() -> None:
    # One check does both jobs: a duplicate is a word that fails to exceed its
    # predecessor, and so is a row that arrives out of order.
    with pytest.raises(AuthoredEntryError):
        parse_entry(VALID, THEMES, "probe:2", previous=VALID["word"])
    with pytest.raises(AuthoredEntryError):
        parse_entry(VALID, THEMES, "probe:2", previous="\u0bb5\u0bbf\u0b9f\u0bc1")
    assert parse_entry(VALID, THEMES, "probe:2", previous="\u0b85").word


def test_a_decomposed_word_is_refused_because_it_would_never_join() -> None:
    decomposed = "\u0b95\u0bc6\u0bbe"  # ka + e-sign + aa-sign, NFC composes to ko
    assert decomposed != "\u0b95\u0bca"
    with pytest.raises(AuthoredEntryError):
        parse_entry(_valid(word=decomposed), THEMES, "probe:1")


def test_a_line_that_is_not_json_names_its_line_number(tmp_path: Path) -> None:
    broken = tmp_path / "entries.jsonl"
    broken.write_text(
        json.dumps(VALID, ensure_ascii=False) + "\n{not json\n", encoding="utf-8"
    )
    with pytest.raises(AuthoredEntryError, match=":2"):
        list(read_entries(broken, THEMES))


# --------------------------------------------------------------------------
# 3. What one row asserts
# --------------------------------------------------------------------------


def test_authored_facts_cover_every_populated_field_in_a_fixed_order() -> None:
    facts = list(authored_facts(parse_entry(VALID, THEMES, "probe:1")))
    assert [attr for attr, _, _ in facts] == [
        "pos",
        "translation",
        "definitionTa",
        "synonym",
        "category",
    ]
    assert [value for _, value, _ in facts] == [
        "noun",
        VALID["translationEn"],
        VALID["definitionTa"],
        VALID["synonymsTa"][0],
        "types-of-plants",
    ]
    assert all(ordinal == 0 for _, _, ordinal in facts)


def test_a_row_asserting_only_a_meaning_emits_only_that_fact() -> None:
    sparse = _valid(pos=None, translationEn=None, synonymsTa=None, categories=None)
    facts = list(authored_facts(parse_entry(sparse, THEMES, "probe:1")))
    assert facts == [("definitionTa", VALID["definitionTa"], 0)]


def test_the_headword_fact_is_the_extractors_job_not_the_rows() -> None:
    # Asserting word-hood is a function of the source's ROLE, so `authored_facts`
    # must not emit it - otherwise flipping the registry role to `category`
    # would leave the source still claiming word-hood.
    attrs = {attr for attr, _, _ in authored_facts(parse_entry(VALID, THEMES, "p:1"))}
    assert "headword" not in attrs


def test_the_extractor_emits_one_observation_and_the_headword_fact(
    tmp_path: Path,
) -> None:
    handle = io.StringIO(json.dumps(VALID, ensure_ascii=False) + "\n")
    tally = Tally()
    emissions = list(emit_from(handle, SOURCE, REGISTRY, tally))
    observations = [e for e in emissions if isinstance(e, Observation)]
    facts = [e for e in emissions if isinstance(e, Fact)]
    assert len(observations) == 1
    assert observations[0].count == 0, "an authored source observes nothing; it asserts"
    assert facts[0].attr == "headword"
    assert tally.rowsIn == 1
    assert tally.rowsOut == 1
    assert tally.parseRejects == 0


def test_the_extractor_refuses_the_whole_run_on_one_bad_row() -> None:
    # EXTRACT counts a parse reject for a third-party source because the bytes
    # are what they are. These bytes are OURS, so a malformed row is a mistake
    # to fix in the diff, not a statistic to report.
    handle = io.StringIO(json.dumps(_valid(pos=["gerund"]), ensure_ascii=False) + "\n")
    with pytest.raises(AuthoredEntryError):
        list(emit_from(handle, SOURCE, REGISTRY, Tally()))


# --------------------------------------------------------------------------
# 4. The Oracle - round-trip byte identity across two runs
# --------------------------------------------------------------------------


def test_the_committed_file_stages_to_byte_identical_facts_across_two_runs(
    tmp_path: Path,
) -> None:
    first = _staged(tmp_path, "run-a")
    second = _staged(tmp_path, "run-b")
    facts_a = _facts_of_source(first, AUTHORED_SOURCE_ID)
    facts_b = _facts_of_source(second, AUTHORED_SOURCE_ID)
    assert facts_a == facts_b
    digest = hashlib.sha256(repr(facts_a).encode("utf-8")).hexdigest()
    assert digest == hashlib.sha256(repr(facts_b).encode("utf-8")).hexdigest()
    assert len(facts_a) > 0


def test_every_staged_fact_traces_back_to_a_line_of_the_committed_file(
    tmp_path: Path,
) -> None:
    db = _staged(tmp_path, "trace")
    staged = _facts_of_source(db, AUTHORED_SOURCE_ID)
    expected: list[tuple[str, str, str, int]] = []
    for entry in ENTRIES:
        expected.append((entry.word, "headword", entry.word, 0))
        expected.extend(
            (entry.word, attr, value, ordinal)
            for attr, value, ordinal in authored_facts(entry)
        )
    assert sorted(staged) == sorted(expected)


def test_the_extract_is_lossless_over_the_committed_file(tmp_path: Path) -> None:
    handle = io.StringIO(_ENTRIES.read_text(encoding="utf-8"))
    tally = Tally()
    for _ in emit_from(handle, SOURCE, REGISTRY, tally):
        pass
    assert tally.rowsIn == len(ENTRIES)
    assert tally.rowsOut + tally.parseRejects == tally.rowsIn
    assert tally.parseRejects == 0


# --------------------------------------------------------------------------
# 5. Peak memory does not track file size
# --------------------------------------------------------------------------


def _peak_bytes(text: str) -> int:
    handle = io.StringIO(text)
    gc.collect()
    tracemalloc.start()
    tracemalloc.reset_peak()
    for _ in emit_from(handle, SOURCE, REGISTRY, Tally()):
        pass
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return peak


def test_ten_times_the_rows_peaks_within_a_fifth_more() -> None:
    # The scaling predicate row 5 decision 6 fixes, over slices of the real file
    # rather than a separate fixture pair - the file is committed, so a slice of
    # it is free and can never drift from what ships.
    lines = _ENTRIES.read_text(encoding="utf-8").splitlines(keepends=True)
    span = max(len(lines) // 10, 1)
    small = _peak_bytes("".join(lines[:span]))
    large = _peak_bytes("".join(lines[: span * 10]))
    assert large <= small * 1.2, f"peak grew {small} -> {large} bytes over 10x the rows"


# --------------------------------------------------------------------------
# 6. What the batch actually authored, reported rather than asserted tightly
# --------------------------------------------------------------------------


def test_the_census_agrees_with_the_entries_it_counted() -> None:
    counts = llm_enrich.census(iter(ENTRIES))
    assert counts["rows"] == len(ENTRIES)
    assert counts["definitionTa"] == sum(e.definitionTa is not None for e in ENTRIES)
    assert counts["categories"] == sum(bool(e.categories) for e in ENTRIES)


def test_a_row_without_a_confident_meaning_is_admissible() -> None:
    # Decision 4 in one assertion: omitting `definitionTa` must be legal, or the
    # no-hedge rule would be unimplementable and every row would carry a guess.
    entry = parse_entry(_valid(definitionTa=None), THEMES, "probe:1")
    assert isinstance(entry, AuthoredEntry)
    assert entry.definitionTa is None


def test_no_store_row_is_written_for_a_word_the_batch_did_not_author(
    tmp_path: Path,
) -> None:
    db = _staged(tmp_path, "scope")
    conn = sqlite3.connect(db)
    try:
        surfaces = {row[0] for row in conn.execute("SELECT surface FROM observation")}
    finally:
        conn.close()
    assert surfaces == {entry.word for entry in ENTRIES}
