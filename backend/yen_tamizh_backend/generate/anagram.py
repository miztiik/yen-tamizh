"""Turn one derived-wordlist row into a playable ``anagram-puzzle`` payload.

The Game (Row 12) knows how to play an anagram; this knows how to BUILD one. It
takes a word the derived layer already vouched for, scrambles its ezhuthu, and
attaches the rules the config declares - attempts, a time limit, a head start,
the ladder of hints the row can honestly answer, what the word means, and the
other words its tiles spell.

Three guarantees this module owns:

- **The scramble is never the answer.** A pre-solved puzzle is not a puzzle
  (Palm). The seeded shuffle is rotated until it differs from the solved order.
- **A tile is an ezhuthu.** Tiles come from the row's ``ezhuthu`` array (Row 6
  segmentation), never from a code-point split, so they rejoin to exactly the
  answer word.
- **A hint is honest, Tamil, and never the answer.** A rung this row cannot
  answer is dropped rather than invented, a phrase carrying Latin script is
  never sold, and a rendered rung that would spell the answer out is dropped
  too. The machinery for that lives in ``generate/hints.py``, shared with every
  other Game; what belongs HERE is which fields the anagram is allowed to sell.
"""

from __future__ import annotations

from collections.abc import Iterable

from yen_tamizh_backend.contracts.anagram_puzzle import AnagramPuzzle
from yen_tamizh_backend.contracts.base import ChangelogEntry
from yen_tamizh_backend.contracts.common import Hint
from yen_tamizh_backend.contracts.daily_generator import GameGeneration
from yen_tamizh_backend.contracts.game_wordlist import GameWord
from yen_tamizh_backend.generate import hints as hint_ladder
from yen_tamizh_backend.generate.seed import seeded_shuffle

_SCHEMA_VERSION = "2026-08-17T18:00"
_CHANGELOG = [
    ChangelogEntry(
        version=_SCHEMA_VERSION,
        change=(
            "Added the optional meaning, translationEn and alsoValid fields to "
            "the baked payload."
        ),
        why=(
            "Row 14 - a player who solves a word should learn what it means, "
            "and the summary is where that costs nothing. All three are "
            "RESOLVED here rather than shipped as inputs: the generator holds "
            "the lexicon columns and the whole served wordlist, so the player "
            "downloads finished display values instead of the arrays they came "
            "from. translationEn is the summary's demoted second line and "
            "never a hint, which is what gives the lexicon's English column a "
            "reader without putting English on the stage. alsoValid has to be "
            "baked at all because the Game cannot derive it - anagramFanOut is "
            "a count, and reading a wordlist at runtime is forbidden - and "
            "without it an arrangement that is real Tamil gets a flat "
            "rejection instead of 'that is a word, but not today's'. All three "
            "are absent on a row that has none, so every day baked before this "
            "still validates."
        ),
    ),
    ChangelogEntry(
        version="2026-08-13",
        change="Initial baked anagram payload: scrambled ezhuthu tiles plus rules.",
        why="Row 13 - the daily engine's first Game payload.",
    ),
]

# The CLOSED vocabulary a hint template may name for THIS Game. A template
# naming anything else is a typo in config and fails the bake; a template naming
# one of these that a particular ROW cannot fill has its rung skipped for that
# row.
#
# ``length`` is deliberately absent. The rung that charged for the tile count
# already on the player's screen was deleted, and leaving the field fillable
# would let one config line put it back.
HINT_FIELDS = frozenset({"firstEzhuthu", "category", "meaning"})


def scramble(ezhuthu: list[str], seed_text: str) -> list[str]:
    """Deterministically reorder the ezhuthu so the tray is never pre-solved.

    A rotation is enough to break the (rare) case where the seeded shuffle lands
    back on the solved order; a word whose ezhuthu are all identical has no other
    arrangement, and is returned unchanged rather than looping forever.
    """
    order = seeded_shuffle(ezhuthu, seed_text)
    for _ in range(len(order)):
        if order != ezhuthu:
            return order
        order = order[1:] + order[:1]
    return order


def hint_values(row: GameWord, spec: GameGeneration, themed: bool) -> dict[str, str]:
    """Exactly the hint fields this row can honestly fill, on this kind of day.

    A field absent from this map is a rung the row does not get. On a THEMED day
    ``category`` is absent for every row, not just the ones without one: the
    theme is announced free in the round header, so the rung would charge for a
    fact already on screen - and because a missing rung shortens the ladder, a
    three-rung day beside an ordinary two-rung one would announce the theme
    before the player had spent anything.
    """
    values: dict[str, str] = {}
    if row.hints is not None:
        values["firstEzhuthu"] = row.hints.firstEzhuthu
    if not themed:
        category = hint_ladder.category_tag(row, spec)
        if category is not None:
            values["category"] = category
    meaning = hint_ladder.sellable_meaning(row)
    if meaning is not None:
        values["meaning"] = meaning
    return values


def build_hints(
    row: GameWord, spec: GameGeneration, limit: int, themed: bool = False
) -> list[Hint]:
    """Render the first ``limit`` rungs this row can HONESTLY answer.

    The rendering rules are shared (``generate/hints.py``); what this adds is
    the anagram's own field vocabulary and the values a row can fill.
    """
    return hint_ladder.build_hints(
        row, spec, limit, hint_values(row, spec, themed), HINT_FIELDS
    )


def build_puzzle(
    row: GameWord,
    spec: GameGeneration,
    seed_text: str,
    hint_limit: int,
    themed: bool = False,
    also_valid: Iterable[str] = (),
) -> AnagramPuzzle:
    """Build one validated anagram puzzle from a derived-wordlist row.

    ``also_valid`` is the day loop's answer to "what else do these tiles
    spell" - the OTHER words the same served set holds for this multiset. It is
    passed in rather than derived, because only the caller holds the wordlist
    the day actually drew from, which on a themed day is the theme's own set.
    """
    return AnagramPuzzle(
        version=_SCHEMA_VERSION,
        changelog=_CHANGELOG,
        word=row.word,
        tiles=scramble(list(row.ezhuthu), seed_text),
        reveal=spec.reveal,
        timeLimitSec=spec.timeLimitSec,
        attempts=spec.attempts,
        hints=build_hints(row, spec, hint_limit, themed) or None,
        meaning=hint_ladder.display_meaning(row),
        translationEn=row.translationEn,
        alsoValid=sorted(also_valid) or None,
    )
