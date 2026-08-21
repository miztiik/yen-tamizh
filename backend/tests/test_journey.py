"""Tests for the Row 17 Journey layer: an authored path -> a playable path.

Real config, the real committed wordlists, and the real committed Journey - no
mocks (Holy Law #7). Tamil is written with ``\\uXXXX`` escapes so this source
stays ASCII (CLAUDE.md section 5).

Four things are proven:

1. **The Oracle - determinism and the hand-edit gate.** Re-baking the committed
   path into a temp tree reproduces its bytes exactly, so a payload edited by
   hand is reverted by the next run and a Journey is reproducible from its file
   alone. A DATE is deliberately absent from the seed: a curated path that drew
   different words every time it was rebuilt would not be curated.
2. **The contract.** The committed path validates as a ``Journey``; a path with
   no entrance, a repeated node id, or an unlock rule nothing implements is
   refused.
3. **Buildability.** Every node names a Game the generator registers and a band
   that Game registers, and every one of them really produced a board - which is
   what the committed file is.
4. **The seams.** The ledger is journey-local (no word twice in one path), the
   path draws only from ordinary wordlists (never a themed set), the file stem
   is the Journey's own id, and the app config's ``defaultJourney`` names a
   Journey that exists.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from yen_tamizh_backend.contracts.app_config import AppConfig
from yen_tamizh_backend.contracts.daily_generator import DailyGenerator
from yen_tamizh_backend.contracts.game_wordlist import GameWordlist
from yen_tamizh_backend.contracts.journey import Journey
from yen_tamizh_backend.generate import daily
from yen_tamizh_backend.generate import journey as journey_build
from yen_tamizh_backend.scripts import build_journeys

_REPO_ROOT = Path(__file__).resolve().parents[2]
_APP_CONFIG = _REPO_ROOT / "config" / "app-config.json"
_GENERATOR = _REPO_ROOT / "config" / "daily-generator.json"
_JOURNEYS = _REPO_ROOT / "datasets" / "journeys"


@pytest.fixture(scope="module")
def app_config() -> AppConfig:
    return AppConfig.model_validate_json(_APP_CONFIG.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def generator() -> DailyGenerator:
    return DailyGenerator.model_validate_json(_GENERATOR.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def wordlists(generator: DailyGenerator) -> dict[str, GameWordlist]:
    """Every ORDINARY served set, which is all a Journey may draw from."""
    return {
        spec.wordlist: GameWordlist.model_validate_json(
            (_REPO_ROOT / spec.wordlist).read_text(encoding="utf-8")
        )
        for spec in generator.games
    }


def _committed_paths() -> list[Path]:
    return sorted(_JOURNEYS.glob("*.json"))


def _committed() -> list[Journey]:
    return [
        Journey.model_validate_json(path.read_text(encoding="utf-8"))
        for path in _committed_paths()
    ]


# --------------------------------------------------------------------------
# 1. The Oracle - determinism and the hand-edit gate
# --------------------------------------------------------------------------


def test_at_least_one_journey_is_committed() -> None:
    # Guards the module: a moved directory would turn every test below into a
    # silent pass over an empty list.
    assert _committed_paths(), f"no journey files under {_JOURNEYS.name}"


def test_rebaking_the_committed_journey_reproduces_its_bytes(
    tmp_path: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """THE ORACLE for the build side: same file + same wordlists -> same bytes.

    Run into a temp tree rather than in place, so a failing assertion leaves the
    committed path untouched. This is also the hand-edit gate: a payload someone
    corrected by hand does not survive the next run, which is what keeps the
    generator the only author of a board.
    """
    staged = tmp_path / build_journeys.JOURNEYS_DIR
    staged.mkdir(parents=True)
    for path in _committed_paths():
        (staged / path.name).write_bytes(path.read_bytes())

    written = build_journeys.build_all(tmp_path, app_config, generator, wordlists)
    assert len(written) == len(_committed_paths())
    for path in _committed_paths():
        assert (staged / path.name).read_bytes() == path.read_bytes(), path.name


def test_two_builds_of_one_plan_agree(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    plan = journey_build.read_plan(
        json.loads(_committed_paths()[0].read_text(encoding="utf-8"))
    )
    first = journey_build.build_journey(plan, app_config, generator, wordlists)
    second = journey_build.build_journey(plan, app_config, generator, wordlists)
    assert build_journeys.render(first) == build_journeys.render(second)


def test_the_seed_is_the_node_address_and_carries_no_date(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    """Renaming a node changes its board; nothing else does.

    The claim the Oracle above cannot make on its own: byte-equality would also
    hold if every node were dealt the same word regardless of its id.
    """
    plan = journey_build.read_plan(
        json.loads(_committed_paths()[0].read_text(encoding="utf-8"))
    )
    renamed = journey_build.JourneyPlan(
        id=plan.id,
        titleTa=plan.titleTa,
        theme=plan.theme,
        nodes=(
            journey_build.NodeSpec(
                id="a-different-address",
                gameId=plan.nodes[0].gameId,
                difficulty=plan.nodes[0].difficulty,
                unlockRule=plan.nodes[0].unlockRule,
            ),
        ),
    )
    original = journey_build.build_journey(plan, app_config, generator, wordlists)
    moved = journey_build.build_journey(renamed, app_config, generator, wordlists)
    assert original.nodes[0].payload != moved.nodes[0].payload


# --------------------------------------------------------------------------
# 2. The contract
# --------------------------------------------------------------------------


def test_the_committed_journeys_validate() -> None:
    for journey in _committed():
        assert journey.nodes, journey.id


def test_a_path_with_no_entrance_is_refused() -> None:
    document = json.loads(_committed_paths()[0].read_text(encoding="utf-8"))
    document["nodes"][0]["unlockRule"] = "previous-complete"
    with pytest.raises(ValidationError, match="first node must be 'open'"):
        Journey.model_validate(document)


def test_a_repeated_node_id_is_refused() -> None:
    document = json.loads(_committed_paths()[0].read_text(encoding="utf-8"))
    document["nodes"][1]["id"] = document["nodes"][0]["id"]
    with pytest.raises(ValidationError, match="repeats a node id"):
        Journey.model_validate(document)


def test_an_unlock_rule_nothing_implements_is_refused() -> None:
    document = json.loads(_committed_paths()[0].read_text(encoding="utf-8"))
    document["nodes"][1]["unlockRule"] = "after-three-stars"
    with pytest.raises(ValidationError):
        Journey.model_validate(document)


def test_a_plan_missing_an_authored_field_fails_loudly() -> None:
    document = json.loads(_committed_paths()[0].read_text(encoding="utf-8"))
    del document["nodes"][0]["difficulty"]
    with pytest.raises(ValueError, match="missing"):
        journey_build.read_plan(document)


# --------------------------------------------------------------------------
# 3. Buildability
# --------------------------------------------------------------------------


def test_every_node_names_a_registered_game_and_band(generator: DailyGenerator) -> None:
    specs = {spec.gameId: spec for spec in generator.games}
    for journey in _committed():
        for node in journey.nodes:
            assert node.gameId in specs, f"{journey.id}/{node.id}"
            assert node.gameId in daily.BUILDERS, f"{journey.id}/{node.id}"
            bands = {band.id for band in specs[node.gameId].difficulties}
            assert node.difficulty in bands, f"{journey.id}/{node.id}"
            assert node.packId == specs[node.gameId].packId


def test_every_node_carries_a_board_that_asks_for_a_word() -> None:
    for journey in _committed():
        for node in journey.nodes:
            assert daily.answer_words(node.payload), f"{journey.id}/{node.id}"


def test_a_node_naming_an_unregistered_game_is_a_loud_failure(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    plan = journey_build.JourneyPlan(
        id="nowhere",
        titleTa="\u0baa\u0baf\u0ba3\u0bae\u0bcd",
        theme="light",
        nodes=(
            journey_build.NodeSpec(
                id="only-node",
                gameId="sudoku",
                difficulty="easy",
                unlockRule="open",
            ),
        ),
    )
    with pytest.raises(ValueError, match="has no generator"):
        journey_build.build_journey(plan, app_config, generator, wordlists)


def test_a_node_asking_for_an_unregistered_band_is_a_loud_failure(
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    plan = journey_build.JourneyPlan(
        id="nowhere",
        titleTa="\u0baa\u0baf\u0ba3\u0bae\u0bcd",
        theme="light",
        nodes=(
            journey_build.NodeSpec(
                id="only-node",
                gameId="anagram",
                difficulty="impossible",
                unlockRule="open",
            ),
        ),
    )
    with pytest.raises(ValueError, match="does not register"):
        journey_build.build_journey(plan, app_config, generator, wordlists)


# --------------------------------------------------------------------------
# 4. The seams
# --------------------------------------------------------------------------


def test_no_word_is_asked_for_twice_inside_one_path() -> None:
    for journey in _committed():
        words = journey_build.answer_words(journey)
        repeated = [word for word, count in Counter(words).items() if count > 1]
        assert not repeated, f"{journey.id} serves {repeated} more than once"


def test_a_path_draws_only_from_ordinary_wordlists(generator: DailyGenerator) -> None:
    """A theme is the Daily's claim about a day, never a Journey's about a node."""
    themed = {
        theme.wordlist for spec in generator.games for theme in spec.themes
    }
    for path in _committed_paths():
        plan = journey_build.read_plan(json.loads(path.read_text(encoding="utf-8")))
        drawn = set(journey_build.wordlist_paths(plan, generator))
        assert drawn.isdisjoint(themed), f"{plan.id} draws from {drawn & themed}"


def test_the_file_stem_is_the_journeys_own_id() -> None:
    for path in _committed_paths():
        journey = Journey.model_validate_json(path.read_text(encoding="utf-8"))
        assert journey.id == path.stem


def test_a_stem_that_disagrees_with_the_id_is_refused(
    tmp_path: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    source = _committed_paths()[0]
    misnamed = tmp_path / "some-other-name.json"
    misnamed.write_bytes(source.read_bytes())
    with pytest.raises(ValueError, match="file stem must match"):
        build_journeys.build_one(misnamed, app_config, generator, wordlists)


def test_the_configured_default_journey_exists(app_config: AppConfig) -> None:
    ids = {journey.id for journey in _committed()}
    assert app_config.ui.defaultJourney in ids


def test_the_journey_mode_is_only_reachable_when_it_is_enabled(
    app_config: AppConfig,
) -> None:
    # The Mode ships on in the committed config; the Home reads the same list.
    assert "journey" in app_config.ui.enabledModes


def test_building_only_one_named_path_leaves_the_others_alone(
    tmp_path: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> None:
    staged = tmp_path / build_journeys.JOURNEYS_DIR
    staged.mkdir(parents=True)
    for path in _committed_paths():
        (staged / path.name).write_bytes(path.read_bytes())
    decoy = staged / "not-a-real-path.json"
    decoy.write_text("{ not json at all", encoding="utf-8")

    only = _committed_paths()[0].stem
    written = build_journeys.build_all(
        tmp_path, app_config, generator, wordlists, only=only
    )
    assert [built.id for _, built in written] == [only]
    # The decoy is unreadable, so touching it at all would have raised.
    assert decoy.read_text(encoding="utf-8") == "{ not json at all"


def test_asking_for_a_path_that_does_not_exist_is_a_loud_failure(tmp_path: Path) -> None:
    staged = tmp_path / build_journeys.JOURNEYS_DIR
    staged.mkdir(parents=True)
    with pytest.raises(ValueError, match="no journey named"):
        build_journeys.journey_paths(staged, "beginners-ladder")
