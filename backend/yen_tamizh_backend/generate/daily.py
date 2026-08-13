"""Bake one day of the puzzle bank, and the index over every baked day.

The rules this module enforces:

- **A day is a pure function of its date.** Selection is a seeded shuffle over a
  stable-sorted candidate list, so re-running any date reproduces it byte for
  byte - the Row 13 Oracle. Nothing here reads a clock; the caller supplies the
  dates.
- **A word does not come back.** Words already used on OTHER days present in the
  bank are skipped, so a player does not meet the same scramble twice. The
  target date's own file is ignored while collecting them, which is exactly what
  makes a re-run idempotent instead of self-poisoning.
- **The mix is config, not code.** How many items a day holds and which Games
  fill them come from ``config/app-config.json`` (``daily.playlistLength`` and
  ``daily.mix``); how a word becomes a puzzle comes from
  ``config/daily-generator.json``. A mismatch between the two is an error, not a
  silently short day.

The bank lives under ``frontend/public/`` so the game reads it same-origin from
its own bundle and it works offline (Holy Law #1).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from yen_tamizh_backend.contracts.app_config import AppConfig
from yen_tamizh_backend.contracts.bank_index import BankDay, BankIndex
from yen_tamizh_backend.contracts.base import ChangelogEntry
from yen_tamizh_backend.contracts.daily_generator import DailyGenerator, GameGeneration
from yen_tamizh_backend.contracts.game_wordlist import GameWord, GameWordlist
from yen_tamizh_backend.contracts.puzzle_file import PuzzleFile, PuzzleItem
from yen_tamizh_backend.generate import anagram
from yen_tamizh_backend.generate.seed import seeded_shuffle

_PUZZLE_FILE_VERSION = "2026-08-13"
_PUZZLE_FILE_CHANGELOG = [
    ChangelogEntry(
        version=_PUZZLE_FILE_VERSION,
        change="Initial baked daily playlist.",
        why="Row 13 - the first committed day of the puzzle bank.",
    )
]

_BANK_INDEX_VERSION = "2026-08-13"
_BANK_INDEX_CHANGELOG = [
    ChangelogEntry(
        version=_BANK_INDEX_VERSION,
        change="Initial bank index over the baked days.",
        why="Row 13 - the game asks the index which days exist before opening one.",
    )
]

# The payload keys a puzzle-file item never repeats: the day file carries its own
# schema stamp, so echoing one inside every item is noise the player downloads.
_STAMP_KEYS = ("version", "changelog")


@dataclass(frozen=True)
class GeneratedDay:
    """One baked day: where it landed, and what it holds."""

    date: str
    path: Path
    rel_path: str
    puzzle_file: PuzzleFile
    words: tuple[str, ...]


def day_path(bank_dir: Path, day: str) -> Path:
    """Where one day's puzzle file lives: ``<bank>/<YYYY>/<YYYY-MM-DD>.json``."""
    return bank_dir / day[:4] / f"{day}.json"


def dates_from(start: date, days_ahead: int) -> list[date]:
    """The run's dates: the start day plus the configured look-ahead."""
    return [start + timedelta(days=offset) for offset in range(days_ahead + 1)]


def baked_days(bank_dir: Path) -> list[str]:
    """Every day already baked into the bank, oldest first."""
    if not bank_dir.is_dir():
        return []
    return sorted(path.stem for path in bank_dir.glob("*/*.json"))


def words_used_before(bank_dir: Path, exclude_day: str) -> set[str]:
    """Every answer word the bank has already served on some OTHER day.

    Excluding the target day is what makes a re-run idempotent: a day must not
    treat its own previous output as a reason to pick different words.
    """
    used: set[str] = set()
    for day in baked_days(bank_dir):
        if day == exclude_day:
            continue
        payload = json.loads(day_path(bank_dir, day).read_text(encoding="utf-8"))
        for item in payload.get("items", []):
            word = item.get("payload", {}).get("word")
            if isinstance(word, str):
                used.add(word)
    return used


def pick_words(
    candidates: Sequence[GameWord],
    day: str,
    game_id: str,
    count: int,
    used: Iterable[str],
) -> list[GameWord]:
    """Choose one day's words: seeded by the date, skipping words already served.

    If the bank has served so much of the wordlist that fewer than ``count``
    fresh words remain, the day is filled from the same seeded order anyway
    rather than shipping short - a repeat is a much smaller failure than a
    playlist that does not add up.
    """
    if not candidates:
        raise ValueError(f"no candidate words for {game_id!r} on {day}")
    seen = set(used)
    order = seeded_shuffle(candidates, f"{day}|{game_id}")
    fresh = [row for row in order if row.word not in seen]
    chosen = fresh[:count]
    if len(chosen) < count:
        chosen += [row for row in order if row not in chosen][: count - len(chosen)]
    return chosen


def build_item(
    row: GameWord, spec: GameGeneration, day: str, hint_limit: int
) -> PuzzleItem:
    """One playlist entry: the Game's validated payload plus its framing.

    The payload drops the schema stamp the model carries: the day file has its
    own ``version`` + ``changelog``, and repeating one inside every item would
    be bytes the player downloads to learn nothing (Carmack). Building the model
    first is still what proves the payload obeys ``anagram-puzzle``.
    """
    puzzle = anagram.build_puzzle(row, spec, f"{day}|{row.word}", hint_limit)
    payload = puzzle.model_dump(mode="json", exclude_none=True)
    for key in _STAMP_KEYS:
        payload.pop(key, None)
    return PuzzleItem(
        gameId=spec.gameId,
        packId=spec.packId,
        difficulty=anagram.difficulty_of(row, spec),
        payload=payload,
    )


def build_day(
    day: str,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
    used: Iterable[str],
) -> PuzzleFile:
    """Build one day's playlist from the config'd mix. Pure; no I/O, no clock."""
    mix = app_config.daily.mix
    total = sum(mix.values())
    if total != app_config.daily.playlistLength:
        raise ValueError(
            f"daily.mix sums to {total} but daily.playlistLength is "
            f"{app_config.daily.playlistLength}"
        )
    specs = {spec.gameId: spec for spec in generator.games}
    seen = set(used)
    items: list[PuzzleItem] = []
    # Sorted so the playlist's order depends on the config, never on dict order.
    for game_id, count in sorted(mix.items()):
        spec = specs.get(game_id)
        if spec is None:
            raise ValueError(f"daily.mix names {game_id!r}, which has no generator")
        # How much help a day may ship is the app config's call, not the
        # generator's: the same switch the shell reads decides what gets baked.
        hint_limit = (
            app_config.hints.perGame.get(game_id, 0) if app_config.hints.enabled else 0
        )
        wordlist = wordlists[game_id]
        for row in pick_words(wordlist.words, day, game_id, count, seen):
            seen.add(row.word)
            items.append(build_item(row, spec, day, hint_limit))
    return PuzzleFile(
        version=_PUZZLE_FILE_VERSION,
        changelog=_PUZZLE_FILE_CHANGELOG,
        date=day,
        items=items,
    )


def build_index(bank_dir: Path) -> BankIndex:
    """Re-read the bank from disk and index it, so the index cannot drift."""
    days = [
        BankDay(
            date=day,
            itemCount=len(
                json.loads(day_path(bank_dir, day).read_text(encoding="utf-8"))["items"]
            ),
        )
        for day in baked_days(bank_dir)
    ]
    return BankIndex(
        version=_BANK_INDEX_VERSION, changelog=_BANK_INDEX_CHANGELOG, days=days
    )
