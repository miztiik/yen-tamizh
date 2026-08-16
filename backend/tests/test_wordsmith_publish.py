"""Tests for PUBLISH, the pipeline's fourth stage (Row 11).

The row writes the FIRST COMMITTED LEXICON ARTIFACT, and git history is
append-only, so the gates here are about bytes rather than about intent:

- **THE INTEGRATION GATE** runs the whole ``pipeline`` - extract, stage, enrich,
  publish - over the committed byte-exact fixture slices and byte-compares the
  result against a committed expected artifact. It exercises all four stage
  boundaries with real fixtures, no mocks (Holy Law #7), and no raw sources, so
  it runs in CI. It is what a regression in ANY stage trips over.
- **THE ORACLES** are asserted over the REAL committed artifact, which is in the
  repository and therefore present in CI too: every declared sha256 matches the
  file on disk, no file crosses the configured ceiling, the two counter families
  reconcile, every row's declared length is its word's own ezhuthu count, and
  every file's rows are sorted and share the address the file is named for.
- **THE MEMORY PREDICATE** is a scaling one, never an absolute ceiling: the same
  rows at ten times the count must peak within 1.2x. An absolute number measures
  the machine; a ratio measures the code.

Tamil is written with ``\\uXXXX`` escapes so this file's own normalization form
cannot change what it asserts.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import tracemalloc
import unicodedata
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from _lexicon_workspace import fixture_registry
from yen_tamizh_backend.contracts.lexicon import (
    PARTITION_KEYS,
    Lexicon,
    LexiconEntry,
)
from yen_tamizh_backend.contracts.lexicon_sources import LexiconSources
from yen_tamizh_backend.ezhuthu import classify, ezhuthu_roman, segment
from yen_tamizh_backend.wordsmith.enrich import load_config
from yen_tamizh_backend.wordsmith.extract import load_registry
from yen_tamizh_backend.wordsmith.pipeline import run
from yen_tamizh_backend.wordsmith.publish import (
    BY_CLASS,
    META_NAME,
    README_NAME,
    PublishError,
    partition_hex,
    partition_path,
    publish,
    render,
    render_readme,
    write_rows,
)
from yen_tamizh_backend.wordsmith.resolve import (
    SEPARATOR,
    ResolutionError,
    check_the_closed_vocabularies,
    first_ezhuthu,
)
from yen_tamizh_backend.wordsmith.store import connect, transaction

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = _REPO_ROOT / "config" / "lexicon-sources.json"
_CONFIG_PATH = _REPO_ROOT / "config" / "wordhood.json"
_EXPECTED = _REPO_ROOT / "datasets" / "fixtures" / "lexicon-expected"
_GITATTRIBUTES = _REPO_ROOT / ".gitattributes"
_GITIGNORE = _REPO_ROOT / ".gitignore"

REGISTRY = load_registry(_REGISTRY_PATH)
CONFIG = load_config(_CONFIG_PATH)

LEXICON = _REPO_ROOT / REGISTRY.lexiconRoot
COMMITTED_META = LEXICON / META_NAME


def _meta_document(path: Path) -> Lexicon:
    return Lexicon.model_validate_json(path.read_text(encoding="utf-8"))


def _rows_under(root: Path) -> list[LexiconEntry]:
    return [
        LexiconEntry.model_validate_json(line)
        for path in sorted((root / BY_CLASS).rglob("*.ndjson"))
        for line in path.read_text(encoding="utf-8").splitlines()
    ]


@dataclass(frozen=True, slots=True)
class Published:
    """A fixture-scale pipeline run: the registry that drove it and its output."""

    registry: LexiconSources
    root: Path
    db: Path
    out: Path


@pytest.fixture(scope="module")
def published(tmp_path_factory: pytest.TempPathFactory) -> Published:
    """The whole pipeline over the committed fixture slices, once per module."""
    root = tmp_path_factory.mktemp("publish")
    registry = fixture_registry(_REPO_ROOT, REGISTRY, root)
    db = root / "out" / "cache" / "lexicon.db"
    run(registry, CONFIG, root, db, force=True)
    return Published(registry=registry, root=root, db=db, out=root / "out")


def _snapshot(root: Path) -> dict[str, bytes]:
    """Every published byte under ``root``, keyed by its relative POSIX path."""
    taken = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted((root / BY_CLASS).rglob("*.ndjson"))
    }
    for name in (META_NAME, README_NAME):
        taken[name] = (root / name).read_bytes()
    return taken


# --------------------------------------------------------------------------
# The integration gate: all four stages, real fixtures, byte-compared.
# --------------------------------------------------------------------------


def test_the_pipeline_over_the_fixtures_reproduces_the_committed_expectation(
    published: Published,
) -> None:
    produced = _snapshot(published.out)
    expected = _snapshot(_EXPECTED)
    assert sorted(produced) == sorted(expected), (
        "the fixture pipeline wrote a different set of files - re-run "
        "`python -m yen_tamizh_backend.scripts.rebuild_lexicon_fixture` and "
        "review the diff"
    )
    for name, bytes_out in produced.items():
        assert bytes_out == expected[name], f"{name} differs from the committed bytes"


def test_the_committed_expectation_is_lf_only() -> None:
    # Row 4's trap: with core.autocrlf a checkout can rewrite line endings, and
    # a byte-compared fixture would then fail on somebody else's machine rather
    # than on the change that broke it.
    for name, bytes_out in _snapshot(_EXPECTED).items():
        assert b"\r\n" not in bytes_out, f"{name} was checked out with CRLF"


def test_the_committed_artifact_is_lf_only() -> None:
    document = _meta_document(COMMITTED_META)
    for cell in document.partitions:
        assert b"\r\n" not in (_REPO_ROOT / cell.path).read_bytes(), cell.path
    assert b"\r\n" not in COMMITTED_META.read_bytes()
    assert b"\r\n" not in (LEXICON / README_NAME).read_bytes()


def test_git_pins_the_published_line_endings() -> None:
    rules = _GITATTRIBUTES.read_text(encoding="utf-8")
    assert "datasets/lexicon/by-class/** text eol=lf" in rules
    assert "datasets/lexicon/lexicon.meta.json text eol=lf" in rules
    assert "datasets/lexicon/README.md text eol=lf" in rules
    assert "datasets/fixtures/lexicon-expected/** text eol=lf" in rules


def test_git_ignores_the_review_reports_but_keeps_their_readme() -> None:
    # Row 9b wrote them into the build cache; they are working material a person
    # reads, so they live under the lexicon root with a committed README saying
    # what they are - and the bytes themselves still never ship.
    rules = _GITIGNORE.read_text(encoding="utf-8")
    assert "datasets/lexicon/review/*" in rules
    assert "!datasets/lexicon/review/README.md" in rules
    assert (LEXICON / "review" / "README.md").is_file()


# --------------------------------------------------------------------------
# Oracle 1 - re-publishing from an unchanged store is byte-identical.
# --------------------------------------------------------------------------


def test_republishing_an_unchanged_store_writes_identical_bytes(
    published: Published,
) -> None:
    before = _snapshot(published.out)
    publish(published.registry, published.root, published.db)
    assert _snapshot(published.out) == before


def test_a_stale_file_from_an_earlier_layout_is_removed(
    published: Published,
) -> None:
    # Without this the directory and the index disagree, and a reader that
    # resolves a file from the index alone would never notice.
    stray = partition_path(published.out / BY_CLASS, "headword", "ffff")
    stray.write_text("{}\n", encoding="utf-8", newline="\n")
    orphan = partition_path(published.out / BY_CLASS, "inflected", "0b95")
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_text("{}\n", encoding="utf-8", newline="\n")
    result = publish(published.registry, published.root, published.db)
    assert "headword/ffff.ndjson" in result.removed
    assert "inflected/0b95.ndjson" in result.removed
    assert not stray.exists()
    # A withheld class must leave no empty directory behind either: an empty
    # directory reads like a class that published nothing rather than one that
    # was never published.
    assert not orphan.parent.exists()


# --------------------------------------------------------------------------
# Oracle 2 - the counters reconcile, in two families.
# --------------------------------------------------------------------------


def test_the_two_counter_families_reconcile(published: Published) -> None:
    document = _meta_document(published.out / META_NAME)
    conn = sqlite3.connect(published.db)
    try:
        stored = {
            str(name): int(count)
            for name, count in conn.execute(
                "SELECT wordClass, count(*) FROM classification GROUP BY 1"
            )
        }
    finally:
        conn.close()
    classified = document.counters.classified
    published_census = document.counters.published
    assert classified.rows == sum(stored.values())
    for name, count in classified.byClass.items():
        assert stored.get(name, 0) == count
    assert sum(cell.rows for cell in document.partitions) == published_census.rows
    for name in classified.byClass:
        if name in published.registry.publishedClasses:
            assert published_census.byClass[name] == classified.byClass[name]
        else:
            assert published_census.byClass[name] == 0


def test_the_committed_artifact_counters_reconcile() -> None:
    # The same Oracle over the REAL artifact, which is in the repository.
    document = _meta_document(COMMITTED_META)
    assert document.counters.published.rows == sum(
        cell.rows for cell in document.partitions
    )
    for name, count in document.counters.published.byClass.items():
        if name in REGISTRY.publishedClasses:
            assert count == document.counters.classified.byClass[name]
        else:
            assert count == 0
    assert document.counters.classified.rows > document.counters.published.rows


# --------------------------------------------------------------------------
# Oracles 3, 4 and 5 over the committed artifact.
# --------------------------------------------------------------------------


def _committed_rows() -> Iterator[tuple[str, LexiconEntry]]:
    """Every committed row, streamed. Nothing here holds the whole artifact."""
    document = _meta_document(COMMITTED_META)
    for cell in document.partitions:
        with (_REPO_ROOT / cell.path).open(encoding="utf-8") as handle:
            for line in handle:
                yield cell.path, LexiconEntry.model_validate_json(line)


def test_every_committed_row_is_self_consistent_sorted_and_correctly_addressed() -> (
    None
):
    # Oracles 3 and 4 over the REAL artifact, in ONE streaming pass:
    #
    # - segment(word) rejoins to the word and its count is the declared length,
    #   which is what proves the dropped ezhuthu column is recomputable from the
    #   committed artifact alone;
    # - every row sits in the file its address names, and each file is sorted by
    #   word ASC, so a refresh INSERTS in place and the partition cut is a range
    #   cut on an order that already exists;
    # - the dropped columns are absent, not empty.
    document = _meta_document(COMMITTED_META)
    addresses = {cell.path: cell for cell in document.partitions}
    previous: dict[str, str] = {}
    counted: Counter[str] = Counter()
    dropped = ("ezhuthu", "wordhood", "freqRank", "compound", "attestedBy")
    for path, row in _committed_rows():
        cell = addresses[path]
        parts = segment(row.word)
        assert "".join(parts) == row.word
        assert row.length == len(parts)
        assert row.wordClass == cell.wordClass
        assert partition_hex(parts[0]) == cell.firstEzhuthu
        assert row.tier1Attestations <= row.attestations
        seen = previous.get(path)
        assert seen is None or seen < row.word, f"{path} is not sorted at {row.word!r}"
        previous[path] = row.word
        counted[path] += 1
        rendered = json.loads(render(row))
        for name in dropped:
            assert name not in rendered
    assert counted
    for cell in document.partitions:
        assert counted[cell.path] == cell.rows


def test_every_committed_file_name_is_its_address_and_sorts_with_it() -> None:
    # Zero-padded 4-digit groups are what make ASCII filename order equal
    # code-point order, so `ls` order is row order. Asserted rather than argued.
    document = _meta_document(COMMITTED_META)
    by_class: dict[str, list[str]] = {}
    for cell in document.partitions:
        assert cell.path.endswith(f"{BY_CLASS}/{cell.wordClass}/{cell.firstEzhuthu}.ndjson")
        assert len(cell.firstEzhuthu) in (4, 8)
        by_class.setdefault(cell.wordClass, []).append(cell.firstEzhuthu)
    for word_class, keys in by_class.items():
        assert keys == sorted(keys), word_class
        first_words = []
        for key in keys:
            path = LEXICON / BY_CLASS / word_class / f"{key}.ndjson"
            with path.open(encoding="utf-8") as handle:
                first_words.append(json.loads(handle.readline())["word"])
        assert first_words == sorted(first_words), word_class


def test_no_committed_file_crosses_the_configured_ceiling() -> None:
    # Oracle 4. A build assertion rather than a partition threshold: it says out
    # loud that one file has outgrown what the address can hold.
    document = _meta_document(COMMITTED_META)
    for cell in document.partitions:
        assert cell.bytes <= REGISTRY.maxPartitionBytes, (
            f"{cell.path} is {cell.bytes} bytes"
        )


def test_every_declared_sha256_matches_the_file_on_disk() -> None:
    # Oracle 5. This is what a no-globbing reader is otherwise blind to: a file
    # written but not registered, registered but not written, or edited by hand.
    document = _meta_document(COMMITTED_META)
    on_disk = sorted(
        path.relative_to(_REPO_ROOT).as_posix()
        for path in (LEXICON / BY_CLASS).rglob("*.ndjson")
    )
    assert sorted(cell.path for cell in document.partitions) == on_disk
    for cell in document.partitions:
        raw = (_REPO_ROOT / cell.path).read_bytes()
        assert len(raw) == cell.bytes, f"{cell.path} is {len(raw)} bytes"
        assert hashlib.sha256(raw).hexdigest() == cell.sha256, f"{cell.path} differs"


def test_the_ezhuthu_index_spells_out_every_address_it_is_asked_about() -> None:
    document = _meta_document(COMMITTED_META)
    assert document.partitionKeys == list(PARTITION_KEYS)
    for hex_key, entry in document.ezhuthuIndex.items():
        assert partition_hex(entry.ezhuthu) == hex_key
        assert segment(entry.ezhuthu) == [entry.ezhuthu]
        assert entry.roman == ezhuthu_roman(entry.ezhuthu)
        assert entry.kind == classify(entry.ezhuthu)
    assert {cell.firstEzhuthu for cell in document.partitions} == set(
        document.ezhuthuIndex
    )


def test_the_generated_readme_restates_the_index_it_is_generated_from() -> None:
    document = _meta_document(COMMITTED_META)
    body = (LEXICON / README_NAME).read_text(encoding="utf-8")
    assert body == render_readme(document), (
        "the committed README is not what PUBLISH renders from the committed "
        "meta - it is generated, never hand-edited"
    )
    for entry in document.ezhuthuIndex.values():
        assert entry.ezhuthu in body and entry.roman in body
    for cell in document.partitions:
        assert f"{BY_CLASS}/{cell.wordClass}/{cell.firstEzhuthu}.ndjson" in body


def test_no_committed_path_is_absolute_or_backslashed() -> None:
    # CLAUDE.md section 2: everything leaving the process is relative POSIX.
    document = _meta_document(COMMITTED_META)
    paths = [cell.path for cell in document.partitions] + [
        source.path for source in document.provenance
    ]
    for path in paths:
        assert "\\" not in path and ":" not in path and not path.startswith("/")


# --------------------------------------------------------------------------
# The address itself, and the two assertions that keep it aligned.
# --------------------------------------------------------------------------


def test_the_address_is_the_whole_first_ezhuthu_not_its_base() -> None:
    assert partition_hex(first_ezhuthu("\u0b85\u0bb0\u0b9a\u0bc1")) == "0b85"
    assert partition_hex(first_ezhuthu("\u0b95\u0b9f\u0bb2\u0bcd")) == "0b95"
    assert partition_hex(first_ezhuthu("\u0b95\u0bbe\u0bb2\u0bcd")) == "0b950bbe"
    assert partition_hex(first_ezhuthu("\u0b95\u0bbf\u0bb3\u0bbf")) == "0b950bbf"


def test_a_decomposed_first_letter_is_refused_rather_than_addressed_twice() -> None:
    # ko written NFD is ke + aa, which segments as one letter and would mint a
    # SECOND file for a letter that already has one.
    composed = "\u0b95\u0bca"
    decomposed = unicodedata.normalize("NFD", composed)
    assert decomposed != composed
    assert segment(decomposed) == [decomposed]
    assert partition_hex(composed) == "0b950bca"
    with pytest.raises(PublishError, match="NFC"):
        partition_hex(decomposed)


def test_a_letter_outside_the_basic_multilingual_plane_is_refused() -> None:
    # A five-digit group would break the zero-padding that makes filename order
    # equal code-point order. Tamil never trips it, which is why it is asserted.
    with pytest.raises(PublishError, match="Basic Multilingual Plane"):
        partition_hex("\U00011fff")


def test_a_mark_sequence_no_letter_has_is_refused() -> None:
    with pytest.raises(PublishError, match="code points"):
        partition_hex("\u0b95\u0bbe\u0bbf")


# --------------------------------------------------------------------------
# The resolution rules.
# --------------------------------------------------------------------------


def test_a_union_column_is_sorted_deduped_and_excludes_the_word_itself(
    published: Published,
) -> None:
    rows = _rows_under(published.out)
    assert rows
    for row in rows:
        for values in (row.pos, row.synonymsTa, row.categories):
            if values is not None:
                assert list(values) == sorted(set(values))
        if row.synonymsTa is not None:
            assert row.word not in row.synonymsTa


def test_attestations_count_the_sources_that_listed_the_word(
    published: Published,
) -> None:
    # The row publishes the COUNT because that is what selection gates on; the
    # names stay in the store, where a question about one word can be asked.
    attesting = {
        source.id: source.attestationTier == "lexicographic"
        for source in published.registry.sources
        if source.role in ("authority", "authored")
    }
    marks = ",".join(f"'{name}'" for name in attesting)
    conn = sqlite3.connect(published.db)
    try:
        measured: dict[str, set[str]] = {}
        for word, source_id in conn.execute(
            f"SELECT DISTINCT word, source_id FROM fact "
            f"WHERE attr = 'headword' AND source_id IN ({marks})"
        ):
            measured.setdefault(str(word), set()).add(str(source_id))
    finally:
        conn.close()
    checked = 0
    for row in _rows_under(published.out):
        sources = measured.get(row.word, set())
        assert row.attestations == len(sources)
        assert row.tier1Attestations == sum(1 for name in sources if attesting[name])
        checked += row.attestations > 0
    assert checked


def test_an_attested_meaning_outranks_an_authored_one(published: Published) -> None:
    # Row 4 decision 2a. Expressed as a rule rather than as a precedence
    # number, because appending a source to the registry must not be able to
    # promote the authoring pass over a dictionary by accident.
    authored = [
        source.id for source in published.registry.sources if source.role == "authored"
    ]
    assert authored, "the registry no longer carries an authored source"
    conn = sqlite3.connect(published.db)
    try:
        marks = ",".join(f"'{name}'" for name in authored)
        both = {
            str(word)
            for (word,) in conn.execute(
                f"SELECT word FROM fact WHERE attr = 'definitionTa' "
                f"AND source_id IN ({marks}) AND word IN ("
                f"  SELECT word FROM fact WHERE attr = 'definitionTa' "
                f"  AND source_id NOT IN ({marks}))"
            )
        }
        attested: dict[str, set[str]] = {}
        for word, value in conn.execute(
            f"SELECT word, value FROM fact WHERE attr = 'definitionTa' "
            f"AND source_id NOT IN ({marks})"
        ):
            attested.setdefault(str(word), set()).add(str(value))
    finally:
        conn.close()
    contested = [row for row in _rows_under(published.out) if row.word in both]
    assert contested, "no fixture word is described by both an authority and the pass"
    for row in contested:
        assert row.definitionTa in attested[row.word]


def test_the_spoken_share_is_a_share_of_the_published_frequency(
    published: Published,
) -> None:
    conn = sqlite3.connect(published.db)
    try:
        spoken = ",".join(f"'{name}'" for name in published.registry.spokenSources)
        frequency = ",".join(
            f"'{source.id}'"
            for source in published.registry.sources
            if source.role == "frequency"
        )
        measured = {
            str(word): (int(total), int(part))
            for word, total, part in conn.execute(
                f"SELECT surface, sum(count), "
                f"sum(CASE WHEN source_id IN ({spoken}) THEN count ELSE 0 END) "
                f"FROM observation WHERE source_id IN ({frequency}) GROUP BY surface"
            )
        }
    finally:
        conn.close()
    checked = 0
    for row in _rows_under(published.out):
        total, part = measured.get(row.word, (0, 0))
        assert row.frequency == total
        if total:
            assert row.spokenRatio == pytest.approx(part / total, abs=5e-7)
            checked += 1
        else:
            assert row.spokenRatio is None
    assert checked


def test_a_value_outside_the_closed_vocabulary_fails_the_publish(
    published: Published,
) -> None:
    # Row 11 decision 3: never dropped, never passed through, and the message
    # names the value AND its row count so the cost of the fix is visible.
    db = published.root / "breach.db"
    shutil.copyfile(published.db, db)
    conn = connect(db)
    try:
        with transaction(conn):
            conn.execute(
                "INSERT INTO fact (source_id, word, attr, value, ordinal) "
                "VALUES ('wiktextract-ta', 'x', 'pos', 'gerund', 0)"
            )
        with pytest.raises(ResolutionError) as failure:
            check_the_closed_vocabularies(conn, published.registry)
    finally:
        conn.close()
    assert "gerund" in str(failure.value)
    assert "1 rows" in str(failure.value)


def test_a_fact_holding_the_join_separator_fails_the_publish(
    published: Published,
) -> None:
    db = published.root / "separator.db"
    shutil.copyfile(published.db, db)
    conn = connect(db)
    try:
        with transaction(conn):
            conn.execute(
                "INSERT INTO fact (source_id, word, attr, value, ordinal) "
                "VALUES ('wiktextract-ta', 'x', 'synonym', ?, 0)",
                (f"a{SEPARATOR}b",),
            )
        with pytest.raises(ResolutionError):
            check_the_closed_vocabularies(conn, published.registry)
    finally:
        conn.close()


# --------------------------------------------------------------------------
# What PUBLISH refuses.
# --------------------------------------------------------------------------


def test_publish_refuses_a_derived_zone_behind_its_staged_one(
    published: Published,
) -> None:
    db = published.root / "stale.db"
    shutil.copyfile(published.db, db)
    conn = connect(db)
    try:
        with transaction(conn):
            conn.execute("UPDATE stage_epoch SET n = n + 1")
    finally:
        conn.close()
    with pytest.raises(PublishError, match="derived zone is behind"):
        publish(published.registry, published.root, db)


def test_publish_refuses_an_output_format_it_does_not_write(
    published: Published,
) -> None:
    # A declared output nothing produces is a claim rather than a knob.
    registry = LexiconSources.model_validate(
        published.registry.model_dump(exclude_none=True)
        | {"outputs": ["ndjson", "csv"]}
    )
    with pytest.raises(PublishError, match="csv"):
        publish(registry, published.root, published.db)


def test_publish_refuses_a_source_staged_from_bytes_the_registry_disowns(
    published: Published,
) -> None:
    db = published.root / "drifted.db"
    shutil.copyfile(published.db, db)
    conn = connect(db)
    try:
        with transaction(conn):
            conn.execute(
                "UPDATE source SET sha256 = ? WHERE id = 'wiktextract-ta'", ("f" * 64,)
            )
    finally:
        conn.close()
    with pytest.raises(PublishError, match="no longer declares"):
        publish(published.registry, published.root, db)


def test_publish_refuses_a_file_over_the_configured_ceiling(
    published: Published,
) -> None:
    tiny = LexiconSources.model_validate(
        published.registry.model_dump(exclude_none=True) | {"maxPartitionBytes": 64}
    )
    with pytest.raises(PublishError, match="maxPartitionBytes"):
        publish(tiny, published.root, published.db)
    # Leave the workspace as the other tests expect to find it.
    publish(published.registry, published.root, published.db)


def test_the_registry_refuses_a_spoken_source_that_is_not_a_frequency_corpus() -> None:
    payload: dict[str, Any] = REGISTRY.model_dump(exclude_none=True)
    with pytest.raises(ValidationError, match="frequency"):
        LexiconSources.model_validate(payload | {"spokenSources": ["wiktextract-ta"]})
    with pytest.raises(ValidationError, match="unregistered"):
        LexiconSources.model_validate(payload | {"spokenSources": ["nope"]})


def test_the_registry_refuses_an_unsorted_published_class_list() -> None:
    payload: dict[str, Any] = REGISTRY.model_dump(exclude_none=True)
    with pytest.raises(ValidationError, match="sorted"):
        LexiconSources.model_validate(
            payload | {"publishedClasses": ["headword", "boundStem"]}
        )


# --------------------------------------------------------------------------
# The memory predicate: a ratio, never an absolute ceiling.
# --------------------------------------------------------------------------


def test_writing_ten_times_the_rows_does_not_cost_ten_times_the_memory(
    published: Published, tmp_path: Path
) -> None:
    # Row 5's shape: everything the traced window must NOT measure is built
    # outside it, and the output goes to a real file whose buffer is bounded -
    # a StringIO would accumulate the whole render and measure the sink.
    rows = _rows_under(published.out)
    base = len(rows) // 10
    assert base >= 20, f"the fixture publish is too small to scale: {len(rows)} rows"
    small = rows[:base]
    large = [rows[index % len(rows)] for index in range(base * 10)]

    def peak(batch: list[LexiconEntry], name: str) -> int:
        target = tmp_path / name
        tracemalloc.start()
        with target.open("w", encoding="utf-8", newline="\n") as handle:
            write_rows(handle, iter(batch))
        _, measured = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return measured

    one = peak(small, "1x.ndjson")
    ten = peak(large, "10x.ndjson")
    assert ten <= one * 1.2, f"peak grew from {one} to {ten} on ten times the rows"


# --------------------------------------------------------------------------
# The rendering itself.
# --------------------------------------------------------------------------


def test_a_rendered_line_is_compact_sorted_and_unescaped() -> None:
    row = LexiconEntry(
        word="\u0b85\u0bb0\u0b9a\u0bc1",
        wordClass="headword",
        length=3,
        frequency=7,
        attestations=2,
        tier1Attestations=1,
        pos=["noun"],
    )
    line = render(row)
    assert line.endswith("\n") and line.count("\n") == 1
    assert "\\u0b85" not in line
    assert line.index('"attestations"') < line.index('"frequency"') < line.index('"word"')
    assert json.loads(line) == {
        "word": "\u0b85\u0bb0\u0b9a\u0bc1",
        "wordClass": "headword",
        "length": 3,
        "frequency": 7,
        "attestations": 2,
        "tier1Attestations": 1,
        "pos": ["noun"],
    }


def test_a_row_cannot_claim_more_tier_one_sources_than_it_has() -> None:
    with pytest.raises(ValidationError, match="tier1Attestations"):
        LexiconEntry(
            word="\u0b85\u0bb0\u0b9a\u0bc1",
            wordClass="headword",
            length=3,
            frequency=0,
            attestations=1,
            tier1Attestations=2,
        )


def test_a_row_whose_length_disagrees_with_its_word_is_refused() -> None:
    with pytest.raises(ValidationError, match="ezhuthu count"):
        LexiconEntry(
            word="\u0b85\u0bb0\u0b9a\u0bc1",
            wordClass="headword",
            length=4,
            frequency=0,
            attestations=1,
            tier1Attestations=1,
        )
