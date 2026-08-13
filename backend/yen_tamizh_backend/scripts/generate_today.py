"""Bake today's puzzles (and the configured look-ahead) into the bank.

    python -m yen_tamizh_backend.scripts.generate_today [YYYY-MM-DD]

The date defaults to today in UTC - the calendar the daily cron runs on. Pass a
date to re-bake or back-fill one; a re-run for a date already in the bank writes
the same bytes, so the working tree stays clean unless something really changed
(the Row 13 determinism Oracle).

This is the entry point, so it owns the impure edges: the clock, the filesystem,
and the stdout event log. Every decision about WHAT a day contains lives in
``yen_tamizh_backend.generate``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, TextIO

from yen_tamizh_backend.contracts.app_config import AppConfig
from yen_tamizh_backend.contracts.daily_generator import DailyGenerator
from yen_tamizh_backend.contracts.game_wordlist import GameWordlist
from yen_tamizh_backend.corpus.artifact import render_document, write_artifact
from yen_tamizh_backend.generate import daily


def _repo_root() -> Path:
    # generate_today.py -> scripts -> yen_tamizh_backend -> backend -> <root>
    return Path(__file__).resolve().parents[3]


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
) -> list[daily.GeneratedDay]:
    """Bake every date in the run, oldest first, and rewrite the bank index."""
    bank_dir = repo_root / generator.bankDir
    written: list[daily.GeneratedDay] = []
    for day_date in daily.dates_from(start, generator.daysAhead):
        day = day_date.isoformat()
        used = daily.words_used_before(bank_dir, day)
        puzzle_file = daily.build_day(day, app_config, generator, wordlists, used)
        path = daily.day_path(bank_dir, day)
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
    return written


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

    written = generate(start, root, app_config, generator, wordlists)
    for day in written:
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
            "generated": [day.date for day in written],
        },
    )


if __name__ == "__main__":
    main()
