"""Tests for the Row 9 derived layer: ranked master -> per-Game wordlists.

Real files and real fixtures throughout, no mocks (Holy Law #7). Tamil is written
with ``\\uXXXX`` escapes so this source stays ASCII (CLAUDE.md section 5) and so
the composed form of every test word is unambiguous. The escaped words are REAL
corpus words with their real ranks noted, so the selection tests exercise the
same shapes the committed artifact does.

Five things are proven:

1. **Selection** - length, band, and the co-anagram rule each reject for their
   own reason, and the counters reconcile against the master with no silent
   drops.
2. **Determinism** - ``rebuild`` writes byte-identical output from identical
   input, and the COMMITTED ``anagram.json`` is exactly what a fresh rebuild from
   the committed master produces. That second assertion is the hand-edit gate: a
   derived set is a build artifact, so any hand edit fails here.
3. **The Oracle** - over the REAL committed artifact: every row's ezhuthu
   multiset is shared with at least one OTHER master word, so an unscramble is
   never trivially the only arrangement.
4. **Coverage + schema** - the committed set is non-empty at every target ezhuthu
   length and validates row-by-row against the contract.
5. **Rejection** - a malformed row, an incoherent selection, and a colliding
   registry all fail validation rather than being silently accepted.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from yen_tamizh_backend.contracts import DerivedWordlists, GameWordlist, MasterWordlist
from yen_tamizh_backend.contracts.derived_wordlists import DerivedSelection
from yen_tamizh_backend.contracts.game_wordlist import (
    DerivedCounters,
    GameWord,
    GameWordHints,
)
from yen_tamizh_backend.contracts.master_wordlist import MasterWord
from yen_tamizh_backend.corpus import derive
from yen_tamizh_backend.corpus.ingest import render as render_master
from yen_tamizh_backend.scripts.rebuild_wordlists import rebuild

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MASTER = _REPO_ROOT / "datasets" / "wordlists" / "master" / "words_ranked.json"
_REGISTRY = _REPO_ROOT / "config" / "derived-wordlists.json"
_ANAGRAM = _REPO_ROOT / "datasets" / "wordlists" / "derived" / "anagram.json"

# A real co-anagram pair: vaasal (doorway, rank 421) and savaal (challenge, rank
# 3385) are the same three ezhuthu in a different order. Both common band.
VAASAL = "\u0bb5\u0bbe\u0b9a\u0bb2\u0bcd"
SAVAAL = "\u0b9a\u0bb5\u0bbe\u0bb2\u0bcd"

# A real SOLITARY word: ithazh (petal, rank 1) has no anagram anywhere in the
# master, so requireCoAnagram must reject it however common it is.
ITHAZH = "\u0b87\u0ba4\u0bb4\u0bcd"

# A real 2-ezhuthu word (oru, rank 2) - inside the bands, outside the lengths.
ORU = "\u0b92\u0bb0\u0bc1"

_SHA = "0" * 64


def _master_word(word: str, rank_position: int, band: str) -> dict[str, Any]:
    """One master row, segmented the way the ingest segments (Row 6)."""
    from yen_tamizh_backend.ezhuthu import segment

    ezhuthu = segment(word)
    return {
        "word": word,
        "ezhuthu": ezhuthu,
        "length": len(ezhuthu),
        "freqRank": rank_position,
        "freqBand": band,
        "sources": ["test-source"],
    }


def _master(rows: list[dict[str, Any]]) -> MasterWordlist:
    """A valid master wordlist around the given rows (counters reconcile)."""
    total = len(rows)
    return MasterWordlist.model_validate(
        {
            "version": "2026-08-13",
            "changelog": [
                {"version": "2026-08-13", "change": "test master", "why": "test"}
            ],
            "generatedAt": "2026-08-13T00:00:00Z",
            "provenance": [
                {
                    "id": "test-source",
                    "name": "test source",
                    "origin": "test",
                    "path": "datasets/corpus/test-source/source.txt",
                    "bytes": 1,
                    "sha256": _SHA,
                    "rowsIn": total,
                    "rowsKept": total,
                }
            ],
            "counters": {
                "rowsIn": total,
                "rejected": 0,
                "duplicates": 0,
                "distinct": total,
                "belowFrequencyFloor": 0,
                "capped": 0,
                "rowsKept": total,
            },
            "words": rows,
        }
    )


def _sample_master() -> MasterWordlist:
    """A master holding one co-anagram pair, one solitary word, one short word."""
    return _master(
        [
            _master_word(VAASAL, 1, "common"),
            _master_word(ITHAZH, 2, "common"),
            _master_word(ORU, 3, "common"),
            _master_word(SAVAAL, 4, "rare"),
        ]
    )


def _spec(out: str, **selection: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "minLength": 3,
        "maxLength": 6,
        "bands": ["common", "mid"],
        "requireCoAnagram": True,
        "maxWords": None,
    }
    base.update(selection)
    return {"gameId": "anagram", "out": out, "selection": base}


@pytest.fixture(scope="module")
def committed_master() -> MasterWordlist:
    """The REAL committed master, parsed once for every Oracle in this module."""
    return derive.load_master(_MASTER)


@pytest.fixture(scope="module")
def committed_anagram() -> GameWordlist:
    """The REAL committed anagram set, validated against its contract."""
    return GameWordlist.model_validate_json(_ANAGRAM.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# 1. Selection
# --------------------------------------------------------------------------


def test_multiset_key_is_order_free_over_ezhuthu() -> None:
    from yen_tamizh_backend.ezhuthu import segment

    assert derive.multiset_key(segment(VAASAL)) == derive.multiset_key(segment(SAVAAL))
    assert derive.multiset_key(segment(VAASAL)) != derive.multiset_key(segment(ITHAZH))


def test_group_by_multiset_puts_anagrams_together() -> None:
    from yen_tamizh_backend.ezhuthu import segment

    groups = derive.group_by_multiset(_sample_master().words)
    assert sorted(groups[derive.multiset_key(segment(VAASAL))]) == sorted(
        [VAASAL, SAVAAL]
    )
    assert groups[derive.multiset_key(segment(ITHAZH))] == [ITHAZH]


def test_selection_rejects_by_length_band_and_co_anagram() -> None:
    master = _sample_master()
    groups = derive.group_by_multiset(master.words)
    selection = DerivedSelection(
        minLength=3, maxLength=6, bands=["common", "mid"], requireCoAnagram=True
    )

    kept, counters = derive.select(master, selection, groups)

    # vaasal alone survives: savaal is out of band, ithazh has no anagram, oru
    # is too short - one word rejected under each heading.
    assert [row.word for row in kept] == [VAASAL]
    assert counters.outsideLength == 1
    assert counters.outsideBand == 1
    assert counters.withoutCoAnagram == 1
    assert counters.rowsKept == 1
    assert counters.masterRows == 4


def test_co_anagram_rule_looks_at_the_whole_master_not_the_shortlist() -> None:
    """A rejected partner still supplies the tension - the language does, not the set."""
    master = _sample_master()
    groups = derive.group_by_multiset(master.words)
    kept, _ = derive.select(
        master,
        DerivedSelection(
            minLength=3, maxLength=6, bands=["common"], requireCoAnagram=True
        ),
        groups,
    )
    # savaal is rare and never reaches the output, yet vaasal is still keepable.
    assert [row.word for row in kept] == [VAASAL]


def test_selection_without_the_co_anagram_rule_keeps_solitary_words() -> None:
    master = _sample_master()
    groups = derive.group_by_multiset(master.words)
    kept, counters = derive.select(
        master,
        DerivedSelection(
            minLength=3, maxLength=6, bands=["common"], requireCoAnagram=False
        ),
        groups,
    )
    assert sorted(row.word for row in kept) == sorted([VAASAL, ITHAZH])
    assert counters.withoutCoAnagram == 0


def test_cap_trims_the_lowest_ranked_and_reports_what_it_cut() -> None:
    master = _master(
        [
            _master_word(VAASAL, 1, "common"),
            _master_word(SAVAAL, 2, "common"),
        ]
    )
    groups = derive.group_by_multiset(master.words)
    kept, counters = derive.select(
        master,
        DerivedSelection(
            minLength=3,
            maxLength=6,
            bands=["common"],
            requireCoAnagram=True,
            maxWords=1,
        ),
        groups,
    )
    assert [row.word for row in kept] == [VAASAL]
    assert counters.capped == 1
    assert counters.rowsKept == 1


def test_rows_stay_in_master_rank_order() -> None:
    master = _master(
        [
            _master_word(SAVAAL, 1, "common"),
            _master_word(VAASAL, 2, "common"),
        ]
    )
    groups = derive.group_by_multiset(master.words)
    kept, _ = derive.select(
        master,
        DerivedSelection(minLength=3, maxLength=6, bands=["common"]),
        groups,
    )
    assert [row.word for row in kept] == [SAVAAL, VAASAL]


# --------------------------------------------------------------------------
# 2. Determinism
# --------------------------------------------------------------------------


def _tmp_repo(tmp_path: Path, sets: list[dict[str, Any]]) -> Path:
    """A miniature repo root: a real master file plus a real registry file."""
    master_rel = "datasets/wordlists/master/words_ranked.json"
    master_path = tmp_path / master_rel
    master_path.parent.mkdir(parents=True)
    master_path.write_text(render_master(_sample_master()), encoding="utf-8", newline="\n")
    registry = tmp_path / "config" / "derived-wordlists.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        json.dumps(
            {
                "version": "2026-08-13",
                "changelog": [
                    {"version": "2026-08-13", "change": "test registry", "why": "test"}
                ],
                "masterPath": master_rel,
                "sets": sets,
            }
        ),
        encoding="utf-8",
    )
    return registry


def test_rebuild_writes_every_registered_set(tmp_path: Path) -> None:
    registry = _tmp_repo(
        tmp_path,
        [
            _spec("datasets/wordlists/derived/anagram.json"),
            {
                **_spec("datasets/wordlists/derived/other.json", requireCoAnagram=False),
                "gameId": "wordle",
            },
        ],
    )
    written = rebuild(registry, tmp_path)

    assert [path.name for path, _ in written] == ["anagram.json", "other.json"]
    assert all(path.exists() for path, _ in written)
    assert [wordlist.gameId for _, wordlist in written] == ["anagram", "wordle"]


def test_rebuild_is_byte_identical_across_runs(tmp_path: Path) -> None:
    registry = _tmp_repo(tmp_path, [_spec("datasets/wordlists/derived/anagram.json")])
    out = rebuild(registry, tmp_path)[0][0]
    first = out.read_bytes()
    rebuild(registry, tmp_path)
    assert out.read_bytes() == first


def test_artifacts_carry_no_wall_clock(committed_anagram: GameWordlist) -> None:
    """A timestamp would make two runs over one master differ - that is the point."""
    raw = json.loads(_ANAGRAM.read_text(encoding="utf-8"))
    assert "generatedAt" not in raw
    # The master's own instant is pinned instead, so the input is still traceable.
    assert committed_anagram.source.generatedAt.endswith("Z")


def test_committed_anagram_set_is_exactly_what_a_rebuild_produces(
    committed_master: MasterWordlist,
) -> None:
    """The hand-edit gate: a derived set is a build artifact, never edited."""
    registry = derive.load_registry(_REGISTRY)
    spec = next(entry for entry in registry.sets if entry.gameId == "anagram")
    source = derive.describe_source(committed_master, _MASTER, registry.masterPath)
    groups = derive.group_by_multiset(committed_master.words)

    rebuilt = derive.render(derive.derive(committed_master, source, spec, groups))

    assert rebuilt == _ANAGRAM.read_text(encoding="utf-8")


def test_committed_set_pins_the_master_it_was_cut_from(
    committed_anagram: GameWordlist,
) -> None:
    from yen_tamizh_backend.corpus.artifact import sha256_of

    digest, _ = sha256_of(_MASTER)
    assert committed_anagram.source.sha256 == digest


def test_master_render_survives_the_shared_renderer(
    committed_master: MasterWordlist,
) -> None:
    """The Row 8 artifact still renders byte-for-byte after the renderer moved."""
    assert render_master(committed_master) == _MASTER.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# 3. The Oracle: every committed row has a co-anagram in the master
# --------------------------------------------------------------------------


def test_every_committed_row_can_be_rearranged_into_another_real_word(
    committed_master: MasterWordlist, committed_anagram: GameWordlist
) -> None:
    groups = derive.group_by_multiset(committed_master.words)

    solitary: list[str] = []
    for row in committed_anagram.words:
        members = groups[derive.multiset_key(row.ezhuthu)]
        if len(members) < 2:
            solitary.append(row.word)
        else:
            assert row.word in members

    assert solitary == [], f"{len(solitary)} rows have no co-anagram"
    assert committed_anagram.words, "the anagram set is empty"


def test_committed_counters_account_for_every_master_row(
    committed_anagram: GameWordlist,
) -> None:
    counters = committed_anagram.counters
    assert counters.masterRows == (
        counters.outsideLength
        + counters.outsideBand
        + counters.withoutCoAnagram
        + counters.capped
        + counters.rowsKept
    )
    assert counters.rowsKept == len(committed_anagram.words)


# --------------------------------------------------------------------------
# 4. Coverage + schema over the real artifact
# --------------------------------------------------------------------------


def test_committed_set_is_non_empty_at_every_target_length(
    committed_anagram: GameWordlist,
) -> None:
    selection = committed_anagram.selection
    lengths = {len(row.ezhuthu) for row in committed_anagram.words}
    for target in range(selection.minLength, selection.maxLength + 1):
        assert target in lengths, f"no {target}-ezhuthu word in the anagram set"


def test_every_committed_row_validates_against_the_contract(
    committed_anagram: GameWordlist,
) -> None:
    from yen_tamizh_backend.ezhuthu import segment

    bands = set(committed_anagram.selection.bands)
    for row in committed_anagram.words:
        # Re-validating each row proves the file's rows are the contract's rows,
        # not merely that the envelope parsed.
        GameWord.model_validate(row.model_dump())
        assert row.ezhuthu == segment(row.word)
        assert row.freqBand in bands
        assert row.hints is not None
        assert row.hints.first_ezhuthu == row.ezhuthu[0]
        assert row.hints.length == len(row.ezhuthu)


def test_committed_rows_are_unique(committed_anagram: GameWordlist) -> None:
    words = [row.word for row in committed_anagram.words]
    assert len(set(words)) == len(words)


def test_committed_set_omits_an_invented_category(committed_anagram: GameWordlist) -> None:
    """A Tamil category name is player-facing copy, so no row may invent one."""
    raw = json.loads(_ANAGRAM.read_text(encoding="utf-8"))
    for row in raw["words"]:
        assert set(row["hints"]) == {"first_ezhuthu", "length"}


def test_registered_output_paths_are_relative_and_posix() -> None:
    registry = derive.load_registry(_REGISTRY)
    for spec in registry.sets:
        assert not spec.out.startswith("/")
        assert "\\" not in spec.out
    assert not registry.masterPath.startswith("/")


# --------------------------------------------------------------------------
# 5. Rejection
# --------------------------------------------------------------------------


def test_a_row_whose_ezhuthu_do_not_rejoin_is_rejected() -> None:
    with pytest.raises(ValidationError, match="does not rejoin"):
        GameWord(word=VAASAL, ezhuthu=["\u0b95"], freqBand="common")


def test_a_row_whose_hints_disagree_with_its_ezhuthu_is_rejected() -> None:
    from yen_tamizh_backend.ezhuthu import segment

    ezhuthu = segment(VAASAL)
    with pytest.raises(ValidationError, match="first_ezhuthu"):
        GameWord(
            word=VAASAL,
            ezhuthu=ezhuthu,
            freqBand="common",
            hints=GameWordHints(first_ezhuthu=ezhuthu[1], length=len(ezhuthu)),
        )
    with pytest.raises(ValidationError, match="hints.length"):
        GameWord(
            word=VAASAL,
            ezhuthu=ezhuthu,
            freqBand="common",
            hints=GameWordHints(first_ezhuthu=ezhuthu[0], length=len(ezhuthu) + 1),
        )


def test_an_unknown_row_field_is_rejected() -> None:
    from yen_tamizh_backend.ezhuthu import segment

    with pytest.raises(ValidationError):
        GameWord.model_validate(
            {
                "word": VAASAL,
                "ezhuthu": segment(VAASAL),
                "freqBand": "common",
                "category_ta": "\u0bae\u0bb0\u0bae\u0bcd",
            }
        )


def test_counters_that_do_not_reconcile_are_rejected() -> None:
    with pytest.raises(ValidationError, match="masterRows"):
        DerivedCounters(
            masterRows=10,
            outsideLength=1,
            outsideBand=1,
            withoutCoAnagram=1,
            capped=0,
            rowsKept=1,
        )


def test_a_wordlist_whose_count_disagrees_with_its_rows_is_rejected() -> None:
    from yen_tamizh_backend.ezhuthu import segment

    with pytest.raises(ValidationError, match="rowsKept"):
        GameWordlist.model_validate(
            {
                "version": "2026-08-13",
                "changelog": [
                    {"version": "2026-08-13", "change": "test", "why": "test"}
                ],
                "gameId": "anagram",
                "source": {
                    "path": "datasets/wordlists/master/words_ranked.json",
                    "version": "2026-08-13",
                    "generatedAt": "2026-08-13T00:00:00Z",
                    "sha256": _SHA,
                    "rows": 2,
                },
                "selection": {
                    "minLength": 3,
                    "maxLength": 6,
                    "bands": ["common"],
                    "requireCoAnagram": True,
                },
                "counters": {
                    "masterRows": 2,
                    "outsideLength": 0,
                    "outsideBand": 0,
                    "withoutCoAnagram": 0,
                    "capped": 0,
                    "rowsKept": 2,
                },
                "words": [
                    {
                        "word": VAASAL,
                        "ezhuthu": segment(VAASAL),
                        "freqBand": "common",
                    }
                ],
            }
        )


def test_an_incoherent_selection_is_rejected() -> None:
    with pytest.raises(ValidationError, match="minLength"):
        DerivedSelection(minLength=7, maxLength=3, bands=["common"])
    with pytest.raises(ValidationError, match="repeated"):
        DerivedSelection(minLength=3, maxLength=6, bands=["common", "common"])
    with pytest.raises(ValidationError):
        DerivedSelection(minLength=3, maxLength=6, bands=[])


def test_two_sets_writing_to_one_path_are_rejected() -> None:
    base = {
        "version": "2026-08-13",
        "changelog": [{"version": "2026-08-13", "change": "test", "why": "test"}],
        "masterPath": "datasets/wordlists/master/words_ranked.json",
    }
    with pytest.raises(ValidationError, match="repeated out"):
        DerivedWordlists.model_validate(
            {
                **base,
                "sets": [
                    _spec("datasets/wordlists/derived/anagram.json"),
                    {
                        **_spec("datasets/wordlists/derived/anagram.json"),
                        "gameId": "wordle",
                    },
                ],
            }
        )
    with pytest.raises(ValidationError, match="repeated gameId"):
        DerivedWordlists.model_validate(
            {
                **base,
                "sets": [
                    _spec("datasets/wordlists/derived/anagram.json"),
                    _spec("datasets/wordlists/derived/other.json"),
                ],
            }
        )


def test_an_absolute_output_path_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DerivedWordlists.model_validate(
            {
                "version": "2026-08-13",
                "changelog": [
                    {"version": "2026-08-13", "change": "test", "why": "test"}
                ],
                "masterPath": "datasets/wordlists/master/words_ranked.json",
                "sets": [_spec("/tmp/anagram.json")],
            }
        )


def test_the_committed_registry_validates() -> None:
    registry = derive.load_registry(_REGISTRY)
    assert [spec.gameId for spec in registry.sets] == ["anagram"]
    assert registry.masterPath == "datasets/wordlists/master/words_ranked.json"


def test_a_missing_master_fails_loudly(tmp_path: Path) -> None:
    registry = _tmp_repo(tmp_path, [_spec("datasets/wordlists/derived/anagram.json")])
    shutil.rmtree(tmp_path / "datasets")
    with pytest.raises(FileNotFoundError):
        rebuild(registry, tmp_path)
