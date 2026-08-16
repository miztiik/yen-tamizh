"""Bake today's puzzles (and the configured look-ahead) into the bank.

    python -m yen_tamizh_backend.scripts.generate_today [YYYY-MM-DD] [--rebake]

The date defaults to today in UTC - the calendar the daily cron runs on. Pass a
date to back-fill one.

A day already in the bank is PUBLISHED and is left alone. Baking is a pure
function of the date AND of the wordlist it drew from, so the moment that
wordlist changes an unguarded re-run would hand a player mid-session a different
puzzle for a day they had already started. ``--rebake`` is the deliberate
override for the case where changing published days is the point. The index is
rebuilt from what is on disk on every run either way, so it can never drift from
the days it lists.

This is the entry point, so it owns the impure edges: the clock, the filesystem,
and the stdout event log. Every decision about WHAT a day contains lives in
``yen_tamizh_backend.generate``.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from yen_tamizh_backend.contracts.app_config import AppConfig
from yen_tamizh_backend.contracts.daily_generator import DailyGenerator
from yen_tamizh_backend.contracts.game_wordlist import GameWordlist
from yen_tamizh_backend.wordsmith.artifact import render_document, write_artifact
from yen_tamizh_backend.generate import daily


def _repo_root() -> Path:
    # generate_today.py -> scripts -> yen_tamizh_backend -> backend -> <root>
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class BakeRun:
    """What one bake did: the days it wrote, and the published days it left alone."""

    written: list[daily.GeneratedDay]
    skipped: list[str]


def _emit(stream: TextIO, name: str, data: dict[str, Any]) -> None:
    """One pipeline event as a JSON line (telemetry.md's catalog, no sink).

    A build-time event is a line on stdout, not a network call: there is no
    telemetry service in this project, and CI logs are the only reader.
    """
    line = json.dumps(
        {"src": "generate_today", "name": name, "level": "info", "data": data},
        ensure_ascii=False,
        sort_keys=True,
    )
    print(line, file=stream)


def load_wordlists(generator: DailyGenerator, repo_root: Path) -> dict[str, GameWordlist]:
    """Load each Game's derived wordlist - the engine's only word input."""
    return {
        spec.gameId: GameWordlist.model_validate_json(
            (repo_root / spec.wordlist).read_text(encoding="utf-8")
        )
        for spec in generator.games
    }


def generate(
    start: date,
    repo_root: Path,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
    rebake: bool = False,
) -> BakeRun:
    """Bake every unpublished date in the run, oldest first, and rewrite the index.

    A date whose file already exists is skipped unless ``rebake`` is set: it has
    shipped, and a player may be part-way through it. The index is rebuilt from
    disk regardless, so skipping a day cannot leave it unlisted.
    """
    bank_dir = repo_root / generator.bankDir
    written: list[daily.GeneratedDay] = []
    skipped: list[str] = []
    for day_date in daily.dates_from(start, generator.daysAhead):
        day = day_date.isoformat()
        path = daily.day_path(bank_dir, day)
        if path.exists() and not rebake:
            skipped.append(day)
            continue
        used = daily.words_used_before(bank_dir, day)
        puzzle_file = daily.build_day(day, app_config, generator, wordlists, used)
        write_artifact(
            path, render_document(puzzle_file.model_dump(mode="json", exclude_none=True), "items")
        )
        written.append(
            daily.GeneratedDay(
                date=day,
                path=path,
                # Paths leaving the process are relative + POSIX (CLAUDE.md section 2).
                rel_path=path.resolve().relative_to(repo_root).as_posix(),
                puzzle_file=puzzle_file,
                words=tuple(str(item.payload["word"]) for item in puzzle_file.items),
            )
        )

    index = daily.build_index(bank_dir)
    write_artifact(
        bank_dir / "index.json",
        render_document(index.model_dump(mode="json", exclude_none=True), "days"),
    )
    return BakeRun(written=written, skipped=skipped)


def main(argv: list[str] | None = None) -> None:
    root = _repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "day",
        nargs="?",
        default=None,
        help="the first date to bake (YYYY-MM-DD); defaults to today in UTC",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "config" / "app-config.json",
        help="the app config holding daily.playlistLength and daily.mix",
    )
    parser.add_argument(
        "--generator",
        type=Path,
        default=root / "config" / "daily-generator.json",
        help="the daily generator registry to read",
    )
    parser.add_argument(
        "--rebake",
        action="store_true",
        help="rewrite days already in the bank (they have shipped; see the how-to)",
    )
    args = parser.parse_args(argv)

    start = (
        date.fromisoformat(args.day)
        if args.day
        else datetime.now(timezone.utc).date()
    )
    app_config = AppConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
    generator = DailyGenerator.model_validate_json(
        args.generator.read_text(encoding="utf-8")
    )
    wordlists = load_wordlists(generator, root)

    run = generate(start, root, app_config, generator, wordlists, rebake=args.rebake)
    for day in run.written:
        for item in day.puzzle_file.items:
            _emit(
                sys.stdout,
                "puzzle.generated",
                {"date": day.date, "gameId": item.gameId, "outputPath": day.rel_path},
            )
    bank_rel = (root / generator.bankDir).resolve().relative_to(root).as_posix()
    _emit(
        sys.stdout,
        "bank.updated",
        {
            "bankDir": bank_rel,
            "days": len(daily.baked_days(root / generator.bankDir)),
            "generated": [day.date for day in run.written],
            "skipped": run.skipped,
        },
    )


if __name__ == "__main__":
    main()
