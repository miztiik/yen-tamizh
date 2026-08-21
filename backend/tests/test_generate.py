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
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from yen_tamizh_backend.contracts.anagram_puzzle import AnagramPuzzle
from yen_tamizh_backend.contracts.app_config import AppConfig
from yen_tamizh_backend.contracts.bank_index import BankIndex
from yen_tamizh_backend.contracts.copy import Copy
from yen_tamizh_backend.contracts.crossword_puzzle import CrosswordEntry, CrosswordPuzzle
from yen_tamizh_backend.contracts.daily_generator import (
    DailyGenerator,
    DifficultyBand,
    GameGeneration,
    HintSpec,
    ThemedSet,
    mask_entries,
)
from yen_tamizh_backend.contracts.game_wordlist import GameWord, GameWordlist
from yen_tamizh_backend.contracts.lexicon import PartOfSpeech
from yen_tamizh_backend.contracts.missing_letters_puzzle import MissingLettersPuzzle
from yen_tamizh_backend.contracts.puzzle_file import PuzzleFile
from yen_tamizh_backend.contracts.word_ladder_puzzle import (
    WordLadderPuzzle,
    added_ezhuthu,
)
from yen_tamizh_backend.contracts.word_search_puzzle import (
    GridPoint,
    WordSearchPuzzle,
    WordSearchTarget,
)
from yen_tamizh_backend.contracts.wordle_puzzle import WordlePuzzle
from yen_tamizh_backend.ezhuthu import EZHUTHU_INVENTORY, segment
from yen_tamizh_backend.generate import (
    Unbuildable,
    anagram,
    crossword,
    daily,
    missing_letters,
    word_ladder,
    word_search,
    wordle,
)
from yen_tamizh_backend.generate import hints as hint_ladder
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

# The first day baked from the two Daily rings - the first day that holds more
# than one Game. Everything before it is three anagrams and is published
# history the re-bake guard leaves alone.
MIX_DAY = "2026-08-21"

# The wordlists are keyed by the path the registry names, because a Game draws
# from more than one: its ordinary set and one per registered theme.
ANAGRAM_SET = "datasets/wordlists/derived/anagram.json"
THEMED_SET = "datasets/wordlists/derived/themed-nature.json"

# A date the configured cadence allows a theme on, and the day after it. Both
# are at or past the end of the committed bank, and every test using them bakes
# from an empty ledger or into a tmp bank, so neither reads committed state.
THEME_DAY = "2026-08-30"
ORDINARY_DAY = "2026-08-31"

# A baked item's payload DROPS version + changelog (the day file carries its
# own), so re-validating one against its per-Game contract needs a stand-in.
_STAMP = {
    "version": "2026-08-19",
    "change": "re-validation stamp",
    "why": "a baked item drops the stamp the model carries",
}


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
    """The item payload carries no schema stamp, so validation supplies one.

    Per-Game, because a day now holds several: each item is validated against
    ITS OWN contract, which is the whole point of the payload being a Game's own
    shape rather than one shared row (the other four are covered by their own
    Game's section).
    """
    checked = 0
    for path in _committed_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            assert set(item.payload) & {"version", "changelog"} == set()
            if item.gameId != "anagram":
                continue
            checked += 1
            AnagramPuzzle.model_validate(
                {
                    "version": "2026-08-13",
                    "changelog": [
                        {"version": "2026-08-13", "change": "test", "why": "test"}
                    ],
                    **item.payload,
                }
            )
    assert checked, "the bank baked no anagram"


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
            if item.gameId != "anagram":
                continue
            word = str(item.payload["word"])
            tiles = [str(tile) for tile in item.payload["tiles"]]
            solved = segment(word)
            assert sorted(tiles) == sorted(solved), word
            assert "".join(sorted(tiles)) == "".join(sorted(solved))
            assert tiles != solved, f"{word} ships pre-solved on {puzzle_file.date}"


def test_no_word_is_served_twice_across_the_bank(bank_dir: Path) -> None:
    """Every ANSWER, not every headline word: a board with several is several."""
    seen: dict[str, str] = {}
    for path in _committed_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            for word in daily.answer_words(item.payload):
                assert word not in seen, (
                    f"{word} repeats ({seen.get(word)} and {path.stem})"
                )
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
    allowed = {row.word for words in wordlists.values() for row in words.words}
    checked = 0
    for path in _committed_days(bank_dir):
        if path.stem < CUTOVER_DAY:
            continue
        checked += 1
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            for word in daily.answer_words(item.payload):
                assert word in allowed
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
            for word in daily.answer_words(item.payload):
                assert word not in proper_nouns, f"{path.stem} serves {word}"


def test_a_day_holds_exactly_the_configured_playlist(
    bank_dir: Path, app_config: AppConfig
) -> None:
    """Every committed day is the configured length and holds only served Games.

    The per-Game COUNT is deliberately not asserted here: which Games a day
    holds is a window that walks with the date, so a fixed count would be a
    claim about one date rather than about the bank. What every day owes is its
    length and its membership.
    """
    known = set(app_config.daily.games) | set(app_config.daily.themedGames)
    for path in _committed_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        assert len(puzzle_file.items) == app_config.daily.playlistLength
        for item in puzzle_file.items:
            assert item.gameId in known, f"{path.stem} serves {item.gameId}"


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
        bucket = daily.difficulty_of(row, spec)
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
        if daily.difficulty_of(row, spec) is None
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
    for path in _committed_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            allowance = app_config.hints.perGame.get(item.gameId, 0)
            hints = item.payload.get("hints", [])
            assert len(hints) <= allowance
            assert app_config.hints.enabled or hints == []
            for hint in hints:
                for word in daily.answer_words(item.payload):
                    assert word not in hint["text"]


def test_a_playlist_longer_than_the_ring_is_refused_by_the_contract(
    app_config: AppConfig,
) -> None:
    """An ordinary day that had to deal the same Game twice is a config error.

    The ring is what makes variety structural rather than hoped for, so the
    refusal lives in the contract: a config that could not honour it never
    reaches the day loop.
    """
    payload = app_config.daily.model_dump()
    payload["playlistLength"] = len(payload["games"]) + 1
    with pytest.raises(ValidationError, match="would deal one twice"):
        type(app_config.daily).model_validate(payload)


def test_a_ring_repeating_a_game_is_refused_by_the_contract(
    app_config: AppConfig,
) -> None:
    payload = app_config.daily.model_dump()
    payload["games"] = [payload["games"][0], *payload["games"]]
    with pytest.raises(ValidationError, match="repeated Game"):
        type(app_config.daily).model_validate(payload)


def test_a_ring_naming_an_unregistered_game_is_an_error(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    # A gameId no row has shipped. It used to be "word-ladder", which stopped
    # being a stand-in for "unregistered" the moment Row 16 registered it -
    # this sentinel is deliberately not a Game anyone plans to build.
    unregistered = "acrostic"
    assert unregistered not in daily.BUILDERS
    broken = app_config.model_copy(
        update={
            "daily": app_config.daily.model_copy(
                update={"playlistLength": 1, "games": [unregistered]}
            )
        }
    )
    with pytest.raises(ValueError, match="no generator"):
        daily.build_day(FIRST_DAY, broken, generator, wordlists, used=())


# --------------------------------------------------------------------------
# 4a. The Daily's two rings: which Games reach a player, and in what order
# --------------------------------------------------------------------------


def test_every_registered_game_reaches_a_player(
    app_config: AppConfig, generator: DailyGenerator
) -> None:
    """A Game that ships, registers a builder and is never dealt is dark.

    Asserted as an EQUALITY rather than a subset in both directions of one
    claim: a Game missing from the ring never reaches a Daily player, and a ring
    naming a Game with no generator fails the bake, so the two lists have to be
    the same list.
    """
    assert set(app_config.daily.games) == {spec.gameId for spec in generator.games}
    assert set(app_config.daily.themedGames) <= set(app_config.daily.games)


def test_the_window_walks_the_ring_and_covers_every_game(
    app_config: AppConfig,
) -> None:
    """The variety rule: three different Games a day, and a different three daily."""
    ring = app_config.daily.games
    length = app_config.daily.playlistLength
    start = date.fromisoformat(FIRST_DAY)
    met: set[str] = set()
    previous: list[str] | None = None
    for offset in range(len(ring) * 2):
        day = (start + timedelta(days=offset)).isoformat()
        window = daily.playlist_games(ring, length, day)
        assert len(window) == length
        assert len(set(window)) == length, f"{day} deals a Game twice"
        assert set(window) <= set(ring)
        if previous is not None:
            assert set(window) != set(previous), f"{day} repeats the day before"
        previous = window
        met.update(window)
    assert met == set(ring), "a registered Game never came round"


def test_the_window_is_a_pure_function_of_its_date(app_config: AppConfig) -> None:
    ring = app_config.daily.games
    length = app_config.daily.playlistLength
    assert daily.playlist_games(ring, length, FIRST_DAY) == daily.playlist_games(
        ring, length, FIRST_DAY
    )


def test_a_ring_shorter_than_the_playlist_wraps_rather_than_shipping_short(
    app_config: AppConfig,
) -> None:
    """What lets a themed day be honest about holding fewer Games than slots."""
    window = daily.playlist_games(["anagram"], app_config.daily.playlistLength, THEME_DAY)
    assert window == ["anagram"] * app_config.daily.playlistLength


def test_a_day_opens_on_the_lightest_board_and_ends_on_the_heaviest(
    app_config: AppConfig, generator: DailyGenerator
) -> None:
    """THE ordering rule, over every window the ring can produce.

    Two claims in one schedule, because a mixed day has two difficulty dials:
    the Games rise by ``dailyRank`` down the playlist, so the heaviest board is
    never the first thing a player meets, and each slot is dealt the band at its
    own position, so the day still opens on the easiest band it has.
    """
    specs = {spec.gameId: spec for spec in generator.games}
    start = date.fromisoformat(FIRST_DAY)
    for offset in range(len(app_config.daily.games) * 2):
        day = (start + timedelta(days=offset)).isoformat()
        slots = daily.day_slots(
            app_config.daily.games, app_config.daily.playlistLength, day, specs
        )
        ranks = [specs[slot.gameId].dailyRank for slot in slots]
        assert ranks == sorted(ranks), f"{day}: {ranks}"
        heaviest = max(specs[slot.gameId].dailyRank for slot in slots)
        assert specs[slots[0].gameId].dailyRank < heaviest or len(set(ranks)) == 1
        for position, slot in enumerate(slots):
            assert slot.position == position
            bands = [band.id for band in specs[slot.gameId].difficulties]
            assert slot.difficulty == bands[position % len(bands)]


def test_every_committed_mixed_day_is_a_curve_of_different_games(
    bank_dir: Path, generator: DailyGenerator
) -> None:
    """The rules, read back off the bank the player actually downloads.

    Scoped to the days baked from the two rings: everything before them is three
    anagrams and is published history.
    """
    specs = {spec.gameId: spec for spec in generator.games}
    checked = 0
    for path in _committed_days(bank_dir):
        if path.stem < MIX_DAY:
            continue
        checked += 1
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        ranks = [specs[item.gameId].dailyRank for item in puzzle_file.items]
        assert ranks == sorted(ranks), f"{path.stem}: {ranks}"
        for position, item in enumerate(puzzle_file.items):
            bands = [band.id for band in specs[item.gameId].difficulties]
            assert item.difficulty == bands[position % len(bands)], path.stem
        if puzzle_file.theme is None:
            games = [item.gameId for item in puzzle_file.items]
            assert len(set(games)) == len(games), f"{path.stem} repeats a Game"
    assert checked, "no day was baked from the two rings"


def test_the_committed_bank_serves_every_registered_game(
    bank_dir: Path, generator: DailyGenerator
) -> None:
    """The measurement that started this row, asserted so it cannot regress.

    Four finished Games shipped dark because the Daily dealt three anagrams
    every day. The claim is not that any ONE day holds all five - a day is three
    slots - but that the bank a player downloads reaches every one of them.
    """
    served: set[str] = set()
    for path in _committed_days(bank_dir):
        if path.stem < MIX_DAY:
            continue
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        served.update(item.gameId for item in puzzle_file.items)
    assert served == {spec.gameId for spec in generator.games}


def test_widening_the_themed_ring_costs_a_themed_day_and_never_a_bake(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """THE tension this row exists to resolve, pinned from the failing side.

    A theme's set is a few hundred rows. Register it for a Game whose board
    cannot be built from that many - measured, the crossword solver fills four
    of themed-nature's 28 easy rows and NONE of its 14 medium ones - and the
    honest outcome is an ordinary day of the configured length, not a themed day
    padded out with an off-theme word and not a bake that dies on the date.
    """
    crossword_spec = next(
        spec for spec in generator.games if spec.gameId == "crossword"
    )
    registered = generator.model_copy(
        update={
            "games": [
                spec.model_copy(
                    update={
                        "themes": [
                            ThemedSet(wordlist=THEMED_SET, copySlug="theme-nature")
                        ]
                    }
                )
                if spec.gameId == crossword_spec.gameId
                else spec
                for spec in generator.games
            ]
        }
    )
    widened = app_config.model_copy(
        update={"daily": app_config.daily.model_copy(update={"themedGames": ["crossword"]})}
    )

    assert daily.is_theme_date(THEME_DAY, registered)
    puzzle = daily.build_day(THEME_DAY, widened, registered, wordlists, used=())
    assert puzzle.theme is None
    assert len(puzzle.items) == app_config.daily.playlistLength
    # And it falls back to the ORDINARY ring, so the day the theme declined is a
    # whole ordinary day rather than a themed shape with the theme taken out.
    assert {item.gameId for item in puzzle.items} <= set(app_config.daily.games)


def test_the_committed_themed_ring_still_runs_a_themed_day(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """The other half of the resolution: widening the ordinary ring did not
    turn themed days off, because the themed ring is its own list.
    """
    puzzle = daily.build_day(THEME_DAY, app_config, generator, wordlists, used=())
    assert puzzle.theme == "theme-nature"
    assert {item.gameId for item in puzzle.items} <= set(app_config.daily.themedGames)
    assert len({item.gameId for item in puzzle.items}) > 1, (
        "a themed day fell back to a single Game"
    )


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
    bands = [band.id for band in spec.difficulties]
    candidates = wordlists[ANAGRAM_SET].words
    plain = daily.pick_words(candidates, spec, FIRST_DAY, bands, used=())
    assert len(plain) == 3
    avoided = daily.pick_words(
        candidates, spec, FIRST_DAY, bands, used={row.word for row, _ in plain}
    )
    assert {row.word for row, _ in avoided}.isdisjoint({row.word for row, _ in plain})


def test_a_day_is_dealt_round_robin_across_the_difficulty_bands(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """A day is a curve, not three rolls of the same dice."""
    spec = generator.games[0]
    bands = [band.id for band in spec.difficulties]
    picked = daily.pick_words(wordlists[ANAGRAM_SET].words, spec, FIRST_DAY, bands, used=())
    assert [difficulty for _, difficulty in picked] == bands
    for row, difficulty in picked:
        assert daily.difficulty_of(row, spec) == difficulty


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
        candidates,
        spec,
        FIRST_DAY,
        [band.id for band in spec.difficulties],
        used={row.word for row in candidates},
    )
    assert len(filled) == 3


def test_selection_with_no_candidates_is_an_error(generator: DailyGenerator) -> None:
    with pytest.raises(ValueError, match="no candidate words"):
        daily.pick_words([], generator.games[0], FIRST_DAY, ["easy"], used=())


def test_a_band_with_an_empty_bucket_is_an_error(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """A day short of a band must fail loudly, never silently pick from another."""
    spec = generator.games[0]
    only_hard = [
        row
        for row in wordlists[ANAGRAM_SET].words
        if daily.difficulty_of(row, spec) == "hard"
    ]
    with pytest.raises(ValueError, match="easy"):
        daily.pick_words(
            only_hard, spec, FIRST_DAY, [band.id for band in spec.difficulties], used=()
        )


def test_the_engine_reads_only_the_derived_layer() -> None:
    """The lexicon and the daily puzzle are different layers (user directive)."""
    forbidden = ("yen_tamizh_backend.wordsmith",)
    # Derived from disk, never pinned: a module a later Game adds is covered by
    # this Oracle without anyone remembering to list it.
    package = _REPO_ROOT / "backend" / "yen_tamizh_backend" / "generate"
    modules = sorted(package.glob("*.py"))
    assert len(modules) >= 4, f"only {len(modules)} modules - has the package moved?"
    for module in modules:
        body = "\n".join(
            line
            for line in module.read_text(encoding="utf-8").splitlines()
            if line.startswith(("import", "from"))
        )
        for name in forbidden:
            assert name not in body, f"{module.name} imports {name}"


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
    served = {
        word for item in puzzle.items for word in daily.answer_words(item.payload)
    }
    assert served <= themed
    assert len(puzzle.items) == app_config.daily.playlistLength
    specs = {spec.gameId: spec for spec in generator.games}
    slots = daily.day_slots(
        app_config.daily.themedGames, app_config.daily.playlistLength, THEME_DAY, specs
    )
    assert [item.gameId for item in puzzle.items] == [slot.gameId for slot in slots]
    assert [item.difficulty for item in puzzle.items] == [
        slot.difficulty for slot in slots
    ]


def test_a_themed_day_draws_from_the_themed_ring_not_the_ordinary_one(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """The two rings are the whole resolution: a themed day is its own shape.

    Every Game on a themed day must be one the theme can honestly fill, so the
    themed window is drawn from ``daily.themedGames`` - and a Game the ordinary
    ring would have dealt that date is simply not on the board.
    """
    puzzle = daily.build_day(THEME_DAY, app_config, generator, wordlists, used=())
    assert puzzle.theme is not None
    assert {item.gameId for item in puzzle.items} <= set(app_config.daily.themedGames)


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
    served = {
        word for item in puzzle.items for word in daily.answer_words(item.payload)
    }
    assert served.isdisjoint(themed)


def test_a_theme_one_word_short_fills_none_of_the_day(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """A theme is all-or-nothing: it never contributes a partial playlist."""
    spec = generator.games[0]
    bands = [band.id for band in spec.difficulties]
    rows = wordlists[THEMED_SET].words
    full = daily.theme_can_fill(rows, spec, THEME_DAY, bands, used=())
    assert full is not None
    assert len({row.word for row, _ in full}) == 3

    almost = {row.word for row in rows} - {full[0][0].word}
    assert daily.theme_can_fill(rows, spec, THEME_DAY, bands, used=almost) is None


def test_a_theme_with_an_empty_difficulty_bucket_declines_instead_of_raising(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """An ordinary day short of a band is an error; a theme has somewhere to go."""
    spec = generator.games[0]
    bands = [band.id for band in spec.difficulties]
    hard_only = [
        row
        for row in wordlists[THEMED_SET].words
        if daily.difficulty_of(row, spec) == "hard"
    ]
    assert hard_only

    assert daily.theme_can_fill(hard_only, spec, THEME_DAY, bands, used=()) is None
    with pytest.raises(ValueError, match="easy"):
        daily.pick_words(hard_only, spec, THEME_DAY, bands, used=())


def test_a_theme_whose_rows_this_game_cannot_build_declines_the_day(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """Buildability is part of "can this theme fill the day", not a bake surprise.

    A theme's set is a few hundred rows, which is thin enough that an interlocked
    board can refuse every one of them - measured, the crossword solver fills
    four of themed-nature's 28 easy rows and none of its medium or hard ones. If
    the question were asked after the theme had been chosen, that date would
    raise mid-bake instead of quietly being an ordinary day.
    """
    spec = generator.games[0]
    bands = [band.id for band in spec.difficulties]
    rows = wordlists[THEMED_SET].words
    assert daily.theme_can_fill(rows, spec, THEME_DAY, bands, used=()) is not None
    refuse_all: Callable[[GameWord, str], bool] = lambda row, band: False
    assert (
        daily.theme_can_fill(rows, spec, THEME_DAY, bands, used=(), buildable=refuse_all)
        is None
    )


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
            for word in daily.answer_words(item.payload):
                assert word in allowed, path.stem


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
    """A meaning at position 1 is the whole answer sold before anything cheaper.

    Unless nothing cheaper exists. Two of the five ladders are two rungs -
    category then meaning - because the boards that print the answer's other
    ezhuthu cannot honestly sell a first-ezhuthu rung, so a word carrying no
    category leaves the meaning ALONE on that ladder. A rung that is the only
    rung was not sold ahead of anything.
    """
    for path in _ladder_days(bank_dir):
        for hints in _baked_hints(path):
            if not hints or hints[0]["kind"] != "meaning":
                continue
            assert len(hints) == 1, f"{path.stem}: {[h['kind'] for h in hints]}"


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
    """English is banned on a paid rung: the rung is omitted instead.

    The no-Latin half is asserted over EVERY baked rung. The gloss half needs
    the served row, and a baked day is history rather than a derivation of the
    current wordlist (row 1's re-bake guard), so a word a later deny-list took
    off the board is no longer there to compare against. Those items keep the
    cheap check and skip the lookup, and both counters must be non-zero so an
    emptied loop cannot pass as a green test.
    """
    served = {row.word: row for row in wordlists[ANAGRAM_SET].words}
    served.update({row.word: row for row in wordlists[THEMED_SET].words})
    checked = 0
    compared = 0
    for path in _ladder_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            row = served.get(str(item.payload.get("word", "")))
            for hint in item.payload.get("hints", []):
                text = str(hint["text"])
                if row is not None:
                    assert row.translationEn is None or row.translationEn not in text
                    compared += 1
                assert not any("a" <= char.lower() <= "z" for char in text)
                checked += 1
    assert checked
    assert compared


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
    assert hint_ladder.sellable_meaning(stripped) is None
    assert hint_ladder.display_meaning(stripped) is None
    kinds = [hint.kind for hint in anagram.build_hints(stripped, spec, 99)]
    assert "meaning" not in kinds


def test_a_baked_hint_never_spells_the_answer_out(
    bank_dir: Path, wordlists: dict[str, GameWordlist]
) -> None:
    """A gloss occasionally contains its own headword; a paid rung may not."""
    for path in _ladder_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            for hint in item.payload.get("hints", []):
                for word in daily.answer_words(item.payload):
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
            assert hint_ladder.category_tag(row, spec) is not None
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
    """requireMeaning is what makes the summary line unconditional.

    Read per ANSWER rather than per item, because the two boards that ask for
    several words carry the text on each answer: a search target states its
    meaning, and a crossword entry states it as the clue it is asked behind,
    which is the same fact in the shape that board reads it.
    """
    for path in _ladder_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            payload = item.payload
            if "word" in payload:
                assert payload.get("meaning"), f"{path.stem}: {payload['word']}"
            for target in payload.get("targets", []):
                assert target.get("meaning"), f"{path.stem}: {target['word']}"
            for entry in payload.get("entries", []):
                assert entry.get("clue"), f"{path.stem}: {entry['word']}"


def test_the_summary_meaning_is_the_one_the_rung_sold(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    """A player who bought the rung must not meet a second, different gloss."""
    spec = generator.games[0]
    agreed = disagreed = 0
    for row in wordlists[ANAGRAM_SET].words:
        sellable = hint_ladder.sellable_meaning(row)
        if sellable is None:
            # Nothing was sold, so the summary is free to show what it has.
            assert hint_ladder.display_meaning(row) is not None
            disagreed += 1
            continue
        assert hint_ladder.display_meaning(row) == sellable
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
    ordinary one - naming a word the day never serves would be a second lie.

    This proves nothing INVALID ships, which is all a committed bank can prove:
    whether any day offers a partner AT ALL is a draw, so that guarantee is
    pinned by the deterministic test below instead.
    """
    by_slug = {
        theme.copySlug: theme.wordlist
        for spec in generator.games
        for theme in spec.themes
    }
    for path in _ladder_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        source = (
            ANAGRAM_SET if puzzle_file.theme is None else by_slug[puzzle_file.theme]
        )
        served = {row.word for row in wordlists[source].words}
        for item in puzzle_file.items:
            if item.gameId != "anagram":
                continue
            word = str(item.payload["word"])
            for partner in item.payload.get("alsoValid", []):
                assert partner in served, f"{path.stem}: {partner}"
                assert partner != word
                assert sorted(segment(partner)) == sorted(segment(word))


def _a_set_holding_one_anagram_pair(
    wordlist: GameWordlist,
) -> tuple[GameWordlist, GameWord, GameWord, GameWord]:
    """A three-row served set, two of whose rows are a REAL anagram pair.

    Every row here is a real committed row and the set is a real validated
    ``GameWordlist`` (Holy Law #7); only ``frequency`` is restated, so that the
    quartiles this set is scored against - and with them which difficulty band
    each row lands in - are pinned instead of inherited from a 32,238-row
    population. One row per band is what lets the day deal all three slots.

    Returned as ``(set, easy filler, pair, pair)``, frequency descending.
    """
    rows = {row.word: row for row in wordlist.words}
    pair = next(
        words
        for key, words in sorted(daily.alternatives_of(wordlist).items())
        if len(words) == 2 and len(key) == 5
    )
    # 3 ezhuthu reaches the easy band, 5 the hard one; the pair's second member
    # is a stratum below its first, so only the harder band can claim it.
    filler = next(row for row in wordlist.words if len(row.ezhuthu) == 3)
    ranked = [(filler, 3, 1), (rows[pair[0]], 2, 2), (rows[pair[1]], 1, 2)]
    words = [
        GameWord.model_validate(
            row.model_dump()
            | {
                "frequency": frequency,
                "frequencyStratum": stratum,
                "anagramFanOut": fan_out,
            }
        )
        for stratum, (row, frequency, fan_out) in enumerate(ranked, start=1)
    ]
    counters = {bucket: 0 for bucket in wordlist.counters.model_dump()} | {
        "lexiconRows": len(words),
        "rowsKept": len(words),
    }
    served = GameWordlist.model_validate(
        wordlist.model_dump(mode="json")
        | {
            "words": [row.model_dump(mode="json") for row in words],
            "counters": counters,
            "source": wordlist.source.model_dump(mode="json") | {"rows": len(words)},
        }
    )
    return served, words[0], words[1], words[2]


def test_a_day_drawn_from_a_set_holding_an_anagram_pair_offers_the_partner(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """A baked payload carries the other served word its own tiles spell.

    The committed bank cannot carry this guarantee, and extending it would not
    help: only 514 of the 32,238 served words have a partner at all (1.6%), so
    the ~54 answers an 18-day window holds are a lottery that usually comes up
    empty - a day that happens to offer one is luck, not proof. The draw is
    left alone (preferring words with partners would distort what a player is
    served) and the mechanism is proven here instead, on a set that is KNOWN to
    hold a pair.
    """
    served, filler, first, second = _a_set_holding_one_anagram_pair(
        wordlists[ANAGRAM_SET]
    )
    # Dealt through the THEMED ring, which is the one a whole day may draw from a
    # single Game: an ordinary day is refused a repeated Game by contract, and
    # the three-row set above is built to fill exactly three anagram slots.
    scrambles = app_config.model_copy(
        update={"daily": app_config.daily.model_copy(update={"themedGames": ["anagram"]})}
    )

    day = daily.build_day(
        THEME_DAY,
        scrambles,
        generator,
        wordlists | {THEMED_SET: served},
        used=(),
    )

    assert day.theme == "theme-nature"
    offered = {
        str(item.payload["word"]): item.payload.get("alsoValid") for item in day.items
    }
    assert offered == {
        filler.word: None,
        first.word: [second.word],
        second.word: [first.word],
    }


def test_a_puzzle_may_not_list_its_own_answer_as_an_alternative(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    spec = generator.games[0]
    row = wordlists[ANAGRAM_SET].words[0]
    with pytest.raises(ValidationError, match="repeats the answer"):
        anagram.build_puzzle(row, spec, "seed", 3, False, [row.word])


# --------------------------------------------------------------------------
# 8. missing-letters (row 18)
#
# The second Game, and the first test of the claim that adding one costs a
# registration rather than a rewrite. The generator's own decision - WHICH
# ezhuthu to hide - is what these cover, because it is the only place a mask
# that admits a second real word can be avoided.
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ml_spec(generator: DailyGenerator) -> GameGeneration:
    return next(
        spec for spec in generator.games if spec.gameId == missing_letters.GAME_ID
    )


@pytest.fixture(scope="module")
def ml_served(
    ml_spec: GameGeneration, wordlists: dict[str, GameWordlist]
) -> missing_letters.ServedByLength:
    return missing_letters.index_by_length(wordlists[ml_spec.wordlist], ml_spec)


@pytest.fixture(scope="module")
def ml_masks(
    ml_spec: GameGeneration, wordlists: dict[str, GameWordlist]
) -> tuple[list[GameWord], list[GameWord]]:
    """Split the served set by whether ANY one-blank mask has a single answer.

    Built with an independent mask INDEX rather than the generator's own
    difference-bitmask scan, so the two implementations cross-check each other -
    and once for the whole module, because the interesting rows are a couple of
    percent of the set and hunting them per test would scan it repeatedly.
    """
    index: Counter[tuple[str | None, ...]] = Counter()
    rows = wordlists[ml_spec.wordlist].words

    def key(ezhuthu: Sequence[str], hole: int) -> tuple[str | None, ...]:
        return tuple(None if i == hole else unit for i, unit in enumerate(ezhuthu))

    for row in rows:
        for hole in range(len(row.ezhuthu)):
            index[key(row.ezhuthu, hole)] += 1
    unique: list[GameWord] = []
    shared: list[GameWord] = []
    for row in rows:
        fewest = min(index[key(row.ezhuthu, hole)] for hole in range(len(row.ezhuthu)))
        (unique if fewest == 1 else shared).append(row)
    return unique, shared


def _ml_rows(
    ml_spec: GameGeneration, wordlists: dict[str, GameWordlist], limit: int
) -> list[GameWord]:
    """A fixed prefix of the served set - a real sample, not a synthetic one."""
    return list(wordlists[ml_spec.wordlist].words[:limit])


def test_every_blank_hides_exactly_one_whole_ezhuthu(
    ml_spec: GameGeneration,
    ml_served: missing_letters.ServedByLength,
    wordlists: dict[str, GameWordlist],
) -> None:
    """A hole is a cluster, never half of one - the invariant the Game rests on."""
    for row in _ml_rows(ml_spec, wordlists, 120):
        for blanks in (1, 2):
            if blanks >= len(row.ezhuthu):
                continue
            puzzle = missing_letters.build_puzzle(
                row, ml_spec, f"{FIRST_DAY}|{row.word}", 2, blanks, ml_served
            )
            units = segment(puzzle.word)
            assert len(units) == len(row.ezhuthu)
            assert puzzle.blanks == sorted(set(puzzle.blanks))
            assert len(puzzle.blanks) == blanks
            assert max(puzzle.blanks) < len(units)
            # The hidden units rejoin the shown ones into exactly the answer,
            # which is what "whole ezhuthu" means operationally.
            assert "".join(units) == row.word
            for index in puzzle.blanks:
                assert units[index] in puzzle.choices


def test_the_bank_can_fill_the_blanks_and_still_offers_a_choice(
    ml_spec: GameGeneration,
    ml_served: missing_letters.ServedByLength,
    wordlists: dict[str, GameWordlist],
) -> None:
    for row in _ml_rows(ml_spec, wordlists, 120):
        puzzle = missing_letters.build_puzzle(
            row, ml_spec, f"{FIRST_DAY}|{row.word}", 2, 1, ml_served
        )
        assert len(puzzle.choices) == ml_spec.choiceCount
        assert len(puzzle.choices) > len(puzzle.blanks)
        # Every decoy is an ezhuthu, not a fragment: a bank tile the player taps
        # has to be a unit the answer's own alphabet contains.
        for choice in puzzle.choices:
            assert segment(choice) == [choice]


def test_the_generator_prefers_a_mask_no_other_served_word_fits(
    ml_spec: GameGeneration,
    ml_served: missing_letters.ServedByLength,
    ml_masks: tuple[list[GameWord], list[GameWord]],
) -> None:
    """The row-18 ruling: ambiguity is designed AROUND, then recorded.

    Unlike the anagram - which is handed the tiles it must work with - this
    generator chooses which ezhuthu to hide, so it scores every candidate mask
    and takes one no other served word answers. What it may not do is REFUSE the
    word when no such mask exists: that is the co-anagram mistake, and the
    settled precedent is to record the alternatives instead
    (docs/architecture/contracts/schemas.md).
    """
    unique, shared = ml_masks
    # The served set really does hold confusable words, or the preference below
    # would prove nothing - and the overwhelming majority still have a way out.
    assert shared, "no ambiguous row in the served set"
    assert len(unique) / (len(unique) + len(shared)) > 0.9

    # Where a unique mask exists the generator finds it, every time.
    for row in unique[:200]:
        puzzle = missing_letters.build_puzzle(
            row, ml_spec, f"{FIRST_DAY}|{row.word}", 2, 1, ml_served
        )
        assert puzzle.alsoValid is None, f"{row.word} had a unique mask and missed it"

    # And where none exists the word is still dealt, carrying what it admits.
    dealt = 0
    for row in shared[:40]:
        puzzle = missing_letters.build_puzzle(
            row, ml_spec, f"{FIRST_DAY}|{row.word}", 2, 1, ml_served
        )
        assert len(segment(puzzle.word)) > len(puzzle.blanks)
        dealt += 1
    assert dealt > 0


def test_an_ambiguous_mask_records_the_words_it_admits(
    ml_spec: GameGeneration,
    ml_served: missing_letters.ServedByLength,
    ml_masks: tuple[list[GameWord], list[GameWord]],
) -> None:
    """A player who fills a real served word is told so, not told "wrong"."""
    _, shared = ml_masks
    recorded = 0
    for row in shared[:60]:
        puzzle = missing_letters.build_puzzle(
            row, ml_spec, f"{FIRST_DAY}|{row.word}", 2, 1, ml_served
        )
        if puzzle.alsoValid is None:
            # The mask admits another word the BANK cannot spell; recording it
            # would be a message that can never fire.
            continue
        recorded += 1
        units = segment(puzzle.word)
        hidden = set(puzzle.blanks)
        served_words = {word for word, _ in ml_served[len(units)]}
        for other in puzzle.alsoValid:
            parts = segment(other)
            assert other != puzzle.word
            assert len(parts) == len(units)
            # It fits the mask ...
            assert all(parts[i] == units[i] for i in range(len(units)) if i not in hidden)
            # ... it is a word this Game would really deal ...
            assert other in served_words
            # ... and the player can actually enter it, counting the bank with
            # multiplicity: two holes needing the same ezhuthu need two of it.
            assert not Counter(parts[i] for i in hidden) - Counter(puzzle.choices)
    assert recorded > 0, "no ambiguous mask in the sample - the check proved nothing"


def test_the_missing_letters_ladder_never_sells_the_first_ezhuthu(
    ml_spec: GameGeneration, wordlists: dict[str, GameWordlist]
) -> None:
    """The rung would be a fact already printed, or the answer itself."""
    assert "firstEzhuthu" not in missing_letters.HINT_FIELDS
    assert missing_letters.HINT_FIELDS < anagram.HINT_FIELDS
    broken = ml_spec.model_copy(
        update={
            "hints": [
                ml_spec.hints[0].model_copy(
                    update={"template": "{firstEzhuthu}", "kind": "first-ezhuthu"}
                )
            ]
        }
    )
    with pytest.raises(KeyError, match="firstEzhuthu"):
        missing_letters.build_hints(wordlists[ml_spec.wordlist].words[0], broken, 1)


def test_a_hint_never_spells_the_answer_out(
    ml_spec: GameGeneration, wordlists: dict[str, GameWordlist]
) -> None:
    checked = 0
    for row in wordlists[ml_spec.wordlist].words[:2000]:
        for hint in missing_letters.build_hints(row, ml_spec, 99):
            assert row.word not in hint.text
            checked += 1
    assert checked > 0


def test_the_mask_and_the_bank_are_a_pure_function_of_the_seed(
    ml_spec: GameGeneration,
    ml_served: missing_letters.ServedByLength,
    wordlists: dict[str, GameWordlist],
) -> None:
    """Two runs of the same date must bake the same bytes, forever."""
    rows = _ml_rows(ml_spec, wordlists, 60)

    def bake(seed_day: str) -> list[dict[str, Any]]:
        return [
            missing_letters.build_puzzle(
                row, ml_spec, f"{seed_day}|{row.word}", 2, 1, ml_served
            ).model_dump(mode="json")
            for row in rows
        ]

    assert bake(FIRST_DAY) == bake(FIRST_DAY)
    # A different seed really does move the board, or "deterministic" would just
    # mean "constant".
    assert bake(ORDINARY_DAY) != bake(FIRST_DAY)


def test_the_blank_count_comes_from_the_band(ml_spec: GameGeneration) -> None:
    bands = {band.id: band for band in ml_spec.difficulties}
    assert bands["hard"].blanks == 2
    assert bands["easy"].blanks == 1
    # A band may never hide every ezhuthu of its own shortest word.
    for band in ml_spec.difficulties:
        assert band.blanks < band.minLength



def test_a_day_can_be_dealt_from_more_than_one_game(
    tmp_path: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """The registry claim: a Game costs a registration, not a day-loop edit.

    A five-slot day is not a shape the shipped config takes - three is what a
    Daily is - so this proves the wiring against a playlist long enough to hold
    every registered Game at once, which is the only way to assert all five
    payload shapes travel through one unchanged puzzle-file.
    """
    mixed = app_config.model_copy(
        update={
            "daily": app_config.daily.model_copy(
                update={
                    "playlistLength": 5,
                    "games": [
                        "anagram",
                        "crossword",
                        "missing-letters",
                        "word-search",
                        "wordle",
                    ],
                }
            )
        }
    )
    spec = generator.model_copy(
        update={"bankDir": tmp_path.name, "daysAhead": 1, "themeEveryNDays": 0}
    )
    run = generate(
        date.fromisoformat(ORDINARY_DAY), tmp_path.parent, mixed, spec, wordlists
    )
    assert len(run.written) == 2
    for day in run.written:
        games = [item.gameId for item in day.puzzle_file.items]
        assert sorted(games) == [
            "anagram",
            "crossword",
            "missing-letters",
            "word-search",
            "wordle",
        ]
        item = next(i for i in day.puzzle_file.items if i.gameId == "missing-letters")
        # The payload validates against ITS OWN schema, not the anagram's.
        MissingLettersPuzzle.model_validate(
            {"version": "2026-08-19", "changelog": [_STAMP], **item.payload}
        )
        assert "tiles" not in item.payload
        guessed = next(i for i in day.puzzle_file.items if i.gameId == "wordle")
        WordlePuzzle.model_validate(
            {"version": "2026-08-19", "changelog": [_STAMP], **guessed.payload}
        )
        traced = next(i for i in day.puzzle_file.items if i.gameId == "word-search")
        WordSearchPuzzle.model_validate(
            {"version": "2026-08-19", "changelog": [_STAMP], **traced.payload}
        )
        crossed = next(i for i in day.puzzle_file.items if i.gameId == "crossword")
        CrosswordPuzzle.model_validate(
            {"version": "2026-08-19", "changelog": [_STAMP], **crossed.payload}
        )
        # Five Games, five payload shapes, one unchanged puzzle-file.
        assert "tiles" not in guessed.payload
        assert "blanks" not in guessed.payload
        assert "choices" not in guessed.payload
        assert "word" not in traced.payload
        assert "attempts" not in traced.payload
        assert "grid" not in crossed.payload
        assert "word" not in crossed.payload
        # A day's own record of what it served has to see every word, or the
        # anti-repeat ledger deals a search board's words again next week.
        assert set(day.words) >= {
            target["word"] for target in traced.payload["targets"]
        }
        # The same claim for the board whose answers all arrived together.
        assert set(day.words) >= {
            entry["word"] for entry in crossed.payload["entries"]
        }


def test_an_unregistered_game_fails_loudly(generator: DailyGenerator) -> None:
    """A ring naming a Game with no builder must not bake a silently empty day."""
    with pytest.raises(ValueError, match="no registered puzzle builder"):
        daily.builder_for("acrostic")
    # Every registered generator has a builder, and every builder has a
    # generator: a spare entry on either side is a Game half added.
    assert set(daily.BUILDERS) == {spec.gameId for spec in generator.games}


def test_the_committed_missing_letters_set_is_servable(
    ml_spec: GameGeneration, wordlists: dict[str, GameWordlist]
) -> None:
    """The length floor is the mechanic's, and the bands can all be filled."""
    rows = wordlists[ml_spec.wordlist].words
    assert min(len(row.ezhuthu) for row in rows) >= 4
    buckets = daily.bucket_candidates(rows, ml_spec)
    for band in ml_spec.difficulties:
        assert buckets[band.id], f"the {band.id} bucket is empty"
        for row in buckets[band.id]:
            assert band.blanks < len(row.ezhuthu)


# --------------------------------------------------------------------------
# 9. wordle (Row 19)
#
# The third Game, and the THINNEST builder in the engine: a wordle's puzzle is
# the word, so there is no scramble, no mask and no bank to arrange. What these
# cover is therefore what the payload cannot be allowed to be - a board wider
# than its answer, an answer nobody can type, or a set holding two widths.
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def wd_spec(generator: DailyGenerator) -> GameGeneration:
    return next(spec for spec in generator.games if spec.gameId == wordle.GAME_ID)


def test_every_served_answer_can_be_typed_on_the_composer(
    wd_spec: GameGeneration, wordlists: dict[str, GameWordlist]
) -> None:
    """The unwinnable-puzzle guard, over the WHOLE served set rather than a sample.

    The keyboard produces exactly the 247 ezhuthu. An answer holding a grantha
    letter, a digit or a Latin character would validate everywhere else and
    arrive as a player running out of attempts, so the contract refuses it - and
    this asserts the property the contract is protecting really does hold for
    every row the Game can ever be dealt. Its frontend twin makes the same claim
    from the keyboard's side, which is what keeps the two inventories honest.
    """
    typeable = set(EZHUTHU_INVENTORY)
    assert len(typeable) == 247
    outside: set[str] = set()
    for row in wordlists[wd_spec.wordlist].words:
        outside.update(unit for unit in segment(row.word) if unit not in typeable)
    assert not outside, f"{len(outside)} served ezhuthu cannot be composed: {sorted(outside)}"


def test_the_board_width_is_derived_and_never_shipped(
    wd_spec: GameGeneration, wordlists: dict[str, GameWordlist]
) -> None:
    """`len(segment(word))` is the width; a stored one would be a drift surface."""
    for row in wordlists[wd_spec.wordlist].words[:200]:
        puzzle = wordle.build_puzzle(row, wd_spec, f"{FIRST_DAY}|{row.word}", 2)
        payload = puzzle.model_dump(mode="json", exclude_none=True)
        for absent in ("length", "ezhuthu", "tiles", "alphabet", "accept", "timeLimitSec"):
            assert absent not in payload, f"{absent} has no reader and must not travel"
        assert len(segment(puzzle.word)) == 6


def test_a_one_ezhuthu_answer_is_refused() -> None:
    """A board with one cell has no position anything can be in the wrong place."""
    with pytest.raises(ValidationError, match="at least two positions"):
        WordlePuzzle(
            version="2026-08-19",
            changelog=[_STAMP],
            word="\u0b95",
            attempts=6,
        )


def test_an_answer_the_composer_cannot_produce_is_refused() -> None:
    """Grantha is not among the 247, so a word needing one is unwinnable."""
    with pytest.raises(ValidationError, match="composer cannot produce"):
        WordlePuzzle(
            version="2026-08-19",
            changelog=[_STAMP],
            # ja + ka: the first base is grantha, borrowed for Sanskrit sounds.
            word="\u0b9c\u0b95",
            attempts=6,
        )


def test_a_single_attempt_board_is_refused() -> None:
    """Marks on the last row can never be acted on, so one row is not a game."""
    with pytest.raises(ValidationError, match="greater than or equal to 2"):
        WordlePuzzle(
            version="2026-08-19",
            changelog=[_STAMP],
            word="\u0b95\u0bcb\u0baf\u0bbf",
            attempts=1,
        )


def test_the_wordle_ladder_never_sells_the_first_ezhuthu(
    wd_spec: GameGeneration, wordlists: dict[str, GameWordlist]
) -> None:
    """The player can buy that fact with a guess, and a guess answers five more.

    The missing-letters board refuses the rung because the ezhuthu is already
    printed; here it is refused because the move it competes with is strictly
    better. Same closed vocabulary, opposite reason.
    """
    assert "firstEzhuthu" not in wordle.HINT_FIELDS
    assert wordle.HINT_FIELDS < anagram.HINT_FIELDS
    assert [hint.kind for hint in wd_spec.hints] == ["category", "meaning"]
    broken = wd_spec.model_copy(
        update={
            "hints": [
                wd_spec.hints[0].model_copy(
                    update={"template": "{firstEzhuthu}", "kind": "first-ezhuthu"}
                )
            ]
        }
    )
    with pytest.raises(KeyError, match="firstEzhuthu"):
        wordle.build_hints(wordlists[wd_spec.wordlist].words[0], broken, 1)


def test_the_payload_is_a_pure_function_of_its_inputs(
    wd_spec: GameGeneration, wordlists: dict[str, GameWordlist]
) -> None:
    """This builder makes no random choice, so the seed cannot move the bytes.

    That is a stronger statement than the other two Games can make and it is
    asserted rather than assumed: if a shuffle were ever added here, a day would
    stop being reproducible from its date alone.
    """
    rows = wordlists[wd_spec.wordlist].words[:60]

    def bake(seed_day: str) -> list[dict[str, Any]]:
        return [
            wordle.build_puzzle(row, wd_spec, f"{seed_day}|{row.word}", 2).model_dump(
                mode="json"
            )
            for row in rows
        ]

    assert bake(FIRST_DAY) == bake(FIRST_DAY) == bake(ORDINARY_DAY)


def test_the_committed_wordle_set_is_servable(
    wd_spec: GameGeneration, wordlists: dict[str, GameWordlist]
) -> None:
    """One width, every band filled, and enough words to keep going for years."""
    rows = wordlists[wd_spec.wordlist].words
    assert {len(row.ezhuthu) for row in rows} == {6}
    assert len(rows) > 5000
    buckets = daily.bucket_candidates(rows, wd_spec)
    for band in wd_spec.difficulties:
        assert buckets[band.id], f"the {band.id} bucket is empty"
    # Every band covers the one width, so what separates them is familiarity
    # alone - the honest shape once the length is pinned.
    for band in wd_spec.difficulties:
        assert band.minLength == band.maxLength == 6
    assert sorted(band.maxStratum for band in wd_spec.difficulties) == [1, 2, 4]


def test_the_attempt_budget_is_the_one_that_was_measured(
    wd_spec: GameGeneration, app_config: AppConfig
) -> None:
    """8 rows, and the ladder's ceiling matches the two rungs it can render.

    The number is a config knob and it is pinned here because it is the one
    that makes the board winnable: at seven guesses the simulated hard band is
    solved 71.5 percent of the time against 85.5 at eight, and a hard word is
    one slot of every three.
    """
    assert wd_spec.attempts == 8
    assert wd_spec.reveal == 0
    assert app_config.hints.perGame[wordle.GAME_ID] == len(wd_spec.hints) == 2


# --------------------------------------------------------------------------
# 10. word-search (Row 20)
#
# The fourth Game, and the first whose board holds more than one answer. Its
# central correctness property is one sentence long - every grid cell is exactly
# one ezhuthu - and everything below either checks that or checks the thing it
# makes possible: that each word the board asks for can really be traced out of
# the grid the player is looking at.
#
# The placement Oracle deliberately walks the grid with its OWN step table
# rather than calling the helper the generator and the contract share. An Oracle
# that reuses the implementation it is checking proves the implementation is
# self-consistent, which is not the claim.
# --------------------------------------------------------------------------

# The eight directions, written out here so the Oracle owes the implementation
# nothing. If these ever disagree with contracts.word_search_puzzle.STEPS, one of
# the two is wrong and the tests below say which.
_ORACLE_STEPS: dict[str, tuple[int, int]] = {
    "right": (0, 1),
    "down-right": (1, 1),
    "down": (1, 0),
    "down-left": (1, -1),
    "left": (0, -1),
    "up-left": (-1, -1),
    "up": (-1, 0),
    "up-right": (-1, 1),
}


def _trace(grid: list[list[str]], row: int, col: int, direction: str, length: int) -> str:
    """Read ``length`` cells out of the grid, or "" when the line leaves it."""
    step_row, step_col = _ORACLE_STEPS[direction]
    units: list[str] = []
    for step in range(length):
        y, x = row + step_row * step, col + step_col * step
        if not (0 <= y < len(grid) and 0 <= x < len(grid[y])):
            return ""
        units.append(grid[y][x])
    return "".join(units)


@pytest.fixture(scope="module")
def ws_spec(generator: DailyGenerator) -> GameGeneration:
    return next(spec for spec in generator.games if spec.gameId == word_search.GAME_ID)


@pytest.fixture(scope="module")
def ws_served(
    ws_spec: GameGeneration, wordlists: dict[str, GameWordlist]
) -> word_search.ServedIndex:
    return word_search.index_served(wordlists[ws_spec.wordlist], ws_spec)


def _boards(
    spec: GameGeneration, served: word_search.ServedIndex, count: int
) -> list[tuple[str, WordSearchPuzzle]]:
    """Generate ``count`` boards per band from real rows and real dates."""
    pools = {
        band.id: word_search.band_candidates(served, band) for band in spec.difficulties
    }
    out: list[tuple[str, WordSearchPuzzle]] = []
    for offset in range(count):
        day = date.fromisoformat(ORDINARY_DAY) + timedelta(days=offset)
        for band in spec.difficulties:
            rows = pools[band.id]
            anchor = rows[(offset * 37 + len(band.id)) % len(rows)]
            seed = f"{day.isoformat()}|{anchor.word}"
            out.append((seed, word_search.build_puzzle(anchor, spec, seed, 0, band, served)))
    return out


def test_every_grid_cell_is_exactly_one_ezhuthu(
    ws_spec: GameGeneration, ws_served: word_search.ServedIndex
) -> None:
    """The row's central property, over every cell of many generated boards.

    Two claims and they are not the same one. ``segment(cell) == [cell]`` says
    the cell holds ONE cluster, so no cell carries half of one and no cell
    carries two crammed together. Membership in the 247 says that cluster is a
    LETTER: a lone vowel sign - exactly what a generator walking code points
    leaves behind when it splits a cluster across two cells - survives
    segmentation as a single unit and would pass the first check while being
    unreadable and untraceable in a grid.
    """
    letters = set(EZHUTHU_INVENTORY)
    assert len(letters) == 247
    cells = 0
    for _, puzzle in _boards(ws_spec, ws_served, 10):
        for line in puzzle.grid:
            for cell in line:
                assert segment(cell) == [cell], f"{cell!r} is not one ezhuthu"
                assert cell in letters, f"{cell!r} is not a letter of Tamil"
                cells += 1
    assert cells == 10 * len(ws_spec.difficulties) * ws_spec.gridRows * ws_spec.gridCols


def test_every_target_is_recoverable_by_tracing_the_grid(
    ws_spec: GameGeneration, ws_served: word_search.ServedIndex
) -> None:
    """ORACLE (a) - the placement claim, read back out of the grid.

    For every target on every generated board, walking ``len(segment(word))``
    cells from its recorded start in its recorded direction must spell that word
    exactly. The walk uses this module's own step table and reads the grid the
    player is given, so nothing the generator believes about where it put a word
    is taken on trust - a board that recorded a start it did not use, or ran a
    word off the edge, or crossed two words onto a cell holding a third letter,
    fails here.
    """
    checked = 0
    for seed, puzzle in _boards(ws_spec, ws_served, 20):
        for target in puzzle.targets:
            units = segment(target.word)
            traced = _trace(
                puzzle.grid,
                target.start.row,
                target.start.col,
                target.direction,
                len(units),
            )
            assert traced == target.word, (
                f"{seed}: {target.word!r} is not at ({target.start.row}, "
                f"{target.start.col}) going {target.direction} - the grid spells "
                f"{traced!r}"
            )
            checked += 1
    assert checked == 20 * (4 + 5 + 6), "the bands did not deal the words they declare"


def test_every_direction_including_the_reversed_and_diagonal_ones_gets_used(
    ws_spec: GameGeneration, ws_served: word_search.ServedIndex
) -> None:
    """A generator that only ever ran left to right would pass every other test."""
    used = {target.direction for _, p in _boards(ws_spec, ws_served, 10) for target in p.targets}
    assert used == set(_ORACLE_STEPS), f"unused directions: {sorted(set(_ORACLE_STEPS) - used)}"


def test_a_board_is_a_pure_function_of_its_seed(
    ws_spec: GameGeneration, ws_served: word_search.ServedIndex
) -> None:
    """Two runs of one date bake the same bytes - the Row 13 Oracle, again.

    Every choice this builder makes is seeded: which companions join the anchor,
    which of the 512 starts each word takes, and which letter falls in which
    empty cell. ``random`` appears nowhere, so a bank baked on 3.14 and re-baked
    by CI on 3.12 cannot differ.
    """
    band = ws_spec.difficulties[-1]
    rows = word_search.band_candidates(ws_served, band)
    for anchor in rows[:8]:
        seed = f"{ORDINARY_DAY}|{anchor.word}"
        first = word_search.build_puzzle(anchor, ws_spec, seed, 0, band, ws_served)
        again = word_search.build_puzzle(anchor, ws_spec, seed, 0, band, ws_served)
        assert first.model_dump(mode="json") == again.model_dump(mode="json")
        # A different date must move the board, or the seed is being ignored.
        other = word_search.build_puzzle(
            anchor, ws_spec, f"{FIRST_DAY}|{anchor.word}", 0, band, ws_served
        )
        assert other.grid != first.grid


def test_the_filler_never_leaks_a_letter_no_target_uses(
    ws_spec: GameGeneration, ws_served: word_search.ServedIndex
) -> None:
    """The filler ruling, asserted rather than described.

    Empty cells are dealt from the multiset of the PLACED words' own ezhuthu, so
    every cell in the grid holds a letter some target really uses. The rejected
    alternative - sampling the whole served set's letter distribution - leaves
    30.7 percent of all cells holding a letter that appears in no target, and a
    player can strike those out on sight without searching for anything.
    """
    for seed, puzzle in _boards(ws_spec, ws_served, 10):
        wanted = {unit for target in puzzle.targets for unit in segment(target.word)}
        present = {cell for line in puzzle.grid for cell in line}
        assert present <= wanted, f"{seed}: {sorted(present - wanted)} appear in no target"


def test_an_unintended_word_is_recorded_and_traceable_never_a_target(
    ws_spec: GameGeneration, ws_served: word_search.ServedIndex
) -> None:
    """The accidental-word ruling: RECORD, do not require (schemas.md).

    Filling the cells the targets do not use makes unintended words, and the
    measurement is that half of all boards hold at least one - 50.4 percent over
    720 generated boards, a mean of 0.70 and a maximum of 5, rising with the
    word count from 41.2 percent on easy to 58.8 on hard. That is not a defect
    to design out: a player who traces a real Tamil word and is told "wrong"
    concludes the game cheated, while "that is a word, but not on today's list"
    teaches them one. What IS required is that every recorded word can actually
    be traced and is not already on the list.
    """
    boards = _boards(ws_spec, ws_served, 12)
    with_extra = 0
    for seed, puzzle in boards:
        asked = {target.word for target in puzzle.targets}
        for other in puzzle.alsoValid or ():
            assert other not in asked, f"{seed}: {other!r} is already on the list"
            assert other in ws_served.words, f"{seed}: {other!r} is not a served word"
            units = segment(other)
            places = [
                (row, col, direction)
                for row in range(len(puzzle.grid))
                for col in range(len(puzzle.grid[row]))
                for direction in _ORACLE_STEPS
                if _trace(puzzle.grid, row, col, direction, len(units)) == other
            ]
            assert places, f"{seed}: {other!r} cannot be traced anywhere"
        with_extra += 1 if puzzle.alsoValid else 0
    # The rate is a measured property of the design, not an accident: if it ever
    # went to zero the field would be dead weight, and if it went to every board
    # the list would stop being what the puzzle is about.
    assert 0 < with_extra < len(boards)


def test_the_payload_carries_nothing_it_can_derive_or_cannot_read(
    ws_spec: GameGeneration, ws_served: word_search.ServedIndex
) -> None:
    """Four fields refused, each for a reason Rows 18 and 19 already settled."""
    _, puzzle = _boards(ws_spec, ws_served, 1)[0]
    payload = puzzle.model_dump(mode="json", exclude_none=True)
    for absent in ("rows", "cols", "ezhuthu", "attempts", "hints", "translationEn", "word"):
        assert absent not in payload, f"{absent} has no reader and must not travel"
    assert len(puzzle.grid) == ws_spec.gridRows
    assert {len(line) for line in puzzle.grid} == {ws_spec.gridCols}


def test_the_word_search_ladder_refuses_every_rung(
    ws_spec: GameGeneration, ws_served: word_search.ServedIndex
) -> None:
    """An empty vocabulary, and it is a ruling rather than an oversight.

    This board PRINTS the words it is asking for, so category, first-ezhuthu and
    meaning are all facts already on the screen. The one thing a player lacks is
    a location, and a baked location rung has to name one particular word - so
    whether it is worth anything depends on whether that word is still unfound,
    and a rung that can be worthless by timing charges for nothing. Same test
    that deleted ``length`` and refused ``firstEzhuthu`` twice, applied to the
    whole ladder.
    """
    assert word_search.HINT_FIELDS == frozenset()
    assert ws_spec.hints == []
    row = ws_served.rows[0]
    broken = ws_spec.model_copy(
        update={"hints": [HintSpec(kind="meaning", template="{meaning}", cost=3)]}
    )
    with pytest.raises(KeyError, match="meaning"):
        word_search.build_hints(row, broken, 1)


def test_the_committed_word_search_set_and_bands_fit_the_board(
    ws_spec: GameGeneration, wordlists: dict[str, GameWordlist]
) -> None:
    """One width the phone allows, three bands that fill, and a floor that fits.

    Eight columns is a phone measurement: a 36px cell with a 4px gutter is 316px
    across eight, against the 328px a 360px screen leaves after its margins, and
    a ninth column is 356px. Placement was measured against that board - four,
    five, six and seven words placed on every one of 200 draws, eight words on
    88.5 percent - so six targets on the hardest band leaves a real margin.
    """
    rows = wordlists[ws_spec.wordlist].words
    assert ws_spec.gridRows == ws_spec.gridCols == 8
    assert min(len(row.ezhuthu) for row in rows) >= 4
    assert max(len(row.ezhuthu) for row in rows) <= min(ws_spec.gridRows, ws_spec.gridCols)
    buckets = daily.bucket_candidates(rows, ws_spec)
    for band in ws_spec.difficulties:
        assert buckets[band.id], f"the {band.id} bucket is empty"
        # Length is NOT the difficulty axis here: a longer word covers more
        # cells and is easier to spot, so all three bands span the same range
        # and separate on how many words are hidden and how familiar they are.
        assert (band.minLength, band.maxLength) == (4, 6)
    assert [band.targets for band in ws_spec.difficulties] == [4, 5, 6]
    assert [band.maxStratum for band in ws_spec.difficulties] == [1, 2, 4]
    # This Game sells nothing, so it needs no allowance - and the day loop reads
    # a missing entry as zero rather than raising.
    assert word_search.GAME_ID not in AppConfig.model_validate_json(
        _APP_CONFIG.read_text(encoding="utf-8")
    ).hints.perGame


def test_a_ragged_grid_is_refused() -> None:
    """A short row has no column for a vertical or diagonal trace to run down."""
    with pytest.raises(ValidationError, match="ragged grid"):
        WordSearchPuzzle(
            version="2026-08-19",
            changelog=[_STAMP],
            grid=[["\u0b95", "\u0bb5"], ["\u0b95"]],
            targets=[
                WordSearchTarget(
                    word="\u0b95\u0bb5",
                    start=GridPoint(row=0, col=0),
                    direction="right",
                )
            ],
        )


def test_a_cell_that_is_not_one_ezhuthu_is_refused() -> None:
    """The code-point bug, caught at the boundary rather than by a player.

    A lone vowel sign is what splitting a cluster across two cells leaves in the
    second of them. It survives segmentation as a single unit, so only the
    inventory check rejects it - which is exactly why the contract makes both
    claims instead of one.
    """
    with pytest.raises(ValidationError, match="not among the 247"):
        WordSearchPuzzle(
            version="2026-08-19",
            changelog=[_STAMP],
            grid=[["\u0b95", "\u0bbe"], ["\u0bb5", "\u0b95"]],
            targets=[
                WordSearchTarget(
                    word="\u0b95\u0bb5",
                    start=GridPoint(row=0, col=0),
                    direction="down",
                )
            ],
        )
    with pytest.raises(ValidationError, match="not single ezhuthu"):
        WordSearchPuzzle(
            version="2026-08-19",
            changelog=[_STAMP],
            grid=[["\u0b95\u0bbe\u0bb5", "\u0bb5"], ["\u0bb5", "\u0b95"]],
            targets=[
                WordSearchTarget(
                    word="\u0bb5\u0b95",
                    start=GridPoint(row=0, col=1),
                    direction="down",
                )
            ],
        )


def test_a_target_that_is_not_where_it_says_is_refused() -> None:
    """The contract states the placement Oracle itself, so a bug cannot ship.

    The grid deliberately repeats its first column, so reading DOWN from the
    corner spells something else rather than the same word again - a symmetric
    grid would accept the wrong placement and prove nothing.
    """
    grid = [["\u0b95", "\u0bb5"], ["\u0b95", "\u0bb5"]]
    with pytest.raises(ValidationError, match="spells"):
        WordSearchPuzzle(
            version="2026-08-19",
            changelog=[_STAMP],
            grid=grid,
            targets=[
                WordSearchTarget(
                    word="\u0b95\u0bb5",
                    start=GridPoint(row=0, col=0),
                    direction="down",
                )
            ],
        )
    with pytest.raises(ValidationError, match="runs off the grid"):
        WordSearchPuzzle(
            version="2026-08-19",
            changelog=[_STAMP],
            grid=grid,
            targets=[
                WordSearchTarget(
                    word="\u0b95\u0bb5",
                    start=GridPoint(row=1, col=1),
                    direction="right",
                )
            ],
        )


def test_an_alternative_that_is_not_in_the_grid_is_refused() -> None:
    """Row 18's lesson: an answer the input method cannot reach can never fire."""
    with pytest.raises(ValidationError, match="cannot be traced"):
        WordSearchPuzzle(
            version="2026-08-19",
            changelog=[_STAMP],
            grid=[["\u0b95", "\u0bb5"], ["\u0bb5", "\u0b95"]],
            targets=[
                WordSearchTarget(
                    word="\u0b95\u0bb5",
                    start=GridPoint(row=0, col=0),
                    direction="right",
                )
            ],
            alsoValid=["\u0ba4\u0bae\u0bbf\u0bb4\u0bcd"],
        )


def test_the_day_ledger_reads_every_payload_shape() -> None:
    """One definition of "the words this payload asked for", used by both readers.

    Three Games put one answer under ``word``, the search board puts several
    under ``targets`` and the crossword puts its own under ``entries``. The
    anti-repeat ledger and the bake's own record of what a day served must
    agree, or a board's words come back a week later because the ledger could
    not see them.
    """
    assert daily.answer_words({"word": "\u0b85"}) == ["\u0b85"]
    assert daily.answer_words(
        {"targets": [{"word": "\u0b85"}, {"word": "\u0b86"}]}
    ) == ["\u0b85", "\u0b86"]
    assert daily.answer_words(
        {"entries": [{"word": "\u0b85"}, {"word": "\u0b86"}]}
    ) == ["\u0b85", "\u0b86"]
    assert daily.answer_words({"choices": ["\u0b85"]}) == []


def test_a_band_that_cannot_fit_on_the_board_is_refused(
    ws_spec: GameGeneration,
) -> None:
    """A configuration that could never bake fails when it is read, not when it runs.

    It is a floor rather than a packing model - what the grid can really take was
    measured and lives in config - but a band asking for more cells than the grid
    has, or for a word longer than its longest line, is impossible by counting
    and should never reach the bake.
    """
    dumped = ws_spec.model_dump()
    greedy = dict(dumped)
    greedy["difficulties"] = [{**dumped["difficulties"][0], "targets": 20}]
    with pytest.raises(ValidationError, match="which needs"):
        GameGeneration.model_validate(greedy)
    # 24 cells of board for a band that needs 24 - and a longest line of five,
    # so a six-ezhuthu word fits nowhere. The two refusals are different
    # arithmetic, and this is the shape that reaches the second one.
    cramped = dict(dumped)
    cramped["difficulties"] = [dumped["difficulties"][0]]
    cramped["gridRows"] = cramped["gridCols"] = 5
    with pytest.raises(ValidationError, match="do not fit"):
        GameGeneration.model_validate(cramped)


# --------------------------------------------------------------------------
# 11. crossword (Row 21)
#
# The fifth Game, and the first whose answers are not independent of each other:
# an entry's letters are decided partly by every entry crossing it. Its central
# correctness property is therefore one sentence long - every crossing cell
# holds exactly one ezhuthu that satisfies BOTH the answer running across it and
# the answer running down it - and everything below either checks that or checks
# the thing it makes possible.
#
# THE SOLVER IS BUILD-TIME. Everything in this section runs the real placement
# search over the real committed served set, because the browser never runs it:
# the shipped payload is a finished board, and a bug in the fill has exactly one
# place left to be caught, which is here.
#
# As in the search board's section, the Oracle walks the grid with its OWN step
# table rather than calling the helper the generator and the contract share. An
# Oracle that reuses the implementation it is checking proves the implementation
# is self-consistent, which is not the claim.
# --------------------------------------------------------------------------

# The two directions, written out here so the Oracle owes the implementation
# nothing. If these ever disagree with contracts.crossword_puzzle.STEPS, one of
# the two is wrong and the tests below say which.
_CW_STEPS: dict[str, tuple[int, int]] = {"across": (0, 1), "down": (1, 0)}


def _cw_cells(entry: CrosswordEntry) -> list[tuple[int, int]]:
    """The cells one entry claims, walked from its own recorded start."""
    step_row, step_col = _CW_STEPS[entry.direction]
    return [
        (entry.start.row + step_row * index, entry.start.col + step_col * index)
        for index in range(len(segment(entry.word)))
    ]


def _cw_grid(puzzle: CrosswordPuzzle) -> dict[tuple[int, int], list[tuple[str, str]]]:
    """Every open cell, and what each entry through it claims that cell holds.

    Built as a LIST of claims rather than a resolved letter on purpose: the
    interlock Oracle's whole question is whether the claims agree, and a dict
    that kept only the last one would answer it by construction.
    """
    board: dict[tuple[int, int], list[tuple[str, str]]] = {}
    for entry in puzzle.entries:
        for cell, unit in zip(_cw_cells(entry), segment(entry.word)):
            board.setdefault(cell, []).append((unit, entry.word))
    return board


@pytest.fixture(scope="module")
def cw_spec(generator: DailyGenerator) -> GameGeneration:
    return next(spec for spec in generator.games if spec.gameId == crossword.GAME_ID)


@pytest.fixture(scope="module")
def cw_served(
    cw_spec: GameGeneration, wordlists: dict[str, GameWordlist]
) -> crossword.ServedIndex:
    return crossword.index_served(wordlists[cw_spec.wordlist], cw_spec)


def _crosswords(
    spec: GameGeneration, served: crossword.ServedIndex, count: int
) -> list[tuple[str, DifficultyBand, GameWord, CrosswordPuzzle]]:
    """Solve ``count`` boards per band from real rows, real bands and real dates.

    A row the search cannot cross is SKIPPED rather than failed, which is what
    the day loop does with it: ``Unbuildable`` is the builder's way of asking for
    the next candidate. How often that happens is measured by its own test
    below, so a silent collapse to a handful of boards cannot hide here.
    """
    pools = {
        band.id: crossword.band_pool(served, band).by_length
        for band in spec.difficulties
    }
    out: list[tuple[str, DifficultyBand, GameWord, CrosswordPuzzle]] = []
    for offset in range(count):
        day = (date.fromisoformat(ORDINARY_DAY) + timedelta(days=offset)).isoformat()
        for band in spec.difficulties:
            rows = [row for pool in pools[band.id].values() for row in pool]
            anchor = rows[(offset * 1319 + len(band.id) * 7919) % len(rows)]
            seed = f"{day}|{anchor.word}"
            try:
                built = crossword.build_puzzle(anchor, spec, seed, 0, band, served)
            except crossword.SolverExhausted:
                continue
            out.append((seed, band, anchor, built))
    return out


def test_every_crossing_cell_satisfies_both_of_its_answers(
    cw_spec: GameGeneration, cw_served: crossword.ServedIndex
) -> None:
    """ORACLE (a) - the interlock, over real solver output.

    For every board the real search produced, every cell two entries share must
    carry exactly ONE ezhuthu, and that ezhuthu has to be the one BOTH of them
    spell at that offset. The claims are collected per cell from each entry's
    own recorded start and direction, so a board that recorded a start it did
    not fill, or ran an answer off its own edge, or wrote two different letters
    into one square, fails here rather than in the renderer.

    A crossing is also checked to be one across and one down. Two entries
    running the same way through one cell would be a stacked pair, not a
    crossing, and the letter they agree on would prove nothing.
    """
    letters = set(EZHUTHU_INVENTORY)
    boards = _crosswords(cw_spec, cw_served, 40)
    assert len(boards) >= 100, f"only {len(boards)} boards solved - the Oracle is thin"
    crossings = cells = 0
    for seed, _, _, puzzle in boards:
        board = _cw_grid(puzzle)
        for cell, claims in board.items():
            units = {unit for unit, _ in claims}
            assert len(units) == 1, (
                f"{seed}: cell {cell} is claimed as {sorted(units)} by "
                f"{sorted(word for _, word in claims)}"
            )
            unit = claims[0][0]
            assert segment(unit) == [unit], f"{seed}: {unit!r} is not one ezhuthu"
            assert unit in letters, f"{seed}: {unit!r} is not a letter of Tamil"
            cells += 1
            if len(claims) > 1:
                assert len(claims) == 2, f"{seed}: cell {cell} carries {len(claims)}"
                ways = {
                    entry.direction
                    for entry in puzzle.entries
                    if cell in _cw_cells(entry)
                }
                assert ways == {"across", "down"}, (
                    f"{seed}: cell {cell} is shared by two {sorted(ways)} entries, "
                    f"which is a stack rather than a crossing"
                )
                crossings += 1
    # Every board is interlocked, not merely valid: an uncrossed board would
    # pass every per-cell claim above and be a word list on squared paper.
    assert crossings > 0
    assert cells > 0


def test_every_answer_is_recoverable_from_the_grid_it_helped_build(
    cw_spec: GameGeneration, cw_served: crossword.ServedIndex
) -> None:
    """ORACLE (b) - read each answer back OUT of the board the player sees.

    The grid is not shipped: it is the union of the entries. So the Oracle
    builds it from every entry at once and then reads each answer back out of
    the finished thing, which is the only reading that can catch an answer
    written correctly into cells another answer later overwrote.
    """
    checked = 0
    for seed, _, _, puzzle in _crosswords(cw_spec, cw_served, 40):
        board = _cw_grid(puzzle)
        for entry in puzzle.entries:
            spelled = "".join(board[cell][0][0] for cell in _cw_cells(entry))
            assert spelled == entry.word, (
                f"{seed}: reading from ({entry.start.row},{entry.start.col}) "
                f"{entry.direction} spells {spelled!r}, not {entry.word!r}"
            )
            checked += 1
    assert checked > 0


def test_every_board_fills_the_mask_its_band_configured(
    cw_spec: GameGeneration, cw_served: crossword.ServedIndex
) -> None:
    """The board is exactly the shape config asked for - no more, no fewer.

    The mask is the difficulty dial, so a solver that quietly dropped an entry
    it could not fill would be changing the difficulty rather than failing. The
    entries' cells are compared to the mask's own open cells as SETS, which
    catches both a missing entry and a cell filled that the mask blocked.
    """
    seen = set()
    for seed, band, _, puzzle in _crosswords(cw_spec, cw_served, 20):
        assert band.grid is not None
        assert (puzzle.rows, puzzle.cols) == (len(band.grid), len(band.grid[0]))
        wanted = mask_entries(band.grid)
        assert len(puzzle.entries) == len(wanted), (
            f"{seed}: {band.id} asks for {len(wanted)} entries, the board has "
            f"{len(puzzle.entries)}"
        )
        assert {frozenset(cells) for cells in wanted} == {
            frozenset(_cw_cells(entry)) for entry in puzzle.entries
        }, f"{seed}: the board's entries are not the mask's runs"
        seen.add(band.id)
    assert seen == {band.id for band in cw_spec.difficulties}


def test_the_word_the_day_picked_is_the_word_that_lands_on_the_board(
    cw_spec: GameGeneration, cw_served: crossword.ServedIndex
) -> None:
    """The anchor is placed, and every other answer is a served word too.

    The day loop chose the anchor against the whole bank's history and the
    difficulty curve; a solver free to drop it would throw that away. The rest
    of the board is drawn by the search itself, so it is checked against the
    served set rather than against the loop.
    """
    served = {
        row.word for pool in cw_served.by_length.values() for row in pool
    }
    for seed, band, anchor, puzzle in _crosswords(cw_spec, cw_served, 20):
        answers = [entry.word for entry in puzzle.entries]
        assert anchor.word in answers, f"{seed}: the anchor was not placed"
        assert len(set(answers)) == len(answers), f"{seed}: an answer repeats"
        for word in answers:
            assert word in served, f"{seed}: {word!r} is not in the served set"
            assert band.minLength <= len(segment(word)) <= band.maxLength


def test_a_crossword_is_a_pure_function_of_its_seed(
    cw_spec: GameGeneration, cw_served: crossword.ServedIndex
) -> None:
    """ORACLE (c) - determinism, asserted on the BYTES.

    Every choice this search makes - which entry it fills next, which candidate
    it tries first, which restart it is on - comes from the shared FNV-1a and
    mulberry32 pair, never from ``random``. So two solves of one seed have to
    serialise identically, or a bank baked locally on 3.14 and re-baked by CI on
    3.12 could differ.
    """
    band = cw_spec.difficulties[-1]
    pool = crossword.band_pool(cw_served, band)
    rows = [row for words in pool.by_length.values() for row in words]
    compared = moved = 0
    for index in range(0, 4000, 331):
        anchor = rows[index % len(rows)]
        seed = f"{ORDINARY_DAY}|{anchor.word}"
        try:
            first = crossword.build_puzzle(anchor, cw_spec, seed, 0, band, cw_served)
        except crossword.SolverExhausted:
            continue
        again = crossword.build_puzzle(anchor, cw_spec, seed, 0, band, cw_served)
        assert first.model_dump_json() == again.model_dump_json()
        compared += 1
        # A different date must be able to move the board, or the seed is
        # decoration. It is counted rather than asserted per row: on a mask this
        # tight one anchor really can have only one fill.
        other = crossword.build_puzzle(
            anchor, cw_spec, f"{FIRST_DAY}|{anchor.word}", 0, band, cw_served
        )
        if [e.word for e in other.entries] != [e.word for e in first.entries]:
            moved += 1
    assert compared >= 8, f"only {compared} boards compared"
    assert moved > 0, "no seed changed any board - the seed is being ignored"


def test_a_day_bakes_the_same_bytes_twice(
    tmp_path: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """The Row 13 Oracle, through the day loop, with the crossword in the ring.

    The solver is the only part of this repo that SEARCHES, and a search is
    where an accidental dependence on set or dict iteration order hides. So the
    determinism claim is made again one layer up: two full bakes of the same
    date into two empty banks must produce byte-identical files.
    """
    mixed = app_config.model_copy(
        update={
            "daily": app_config.daily.model_copy(
                update={"playlistLength": 2, "games": ["anagram", "crossword"]}
            )
        }
    )
    baked = []
    for run in ("a", "b"):
        root = tmp_path / run
        (root / "bank").mkdir(parents=True)
        spec = generator.model_copy(
            update={"bankDir": "bank", "daysAhead": 2, "themeEveryNDays": 0}
        )
        generate(date.fromisoformat(ORDINARY_DAY), root, mixed, spec, wordlists)
        days = sorted((root / "bank").rglob("*.json"))
        baked.append({path.name: path.read_bytes() for path in days})
    assert baked[0] == baked[1]
    assert len(baked[0]) >= 3, f"only {sorted(baked[0])} were baked"


def test_a_word_the_search_cannot_cross_is_skipped_rather_than_failing_the_day(
    cw_spec: GameGeneration, cw_served: crossword.ServedIndex
) -> None:
    """``Unbuildable`` is a request for the next candidate, not a bake failure.

    It also MEASURES how often that happens: the whole design rests on a Tamil
    grid being interlockable, so a fill rate that quietly collapsed would be the
    row's central claim failing while every other test still passed.
    """
    assert issubclass(crossword.SolverExhausted, Unbuildable)
    tried = filled = 0
    for band in cw_spec.difficulties:
        pool = crossword.band_pool(cw_served, band)
        rows = [row for words in pool.by_length.values() for row in words]
        for index in range(0, 2000, 97):
            anchor = rows[index % len(rows)]
            tried += 1
            try:
                crossword.build_puzzle(
                    anchor, cw_spec, f"{ORDINARY_DAY}|{anchor.word}", 0, band, cw_served
                )
            except crossword.SolverExhausted:
                continue
            filled += 1
    assert tried > 0
    assert filled / tried >= 0.90, f"only {filled} of {tried} anchors could be crossed"


def test_a_word_the_mask_has_no_room_for_is_unbuildable_not_a_crash(
    cw_spec: GameGeneration, cw_served: crossword.ServedIndex
) -> None:
    """A length no run on this mask has must be refused by the shared vocabulary."""
    band = cw_spec.difficulties[0]
    assert band.grid is not None
    lengths = {len(cells) for cells in mask_entries(band.grid)}
    wrong = next(
        row
        for words in cw_served.by_length.items()
        for row in words[1]
        if len(row.ezhuthu) not in lengths
    )
    with pytest.raises(Unbuildable, match="no entry"):
        crossword.build_puzzle(
            wrong, cw_spec, f"{ORDINARY_DAY}|{wrong.word}", 0, band, cw_served
        )


def test_every_clue_asks_for_its_answer_without_spelling_it(
    cw_spec: GameGeneration, cw_served: crossword.ServedIndex
) -> None:
    """The clue is the lexicon's own sense, and it is printable as a question.

    Three properties, and the derived set's ``requireClueableMeaning`` gate is
    what makes them hold - so this is the gate checked from the far end, against
    the boards a player would actually be handed.
    """
    ceiling = 60
    for seed, _, _, puzzle in _crosswords(cw_spec, cw_served, 20):
        for entry in puzzle.entries:
            assert entry.clue, f"{seed}: {entry.word!r} has no clue"
            assert entry.word not in entry.clue, f"{seed}: the clue spells {entry.word!r}"
            assert not any(
                char.isascii() and char.isalpha() for char in entry.clue
            ), f"{seed}: {entry.clue!r} clues a Tamil grid in Latin script"
            assert len(entry.clue) <= ceiling, f"{seed}: {entry.clue!r} is too long"


def test_the_numbers_a_player_reads_are_the_ones_on_the_board(
    cw_spec: GameGeneration, cw_served: crossword.ServedIndex
) -> None:
    """Numbering is reading order over the starting cells, computed here again.

    An across and a down beginning on one square share a number, which is what
    lets the clue list say "3 across" and "3 down" of the same cell.
    """
    for seed, _, _, puzzle in _crosswords(cw_spec, cw_served, 10):
        starts = sorted({(e.start.row, e.start.col) for e in puzzle.entries})
        expected = {cell: index for index, cell in enumerate(starts, start=1)}
        for entry in puzzle.entries:
            assert entry.number == expected[(entry.start.row, entry.start.col)], (
                f"{seed}: {entry.word!r} is numbered {entry.number}"
            )
        assert sorted({e.number for e in puzzle.entries}) == list(
            range(1, len(starts) + 1)
        )


def test_every_alternative_fits_the_crossings_and_means_the_same_thing(
    cw_spec: GameGeneration, cw_served: crossword.ServedIndex
) -> None:
    """``alsoValid`` is narrow here: a rival that fits AND is a listed synonym.

    A word that merely fits the crossings answers a DIFFERENT clue and marking
    it right would make the clue list decoration, so this checks BOTH halves -
    that the rival really is enterable, and that the answer's own lexicon row
    calls it a synonym.
    """
    synonyms = {
        row.word: set(row.synonymsTa or ())
        for pool in cw_served.by_length.values()
        for row in pool
    }
    offered = 0
    for seed, _, _, puzzle in _crosswords(cw_spec, cw_served, 20):
        board = _cw_grid(puzzle)
        answers = {entry.word for entry in puzzle.entries}
        for entry in puzzle.entries:
            for rival in entry.alsoValid or ():
                offered += 1
                assert rival not in answers, f"{seed}: {rival!r} is already an answer"
                units, spare = segment(rival), segment(entry.word)
                assert len(units) == len(spare)
                for index, cell in enumerate(_cw_cells(entry)):
                    if len(board[cell]) > 1:
                        assert units[index] == spare[index], (
                            f"{seed}: {rival!r} breaks the word crossing "
                            f"{entry.word!r} at {cell}"
                        )
                assert rival in synonyms[entry.word], (
                    f"{seed}: {rival!r} is not a listed synonym of {entry.word!r}"
                )
    assert offered > 0, "no board offered an alternative - the narrowing is total"


def test_the_crossword_ladder_refuses_every_rung(
    cw_spec: GameGeneration, wordlists: dict[str, GameWordlist]
) -> None:
    """A board that PRINTS a meaning per answer has no rung left to sell.

    The empty vocabulary is not decoration: a hint template registered against
    this Game names a field it cannot sell, and the bake has to fail loudly
    rather than ship a rung that says nothing.
    """
    assert crossword.HINT_FIELDS == frozenset()
    assert cw_spec.hints == []
    row = wordlists[cw_spec.wordlist].words[0]
    broken = cw_spec.model_copy(
        update={"hints": [HintSpec(kind="meaning", template="{meaning}", cost=3)]}
    )
    with pytest.raises(KeyError, match="meaning"):
        crossword.build_hints(row, broken, 1)


def test_the_committed_crossword_set_and_masks_agree(
    cw_spec: GameGeneration, wordlists: dict[str, GameWordlist]
) -> None:
    """Every run on every mask is a length the set can fill, and vice versa.

    The two are configured in different files - the mask in the generator, the
    length range in the wordlist registry - so nothing but this check stops them
    drifting apart into a band that deals a word with nowhere to go.
    """
    words = wordlists[cw_spec.wordlist].words
    assert words, "the committed crossword set is empty"
    lengths = Counter(len(row.ezhuthu) for row in words)
    for band in cw_spec.difficulties:
        assert band.grid is not None, f"band {band.id} lays out no mask"
        runs = {len(cells) for cells in mask_entries(band.grid)}
        assert runs == set(range(band.minLength, band.maxLength + 1))
        for length in runs:
            assert lengths[length] > 0, f"no {length}-ezhuthu word for band {band.id}"
        assert len(band.grid) <= cw_spec.gridRows
        assert len(band.grid[0]) <= cw_spec.gridCols
    # This Game sells no rungs, so it needs no allowance - and a missing entry
    # already reads as zero.
    assert crossword.GAME_ID not in AppConfig.model_validate_json(
        _APP_CONFIG.read_text(encoding="utf-8")
    ).hints.perGame


def test_a_mask_that_could_never_become_a_crossword_is_refused(
    cw_spec: GameGeneration,
) -> None:
    """Five ways a mask can look fine and be unusable, refused when it is READ.

    A mask is config, so it is a persisted surface, and the contract is where it
    has to fail - not in the solver, which would only discover it on the day the
    cron reached that band.
    """
    band = cw_spec.difficulties[0].model_dump()

    def refuse(grid: list[str], match: str) -> None:
        with pytest.raises(ValidationError, match=match):
            DifficultyBand.model_validate({**band, "grid": grid})

    refuse(["#.#.#", "...."], "ragged")
    # A run of two on a band whose words are five ezhuthu.
    refuse(["..#..", ".....", "#.#.#", ".....", "#.#.#"], "cannot fill")
    # Two five-cell entries that never meet.
    refuse([".....", "#####", "....."], "crosses nothing")
    # Nothing but unchecked cells: every open cell is isolated, so no run is
    # longer than one and there is nothing on the board to fill.
    refuse([".#.#.", "#####", ".#.#."], "no entry at all")
    # A perfectly good five-cell run on a board with nothing else on it.
    refuse([".....", "#####"], "entries; a crossword needs two")



# --------------------------------------------------------------------------
# 12. word-ladder (Row 15)
#
# The sixth Game, and the only one whose payload lands a row BEFORE its board.
# The reason is the mechanic: a ladder is a chain of proofs, and the proof is
# the expensive half. Every other Game's builder deals a word; this one has to
# know, before it deals anything, that the word can be climbed from - which is a
# fact about the whole served set rather than about the row. That search runs at
# build time because the browser may never run one (Holy Law #1), so it is the
# graph and the contract that ship here and the board that ships in Row 16.
#
# NOTHING IS ADDED TO config/daily-generator.json. A generator entry there would
# make the cron bake a payload no Game can render. So the spec these tests run
# against is built HERE, out of the same knobs a real entry would carry, and the
# committed config is left alone until the Game exists.
#
# As in the two sections above, the Oracle states the rung rule in its OWN
# arithmetic rather than calling the helper the generator and the contract
# share. An Oracle that reuses the implementation it is checking proves the
# implementation is self-consistent, which is not the claim.
# --------------------------------------------------------------------------

LADDER_SET = "datasets/wordlists/derived/ladder.json"


def _rung_rule(below: str, above: str) -> str:
    """The Oracle's own reading of "one added ezhuthu, rearranging allowed".

    Written out of ``Counter`` rather than out of ``added_ezhuthu`` so the
    implementation owes it nothing. Raises when the pair is not a legal step, so
    a caller need only call it to have asserted the rule.
    """
    low, high = Counter(segment(below)), Counter(segment(above))
    gained = sorted((high - low).elements())
    lost = sorted((low - high).elements())
    assert not lost, f"{above!r} drops {lost} from {below!r}"
    assert len(gained) == 1, f"{above!r} adds {gained} to {below!r}"
    return gained[0]


@pytest.fixture(scope="module")
def wl_wordlist() -> GameWordlist:
    return GameWordlist.model_validate_json(
        (_REPO_ROOT / LADDER_SET).read_text(encoding="utf-8")
    )


@pytest.fixture(scope="module")
def wl_spec() -> GameGeneration:
    """The generator entry the ladder WOULD carry, built here rather than committed.

    Its three bands separate on rung count, which is what a ladder's difficulty
    is: a longer climb is more steps to survive, where a rarer word is only a
    harder step. ``targets`` is the knob, borrowed unchanged from the search
    board, because on both boards the number of words IS the difficulty.
    """
    return GameGeneration(
        gameId=word_ladder.GAME_ID,
        packId="ta-core",
        wordlist=LADDER_SET,
        attempts=1,
        timeLimitSec=0,
        reveal=0,
        choiceCount=8,
        dailyRank=15,
        difficulties=[
            DifficultyBand(id="easy", minLength=2, maxLength=3, maxStratum=2, targets=3),
            DifficultyBand(id="medium", minLength=2, maxLength=4, maxStratum=3, targets=4),
            DifficultyBand(id="hard", minLength=2, maxLength=4, maxStratum=4, targets=5),
        ],
    )


@pytest.fixture(scope="module")
def wl_graph(
    wl_spec: GameGeneration, wl_wordlist: GameWordlist
) -> word_ladder.LadderGraph:
    return word_ladder.index_served(wl_wordlist, wl_spec)


def _band_rows(
    graph: word_ladder.LadderGraph, band: DifficultyBand
) -> list[GameWord]:
    """Every served row this band would deal, in a stable order."""
    return sorted(
        (
            row
            for rows in graph.words.values()
            for row in rows
            if band.minLength <= len(row.ezhuthu) <= band.maxLength
            and row.frequencyStratum <= band.maxStratum
        ),
        key=lambda row: row.word,
    )


def _ladders(
    spec: GameGeneration, graph: word_ladder.LadderGraph, per_band: int
) -> list[tuple[str, DifficultyBand, GameWord, WordLadderPuzzle]]:
    """Build ``per_band`` real ladders per band, from real rows and real dates.

    A row the graph cannot climb from is SKIPPED rather than failed, which is
    what the day loop does with it: ``Unbuildable`` is the builder's way of
    asking for the next candidate. How often that happens is measured by its own
    test below, so a silent collapse to a handful of ladders cannot hide here.
    """
    out: list[tuple[str, DifficultyBand, GameWord, WordLadderPuzzle]] = []
    for band in spec.difficulties:
        made = 0
        for offset, anchor in enumerate(_band_rows(graph, band)):
            if made >= per_band:
                break
            day = (
                date.fromisoformat(ORDINARY_DAY) + timedelta(days=offset)
            ).isoformat()
            seed = f"{day}|{anchor.word}"
            try:
                built = word_ladder.build_puzzle(anchor, spec, seed, 0, band, graph)
            except word_ladder.NoLadder:
                continue
            out.append((seed, band, anchor, built))
            made += 1
    return out


def test_every_rung_adds_exactly_one_ezhuthu_to_the_one_below(
    wl_spec: GameGeneration, wl_graph: word_ladder.LadderGraph
) -> None:
    """ORACLE (a) - the rung rule, over real generator output.

    For every ladder the real graph produced, each consecutive pair is checked
    with the Oracle's own multiset arithmetic: exactly one ezhuthu arrives and
    none leaves. Rearrangement is therefore free and substitution impossible,
    both stated in one comparison rather than as two rules that could disagree.
    Strictly increasing length is asserted separately even though it follows,
    because it is the property a reader of the board would notice first.
    """
    ladders = _ladders(wl_spec, wl_graph, 60)
    assert len(ladders) >= 150, f"only {len(ladders)} ladders built - the Oracle is thin"
    steps = 0
    for seed, band, _, puzzle in ladders:
        assert len(puzzle.rungs) == band.targets, seed
        for below, above in zip(puzzle.rungs, puzzle.rungs[1:]):
            _rung_rule(below.word, above.word)
            assert len(segment(above.word)) == len(segment(below.word)) + 1, (
                f"{seed}: {above.word!r} is not one ezhuthu taller than {below.word!r}"
            )
            steps += 1
    assert steps >= 300


def test_every_rung_is_a_word_the_set_really_serves(
    wl_spec: GameGeneration,
    wl_graph: word_ladder.LadderGraph,
    wl_wordlist: GameWordlist,
) -> None:
    """ORACLE (b) - a climb only ever passes through SERVED words.

    Checked against the committed wordlist rather than against the graph the
    builder was handed, so an index built from the wrong set, or a rung invented
    somewhere between the graph and the payload, fails here. Every alternative
    the payload records is checked the same way: telling a player that what they
    spelled is a word only helps when it is a word this game would deal.
    """
    served = {row.word for row in wl_wordlist.words}
    for seed, _, anchor, puzzle in _ladders(wl_spec, wl_graph, 40):
        assert puzzle.rungs[0].word == anchor.word, seed
        for rung in puzzle.rungs:
            assert rung.word in served, f"{seed}: {rung.word!r} is not served"
            for other in rung.alsoValid or ():
                assert other in served, f"{seed}: alsoValid {other!r} is not served"


def test_every_alternative_is_reachable_from_the_rung_below_using_the_bank(
    wl_spec: GameGeneration, wl_graph: word_ladder.LadderGraph
) -> None:
    """ORACLE (c) - what is recorded is what the player can actually reach.

    An alternative is a promise that a particular arrangement will be answered
    rather than crossed out, so it has to be one the bank can really produce:
    one added ezhuthu above the rung below, with that ezhuthu in the bank. The
    first rung is given, so it carries none.
    """
    recorded = 0
    for seed, _, _, puzzle in _ladders(wl_spec, wl_graph, 40):
        bank = set(puzzle.choices)
        assert puzzle.rungs[0].alsoValid is None, seed
        for below, above in zip(puzzle.rungs, puzzle.rungs[1:]):
            for other in above.alsoValid or ():
                assert other != above.word, seed
                unit = _rung_rule(below.word, other)
                assert unit in bank, f"{seed}: {other!r} needs {unit!r}, not in the bank"
                recorded += 1
    # A ladder whose every rung had one answer would make the field dead weight;
    # the graph branches enough that it does not.
    assert recorded > 0


def test_the_bank_can_climb_the_whole_ladder_and_still_hold_a_decision(
    wl_spec: GameGeneration, wl_graph: word_ladder.LadderGraph
) -> None:
    """ORACLE (d) - the ladder is playable with no Tamil keyboard.

    Every ezhuthu the climb adds has to be in the bank, counted with
    multiplicity so a ladder adding the same letter twice really is offered two
    of them, and the bank has to be strictly bigger than the climb needs or it
    is an answer rather than a choice. Every tile is checked to be one ezhuthu
    AND a letter of Tamil: a lone vowel sign passes the first and fails the
    second.
    """
    letters = set(EZHUTHU_INVENTORY)
    for seed, _, _, puzzle in _ladders(wl_spec, wl_graph, 40):
        needed = Counter(
            _rung_rule(below.word, above.word)
            for below, above in zip(puzzle.rungs, puzzle.rungs[1:])
        )
        available = Counter(puzzle.choices)
        for unit, count in needed.items():
            assert available[unit] >= count, f"{seed}: the bank is short of {unit!r}"
        assert len(puzzle.choices) == wl_spec.choiceCount, seed
        assert len(puzzle.choices) > sum(needed.values()), seed
        for unit in puzzle.choices:
            assert segment(unit) == [unit], f"{seed}: {unit!r} is not one ezhuthu"
            assert unit in letters, f"{seed}: {unit!r} is not a letter of Tamil"


def test_two_runs_of_one_ladder_are_byte_identical(
    wl_spec: GameGeneration, wl_wordlist: GameWordlist
) -> None:
    """ORACLE (e) - determinism, from the graph up.

    Both halves are rebuilt from the committed wordlist, so the index, the
    climb, the bank and the recorded alternatives all have to land the same way
    twice. Compared as serialized BYTES rather than as models, because that is
    what a bake commits and what a drift gate would compare.
    """
    first = word_ladder.index_served(wl_wordlist, wl_spec)
    second = word_ladder.index_served(wl_wordlist, wl_spec)
    assert first.reach == second.reach
    assert first.up == second.up
    band = wl_spec.difficulties[1]
    made = 0
    for anchor in _band_rows(first, band)[:400]:
        seed = f"{ORDINARY_DAY}|{anchor.word}"
        try:
            left = word_ladder.build_puzzle(anchor, wl_spec, seed, 0, band, first)
        except word_ladder.NoLadder:
            continue
        right = word_ladder.build_puzzle(anchor, wl_spec, seed, 0, band, second)
        assert left.model_dump_json() == right.model_dump_json(), seed
        made += 1
    assert made > 0


def test_the_graph_is_the_add_one_ezhuthu_relation_and_nothing_else(
    wl_graph: word_ladder.LadderGraph, wl_wordlist: GameWordlist
) -> None:
    """Every edge is a legal step, and no legal step is missing.

    Both directions matter and they fail differently. A wrong edge ships a
    ladder that does not climb; a missing one silently throws content away, and
    that is the failure this row's whole risk is about. Completeness is checked
    by asking, for a sample of signatures, which OTHER signatures are one letter
    above them under the Oracle's own arithmetic, and comparing that set to the
    edges the index recorded.
    """
    by_key: dict[tuple[str, ...], list[str]] = {}
    for row in wl_wordlist.words:
        by_key.setdefault(tuple(sorted(row.ezhuthu)), []).append(row.word)
    assert set(by_key) == set(wl_graph.words)
    for below, above_keys in wl_graph.up.items():
        for above in above_keys:
            gained = Counter(above) - Counter(below)
            assert sum(gained.values()) == 1, (below, above)
            assert not (Counter(below) - Counter(above)), (below, above)
    sample = sorted(by_key)[::400]
    by_size: dict[int, list[tuple[str, ...]]] = {}
    for key in by_key:
        by_size.setdefault(len(key), []).append(key)
    for key in sample:
        expected = {
            other
            for other in by_size.get(len(key) + 1, ())
            if sum((Counter(other) - Counter(key)).values()) == 1
            and not (Counter(key) - Counter(other))
        }
        assert set(wl_graph.up.get(key, ())) == expected, key


def test_reach_is_the_longest_climb_and_a_shorter_one_always_fits_inside_it(
    wl_graph: word_ladder.LadderGraph
) -> None:
    """``reach`` is what lets the climb never backtrack, so it has to be exact.

    Recomputed here from the edges alone. Its two claims are that a signature
    with ``reach`` r really has a chain of r, and that it has no chain of r + 1 -
    the second being the one that would let the builder step onto a dead end.
    """
    for key, deep in wl_graph.reach.items():
        above = wl_graph.up.get(key, ())
        assert deep == 1 + max((wl_graph.reach[nxt] for nxt in above), default=0), key
        if deep == 1:
            assert not above, key


def test_a_word_the_graph_cannot_climb_from_is_refused_rather_than_shortened(
    wl_spec: GameGeneration, wl_graph: word_ladder.LadderGraph
) -> None:
    """The thin-graph case, which is the COMMON case, and how it is answered.

    Most served words start no ladder: a builder that quietly returned a short
    climb would ship a two-rung "ladder" under a three-rung band. ``NoLadder``
    is an ``Unbuildable``, which is the day loop's signal to deal the next
    candidate - the same contract the crossword's exhausted solver has.
    """
    band = wl_spec.difficulties[2]
    rows = _band_rows(wl_graph, band)
    refused = [
        row
        for row in rows
        if wl_graph.reach.get(word_ladder.signature(row.ezhuthu), 0) < band.targets
    ]
    assert refused, "the band has no unclimbable word, so this test proves nothing"
    with pytest.raises(word_ladder.NoLadder):
        word_ladder.build_puzzle(refused[0], wl_spec, "seed", 0, band, wl_graph)
    assert issubclass(word_ladder.NoLadder, Unbuildable)
    built = sum(
        1
        for row in rows
        if wl_graph.reach.get(word_ladder.signature(row.ezhuthu), 0) >= band.targets
    )
    # The measured density this row exists to report: the hardest band's pool is
    # thousands of rows and about one in a hundred of them can be climbed from.
    assert 0 < built < len(rows)


def test_the_signature_step_and_the_contract_agree_on_what_was_added(
    wl_spec: GameGeneration, wl_graph: word_ladder.LadderGraph
) -> None:
    """The generator reads the added letter off multisets; the contract off words.

    They have to be the same value, and the module says so in prose - a
    signature IS ``sorted(segment(word))``. This is where that claim is checked
    rather than asserted, over real climbs, because the generator deliberately
    does NOT round-trip a signature back into a string to reuse the contract's
    reading.
    """
    checked = 0
    for seed, _, _, puzzle in _ladders(wl_spec, wl_graph, 30):
        for below, above in zip(puzzle.rungs, puzzle.rungs[1:]):
            keys = (
                word_ladder.signature(segment(below.word)),
                word_ladder.signature(segment(above.word)),
            )
            assert word_ladder.step(*keys) == added_ezhuthu(below.word, above.word)
            assert word_ladder.step(*keys) == _rung_rule(below.word, above.word)
            checked += 1
    assert checked > 0


def test_the_climb_maximises_the_weakest_rung_rather_than_taking_any_step(
    wl_spec: GameGeneration, wl_graph: word_ladder.LadderGraph
) -> None:
    """The one quality decision in the builder, checked as a property.

    A ladder is played by guessing each next word, so one word nobody knows ends
    the climb however good the rest is. Every step is therefore taken to leave
    the RAREST rung of the finished ladder as familiar as it can be. Checked by
    replaying each choice: no neighbour that could still finish the climb offers
    a better guaranteed floor than the one the builder took.
    """
    checked = 0
    for seed, band, anchor, _ in _ladders(wl_spec, wl_graph, 25):
        chain = word_ladder.climb(
            wl_graph, word_ladder.signature(anchor.ezhuthu), band.targets, seed
        )
        for index, (below, above) in enumerate(zip(chain, chain[1:])):
            left = band.targets - index - 1
            taken = min(
                float(wl_graph.best_word(above).frequency), wl_graph.promise[above][left]
            )
            for other in wl_graph.up[below]:
                if wl_graph.reach[other] < left:
                    continue
                offered = min(
                    float(wl_graph.best_word(other).frequency),
                    wl_graph.promise[other][left],
                )
                assert offered <= taken, f"{seed}: {other} was a better step"
            checked += 1
    assert checked > 0


def test_a_ladder_that_substitutes_or_drops_an_ezhuthu_is_refused(
    wl_spec: GameGeneration, wl_graph: word_ladder.LadderGraph
) -> None:
    """The rejection half: the contract refuses what the generator cannot build.

    Three ways a chain can look like a ladder and not be one, each stated
    against the payload rather than against the builder, because the payload is
    what a future Game and a future generator both read.
    """
    seed, _, _, good = _ladders(wl_spec, wl_graph, 1)[0]
    payload = good.model_dump(mode="json", exclude_none=True)

    def refuse(rungs: list[dict[str, Any]], match: str) -> None:
        with pytest.raises(ValidationError, match=match):
            WordLadderPuzzle.model_validate({**payload, "rungs": rungs})

    # Two ezhuthu added at once: a legal-looking climb that skips a rung.
    skipped = [dict(rung) for rung in payload["rungs"]]
    skipped[1]["word"] = good.rungs[2].word
    skipped[1].pop("alsoValid", None)
    refuse(skipped, "exactly one ezhuthu")
    # An ezhuthu swapped rather than added: the same length change, a different
    # word underneath it.
    swapped = [dict(rung) for rung in payload["rungs"]]
    units = segment(good.rungs[1].word)
    swapped[1]["word"] = "".join([*units[:-1], segment(good.rungs[0].word)[0], units[-1]])
    swapped[1].pop("alsoValid", None)
    with pytest.raises(ValidationError):
        WordLadderPuzzle.model_validate({**payload, "rungs": swapped})
    # The climb run backwards, which drops letters instead of adding them.
    refuse([dict(rung) for rung in reversed(payload["rungs"])], "may only add")


def test_a_bank_that_cannot_climb_or_offers_no_choice_is_refused(
    wl_spec: GameGeneration, wl_graph: word_ladder.LadderGraph
) -> None:
    """Without a Tamil keyboard the bank IS the input method, so it is checked."""
    _, _, _, good = _ladders(wl_spec, wl_graph, 1)[0]
    payload = good.model_dump(mode="json", exclude_none=True)
    needed = [
        added_ezhuthu(below.word, above.word)
        for below, above in zip(good.rungs, good.rungs[1:])
    ]
    with pytest.raises(ValidationError, match="cannot climb the ladder"):
        WordLadderPuzzle.model_validate(
            {**payload, "choices": [u for u in payload["choices"] if u != needed[0]]}
        )
    with pytest.raises(ValidationError, match="rather than a choice"):
        WordLadderPuzzle.model_validate({**payload, "choices": needed})
    with pytest.raises(ValidationError, match="not a letter of Tamil"):
        WordLadderPuzzle.model_validate(
            {**payload, "choices": [*payload["choices"], "z"]}
        )


def test_an_alternative_the_bank_cannot_spell_is_refused(
    wl_spec: GameGeneration, wl_graph: word_ladder.LadderGraph
) -> None:
    """An alternative nobody can enter is a message that can never fire."""
    ladders = [
        entry
        for entry in _ladders(wl_spec, wl_graph, 40)
        if any(rung.alsoValid for rung in entry[3].rungs[1:])
    ]
    assert ladders, "no ladder recorded an alternative, so this test proves nothing"
    good = ladders[0][3]
    payload = good.model_dump(mode="json", exclude_none=True)
    spent = {
        added_ezhuthu(below.word, other)
        for below, above in zip(good.rungs, good.rungs[1:])
        for other in above.alsoValid or ()
    }
    with pytest.raises(ValidationError, match="which the bank does not hold"):
        WordLadderPuzzle.model_validate(
            {
                **payload,
                "choices": [
                    unit
                    for unit in payload["choices"]
                    if unit not in spent
                    or unit
                    in {
                        added_ezhuthu(a.word, b.word)
                        for a, b in zip(good.rungs, good.rungs[1:])
                    }
                ],
            }
        )
    first = [dict(rung) for rung in payload["rungs"]]
    first[0]["alsoValid"] = [good.rungs[1].word]
    with pytest.raises(ValidationError, match="is given"):
        WordLadderPuzzle.model_validate({**payload, "rungs": first})


def test_the_ladder_set_is_registered_and_a_day_can_now_bake_it(
    generator: DailyGenerator, app_config: AppConfig, wl_wordlist: GameWordlist
) -> None:
    """Row 15 shipped the proof; Row 16 ships the board, and the seam was config.

    The claim Row 15 made was that adding this Game would cost a ``games`` entry
    plus a builder registration and nothing else - the same one-Game-one-
    registration claim the five Games before it made. This is that claim,
    collected: the derived set, the registry entry, the generator spec, the
    builder, and the ordinary ring all name it, and no other file had to move.
    """
    assert wl_wordlist.gameId == word_ladder.GAME_ID
    spec = next(one for one in generator.games if one.gameId == word_ladder.GAME_ID)
    assert spec.wordlist == LADDER_SET
    assert word_ladder.GAME_ID in daily.BUILDERS
    assert word_ladder.GAME_ID in app_config.daily.games
    registry = derive.load_registry(_REPO_ROOT / "config" / "derived-wordlists.json")
    entry = next(one for one in registry.sets if one.gameId == word_ladder.GAME_ID)
    assert entry.out == LADDER_SET
    assert (entry.selection.minLength, entry.selection.maxLength) == (2, 7)


def test_the_ladder_is_not_in_the_themed_ring_and_the_measurement_says_why(
    generator: DailyGenerator,
    app_config: AppConfig,
    wordlists: dict[str, GameWordlist],
) -> None:
    """The one ring this Game is deliberately kept OUT of, pinned from the data.

    A themed day needs every Game in it to build from that theme's few hundred
    rows, and a ladder needs something stronger than enough words: it needs an
    add-one-ezhuthu CHAIN through them. themed-nature has 429 rows and five
    edges in total, so five rows can climb one rung and none can climb the three
    the easiest band asks for. Registering it would not have crashed a bake - it
    would have made every themed date decline in silence and fall back to an
    ordinary day - which is exactly why the refusal is asserted here rather than
    left to be noticed as a missing feature.
    """
    assert word_ladder.GAME_ID not in app_config.daily.themedGames
    spec = next(one for one in generator.games if one.gameId == word_ladder.GAME_ID)
    graph = word_ladder.index_served(wordlists[THEMED_SET], spec)
    assert sum(len(above) for above in graph.up.values()) == 5
    easiest = min(band.targets for band in spec.difficulties)
    assert easiest == 3
    assert not [key for key, reach in graph.reach.items() if reach >= easiest]


def test_the_ladder_bands_have_years_of_climbable_content(
    generator: DailyGenerator, wl_wordlist: GameWordlist, wl_graph: word_ladder.LadderGraph
) -> None:
    """The other half of the registration: what each band can actually deal.

    Most served words start no ladder at all, so a band's row count says nothing
    about its content - what matters is how many of those rows the graph can
    carry the band's rung count from. Asserted as a floor rather than an exact
    number, because the lexicon grows underneath it; the point is that the
    thinnest band still holds decades of daily content at one draw a day.
    """
    claimed: dict[str, list[GameWord]] = {}
    spec = next(one for one in generator.games if one.gameId == word_ladder.GAME_ID)
    claimed = {band.id: [] for band in spec.difficulties}
    for row in wl_wordlist.words:
        band_id = daily.difficulty_of(row, spec)
        if band_id is not None:
            claimed[band_id].append(row)
    for band in spec.difficulties:
        climbable = [
            row
            for row in claimed[band.id]
            if wl_graph.reach.get(word_ladder.signature(row.ezhuthu), 0) >= band.targets
        ]
        assert len(climbable) >= 80, f"{band.id} has {len(climbable)} climbable rows"


def test_the_ledger_reads_every_rung_a_served_ladder_showed(
    wl_spec: GameGeneration, wl_graph: word_ladder.LadderGraph, wl_wordlist: GameWordlist
) -> None:
    """The anti-repeat ledger reads a ladder's WHOLE climb, not just its start.

    A ladder is the fourth way a payload names its answers, and the third that
    names more than one. A day that served a climb has shown the player every
    word in it - with its meaning, free, beside the rung - so all of them must
    reach ``answer_words``, or one comes back as another day's answer.
    """
    band = wl_spec.difficulties[0]
    anchor = next(
        row
        for row in wl_wordlist.words
        if wl_graph.reach.get(word_ladder.signature(row.ezhuthu), 0) >= band.targets
    )
    built = word_ladder.build_puzzle(anchor, wl_spec, "ledger", 0, band, wl_graph)
    payload = built.model_dump(mode="json", exclude_none=True)
    assert daily.answer_words(payload) == [rung.word for rung in built.rungs]
    assert len(built.rungs) == band.targets >= 3


def test_this_game_bakes_no_hint_and_a_registered_rung_would_fail_the_bake(
    wl_spec: GameGeneration, wl_wordlist: GameWordlist
) -> None:
    """The empty vocabulary is a refusal, not an oversight.

    Every rung the shared ladder can render is a fact about the NEXT word, which
    on a three-letter answer is most of it - so the help this Game gives is a
    per-rung reveal the Game prices at play time, and the payload carries no
    hints at all. A config that registered a rung against it names a field this
    Game cannot sell and fails the bake loudly.
    """
    row = wl_wordlist.words[0]
    assert word_ladder.HINT_FIELDS == frozenset()
    assert word_ladder.build_hints(row, wl_spec, 3) == []
    with_rung = wl_spec.model_copy(
        update={
            "hints": [HintSpec(kind="meaning", template="{meaning}", cost=5)],
        }
    )
    with pytest.raises(KeyError, match="cannot sell"):
        word_ladder.build_hints(row, with_rung, 3)
