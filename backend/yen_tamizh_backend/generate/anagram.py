"""Turn one derived-wordlist row into a playable ``anagram-puzzle`` payload.

The Game (Row 12) knows how to play an anagram; this knows how to BUILD one. It
takes a word the derived layer already vouched for, scrambles its ezhuthu, and
attaches the rules the config declares - attempts, a time limit, a head start,
and the honest hints the row's own fields support.

Two guarantees this module owns:

- **The scramble is never the answer.** A pre-solved puzzle is not a puzzle
  (Palm). The seeded shuffle is rotated until it differs from the solved order.
- **A tile is an ezhuthu.** Tiles come from the row's ``ezhuthu`` array (Row 6
  segmentation), never from a code-point split, so they rejoin to exactly the
  answer word.
"""

from __future__ import annotations

from yen_tamizh_backend.contracts.anagram_puzzle import AnagramPuzzle
from yen_tamizh_backend.contracts.base import ChangelogEntry
from yen_tamizh_backend.contracts.common import Hint
from yen_tamizh_backend.contracts.daily_generator import GameGeneration
from yen_tamizh_backend.contracts.game_wordlist import GameWord
from yen_tamizh_backend.generate.seed import seeded_shuffle

_SCHEMA_VERSION = "2026-08-13"
_CHANGELOG = [
    ChangelogEntry(
        version=_SCHEMA_VERSION,
        change="Initial baked anagram payload: scrambled ezhuthu tiles plus rules.",
        why="Row 13 - the daily engine's first Game payload.",
    )
]


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


def build_hints(row: GameWord, spec: GameGeneration, limit: int) -> list[Hint]:
    """Render up to ``limit`` configured hints for one word from its own fields.

    A hint's TEXT is per-puzzle data, so it is generated here rather than kept
    in ``config/copy.json`` - but the wording is still copy, so the template
    lives in the generator config and only the values come from the row. A
    template naming a field the row does not carry fails loudly (an honest hint
    cannot be invented). ``limit`` is the app config's per-Game allowance, so a
    day never bakes more help than the game is willing to offer.
    """
    if row.hints is None or limit <= 0:
        return []
    values = {"firstEzhuthu": row.hints.firstEzhuthu, "length": row.hints.length}
    return [
        Hint(kind=hint.kind, text=hint.template.format(**values), cost=hint.cost)
        for hint in spec.hints[:limit]
    ]


def build_puzzle(
    row: GameWord, spec: GameGeneration, seed_text: str, hint_limit: int
) -> AnagramPuzzle:
    """Build one validated anagram puzzle from a derived-wordlist row."""
    return AnagramPuzzle(
        version=_SCHEMA_VERSION,
        changelog=_CHANGELOG,
        word=row.word,
        tiles=scramble(list(row.ezhuthu), seed_text),
        reveal=spec.reveal,
        timeLimitSec=spec.timeLimitSec,
        attempts=spec.attempts,
        hints=build_hints(row, spec, hint_limit) or None,
    )


def difficulty_of(row: GameWord, spec: GameGeneration) -> str:
    """The configured difficulty bucket for a word's ezhuthu count.

    Falls back to the widest band's id rather than inventing one, so a word
    outside every configured range still ships with a real difficulty slug.
    """
    length = len(row.ezhuthu)
    for band in spec.difficulties:
        if band.minLength <= length <= band.maxLength:
            return band.id
    return spec.difficulties[-1].id
