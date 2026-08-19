"""The wordle Game's puzzle-payload contract (wordle-puzzle).

wordle asks the player to guess a word of a fixed ezhuthu count inside a limited
number of attempts, marking every submitted row per position: right ezhuthu in
the right place, right ezhuthu somewhere else, or not in the word at all
(games.md ``wordle``). This is the per-Game ``payload`` schema a puzzle-file item
carries, and it is the THIRD of them - the anagram's and the missing-letters'
are unchanged, which is the whole claim one-schema-per-Game makes.

The payload is deliberately almost empty, and each thing it does NOT carry is a
decision:

- **The length does not travel.** How many cells the board has is
  ``len(segment(word))``, derived by the same Row 6 library both sides already
  run. A stored copy of a derived value is a drift surface (row 11 took
  ``ezhuthu`` off the published lexicon row on exactly these grounds, and Row 18
  kept the segmentation out of ``missing-letters-puzzle`` for the same reason),
  and here the drift would be player-visible: a board with more cells than the
  answer has ezhuthu can never be filled.
- **There is no alphabet, and no accept list.** The keyboard is a COMPOSER over
  the closed 247-ezhuthu inventory, so what a player may enter is a property of
  Tamil rather than of a puzzle, and shipping either per day would be bytes
  restating a constant. What a guess is CHECKED against is the answer alone; see
  ``_the_answer_is_typeable`` for the one thing that genuinely has to be
  verified per puzzle.
- **There is no ``alsoValid``.** The anagram and the missing-letters both have a
  third state - an entry that is a real served word but not today's - because
  their input methods can only produce a handful of strings and some of those
  are other words. A wordle guess is one of 247**N strings and is answered by
  its per-position marks, which say something true about EVERY guess. There is
  no state left for the field to name.

What it does carry beyond the answer is the same framing every other Game's
payload carries: how many attempts, the ladder of hints this row could honestly
answer, and the meaning strings the summary shows once the word is revealed.

**The answer ships in the clear, and that is forced rather than chosen.** The
marks are computed against the answer on the player's device, and there is no
runtime backend to ask (Holy Law #1), so the answer must be in the bundle by the
time the board is playable. Obfuscating it would ship its own decoder in the
same bundle - theatre that also costs the architecture its "a payload is
serializable, loggable, replayable" property (CLAUDE.md section 1a). The bank
already publishes six days of anagram and missing-letters answers ahead of time
on the same terms, so this is consistency rather than a new exposure; what makes
it acceptable is unchanged - there is no leaderboard and nothing to win by
reading ahead.
"""

from __future__ import annotations

from typing import Self

from pydantic import Field, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import Hint
from yen_tamizh_backend.ezhuthu import EZHUTHU_INVENTORY, segment

# The 247 ezhuthu a player can actually compose: twelve uyir, eighteen mei,
# eighteen by twelve uyirmei, and the aytham. Held as a set here purely so the
# per-puzzle check below is a membership test rather than a scan.
_TYPEABLE = frozenset(EZHUTHU_INVENTORY)


class WordlePuzzle(SchemaModel):
    """One wordle puzzle: the answer, how many rows to find it in, and its framing.

    ``attempts`` is the number of guesses. It is at least 2 because the marks on
    the FINAL row can never be acted on - a one-attempt board shows a player
    feedback about a puzzle that is already over, which is a scoreboard rather
    than a deduction game.

    ``meaning`` and ``translationEn`` are resolved at bake time and read by the
    summary, exactly as they are for the other two Games: the player downloads
    finished display strings, never the lexicon columns they came from.
    ``translationEn`` is the summary's demoted second line and never a hint - a
    paid rung the player cannot read is a rung that stole score.
    """

    word: str = Field(min_length=1)
    attempts: int = Field(ge=2)
    hints: list[Hint] | None = None
    meaning: str | None = Field(default=None, min_length=1)
    translationEn: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _the_board_has_positions_to_be_wrong_about(self) -> Self:
        units = segment(self.word)
        if len(units) < 2:
            raise ValueError(
                f"{self.word!r} is {len(units)} ezhuthu; a wordle board needs at "
                "least two positions, or there is nothing to be in the wrong place"
            )
        return self

    @model_validator(mode="after")
    def _the_answer_is_typeable(self) -> Self:
        """Every ezhuthu of the answer must be one the composer can produce.

        This is the Row 18 lesson transposed. There the bank was the input
        method, so an alternative the bank could not spell was a message that
        could never fire; here the 247-ezhuthu composer is the input method, so
        an answer holding a grantha letter, a digit, or a Latin character is a
        puzzle nobody can win - and the failure would arrive as a player running
        out of attempts, not as an error. The word CLASS gate upstream already
        keeps grantha and non-Tamil surfaces out of the served set, which is
        exactly why this is checked rather than assumed: a contract that only
        restates what the layer above promised is worth nothing the day that
        layer changes.
        """
        outside = sorted({unit for unit in segment(self.word) if unit not in _TYPEABLE})
        if outside:
            raise ValueError(
                f"{self.word!r} holds {outside}, which the ezhuthu composer cannot "
                "produce, so the puzzle would be unwinnable"
            )
        return self
