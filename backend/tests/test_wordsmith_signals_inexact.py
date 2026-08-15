"""Tests for the inexact word-hood signals (Row 8).

Three halves, and they are tested differently on purpose:

- the MODEL and the SEARCH are pure functions, so they are tested as pure
  functions - a fitted n-gram model over a corpus written into the test, and a
  deletion neighbourhood over a dictionary written into the test. No store, no
  fixtures, nothing to wait for;
- the EZHUTHU METRIC is tested against the thing it exists to be different
  from. Two pairs decide it: one that a code-point metric calls neighbours and
  an ezhuthu metric does not, and one the other way round. If both agreed, the
  whole re-encoding would be ceremony;
- the SIGNALS are store queries, so they run against a real store built by
  running the REAL extractor and the REAL stage over the committed byte-exact
  fixture slices under ``datasets/fixtures/lexicon/``. No mocks (Holy Law #7),
  no raw sources, so the whole file runs in CI.

The row's Oracle is determinism: all three signal vectors are byte-identical
across two runs over the same staged zone, and the one signal that scores across
processes gives the same column whatever the worker count.

``rapidfuzz`` is optional and absent from CI. Every test that names it skips
when it is not installed, and the one that matters asserts the pure-Python path
returns exactly what it returns - so which of the two ran can never change a
stored value.

Tamil is written with ``\\uXXXX`` escapes so this file's own normalization form
cannot change what it asserts.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from _lexicon_workspace import source_bytes
from yen_tamizh_backend.contracts.lexicon_sources import LexiconSources
from yen_tamizh_backend.contracts.wordhood import (
    MAX_EDIT_DISTANCE,
    NeighbourSettings,
    Wordhood,
)
from yen_tamizh_backend.ezhuthu import EZHUTHU_INVENTORY, segment
from yen_tamizh_backend.wordsmith import neighbours, ngram
from yen_tamizh_backend.wordsmith.enrich import SIGNALS, enrich, load_config
from yen_tamizh_backend.wordsmith.extract import extract, load_registry, sha256_of
from yen_tamizh_backend.wordsmith.signals_exact import EXACT_SIGNALS
from yen_tamizh_backend.wordsmith.signals_inexact import (
    HEADWORDS,
    INEXACT_SIGNALS,
    NEIGHBOUR_INDEX,
    NGRAM_MODEL,
    ZIPF_FIT,
    HeadwordCensus,
    fit_zipf,
)
from yen_tamizh_backend.wordsmith.stage import stage
from yen_tamizh_backend.wordsmith.store import derived_epoch, open_store

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = _REPO_ROOT / "config" / "lexicon-sources.json"
_CONFIG_PATH = _REPO_ROOT / "config" / "wordhood.json"
_FIXTURES = _REPO_ROOT / "datasets" / "fixtures" / "lexicon"

REGISTRY = load_registry(_REGISTRY_PATH)
CONFIG = load_config(_CONFIG_PATH)

INEXACT: tuple[str, ...] = tuple(signal.name for signal in INEXACT_SIGNALS)

# Two uyirmei of one consonant, so a word can be built out of known pieces
# rather than out of an escape sequence nobody can check by eye.
KA = "\u0b95"  # ka
KAA = "\u0b95\u0bbe"  # kaa - one ezhuthu, two code points
PI = "\u0baa\u0bbf"  # pi - one ezhuthu, two code points
LA = "\u0bb2"  # la
MA = "\u0bae"  # ma
NA = "\u0ba8"  # na
TA = "\u0ba4"  # ta

requires_rapidfuzz = pytest.mark.skipif(
    not neighbours.RAPIDFUZZ,
    reason="rapidfuzz is an optional build-time extra and is absent here",
)


# --------------------------------------------------------------------------
# The metric: one ezhuthu is one unit of distance, and code points are not
# --------------------------------------------------------------------------


def _ezhuthu_distance(left: str, right: str, limit: int) -> int:
    alphabet = neighbours.build_alphabet(
        unit for word in (left, right) for unit in segment(word)
    )
    return neighbours.bounded_distance(
        neighbours.encode(segment(left), alphabet),
        neighbours.encode(segment(right), alphabet),
        limit,
    )


def test_a_pair_code_points_call_neighbours_is_two_ezhuthu_apart() -> None:
    # THE reason decision 2 exists. `kaa` and `ka ka` are the same two code
    # points long and differ in one of them, so a code-point metric puts them a
    # single edit apart - but one is a single ezhuthu and the other is two, and
    # no player would call them near-misses.
    assert len(KAA) == len(KA + KA)
    assert neighbours.bounded_distance(KAA, KA + KA, 3) == 1
    assert _ezhuthu_distance(KAA, KA + KA, 3) == 2


def test_a_pair_code_points_call_far_is_one_ezhuthu_apart() -> None:
    # And the other way round: two whole syllables that differ in both their
    # consonant and their vowel are two code-point edits apart and exactly one
    # ezhuthu apart, which is what they are.
    assert neighbours.bounded_distance(KAA, PI, 3) == 2
    assert _ezhuthu_distance(KAA, PI, 3) == 1


def test_the_encoding_is_one_character_per_ezhuthu() -> None:
    word = KAA + PI + LA
    alphabet = neighbours.build_alphabet(segment(word))
    encoded = neighbours.encode(segment(word), alphabet)
    assert len(segment(word)) == 3
    assert len(encoded) == 3
    assert len(set(encoded)) == 3


def test_the_alphabet_is_a_pure_function_of_the_units_it_is_given() -> None:
    # Sorted assignment, so two runs over the same headwords encode identically.
    # Half of why two runs produce the same signal vector.
    units = [KAA, PI, LA, MA]
    assert neighbours.build_alphabet(units) == neighbours.build_alphabet(reversed(units))
    assert neighbours.build_alphabet(units) == neighbours.build_alphabet(units * 3)


def test_a_unit_the_dictionary_never_used_encodes_to_one_foreign_character() -> None:
    # Safe rather than lossy: no headword holds it, so it mismatches every
    # dictionary character exactly as a distinct code would.
    alphabet = neighbours.build_alphabet([KAA, LA])
    assert neighbours.encode(segment(KAA + "Z" + LA), alphabet)[1] == "\ue000"


# --------------------------------------------------------------------------
# The bounded distance, and the optional accelerator
# --------------------------------------------------------------------------


def _pairs() -> list[tuple[str, str]]:
    units = list(EZHUTHU_INVENTORY[:40])
    words = ["".join(units[index : index + 5]) for index in range(0, 35)]
    return [(left, right) for left in words[:12] for right in words[:12]]


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_the_bounded_distance_agrees_with_the_unbounded_one(limit: int) -> None:
    for left, right in _pairs():
        exact = neighbours.bounded_distance(left, right, len(left) + len(right))
        bounded = neighbours.bounded_distance(left, right, limit)
        assert bounded == (exact if exact <= limit else limit + 1), (left, right)


@requires_rapidfuzz
@pytest.mark.parametrize("limit", [1, 2])
def test_the_optional_accelerator_returns_exactly_the_pure_python_answer(
    limit: int,
) -> None:
    # The single thing that could make an optional dependency change an output.
    # If these ever diverge, a store enriched on a developer's machine and one
    # enriched in CI would disagree, and the row's Oracle would be a lie.
    for left, right in _pairs():
        assert neighbours.distance(left, right, limit) == neighbours.bounded_distance(
            left, right, limit
        ), (left, right)


def test_deletion_variants_are_the_word_and_everything_below_it() -> None:
    assert neighbours.deletion_variants("abc", 0) == {"abc"}
    assert neighbours.deletion_variants("abc", 1) == {"abc", "bc", "ac", "ab"}
    assert neighbours.deletion_variants("abc", 2) == {
        "abc",
        "bc",
        "ac",
        "ab",
        "a",
        "b",
        "c",
    }


def test_a_repeated_unit_is_not_indexed_twice() -> None:
    # Deleting either copy of a repeat reaches the same variant, and indexing it
    # twice would only cost memory.
    assert neighbours.deletion_variants("aab", 1) == {"aab", "ab", "aa"}


# --------------------------------------------------------------------------
# The deletion neighbourhood
# --------------------------------------------------------------------------


def _dictionary() -> list[str]:
    return [
        KAA + LA + MA,
        KAA + LA + NA,
        MA + NA + TA,
        PI + LA + MA + NA,
        KA + KA + LA,
    ]


def test_the_index_finds_a_headword_one_ezhuthu_away() -> None:
    index = neighbours.build_index(_dictionary(), 2)
    assert neighbours.nearest(KAA + LA + TA, index) == 1
    assert neighbours.closeness(KAA + LA + TA, index) == 1.0


def test_the_index_finds_a_headword_two_ezhuthu_away() -> None:
    index = neighbours.build_index(_dictionary(), 2)
    assert neighbours.nearest(KAA + TA + TA, index) == 2
    assert neighbours.closeness(KAA + TA + TA, index) == 0.5


def test_a_surface_with_no_headword_in_range_scores_zero() -> None:
    # Zero is "we looked and found nothing", which the store keeps distinct from
    # the NULL that means "we did not look".
    index = neighbours.build_index(_dictionary(), 2)
    far = "".join(EZHUTHU_INVENTORY[100:108])
    assert neighbours.nearest(far, index) > index.maxDistance
    assert neighbours.closeness(far, index) == 0.0


def test_the_index_finds_every_neighbour_a_brute_force_search_finds() -> None:
    # The deletion neighbourhood is a candidate GENERATOR, so the property that
    # matters is that it generates every candidate an all-pairs search would.
    dictionary = _dictionary()
    index = neighbours.build_index(dictionary, 2)
    alphabet = index.alphabet
    encoded = [neighbours.encode(segment(word), alphabet) for word in dictionary]
    queries = [
        KAA + LA + TA,
        KAA + TA + TA,
        MA + NA,
        PI + LA + MA,
        KA + KA,
        MA + NA + TA + LA,
    ]
    for query in queries:
        probe = neighbours.encode(segment(query), alphabet)
        brute = min(
            neighbours.bounded_distance(probe, word, 2) for word in encoded
        )
        assert neighbours.nearest(query, index) == brute, query


def test_an_edit_distance_beyond_the_ceiling_is_refused_by_the_code() -> None:
    # A hard assert, not only a config default: the arithmetic is what makes it
    # a limit. At three the index is two and a half times as many entries and
    # the pass is hours, so a config typo has to fail rather than run all
    # afternoon.
    with pytest.raises(ValueError, match="maxEditDistance"):
        neighbours.build_index(_dictionary(), MAX_EDIT_DISTANCE + 1)
    with pytest.raises(ValueError, match="maxEditDistance"):
        neighbours.build_index(_dictionary(), 0)


def test_the_index_is_a_pure_function_of_the_dictionary() -> None:
    forwards = neighbours.build_index(_dictionary(), 2)
    backwards = neighbours.build_index(list(reversed(_dictionary())), 2)
    assert list(forwards.packed) == list(backwards.packed)
    assert forwards.alphabet == backwards.alphabet


# --------------------------------------------------------------------------
# The n-gram model
# --------------------------------------------------------------------------


def _training() -> list[str]:
    units = list(EZHUTHU_INVENTORY[:24])
    return ["".join(units[index : index + 4]) for index in range(0, 20)]


def test_a_trained_model_scores_inside_the_unit_interval() -> None:
    model = ngram.train(_training(), order=3, smoothing=0.1)
    for word in _training():
        value = ngram.score(model, word)
        assert 0.0 < value <= 1.0, word


def test_a_word_the_model_was_trained_on_outscores_a_shuffled_one() -> None:
    model = ngram.train(_training(), order=3, smoothing=0.1)
    seen = _training()[0]
    units = segment(seen)
    shuffled = "".join([units[-1], units[0], units[2], units[1]])
    assert ngram.score(model, seen) > ngram.score(model, shuffled)


def test_a_surface_that_is_not_tamil_at_all_scores_near_zero() -> None:
    # It is scored, not refused: every unit folds to the unknown symbol and the
    # smoothing mass is all that is left, which is the answer the classifier
    # wants rather than an exception it would have to handle.
    model = ngram.train(_training(), order=3, smoothing=0.1)
    foreign = ngram.score(model, "computer")
    assert foreign > 0.0
    assert foreign < min(ngram.score(model, word) for word in _training())


def test_length_does_not_decide_the_score() -> None:
    # A geometric mean rather than a product: a long clean word must not score
    # below a short broken one just for being long.
    model = ngram.train(_training(), order=3, smoothing=0.1)
    units = segment(_training()[0])
    short = "".join(units[:2])
    long = _training()[0] + _training()[1]
    assert ngram.score(model, long) > ngram.score(model, "z" + short)


def test_the_model_is_a_pure_function_of_its_training_set() -> None:
    forwards = ngram.train(_training(), order=3, smoothing=0.1)
    backwards = ngram.train(list(reversed(_training())), order=3, smoothing=0.1)
    for word in _training():
        assert ngram.score(forwards, word) == ngram.score(backwards, word), word
    assert forwards.logProbability == backwards.logProbability


def test_an_empty_training_set_is_refused() -> None:
    # A model fitted on nothing would score every surface identically, which
    # reads exactly like a signal that found nothing to say.
    with pytest.raises(ValueError, match="empty"):
        ngram.train([], order=3, smoothing=0.1)


def test_an_order_that_models_no_sequence_is_refused() -> None:
    with pytest.raises(ValueError, match="order"):
        ngram.train(_training(), order=1, smoothing=0.1)


def test_smoothing_that_makes_an_unseen_unit_impossible_is_refused() -> None:
    with pytest.raises(ValueError, match="smoothing"):
        ngram.train(_training(), order=3, smoothing=0.0)


# --------------------------------------------------------------------------
# The Zipf fit
# --------------------------------------------------------------------------


def test_a_perfect_zipf_distribution_fits_with_no_residual() -> None:
    groups = [(1_000_000 // rank, 1) for rank in range(1, 200)]
    fit, residuals = fit_zipf(groups)
    assert fit.exponent == pytest.approx(1.0, abs=0.02)
    assert max(abs(value) for _, value in residuals) < 0.01


def test_a_surface_far_off_the_line_gets_the_residual_that_says_so() -> None:
    groups = [(1_000_000 // rank, 1) for rank in range(1, 200)]
    groups.append((1, 1))
    fit, residuals = fit_zipf(groups)
    assert fit.exponent > 0.0
    assert dict(residuals)[1] < -0.5


def test_ties_share_a_rank_and_the_next_total_takes_the_rank_after_them() -> None:
    # Competition ranking. Broken any other way - by the surface's own spelling,
    # say - the exponent would depend on collation rather than on the corpus.
    fit, residuals = fit_zipf([(100, 3), (50, 1)])
    assert fit.surfaces == 4
    assert len(residuals) == 2


def test_a_corpus_with_one_frequency_has_no_line_to_deviate_from() -> None:
    fit, residuals = fit_zipf([(7, 5000)])
    assert fit.exponent == 0.0
    assert residuals == [(7, 0.0)]


# --------------------------------------------------------------------------
# The config
# --------------------------------------------------------------------------


def test_the_committed_config_carries_both_new_sections() -> None:
    assert CONFIG.ngram.order >= 2
    assert CONFIG.ngram.smoothing > 0.0
    assert CONFIG.neighbour.maxEditDistance <= MAX_EDIT_DISTANCE
    assert CONFIG.neighbour.pruneBreadth >= 1


def _config_payload() -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    return payload


def test_the_schema_refuses_an_edit_distance_the_search_cannot_afford() -> None:
    # The ceiling is in the schema as well as in the code, because raising it is
    # not a tuning decision - it is an afternoon.
    payload = _config_payload()
    payload["neighbour"]["maxEditDistance"] = MAX_EDIT_DISTANCE + 1
    with pytest.raises(ValidationError, match="maxEditDistance"):
        Wordhood.model_validate(payload)


def test_the_schema_refuses_a_model_order_that_measures_itself() -> None:
    payload = _config_payload()
    payload["ngram"]["order"] = 9
    with pytest.raises(ValidationError, match="order"):
        Wordhood.model_validate(payload)


def test_the_config_version_matches_its_newest_changelog_entry() -> None:
    assert CONFIG.version == CONFIG.changelog[0].version
    assert len(CONFIG.changelog) >= 2


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
    root = tmp_path_factory.mktemp("inexact")
    entries: list[dict[str, Any]] = []
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
    registry = LexiconSources.model_validate(
        REGISTRY.model_dump(exclude_none=True) | {"lexiconRoot": "out", "sources": entries}
    )
    extract(registry, root, force=True)
    db = root / "out" / "cache" / "lexicon.db"
    stage(registry, root, db)
    enrich(registry, CONFIG, db, workers=1)
    return Enriched(registry=registry, root=root, db=db)


def _scalar(conn: sqlite3.Connection, sql: str, *values: object) -> int:
    row = conn.execute(sql, values).fetchone()
    assert row is not None
    return int(row[0])


def _column_digest(db: Path, column: str) -> str:
    """The whole column in key order, hashed, so two runs can be compared.

    ``repr`` of a float round-trips exactly, so this compares the values that
    were stored and not a rendering of them.
    """
    digest = hashlib.sha256()
    conn = open_store(db)
    try:
        for word, value in conn.execute(
            f'SELECT word, "{column}" FROM signal ORDER BY word'
        ):
            digest.update(f"{word}\t{value!r}\n".encode())
    finally:
        conn.close()
    return digest.hexdigest()


def _pruned(conn: sqlite3.Connection) -> int:
    return _scalar(
        conn,
        "SELECT count(*) FROM signal WHERE attested > 0 OR knownVerbForm > 0 "
        "OR breadth >= ?",
        CONFIG.neighbour.pruneBreadth,
    )


def test_every_staged_surface_receives_the_three_inexact_values(
    enriched: Enriched,
) -> None:
    # ngram is a total function of the surface, so it is measured everywhere.
    # The other two are not, and the two tests below say exactly where.
    conn = open_store(enriched.db)
    try:
        rows = _scalar(conn, "SELECT count(*) FROM signal")
        assert _scalar(conn, "SELECT count(ngram) FROM signal") == rows
        assert _scalar(conn, "SELECT count(*) FROM signal WHERE ngram > 0") == rows
    finally:
        conn.close()


def test_neighbour_is_null_on_exactly_the_surfaces_the_prune_skipped(
    enriched: Enriched,
) -> None:
    # NULL is "nobody asked", and it is the honest answer for a surface an
    # authority attested: the signal's only consumer is suspectedTypo.
    conn = open_store(enriched.db)
    try:
        rows = _scalar(conn, "SELECT count(*) FROM signal")
        skipped = _pruned(conn)
        assert skipped > 0
        assert _scalar(conn, "SELECT count(*) FROM signal WHERE neighbour IS NULL") == (
            skipped
        )
        assert _scalar(conn, "SELECT count(neighbour) FROM signal") == rows - skipped
        assert (
            _scalar(
                conn,
                "SELECT count(*) FROM signal WHERE neighbour IS NOT NULL AND "
                "(attested > 0 OR knownVerbForm > 0 OR breadth >= ?)",
                CONFIG.neighbour.pruneBreadth,
            )
            == 0
        )
    finally:
        conn.close()


def test_zipf_is_null_on_exactly_the_surfaces_nobody_counted(
    enriched: Enriched,
) -> None:
    # A word with no frequency has no rank, so it has no residual, and a zero
    # would claim it sits exactly on the line. "No frequency" is broader than
    # "never observed": a dictionary is a word list rather than a count, so its
    # surfaces arrive observed with a count of zero, and zero occurrences is not
    # a measured frequency either.
    conn = open_store(enriched.db)
    try:
        uncounted = _scalar(
            conn,
            "SELECT count(*) FROM signal WHERE word NOT IN "
            "(SELECT surface FROM observation GROUP BY surface HAVING SUM(count) > 0)",
        )
        assert uncounted > 0
        assert _scalar(conn, "SELECT count(*) FROM signal WHERE zipf IS NULL") == (
            uncounted
        )
    finally:
        conn.close()


def test_a_neighbour_score_is_one_of_the_three_it_can_be(enriched: Enriched) -> None:
    conn = open_store(enriched.db)
    try:
        assert (
            _scalar(
                conn,
                "SELECT count(*) FROM signal WHERE neighbour IS NOT NULL "
                "AND neighbour NOT IN (0.0, 0.5, 1.0)",
            )
            == 0
        )
    finally:
        conn.close()


def test_the_dictionary_is_the_attested_headwords_that_are_wholly_tamil(
    enriched: Enriched,
) -> None:
    # FLAG 1. Decision 1 says "trained only on authority headwords"; Row 7 then
    # measured that a fifth of them are not Tamil at all. The training set is
    # the intersection, and both counts are reported rather than only the one
    # that survives.
    run = enrich(enriched.registry, CONFIG, enriched.db, workers=1)
    census = run.state[HEADWORDS]
    assert isinstance(census, HeadwordCensus)
    assert 0 < census.tamil <= census.attested
    conn = open_store(enriched.db)
    try:
        attested = _scalar(
            conn,
            "SELECT count(*) FROM signal WHERE attested > 0",
        )
    finally:
        conn.close()
    assert census.attested == attested


def test_the_model_and_the_index_read_the_same_dictionary(enriched: Enriched) -> None:
    run = enrich(enriched.registry, CONFIG, enriched.db, workers=1)
    census = run.state[HEADWORDS]
    index = run.state[NEIGHBOUR_INDEX]
    model = run.state[NGRAM_MODEL]
    assert isinstance(census, HeadwordCensus)
    assert isinstance(index, neighbours.NeighbourIndex)
    assert isinstance(model, ngram.NgramModel)
    # One dictionary, consulted twice: the index dedupes on the encoded form, so
    # it can only ever be at or below the model's word count.
    assert len(index.headwords) <= census.tamil
    assert model.words == census.tamil


def test_the_fitted_line_is_reported_with_the_run(enriched: Enriched) -> None:
    run = enrich(enriched.registry, CONFIG, enriched.db, workers=1)
    fit = run.state[ZIPF_FIT]
    assert fit is not None
    assert getattr(fit, "surfaces", 0) > 0


@pytest.mark.parametrize("column", INEXACT)
def test_two_runs_over_one_staged_zone_write_the_same_column(
    enriched: Enriched, column: str
) -> None:
    # THE ORACLE. The derived zone is dropped and recomputed whole, so a second
    # run is a completely independent computation over the same staged rows -
    # and it has to land on the same bytes.
    first = _column_digest(enriched.db, column)
    enrich(enriched.registry, CONFIG, enriched.db, workers=1)
    assert _column_digest(enriched.db, column) == first


def test_scoring_across_processes_writes_the_same_column(enriched: Enriched) -> None:
    # The scheduling half of the Oracle. Results come back in the order the
    # chunks went out and a word's score is a pure function of the word and the
    # index, so the column cannot depend on which worker finished first.
    single = _column_digest(enriched.db, "neighbour")
    enrich(enriched.registry, CONFIG, enriched.db, workers=3)
    assert _column_digest(enriched.db, "neighbour") == single


@pytest.mark.parametrize("name", INEXACT)
def test_recomputing_one_inexact_signal_reproduces_what_a_rebuild_wrote(
    enriched: Enriched, name: str
) -> None:
    before = _column_digest(enriched.db, name)
    conn = open_store(enriched.db)
    try:
        stamp = derived_epoch(conn)
    finally:
        conn.close()
    enrich(enriched.registry, CONFIG, enriched.db, name, workers=1)
    conn = open_store(enriched.db)
    try:
        assert derived_epoch(conn) == stamp
    finally:
        conn.close()
    assert _column_digest(enriched.db, name) == before


def test_every_inexact_signal_writes_a_column_the_runner_declares() -> None:
    assert INEXACT == ("ngram", "zipf", "neighbour")
    assert SIGNALS == EXACT_SIGNALS + INEXACT_SIGNALS
    # Exactly one of the three needs a pass of its own, and it is the one whose
    # query set the population pass is still computing.
    assert [signal.name for signal in SIGNALS if signal.second_pass is not None] == [
        "neighbour"
    ]


def test_a_config_naming_a_wider_search_is_refused_before_anything_is_built(
    enriched: Enriched,
) -> None:
    # Row 7's `check_configured_sources` guards the store; this guards the run
    # from a knob nobody can afford, and it fires before the population write.
    broken = CONFIG.model_copy(
        update={
            "neighbour": NeighbourSettings.model_construct(
                maxEditDistance=MAX_EDIT_DISTANCE + 1,
                pruneBreadth=CONFIG.neighbour.pruneBreadth,
            )
        }
    )
    with pytest.raises(ValueError, match="maxEditDistance"):
        enrich(enriched.registry, broken, enriched.db, "neighbour", workers=1)
