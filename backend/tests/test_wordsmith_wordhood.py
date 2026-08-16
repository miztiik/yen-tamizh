"""Tests for the word-hood CLASSIFIER (Row 9).

Three halves, tested three different ways on purpose:

- **THE ORACLE** runs the cascade over the committed 200-row golden fixture and
  byte-compares its verdicts against the committed expected-output file. It
  needs no store, no connection and no raw source, so it runs in CI - which is
  the whole point. A classifier that could only be exercised against a 1.8 GB
  gitignored store would have no regression gate at all, and the second half of
  the Oracle - that not one row hand-labelled ``sandhiArtifact``,
  ``suspectedTypo``, ``boundStem`` or ``properNoun`` comes out ``headword`` -
  is the predicate Row 12's serving gate rests on;
- **THE CASCADE'S PROPERTIES** are asserted directly on the pure function:
  that ``zipf`` cannot change a verdict, that a NULL ``neighbour`` cannot
  produce an accusation, that the evidence priority does not depend on the
  order evidence arrives in;
- **THE STAGE** is asserted over a real store built by running the REAL
  extractor, the REAL stage and the REAL enrich over the committed byte-exact
  fixture slices under ``datasets/fixtures/lexicon/``. No mocks (Holy Law #7),
  no raw sources, so this runs in CI too.

Tamil is written with ``\\uXXXX`` escapes here and in both fixtures so this
file's own normalization form cannot change what it asserts.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from _lexicon_workspace import source_bytes
from yen_tamizh_backend.contracts.lexicon import WordClass
from yen_tamizh_backend.contracts.lexicon_sources import (
    ATTESTING_ROLES,
    LexiconSource,
    LexiconSources,
    WordClassEvidence,
)
from yen_tamizh_backend.contracts.wordhood import Wordhood
from yen_tamizh_backend.wordsmith.enrich import enrich, load_config, reclassify
from yen_tamizh_backend.wordsmith.extract import extract, load_registry, sha256_of
from yen_tamizh_backend.wordsmith.signals_exact import SignalContext, orthotactic_score
from yen_tamizh_backend.wordsmith.stage import stage
from yen_tamizh_backend.wordsmith.store import (
    SIGNAL_COLUMNS,
    canonical_dump,
    derived_epoch,
    open_store,
    stage_epoch,
)
from yen_tamizh_backend.wordsmith.wordhood import (
    EVIDENCE_TABLE,
    SIGNAL_ARGUMENTS,
    WORD_CLASSES,
    Surface,
    asserted,
    classify_surface,
    discoveries,
    distribution,
    is_discovery,
    parse_evidence,
    prepare_evidence,
    tally,
    tier_one_sources,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = _REPO_ROOT / "config" / "lexicon-sources.json"
_CONFIG_PATH = _REPO_ROOT / "config" / "wordhood.json"
_FIXTURES = _REPO_ROOT / "datasets" / "fixtures" / "lexicon"
_GOLDEN = _REPO_ROOT / "datasets" / "fixtures" / "wordhood_golden.jsonl"
_EXPECTED = _REPO_ROOT / "datasets" / "fixtures" / "wordhood_expected.jsonl"

REGISTRY = load_registry(_REGISTRY_PATH)
CONFIG = load_config(_CONFIG_PATH)

# The vocabulary a SOURCE may assert, taken from the contract rather than
# restated. Deliberately narrower than ``WordClass``.
EVIDENCE_CLASSES: tuple[WordClassEvidence, ...] = get_args(WordClassEvidence)

# The classes Row 12 must never see wearing a headword's badge. A surface in any
# of them is not a word a player can be asked to produce, and the served set is
# cut on ``wordClass == headword`` alone.
NEVER_A_HEADWORD: tuple[WordClass, ...] = (
    "sandhiArtifact",
    "suspectedTypo",
    "boundStem",
    "properNoun",
    "notAWord",
)

# What a hand-labelled ``notAWord`` row must NOT come out as. Row 9's Oracle
# asserted only that junk was not a headword, which is exactly why repeated
# aytham shipped as a loanword and a leading dot as an inflection.
NEVER_JUNK: tuple[WordClass, ...] = (
    "headword",
    "loanword",
    "suspectedTypo",
    "inflected",
    "unclassified",
)

# The rows a hand label calls never-servable and a TIER-1 DICTIONARY calls an
# entry. `asura` is the stem of `asuran` and `master-dictionary` lists it, with
# nothing else said about it - exactly as it lists 87,611 real headwords that
# Row 9's per-row entry test demoted. Trusting the dictionary recovers all of
# them and admits this one; no signal in the store separates them, and the
# morphological rule that would was measured and rejected in Row 9 for costing a
# real headword. Recorded here so a SECOND escape cannot arrive unnoticed.
SOURCE_ASSERTED_ESCAPES: tuple[str, ...] = ("\u0b85\u0b9a\u0bc1\u0bb0",)


# --------------------------------------------------------------------------
# The golden fixture
# --------------------------------------------------------------------------


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
    ]


GOLDEN: list[dict[str, Any]] = _read_jsonl(_GOLDEN)


def _surface(record: dict[str, Any]) -> Surface:
    """Rebuild one fixture row into the classifier's input, and nothing else.

    Deliberately explicit rather than a splat: the fixture is the Oracle's
    input, so the one place its keys are read is a place worth being able to
    read.
    """
    signals = record["signals"]
    return Surface(
        word=record["word"],
        attested=signals["attested"],
        orthotactic=signals["orthotactic"],
        breadth=signals["breadth"],
        nannulValid=signals["nannulValid"],
        knownVerbForm=signals["knownVerbForm"],
        ngram=signals["ngram"],
        neighbour=signals["neighbour"],
        zipf=signals["zipf"],
        entry=record["entry"],
        evidence=tuple(record["evidence"]),
    )


def _render_expected(records: list[dict[str, Any]]) -> bytes:
    """The expected file's bytes, exactly as the committed one is written."""
    lines = [
        json.dumps(
            {"word": record["word"], "wordClass": classify_surface(_surface(record), CONFIG)},
            ensure_ascii=True,
        )
        for record in records
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def test_the_classifier_output_byte_equals_the_committed_expected_file() -> None:
    # THE ORACLE, first predicate. Any change in classification is then an
    # explicit reviewed diff of this file rather than a number that drifted.
    assert _render_expected(GOLDEN) == _EXPECTED.read_bytes()


def test_no_row_the_classifier_INFERS_about_escapes_as_a_headword() -> None:
    # THE ORACLE, second predicate: headword precision over the classes that
    # must never be served. Row 12 cuts the served wordlist on
    # `wordClass == headword` and nothing else, so this is the predicate
    # standing between a player and a proper noun.
    #
    # Scoped to the rows the classifier reasons about ON ITS OWN - those no
    # tier-1 dictionary gave an entry. Where a dictionary DID give one, the
    # verdict is that source's claim rather than this layer's inference, and
    # the test below pins those by name instead of hiding them here.
    escaped = [
        record["word"]
        for record in GOLDEN
        if record["wordClass"] in NEVER_A_HEADWORD
        and not record["entry"]
        and classify_surface(_surface(record), CONFIG) == "headword"
    ]
    assert escaped == []


def test_every_never_servable_row_that_does_escape_is_a_dictionary_ENTRY() -> None:
    # The other half, and it is a ledger rather than a hole. Row 9a's entry test
    # trusts a tier-1 source's listing, which is what recovers 87,611 real
    # headwords the curated dictionary carries with nothing else said about
    # them - and the same trust admits the one stem that dictionary also lists.
    # No signal separates the two: `asura` and `aqkaram` have the same
    # attestation, breadth, shape and n-gram profile, and the morphological rule
    # that would tell them apart was measured and rejected in Row 9 because it
    # costs a real headword.
    #
    # So the escape is pinned by NAME, with its cause asserted: the row must
    # carry an ENTRY and no contrary source assertion. A second escape, or the
    # same one arriving by inference instead, fails here.
    escaped = {
        record["word"]: record
        for record in GOLDEN
        if record["wordClass"] in NEVER_A_HEADWORD
        and classify_surface(_surface(record), CONFIG) == "headword"
    }
    assert sorted(escaped) == sorted(SOURCE_ASSERTED_ESCAPES)
    for record in escaped.values():
        assert record["entry"] is True, record["word"]
        assert record["evidence"] == [], record["word"]


def test_every_hand_labelled_junk_row_is_classified_not_a_word() -> None:
    # THE ORACLE, third predicate (Row 9a). Row 9's second predicate only
    # asserted junk was not a HEADWORD, so scrape artifacts sailed through
    # wearing loanword, suspectedTypo and inflected instead. A confident
    # negative has to be reachable, or the class ships as decoration.
    wrong: list[tuple[str, str]] = []
    labelled = 0
    for record in GOLDEN:
        if record["wordClass"] != "notAWord":
            continue
        labelled += 1
        verdict = classify_surface(_surface(record), CONFIG)
        if verdict in NEVER_JUNK:
            wrong.append((record["word"], verdict))
    assert labelled > 0
    assert wrong == []


def test_the_fixture_covers_every_class() -> None:
    # Every class the contract names has at least one hand-labelled row, so a
    # newly minted verdict cannot ship with no fixture coverage.
    labelled = tally(record["wordClass"] for record in GOLDEN)
    assert all(count > 0 for count in labelled.values()), labelled


def test_the_fixture_holds_no_duplicate_surface() -> None:
    words = [record["word"] for record in GOLDEN]
    assert len(set(words)) == len(words)


def test_every_fixture_row_carries_all_eight_signals_under_their_own_names() -> None:
    # A fixture missing a signal would silently exercise a different classifier
    # from the one the store runs, and the byte-equality Oracle would still pass.
    for record in GOLDEN:
        assert tuple(record["signals"]) == SIGNAL_ARGUMENTS, record["word"]
    assert set(SIGNAL_ARGUMENTS) == set(SIGNAL_COLUMNS)


def test_every_fixture_row_is_labelled_with_a_real_word_class() -> None:
    for record in GOLDEN:
        assert record["wordClass"] in WORD_CLASSES, record["word"]
        assert record["profile"], record["word"]
        assert record["note"], record["word"]


def test_the_fixtures_orthotactic_column_is_not_hand_edited() -> None:
    # The fixture was drawn from the real store, so its orthotactic score must
    # be the score the shipped function computes for that surface under the
    # shipped weights. This is what stops a row being nudged into the class
    # somebody wanted for it.
    for record in GOLDEN:
        computed = orthotactic_score(record["word"], CONFIG.orthotactic)
        assert record["signals"]["orthotactic"] == pytest.approx(computed), record["word"]


def test_no_fixture_row_sits_on_a_configured_threshold() -> None:
    # The recorded ngram scores are rounded so the file stays readable. That is
    # only safe while no row sits within the rounding of a threshold, because
    # then the rounding itself would decide the verdict.
    floors = (CONFIG.classifier.discovery.minNgram, CONFIG.classifier.typo.maxNgram)
    for record in GOLDEN:
        for floor in floors:
            assert abs(record["signals"]["ngram"] - floor) > 1e-6, record["word"]


def test_the_expected_file_answers_for_exactly_the_golden_rows() -> None:
    expected = _read_jsonl(_EXPECTED)
    assert [row["word"] for row in expected] == [row["word"] for row in GOLDEN]
    for row in expected:
        assert row["wordClass"] in WORD_CLASSES


# --------------------------------------------------------------------------
# The cascade's properties, asserted on the pure function
# --------------------------------------------------------------------------

_PLAIN = Surface(
    word="\u0b95\u0ba3\u0bc8",
    attested=1.0,
    orthotactic=1.0,
    breadth=7.0,
    nannulValid=0.0,
    knownVerbForm=0.0,
    ngram=0.3,
    neighbour=None,
    zipf=None,
    entry=True,
    evidence=(),
)


@pytest.mark.parametrize("zipf", [None, -12.0, -1.0, 0.0, 1.0, 12.0])
def test_zipf_can_never_change_a_verdict(zipf: float | None) -> None:
    # Frequency and word-hood are independent axes - the founding observation of
    # this whole layer - so a rule keyed on a frequency residual would re-import
    # the exact defect the lexicon exists to remove. The doctrine is written
    # down in word-hood.md; this is the predicate that keeps it true.
    for record in GOLDEN:
        surface = _surface(record)
        assert classify_surface(replace(surface, zipf=zipf), CONFIG) == classify_surface(
            surface, CONFIG
        ), record["word"]


def test_a_null_neighbour_can_never_produce_a_typo_verdict() -> None:
    # NULL means nobody asked, which is a different fact from "we looked and
    # found nothing". A classifier reading the two the same would accuse every
    # surface Row 8's prune skipped - which includes every attested headword.
    candidate = replace(
        _PLAIN,
        attested=0.0,
        entry=False,
        nannulValid=0.0,
        breadth=1.0,
        ngram=0.001,
        neighbour=None,
    )
    assert classify_surface(candidate, CONFIG) == "unclassified"
    assert classify_surface(replace(candidate, neighbour=1.0), CONFIG) == "suspectedTypo"


def test_a_probable_sequence_is_not_accused_however_near_its_neighbour() -> None:
    # An agglutinative language generates real forms one ezhuthu apart by the
    # thousand. Without the n-gram ceiling the profile accuses ordinary Tamil.
    accused = replace(
        _PLAIN, attested=0.0, entry=False, breadth=1.0, ngram=0.001, neighbour=1.0
    )
    assert classify_surface(accused, CONFIG) == "suspectedTypo"
    probable = replace(accused, ngram=CONFIG.classifier.typo.maxNgram + 0.05)
    assert classify_surface(probable, CONFIG) == "unclassified"


def test_a_measured_zero_neighbour_is_not_a_typo_either() -> None:
    # Zero means the search ran and found no real word within its radius, which
    # is evidence AGAINST the surface being a slip of one.
    candidate = replace(
        _PLAIN, attested=0.0, entry=False, breadth=1.0, ngram=0.001, neighbour=0.0
    )
    assert classify_surface(candidate, CONFIG) != "suspectedTypo"


def test_the_evidence_verdict_does_not_depend_on_the_order_it_arrives_in() -> None:
    pair: tuple[Any, ...] = ("inflected", "properNoun")
    assert asserted(replace(_PLAIN, evidence=pair), CONFIG) == "properNoun"
    assert asserted(replace(_PLAIN, evidence=pair[::-1]), CONFIG) == "properNoun"


def test_asserted_evidence_outranks_a_bare_attestation() -> None:
    # A source that listed a name as an entry and a source that tagged it a name
    # are both right; only one of them is answering this question.
    named = replace(_PLAIN, evidence=("properNoun",))
    assert classify_surface(_PLAIN, CONFIG) == "headword"
    assert classify_surface(named, CONFIG) == "properNoun"


def test_a_bare_listing_is_not_enough_to_be_a_headword() -> None:
    # The whole reason the ENTRY test exists: three of the six authority sources
    # are word LISTS, and between them they attest a political party, a bound
    # stem and a pile of case-marked nouns.
    assert classify_surface(replace(_PLAIN, entry=False), CONFIG) != "headword"


def test_a_known_verb_form_is_inflected_by_evidence_not_by_inference() -> None:
    assert (
        classify_surface(replace(_PLAIN, entry=False, knownVerbForm=1.0), CONFIG)
        == "inflected"
    )


def test_an_entry_outranks_bulk_verb_form_membership() -> None:
    # A generated paradigm table necessarily contains the citation form, so if
    # form evidence outranked a lexicographic entry the classifier would delete
    # every verb headword in the language from the served set. Measured over the
    # real store: 2,239 surfaces are both.
    assert classify_surface(replace(_PLAIN, knownVerbForm=1.0), CONFIG) == "headword"


def test_the_discovery_profile_is_never_read_as_a_misspelling() -> None:
    # Decision 4: orthotactically clean, corroborated, well-formed and still
    # unattested is a modern word the dictionaries missed. It goes to the
    # enrichment queue, not to an accusation.
    found = replace(
        _PLAIN,
        attested=0.0,
        entry=False,
        breadth=float(CONFIG.classifier.discovery.minBreadth),
        ngram=CONFIG.classifier.discovery.minNgram + 0.1,
        neighbour=1.0,
    )
    assert is_discovery(found, CONFIG)
    assert classify_surface(found, CONFIG) == "unclassified"


def test_parse_evidence_refuses_a_value_no_contract_names() -> None:
    assert parse_evidence(None) == ()
    assert parse_evidence("") == ()
    assert parse_evidence("properNoun,inflected") == ("properNoun", "inflected")
    with pytest.raises(ValueError, match="wordClassEvidence"):
        parse_evidence("headword")


# --------------------------------------------------------------------------
# The precondition: is this a word at all?
# --------------------------------------------------------------------------

# Longer than `maxEzhuthu` and otherwise perfectly well-formed Tamil - the
# shape a scrape that lost its spaces produces. Two ezhuthu per repeat.
_OVERLONG = "\u0b95\u0ba3" * 14


def test_the_precondition_outranks_a_source_assertion() -> None:
    # A scraped paragraph a source tagged as a name is still a scraped
    # paragraph. A statement about the STRING outranks a statement about the
    # word it is not, which is why the precondition runs before phase 1.
    tagged = replace(_PLAIN, word=_OVERLONG, evidence=("properNoun",))
    assert classify_surface(tagged, CONFIG) == "notAWord"


def test_a_surface_at_the_length_ceiling_is_still_a_word() -> None:
    # The ceiling is a threshold, so the boundary is worth pinning: Tamil
    # compounds freely and a long compound is a word.
    ceiling = CONFIG.classifier.notAWord.maxEzhuthu
    at_the_line = replace(_PLAIN, word="\u0b95\u0ba3" * (ceiling // 2))
    assert classify_surface(at_the_line, CONFIG) == "headword"
    assert classify_surface(replace(_PLAIN, word=_OVERLONG), CONFIG) == "notAWord"


def test_one_ezhuthu_repeated_is_not_a_word_but_one_ezhuthu_alone_is() -> None:
    # `minDistinctEzhuthu` applies only above one ezhuthu: a one-ezhuthu word is
    # ordinary Tamil, and this test is what stops the rule eating it.
    assert classify_surface(replace(_PLAIN, word="\u0b85" * 4), CONFIG) == "notAWord"
    assert classify_surface(replace(_PLAIN, word="\u0b85"), CONFIG) == "headword"


def test_turning_the_non_tamil_rejection_off_restores_the_row_9_verdict() -> None:
    # The knob genuinely selects between two behaviours rather than switching
    # one off, so the `suspectedTypo` arm below it stays reachable.
    latin = replace(_PLAIN, word="\u0b95\u0ba3abc", entry=False)
    assert classify_surface(latin, CONFIG) == "notAWord"
    payload = _config_payload()
    payload["classifier"]["notAWord"]["rejectNonTamil"] = False
    assert classify_surface(latin, Wordhood.model_validate(payload)) == "suspectedTypo"


def test_not_a_word_is_a_confident_negative_and_unclassified_an_absent_one() -> None:
    # The two must stay distinct: collapsing them would destroy the only
    # counters that say whether the classifier works.
    assert "notAWord" in WORD_CLASSES
    assert "unclassified" in WORD_CLASSES
    junk = replace(_PLAIN, word="\u0b83" * 3, entry=False)
    unknown = replace(
        _PLAIN, attested=0.0, entry=False, breadth=1.0, ngram=0.5, neighbour=None
    )
    assert classify_surface(junk, CONFIG) == "notAWord"
    assert classify_surface(unknown, CONFIG) == "unclassified"


# --------------------------------------------------------------------------
# Row 9b - the notAWord veto: when a source says the unit is a LETTER
# --------------------------------------------------------------------------

# a (U+0B85) - the first letter of the Tamil alphabet, and the surface this
# veto exists to remove. Its SHAPE breaks no rule, so no threshold can refuse
# it; only a lexicographer's verdict can.
_LETTER_A = "\u0b85"


def test_a_source_s_denial_beats_the_headword_gate() -> None:
    # Every clause of the gate passes - the letter is a clean, entered, wholly
    # Tamil one-ezhuthu surface - and it is still not a word, because a
    # dictionary looked at it and said so.
    listed = replace(_PLAIN, word=_LETTER_A, entry=True, evidence=())
    assert classify_surface(listed, CONFIG) == "headword"
    denied = replace(listed, evidence=("notAWord",))
    assert classify_surface(denied, CONFIG) == "notAWord"


def test_a_denial_outranks_every_other_thing_a_source_could_say() -> None:
    # It answers a different question from the rest of the vocabulary: not what
    # KIND of word this is, but whether it is one. So it is ranked first, and
    # the ranking is what makes the verdict independent of fact order.
    assert CONFIG.classifier.evidencePriority[0] == "notAWord"
    for other in CONFIG.classifier.evidencePriority[1:]:
        both = replace(_PLAIN, word=_LETTER_A, evidence=("notAWord", other))
        reversed_order = replace(both, evidence=(other, "notAWord"))
        assert classify_surface(both, CONFIG) == "notAWord"
        assert classify_surface(reversed_order, CONFIG) == "notAWord"


def test_the_veto_is_not_a_length_rule() -> None:
    # nii, thii, puu, vaa - four ordinary one-ezhuthu Tamil words. Nothing about
    # being short refuses a surface; only a source's own verdict does.
    for word in ("\u0ba8\u0bc0", "\u0ba4\u0bc0", "\u0baa\u0bc2", "\u0bb5\u0bbe"):
        short = replace(_PLAIN, word=word, entry=True, evidence=())
        assert classify_surface(short, CONFIG) == "headword", word


def test_a_denial_is_a_negative_and_can_never_assert_word_hood() -> None:
    # The evidence vocabulary is deliberately narrower than WordClass so a
    # config edit cannot let a weak source assert word-hood. notAWord is
    # admissible on it precisely because it asserts none.
    assert "notAWord" in EVIDENCE_CLASSES
    assert "headword" not in EVIDENCE_CLASSES
    assert "unclassified" not in EVIDENCE_CLASSES


def _evidence_over(rows: list[tuple[str, str, str, str]], db: Path) -> dict[str, str]:
    """Run the real evidence collector over a store holding exactly ``rows``."""
    conn = open_store(db)
    try:
        conn.executemany(
            "INSERT INTO fact (source_id, word, attr, value, ordinal) "
            "VALUES (?, ?, ?, ?, 0)",
            rows,
        )
        prepare_evidence(SignalContext(conn=conn, registry=REGISTRY, config=CONFIG))
        return {
            str(word): str(values)
            for word, values in conn.execute(
                f"SELECT word, evidence FROM {EVIDENCE_TABLE} ORDER BY word"
            )
        }
    finally:
        conn.close()


def test_a_denial_stands_only_when_it_is_all_that_source_said(tmp_path: Path) -> None:
    # The Wiktionary extract files the vowel AA as a character in one row and as
    # a noun in another. The noun has to win, so a denial is dropped when the
    # SAME source also gave the SAME word a part of speech.
    letter = _LETTER_A
    both = "\u0b86"
    collected = _evidence_over(
        [
            ("wiktextract-ta", letter, "wordClassEvidence", "notAWord"),
            ("wiktextract-ta", both, "wordClassEvidence", "notAWord"),
            ("wiktextract-ta", both, "pos", "noun"),
        ],
        tmp_path / "denial.db",
    )
    assert collected == {letter: "notAWord"}


def test_one_source_s_denial_is_not_answered_by_another_source_s_listing(
    tmp_path: Path,
) -> None:
    # Asking per SOURCE is what keeps the cross-source veto: a bare word list
    # carrying the same letter says nothing about it, and a describing fact from
    # a DIFFERENT source is not the denying source changing its mind.
    letter = _LETTER_A
    collected = _evidence_over(
        [
            ("wiktextract-ta", letter, "wordClassEvidence", "notAWord"),
            ("ta-wiktionary-content", letter, "pos", "noun"),
            ("spellcheck-wordlist", letter, "headword", letter),
        ],
        tmp_path / "cross.db",
    )
    assert collected == {letter: "notAWord"}


# --------------------------------------------------------------------------
# The knobs
# --------------------------------------------------------------------------


def _config_payload() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return payload


def _source_payload(source_id: str) -> dict[str, Any]:
    for source in REGISTRY.sources:
        if source.id == source_id:
            return dict(source.model_dump(exclude_none=True))
    raise AssertionError(f"{source_id} is not registered")


def test_the_committed_config_validates() -> None:
    settings = Wordhood.model_validate(_config_payload()).classifier
    assert settings.notAWord.maxEzhuthu == 25
    assert settings.notAWord.minDistinctEzhuthu == 2
    assert settings.notAWord.rejectNonTamil is True


def test_a_partial_evidence_priority_is_refused() -> None:
    # An unranked assertion has no defined winner, and a verdict that depends on
    # which fact SQLite returned first is not a verdict.
    payload = _config_payload()
    payload["classifier"]["evidencePriority"] = ["properNoun", "inflected"]
    with pytest.raises(ValidationError, match="evidencePriority"):
        Wordhood.model_validate(payload)


def test_a_repeated_evidence_priority_is_refused() -> None:
    payload = _config_payload()
    priority = payload["classifier"]["evidencePriority"]
    payload["classifier"]["evidencePriority"] = [priority[0], *priority]
    with pytest.raises(ValidationError, match="evidencePriority"):
        Wordhood.model_validate(payload)


def test_the_retired_entry_attribute_knob_is_refused() -> None:
    # Row 9a replaced the per-row entry test with the source's declared tier, so
    # entryAttrs has no reader. `extra="forbid"` is what stops it lingering in a
    # config file as a knob that reads like a claim and changes nothing.
    payload = _config_payload()
    payload["classifier"]["entryAttrs"] = ["pos"]
    with pytest.raises(ValidationError):
        Wordhood.model_validate(payload)


@pytest.mark.parametrize("knob", ["maxEzhuthu", "minDistinctEzhuthu"])
def test_a_non_positive_not_a_word_threshold_is_refused(knob: str) -> None:
    payload = _config_payload()
    payload["classifier"]["notAWord"][knob] = 0
    with pytest.raises(ValidationError, match=knob):
        Wordhood.model_validate(payload)


def test_the_not_a_word_profile_is_required() -> None:
    # A missing precondition would classify junk as a real class in silence,
    # which is the defect this row exists to close.
    payload = _config_payload()
    del payload["classifier"]["notAWord"]
    with pytest.raises(ValidationError, match="notAWord"):
        Wordhood.model_validate(payload)


# --------------------------------------------------------------------------
# The source tier, which is what an ENTRY now means
# --------------------------------------------------------------------------


def test_every_source_that_may_assert_word_hood_declares_a_tier() -> None:
    for source in REGISTRY.sources:
        if source.role in ATTESTING_ROLES:
            assert source.attestationTier is not None, source.id
        else:
            assert source.attestationTier is None, source.id


def test_the_registry_names_a_lexicographic_and_an_enumerative_authority() -> None:
    # Both halves of the split have a real producer. A registry that was all one
    # tier would make the gate either vacuous or impossible.
    tiers = {
        source.attestationTier
        for source in REGISTRY.sources
        if source.role in ATTESTING_ROLES and source.enabled
    }
    assert tiers == {"lexicographic", "enumerative"}


def test_an_attesting_source_without_a_tier_is_refused() -> None:
    payload = _source_payload("master-dictionary")
    del payload["attestationTier"]
    with pytest.raises(ValidationError, match="lexicographic entry"):
        LexiconSource.model_validate(payload)


def test_a_tier_on_a_source_that_cannot_assert_word_hood_is_refused() -> None:
    # A field set where nothing reads it is a claim the config cannot keep.
    payload = _source_payload("opensubtitles-ta")
    payload["attestationTier"] = "lexicographic"
    with pytest.raises(ValidationError, match="nothing reads"):
        LexiconSource.model_validate(payload)


def test_the_bare_word_lists_are_the_enumerative_tier() -> None:
    # The four sources that emit a headword fact and nothing else. Between them
    # they attest a political party, a sitting politician and a bound stem, and
    # the whole point of the tier is that none of that can be a headword.
    listings = {
        source.id
        for source in REGISTRY.sources
        if source.attestationTier == "enumerative"
    }
    assert listings == {
        "spellcheck-wordlist",
        "huggingface-wordlist",
        "old-wordlist",
        "ta-wiktionary-titles",
    }


# --------------------------------------------------------------------------
# The stage, over a store built from the committed fixtures
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Enriched:
    """A staged store with its derived zone computed, plus what built it."""

    registry: LexiconSources
    root: Path
    db: Path


def _fixture_registry(root: Path) -> LexiconSources:
    entries: list[dict[str, Any]] = []
    source: LexiconSource
    for source in REGISTRY.sources:
        fixture = source_bytes(_REPO_ROOT, _FIXTURES, source)
        staged = root / "sources" / fixture.name
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fixture, staged)
        digest, size = sha256_of(staged)
        entries.append(
            source.model_dump(exclude_none=True)
            | {
                "path": f"sources/{fixture.name}",
                "sha256": digest,
                "bytes": size,
                "enabled": True,
            }
        )
    return LexiconSources.model_validate(
        REGISTRY.model_dump(exclude_none=True) | {"lexiconRoot": "out", "sources": entries}
    )


@pytest.fixture(scope="module")
def enriched(tmp_path_factory: pytest.TempPathFactory) -> Enriched:
    """Extract, stage and enrich the committed fixtures once for the module."""
    root = tmp_path_factory.mktemp("classifier")
    registry = _fixture_registry(root)
    extract(registry, root, force=True)
    db = root / "out" / "cache" / "lexicon.db"
    stage(registry, root, db)
    enrich(registry, CONFIG, db)
    return Enriched(registry=registry, root=root, db=db)


def _scalar(conn: sqlite3.Connection, sql: str, *values: object) -> int:
    row = conn.execute(sql, values).fetchone()
    assert row is not None
    return int(row[0])


def test_every_surface_in_the_derived_zone_has_exactly_one_word_class(
    enriched: Enriched,
) -> None:
    conn = open_store(enriched.db)
    try:
        signals = _scalar(conn, "SELECT count(*) FROM signal")
        assert signals > 0
        assert _scalar(conn, "SELECT count(*) FROM classification") == signals
        assert (
            _scalar(
                conn,
                "SELECT count(*) FROM signal s WHERE NOT EXISTS "
                "(SELECT 1 FROM classification c WHERE c.word = s.word)",
            )
            == 0
        )
    finally:
        conn.close()


def test_every_stored_verdict_is_a_class_the_contract_names(enriched: Enriched) -> None:
    conn = open_store(enriched.db)
    try:
        counted = distribution(conn)
        assert set(counted) == set(WORD_CLASSES)
        assert sum(counted.values()) == _scalar(conn, "SELECT count(*) FROM signal")
        assert counted["headword"] > 0
    finally:
        conn.close()


def test_the_classifier_runs_inside_the_rebuild_and_stamps_the_epoch(
    enriched: Enriched,
) -> None:
    # The verdicts land in the same transaction as the signals, so a store can
    # never hold one without the other - and the epoch stamp says the whole
    # derived zone was computed over the staged zone as it stands.
    conn = open_store(enriched.db)
    try:
        assert derived_epoch(conn) == stage_epoch(conn)
    finally:
        conn.close()


def test_enrich_over_an_unchanged_staged_zone_is_idempotent(enriched: Enriched) -> None:
    # The acceptance gate, first half. The derived zone is a pure function of
    # the staged one, so running it twice writes the same bytes.
    db = enriched.root / "idempotent.db"
    stage(enriched.registry, enriched.root, db)
    enrich(enriched.registry, CONFIG, db)
    conn = open_store(db)
    try:
        first = canonical_dump(conn)
    finally:
        conn.close()
    enrich(enriched.registry, CONFIG, db)
    conn = open_store(db)
    try:
        assert canonical_dump(conn) == first
    finally:
        conn.close()


def test_enrich_after_a_delta_equals_enrich_after_a_full_rebuild(
    enriched: Enriched,
) -> None:
    # The acceptance gate, second half, and it covers the verdicts because Row
    # 6's canonical dump reads every DATA table in both zones - it discovers
    # them from sqlite_schema rather than from a list, so `classification` was
    # covered the moment this row started writing it.
    full = enriched.root / "full.db"
    stage(enriched.registry, enriched.root, full)
    enrich(enriched.registry, CONFIG, full)

    delta = enriched.root / "delta.db"
    for source in enriched.registry.sources:
        stage(enriched.registry, enriched.root, delta, only=source.id)
    victim = enriched.registry.sources[0].id
    stage(enriched.registry, enriched.root, delta, remove=victim)
    stage(enriched.registry, enriched.root, delta, only=victim)
    enrich(enriched.registry, CONFIG, delta)

    conn = open_store(full)
    try:
        expected = canonical_dump(conn)
    finally:
        conn.close()
    conn = open_store(delta)
    try:
        assert canonical_dump(conn) == expected
    finally:
        conn.close()


def test_reclassifying_reproduces_what_the_full_rebuild_wrote(
    enriched: Enriched,
) -> None:
    # `--classify` is the development path for the cascade. It has to land
    # exactly where a whole rebuild would, or iterating on the classifier would
    # leave a store nobody can trust.
    db = enriched.root / "reclassify.db"
    stage(enriched.registry, enriched.root, db)
    enrich(enriched.registry, CONFIG, db)
    conn = open_store(db)
    try:
        before = _verdicts(conn)
        stamp = derived_epoch(conn)
    finally:
        conn.close()

    run = reclassify(enriched.registry, CONFIG, db)
    assert run.classified == len(before)
    conn = open_store(db)
    try:
        assert _verdicts(conn) == before
        # Deliberately untouched: a verdict is a pure function of the staged
        # zone, so recomputing it can neither make a current zone stale nor make
        # a stale one current.
        assert derived_epoch(conn) == stamp
    finally:
        conn.close()


def test_reclassifying_an_empty_derived_zone_is_refused(enriched: Enriched) -> None:
    db = enriched.root / "empty.db"
    stage(enriched.registry, enriched.root, db)
    with pytest.raises(ValueError, match="derived zone is empty"):
        reclassify(enriched.registry, CONFIG, db)


def _verdicts(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        str(row[0]): str(row[1])
        for row in conn.execute("SELECT word, wordClass FROM classification")
    }


def test_the_stored_verdicts_agree_with_the_pure_function(enriched: Enriched) -> None:
    # The store path and the fixture path must be one classifier, or the Oracle
    # guards something the pipeline does not run.
    sources = tier_one_sources(enriched.registry)
    tier_one = ",".join(f"'{source_id}'" for source_id in sources)
    conn = open_store(enriched.db)
    try:
        rows = conn.execute(
            'SELECT s.word, s."attested", s."orthotactic", s."breadth", '
            's."nannulValid", s."knownVerbForm", s."ngram", s."neighbour", s."zipf", '
            "CASE WHEN t.word IS NULL THEN 0 ELSE 1 END, e.evidence, c.wordClass "
            "FROM signal s JOIN classification c ON c.word = s.word "
            f"LEFT JOIN (SELECT DISTINCT word FROM fact WHERE attr = 'headword' "
            f"AND source_id IN ({tier_one})) t ON t.word = s.word "
            "LEFT JOIN (SELECT word, group_concat(DISTINCT value) AS evidence FROM fact "
            "WHERE attr = 'wordClassEvidence' GROUP BY word) e ON e.word = s.word"
        ).fetchall()
        assert rows
        for row in rows:
            surface = Surface(
                word=str(row[0]),
                attested=float(row[1]),
                orthotactic=float(row[2]),
                breadth=float(row[3]),
                nannulValid=float(row[4]),
                knownVerbForm=float(row[5]),
                ngram=float(row[6]),
                neighbour=None if row[7] is None else float(row[7]),
                zipf=None if row[8] is None else float(row[8]),
                entry=bool(row[9]),
                evidence=parse_evidence(row[10]),
            )
            assert classify_surface(surface, CONFIG) == row[11], surface.word
    finally:
        conn.close()


def test_a_bare_word_list_never_supplies_an_entry(enriched: Enriched) -> None:
    # The measurement the headword gate rests on, asserted rather than assumed.
    # The fixture store holds four enumerative authorities, and not one surface
    # reaches `headword` on their say-so alone.
    sources = tier_one_sources(enriched.registry)
    assert sources
    listings = [
        source.id
        for source in enriched.registry.sources
        if source.attestationTier == "enumerative"
    ]
    assert listings, "the fixture store holds no bare word list to test against"
    tier_one = ",".join(f"'{source_id}'" for source_id in sources)
    conn = open_store(enriched.db)
    try:
        unearned = _scalar(
            conn,
            f"SELECT count(*) FROM classification c WHERE c.wordClass = 'headword' "
            f"AND NOT EXISTS (SELECT 1 FROM fact f WHERE f.word = c.word "
            f"AND f.attr = 'headword' AND f.source_id IN ({tier_one}))",
        )
        assert unearned == 0
    finally:
        conn.close()


def test_the_discovery_count_is_measurable_over_a_store(enriched: Enriched) -> None:
    conn = open_store(enriched.db)
    try:
        found = discoveries(conn, CONFIG)
        assert found >= 0
        assert found <= _scalar(conn, "SELECT count(*) FROM signal WHERE attested = 0")
    finally:
        conn.close()
