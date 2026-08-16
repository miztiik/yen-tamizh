"""Bake one day of the puzzle bank, and the index over every baked day.

The rules this module enforces:

- **A day is a pure function of its date.** Selection is a seeded, frequency-
  stratified draw over a stable-sorted candidate list, so re-running any date
  reproduces it byte for byte - the Row 13 Oracle. Nothing here reads a clock;
  the caller supplies the dates.
- **A day is a curve.** Its slots are dealt round-robin across the configured
  difficulty bands, and the easiest band admits only the most familiar quarter of
  the served set, so a day can never be three words nobody knows.
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
from collections import defaultdict
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
from yen_tamizh_backend.generate.seed import seeded_index, seeded_shuffle

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


def bucket_candidates(
    candidates: Iterable[GameWord], spec: GameGeneration
) -> dict[str, list[GameWord]]:
    """Split a Game's words into its configured difficulty buckets.

    A word no band claims is DROPPED rather than filed under the nearest one.
    The wordlist says what is servable; the bands say what is drawable, and a
    3-ezhuthu word outside the familiar quarters is neither an easy word nor a
    fair hard one.
    """
    buckets: dict[str, list[GameWord]] = {band.id: [] for band in spec.difficulties}
    for row in candidates:
        bucket = anagram.difficulty_of(row, spec)
        if bucket is not None:
            buckets[bucket].append(row)
    return buckets


def stratified_order(rows: Sequence[GameWord], seed_text: str) -> list[GameWord]:
    """Order one bucket so any prefix of it is a proportional frequency sample.

    Each frequency stratum is shuffled on its own and the strata are then
    interleaved, so every window of four picks holds one word from each quarter
    rather than four from whichever quarter happens to be largest. That is the
    whole difference between a stratified draw and a uniform shuffle here: the
    uniform one has the right mix on average and still hands out three unfamiliar
    words on a bad day, which is the day a player stops.

    Which stratum LEADS is seeded by the day, so a bucket's first pick is not
    permanently its most common word.
    """
    by_stratum: dict[int, list[GameWord]] = defaultdict(list)
    for row in rows:
        by_stratum[row.frequencyStratum].append(row)
    strata = sorted(by_stratum)
    shuffled = {
        stratum: seeded_shuffle(by_stratum[stratum], f"{seed_text}|{stratum}")
        for stratum in strata
    }
    start = seeded_index(len(strata), seed_text)

    order: list[GameWord] = []
    depth = 0
    while len(order) < len(rows):
        for offset in range(len(strata)):
            group = shuffled[strata[(start + offset) % len(strata)]]
            if depth < len(group):
                order.append(group[depth])
        depth += 1
    return order


def pick_words(
    candidates: Sequence[GameWord],
    spec: GameGeneration,
    day: str,
    count: int,
    used: Iterable[str],
) -> list[tuple[GameWord, str]]:
    """Choose one day's words and their difficulties, skipping words already served.

    Slots are dealt round-robin across the configured bands, so a three-item day
    is a curve rather than three rolls of the same dice - and because the easiest
    band admits only the most familiar quarter, a day can never be three
    unfamiliar words.

    Within a band the draw is stratified (see ``stratified_order``), seeded by
    the date so the day stays a pure function of its date. If the bank has served
    a band's whole bucket, the day repeats from that same order rather than
    shipping short: a repeat is a much smaller failure than a playlist that does
    not add up.
    """
    if not candidates:
        raise ValueError(f"no candidate words for {spec.gameId!r} on {day}")
    buckets = bucket_candidates(candidates, spec)
    bands = [band.id for band in spec.difficulties]
    seen = set(used)
    chosen: list[tuple[GameWord, str]] = []
    for slot in range(count):
        band_id = bands[slot % len(bands)]
        pool = buckets[band_id]
        if not pool:
            raise ValueError(
                f"no candidate words for {spec.gameId!r} in the {band_id!r} bucket"
            )
        order = stratified_order(pool, f"{day}|{spec.gameId}|{band_id}")
        picked = {row.word for row, _ in chosen}
        row = next(
            (row for row in order if row.word not in seen),
            next((row for row in order if row.word not in picked), order[0]),
        )
        seen.add(row.word)
        chosen.append((row, band_id))
    return chosen


def build_item(
    row: GameWord, spec: GameGeneration, day: str, hint_limit: int, difficulty: str
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
        difficulty=difficulty,
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
        for row, difficulty in pick_words(wordlist.words, spec, day, count, seen):
            seen.add(row.word)
            items.append(build_item(row, spec, day, hint_limit, difficulty))
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
