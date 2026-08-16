"""Contract-tier tests for the Row 7 core schemas and the Row 3 lexicon contracts.

Real fixtures, no mocks (Holy Law #7). For each of the six core contracts (plus
copy) the Pydantic model ACCEPTS the shared valid fixture and REJECTS the shared
malformed one - the SAME bytes the frontend ajv test loads
(``frontend/src/contracts/core-schemas.test.ts``), so accept/reject is proven on
both sides of the boundary (the contract Oracle). The committed config files must
validate too, and the derived-key helper is unit-tested.

The lexicon block at the end proves the reconciliation Oracle and the reader
contract instead: neither lexicon schema is registered in the frontend's load
boundary (both are build-time surfaces the browser never fetches), so there is
no ajv half to share fixture bytes with, and its payloads are built from the
real ezhuthu library rather than read from disk.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import pytest
from pydantic import ValidationError

from yen_tamizh_backend.contracts import (
    LEXICON_CHANGELOG,
    LEXICON_SOURCES_CHANGELOG,
    LEXICON_SOURCES_VERSION,
    LEXICON_VERSION,
    PARTITION_KEYS,
    REGISTRY,
    AnagramPuzzle,
    AppConfig,
    BankIndex,
    Copy,
    EventEnvelope,
    Lexicon,
    LexiconEntry,
    LexiconSources,
    PartOfSpeech,
    PuzzleFile,
    Save,
    WordClass,
)
from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.save import compute_day_key
from yen_tamizh_backend.ezhuthu import BASE_ROMAN, segment

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURES = _REPO_ROOT / "datasets" / "fixtures" / "contracts"
_CONFIG = _REPO_ROOT / "config"

# Each core contract paired with its fixture stem. The stems match the shared
# datasets/fixtures/contracts/<stem>_{valid,invalid}.json the frontend loads.
_CORE: tuple[tuple[type[SchemaModel], str], ...] = (
    (AppConfig, "app-config"),
    (EventEnvelope, "event-envelope"),
    (Save, "save"),
    (PuzzleFile, "puzzle-file"),
    (BankIndex, "bank-index"),
    (AnagramPuzzle, "anagram-puzzle"),
    (Copy, "copy"),
)


def _load(path: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return data


@pytest.mark.parametrize(("model", "stem"), _CORE)
def test_model_accepts_valid_fixture(model: type[SchemaModel], stem: str) -> None:
    # Oracle acceptance half: the shared valid fixture validates against Pydantic.
    model.model_validate(_load(_FIXTURES / f"{stem}_valid.json"))


@pytest.mark.parametrize(("model", "stem"), _CORE)
def test_model_rejects_malformed_fixture(model: type[SchemaModel], stem: str) -> None:
    # Oracle rejection half: the SAME malformed bytes the frontend ajv test
    # rejects are rejected here too (missing/mistyped required field).
    with pytest.raises(ValidationError):
        model.model_validate(_load(_FIXTURES / f"{stem}_invalid.json"))


def test_app_config_file_validates() -> None:
    # The committed defaults must satisfy the schema (a fresh clone runs on them).
    AppConfig.model_validate(_load(_CONFIG / "app-config.json"))


def test_copy_file_validates() -> None:
    Copy.model_validate(_load(_CONFIG / "copy.json"))


def test_compute_day_key_joins_value_fields() -> None:
    # The derived key is rebuilt from its value fields, never trusted from storage.
    assert (
        compute_day_key("2026-08-13", "daily", "anagram", "ta-core")
        == "2026-08-13|daily|anagram|ta-core"
    )


# --------------------------------------------------------------------------
# The lexicon contracts (Row 3).
#
# Payloads are BUILT from the real ezhuthu library rather than hand-typed, so a
# fixture cannot quietly disagree with the segmentation the contract validates
# against (Holy Law #7 - real implementations, no mocks). Tamil is written with
# \uXXXX escapes so the source file's own normalization form cannot change what
# the test asserts.
# --------------------------------------------------------------------------

# வாய்ப்பு - a headword from the plan's reference classification table.
_WORD = "\u0bb5\u0bbe\u0baf\u0bcd\u0baa\u0bcd\u0baa\u0bc1"
_EZHUTHU = segment(_WORD)
_BASE = _WORD[0]
_BASE_HEX = f"{ord(_BASE):04x}"
_SHA = "a" * 64


def _entry(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "word": _WORD,
        "length": len(_EZHUTHU),
        "wordClass": "headword",
        "frequency": 42,
    }
    row.update(overrides)
    return row


def _by_class(**counts: int) -> dict[str, int]:
    buckets = dict.fromkeys(get_args(WordClass), 0)
    buckets.update(counts)
    return buckets


def _counters(published: int = 1, **counts: int) -> dict[str, object]:
    classified = _by_class(**(counts or {"headword": 1}))
    shown = dict.fromkeys(get_args(WordClass), 0)
    shown["headword"] = published
    return {
        "classified": {"rows": sum(classified.values()), "byClass": classified},
        "published": {"rows": sum(shown.values()), "byClass": shown},
    }


def _meta(**overrides: object) -> dict[str, object]:
    doc: dict[str, object] = {
        "version": LEXICON_VERSION,
        "changelog": [entry.model_dump() for entry in LEXICON_CHANGELOG],
        "partitionKeys": list(PARTITION_KEYS),
        "provenance": [
            {
                "id": "en-ta-dictionary",
                "name": "English-Tamil dictionary",
                "origin": "yen-tamizh_OLD src/dictionary/raw/t1.json",
                "path": "datasets/lexicon/sources/en-ta-dictionary/source.json",
                "bytes": 1024,
                "sha256": _SHA,
                "observations": 56856,
                "facts": 54156,
            }
        ],
        "counters": _counters(),
        "partitions": [
            {
                "path": f"datasets/lexicon/by-class/headword-{_BASE_HEX}.ndjson",
                "wordClass": "headword",
                "baseFirstEzhuthu": _BASE_HEX,
                "rows": 1,
                "bytes": 256,
                "sha256": _SHA,
            }
        ],
        "ezhuthuIndex": {
            _BASE_HEX: {"ezhuthu": _BASE, "roman": BASE_ROMAN[_BASE], "kind": "uyirmei"}
        },
    }
    doc.update(overrides)
    return doc


def _source(**overrides: object) -> dict[str, object]:
    source: dict[str, object] = {
        "id": "spellcheck-wordlist",
        "name": "Nannul-rules validated Tamil word list",
        "origin": "yen-tamizh_OLD src/dictionary/intermediate/ta_words_v1.json",
        "role": "authority",
        "attestationTier": "enumerative",
        "kind": "json-array",
        "path": "datasets/lexicon/sources/spellcheck-wordlist/source.json",
        "bytes": 2048,
        "sha256": _SHA,
        "precedence": 30,
        "rootKey": "data",
        "elementKind": "string",
    }
    source.update(overrides)
    return source


def _frequency_source(**overrides: object) -> dict[str, object]:
    source: dict[str, object] = {
        "id": "opensubtitles-ta",
        "name": "OpenSubtitles 2018 Tamil word frequency",
        "origin": "hermitdave/FrequencyWords content/2018/ta/ta_full.txt",
        "role": "frequency",
        "kind": "delimited",
        "path": "datasets/corpus/opensubtitles-ta/source.txt",
        "bytes": 4096,
        "sha256": _SHA,
        "precedence": 31,
        "delimiter": " ",
        "wordColumn": 0,
        "countColumn": 1,
    }
    source.update(overrides)
    return source


def _registry(**overrides: object) -> dict[str, object]:
    # The frequency corpus rides along in every fixture registry: spokenSources
    # names a registered frequency source, so a registry without one could not
    # validate whatever else the caller is testing.
    named = overrides.pop("sources", [_source()])
    assert isinstance(named, list)
    doc: dict[str, object] = {
        "version": LEXICON_SOURCES_VERSION,
        "changelog": [entry.model_dump() for entry in LEXICON_SOURCES_CHANGELOG],
        "lexiconRoot": "datasets/lexicon",
        "outputs": ["ndjson"],
        "publishedClasses": ["headword"],
        "spokenSources": ["opensubtitles-ta"],
        "maxPartitionBytes": 34603008,
        "posAliases": {"noun": {"pos": ["noun"]}},
        "sources": [*named, _frequency_source()],
    }
    doc.update(overrides)
    return doc


def test_lexicon_entry_is_not_a_schema_model() -> None:
    # A data row must carry neither version nor changelog: repeating a schema
    # stamp on every NDJSON line is bytes a reader learns nothing from. That is
    # why LexiconEntry is a plain BaseModel and is absent from REGISTRY.
    assert not issubclass(LexiconEntry, SchemaModel)
    assert "lexicon-entry" not in {model.schema_name() for model in REGISTRY}
    with pytest.raises(ValidationError):
        LexiconEntry.model_validate(_entry(version=LEXICON_VERSION))


def test_lexicon_entry_accepts_a_minimal_row() -> None:
    row = LexiconEntry.model_validate(_entry())
    assert row.word == _WORD
    # Sparse columns are absent, not empty: model_dump(exclude_none=True) drops
    # None but keeps [], which is why none of them defaults to a list.
    assert "pos" not in row.model_dump(exclude_none=True)


def test_lexicon_entry_recomputes_the_length_from_the_word() -> None:
    # There is no ezhuthu column to trust, so the check is against the live
    # segmentation - which is a stronger statement than a stored list agreeing
    # with itself, and it is what keeps a corrupt row out at 12 bytes a row.
    assert "ezhuthu" not in LexiconEntry.model_fields
    with pytest.raises(ValidationError):
        LexiconEntry.model_validate(_entry(length=len(_EZHUTHU) + 1))
    with pytest.raises(ValidationError):
        LexiconEntry.model_validate(_entry(ezhuthu=list(_EZHUTHU)))


def test_lexicon_entry_rejects_an_empty_sparse_list() -> None:
    # min_length=1 is what makes "absent" the only way to say "no value".
    with pytest.raises(ValidationError):
        LexiconEntry.model_validate(_entry(pos=[]))


def test_lexicon_entry_rejects_an_unsorted_or_duplicated_union() -> None:
    with pytest.raises(ValidationError):
        LexiconEntry.model_validate(_entry(pos=["verb", "noun"]))
    with pytest.raises(ValidationError):
        LexiconEntry.model_validate(_entry(pos=["noun", "noun"]))


def test_lexicon_entry_binds_provenance_to_the_value_it_describes() -> None:
    # A category renders as a PAID hint, so a category with no provenance state
    # cannot be suppressed when it is unreviewed - the worst failure available.
    with pytest.raises(ValidationError):
        LexiconEntry.model_validate(_entry(categories=["birds"]))
    with pytest.raises(ValidationError):
        LexiconEntry.model_validate(_entry(categorySource="attested"))
    LexiconEntry.model_validate(
        _entry(categories=["birds"], categorySource="attested")
    )


def test_lexicon_entry_treats_the_tamil_meaning_pair_as_one_unit() -> None:
    # definitionTa and synonymsTa compete for ONE display slot, so one
    # provenance state describes whichever won.
    with pytest.raises(ValidationError):
        LexiconEntry.model_validate(_entry(synonymsTa=["\u0b85\u0bb0\u0b9a\u0bc1"]))
    LexiconEntry.model_validate(
        _entry(synonymsTa=["\u0b85\u0bb0\u0b9a\u0bc1"], meaningSource="authored")
    )


def test_part_of_speech_excludes_word_class_and_english_only_categories() -> None:
    # One fact, one home: a proper noun is a wordClass. And Tamil has
    # POSTpositions, so mirroring an English source's "preposition" would put a
    # category the language lacks into a contract that claims to describe it.
    members = set(get_args(PartOfSpeech))
    assert "properNoun" not in members
    assert "preposition" not in members
    assert "article" not in members
    assert "postposition" in members
    with pytest.raises(ValidationError):
        LexiconEntry.model_validate(_entry(pos=["properNoun"]))


def test_lexicon_meta_accepts_the_initial_mint() -> None:
    doc = Lexicon.model_validate(_meta())
    assert doc.version == LEXICON_VERSION
    assert doc.rowSchema is None


def test_lexicon_counters_require_a_bucket_for_every_word_class() -> None:
    thin = _by_class(headword=1)
    del thin["sandhiArtifact"]
    with pytest.raises(ValidationError):
        Lexicon.model_validate(
            _meta(
                counters={
                    "classified": {"rows": 1, "byClass": thin},
                    "published": {"rows": 1, "byClass": _by_class(headword=1)},
                }
            )
        )


def test_lexicon_counters_reject_an_unknown_word_class_bucket() -> None:
    with pytest.raises(ValidationError):
        Lexicon.model_validate(
            _meta(
                counters={
                    "classified": {
                        "rows": 1,
                        "byClass": _by_class(headword=1) | {"noun": 0},
                    },
                    "published": {"rows": 1, "byClass": _by_class(headword=1)},
                }
            )
        )


def test_a_withheld_class_is_counted_in_full_and_published_at_zero() -> None:
    # The two families are what make "nothing was discarded" checkable: the
    # classes this policy withholds keep their real size on the record, and the
    # published family carries a zero rather than a silence.
    doc = Lexicon.model_validate(_meta(counters=_counters(headword=1, inflected=99)))
    assert doc.counters.classified.byClass["inflected"] == 99
    assert doc.counters.published.byClass["inflected"] == 0
    assert doc.counters.classified.rows == 100
    assert doc.counters.published.rows == 1


def test_a_class_is_published_whole_or_withheld_whole() -> None:
    # A published count that is neither zero nor the classified count is rows
    # LOST between the classifier and the writer, which a single counter family
    # could not have told apart from rows withheld.
    with pytest.raises(ValidationError):
        Lexicon.model_validate(
            _meta(
                counters={
                    "classified": {"rows": 2, "byClass": _by_class(headword=2)},
                    "published": {"rows": 1, "byClass": _by_class(headword=1)},
                }
            )
        )


@pytest.mark.parametrize(
    "mutated",
    (
        pytest.param(
            {"rows": 1, "byClass": _by_class(headword=2)}, id="byClass-stops-summing"
        ),
        pytest.param(
            {"rows": 2, "byClass": _by_class(headword=1)}, id="rows-stops-matching"
        ),
        pytest.param(
            {"rows": 1, "byClass": _by_class(headword=0, colloquial=1)},
            id="partitions-disagree-class-by-class",
        ),
    ),
)
def test_mutating_one_class_count_breaks_the_reconciliation(
    mutated: dict[str, object],
) -> None:
    # THE ORACLE. sum(byClass) == counters.published.rows == the rows the
    # partition table declares. Move ONE class count and the document stops
    # validating, so a row lost between the classifier and the writer cannot
    # ship as a silent drop.
    Lexicon.model_validate(_meta())
    with pytest.raises(ValidationError):
        Lexicon.model_validate(
            _meta(
                counters={
                    "classified": {"rows": 1, "byClass": _by_class(headword=1)},
                    "published": mutated,
                }
            )
        )


def test_lexicon_partitions_decode_through_the_ezhuthu_index() -> None:
    # No globbing and no probe-and-fallback: a reader resolves a file from this
    # table alone, so a hex it cannot decode - or an entry no file uses - is a
    # document that describes something other than itself.
    Lexicon.model_validate(_meta())
    with pytest.raises(ValidationError):
        Lexicon.model_validate(_meta(ezhuthuIndex={}))
    with pytest.raises(ValidationError):
        Lexicon.model_validate(
            _meta(
                ezhuthuIndex={
                    "0b95": {"ezhuthu": _BASE, "roman": "k", "kind": "uyirmei"}
                }
            )
        )
    with pytest.raises(ValidationError):
        Lexicon.model_validate(
            _meta(
                ezhuthuIndex={
                    _BASE_HEX: {
                        "ezhuthu": _BASE,
                        "roman": BASE_ROMAN[_BASE],
                        "kind": "uyirmei",
                    },
                    "0b95": {"ezhuthu": "\u0b95", "roman": "k", "kind": "uyirmei"},
                }
            )
        )


def test_lexicon_declares_the_address_its_partitions_use() -> None:
    # A declared address nothing enforces is a comment wearing a field's
    # clothes, so the contract pins it - and changing the layout becomes a
    # contract change rather than a quiet one.
    assert tuple(PARTITION_KEYS) == ("wordClass", "baseFirstEzhuthu")
    with pytest.raises(ValidationError):
        Lexicon.model_validate(_meta(partitionKeys=["wordClass", "length"]))


def test_lexicon_carries_no_generated_at() -> None:
    # Identity is content-addressed through provenance[].sha256 plus the row
    # count; a wall clock would make every rebuild a diff.
    assert "generatedAt" not in Lexicon.model_fields
    with pytest.raises(ValidationError):
        Lexicon.model_validate(_meta(generatedAt="2026-08-14T00:00:00Z"))


def test_lexicon_sources_accepts_the_initial_mint() -> None:
    LexiconSources.model_validate(_registry())


def test_json_array_source_requires_an_explicit_element_kind() -> None:
    # No default: a defaulted "object" is exactly the silent assumption the
    # self-terminating element rule exists to prevent.
    with pytest.raises(ValidationError):
        LexiconSources.model_validate(
            _registry(sources=[_source(elementKind=None, wordField=None)])
        )


def test_string_element_kind_rejects_a_field_mapping() -> None:
    # A bare string element has no fields at all, so any field mapping on it is
    # a knob that silently does nothing - rejected, never ignored.
    for stray in ("wordField", "countField", "categoryField", "posField"):
        with pytest.raises(ValidationError):
            LexiconSources.model_validate(
                _registry(sources=[_source(**{stray: "word"})])
            )


def test_object_element_kind_requires_root_key_and_word_field() -> None:
    LexiconSources.model_validate(
        _registry(sources=[_source(elementKind="object", wordField="tamil")])
    )
    with pytest.raises(ValidationError):
        LexiconSources.model_validate(_registry(sources=[_source(elementKind="object")]))


def test_element_kind_is_forbidden_on_every_other_kind() -> None:
    for kind, extra in (
        ("delimited", {"delimiter": " ", "wordColumn": 0}),
        ("jsonl", {"wordField": "word"}),
    ):
        LexiconSources.model_validate(
            _registry(
                sources=[
                    _source(kind=kind, rootKey=None, elementKind=None, **extra)
                ]
            )
        )
        with pytest.raises(ValidationError):
            LexiconSources.model_validate(
                _registry(
                    sources=[
                        _source(
                            kind=kind, rootKey=None, elementKind="object", **extra
                        )
                    ]
                )
            )


def test_has_header_is_a_stray_knob_on_every_json_kind() -> None:
    # hasHeader carries a non-None default, so "is not None" cannot tell an
    # assertion from the default - which is how a knob that silently does
    # nothing survives. Only a True value is an assertion, and on a JSON kind
    # nothing reads it.
    with pytest.raises(ValidationError):
        LexiconSources.model_validate(_registry(sources=[_source(hasHeader=True)]))
    with pytest.raises(ValidationError):
        LexiconSources.model_validate(
            _registry(
                sources=[
                    _source(
                        kind="jsonl",
                        rootKey=None,
                        elementKind=None,
                        wordField="word",
                        hasHeader=True,
                    )
                ]
            )
        )


def test_lexicon_sources_reject_a_shared_precedence() -> None:
    # Precedence must be a TOTAL order, or the source that wins a single-slot
    # value is decided by array position after all.
    with pytest.raises(ValidationError):
        LexiconSources.model_validate(
            _registry(sources=[_source(), _source(id="huggingface-wordlist")])
        )


def test_pos_alias_requires_a_destination() -> None:
    # Every raw census tag lands somewhere: a pos member, word-class evidence,
    # or an explicit named reject. A tag with no destination is the silent drop
    # the registry exists to prevent.
    with pytest.raises(ValidationError):
        LexiconSources.model_validate(_registry(posAliases={"noun": {}}))
    with pytest.raises(ValidationError):
        LexiconSources.model_validate(
            _registry(posAliases={"symbol": {"pos": ["noun"], "reject": "notAWord"}})
        )
    LexiconSources.model_validate(
        _registry(
            posAliases={
                # The four destination kinds the Row 4 census forces.
                "noun plural": {"pos": ["noun"], "wordClassEvidence": ["inflected"]},
                "name": {"wordClassEvidence": ["properNoun"]},
                "proverb": {"reject": "multiWordUnit"},
                # A recurring value in a structured POS field that names no
                # part of speech. A row with no POS prefix at all is NOT this -
                # it is a counted parse reject at extract.
                "romanization": {"reject": "notAPosLabel"},
            }
        )
    )


def test_word_class_evidence_cannot_assert_word_hood() -> None:
    # wordClassEvidence is NARROWER than WordClass on purpose. posAliases is
    # config, and C1's Nouns / Verbs / Adjectives tags route through it, so on
    # the wider type a one-line config edit would let a category source assert
    # word-hood - which only a role=authority / authored source's headword fact
    # may do. `unclassified` is refused for the mirror reason: nothing can be
    # evidence FOR the classifier's non-verdict.
    for verdict in ("headword", "unclassified"):
        with pytest.raises(ValidationError):
            LexiconSources.model_validate(
                _registry(posAliases={"Nouns": {"wordClassEvidence": [verdict]}})
            )
    LexiconSources.model_validate(
        _registry(posAliases={"prefix": {"wordClassEvidence": ["boundStem"]}})
    )
