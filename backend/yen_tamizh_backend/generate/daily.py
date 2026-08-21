"""Bake one day of the puzzle bank, and the index over every baked day.

The rules this module enforces:

- **A day is a pure function of its date.** Selection is a seeded, frequency-
  stratified draw over a stable-sorted candidate list, so re-running any date
  reproduces it byte for byte - the Row 13 Oracle. Nothing here reads a clock;
  the caller supplies the dates.
- **A day is a curve, and the curve orders the day.** Its slots are dealt the
  configured difficulty bands in order - easy, then medium, then hard - and the
  Games that fill them are dealt in ascending ``dailyRank``, so the lightest
  board opens the day on its easiest band and the heaviest closes it on its
  hardest. Because the easiest band admits only the most familiar quarter, a day
  can never be three words nobody knows.
- **A day holds several Games, and which ones is a WINDOW over a ring.** The
  Daily serves more Games than a day has slots, so a day takes the
  ``playlistLength`` window of ``daily.games`` that starts at its own date. Every
  Game reaches a player within one turn of the ring without any single day
  holding all of them, which is what keeps the Daily a burst rather than a
  sitting - and because the ring is at least as long as the playlist, an
  ordinary day never deals the same Game twice.
- **A word does not come back.** Words already used on OTHER days present in the
  bank are skipped, so a player does not meet the same scramble twice. The
  target date's own file is ignored while collecting them, which is exactly what
  makes a re-run idempotent instead of self-poisoning.
- **Some days are THEMED.** On the dates the configured cadence allows, if one
  registered theme can fill every slot of the THEMED window from its own
  wordlist - without repeating a word the bank has served, and with every one of
  those rows actually buildable by the Game holding it - the whole day is drawn
  from that theme and the day records its copy slug. Otherwise the day is
  ordinary. A theme is never padded out with an off-theme word - three unrelated
  anagrams are a list, three that share a theme are a round, and half a theme is
  neither. The themed window is its own ring for that reason: it holds only the
  Games the theme can honestly fill, and it is allowed to repeat one rather than
  reach for a Game whose slots the theme cannot fill. A themed day also drops the
  ``category`` rung from every ladder it bakes, because the theme is already
  announced free in the round header.
- **What else the tiles spell is answered HERE.** This is the only layer holding
  a whole served wordlist, so it is the only layer that can tell a puzzle which
  other served words it could be confused with - the ones its tiles also spell,
  or the ones its mask also admits. Partners come from the set the day actually
  drew from, which on a themed day is the theme's own.
- **A second Game is a REGISTRATION, not a branch.** ``BUILDERS`` maps a
  ``gameId`` to the pair of functions the loop needs: how to index one served
  set, and how to turn one row into that Game's validated payload. The loop
  below never asks which Game it is holding.
- **The mix is config, not code.** How long a day is and which Games fill it come
  from ``config/app-config.json`` (``daily.playlistLength``, ``daily.games`` and
  ``daily.themedGames``); how a word becomes a puzzle, and how heavy that Game
  is on the day's ramp, come from ``config/daily-generator.json``. A Game named
  in a ring with no registered generator is an error, not a silently short day.

The bank lives under ``frontend/public/`` so the game reads it same-origin from
its own bundle and it works offline (Holy Law #1).
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from yen_tamizh_backend.contracts.app_config import AppConfig
from yen_tamizh_backend.contracts.bank_index import BankDay, BankIndex
from yen_tamizh_backend.contracts.base import ChangelogEntry
from yen_tamizh_backend.contracts.daily_generator import (
    DailyGenerator,
    DifficultyBand,
    GameGeneration,
)
from yen_tamizh_backend.contracts.game_wordlist import GameWord, GameWordlist
from yen_tamizh_backend.contracts.puzzle_file import PuzzleFile, PuzzleItem
from yen_tamizh_backend.generate import (
    Unbuildable,
    anagram,
    crossword,
    missing_letters,
    word_ladder,
    word_search,
    wordle,
)
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
class Slot:
    """One position in a day's playlist: which Game fills it, and how hard.

    The day owns both, which is what makes the curve a property of the DAY
    rather than of whichever Game happens to hold three slots. ``position`` is
    the order the player meets it in.
    """

    position: int
    gameId: str
    difficulty: str


@dataclass(frozen=True)
class ThemedDraw:
    """A whole themed day: the theme's copy slug, its word per slot, and where
    each of those words came from.

    ``sources`` is what lets the rest of the bake stay honest about a themed
    day: the alternative arrangements a puzzle offers must come from the set the
    day actually drew from, and on a themed day that is the theme's wordlist,
    not the Game's ordinary one.
    """

    copySlug: str
    rows: tuple[GameWord, ...]
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


def answer_words(payload: Mapping[str, Any]) -> list[str]:
    """Every word one baked payload asks the player for, in payload order.

    A payload names its answers in one of four ways and all four are read here.
    Three of the six Games hide ONE word and put it under ``word``; a search
    board lists what it hid under ``targets``, a crossword lists what it asks
    for under ``entries``, and a ladder lists what it climbs through under
    ``rungs``. Every one of those has been met by the player just as surely as a
    scramble's answer has - including a ladder's FIRST rung, which is given
    rather than asked for but is printed with its meaning like any other.

    It is one function rather than a key lookup at each call site because the
    two readers - the anti-repeat ledger and the bake's own record of what a day
    served - must agree about what a day served. A day whose words the ledger
    could not see would be dealt again a week later.
    """
    words: list[str] = []
    single = payload.get("word")
    if isinstance(single, str):
        words.append(single)
    for key in ("targets", "entries", "rungs"):
        listed = payload.get(key)
        if not isinstance(listed, list):
            continue
        for item in listed:
            named = item.get("word") if isinstance(item, Mapping) else None
            if isinstance(named, str):
                words.append(named)
    return words


def words_used_before(bank_dir: Path, exclude_day: str) -> set[str]:
    """Every answer word the bank has already served on some OTHER day.

    Excluding the target day is what makes a re-run idempotent: a day must not
    treat its own previous output as a reason to pick different words.
    """
    used: set[str] = set()
    for day in baked_days(bank_dir):
        if day == exclude_day:
            continue
        document = json.loads(day_path(bank_dir, day).read_text(encoding="utf-8"))
        for item in document.get("items", []):
            used.update(answer_words(item.get("payload", {})))
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


def difficulty_of(row: GameWord, spec: GameGeneration) -> str | None:
    """The first configured band that covers the word's LENGTH and its FAMILIARITY.

    Two axes, because length alone is anti-correlated at both tails: a long
    headword is usually a compound that decomposes and is easier than its tile
    count suggests, while a short rare word is brutal and a 3-ezhuthu one is
    brute-forceable by shuffling. Bands overlap on length and tile on
    familiarity, so which band claims a word is mostly a question of how well the
    player knows it.

    ``None`` when no band claims the row - typically a short word outside the
    familiar quarters. That is a real answer, not a failure: the wordlist says
    what is SERVABLE and the bands say what is DRAWABLE, and inventing a
    difficulty for a row no band wants would put exactly the museum piece on the
    board that the second axis exists to keep off it.

    It lives with the day loop rather than with a Game because it is the loop's
    question: every Game deals its slots across the same bands.
    """
    length = len(row.ezhuthu)
    for band in spec.difficulties:
        if (
            band.minLength <= length <= band.maxLength
            and row.frequencyStratum <= band.maxStratum
        ):
            return band.id
    return None


@dataclass(frozen=True)
class GameBuilder:
    """How the day loop turns served rows into one Game's payloads.

    ``prepare`` indexes a whole served set once per day - the only place a Game
    may learn about words other than the one it is building - and ``build``
    turns one row into a validated payload. Registering a pair here is the whole
    cost of adding a Game to the day loop, which is the promise the generator
    registry's docstring makes.
    """

    prepare: Callable[[GameWordlist, GameGeneration], Any]
    build: Callable[
        [GameWord, GameGeneration, str, int, DifficultyBand, bool, Any], BaseModel
    ]


def _prepare_anagram(wordlist: GameWordlist, spec: GameGeneration) -> Any:
    del spec
    return alternatives_of(wordlist)


def _build_anagram(
    row: GameWord,
    spec: GameGeneration,
    day: str,
    hint_limit: int,
    band: DifficultyBand,
    themed: bool,
    prepared: Any,
) -> BaseModel:
    del band
    index: dict[MultisetKey, tuple[str, ...]] = prepared
    partners = [
        word for word in index.get(multiset_key(row.ezhuthu), ()) if word != row.word
    ]
    return anagram.build_puzzle(
        row, spec, f"{day}|{row.word}", hint_limit, themed, partners
    )


def _build_missing_letters(
    row: GameWord,
    spec: GameGeneration,
    day: str,
    hint_limit: int,
    band: DifficultyBand,
    themed: bool,
    prepared: Any,
) -> BaseModel:
    return missing_letters.build_puzzle(
        row, spec, f"{day}|{row.word}", hint_limit, band.blanks, prepared, themed
    )


def _prepare_wordle(wordlist: GameWordlist, spec: GameGeneration) -> Any:
    """A wordle needs to know nothing about the other served words.

    The anagram has to be told what else its tiles spell and the missing-letters
    board what else its mask admits, because both input methods can produce only
    a handful of strings and some of those are other words. A wordle guess is
    one of 247**N strings and is answered by its own per-position marks, so
    there is no index to build.
    """
    del wordlist, spec
    return None


def _build_wordle(
    row: GameWord,
    spec: GameGeneration,
    day: str,
    hint_limit: int,
    band: DifficultyBand,
    themed: bool,
    prepared: Any,
) -> BaseModel:
    del band, prepared
    return wordle.build_puzzle(row, spec, f"{day}|{row.word}", hint_limit, themed)


def _build_word_search(
    row: GameWord,
    spec: GameGeneration,
    day: str,
    hint_limit: int,
    band: DifficultyBand,
    themed: bool,
    prepared: Any,
) -> BaseModel:
    """The one builder that draws MORE words than the day loop picked.

    A search board hides several words and the loop deals one slot at a time, so
    the row it picked becomes the board's anchor and the builder draws the rest
    from the same prepared set and the same band. That is why this Game's
    ``prepare`` hands over the whole served index rather than a lookup table: it
    is the only layer holding a served set, and the alternative - teaching the
    loop to deal several rows into one slot - would put one Game's arithmetic
    into the loop that is supposed to know nothing about which Game it holds.
    """
    return word_search.build_puzzle(
        row, spec, f"{day}|{row.word}", hint_limit, band, prepared, themed
    )


def _build_crossword(
    row: GameWord,
    spec: GameGeneration,
    day: str,
    hint_limit: int,
    band: DifficultyBand,
    themed: bool,
    prepared: Any,
) -> BaseModel:
    """The second builder that draws more words than the day loop picked.

    A crossword's answers are not independent of each other - each one is
    constrained by every answer that crosses it - so the row the loop picked
    becomes the word the solver must place, and the rest of the board is solved
    around it from the same served index and the same band.
    """
    return crossword.build_puzzle(
        row, spec, f"{day}|{row.word}", hint_limit, band, prepared, themed
    )


def _build_word_ladder(
    row: GameWord,
    spec: GameGeneration,
    day: str,
    hint_limit: int,
    band: DifficultyBand,
    themed: bool,
    prepared: Any,
) -> BaseModel:
    """The third builder that draws more words than the day loop picked.

    The row the loop picked is the ledge the climb STARTS on, and every rung
    above it is whatever the prepared reachability graph proves is reachable -
    so the band gates the start and the graph decides the rest. Most served
    words start no ladder at all, which is why this Game leans hardest of the
    six on ``pick_words``' buildability probe: a refused row is stepped over
    like a word the bank has already served.
    """
    return word_ladder.build_puzzle(
        row, spec, f"{day}|{row.word}", hint_limit, band, prepared, themed
    )


# The registered Games, keyed by the ``gameId`` config names in `daily.games`.
BUILDERS: dict[str, GameBuilder] = {
    "anagram": GameBuilder(prepare=_prepare_anagram, build=_build_anagram),
    missing_letters.GAME_ID: GameBuilder(
        prepare=missing_letters.index_by_length, build=_build_missing_letters
    ),
    wordle.GAME_ID: GameBuilder(prepare=_prepare_wordle, build=_build_wordle),
    word_search.GAME_ID: GameBuilder(
        prepare=word_search.index_served, build=_build_word_search
    ),
    crossword.GAME_ID: GameBuilder(
        prepare=crossword.index_served, build=_build_crossword
    ),
    word_ladder.GAME_ID: GameBuilder(
        prepare=word_ladder.index_served, build=_build_word_ladder
    ),
}


def builder_for(game_id: str) -> GameBuilder:
    """The registered builder for a Game, or a loud failure naming what exists."""
    builder = BUILDERS.get(game_id)
    if builder is None:
        raise ValueError(
            f"{game_id!r} has no registered puzzle builder: {sorted(BUILDERS)}"
        )
    return builder


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
        bucket = difficulty_of(row, spec)
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


def playlist_games(ring: Sequence[str], playlist_length: int, day: str) -> list[str]:
    """The Games one day holds: the window of ``ring`` that starts at this date.

    A window rather than a fixed mix because the Daily serves more Games than a
    day has slots. Walking the ring by a whole playlist each day means
    consecutive days share at most the one Game the window carries over, so a
    player meets a different set of boards every morning while every Game still
    comes round within one turn of the ring.

    **Plus one extra step for every lap the ring has completed.** Walking by the
    playlist alone only reaches ``len(ring) / gcd(len(ring), playlistLength)``
    of the possible windows, so a six-Game ring dealt three a day would
    oscillate between exactly TWO playlists for ever - and because ``day_slots``
    ranks a window's Games against each other, every Game would then be locked
    to one difficulty band and the other bands of its registry entry would never
    ship. The lap term is coprime-free: after enough laps the phase has drifted
    through every offset, so every window the ring can produce is reached
    whatever the two numbers are. It is still a pure function of the date.

    The window WRAPS, so a ring shorter than the playlist deals a Game more than
    once. That is refused for ordinary days by the contract and allowed for
    themed ones, because the two make different claims: an ordinary day claims
    variety of Games, a themed day claims its words belong together.
    """
    walked = date.fromisoformat(day).toordinal() * playlist_length
    start = (walked + walked // len(ring)) % len(ring)
    return [ring[(start + offset) % len(ring)] for offset in range(playlist_length)]


def day_slots(
    ring: Sequence[str], playlist_length: int, day: str, specs: Mapping[str, GameGeneration]
) -> list[Slot]:
    """One day's playlist as ordered slots: the curve, and who fills each step.

    The Games come from the date's window; they are ORDERED by ``dailyRank`` so
    the lightest board opens the day and the heaviest closes it, and each slot is
    then dealt the band at its own position on its Game's ramp. Both dials
    therefore rise together down the playlist, which is what "a day opens easy
    and ends harder" means once a day holds more than one Game.

    Ties on rank break on ``gameId``, and a repeated Game keeps window order, so
    the schedule stays a pure function of the date.
    """
    window = playlist_games(ring, playlist_length, day)
    order = sorted(
        range(len(window)),
        key=lambda index: (specs[window[index]].dailyRank, window[index], index),
    )
    slots: list[Slot] = []
    for position, index in enumerate(order):
        spec = specs[window[index]]
        band = spec.difficulties[position % len(spec.difficulties)]
        slots.append(Slot(position=position, gameId=spec.gameId, difficulty=band.id))
    return slots


def pick_words(
    candidates: Sequence[GameWord],
    spec: GameGeneration,
    day: str,
    bands: Sequence[str],
    used: Iterable[str],
    buildable: Callable[[GameWord, str], bool] | None = None,
) -> list[tuple[GameWord, str]]:
    """Choose this Game's words for the bands it was dealt, skipping served ones.

    ``bands`` is the day's own schedule for this Game - one band id per slot it
    holds - so the curve is decided by the day and this only fills it. A Game
    holding three slots gets all three bands and is a curve by itself; a Game
    holding one gets the single band its position on the day's ramp earned.

    Within a band the draw is stratified (see ``stratified_order``), seeded by
    the date so the day stays a pure function of its date. If the bank has served
    a band's whole bucket, the day repeats from that same order rather than
    shipping short: a repeat is a much smaller failure than a playlist that does
    not add up.

    ``buildable`` is the third question, after "is this word servable" and "does
    a band claim it": can this Game actually build a puzzle out of it. Only an
    interlocked board can answer no - a crossword answer has to share letters
    with everything crossing it - so the default is that every row is buildable
    and the loop is unchanged for the four Games that were here first. A refused
    row is stepped over exactly like a row the bank has already served, so the
    day stays a pure function of its date. It narrows all three fallbacks rather
    than replacing them: repeating a word is still a smaller failure than a
    short playlist, and only a band whose every word this Game refuses is an
    error.
    """
    if not candidates:
        raise ValueError(f"no candidate words for {spec.gameId!r} on {day}")
    accepts = buildable if buildable is not None else (lambda row, band: True)
    buckets = bucket_candidates(candidates, spec)
    seen = set(used)
    chosen: list[tuple[GameWord, str]] = []
    for band_id in bands:
        pool = buckets[band_id]
        if not pool:
            raise ValueError(
                f"no candidate words for {spec.gameId!r} in the {band_id!r} bucket"
            )
        order = stratified_order(pool, f"{day}|{spec.gameId}|{band_id}")
        picked = {row.word for row, _ in chosen}
        row = next(
            (row for row in order if row.word not in seen and accepts(row, band_id)),
            None,
        )
        if row is None:
            row = next(
                (row for row in order if row.word not in picked and accepts(row, band_id)),
                None,
            )
        if row is None:
            row = next((row for row in order if accepts(row, band_id)), None)
        if row is None:
            raise ValueError(
                f"{spec.gameId!r} could not build any of the {len(order)} words in its "
                f"{band_id!r} bucket on {day}"
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
    bands: Sequence[str],
    used: Iterable[str],
    buildable: Callable[[GameWord, str], bool] | None = None,
) -> list[tuple[GameWord, str]] | None:
    """This theme's draw for one Game's slots, or ``None`` if it cannot fill them.

    A themed round is OPPORTUNISTIC: it runs on the days a full themed playlist
    can be drawn and is skipped otherwise, never padded out with an off-theme
    word, because the round's whole claim is that its words belong together.

    "Can fill" is stricter than what an ordinary day tolerates, in three ways.
    An ordinary day repeats a served word rather than shipping short, which is
    the right trade when the alternative is a playlist that does not add up; a
    theme has an alternative - be an ordinary day - so a theme that would have to
    repeat, or that has an empty difficulty bucket, simply does not run. And a
    row this Game cannot BUILD is not a fill either: a theme's set is a few
    hundred words, which is thin enough that an interlocked board can refuse
    every one of them, so the question has to be asked here rather than
    discovered by a bake that has already committed to the theme.
    """
    seen = set(used)
    buckets = bucket_candidates(rows, spec)
    if any(not buckets[band_id] for band_id in bands):
        return None
    try:
        picks = pick_words(rows, spec, day, bands, seen, buildable)
    except ValueError:
        # Every candidate in some band was refused. That is a real answer here -
        # this theme does not run today - not a failed bake.
        return None
    words = [row.word for row, _ in picks]
    if len(set(words)) != len(bands) or not seen.isdisjoint(words):
        return None
    return picks


def themed_draw(
    day: str,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
    slots: Sequence[Slot],
    used: Iterable[str],
) -> ThemedDraw | None:
    """The theme this date runs, with its whole playlist - or ``None`` for an
    ordinary day.

    A theme is registered per Game, but a themed DAY is a claim about the whole
    playlist, so a theme qualifies only when EVERY Game in the themed window
    registers it under the same ``copySlug`` and every one of them can fill its
    own slots from that theme's set. Anything less would announce a theme over a
    day that is partly off-theme.

    Which theme runs on a date with more than one candidate is seeded by the
    date, so the choice is a pure function of the day like every other decision
    here, and a theme that cannot fill this date does not block the next one.
    """
    if not is_theme_date(day, generator):
        return None
    specs = {spec.gameId: spec for spec in generator.games}
    wanted = sorted({slot.gameId for slot in slots})
    covered: dict[str, dict[str, str]] = defaultdict(dict)
    for game_id in wanted:
        for theme in specs[game_id].themes:
            covered[theme.copySlug][game_id] = theme.wordlist
    candidates = sorted(
        slug for slug, games in covered.items() if len(games) == len(wanted)
    )
    if not candidates:
        return None

    start = seeded_index(len(candidates), day)
    for offset in range(len(candidates)):
        slug = candidates[(start + offset) % len(candidates)]
        seen = set(used)
        drawn: dict[int, GameWord] = {}
        for game_id in wanted:
            spec = specs[game_id]
            source = covered[slug][game_id]
            mine = [slot for slot in slots if slot.gameId == game_id]
            builder = builder_for(game_id)
            prepared = builder.prepare(wordlists[source], spec)
            probe, _ = buildability_probe(
                spec, day, hint_limit_for(app_config, game_id), True, prepared
            )
            picks = theme_can_fill(
                wordlists[source].words,
                spec,
                day,
                [slot.difficulty for slot in mine],
                seen,
                probe,
            )
            if picks is None:
                break
            for slot, (row, _) in zip(mine, picks, strict=True):
                drawn[slot.position] = row
            seen.update(row.word for row, _ in picks)
        else:
            return ThemedDraw(
                copySlug=slug,
                rows=tuple(drawn[slot.position] for slot in slots),
                sources=dict(covered[slug]),
            )
    return None


def build_item(
    row: GameWord,
    spec: GameGeneration,
    day: str,
    hint_limit: int,
    difficulty: str,
    themed: bool,
    prepared: Any,
) -> PuzzleItem:
    """One playlist entry: the Game's validated payload plus its framing.

    The payload drops the schema stamp the model carries: the day file has its
    own ``version`` + ``changelog``, and repeating one inside every item would
    be bytes the player downloads to learn nothing (Carmack). Building the model
    first is still what proves the payload obeys its own per-Game contract.
    """
    band = next(entry for entry in spec.difficulties if entry.id == difficulty)
    puzzle = builder_for(spec.gameId).build(
        row, spec, day, hint_limit, band, themed, prepared
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


def hint_limit_for(app_config: AppConfig, game_id: str) -> int:
    """How many rungs a day may bake for one Game.

    The app config's call, not the generator's: the same switch the shell reads
    decides what gets baked. A Game with no entry sells nothing.
    """
    if not app_config.hints.enabled:
        return 0
    return app_config.hints.perGame.get(game_id, 0)


def buildability_probe(
    spec: GameGeneration,
    day: str,
    hint_limit: int,
    themed: bool,
    prepared: Any,
) -> tuple[Callable[[GameWord, str], bool], dict[tuple[str, str], PuzzleItem]]:
    """A "can this Game build this row" test, and the items it built answering it.

    Built here rather than after the pick because "can this Game build this row"
    can only be answered by building it - and building it twice would let the
    answer and the item disagree. Every accepted row's item is kept, so the loop
    that asked the question also gets the puzzle for free.
    """
    made: dict[tuple[str, str], PuzzleItem] = {}

    def buildable(row: GameWord, difficulty: str) -> bool:
        try:
            made[(row.word, difficulty)] = build_item(
                row, spec, day, hint_limit, difficulty, themed, prepared
            )
        except Unbuildable:
            return False
        return True

    return buildable, made


def build_day(
    day: str,
    app_config: AppConfig,
    generator: DailyGenerator,
    wordlists: dict[str, GameWordlist],
    used: Iterable[str],
) -> PuzzleFile:
    """Build one day's playlist from the config'd rings. Pure; no I/O, no clock.

    ``wordlists`` is keyed by the repo-relative PATH each set was written to,
    because a Game has more than one: its ordinary set and, once it registers
    themes, one set per theme. A path is what the registry actually names.
    """
    specs = {spec.gameId: spec for spec in generator.games}
    daily_config = app_config.daily
    for name, ring in (
        ("games", daily_config.games),
        ("themedGames", daily_config.themedGames),
    ):
        for game_id in ring:
            if game_id not in specs:
                raise ValueError(f"daily.{name} names {game_id!r}, which has no generator")

    themed_slots = day_slots(
        daily_config.themedGames, daily_config.playlistLength, day, specs
    )
    themed = themed_draw(day, app_config, generator, wordlists, themed_slots, used)
    slots = (
        themed_slots
        if themed is not None
        else day_slots(daily_config.games, daily_config.playlistLength, day, specs)
    )

    seen = set(used)
    chosen: dict[int, GameWord] = {}
    if themed is not None:
        chosen = {slot.position: row for slot, row in zip(slots, themed.rows, strict=True)}
        seen.update(row.word for row in themed.rows)

    items: dict[int, PuzzleItem] = {}
    prepared: dict[tuple[str, str], Any] = {}
    # Sorted so which Game draws first depends on the config, never on dict order.
    for game_id in sorted({slot.gameId for slot in slots}):
        spec = specs[game_id]
        mine = [slot for slot in slots if slot.gameId == game_id]
        hint_limit = hint_limit_for(app_config, game_id)
        # Which set the day drew from is also which set may answer "what else
        # could this have been": offering an alternative from the ordinary set on
        # a themed day would name a word the day never serves.
        source = spec.wordlist if themed is None else themed.sources[game_id]
        key = (game_id, source)
        if key not in prepared:
            prepared[key] = builder_for(game_id).prepare(wordlists[source], spec)
        probe, made = buildability_probe(
            spec, day, hint_limit, themed is not None, prepared[key]
        )
        if themed is None:
            picks = pick_words(
                wordlists[source].words,
                spec,
                day,
                [slot.difficulty for slot in mine],
                seen,
                probe,
            )
        else:
            picks = [(chosen[slot.position], slot.difficulty) for slot in mine]
        for slot, (row, difficulty) in zip(mine, picks, strict=True):
            seen.add(row.word)
            items[slot.position] = made.get((row.word, difficulty)) or build_item(
                row, spec, day, hint_limit, difficulty, themed is not None, prepared[key]
            )
    return PuzzleFile(
        version=_PUZZLE_FILE_VERSION,
        changelog=_PUZZLE_FILE_CHANGELOG,
        date=day,
        theme=None if themed is None else themed.copySlug,
        items=[items[slot.position] for slot in slots],
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
