"""Bake the Infinite Mode's pool for every Game the Daily deals.

    python -m yen_tamizh_backend.scripts.generate_infinite [--game <id>]

Writes ``frontend/public/pool/<gameId>/<NNNNN>.json`` - one puzzle per file - and
``frontend/public/pool/<gameId>/index.json`` beside them. The one-file-per-puzzle
shape is what makes the stream lazy: the Mode fetches the index once and then one
board at a time, so an endless mode costs a phone a few hundred bytes a puzzle
rather than the whole pool up front (Holy Law #2).

Re-running is idempotent by construction: a pool is seeded by its Game's name and
drawn from the committed wordlists, so the same wordlists always produce the same
bytes and the same ids. That is also the hand-edit gate - a board edited by hand
is reverted by the next run.

Like a Journey and unlike the bank, a pool has no re-bake guard. A day is a
promise about a DATE that a player may be part-way through; a pool is content,
and the run that changes it is the run that meant to. A player's seen-list may
then name an id whose board has moved, which costs them at worst one puzzle they
have met before - not a broken save.

A pool directory is REBUILT rather than merged: files left behind by a larger
previous pool would still be served, still be indexed by nothing, and still be
committed, so the writer clears the Game's directory first.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TextIO

from yen_tamizh_backend.contracts.app_config import AppConfig
from yen_tamizh_backend.contracts.daily_generator import DailyGenerator
from yen_tamizh_backend.contracts.game_wordlist import GameWordlist
from yen_tamizh_backend.contracts.pool_index import PoolItem
from yen_tamizh_backend.generate import infinite
from yen_tamizh_backend.scripts.generate_today import load_wordlists
from yen_tamizh_backend.wordsmith.artifact import render_document, write_artifact

INDEX_NAME = "index.json"


def _repo_root() -> Path:
    # generate_infinite.py -> scripts -> yen_tamizh_backend -> backend -> <root>
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class PoolBake:
    """What one Game's bake produced: where it landed and how big it is."""

    gameId: str
    rel_dir: str
    items: int
    bytes: int
    indexBytes: int
    byBand: dict[str, int]


def _emit(stream: TextIO, name: str, data: dict[str, Any]) -> None:
    """One pipeline event as a JSON line - a build-time log, never a network call."""
    line = json.dumps(
        {"src": "generate_infinite", "name": name, "level": "info", "data": data},
        ensure_ascii=False,
        sort_keys=True,
    )
    print(line, file=stream)


def render_item(item: PoolItem) -> str:
    """The committed bytes of one pooled puzzle: one compact line.

    Compact rather than indented because a pool is thousands of machine-written
    files that are never reviewed as a diff and never hand-edited - the bake IS
    the review - so every byte of whitespace would be paid for by the repo, by
    the deploy, and by the player who fetches it.
    """
    return json.dumps(item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n"


def write_pool(
    repo_root: Path, pool_dir: Path, game_id: str, items: list[PoolItem]
) -> PoolBake:
    """Write one Game's whole pool and its index; return what it cost."""
    game_dir = pool_dir / game_id
    if game_dir.exists():
        shutil.rmtree(game_dir)
    total = 0
    by_band: dict[str, int] = {}
    for item in items:
        text = render_item(item)
        write_artifact(game_dir / f"{item.id}.json", text)
        total += len(text.encode("utf-8"))
        by_band[item.difficulty] = by_band.get(item.difficulty, 0) + 1
    index = infinite.build_index(game_id, items)
    index_text = render_document(index.model_dump(mode="json", exclude_none=True), "items")
    write_artifact(game_dir / INDEX_NAME, index_text)
    return PoolBake(
        gameId=game_id,
        # Paths leaving the process are relative + POSIX (CLAUDE.md section 2).
        rel_dir=game_dir.resolve().relative_to(repo_root).as_posix(),
        items=len(items),
        bytes=total,
        indexBytes=len(index_text.encode("utf-8")),
        byBand=by_band,
    )


def generate(
    repo_root: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
    only: str | None = None,
) -> list[PoolBake]:
    """Bake a pool for every Game in the Daily's ring (or just the named one)."""
    games = infinite.pool_games(app_config)
    if only is not None:
        if only not in games:
            raise ValueError(f"no pool is baked for {only!r}: {games}")
        games = [only]
    pool_dir = repo_root / generator.poolDir
    return [
        write_pool(
            repo_root,
            pool_dir,
            game_id,
            infinite.build_pool(game_id, app_config, generator, wordlists),
        )
        for game_id in games
    ]


def main(argv: list[str] | None = None) -> None:
    root = _repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--game",
        default=None,
        help="bake only this Game's pool (default: every Game in daily.games)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "config" / "app-config.json",
        help="the app config naming the Games that have pools",
    )
    parser.add_argument(
        "--generator",
        type=Path,
        default=root / "config" / "daily-generator.json",
        help="the generator registry naming each Game's wordlist, bands and pool size",
    )
    args = parser.parse_args(argv)

    app_config = AppConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    generator = DailyGenerator.model_validate_json(
        args.generator.read_text(encoding="utf-8")
    )
    wordlists = load_wordlists(generator, root)

    baked = generate(root, app_config, generator, wordlists, args.game)
    for bake in baked:
        _emit(
            sys.stdout,
            "pool.generated",
            {
                "gameId": bake.gameId,
                "outputPath": bake.rel_dir,
                "items": bake.items,
                "bytes": bake.bytes,
                "indexBytes": bake.indexBytes,
                "byBand": bake.byBand,
            },
        )
    _emit(
        sys.stdout,
        "pool.updated",
        {
            "poolDir": generator.poolDir,
            "games": [bake.gameId for bake in baked],
            "items": sum(bake.items for bake in baked),
            "bytes": sum(bake.bytes + bake.indexBytes for bake in baked),
        },
    )


if __name__ == "__main__":
    main()
