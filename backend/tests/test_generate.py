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
4. **The knobs.** Difficulty comes from the configured length bands, hints are
   capped by the app config's per-Game allowance, and a mix that does not add up
   to the playlist length is an error rather than a short day.
5. **The seam.** The engine reads the derived wordlist and nothing above it, and
   a published day survives a changed wordlist untouched.
"""

from __future__ import annotations

import json
import shutil
from datetime import date, timedelta
from pathlib import Path

import pytest

from yen_tamizh_backend.contracts.anagram_puzzle import AnagramPuzzle
from yen_tamizh_backend.contracts.app_config import AppConfig
from yen_tamizh_backend.contracts.bank_index import BankIndex
from yen_tamizh_backend.contracts.daily_generator import DailyGenerator
from yen_tamizh_backend.contracts.game_wordlist import GameWordlist
from yen_tamizh_backend.contracts.puzzle_file import PuzzleFile
from yen_tamizh_backend.ezhuthu import segment
from yen_tamizh_backend.generate import anagram, daily
from yen_tamizh_backend.generate.seed import hash_seed, seeded_shuffle
from yen_tamizh_backend.scripts.generate_today import generate, load_wordlists

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP_CONFIG = _REPO_ROOT / "config" / "app-config.json"
_GENERATOR = _REPO_ROOT / "config" / "daily-generator.json"

# The first day the bank was baked (Row 13). Used as a fixed date so the tests
# assert over a real, committed day rather than whatever today happens to be.
FIRST_DAY = "2026-08-13"


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


# --------------------------------------------------------------------------
# 1a. The guard: a published day is never rewritten
# --------------------------------------------------------------------------


def _reordered(wordlists: dict[str, GameWordlist]) -> dict[str, GameWordlist]:
    """The same real rows in a different order - what a wordlist change looks like.

    A day is a pure function of its date AND of the list it drew from, so
    reordering the candidates is enough to make every later pick differ.
    """
    return {
        game_id: wordlist.model_copy(update={"words": list(reversed(wordlist.words))})
        for game_id, wordlist in wordlists.items()
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
    """The engine consumes the derived layer; it never invents a word."""
    allowed = {row.word for row in wordlists["anagram"].words}
    for path in _committed_days(bank_dir):
        puzzle_file = PuzzleFile.model_validate_json(path.read_text(encoding="utf-8"))
        for item in puzzle_file.items:
            assert str(item.payload["word"]) in allowed


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


def test_difficulty_comes_from_the_configured_length_bands(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    spec = generator.games[0]
    bands = {band.id: (band.minLength, band.maxLength) for band in spec.difficulties}
    for row in wordlists["anagram"].words:
        bucket = anagram.difficulty_of(row, spec)
        low, high = bands[bucket]
        assert low <= len(row.ezhuthu) <= high


def test_hints_are_capped_by_the_app_config_allowance(
    generator: DailyGenerator, wordlists: dict[str, GameWordlist]
) -> None:
    spec = generator.games[0]
    row = wordlists["anagram"].words[0]
    assert anagram.build_hints(row, spec, 0) == []
    assert len(anagram.build_hints(row, spec, 1)) == 1
    assert len(anagram.build_hints(row, spec, 99)) == len(spec.hints)
    assert row.hints is not None
    assert row.hints.firstEzhuthu in anagram.build_hints(row, spec, 1)[0].text


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
    spec = generator.games[0]
    broken = spec.model_copy(
        update={
            "hints": [
                spec.hints[0].model_copy(update={"template": "{meaning}"}),
            ]
        }
    )
    with pytest.raises(KeyError):
        anagram.build_hints(wordlists["anagram"].words[0], broken, 1)


# --------------------------------------------------------------------------
# 5. Selection + the layer seam
# --------------------------------------------------------------------------


def test_selection_skips_words_already_served(
    wordlists: dict[str, GameWordlist],
) -> None:
    candidates = wordlists["anagram"].words
    plain = daily.pick_words(candidates, FIRST_DAY, "anagram", 3, used=())
    assert len(plain) == 3
    avoided = daily.pick_words(
        candidates, FIRST_DAY, "anagram", 3, used={row.word for row in plain}
    )
    assert {row.word for row in avoided}.isdisjoint({row.word for row in plain})


def test_selection_fills_the_day_even_when_everything_was_served(
    wordlists: dict[str, GameWordlist],
) -> None:
    """A repeat is a smaller failure than a playlist that does not add up."""
    candidates = wordlists["anagram"].words
    filled = daily.pick_words(
        candidates, FIRST_DAY, "anagram", 3, used={row.word for row in candidates}
    )
    assert len(filled) == 3


def test_selection_with_no_candidates_is_an_error() -> None:
    with pytest.raises(ValueError, match="no candidate words"):
        daily.pick_words([], FIRST_DAY, "anagram", 1, used=())


def test_the_engine_reads_only_the_derived_layer() -> None:
    """The corpus and the daily puzzle are different layers (user directive)."""
    forbidden = ("corpus.ingest", "corpus.rank", "corpus.derive")
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
