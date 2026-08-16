"""Tests for the exact word-hood signals and the ENRICH stage (Row 7).

Two halves, and they are tested differently on purpose:

- the ORTHOTACTIC TABLE is a fact about Tamil letters, so it is tested as a
  fact - exhaustively, over the whole 247-ezhuthu inventory, with no store and
  no fixture involved. That is the coverage class the word-final ``FINAL_MEI``
  set is already held to;
- the FIVE SIGNALS are store queries, so they are tested against a real store
  built by running the REAL extractor and the REAL stage over the committed
  byte-exact fixture slices under ``datasets/fixtures/lexicon/``. No mocks
  (Holy Law #7), and no raw sources, so the whole file runs in CI.

The row's Oracle is one predicate: every staged surface receives exactly these
five signal values. Row 8 has since filled the other three columns, and their
coverage - including where each of them deliberately leaves a NULL - is asserted
in ``test_wordsmith_signals_inexact.py`` rather than restated here.

Tamil is written with ``\\uXXXX`` escapes so this file's own normalization form
cannot change what it asserts.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from _lexicon_workspace import source_bytes
from yen_tamizh_backend.contracts.lexicon import SignalName
from yen_tamizh_backend.contracts.lexicon_sources import (
    ATTESTING_ROLES,
    LexiconSource,
    LexiconSources,
)
from yen_tamizh_backend.contracts.wordhood import Wordhood
from yen_tamizh_backend.ezhuthu import (
    CLUSTER_FOLLOWERS,
    CONSONANTS,
    EZHUTHU_INVENTORY,
    FINAL_MEI,
    GRANTHA,
    INITIAL_CONSONANTS,
    UYIR,
    analyse,
    begins_like_a_word,
    classify,
    cluster_is_legal,
    ends_like_a_word,
    segment,
)
from yen_tamizh_backend.ezhuthu.word_shape import PULLI
from yen_tamizh_backend.wordsmith.enrich import (
    SIGNALS,
    check_configured_sources,
    distribution,
    enrich,
    load_config,
    selected,
)
from yen_tamizh_backend.wordsmith.extract import extract, load_registry, sha256_of
from yen_tamizh_backend.wordsmith.signals_exact import (
    EXACT_SIGNALS,
    orthotactic_score,
)
from yen_tamizh_backend.wordsmith.stage import stage
from yen_tamizh_backend.wordsmith.store import (
    SIGNAL_COLUMNS,
    canonical_dump,
    derived_epoch,
    derived_is_current,
    open_store,
    stage_epoch,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = _REPO_ROOT / "config" / "lexicon-sources.json"
_CONFIG_PATH = _REPO_ROOT / "config" / "wordhood.json"
_FIXTURES = _REPO_ROOT / "datasets" / "fixtures" / "lexicon"

REGISTRY = load_registry(_REGISTRY_PATH)
CONFIG = load_config(_CONFIG_PATH)

# The five this row writes. Row 8 writes ngram, neighbour and zipf.
WRITTEN: tuple[SignalName, ...] = tuple(signal.name for signal in EXACT_SIGNALS)
INEXACT: tuple[str, ...] = tuple(
    column for column in SIGNAL_COLUMNS if column not in WRITTEN
)

# The eighteen mei, as the cluster table keys them.
MEI: tuple[str, ...] = tuple(f"{base}{PULLI}" for base in CONSONANTS)

# --------------------------------------------------------------------------
# The orthotactic table, tested as the fact about Tamil that it is
# --------------------------------------------------------------------------


def test_the_inventory_is_exactly_the_247_ezhuthu() -> None:
    # 12 uyir + 18 mei + 18 x 12 uyirmei + the aytham. The coverage checks below
    # are only meaningful because this set is the whole alphabet.
    assert len(EZHUTHU_INVENTORY) == 247
    assert len(set(EZHUTHU_INVENTORY)) == 247


def test_every_inventory_entry_is_one_ezhuthu_the_library_recognises() -> None:
    # Segmentation is the authority on what one ezhuthu IS, so the inventory is
    # checked against it rather than against a second hand-written table.
    for unit in EZHUTHU_INVENTORY:
        assert segment(unit) == [unit], unit
        assert classify(unit) != "other", unit


def test_the_word_initial_rule_covers_the_whole_inventory() -> None:
    # Exhaustive by partition: every ezhuthu is either a legal opening or not,
    # and the legal set is exactly the twelve uyir plus the twelve uyirmei forms
    # of the ten consonants a Tamil word may open on. No third answer, no gap.
    legal = {unit for unit in EZHUTHU_INVENTORY if begins_like_a_word([unit])}
    expected = {*UYIR} | {
        unit
        for unit in EZHUTHU_INVENTORY
        if classify(unit) == "uyirmei" and unit[0] in INITIAL_CONSONANTS
    }
    assert legal == expected
    assert len(legal) == 12 + 10 * 12
    assert len(EZHUTHU_INVENTORY) - len(legal) == 115


def test_the_word_final_rule_covers_the_whole_inventory() -> None:
    # The same partition over the other end of the word: only ten of the
    # eighteen mei are refused, and every vowel-bearing ezhuthu is admitted.
    illegal = {unit for unit in EZHUTHU_INVENTORY if not ends_like_a_word([unit])}
    assert illegal == {unit for unit in MEI if unit not in FINAL_MEI}
    assert len(illegal) == 10
    assert len(FINAL_MEI) == 8


def test_every_mei_has_a_cluster_entry() -> None:
    # Exhaustive over the mei: eighteen keys, no more and no fewer, and every
    # follower named is one of the eighteen native consonants.
    assert set(CLUSTER_FOLLOWERS) == set(MEI)
    for mei, followers in CLUSTER_FOLLOWERS.items():
        assert followers, mei
        assert followers <= set(CONSONANTS), mei


def test_every_ordered_pair_of_ezhuthu_is_decidable() -> None:
    # The whole 18 x 247 grid, with a pinned legal count. Pinning the number is
    # what makes a change to the table an explicit reviewed diff rather than a
    # silent drift in how many surfaces the signal marks down.
    pairs = len(MEI) * len(EZHUTHU_INVENTORY)
    legal = sum(
        1 for mei in MEI for unit in EZHUTHU_INVENTORY if cluster_is_legal(mei, unit)
    )
    assert pairs == 4446
    assert legal == 2613


def test_a_mei_is_never_followed_by_a_vowel_or_the_aytham() -> None:
    # Tamil writes a vowel after a consonant as a matra ON that consonant, so
    # this shape is a join that was never made - which is what a compound
    # scraped without its space looks like.
    for mei in MEI:
        for unit in EZHUTHU_INVENTORY:
            if classify(unit) in ("uyir", "aytham"):
                assert not cluster_is_legal(mei, unit), (mei, unit)


def test_ra_and_zha_are_the_two_consonants_that_do_not_double() -> None:
    doubles = {base for base in CONSONANTS if base in CLUSTER_FOLLOWERS[f"{base}{PULLI}"]}
    assert set(CONSONANTS) - doubles == {"\u0bb0", "\u0bb4"}  # ra, zha


def test_the_homorganic_nasal_stop_pairs_are_all_legal() -> None:
    # ngka, njcha, Nda, nhtha, mpa, ntra - the six every Tamil word is built of.
    for nasal, stop in (
        ("\u0b99", "\u0b95"),
        ("\u0b9e", "\u0b9a"),
        ("\u0ba3", "\u0b9f"),
        ("\u0ba8", "\u0ba4"),
        ("\u0bae", "\u0baa"),
        ("\u0ba9", "\u0bb1"),
    ):
        assert cluster_is_legal(f"{nasal}{PULLI}", stop), (nasal, stop)


def test_grantha_is_recorded_and_never_judged_as_a_defect() -> None:
    # The five grantha consonants are not among the 247: they were borrowed to
    # write Sanskrit and foreign sounds, so a cluster involving one is evidence
    # of a loanword rather than a broken word (Row 7 decision 6).
    assert GRANTHA.isdisjoint({unit[0] for unit in EZHUTHU_INVENTORY})
    for mei in MEI:
        for base in GRANTHA:
            assert cluster_is_legal(mei, base), (mei, base)
    # ksha: k + ssa. The compound needs no entry of its own - its ssa is here.
    ksha = analyse("\u0bb2\u0b9f\u0bcd\u0bb7\u0bae\u0bcd")  # latchumam-shaped
    assert ksha.hasGrantha
    assert ksha.clustersLegal


def test_a_clean_word_scores_one_and_grantha_does_not_cost_it_anything() -> None:
    # maram (tree) - the shape every rule admits.
    assert orthotactic_score("\u0bae\u0bb0\u0bae\u0bcd", CONFIG.orthotactic) == 1.0
    # bajanai - a loanword carrying grantha in the middle. It still scores 1
    # under the committed weights, because granthaPenalty is 0: grantha is
    # evidence of a loanword, not damage to a word.
    bajanai = "\u0baa\u0b9c\u0ba9\u0bc8"
    assert analyse(bajanai).hasGrantha
    assert orthotactic_score(bajanai, CONFIG.orthotactic) == 1.0


def test_a_grantha_edge_still_fails_the_rule_it_actually_breaks() -> None:
    # shri opens on a bare mei, and no native Tamil word does. The initial rule
    # is about NATIVE shape, so it fires - and that is not double-counting the
    # grantha penalty, it is the second, independent fact. The classifier reads
    # both: a low score WITH grantha is a loanword, a low score WITHOUT one is
    # junk, and collapsing them would lose exactly that distinction.
    shri = "\u0bb8\u0bcd\u0bb0\u0bc0"
    shape = analyse(shri)
    assert shape.hasGrantha
    assert shape.clustersLegal
    assert not shape.initialLegal
    assert orthotactic_score(shri, CONFIG.orthotactic) == 1.0 - (
        CONFIG.orthotactic.initialWeight
    )


def test_the_shapes_the_signal_exists_to_catch() -> None:
    # A bare mei cannot open a word: this is how a transliterated name reaches
    # a served wordlist (the committed anagram set once served this one).
    stalin = "\u0bb8\u0bcd\u0b9f\u0bbe\u0bb2\u0bbf\u0ba9\u0bcd"
    assert not analyse(stalin).initialLegal
    # aayvup: the euphonic doubling belonging to the NEXT word, tokenized here.
    aayvup = "\u0b86\u0baf\u0bcd\u0bb5\u0bc1\u0baa\u0bcd"
    assert not analyse(aayvup).finalLegal
    # maram + illaatha, a compound scraped without its space: m followed by an
    # independent vowel is a join Tamil never writes.
    joined = "\u0bae\u0bb0\u0bae\u0bcd\u0b87\u0bb2\u0bcd\u0bb2\u0bbe"
    assert not analyse(joined).clustersLegal
    # ra never opens a native word; the surfaces that do are loanwords.
    assert not analyse("\u0bb0\u0bbe\u0bae\u0ba9\u0bcd").initialLegal


def test_anything_that_is_not_tamil_scores_zero_outright() -> None:
    # Not badly-shaped Tamil - not Tamil. No weighting of the three letter rules
    # should be able to argue otherwise, so it is not weighted at all.
    for surface in ("David", "\u0bae\u0bb0\u0bae\u0bcd 2", "\u0bae\u0bb0-\u0bae\u0bcd"):
        assert analyse(surface).hasNonTamil, surface
        assert orthotactic_score(surface, CONFIG.orthotactic) == 0.0, surface
    assert orthotactic_score("", CONFIG.orthotactic) == 0.0


def test_each_broken_rule_costs_exactly_its_configured_weight() -> None:
    weights = CONFIG.orthotactic
    stalin = "\u0bb8\u0bcd\u0b9f\u0bbe\u0bb2\u0bbf\u0ba9\u0bcd"
    aayvup = "\u0b86\u0baf\u0bcd\u0bb5\u0bc1\u0baa\u0bcd"
    assert orthotactic_score(stalin, weights) == 1.0 - weights.initialWeight
    assert orthotactic_score(aayvup, weights) == 1.0 - weights.finalWeight


# --------------------------------------------------------------------------
# The config surface
# --------------------------------------------------------------------------


def test_the_committed_config_validates() -> None:
    # A fresh clone runs on the committed defaults.
    Wordhood.model_validate_json(_CONFIG_PATH.read_text(encoding="utf-8"))


def test_every_configured_source_is_in_the_lexicon_registry() -> None:
    # The cross-file check that catches a typo with no store on disk, which is
    # the only form of it CI can run.
    known = {source.id for source in REGISTRY.sources}
    for name in (*CONFIG.nannulSources, *CONFIG.verbFormSources):
        assert name in known, name


def _config_payload() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return payload


def test_weights_that_overrun_the_score_are_rejected() -> None:
    payload = _config_payload()
    payload["orthotactic"]["clusterWeight"] = 0.9
    with pytest.raises(ValidationError):
        Wordhood.model_validate(payload)


def test_a_repeated_source_is_rejected() -> None:
    payload = _config_payload()
    payload["verbFormSources"] = [*payload["verbFormSources"], payload["verbFormSources"][0]]
    with pytest.raises(ValidationError):
        Wordhood.model_validate(payload)


def test_a_signal_with_no_producer_is_rejected() -> None:
    payload = _config_payload()
    payload["nannulSources"] = []
    with pytest.raises(ValidationError):
        Wordhood.model_validate(payload)


# --------------------------------------------------------------------------
# The signals, over a store built from the committed fixtures
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Enriched:
    """A staged store with its derived zone computed, plus what built it."""

    registry: LexiconSources
    root: Path
    db: Path


@pytest.fixture(scope="module")
def enriched(tmp_path_factory: pytest.TempPathFactory) -> Enriched:
    """Extract, stage and enrich the committed fixtures once for the module."""
    root = tmp_path_factory.mktemp("wordhood")
    entries: list[dict[str, Any]] = []
    for source in REGISTRY.sources:
        fixture = source_bytes(_REPO_ROOT, source)
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
                # The one known-bad source is disabled in the real registry; a
                # signal that can score it is a signal that can score anything.
                "enabled": True,
            }
        )
    registry = LexiconSources.model_validate(
        REGISTRY.model_dump(exclude_none=True) | {"lexiconRoot": "out", "sources": entries}
    )
    extract(registry, root, force=True)
    db = root / "out" / "cache" / "lexicon.db"
    stage(registry, root, db)
    enrich(registry, CONFIG, db)
    return Enriched(registry=registry, root=root, db=db)


def _connect(db: Path) -> sqlite3.Connection:
    return open_store(db)


def _scalar(conn: sqlite3.Connection, sql: str, *values: object) -> int:
    row = conn.execute(sql, values).fetchone()
    assert row is not None
    return int(row[0])


def _population(conn: sqlite3.Connection) -> int:
    return _scalar(
        conn,
        "SELECT count(*) FROM "
        "(SELECT surface AS w FROM observation UNION SELECT word FROM fact)",
    )


def test_every_staged_surface_receives_all_five_signal_values(enriched: Enriched) -> None:
    # THE ORACLE, first half. One signal row per staged surface, and not one of
    # the five is missing on any of them.
    conn = _connect(enriched.db)
    try:
        assert _scalar(conn, "SELECT count(*) FROM signal") == _population(conn)
        missing = " OR ".join(f'"{column}" IS NULL' for column in WRITTEN)
        assert _scalar(conn, f"SELECT count(*) FROM signal WHERE {missing}") == 0
    finally:
        conn.close()


def test_the_signals_this_row_owns_are_exactly_the_exact_five() -> None:
    # The split between the two rows is a fact about the runner's tuple, not a
    # comment: these five are lookups, and the other three need a model or a
    # search. Row 8 appended its own rather than editing any of these.
    assert INEXACT == ("ngram", "neighbour", "zipf")
    assert tuple(signal.name for signal in SIGNALS)[: len(WRITTEN)] == WRITTEN
    assert all(signal.second_pass is None for signal in EXACT_SIGNALS)


def test_attested_marks_exactly_the_authority_headwords(enriched: Enriched) -> None:
    conn = _connect(enriched.db)
    try:
        placeholders = ",".join("?" for _ in ATTESTING_ROLES)
        disagreements = _scalar(
            conn,
            "SELECT count(*) FROM signal s WHERE s.attested != CAST(EXISTS ("
            "SELECT 1 FROM fact f JOIN source src ON src.id = f.source_id "
            f"WHERE f.word = s.word AND f.attr = 'headword' "
            f"AND src.role IN ({placeholders})) AS REAL)",
            *ATTESTING_ROLES,
        )
        assert disagreements == 0
        # And the signal actually fires - a column of zeros would pass the
        # check above while measuring nothing at all.
        assert _scalar(conn, "SELECT count(*) FROM signal WHERE attested > 0") > 0
    finally:
        conn.close()


def test_a_frequency_source_can_never_make_a_surface_attested(
    enriched: Enriched,
) -> None:
    # Observation is not attestation. A surface only a frequency list ever saw
    # must score zero however many times it saw it.
    conn = _connect(enriched.db)
    try:
        assert (
            _scalar(
                conn,
                "SELECT count(*) FROM signal s WHERE s.attested > 0 AND NOT EXISTS ("
                "SELECT 1 FROM fact f WHERE f.word = s.word AND f.attr = 'headword')",
            )
            == 0
        )
    finally:
        conn.close()


def test_breadth_is_the_count_of_distinct_observing_sources(
    enriched: Enriched,
) -> None:
    conn = _connect(enriched.db)
    try:
        assert (
            _scalar(
                conn,
                "SELECT count(*) FROM signal s WHERE s.breadth != CAST(COALESCE(("
                "SELECT count(DISTINCT o.source_id) FROM observation o "
                "WHERE o.surface = s.word), 0) AS REAL)",
            )
            == 0
        )
        assert _scalar(conn, "SELECT count(*) FROM signal WHERE breadth > 1") > 0
    finally:
        conn.close()


@pytest.mark.parametrize(
    ("column", "field"),
    [("nannulValid", "nannulSources"), ("knownVerbForm", "verbFormSources")],
)
def test_a_membership_signal_marks_exactly_its_configured_sources(
    enriched: Enriched, column: str, field: str
) -> None:
    sources: list[str] = list(getattr(CONFIG, field))
    placeholders = ",".join("?" for _ in sources)
    conn = _connect(enriched.db)
    try:
        disagreements = _scalar(
            conn,
            f'SELECT count(*) FROM signal s WHERE s."{column}" != CAST(('
            f"EXISTS (SELECT 1 FROM observation o WHERE o.surface = s.word "
            f"AND o.source_id IN ({placeholders})) OR "
            f"EXISTS (SELECT 1 FROM fact f WHERE f.word = s.word "
            f"AND f.source_id IN ({placeholders}))) AS REAL)",
            *sources,
            *sources,
        )
        assert disagreements == 0
        assert _scalar(conn, f'SELECT count(*) FROM signal WHERE "{column}" > 0') > 0
    finally:
        conn.close()


def test_the_stored_orthotactic_value_is_the_pure_function_of_the_word(
    enriched: Enriched,
) -> None:
    # The strongest check available for a signal computed by a user-defined
    # function: every stored value re-derived from the surface alone.
    conn = _connect(enriched.db)
    try:
        rows = conn.execute("SELECT word, orthotactic FROM signal").fetchall()
        assert rows
        for word, value in rows:
            assert value == orthotactic_score(str(word), CONFIG.orthotactic), word
    finally:
        conn.close()


def test_enrich_stamps_the_derived_zone_with_the_staged_version(
    enriched: Enriched,
) -> None:
    conn = _connect(enriched.db)
    try:
        assert derived_epoch(conn) == stage_epoch(conn)
        assert derived_is_current(conn)
    finally:
        conn.close()


def test_a_later_stage_write_makes_the_derived_zone_stale(
    enriched: Enriched, tmp_path: Path
) -> None:
    # The guard PUBLISH refuses on, driven end to end rather than asserted.
    db = tmp_path / "stale.db"
    stage(enriched.registry, enriched.root, db)
    enrich(enriched.registry, CONFIG, db)
    conn = _connect(db)
    try:
        assert derived_is_current(conn)
    finally:
        conn.close()
    stage(enriched.registry, enriched.root, db, remove="wiki")
    conn = _connect(db)
    try:
        assert not derived_is_current(conn)
    finally:
        conn.close()


def test_enrich_over_an_unchanged_staged_zone_is_idempotent(
    enriched: Enriched, tmp_path: Path
) -> None:
    db = tmp_path / "twice.db"
    stage(enriched.registry, enriched.root, db)
    enrich(enriched.registry, CONFIG, db)
    conn = _connect(db)
    try:
        first = canonical_dump(conn)
    finally:
        conn.close()
    enrich(enriched.registry, CONFIG, db)
    conn = _connect(db)
    try:
        assert canonical_dump(conn) == first
    finally:
        conn.close()


def test_recomputing_one_signal_reproduces_it_and_leaves_the_stamp_alone(
    enriched: Enriched, tmp_path: Path
) -> None:
    db = tmp_path / "one.db"
    stage(enriched.registry, enriched.root, db)
    enrich(enriched.registry, CONFIG, db)
    conn = _connect(db)
    try:
        before = canonical_dump(conn)
        stamp = derived_epoch(conn)
    finally:
        conn.close()
    for signal in EXACT_SIGNALS:
        enrich(enriched.registry, CONFIG, db, signal.name)
    conn = _connect(db)
    try:
        assert canonical_dump(conn) == before
        assert derived_epoch(conn) == stamp
    finally:
        conn.close()


def test_recomputing_a_signal_before_there_is_a_population_is_refused(
    enriched: Enriched, tmp_path: Path
) -> None:
    # A single-signal run over an empty zone would write nothing and report
    # success, which is the shape of a silent failure.
    db = tmp_path / "unenriched.db"
    stage(enriched.registry, enriched.root, db)
    with pytest.raises(ValueError, match="empty"):
        enrich(enriched.registry, CONFIG, db, "attested")


def test_an_unknown_signal_name_is_refused() -> None:
    with pytest.raises(ValueError, match="no signal"):
        selected("orthotactics")


def test_a_configured_source_that_is_not_staged_is_refused(
    enriched: Enriched,
) -> None:
    # Fail fast at the boundary: a misspelled id would otherwise produce a
    # column of zeros, which reads exactly like a signal that found nothing.
    broken = CONFIG.model_copy(update={"nannulSources": ["spellcheck-wordlst"]})
    conn = _connect(enriched.db)
    try:
        with pytest.raises(ValueError, match="spellcheck-wordlst"):
            check_configured_sources(conn, broken)
    finally:
        conn.close()


def test_every_signal_writes_a_column_the_store_declares() -> None:
    # One name for the signal and its column, so a signal cannot be written into
    # the wrong one, and no two signals can claim the same one.
    names = [signal.name for signal in SIGNALS]
    assert len(set(names)) == len(names)
    assert set(names) <= set(SIGNAL_COLUMNS)


def test_the_run_reports_a_measurement_for_every_column(enriched: Enriched) -> None:
    conn = _connect(enriched.db)
    try:
        measured = distribution(conn)
        rows = _scalar(conn, "SELECT count(*) FROM signal")
    finally:
        conn.close()
    assert set(measured) == set(SIGNAL_COLUMNS)
    for column in WRITTEN:
        assert measured[column][0] == rows, column
        assert measured[column][1] > 0, column


def test_the_derived_zone_is_recomputed_whole_rather_than_merged(
    enriched: Enriched, tmp_path: Path
) -> None:
    # A stale row from a previous population must not survive a re-run: the
    # zone is a pure function of the staged one, so it is dropped, not merged.
    db = tmp_path / "whole.db"
    stage(enriched.registry, enriched.root, db)
    enrich(enriched.registry, CONFIG, db)
    conn = _connect(db)
    try:
        conn.execute(
            "INSERT INTO signal (word, attested) VALUES ('\u0bb5\u0bbf\u0bb2', 1.0)"
        )
        conn.execute("INSERT INTO classification (word, wordClass) VALUES ('x', 'headword')")
        conn.commit()
    finally:
        conn.close()
    enrich(enriched.registry, CONFIG, db)
    conn = _connect(db)
    try:
        assert _scalar(conn, "SELECT count(*) FROM signal") == _population(conn)
        # Row 9 writes this table too, so "dropped and recomputed whole" is now
        # a claim about both: the injected row is gone and every surface has a
        # verdict, rather than the table simply being empty.
        assert _scalar(conn, "SELECT count(*) FROM classification") == _population(conn)
        assert _scalar(conn, "SELECT count(*) FROM classification WHERE word = 'x'") == 0
    finally:
        conn.close()


def test_a_source_named_only_by_facts_still_reaches_the_derived_zone(
    enriched: Enriched,
) -> None:
    # The population is the UNION of observed surfaces and worded facts. Every
    # fact word is observed today, so this asserts the union rather than a
    # coincidence of the sources currently registered.
    conn = _connect(enriched.db)
    try:
        assert (
            _scalar(
                conn,
                "SELECT count(*) FROM (SELECT DISTINCT word FROM fact "
                "EXCEPT SELECT word FROM signal)",
            )
            == 0
        )
    finally:
        conn.close()


def test_the_fixture_store_holds_every_registered_source(enriched: Enriched) -> None:
    # Guards the checks above: they only mean something over a store that
    # actually holds all nineteen sources' contributions.
    conn = _connect(enriched.db)
    try:
        assert _scalar(conn, "SELECT count(*) FROM source") == len(REGISTRY.sources)
    finally:
        conn.close()


def _source(registry: LexiconSources, source_id: str) -> LexiconSource:
    return next(entry for entry in registry.sources if entry.id == source_id)


def test_removing_a_source_changes_the_signals_it_supported(
    enriched: Enriched, tmp_path: Path
) -> None:
    # The derived zone follows the staged one. Drop the Nannul source and the
    # signal that IS its membership must go to zero everywhere.
    db = tmp_path / "removed.db"
    stage(enriched.registry, enriched.root, db)
    enrich(enriched.registry, CONFIG, db)
    conn = _connect(db)
    try:
        before = _scalar(conn, "SELECT count(*) FROM signal WHERE nannulValid > 0")
    finally:
        conn.close()
    assert before > 0
    nannul = CONFIG.nannulSources[0]
    stage(enriched.registry, enriched.root, db, remove=nannul)
    # The configured source is gone, so ENRICH must refuse rather than quietly
    # report every surface as failing a grammar check nobody ran.
    with pytest.raises(ValueError, match=nannul):
        enrich(enriched.registry, CONFIG, db)
    assert _source(enriched.registry, nannul).role == "authority"
