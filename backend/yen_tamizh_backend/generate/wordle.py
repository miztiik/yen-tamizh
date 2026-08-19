"""Turn one derived-wordlist row into a playable ``wordle`` payload.

The Game (Row 19) knows how to mark a guess; this knows how to set one. It is
the THINNEST builder in the engine, and that is the finding rather than an
oversight: an anagram has to scramble tiles, a missing-letters board has to
choose a mask and a bank, but a wordle's puzzle IS the word. Everything a player
does is composed at play time from a keyboard that is a constant, so there is
nothing per-puzzle left to arrange.

Three things this module owns:

- **The answer is passed through, never transformed.** No scramble, no mask, no
  bank. What the payload adds to the word is framing: how many attempts, the
  rungs this row can honestly answer, and the meaning the summary shows once the
  word is out.
- **Nothing here reads a clock or a random source.** There is no shuffle to
  seed, so ``seed_text`` arrives and is deliberately unused - the day loop hands
  every builder the same arguments, and a builder that needs none of them says
  so rather than inventing a use. Determinism is therefore total by
  construction: the same row and the same config bake the same bytes.
- **The ladder is two rungs, and ``firstEzhuthu`` is not one of them.** See
  ``HINT_FIELDS``.

What is NOT here is the accept list. A wordle in English rejects a guess that is
not a word; this one accepts any complete row of ezhuthu, so no list is baked,
consulted, or shipped. The reasoning is in docs/concepts/games.md and in the
schemas doc: the best accept list this repo could build is the published
headword class, which withholds 1,395,218 classified ``inflected`` surfaces -
precisely the forms a speaker of an agglutinative language types - and a
rejection is a FAVOUR (it hands the row back), so accepting everything is the
strictly harsher setting and the only one that can never tell a player their
real Tamil word is not a word.
"""

from __future__ import annotations

from yen_tamizh_backend.contracts.base import ChangelogEntry
from yen_tamizh_backend.contracts.common import Hint
from yen_tamizh_backend.contracts.daily_generator import GameGeneration
from yen_tamizh_backend.contracts.game_wordlist import GameWord
from yen_tamizh_backend.contracts.wordle_puzzle import WordlePuzzle
from yen_tamizh_backend.generate import hints as hint_ladder

GAME_ID = "wordle"

_SCHEMA_VERSION = "2026-08-19"
_CHANGELOG = [
    ChangelogEntry(
        version=_SCHEMA_VERSION,
        change="Initial baked wordle payload: the answer word and its attempt budget.",
        why=(
            "Row 19 - the third Game, and the one that shows how little a "
            "payload schema can be. The board's width is len(segment(word)) "
            "rather than a stored field, on the same grounds Row 18 kept the "
            "segmentation out of missing-letters-puzzle: a stored copy of a "
            "derived value is a drift surface, and a board wider than its "
            "answer can never be filled. No alphabet and no accept list travel "
            "- the composer keyboard is the closed 247-ezhuthu inventory, so "
            "what a player may enter is a fact about Tamil rather than about a "
            "puzzle. The answer ships in the clear because the marks are "
            "computed on the player's device and there is no runtime backend "
            "to ask (Holy Law #1)."
        ),
    )
]

# The CLOSED vocabulary a hint template may name for THIS Game.
#
# ``firstEzhuthu`` is absent for a reason that is the mirror image of the
# missing-letters board's. There the rung is refused because the answer's other
# ezhuthu are already printed; here it is refused because the player can BUY the
# same fact with a guess, and the board answers it more precisely than the rung
# would - one row spent on any word tells you about five positions at once. A
# rung that is strictly worse than the move the player was going to make anyway
# is a rung that charges for nothing, which is the same mistake the deleted
# ``length`` rung made in a different costume.
HINT_FIELDS = frozenset({"category", "meaning"})


def hint_values(row: GameWord, spec: GameGeneration, themed: bool) -> dict[str, str]:
    """Exactly the hint fields this row can honestly fill, on this kind of day.

    On a THEMED day ``category`` is absent for every row, not just the ones
    without one: the theme is announced free in the round header, so the rung
    would charge for a fact already on screen.
    """
    values: dict[str, str] = {}
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
    """Render the first ``limit`` rungs this row can HONESTLY answer."""
    return hint_ladder.build_hints(
        row, spec, limit, hint_values(row, spec, themed), HINT_FIELDS
    )


def build_puzzle(
    row: GameWord,
    spec: GameGeneration,
    seed_text: str,
    hint_limit: int,
    themed: bool = False,
) -> WordlePuzzle:
    """Build one validated wordle puzzle from a derived-wordlist row.

    ``seed_text`` is accepted and unused: this builder makes no random choice,
    so taking the seed and ignoring it keeps every Game's builder callable the
    same way while saying plainly that there is nothing here to vary.
    """
    del seed_text
    return WordlePuzzle(
        version=_SCHEMA_VERSION,
        changelog=_CHANGELOG,
        word=row.word,
        attempts=spec.attempts,
        hints=build_hints(row, spec, hint_limit, themed) or None,
        meaning=hint_ladder.display_meaning(row),
        translationEn=row.translationEn,
    )
