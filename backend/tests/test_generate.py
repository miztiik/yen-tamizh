"""Tests for the Row 13 daily puzzle ENGINE: derived wordlist -> puzzle bank.

Real config, the real committed wordlist, and the real committed bank - no mocks
(Holy Law #7). Tamil is written with ``\\uXXXX`` escapes so this source stays
ASCII (CLAUDE.md section 5).

Five things are proven:

1. **The Oracle - determinism.** Two runs of ``generate`` for the same date, into
   two empty banks, produce BYTE-IDENTICAL files; and a run over a copy of the
   COMMITTED bank leaves every published day untouched, because a day that has
   shipped is history rather than a rebuildable artifact.
2. **The contracts.** Every baked day validates against ``puzzle-file``, every
   payload against ``anagram-puzzle``, and the index against ``bank-index``.
3. **Playability.** The tiles rejoin to the answer word (ezhuthu integrity, Row
   6), the scramble is never the solved order, and no word repeats across days.
4. **The knobs.** Difficulty reads BOTH configured axes - ezhuthu length and
   frequency stratum - hints are capped by the app config's per-Game allowance,
   and a mix that does not add up to the playlist length is an error rather than
   a short day.
5. **The seam.** The engine reads the derived wordlist and nothing above it, and
   a published day survives a changed wordlist untouched.
6. **Themed days.** On the dates the cadence allows, a theme that can fill every
   slot from its own wordlist fills all of them and the day records its copy
   slug; a theme that cannot is skipped entirely rather than padded out with an
   off-theme word.
7. **The ladder.** A baked ladder never gets cheaper down the array, never sells
   the meaning first, never answers in English and never spells the answer out;
   a rung a word cannot honestly fill is skipped rather than raised, and a
   themed day drops the category rung from every ladder that DAY.
"""

from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from yen_tamizh_backend.contracts.anagram_puzzle import AnagramPuzzle
from yen_tamizh_backend.contracts.app_config import AppConfig
from yen_tamizh_backend.contracts.bank_index import BankIndex
from yen_tamizh_backend.contracts.copy import Copy
from yen_tamizh_backend.contracts.daily_generator import DailyGenerator, GameGeneration
from yen_tamizh_backend.contracts.game_wordlist import GameWord, GameWordlist
from yen_tamizh_backend.contracts.lexicon import PartOfSpeech
from yen_tamizh_backend.contracts.puzzle_file import PuzzleFile
from yen_tamizh_backend.ezhuthu import segment
from yen_tamizh_backend.generate import anagram, daily
from yen_tamizh_backend.generate.seed import hash_seed, seeded_index, seeded_shuffle
from yen_tamizh_backend.scripts.generate_today import generate, load_wordlists
from yen_tamizh_backend.wordsmith import derive

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP_CONFIG = _REPO_ROOT / "config" / "app-config.json"
_COPY = _REPO_ROOT / "config" / "copy.json"
_GENERATOR = _REPO_ROOT / "config" / "daily-generator.json"

# The first day the bank was baked (Row 13). Used as a fixed date so the tests
# assert over a real, committed day rather than whatever today happens to be.
FIRST_DAY = "2026-08-13"

# The first day baked from the lexicon-gated wordlist (row 12). Days before it
# were baked from the pre-cutover set and the re-bake guard leaves them alone.
CUTOVER_DAY = "2026-08-23"

# The first day baked from the rebuilt hint ladder (row 14). Earlier days shipped
# the old two-rung ladder and are published history.
LADDER_DAY = "2026-08-18"

# The wordlists are keyed by the path the registry names, because a Game draws
# from more than one: its ordinary set and one per registered theme.
ANAGRAM_SET = "datasets/wordlists/derived/anagram.json"
THEMED_SET = "datasets/wordlists/derived/themed-nature.json"

# A date the configured cadence allows a theme on, and the day after it. Both
# are past the committed bank, so a themed test bakes into empty ground.
THEME_DAY = "2026-08-30"
ORDINARY_DAY = "2026-08-31"


@pytest.fixture(scope="module")
def app_config() -> AppConfig:
    return AppConfig.model_validate_json(_APP_CONFIG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def generator() -> DailyGenerator:
    return DailyGenerator.model_validate_json(_GENERATOR.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def wordlists(generator: DailyGenerator) -> dict[str, GameWordlist]:
    return load_wordlists(generator, _REPO_ROOT)


@pytest.fixture(scope="module")
def bank_dir(generator: DailyGenerator) -> Path:
    return _REPO_ROOT / generator.bankDir


def _committed_days(bank_dir: Path) -> list[Path]:
    return sorted(bank_dir.glob("*/*.json"))


def _committed_span(bank_dir: Path) -> tuple[date, int]:
    """The first committed day and the look-ahead that reaches the last one.

    Derived from the bank rather than pinned, because the daily cron adds a day
    at a time: a fixed window would stop covering the bank the moment it grew.
    """
    days = [date.fromisoformat(path.stem) for path in _committed_days(bank_dir)]
    return days[0], (days[-1] - days[0]).days


def _a_row_with_every_rung(spec: GameGeneration, wordlist: GameWordlist) -> GameWord:
    """A served row the whole configured ladder can be rendered for.

    Only about one served word in fifteen carries a category, so a test about
    the ALLOWANCE has to pick a row the allowance is the binding constraint on.
    """
    return next(
        row
        for row in wordlist.words
        if len(anagram.build_hints(row, spec, 99)) == len(spec.hints)
    )


# --------------------------------------------------------------------------
# 1. The Oracle: determinism
# --------------------------------------------------------------------------


def test_two_runs_for_the_same_date_produce_identical_bytes(
    tmp_path: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """THE Row 13 Oracle: a date is a pure function, not a roll of the dice."""
    first = tmp_path / "run-a"
    second = tmp_path / "run-b"
    day = date.fromisoformat(FIRST_DAY)

    runs = []
    for root in (first, second):
        spec = generator.model_copy(update={"bankDir": "bank"})
        generate(day, root, app_config, spec, wordlists)
        runs.append(
            {
                path.relative_to(root).as_posix(): path.read_bytes()
                for path in sorted((root / "bank").rglob("*.json"))
            }
        )

    assert runs[0].keys() == runs[1].keys()
    assert runs[0] == runs[1]
    assert f"bank/2026/{FIRST_DAY}.json" in runs[0]


def test_a_rerun_over_the_committed_bank_leaves_every_published_day_alone(
    tmp_path: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
    bank_dir: Path,
) -> None:
    """The published bank is history, and a cron tick may not rewrite history.

    A day is a pure function of its date and of the wordlist it drew from, so
    once that wordlist changes the committed days are no longer re-derivable -
    which is exactly why they are frozen rather than regenerated. This runs the
    real entry point over a copy of the REAL bank and proves nothing moves.
    """
    bank_copy = tmp_path / "bank"
    shutil.copytree(bank_dir, bank_copy)
    before = {
        path.relative_to(bank_copy).as_posix(): path.read_bytes()
        for path in sorted(bank_copy.rglob("*.json"))
    }
    start, days_ahead = _committed_span(bank_dir)
    spec = generator.model_copy(update={"bankDir": "bank", "daysAhead": days_ahead})

    run = generate(start, tmp_path, app_config, spec, wordlists)

    after = {
        path.relative_to(bank_copy).as_posix(): path.read_bytes()
        for path in sorted(bank_copy.rglob("*.json"))
    }
    assert run.written == []
    assert after == before


def test_a_rerun_over_an_existing_bank_is_idempotent(
    tmp_path: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """A day must not treat its own previous output as a reason to change."""
    spec = generator.model_copy(update={"bankDir": "bank"})
    day = date.fromisoformat(FIRST_DAY)
    generate(day, tmp_path, app_config, spec, wordlists)
    before = {
        path: path.read_bytes() for path in sorted((tmp_path / "bank").rglob("*.json"))
    }
    # Forced, so this still proves the day is a pure function rather than merely
    # proving the guard below skipped it.
    generate(day, tmp_path, app_config, spec, wordlists, rebake=True)
    after = {
        path: path.read_bytes() for path in sorted((tmp_path / "bank").rglob("*.json"))
    }
    assert before == after


def test_the_seeded_shuffle_is_stable_and_permutes(tmp_path: Path) -> None:
    items = ["a", "b", "c", "d", "e"]
    once = seeded_shuffle(items, "2026-08-13|anagram")
    twice = seeded_shuffle(items, "2026-08-13|anagram")
    assert once == twice
    assert sorted(once) == sorted(items)
    assert seeded_shuffle(items, "2026-08-14|anagram") != once
    assert hash_seed("2026-08-13") == hash_seed("2026-08-13")
    assert hash_seed("2026-08-13") != hash_seed("2026-08-14")


def test_seeded_index_is_stable_and_covers_its_whole_range() -> None:
    seeds = [f"2026-08-{day:02d}|anagram|hard" for day in range(1, 32)]
    picks = [seeded_index(4, seed) for seed in seeds]
    assert picks == [seeded_index(4, seed) for seed in seeds]
    assert set(picks) == {0, 1, 2, 3}
    assert seeded_index(1, "anything") == 0
    with pytest.raises(ValueError, match="count must be positive"):
        seeded_index(0, "anything")


def test_seeded_index_does_not_inherit_the_low_bit_correlation() -> None:
    """FNV-1a's low bit is the XOR of its inputs' low bits - so it cannot pick.

    The two band seeds below share that parity, so ``hash_seed(...) % n`` gave
    the medium and hard buckets the SAME stratum rotation on every single date -
    two \"random\" choices that were one choice wearing two names. The regression
    this pins is that the digest is mixed before it is reduced.
    """
    days = [f"2026-09-{day:02d}" for day in range(1, 31)]
    raw = {
        hash_seed(f"{day}|anagram|medium") % 2 == hash_seed(f"{day}|anagram|hard") % 2
        for day in days
    }
    assert raw == {True}, "the trap this test exists for has changed shape"

    mixed = [
        (
            seeded_index(2, f"{day}|anagram|medium"),
            seeded_index(4, f"{day}|anagram|hard") % 2,
        )
        for day in days
    ]
    assert any(medium != hard for medium, hard in mixed)


# --------------------------------------------------------------------------
# 1a. The guard: a published day is never rewritten
# --------------------------------------------------------------------------


def _reordered(wordlists: dict[str, GameWordlist]) -> dict[str, GameWordlist]:
    """The same real rows in a different order - what a wordlist change looks like.

    A day is a pure function of its date AND of the list it drew from, so
    reordering the candidates is enough to make every later pick differ.
    """
    return {
        path: wordlist.model_copy(update={"words": list(reversed(wordlist.words))})
        for path, wordlist in wordlists.items()
    }


def test_a_changed_wordlist_does_not_rewrite_a_day_already_baked(
    tmp_path: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """A published day has shipped, and a player may be part-way through it."""
    spec = generator.model_copy(update={"bankDir": "bank"})
    day = date.fromisoformat(FIRST_DAY)
    generate(day, tmp_path, app_config, spec, wordlists)
    published = {
        path: path.read_bytes()
        for path in sorted((tmp_path / "bank").rglob("2026/*.json"))
    }
    assert published, "nothing was baked to guard"

    run = generate(day, tmp_path, app_config, spec, _reordered(wordlists))

    assert run.written == []
    assert run.skipped == sorted(path.stem for path in published)
    for path, before in published.items():
        assert path.read_bytes() == before, path.name


def test_the_guard_still_bakes_the_days_that_are_missing(
    tmp_path: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """Skipping published days must not stop the look-ahead from growing."""
    spec = generator.model_copy(update={"bankDir": "bank"})
    generate(date.fromisoformat(FIRST_DAY), tmp_path, app_config, spec, wordlists)

    run = generate(
        date.fromisoformat(FIRST_DAY) + timedelta(days=1),
        tmp_path,
        app_config,
        spec,
        wordlists,
    )

    assert [day.date for day in run.written] == ["2026-08-20"]
    index = BankIndex.model_validate_json(
        (tmp_path / "bank" / "index.json").read_text(encoding="utf-8")
    )
    assert [entry.date for entry in index.days] == sorted(
        path.stem for path in (tmp_path / "bank").rglob("2026/*.json")
    )


def test_the_index_is_rebuilt_from_disk_even_when_every_day_is_skipped(
    tmp_path: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """The guard may not leave the manifest behind the days it lists."""
    spec = generator.model_copy(update={"bankDir": "bank"})
    day = date.fromisoformat(FIRST_DAY)
    generate(day, tmp_path, app_config, spec, wordlists)
    index_path = tmp_path / "bank" / "index.json"
    expected = index_path.read_bytes()
    index_path.unlink()

    run = generate(day, tmp_path, app_config, spec, wordlists)

    assert run.written == []
    assert index_path.read_bytes() == expected


def test_rebake_is_the_deliberate_way_to_rewrite_a_published_day(
    tmp_path: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    spec = generator.model_copy(update={"bankDir": "bank"})
    day = date.fromisoformat(FIRST_DAY)
    generate(day, tmp_path, app_config, spec, wordlists)
    before = (tmp_path / "bank" / "2026" / f"{FIRST_DAY}.json").read_bytes()

    run = generate(day, tmp_path, app_config, spec, _reordered(wordlists), rebake=True)

    assert run.skipped == []
    assert len(run.written) == generator.daysAhead + 1
    assert (tmp_path / "bank" / "2026" / f"{FIRST_DAY}.json").read_bytes() != before


# --------------------------------------------------------------------------
# 2. The contracts
# --------------------------------------------------------------------------


def test_every_committed_day_validates_against_puzzle_file(bank_dir: Path) -> None:
    days = _committed_days(bank_dir)
    assert days, "the bank has no baked days"
    for path in days:
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        assert puzzle_file.date == path.stem
        assert path.parent.name == puzzle_file.date[:4]


def test_every_committed_payload_validates_against_anagram_puzzle(
    bank_dir: Path,
) -> None:
    """The item payload carries no schema stamp, so validation supplies one."""
    for path in _committed_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            assert set(item.payload) & {"version", "changelog"} == set()
            AnagramPuzzle.model_validate(
                {
                    "version": "2026-08-13",
                    "changelog": [
                        {"version": "2026-08-13", "change": "test", "why": "test"}
                    ],
                    **item.payload,
                }
            )


def test_the_committed_index_matches_the_committed_days(bank_dir: Path) -> None:
    index = BankIndex.model_validate_json(
        (bank_dir / "index.json").read_text(encoding="utf-8")
    )
    days = _committed_days(bank_dir)
    assert [entry.date for entry in index.days] == [path.stem for path in days]
    for entry, path in zip(index.days, days, strict=True):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert entry.itemCount == len(payload["items"])


def test_today_is_in_the_committed_bank(bank_dir: Path) -> None:
    assert daily.day_path(bank_dir, FIRST_DAY).exists()


# --------------------------------------------------------------------------
# 3. Playability over the real bank
# --------------------------------------------------------------------------


def test_tiles_rejoin_to_the_answer_and_are_never_pre_solved(bank_dir: Path) -> None:
    for path in _committed_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            word = str(item.payload["word"])
            tiles = [str(tile) for tile in item.payload["tiles"]]
            solved = segment(word)
            assert sorted(tiles) == sorted(solved), word
            assert "".join(sorted(tiles)) == "".join(sorted(solved))
            assert tiles != solved, f"{word} ships pre-solved on {puzzle_file.date}"


def test_no_word_is_served_twice_across_the_bank(bank_dir: Path) -> None:
    seen: dict[str, str] = {}
    for path in _committed_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            word = str(item.payload["word"])
            assert word not in seen, f"{word} repeats ({seen.get(word)} and {path.stem})"
            seen[word] = path.stem


def test_every_served_word_comes_from_the_derived_wordlist(
    bank_dir: Path, wordlists: dict[str, GameWordlist]
) -> None:
    """The engine consumes the derived layer; it never invents a word.

    Scoped to the days baked from the CURRENT wordlist. A published day is a
    pure function of its date AND of the wordlist it drew from, so once that
    wordlist moves the earlier days stop being checkable against it - they are
    history the re-bake guard deliberately preserves, not a rebuildable
    artifact.
    """
    allowed = {
        row.word
        for path in (ANAGRAM_SET, THEMED_SET)
        for row in wordlists[path].words
    }
    checked = 0
    for path in _committed_days(bank_dir):
        if path.stem < CUTOVER_DAY:
            continue
        checked += 1
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            assert str(item.payload["word"]) in allowed
    assert checked, "no day was baked from the current wordlist"


def test_no_day_baked_since_the_cutover_serves_a_proper_noun(bank_dir: Path) -> None:
    """The goal of the cutover, asserted over the committed bank.

    Scoped to the days the cutover reaches: the earlier days are history the
    re-bake guard deliberately leaves alone, and rewriting a day a player has
    already played buys nothing (row 12 decision 7).
    """
    meta = derive.load_meta(_REPO_ROOT / "datasets" / "lexicon" / "lexicon.meta.json")
    proper_nouns = {
        row.word for row in derive.read_rows(meta, _REPO_ROOT, ["properNoun"])
    }
    assert proper_nouns, "the lexicon publishes no proper nouns to guard against"
    for path in _committed_days(bank_dir):
        if path.stem < CUTOVER_DAY:
            continue
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            word = str(item.payload["word"])
            assert word not in proper_nouns, f"{path.stem} serves {word}"


def test_a_day_holds_exactly_the_configured_playlist(
    bank_dir: Path, app_config: AppConfig
) -> None:
    for path in _committed_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        assert len(puzzle_file.items) == app_config.daily.playlistLength
        for game_id, count in app_config.daily.mix.items():
            assert sum(1 for item in puzzle_file.items if item.gameId == game_id) == count


# --------------------------------------------------------------------------
# 4. The knobs
# --------------------------------------------------------------------------


def test_difficulty_reads_both_length_and_familiarity(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    spec = generator.games[0]
    bands = {
        band.id: (band.minLength, band.maxLength, band.maxStratum)
        for band in spec.difficulties
    }
    claimed = 0
    for row in wordlists[ANAGRAM_SET].words:
        bucket = anagram.difficulty_of(row, spec)
        if bucket is None:
            # No band claims it, so no slot can draw it - see bucket_candidates.
            continue
        claimed += 1
        low, high, top = bands[bucket]
        assert low <= len(row.ezhuthu) <= high
        assert row.frequencyStratum <= top
    assert claimed, "no served word lands in any difficulty band"


def test_the_easiest_band_admits_only_the_most_familiar_quarter(
    generator: DailyGenerator,
) -> None:
    """This is what makes a day of three unfamiliar words structurally impossible."""
    assert generator.games[0].difficulties[0].maxStratum == 1


def test_a_word_no_band_claims_is_dropped_rather_than_relabelled(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    spec = generator.games[0]
    buckets = daily.bucket_candidates(wordlists[ANAGRAM_SET].words, spec)
    assert set(buckets) == {band.id for band in spec.difficulties}
    bucketed = sum(len(rows) for rows in buckets.values())
    unclaimed = [
        row
        for row in wordlists[ANAGRAM_SET].words
        if anagram.difficulty_of(row, spec) is None
    ]
    assert bucketed + len(unclaimed) == len(wordlists[ANAGRAM_SET].words)
    for row in unclaimed:
        assert row not in buckets[spec.difficulties[-1].id]


def test_hints_are_capped_by_the_app_config_allowance(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    spec = generator.games[0]
    row = _a_row_with_every_rung(spec, wordlists[ANAGRAM_SET])
    assert anagram.build_hints(row, spec, 0) == []
    assert len(anagram.build_hints(row, spec, 1)) == 1
    assert len(anagram.build_hints(row, spec, 99)) == len(spec.hints)
    assert row.hints is not None
    assert row.hints.firstEzhuthu in anagram.build_hints(row, spec, 2)[1].text


def test_the_allowance_admits_the_whole_ladder(
    app_config: AppConfig, generator: DailyGenerator
) -> None:
    """Left below the ladder's height, the dearest rung would never be baked."""
    assert app_config.hints.perGame["anagram"] >= len(generator.games[0].hints)


def test_committed_hints_honour_the_app_config(
    bank_dir: Path, app_config: AppConfig
) -> None:
    allowance = app_config.hints.perGame.get("anagram", 0)
    for path in _committed_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            hints = item.payload.get("hints", [])
            assert len(hints) <= allowance
            assert app_config.hints.enabled or hints == []
            for hint in hints:
                assert str(item.payload["word"]) not in hint["text"]


def test_a_mix_that_does_not_add_up_is_an_error(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    broken = app_config.model_copy(
        update={"daily": app_config.daily.model_copy(update={"playlistLength": 99})}
    )
    with pytest.raises(ValueError, match="playlistLength"):
        daily.build_day(FIRST_DAY, broken, generator, wordlists, used=())


def test_a_mix_naming_an_unregistered_game_is_an_error(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    broken = app_config.model_copy(
        update={
            "daily": app_config.daily.model_copy(
                update={"playlistLength": 1, "mix": {"word-ladder": 1}}
            )
        }
    )
    with pytest.raises(ValueError, match="no generator"):
        daily.build_day(FIRST_DAY, broken, generator, wordlists, used=())


def test_a_hint_template_naming_an_unknown_field_fails_loudly(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """A typo in config must not vanish into a silently shorter ladder.

    ``{length}`` is the sharpest case: it is a real field on every row and it
    named the deleted rung, so leaving it fillable would let one config line put
    the fake hint back.
    """
    spec = generator.games[0]
    for field in ("{length}", "{freqBand}"):
        broken = spec.model_copy(
            update={"hints": [spec.hints[0].model_copy(update={"template": field})]}
        )
        with pytest.raises(KeyError):
            anagram.build_hints(wordlists[ANAGRAM_SET].words[0], broken, 1)


# --------------------------------------------------------------------------
# 5. Selection + the layer seam
# --------------------------------------------------------------------------


def test_selection_skips_words_already_served(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    spec = generator.games[0]
    candidates = wordlists[ANAGRAM_SET].words
    plain = daily.pick_words(candidates, spec, FIRST_DAY, 3, used=())
    assert len(plain) == 3
    avoided = daily.pick_words(
        candidates, spec, FIRST_DAY, 3, used={row.word for row, _ in plain}
    )
    assert {row.word for row, _ in avoided}.isdisjoint({row.word for row, _ in plain})


def test_a_day_is_dealt_round_robin_across_the_difficulty_bands(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """A day is a curve, not three rolls of the same dice."""
    spec = generator.games[0]
    picked = daily.pick_words(wordlists[ANAGRAM_SET].words, spec, FIRST_DAY, 3, used=())
    assert [difficulty for _, difficulty in picked] == [
        band.id for band in spec.difficulties
    ]
    for row, difficulty in picked:
        assert anagram.difficulty_of(row, spec) == difficulty


def test_the_draw_within_a_band_is_stratified_not_uniform(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """Every window of four holds one word from each quarter, by construction."""
    spec = generator.games[0]
    pool = daily.bucket_candidates(wordlists[ANAGRAM_SET].words, spec)[
        spec.difficulties[-1].id
    ]
    order = daily.stratified_order(pool, f"{FIRST_DAY}|anagram|hard")

    assert len(order) == len(pool)
    assert {row.word for row in order} == {row.word for row in pool}
    strata = sorted({row.frequencyStratum for row in pool})
    window = [row.frequencyStratum for row in order[: len(strata)]]
    assert sorted(window) == strata


def test_the_stratified_order_is_a_pure_function_of_its_seed(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    spec = generator.games[0]
    pool = daily.bucket_candidates(wordlists[ANAGRAM_SET].words, spec)["easy"]
    first = [row.word for row in daily.stratified_order(pool, "seed")]
    assert [row.word for row in daily.stratified_order(pool, "seed")] == first
    assert [row.word for row in daily.stratified_order(pool, "other")] != first


def test_selection_fills_the_day_even_when_everything_was_served(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """A repeat is a smaller failure than a playlist that does not add up."""
    spec = generator.games[0]
    candidates = wordlists[ANAGRAM_SET].words
    filled = daily.pick_words(
        candidates, spec, FIRST_DAY, 3, used={row.word for row in candidates}
    )
    assert len(filled) == 3


def test_selection_with_no_candidates_is_an_error(generator: DailyGenerator) -> None:
    with pytest.raises(ValueError, match="no candidate words"):
        daily.pick_words([], generator.games[0], FIRST_DAY, 1, used=())


def test_a_band_with_an_empty_bucket_is_an_error(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """A day short of a band must fail loudly, never silently pick from another."""
    spec = generator.games[0]
    only_hard = [
        row
        for row in wordlists[ANAGRAM_SET].words
        if anagram.difficulty_of(row, spec) == "hard"
    ]
    with pytest.raises(ValueError, match="easy"):
        daily.pick_words(only_hard, spec, FIRST_DAY, 3, used=())


def test_the_engine_reads_only_the_derived_layer() -> None:
    """The lexicon and the daily puzzle are different layers (user directive)."""
    forbidden = ("yen_tamizh_backend.wordsmith",)
    for module in ("daily.py", "anagram.py", "seed.py", "__init__.py"):
        source = (
            _REPO_ROOT / "backend" / "yen_tamizh_backend" / "generate" / module
        ).read_text(encoding="utf-8")
        body = "\n".join(
            line for line in source.splitlines() if line.startswith(("import", "from"))
        )
        for name in forbidden:
            assert name not in body, f"{module} imports {name}"


def test_generated_paths_are_relative_and_posix(
    tmp_path: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    spec = generator.model_copy(update={"bankDir": "bank"})
    run = generate(date.fromisoformat(FIRST_DAY), tmp_path, app_config, spec, wordlists)
    assert len(run.written) == generator.daysAhead + 1
    for day in run.written:
        assert not day.rel_path.startswith("/")
        assert "\\" not in day.rel_path
        assert day.rel_path == f"bank/{day.date[:4]}/{day.date}.json"


def test_the_configured_bank_lives_inside_the_frontend_bundle(
    generator: DailyGenerator,
) -> None:
    """Same-origin, in-bundle, offline (Holy Law #1) - never a CDN."""
    assert generator.bankDir.startswith("frontend/public/")


# --------------------------------------------------------------------------
# 6. Themed days (row 15)
# --------------------------------------------------------------------------


def test_the_theme_cadence_is_a_pure_function_of_the_date(
    generator: DailyGenerator,
) -> None:
    """Exactly one date in every window, decided by the date and nothing else."""
    cadence = generator.themeEveryNDays
    assert cadence > 0
    start = date.fromisoformat(FIRST_DAY)
    flags = [
        daily.is_theme_date((start + timedelta(days=offset)).isoformat(), generator)
        for offset in range(cadence * 3)
    ]
    assert sum(flags) == 3
    for window in range(3):
        assert sum(flags[window * cadence : (window + 1) * cadence]) == 1
    assert daily.is_theme_date(THEME_DAY, generator)
    assert not daily.is_theme_date(ORDINARY_DAY, generator)


def test_a_cadence_of_zero_turns_themed_days_off(generator: DailyGenerator) -> None:
    """The off switch is a knob, not a code path that has to be deleted."""
    off = generator.model_copy(update={"themeEveryNDays": 0})
    start = date.fromisoformat(FIRST_DAY)
    assert not any(
        daily.is_theme_date((start + timedelta(days=offset)).isoformat(), off)
        for offset in range(30)
    )


def test_a_theme_date_draws_the_whole_day_from_one_theme_and_says_so(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """THE row 15 mechanism: the themed set is a set the day loop actually reads."""
    puzzle = daily.build_day(THEME_DAY, app_config, generator, wordlists, used=())

    assert puzzle.theme == "theme-nature"
    themed = {row.word for row in wordlists[THEMED_SET].words}
    served = {str(item.payload["word"]) for item in puzzle.items}
    assert served <= themed
    assert len(puzzle.items) == app_config.daily.playlistLength
    assert [item.difficulty for item in puzzle.items] == [
        band.id for band in generator.games[0].difficulties
    ]


def test_an_ordinary_date_records_no_theme(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    puzzle = daily.build_day(ORDINARY_DAY, app_config, generator, wordlists, used=())

    assert puzzle.theme is None
    assert "theme" not in puzzle.model_dump(mode="json", exclude_none=True)


def test_a_themed_day_is_a_pure_function_of_its_date(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    first = daily.build_day(THEME_DAY, app_config, generator, wordlists, used=())
    second = daily.build_day(THEME_DAY, app_config, generator, wordlists, used=())
    assert first.model_dump() == second.model_dump()


def test_a_theme_that_cannot_fill_the_day_is_skipped_rather_than_padded(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """Half a theme is not a round: the day becomes ordinary, whole (decision 5)."""
    themed = {row.word for row in wordlists[THEMED_SET].words}
    puzzle = daily.build_day(THEME_DAY, app_config, generator, wordlists, used=themed)

    assert puzzle.theme is None
    assert len(puzzle.items) == app_config.daily.playlistLength
    assert {str(item.payload["word"]) for item in puzzle.items}.isdisjoint(themed)


def test_a_theme_one_word_short_fills_none_of_the_day(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """A theme is all-or-nothing: it never contributes a partial playlist."""
    spec = generator.games[0]
    rows = wordlists[THEMED_SET].words
    full = daily.theme_can_fill(rows, spec, THEME_DAY, 3, used=())
    assert full is not None
    assert len({row.word for row, _ in full}) == 3

    almost = {row.word for row in rows} - {full[0][0].word}
    assert daily.theme_can_fill(rows, spec, THEME_DAY, 3, used=almost) is None


def test_a_theme_with_an_empty_difficulty_bucket_declines_instead_of_raising(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """An ordinary day short of a band is an error; a theme has somewhere to go."""
    spec = generator.games[0]
    hard_only = [
        row
        for row in wordlists[THEMED_SET].words
        if anagram.difficulty_of(row, spec) == "hard"
    ]
    assert hard_only

    assert daily.theme_can_fill(hard_only, spec, THEME_DAY, 3, used=()) is None
    with pytest.raises(ValueError, match="easy"):
        daily.pick_words(hard_only, spec, THEME_DAY, 3, used=())


def test_a_baked_themed_day_carries_its_slug_on_disk(
    tmp_path: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    spec = generator.model_copy(update={"bankDir": "bank", "daysAhead": 0})
    generate(date.fromisoformat(THEME_DAY), tmp_path, app_config, spec, wordlists)

    raw = json.loads(
        (tmp_path / "bank" / "2026" / f"{THEME_DAY}.json").read_text(encoding="utf-8")
    )
    assert raw["theme"] == "theme-nature"
    PuzzleFile.model_validate(raw)


def test_every_registered_theme_has_player_facing_copy(
    generator: DailyGenerator,
) -> None:
    """A Tamil theme name is copy, so the day bakes the SLUG and copy holds the word."""
    copy = Copy.model_validate_json(_COPY.read_text(encoding="utf-8"))
    slugs = [theme.copySlug for spec in generator.games for theme in spec.themes]
    assert slugs
    for slug in slugs:
        assert copy.strings.get(slug), f"{slug} has no player-facing copy"


def test_every_registered_theme_names_a_registered_derived_set(
    generator: DailyGenerator,
) -> None:
    registry = derive.load_registry(_REPO_ROOT / "config" / "derived-wordlists.json")
    registered = {entry.out for entry in registry.sets}
    for spec in generator.games:
        assert spec.wordlist in registered
        for theme in spec.themes:
            assert theme.wordlist in registered


def test_a_theme_pointing_at_the_ordinary_wordlist_is_rejected(
    generator: DailyGenerator,
) -> None:
    """Every day themed is no theme at all, and the header would be a lie."""
    payload = generator.games[0].model_dump()
    payload["themes"] = [{"wordlist": payload["wordlist"], "copySlug": "theme-nature"}]
    with pytest.raises(ValidationError, match="repeated wordlist"):
        GameGeneration.model_validate(payload)


def test_every_committed_themed_day_serves_only_its_own_theme(
    bank_dir: Path, generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """A day that announces a theme must have drawn every word from it."""
    by_slug = {
        theme.copySlug: theme.wordlist
        for spec in generator.games
        for theme in spec.themes
    }
    for path in _committed_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        if puzzle_file.theme is None:
            continue
        allowed = {row.word for row in wordlists[by_slug[puzzle_file.theme]].words}
        for item in puzzle_file.items:
            assert str(item.payload["word"]) in allowed, path.stem


# --------------------------------------------------------------------------
# 7. The hint ladder, the meaning, and the other words the tiles spell (row 14)
# --------------------------------------------------------------------------


def _ladder_days(bank_dir: Path) -> list[Path]:
    """The committed days baked from the rebuilt ladder.

    Earlier days shipped the old two-hint ladder and are history the re-bake
    guard leaves alone (row 12 decision 7): rewriting a day a player has already
    played buys nothing, so the ladder's invariants are asserted over the days
    it actually reaches.
    """
    days = [path for path in _committed_days(bank_dir) if path.stem >= LADDER_DAY]
    assert days, "no day was baked from the rebuilt ladder"
    return days


def _baked_hints(path: Path) -> list[list[dict[str, Any]]]:
    puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
    return [list(item.payload.get("hints", [])) for item in puzzle_file.items]


def test_the_baked_ladder_never_gets_cheaper(bank_dir: Path) -> None:
    """THE row 14 Oracle, over whatever length each day's ladder came out.

    The array is walked in order rather than chosen from, so a rung that cost
    less than the one before it would be unreachable without buying the dearer
    one first. The lengths vary - a rung a word cannot answer is skipped - which
    is exactly why this is asserted over the array as baked rather than over the
    config alone.
    """
    lengths = set()
    for path in _ladder_days(bank_dir):
        for hints in _baked_hints(path):
            costs = [int(hint["cost"]) for hint in hints]
            assert costs == sorted(costs), f"{path.stem}: {costs}"
            lengths.add(len(costs))
    assert len(lengths) > 1, "every ladder came out the same length"


def test_the_dearest_rung_is_never_the_first_one_offered(bank_dir: Path) -> None:
    """A meaning at position 1 is the whole answer sold before anything cheaper."""
    for path in _ladder_days(bank_dir):
        for hints in _baked_hints(path):
            assert not hints or hints[0]["kind"] != "meaning", path.stem


def test_the_config_refuses_a_ladder_that_gets_cheaper(
    generator: DailyGenerator,
) -> None:
    payload = generator.games[0].model_dump()
    payload["hints"] = list(reversed(payload["hints"]))
    with pytest.raises(ValidationError, match="non-decreasing cost"):
        GameGeneration.model_validate(payload)


def test_the_fake_length_rung_is_gone(generator: DailyGenerator) -> None:
    """Deleted from the config AND from the vocabulary, so it cannot come back."""
    assert [hint.kind for hint in generator.games[0].hints] == [
        "category",
        "first-ezhuthu",
        "meaning",
    ]
    assert "length" not in anagram.HINT_FIELDS


def test_a_rung_this_row_cannot_answer_is_skipped_rather_than_raised(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """Only about one served word in fifteen carries a category."""
    spec = generator.games[0]
    rows = wordlists[ANAGRAM_SET].words
    without = next(row for row in rows if not row.categories)
    kinds = [hint.kind for hint in anagram.build_hints(without, spec, 99)]
    assert "category" not in kinds
    assert kinds, "skipping one rung emptied the whole ladder"
    assert kinds == [hint.kind for hint in spec.hints if hint.kind != "category"]


def test_most_served_words_get_a_shorter_ladder_than_the_config_offers(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """A ladder that is sometimes two rungs is correct, and it is the usual case."""
    spec = generator.games[0]
    rows = wordlists[ANAGRAM_SET].words
    shorter = sum(1 for row in rows if len(anagram.build_hints(row, spec, 99)) < 3)
    assert shorter > len(rows) // 2


def test_a_baked_hint_never_answers_in_english(
    bank_dir: Path, wordlists: dict[str, GameWordlist]
) -> None:
    """English is banned on a paid rung: the rung is omitted instead."""
    served = {row.word: row for row in wordlists[ANAGRAM_SET].words}
    served.update({row.word: row for row in wordlists[THEMED_SET].words})
    checked = 0
    for path in _ladder_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            row = served[str(item.payload["word"])]
            for hint in item.payload.get("hints", []):
                text = str(hint["text"])
                assert row.translationEn is None or row.translationEn not in text
                assert not any("a" <= char.lower() <= "z" for char in text)
                checked += 1
    assert checked


def test_the_meaning_rung_never_reaches_for_english(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """Proven where it is decided, not only where it happened not to fire.

    A row stripped of every Tamil meaning still carries an English gloss, and
    the rung must be dropped rather than answered from it.
    """
    spec = generator.games[0]
    row = next(
        r for r in wordlists[ANAGRAM_SET].words if r.translationEn and r.definitionTa
    )
    stripped = row.model_copy(update={"definitionTa": None, "synonymsTa": None})
    assert stripped.translationEn
    assert anagram.sellable_meaning(stripped) is None
    assert anagram.display_meaning(stripped) is None
    kinds = [hint.kind for hint in anagram.build_hints(stripped, spec, 99)]
    assert "meaning" not in kinds


def test_a_baked_hint_never_spells_the_answer_out(
    bank_dir: Path, wordlists: dict[str, GameWordlist]
) -> None:
    """A gloss occasionally contains its own headword; a paid rung may not."""
    for path in _ladder_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            word = str(item.payload["word"])
            for hint in item.payload.get("hints", []):
                assert word not in str(hint["text"]), f"{path.stem}: {word}"


def test_a_themed_day_omits_the_category_rung_from_every_ladder(
    bank_dir: Path, generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """Decision 18, proved per DAY rather than per word.

    A themed set is cut ON the categories dimension, so every one of its rows
    carries a category the config names a Tamil tag for. If the omission were
    per word, every themed day would bake three category rungs; it bakes none.
    """
    by_slug = {
        theme.copySlug: theme.wordlist
        for spec in generator.games
        for theme in spec.themes
    }
    spec = generator.games[0]
    themed_days = 0
    for path in _ladder_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        if puzzle_file.theme is None:
            continue
        themed_days += 1
        rows = {
            row.word: row for row in wordlists[by_slug[puzzle_file.theme]].words
        }
        for item in puzzle_file.items:
            row = rows[str(item.payload["word"])]
            # The rung WOULD have rendered on an ordinary day - that is what
            # makes the omission the day's doing rather than the word's.
            assert anagram.category_tag(row, spec) is not None
            kinds = [hint["kind"] for hint in item.payload.get("hints", [])]
            assert "category" not in kinds, path.stem
    assert themed_days, "no committed themed day to check"


def test_an_ordinary_day_still_bakes_a_category_rung(bank_dir: Path) -> None:
    """The counterpart: the rung is alive, so the themed omission means something."""
    kinds = {
        str(hint["kind"])
        for path in _ladder_days(bank_dir)
        for hints in _baked_hints(path)
        for hint in hints
    }
    assert "category" in kinds


def test_every_category_label_is_one_bare_tamil_word(
    generator: DailyGenerator,
) -> None:
    """The ladder's pricing is legible in the shape of what each rung returns."""
    labels = generator.games[0].categoryLabels
    assert labels
    for slug, label in labels.items():
        assert label.split() == [label], slug
        assert not any("a" <= char.lower() <= "z" for char in label), slug


def test_a_part_of_speech_can_never_reach_the_category_rung(
    generator: DailyGenerator,
) -> None:
    """The predecessor's category hint was 'noun', which narrows nothing.

    Structural rather than incidental: the labels are keyed on the lexicon's
    closed category vocabulary, and POS labels are routed to a different column
    entirely (row 11 decision 3), so no part of speech has a key to be given a
    tag under.
    """
    registry = json.loads(
        (_REPO_ROOT / "config" / "lexicon-sources.json").read_text(encoding="utf-8")
    )
    categories = set(registry["categoryAliases"].values())
    assert set(generator.games[0].categoryLabels) <= categories
    assert categories.isdisjoint(get_args(PartOfSpeech))


def test_every_served_word_can_say_what_it_means(bank_dir: Path) -> None:
    """requireMeaning is what makes the summary line unconditional."""
    for path in _ladder_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            meaning = item.payload.get("meaning")
            assert isinstance(meaning, str) and meaning, (
                f"{path.stem}: {item.payload['word']}"
            )


def test_the_summary_meaning_is_the_one_the_rung_sold(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """A player who bought the rung must not meet a second, different gloss."""
    spec = generator.games[0]
    agreed = disagreed = 0
    for row in wordlists[ANAGRAM_SET].words:
        sellable = anagram.sellable_meaning(row)
        if sellable is None:
            # Nothing was sold, so the summary is free to show what it has.
            assert anagram.display_meaning(row) is not None
            disagreed += 1
            continue
        assert anagram.display_meaning(row) == sellable
        agreed += 1
    assert agreed and disagreed


def test_the_multiset_key_agrees_with_the_derived_layer(
    wordlists: dict[str, GameWordlist],
) -> None:
    """The engine may not import the lexicon pipeline, so the twin keys are pinned."""
    for row in wordlists[ANAGRAM_SET].words:
        assert daily.multiset_key(row.ezhuthu) == derive.multiset_key(row.ezhuthu)


def test_also_valid_is_the_other_served_words_the_same_tiles_spell(
    wordlists: dict[str, GameWordlist],
) -> None:
    wordlist = wordlists[ANAGRAM_SET]
    index = daily.alternatives_of(wordlist)
    shared = [row for row in wordlist.words if row.anagramFanOut > 1]
    assert shared, "the served set holds no co-anagram to answer with"
    for row in shared:
        partners = index[daily.multiset_key(row.ezhuthu)]
        # The count the derived layer records and the words baked here are two
        # views of one fact, so they must agree exactly.
        assert len(partners) == row.anagramFanOut
        assert row.word in partners
        for partner in partners:
            assert sorted(segment(partner)) == sorted(row.ezhuthu)


def test_a_baked_puzzle_offers_only_partners_the_day_could_have_served(
    bank_dir: Path, generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """On a themed day the partners must come from the THEME's set, not the
    ordinary one - naming a word the day never serves would be a second lie."""
    by_slug = {
        theme.copySlug: theme.wordlist
        for spec in generator.games
        for theme in spec.themes
    }
    offered = 0
    for path in _ladder_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        source = (
            ANAGRAM_SET if puzzle_file.theme is None else by_slug[puzzle_file.theme]
        )
        served = {row.word for row in wordlists[source].words}
        for item in puzzle_file.items:
            word = str(item.payload["word"])
            for partner in item.payload.get("alsoValid", []):
                offered += 1
                assert partner in served, f"{path.stem}: {partner}"
                assert partner != word
                assert sorted(segment(partner)) == sorted(segment(word))
    assert offered, "no committed day offers an alternative arrangement"


def test_a_puzzle_may_not_list_its_own_answer_as_an_alternative(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    spec = generator.games[0]
    row = wordlists[ANAGRAM_SET].words[0]
    with pytest.raises(ValidationError, match="repeats the answer"):
        anagram.build_puzzle(row, spec, "seed", 3, False, [row.word])
