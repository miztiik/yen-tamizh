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
  other served words it could be confused with - the ones its tiles also spell,
  or the ones its mask also admits. Partners come from the set the day actually
  drew from, which on a themed day is the theme's own.
- **A second Game is a REGISTRATION, not a branch.** ``BUILDERS`` maps a
  ``gameId`` to the pair of functions the loop needs: how to index one served
  set, and how to turn one row into that Game's validated payload. The loop
  below never asks which Game it is holding.
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


def answer_words(payload: Mapping[str, Any]) -> list[str]:
    """Every word one baked payload asks the player for, in payload order.

    A payload names its answers in one of three ways and all three are read
    here. Three of the five Games hide ONE word and put it under ``word``; a
    search board lists what it hid under ``targets``, and a crossword lists what
    it asks for under ``entries``. Every one of those has been met by the player
    just as surely as a scramble's answer has.

    It is one function rather than a key lookup at each call site because the
    two readers - the anti-repeat ledger and the bake's own record of what a day
    served - must agree about what a day served. A day whose words the ledger
    could not see would be dealt again a week later.
    """
    words: list[str] = []
    single = payload.get("word")
    if isinstance(single, str):
        words.append(single)
    for key in ("targets", "entries"):
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


# The registered Games, keyed by the ``gameId`` config names in `daily.mix`.
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


def pick_words(
    candidates: Sequence[GameWord],
    spec: GameGeneration,
    day: str,
    count: int,
    used: Iterable[str],
    buildable: Callable[[GameWord, str], bool] | None = None,
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
    prepared: dict[tuple[str, str], Any] = {}
    # Sorted so the playlist's order depends on the config, never on dict order.
    for game_id, count in sorted(mix.items()):
        spec = specs[game_id]
        # How much help a day may ship is the app config's call, not the
        # generator's: the same switch the shell reads decides what gets baked.
        hint_limit = (
            app_config.hints.perGame.get(game_id, 0) if app_config.hints.enabled else 0
        )
        # Which set the day drew from is also which set may answer "what else
        # could this have been": offering an alternative from the ordinary set on
        # a themed day would name a word the day never serves.
        source = spec.wordlist if themed is None else themed.sources[game_id]
        key = (game_id, source)
        if key not in prepared:
            prepared[key] = builder_for(game_id).prepare(wordlists[source], spec)
        # Built here, not after the pick, because "can this Game build this row"
        # can only be answered by building it - and building it twice would let
        # the answer and the item disagree. Every accepted row's item is kept.
        made: dict[tuple[str, str], PuzzleItem] = {}

        def buildable(
            row: GameWord,
            difficulty: str,
            spec: GameGeneration = spec,
            key: tuple[str, str] = key,
            hint_limit: int = hint_limit,
            made: dict[tuple[str, str], PuzzleItem] = made,
        ) -> bool:
            try:
                made[(row.word, difficulty)] = build_item(
                    row, spec, day, hint_limit, difficulty, themed is not None,
                    prepared[key],
                )
            except Unbuildable:
                return False
            return True

        picks = (
            themed.picks[game_id]
            if themed is not None
            else pick_words(
                wordlists[spec.wordlist].words, spec, day, count, seen, buildable
            )
        )
        for row, difficulty in picks:
            seen.add(row.word)
            items.append(
                made.get((row.word, difficulty))
                or build_item(
                    row,
                    spec,
                    day,
                    hint_limit,
                    difficulty,
                    themed is not None,
                    prepared[key],
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
