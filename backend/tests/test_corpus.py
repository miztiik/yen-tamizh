"""Tests for the Row 8 corpus layer: streaming ingest -> ranked master wordlist.

Real files and real fixtures throughout, no mocks (Holy Law #7). Tamil is written
with ``\\uXXXX`` escapes so this source stays ASCII (CLAUDE.md section 5) and so
the composed/decomposed form of every test word is unambiguous.

Four things are proven:

1. **Streaming** - both readers are generator functions, and reading a file many
   times larger than the reader's buffer never costs more than a fraction of the
   file. A truncated JSON array raises rather than silently ending early.
2. **Ingest behaviour** - NFC normalization, Tamil-only acceptance, and the
   registry-driven merge (a word attested by two sources lists both and sums
   their counts).
3. **Ranking + banding** - deterministic ordering, the configured percentile
   cuts, and floor/cap reporting what they dropped.
4. **The integrity Oracle** - over the REAL committed artifact: every row's
   ezhuthu equals the Row 6 segmentation and rejoins to its word, every row
   carries a band, ranks run 1..N, and the counters reconcile with no silent
   drops.
"""

from __future__ import annotations

import inspect
import json
import tracemalloc
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from yen_tamizh_backend.contracts import CorpusSources, MasterWordlist
from yen_tamizh_backend.contracts.corpus_sources import CorpusBands
from yen_tamizh_backend.corpus import rank
from yen_tamizh_backend.corpus.ingest import (
    accept,
    ingest,
    load_registry,
    normalize,
    read_source,
    render,
)
from yen_tamizh_backend.ezhuthu import segment

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _REPO_ROOT / "datasets" / "fixtures" / "contracts"
_MASTER = _REPO_ROOT / "datasets" / "wordlists" / "master" / "words_ranked.json"

# Tamil test words, escaped so the composed form is explicit.
TAMIZH = "\u0ba4\u0bae\u0bbf\u0bb4\u0bcd"  # 3 ezhuthu
KADHAI = "\u0b95\u0ba4\u0bc8"  # 2 ezhuthu
MAZHAI = "\u0bae\u0bb4\u0bc8"  # 2 ezhuthu
ORU = "\u0b92\u0bb0\u0bc1"  # 2 ezhuthu

# The same ezhuthu written decomposed (o-sign = e-sign + aa-sign) and composed.
KO_DECOMPOSED = "\u0b95\u0bc6\u0bbe"
KO_COMPOSED = "\u0b95\u0bca"

_BANDS = CorpusBands(commonMaxPercentile=0.1, midMaxPercentile=0.5)


def _registry(tmp_path: Path, sources: list[dict[str, Any]], **filters: Any) -> CorpusSources:
    """Build a validated registry rooted at ``tmp_path`` (relative, POSIX)."""
    base: dict[str, Any] = {
        "minLength": 2,
        "maxLength": 12,
        "minTotalFrequency": 1,
        "maxWords": None,
        "dropCategories": [],
    }
    base.update(filters)
    return CorpusSources.model_validate(
        {
            "version": "2026-08-13",
            "changelog": [
                {"version": "2026-08-13", "change": "test registry", "why": "test"}
            ],
            "corpusRoot": "corpus",
            "filters": base,
            "bands": {"commonMaxPercentile": 0.1, "midMaxPercentile": 0.5},
            "sources": sources,
        }
    )


def _write_source(tmp_path: Path, source_id: str, name: str, text: str) -> None:
    directory = tmp_path / "corpus" / source_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding="utf-8", newline="\n")


def _delimited(source_id: str, name: str = "source.csv") -> dict[str, Any]:
    return {
        "id": source_id,
        "name": f"{source_id} fixture",
        "origin": f"tests/{source_id}",
        "kind": "delimited",
        "path": f"{source_id}/{name}",
        "delimiter": ",",
        "wordColumn": 0,
        "countColumn": 1,
    }


# --------------------------------------------------------------------------
# 1. Streaming
# --------------------------------------------------------------------------


def test_readers_are_generator_based() -> None:
    # A generator function does no I/O until the first record is pulled, which
    # is what makes "never load a whole corpus file" structural rather than a
    # promise in a comment.
    assert inspect.isgeneratorfunction(read_source)


@pytest.mark.parametrize("kind", ["delimited", "json-array"])
def test_reading_a_large_source_never_buffers_the_whole_file(
    tmp_path: Path, kind: str
) -> None:
    if kind == "delimited":
        row = f"{TAMIZH},7\n"
        text = row * (4 * 1024 * 1024 // len(row.encode("utf-8")))
        _write_source(tmp_path, "big", "source.csv", text)
        source = _registry(tmp_path, [_delimited("big")]).sources[0]
        path = tmp_path / "corpus" / "big" / "source.csv"
    else:
        element = '{"ta": "' + TAMIZH + '", "word_frequency": 7},'
        body = element * (4 * 1024 * 1024 // len(element.encode("utf-8")))
        _write_source(tmp_path, "big", "source.json", '{"data": [' + body[:-1] + "]}")
        source = _registry(
            tmp_path,
            [
                {
                    "id": "big",
                    "name": "big fixture",
                    "origin": "tests/big",
                    "kind": "json-array",
                    "path": "big/source.json",
                    "rootKey": "data",
                    "wordField": "ta",
                    "countField": "word_frequency",
                }
            ],
        ).sources[0]
        path = tmp_path / "corpus" / "big" / "source.json"

    file_bytes = path.stat().st_size
    assert file_bytes > 3 * 1024 * 1024

    tracemalloc.start()
    read = sum(1 for _ in read_source(path, source))
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert read > 30_000
    # Peak is one chunk plus one record - a small fraction of the file, not a
    # copy of it.
    assert peak < file_bytes // 4


def test_a_truncated_json_array_raises_rather_than_ending_early(tmp_path: Path) -> None:
    # A silent early stop would look exactly like a small source, so the reader
    # fails fast at the boundary instead (CLAUDE.md anti-patterns).
    _write_source(tmp_path, "cut", "source.json", '{"data": [{"ta": "' + TAMIZH + '"}')
    source = _registry(
        tmp_path,
        [
            {
                "id": "cut",
                "name": "truncated fixture",
                "origin": "tests/cut",
                "kind": "json-array",
                "path": "cut/source.json",
                "rootKey": "data",
                "wordField": "ta",
            }
        ],
    ).sources[0]
    with pytest.raises(ValueError, match="unterminated"):
        list(read_source(tmp_path / "corpus" / "cut" / "source.json", source))


# --------------------------------------------------------------------------
# 2. Normalization + acceptance + the registry-driven merge
# --------------------------------------------------------------------------


def test_normalize_composes_to_nfc_and_trims() -> None:
    assert normalize(f"  {KO_DECOMPOSED}\n") == KO_COMPOSED
    assert len(segment(normalize(KO_DECOMPOSED))) == 1


@pytest.mark.parametrize(
    "word",
    [
        "",
        "abc",
        TAMIZH + "1",
        TAMIZH + "_" + KADHAI,
        "\u0be7\u0be8",  # Tamil digits are not letters
        "\u0b85",  # 1 ezhuthu, below minLength
        TAMIZH * 5,  # 15 ezhuthu, above maxLength
    ],
)
def test_accept_rejects_non_words_and_out_of_range_lengths(word: str) -> None:
    assert accept(word, 2, 12) is None


def test_accept_returns_the_row_6_segmentation() -> None:
    assert accept(TAMIZH, 2, 12) == segment(TAMIZH) == ["\u0ba4", "\u0bae\u0bbf", "\u0bb4\u0bcd"]


def test_a_word_in_two_sources_lists_both_and_sums_their_counts(tmp_path: Path) -> None:
    _write_source(tmp_path, "alpha", "source.csv", f"{TAMIZH},10\n{KADHAI},4\n")
    _write_source(tmp_path, "beta", "source.csv", f"{TAMIZH},5\n{MAZHAI},3\n")
    registry = _registry(tmp_path, [_delimited("alpha"), _delimited("beta")])

    words = {row.word: row for row in ingest(registry, tmp_path).wordlist.words}

    assert words[TAMIZH].sources == ["alpha", "beta"]
    assert words[KADHAI].sources == ["alpha"]
    assert words[MAZHAI].sources == ["beta"]
    # 10 + 5 outranks every single-source word, which is the whole point of
    # merging: attestation and frequency both push a word up.
    assert words[TAMIZH].freqRank == 1


def test_a_disabled_source_is_skipped_entirely(tmp_path: Path) -> None:
    _write_source(tmp_path, "alpha", "source.csv", f"{TAMIZH},10\n")
    disabled = _delimited("beta") | {"enabled": False}
    registry = _registry(tmp_path, [_delimited("alpha"), disabled])

    result = ingest(registry, tmp_path)

    # Its bytes are never read, so a disabled source needs no file on disk.
    assert [entry.id for entry in result.wordlist.provenance] == ["alpha"]


def test_counters_reconcile_with_every_rejection_and_duplicate(tmp_path: Path) -> None:
    _write_source(tmp_path, "alpha", "source.csv", f"{TAMIZH},10\nabc,9\n{KADHAI},4\n")
    _write_source(tmp_path, "beta", "source.csv", f"{TAMIZH},5\n{MAZHAI},3\n")
    registry = _registry(tmp_path, [_delimited("alpha"), _delimited("beta")])

    counters = ingest(registry, tmp_path).wordlist.counters

    assert counters.rowsIn == 5
    assert counters.rejected == 1  # "abc" is not Tamil
    assert counters.duplicates == 1  # TAMIZH seen again in beta
    assert counters.distinct == 3
    assert counters.rowsKept == 3


def test_the_frequency_floor_and_the_cap_report_what_they_dropped(
    tmp_path: Path,
) -> None:
    _write_source(
        tmp_path, "alpha", "source.csv", f"{TAMIZH},10\n{KADHAI},4\n{MAZHAI},1\n"
    )
    registry = _registry(
        tmp_path, [_delimited("alpha")], minTotalFrequency=4, maxWords=1
    )

    counters = ingest(registry, tmp_path).wordlist.counters

    assert counters.distinct == 3
    assert counters.belowFrequencyFloor == 1
    assert counters.capped == 1
    assert counters.rowsKept == 1


def test_the_json_reader_carries_categories_and_drops_the_suppressed_ones(
    tmp_path: Path,
) -> None:
    payload = {
        "data": [
            {"ta": TAMIZH, "word_frequency": 9, "category": ["nouns", "trees"]},
            {"ta": KADHAI, "word_frequency": 8, "category": ["nouns"]},
        ]
    }
    _write_source(tmp_path, "dict", "source.json", json.dumps(payload))
    registry = _registry(
        tmp_path,
        [
            {
                "id": "dict",
                "name": "dictionary fixture",
                "origin": "tests/dict",
                "kind": "json-array",
                "path": "dict/source.json",
                "rootKey": "data",
                "wordField": "ta",
                "countField": "word_frequency",
                "categoryField": "category",
            }
        ],
        dropCategories=["nouns"],
    )

    words = {row.word: row for row in ingest(registry, tmp_path).wordlist.words}

    assert words[TAMIZH].category == ["trees"]
    assert words[KADHAI].category is None


def test_provenance_records_the_exact_bytes_each_source_contributed(
    tmp_path: Path,
) -> None:
    text = f"{TAMIZH},10\nabc,9\n"
    _write_source(tmp_path, "alpha", "source.csv", text)
    registry = _registry(tmp_path, [_delimited("alpha")])

    entry = ingest(registry, tmp_path).wordlist.provenance[0]

    assert entry.bytes == len(text.encode("utf-8"))
    assert entry.rowsIn == 2
    assert entry.rowsKept == 1
    assert entry.path == "corpus/alpha/source.csv"


# --------------------------------------------------------------------------
# 3. Ranking + banding
# --------------------------------------------------------------------------


def test_order_is_by_merged_frequency_then_deterministic_on_ties() -> None:
    entries = [
        rank.CorpusEntry(word=MAZHAI, total=5),
        rank.CorpusEntry(word=TAMIZH, total=9),
        rank.CorpusEntry(word=KADHAI, total=5),
    ]

    ordered = [entry.word for entry in rank.order(entries)]

    assert ordered[0] == TAMIZH
    # The two 5s tie, so the tie-break decides - and decides the same way every
    # run, or the committed artifact would not be reproducible.
    assert ordered[1:] == [entry.word for entry in rank.order(list(reversed(entries)))][1:]


def test_bands_cut_at_the_configured_percentiles() -> None:
    assert rank.band_for(1, 100, _BANDS) == "common"
    assert rank.band_for(10, 100, _BANDS) == "common"
    assert rank.band_for(11, 100, _BANDS) == "mid"
    assert rank.band_for(50, 100, _BANDS) == "mid"
    assert rank.band_for(51, 100, _BANDS) == "rare"
    assert rank.band_for(100, 100, _BANDS) == "rare"


def test_floor_and_cap_are_pure_and_report_their_drops() -> None:
    entries = [
        rank.CorpusEntry(word=TAMIZH, total=9),
        rank.CorpusEntry(word=KADHAI, total=4),
        rank.CorpusEntry(word=MAZHAI, total=1),
    ]

    above, dropped = rank.apply_floor(entries, 4)
    assert [entry.word for entry in above] == [TAMIZH, KADHAI]
    assert dropped == 1

    capped, cut = rank.apply_cap(above, 1)
    assert [entry.word for entry in capped] == [TAMIZH]
    assert cut == 1
    assert rank.apply_cap(above, None) == (list(above), 0)


def test_render_is_deterministic_and_round_trips_through_the_model(
    tmp_path: Path,
) -> None:
    _write_source(tmp_path, "alpha", "source.csv", f"{TAMIZH},10\n{KADHAI},4\n")
    wordlist = ingest(_registry(tmp_path, [_delimited("alpha")]), tmp_path).wordlist

    text = render(wordlist)

    assert text == render(wordlist)
    assert text.endswith("\n")
    reloaded = MasterWordlist.model_validate_json(text)
    assert [row.word for row in reloaded.words] == [row.word for row in wordlist.words]


# --------------------------------------------------------------------------
# 4. Contract tier - the shared fixtures
# --------------------------------------------------------------------------


def _fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_master_wordlist_accepts_the_shared_valid_fixture() -> None:
    model = MasterWordlist.model_validate_json(_fixture("master-wordlist_valid.json"))
    assert model.counters.rowsKept == len(model.words)


def test_master_wordlist_rejects_the_shared_malformed_fixture() -> None:
    # Its first row's ezhuthu does not rejoin to its word, and its second row has
    # freqRank 0, an unknown band, and no source.
    with pytest.raises(ValidationError):
        MasterWordlist.model_validate_json(_fixture("master-wordlist_invalid.json"))


def test_corpus_sources_accepts_the_shared_valid_fixture() -> None:
    registry = CorpusSources.model_validate_json(_fixture("corpus-sources_valid.json"))
    assert [source.id for source in registry.sources if source.enabled] == [
        "demo-frequency"
    ]


def test_corpus_sources_rejects_the_shared_malformed_fixture() -> None:
    # An absolute corpusRoot, an inverted length range, inverted band cuts, and a
    # delimited source carrying json-array mappings - each a silent-misread trap.
    with pytest.raises(ValidationError):
        CorpusSources.model_validate_json(_fixture("corpus-sources_invalid.json"))


def test_the_committed_registry_validates() -> None:
    registry = load_registry(_REPO_ROOT / "config" / "corpus-sources.json")
    assert len(registry.sources) >= 1
    assert any(source.enabled for source in registry.sources)


# --------------------------------------------------------------------------
# 5. The integrity Oracle, over the real committed artifact
# --------------------------------------------------------------------------


def test_the_committed_master_wordlist_is_whole() -> None:
    wordlist = MasterWordlist.model_validate_json(_MASTER.read_text(encoding="utf-8"))
    counters = wordlist.counters

    # No silent drops: every row read is accounted for as kept, rejected,
    # merged into a duplicate, floored, or capped.
    assert counters.rowsIn - counters.rejected - counters.duplicates == counters.distinct
    assert (
        counters.distinct - counters.belowFrequencyFloor - counters.capped
        == counters.rowsKept
    )
    assert counters.rowsKept == len(wordlist.words)
    assert counters.rowsIn == sum(entry.rowsIn for entry in wordlist.provenance)

    seen: set[str] = set()
    for position, row in enumerate(wordlist.words, start=1):
        assert row.ezhuthu == segment(row.word), row.word
        assert "".join(row.ezhuthu) == row.word
        assert row.length == len(row.ezhuthu)
        assert row.freqBand in {"common", "mid", "rare"}
        assert row.freqRank == position
        assert row.word not in seen
        seen.add(row.word)
