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
- **Some days are THEMED.** On the dates the configured cadence allows, if one
  registered theme can fill every slot from its own wordlist without repeating a
  word the bank has served, the whole day is drawn from that theme and the day
  records its copy slug. Otherwise the day is ordinary. A theme is never padded
  out with an off-theme word - three unrelated anagrams are a list, three that
  share a theme are a round, and half a theme is neither. A themed day also
  drops the ``category`` rung from every ladder it bakes, because the theme is
  already announced free in the round header.
- **What else the tiles spell is answered HERE.** This is the only layer holding
  a whole served wordlist, so it is the only layer that can tell a puzzle which
  other served words share its ezhuthu multiset. Partners come from the set the
  day actually drew from, which on a themed day is the theme's own.
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

_PUZZLE_FILE_VERSION = "2026-08-17"
_PUZZLE_FILE_CHANGELOG = [
    ChangelogEntry(
        version=_PUZZLE_FILE_VERSION,
        change="Added the optional theme slug to a day.",
        why=(
            "Row 15 - a themed day draws every slot from one theme's wordlist, "
            "and the shell can only announce that if the day says so. The SLUG "
            "travels rather than the Tamil label, because the label is copy the "
            "shell already reads and a baked label could only be corrected by a "
            "rebuild. Absent means an ordinary day, so every day baked before "
            "this still validates unchanged."
        ),
    ),
    ChangelogEntry(
        version="2026-08-13",
        change="Initial baked daily playlist.",
        why="Row 13 - the first committed day of the puzzle bank.",
    ),
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

# The order-free key two words share exactly when one's tiles spell the other.
# Deliberately a local definition: the derived layer computes the same key when
# it counts fan-out, but the daily engine may not import from the lexicon
# pipeline (see test_the_engine_reads_only_the_derived_layer), and a test pins
# the two against each other over the whole served set.
MultisetKey = tuple[str, ...]


@dataclass(frozen=True)
class GeneratedDay:
    """One baked day: where it landed, and what it holds."""

    date: str
    path: Path
    rel_path: str
    puzzle_file: PuzzleFile
    words: tuple[str, ...]


@dataclass(frozen=True)
class ThemedDraw:
    """A whole themed day: the theme's copy slug, every Game's picks, and where
    each of those picks came from.

    ``sources`` is what lets the rest of the bake stay honest about a themed
    day: the alternative arrangements a puzzle offers must come from the set the
    day actually drew from, and on a themed day that is the theme's wordlist,
    not the Game's ordinary one.
    """

    copySlug: str
    picks: dict[str, list[tuple[GameWord, str]]]
    sources: dict[str, str]


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


def multiset_key(ezhuthu: Iterable[str]) -> MultisetKey:
    """Return the order-free key two words share exactly when they are anagrams."""
    return tuple(sorted(ezhuthu))


def alternatives_of(wordlist: GameWordlist) -> dict[MultisetKey, tuple[str, ...]]:
    """Index one served set by ezhuthu multiset - what each scramble can spell.

    Built ONCE per set per day rather than per puzzle, and over the SERVED rows
    only, because that is the population a Game can say anything true about:
    telling a player their arrangement is another word only helps when the game
    would actually serve that word.
    """
    groups: dict[MultisetKey, list[str]] = defaultdict(list)
    for row in wordlist.words:
        groups[multiset_key(row.ezhuthu)].append(row.word)
    return {key: tuple(sorted(words)) for key, words in groups.items()}


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


def is_theme_date(day: str, generator: DailyGenerator) -> bool:
    """Whether this date is one the Daily MAY run a theme on.

    The cadence is counted on the proleptic Gregorian day number, so it is a
    pure function of the date with no phase knob and no reference to when the
    bank was first baked. ``themeEveryNDays`` of 0 turns themed days off.

    A cadence is needed at all because a theme wide enough to be worth having is
    also wide enough to fill months of consecutive days, and a Daily that is the
    same theme every day for months is the opposite of the variety a theme adds.
    """
    if generator.themeEveryNDays == 0:
        return False
    return date.fromisoformat(day).toordinal() % generator.themeEveryNDays == 0


def theme_can_fill(
    rows: Sequence[GameWord],
    spec: GameGeneration,
    day: str,
    count: int,
    used: Iterable[str],
) -> list[tuple[GameWord, str]] | None:
    """This theme's whole draw for one Game, or ``None`` if it cannot fill it.

    A themed round is OPPORTUNISTIC: it runs on the days a full themed playlist
    can be drawn and is skipped otherwise, never padded out with an off-theme
    word, because the round's whole claim is that its words belong together.

    "Can fill" is stricter than what an ordinary day tolerates. An ordinary day
    repeats a served word rather than shipping short, which is the right trade
    when the alternative is a playlist that does not add up; a theme has an
    alternative - be an ordinary day - so a theme that would have to repeat, or
    that has an empty difficulty bucket, simply does not run.
    """
    seen = set(used)
    buckets = bucket_candidates(rows, spec)
    bands = [band.id for band in spec.difficulties]
    if any(not buckets[bands[slot % len(bands)]] for slot in range(count)):
        return None
    picks = pick_words(rows, spec, day, count, seen)
    words = [row.word for row, _ in picks]
    if len(set(words)) != count or not seen.isdisjoint(words):
        return None
    return picks


def themed_draw(
    day: str,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
    used: Iterable[str],
) -> ThemedDraw | None:
    """The theme this date runs, with its whole playlist - or ``None`` for an
    ordinary day.

    A theme is registered per Game, but a themed DAY is a claim about the whole
    playlist, so a theme qualifies only when EVERY Game in the mix registers it
    under the same ``copySlug`` and every one of them can fill its own slots from
    that theme's set. Anything less would announce a theme over a day that is
    partly off-theme.

    Which theme runs on a date with more than one candidate is seeded by the
    date, so the choice is a pure function of the day like every other decision
    here, and a theme that cannot fill this date does not block the next one.
    """
    if not is_theme_date(day, generator):
        return None
    mix = app_config.daily.mix
    specs = {spec.gameId: spec for spec in generator.games}
    covered: dict[str, dict[str, str]] = defaultdict(dict)
    for game_id in mix:
        for theme in specs[game_id].themes:
            covered[theme.copySlug][game_id] = theme.wordlist
    candidates = sorted(slug for slug, games in covered.items() if len(games) == len(mix))
    if not candidates:
        return None

    start = seeded_index(len(candidates), day)
    for offset in range(len(candidates)):
        slug = candidates[(start + offset) % len(candidates)]
        seen = set(used)
        picks: dict[str, list[tuple[GameWord, str]]] = {}
        for game_id, count in sorted(mix.items()):
            drawn = theme_can_fill(
                wordlists[covered[slug][game_id]].words,
                specs[game_id],
                day,
                count,
                seen,
            )
            if drawn is None:
                break
            picks[game_id] = drawn
            seen.update(row.word for row, _ in drawn)
        else:
            return ThemedDraw(copySlug=slug, picks=picks, sources=dict(covered[slug]))
    return None


def build_item(
    row: GameWord,
    spec: GameGeneration,
    day: str,
    hint_limit: int,
    difficulty: str,
    themed: bool,
    also_valid: Sequence[str],
) -> PuzzleItem:
    """One playlist entry: the Game's validated payload plus its framing.

    The payload drops the schema stamp the model carries: the day file has its
    own ``version`` + ``changelog``, and repeating one inside every item would
    be bytes the player downloads to learn nothing (Carmack). Building the model
    first is still what proves the payload obeys ``anagram-puzzle``.
    """
    puzzle = anagram.build_puzzle(
        row, spec, f"{day}|{row.word}", hint_limit, themed, also_valid
    )
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
    """Build one day's playlist from the config'd mix. Pure; no I/O, no clock.

    ``wordlists`` is keyed by the repo-relative PATH each set was written to,
    because a Game has more than one: its ordinary set and, once it registers
    themes, one set per theme. A path is what the registry actually names.
    """
    mix = app_config.daily.mix
    total = sum(mix.values())
    if total != app_config.daily.playlistLength:
        raise ValueError(
            f"daily.mix sums to {total} but daily.playlistLength is "
            f"{app_config.daily.playlistLength}"
        )
    specs = {spec.gameId: spec for spec in generator.games}
    for game_id in sorted(mix):
        if game_id not in specs:
            raise ValueError(f"daily.mix names {game_id!r}, which has no generator")

    themed = themed_draw(day, app_config, generator, wordlists, used)
    seen = set(used)
    items: list[PuzzleItem] = []
    alternatives: dict[str, dict[MultisetKey, tuple[str, ...]]] = {}
    # Sorted so the playlist's order depends on the config, never on dict order.
    for game_id, count in sorted(mix.items()):
        spec = specs[game_id]
        # How much help a day may ship is the app config's call, not the
        # generator's: the same switch the shell reads decides what gets baked.
        hint_limit = (
            app_config.hints.perGame.get(game_id, 0) if app_config.hints.enabled else 0
        )
        # Which set the day drew from is also which set may answer "what else do
        # these tiles spell": offering a partner from the ordinary set on a
        # themed day would name a word the day never serves.
        source = spec.wordlist if themed is None else themed.sources[game_id]
        if source not in alternatives:
            alternatives[source] = alternatives_of(wordlists[source])
        picks = (
            themed.picks[game_id]
            if themed is not None
            else pick_words(wordlists[spec.wordlist].words, spec, day, count, seen)
        )
        for row, difficulty in picks:
            seen.add(row.word)
            partners = [
                word
                for word in alternatives[source].get(multiset_key(row.ezhuthu), ())
                if word != row.word
            ]
            items.append(
                build_item(
                    row,
                    spec,
                    day,
                    hint_limit,
                    difficulty,
                    themed is not None,
                    partners,
                )
            )
    return PuzzleFile(
        version=_PUZZLE_FILE_VERSION,
        changelog=_PUZZLE_FILE_CHANGELOG,
        date=day,
        theme=None if themed is None else themed.copySlug,
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
