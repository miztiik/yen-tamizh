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
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any, get_args

import pytest
from pydantic import ValidationError

from yen_tamizh_backend.contracts.anagram_puzzle import AnagramPuzzle
from yen_tamizh_backend.contracts.app_config import AppConfig
from yen_tamizh_backend.contracts.bank_index import BankIndex
from yen_tamizh_backend.contracts.copy import Copy
from yen_tamizh_backend.contracts.daily_generator import (
    DailyGenerator,
    GameGeneration,
    HintSpec,
)
from yen_tamizh_backend.contracts.game_wordlist import GameWord, GameWordlist
from yen_tamizh_backend.contracts.lexicon import PartOfSpeech
from yen_tamizh_backend.contracts.missing_letters_puzzle import MissingLettersPuzzle
from yen_tamizh_backend.contracts.puzzle_file import PuzzleFile
from yen_tamizh_backend.contracts.word_search_puzzle import (
    GridPoint,
    WordSearchPuzzle,
    WordSearchTarget,
)
from yen_tamizh_backend.contracts.wordle_puzzle import WordlePuzzle
from yen_tamizh_backend.ezhuthu import EZHUTHU_INVENTORY, segment
from yen_tamizh_backend.generate import anagram, daily, missing_letters, word_search, wordle
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

# The wordlists are keyed by the path the registry names, because a Game draws
# from more than one: its ordinary set and one per registered theme.
ANAGRAM_SET = "datasets/wordlists/derived/anagram.json"
THEMED_SET = "datasets/wordlists/derived/themed-nature.json"

# A date the configured cadence allows a theme on, and the day after it. Both
# are past the committed bank, so a themed test bakes into empty ground.
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
        if daily.difficulty_of(row, spec) == "hard"
    ]
    with pytest.raises(ValueError, match="easy"):
        daily.pick_words(only_hard, spec, FIRST_DAY, 3, used=())


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
        if daily.difficulty_of(row, spec) == "hard"
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
            row = served.get(str(item.payload["word"]))
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

    day = daily.build_day(
        ORDINARY_DAY,
        app_config,
        generator,
        wordlists | {ANAGRAM_SET: served},
        used=(),
    )

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
    """The registry claim: a second Game costs a registration, not a day-loop edit.

    ``config/app-config.json`` deliberately still deals three anagrams - changing
    what today's players get is its own reviewed decision - so this proves the
    wiring against a mix the config COULD hold rather than against the one it
    does.
    """
    mixed = app_config.model_copy(
        update={
            "daily": app_config.daily.model_copy(
                update={
                    "playlistLength": 4,
                    "mix": {
                        "anagram": 1,
                        "missing-letters": 1,
                        "wordle": 1,
                        "word-search": 1,
                    },
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
        # Four Games, four payload shapes, one unchanged puzzle-file.
        assert "tiles" not in guessed.payload
        assert "blanks" not in guessed.payload
        assert "choices" not in guessed.payload
        assert "word" not in traced.payload
        assert "attempts" not in traced.payload
        # A day's own record of what it served has to see every word, or the
        # anti-repeat ledger deals a search board's words again next week.
        assert set(day.words) >= {
            target["word"] for target in traced.payload["targets"]
        }


def test_an_unregistered_game_fails_loudly(generator: DailyGenerator) -> None:
    """A mix naming a Game with no builder must not bake a silently empty day."""
    with pytest.raises(ValueError, match="no registered puzzle builder"):
        daily.builder_for("word-ladder")
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


def test_the_day_ledger_reads_both_payload_shapes() -> None:
    """One definition of "the words this payload asked for", used by both readers.

    Three Games put one answer under ``word`` and this one puts several under
    ``targets``. The anti-repeat ledger and the bake's own record of what a day
    served must agree, or a search board's words come back a week later because
    the ledger could not see them.
    """
    assert daily.answer_words({"word": "\u0b85"}) == ["\u0b85"]
    assert daily.answer_words(
        {"targets": [{"word": "\u0b85"}, {"word": "\u0b86"}]}
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

