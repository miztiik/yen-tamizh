"""Bake every authored Journey under ``datasets/journeys/`` into a playable path.

    python -m yen_tamizh_backend.scripts.build_journeys [--journey <id>]

Each file is read for its AUTHORED half - the path's id, title, palette, and the
ordered nodes with their Game, band and unlock rule - and rewritten with a freshly
built board on every node. So authoring a new path is dropping a file that names
its nodes and running this once; nothing about the Mode, the map, or the schema
moves.

Re-running is idempotent by construction: a node's board is seeded by
``<journeyId>|<nodeId>`` and drawn from the committed wordlists, so the same file
plus the same wordlists always produce the same bytes. That is also the hand-edit
gate - a payload edited by hand is reverted by the next run, and the test that
re-bakes the committed path into a temp tree is what proves it.

Unlike the bank, a Journey has no re-bake guard. A day is a promise about a
DATE that a player may be part-way through; a path is content, and the run that
changes it is the run that meant to.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, TextIO

from yen_tamizh_backend.contracts.app_config import AppConfig
from yen_tamizh_backend.contracts.daily_generator import DailyGenerator
from yen_tamizh_backend.contracts.game_wordlist import GameWordlist
from yen_tamizh_backend.contracts.journey import Journey
from yen_tamizh_backend.generate import journey as journey_build
from yen_tamizh_backend.wordsmith.artifact import render_document, write_artifact

JOURNEYS_DIR = "datasets/journeys"


def _repo_root() -> Path:
    # build_journeys.py -> scripts -> yen_tamizh_backend -> backend -> <root>
    return Path(__file__).resolve().parents[3]


def _emit(stream: TextIO, name: str, data: dict[str, Any]) -> None:
    """One pipeline event as a JSON line - a build-time log, never a network call."""
    line = json.dumps(
        {"src": "build_journeys", "name": name, "level": "info", "data": data},
        ensure_ascii=False,
        sort_keys=True,
    )
    print(line, file=stream)


def journey_paths(journeys_dir: Path, only: str | None = None) -> list[Path]:
    """Every authored journey file, oldest-first by name; one when ``only`` names it."""
    paths = sorted(journeys_dir.glob("*.json"))
    if only is None:
        return paths
    wanted = [path for path in paths if path.stem == only]
    if not wanted:
        raise ValueError(f"no journey named {only!r} under {journeys_dir.name}")
    return wanted


def build_one(
    path: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
) -> Journey:
    """Read one authored path, build every node's board, and return the Journey.

    The file's stem must be the Journey's own id: the id is what the Mode asks
    for and the stem is what it fetches, so a disagreement would be a path that
    validates and cannot be opened.
    """
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    plan = journey_build.read_plan(document)
    if plan.id != path.stem:
        raise ValueError(f"{path.name} declares id {plan.id!r}; the file stem must match")
    return journey_build.build_journey(plan, app_config, generator, wordlists)


def render(journey: Journey) -> str:
    """The committed bytes of one Journey: pretty header, one node per line."""
    return render_document(journey.model_dump(mode="json", exclude_none=True), "nodes")


def build_all(
    repo_root: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
    only: str | None = None,
) -> list[tuple[Path, Journey]]:
    """Rebuild every authored path in place; return what was written."""
    written: list[tuple[Path, Journey]] = []
    for path in journey_paths(repo_root / JOURNEYS_DIR, only):
        built = build_one(path, app_config, generator, wordlists)
        write_artifact(path, render(built))
        written.append((path, built))
    return written


def main(argv: list[str] | None = None) -> None:
    root = _repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--journey",
        default=None,
        help="rebuild only the path with this id (default: every one)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "config" / "app-config.json",
        help="the app config holding the hint allowances a node may bake",
    )
    parser.add_argument(
        "--generator",
        type=Path,
        default=root / "config" / "daily-generator.json",
        help="the generator registry naming each Game's wordlist and bands",
    )
    args = parser.parse_args(argv)

    app_config = AppConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    generator = DailyGenerator.model_validate_json(
        args.generator.read_text(encoding="utf-8")
    )
    paths = {
        spec.wordlist: GameWordlist.model_validate_json(
            (root / spec.wordlist).read_text(encoding="utf-8")
        )
        for spec in generator.games
    }

    for path, built in build_all(root, app_config, generator, paths, args.journey):
        _emit(
            sys.stdout,
            "journey.built",
            {
                # Paths leaving the process are relative + POSIX (CLAUDE.md section 2).
                "outputPath": path.resolve().relative_to(root).as_posix(),
                "journeyId": built.id,
                "nodes": len(built.nodes),
                "words": len(journey_build.answer_words(built)),
            },
        )


if __name__ == "__main__":
    main()
