"""The Infinite pool: what the generator promises, and what is on disk (Row 22).

Five claims, and every one of them is checked against real committed artifacts
rather than a fabricated pool (Holy Law #7):

1. **Determinism.** A pool is seeded by its Game's name and drawn from committed
   wordlists, so two runs over the same inputs produce byte-identical files and
   the same ids. That is the hand-edit gate: a board edited by hand is reverted
   by the next bake, and this test is what proves the next bake is predictable.
2. **The committed pool IS what the generator produces.** For the two Games
   cheap enough to rebuild at their real ceiling, the bytes on disk are compared
   against a fresh bake.
3. **Integrity of what shipped.** Every file under ``frontend/public/pool/``
   parses, validates as a pool item, is named after its own id, and is listed by
   its Game's index at the band it claims - and the index lists nothing that is
   not there.
4. **No word twice inside one Game's pool.** The stream's whole claim is that it
   does not repeat itself, and a pool holding one word under two ids would break
   that before the anti-repeat window ever ran.
5. **The ceiling is a ceiling.** A band that runs out of buildable rows stops
   early and the index says so, rather than padding with a repeat.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

import pytest

from yen_tamizh_backend.contracts.app_config import AppConfig
from yen_tamizh_backend.contracts.daily_generator import DailyGenerator
from yen_tamizh_backend.contracts.game_wordlist import GameWordlist
from yen_tamizh_backend.contracts.pool_index import PoolIndex, PoolItem
from yen_tamizh_backend.generate import daily, infinite
from yen_tamizh_backend.scripts import generate_infinite
from yen_tamizh_backend.scripts.generate_today import load_wordlists

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP_CONFIG = _REPO_ROOT / "config" / "app-config.json"
_GENERATOR = _REPO_ROOT / "config" / "daily-generator.json"

# A ceiling small enough to bake all six Games twice in a couple of seconds. The
# claim it proves - the same inputs give the same bytes - does not depend on how
# deep the pool is, so paying 54 seconds of CI for it would buy nothing.
_PROBE_PER_BAND = 3

# The Games whose real-ceiling bake is fast enough to compare against the
# committed bytes on every run (measured: 0.06 s and 0.91 s; the crossword and
# the search grid are 20 seconds each).
_CHEAP_GAMES = ("wordle", "anagram")


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
def pool_dir(generator: DailyGenerator) -> Path:
    return _REPO_ROOT / generator.poolDir


@pytest.fixture(scope="module")
def pooled_games(app_config: AppConfig) -> list[str]:
    return infinite.pool_games(app_config)


# --- 1. determinism -------------------------------------------------------


def test_two_runs_over_the_same_inputs_are_byte_identical(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
    pooled_games: list[str],
) -> None:
    for game_id in pooled_games:
        runs = [
            [
                generate_infinite.render_item(item)
                for item in infinite.build_pool(
                    game_id, app_config, generator, wordlists, _PROBE_PER_BAND
                )
            ]
            for _ in range(2)
        ]
        assert runs[0] == runs[1], f"{game_id} pool is not reproducible"
        assert runs[0], f"{game_id} baked no pool at all"


def test_a_pool_is_numbered_from_zero_without_a_gap(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
    pooled_games: list[str],
) -> None:
    for game_id in pooled_games:
        items = infinite.build_pool(
            game_id, app_config, generator, wordlists, _PROBE_PER_BAND
        )
        assert [item.id for item in items] == [
            infinite.pool_id(ordinal) for ordinal in range(len(items))
        ]


def test_the_index_agrees_with_the_pool_it_indexes(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    items = infinite.build_pool(
        "anagram", app_config, generator, wordlists, _PROBE_PER_BAND
    )
    index = infinite.build_index("anagram", items)
    assert index.gameId == "anagram"
    assert index.totalCount == len(items)
    assert [entry.id for entry in index.items] == [item.id for item in items]
    assert [entry.difficulty for entry in index.items] == [
        item.difficulty for item in items
    ]


# --- 2. the committed bytes are the generator's own -----------------------


def test_the_committed_pool_is_what_the_generator_produces(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
    pool_dir: Path,
    tmp_path: Path,
) -> None:
    for game_id in _CHEAP_GAMES:
        items = infinite.build_pool(game_id, app_config, generator, wordlists)
        generate_infinite.write_pool(tmp_path, tmp_path, game_id, items)
        for item in items:
            fresh = (tmp_path / game_id / f"{item.id}.json").read_bytes()
            committed = (pool_dir / game_id / f"{item.id}.json").read_bytes()
            assert fresh == committed, f"{game_id}/{item.id} has drifted"
        assert (tmp_path / game_id / "index.json").read_bytes() == (
            pool_dir / game_id / "index.json"
        ).read_bytes()


# --- 3. integrity of what shipped -----------------------------------------


def test_every_committed_pool_file_is_a_valid_item_named_after_its_own_id(
    pool_dir: Path, pooled_games: list[str]
) -> None:
    for game_id in pooled_games:
        game_dir = pool_dir / game_id
        assert game_dir.is_dir(), f"{game_id} has no committed pool"
        for path in sorted(game_dir.glob("*.json")):
            if path.name == generate_infinite.INDEX_NAME:
                continue
            item = PoolItem.model_validate_json(path.read_text(encoding="utf-8"))
            assert item.id == path.stem
            assert item.gameId == game_id
            assert daily.answer_words(item.payload), f"{path.stem} asks for no word"


def test_every_index_lists_exactly_the_boards_beside_it(
    pool_dir: Path, pooled_games: list[str]
) -> None:
    for game_id in pooled_games:
        game_dir = pool_dir / game_id
        index = PoolIndex.model_validate_json(
            (game_dir / generate_infinite.INDEX_NAME).read_text(encoding="utf-8")
        )
        on_disk = sorted(
            path.stem
            for path in game_dir.glob("*.json")
            if path.name != generate_infinite.INDEX_NAME
        )
        assert [entry.id for entry in index.items] == on_disk
        for entry in index.items:
            item = PoolItem.model_validate_json(
                (game_dir / f"{entry.id}.json").read_text(encoding="utf-8")
            )
            assert item.difficulty == entry.difficulty


def test_the_committed_pool_holds_every_band_the_generator_registers(
    generator: DailyGenerator, pool_dir: Path, pooled_games: list[str]
) -> None:
    specs = {spec.gameId: spec for spec in generator.games}
    for game_id in pooled_games:
        index = PoolIndex.model_validate_json(
            (pool_dir / game_id / generate_infinite.INDEX_NAME).read_text(
                encoding="utf-8"
            )
        )
        bands = {entry.difficulty for entry in index.items}
        assert bands == {band.id for band in specs[game_id].difficulties}
        for band in specs[game_id].difficulties:
            held = sum(1 for entry in index.items if entry.difficulty == band.id)
            assert 0 < held <= generator.poolPerBand


# --- 4. no word twice inside one Game's pool -------------------------------


def test_no_word_is_asked_for_twice_inside_one_committed_pool(
    pool_dir: Path, pooled_games: list[str]
) -> None:
    for game_id in pooled_games:
        seen: set[str] = set()
        for path in sorted((pool_dir / game_id).glob("*.json")):
            if path.name == generate_infinite.INDEX_NAME:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))["payload"]
            for word in daily.answer_words(payload):
                assert word not in seen, f"{game_id} asks for {word!r} twice"
                seen.add(word)


def test_the_pool_ledger_is_per_game_not_shared(
    pool_dir: Path, pooled_games: list[str]
) -> None:
    """Two Games MAY hold the same word - that is two puzzles, not a repeat.

    Pinned rather than merely tolerated, because the alternative design (one
    ledger across the whole pool) would silently shrink every later Game's pool
    and nothing else in the suite would notice.
    """

    def words_of(game_id: str) -> set[str]:
        found: set[str] = set()
        for path in (pool_dir / game_id).glob("*.json"):
            if path.name == generate_infinite.INDEX_NAME:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))["payload"]
            found.update(daily.answer_words(payload))
        return found

    first, second = pooled_games[0], pooled_games[1]
    assert words_of(first) & words_of(second)


# --- 5. the ceiling is a ceiling ------------------------------------------


def test_a_band_that_runs_out_stops_early_rather_than_repeating(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """A ceiling no bucket can reach yields fewer boards, never a duplicate.

    The word-ladder's hard band is the real case - its reachability graph holds
    only so many four-rung climbs - so an unreachable ceiling is asked for here
    and the pool is expected to be short and still clean.
    """
    items = infinite.build_pool(
        "word-ladder", app_config, generator, wordlists, 10_000
    )
    per_band: dict[str, int] = {}
    for item in items:
        per_band[item.difficulty] = per_band.get(item.difficulty, 0) + 1
    assert min(per_band.values()) < 10_000
    words = [word for item in items for word in daily.answer_words(item.payload)]
    assert len(set(words)) == len(words)


def test_a_zero_ceiling_bakes_no_pool_at_all(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    assert infinite.build_pool("wordle", app_config, generator, wordlists, 0) == []


def test_an_unregistered_game_is_a_loud_failure(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    with pytest.raises(ValueError, match="no generator"):
        infinite.build_pool("sudoku", app_config, generator, wordlists, 1)


def test_the_pool_is_baked_for_the_dailys_own_ring(
    app_config: AppConfig, pooled_games: list[str]
) -> None:
    # One roster, not two: a Game the Daily deals is a Game the stream deals.
    assert pooled_games == list(app_config.daily.games)


def test_every_committed_pool_file_obeys_the_repo_encoding_rules(
    pool_dir: Path, pooled_games: list[str]
) -> None:
    """The five properties `test_encoding.py` asserts, over the whole pool.

    Checked in ONE test rather than by adding the pool to that module's glob
    list, because it parametrises five tests per file and the pool is 1,771 of
    them - nine thousand test ids to prove a property of one writer. The claim
    is identical; only the reporting granularity differs.
    """
    checked = 0
    for game_id in pooled_games:
        for path in sorted((pool_dir / game_id).glob("*.json")):
            rel = path.relative_to(pool_dir).as_posix()
            raw = path.read_bytes()
            assert not raw.startswith(b"\xef\xbb\xbf"), f"{rel} starts with a BOM"
            assert b"\r" not in raw, f"{rel} contains a carriage return"
            assert raw.endswith(b"\n") and not raw.endswith(b"\n\n"), (
                f"{rel} does not end in exactly one newline"
            )
            text = raw.decode("utf-8")
            assert unicodedata.normalize("NFC", text) == text, f"{rel} is not NFC"
            assert not any(ord(char) > 0xFFFF for char in text), f"{rel} is astral"
            assert "\\u0b" not in text, f"{rel} escapes Tamil as \\uXXXX"
            checked += 1
    assert checked > 1_000, f"only {checked} pool files were checked - has a path moved?"
