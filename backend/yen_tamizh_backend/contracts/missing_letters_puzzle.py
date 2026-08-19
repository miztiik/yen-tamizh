"""The missing-letters Game's puzzle-payload contract (missing-letters-puzzle).

missing-letters shows a word with whole ezhuthu punched out of it and asks the
player to put them back (games.md ``missing-letters``). This is the per-Game
``payload`` schema a puzzle-file item carries.

Three shape decisions are worth stating, because each one closes a way the Game
could lie to a player:

- **The segmentation does NOT travel.** ``blanks`` are indices into
  ``segment(word)``, not into a stored ezhuthu array. A stored copy of a derived
  value is a drift surface (the same argument that took ``ezhuthu`` off the
  published lexicon row in row 11), and the ezhuthu library is a shared Row 6
  twin that both sides already run - the anagram's own Game re-segments its
  answer rather than trusting the tiles it was handed. So the contract validates
  the indices against the LIVE segmentation, which is what makes a blank that
  splits a cluster impossible rather than merely discouraged.
- **The choice bank is REQUIRED, not optional.** There is no Tamil keyboard in
  this game and there is not going to be one, so a payload with nothing to pick
  from is a puzzle nobody can answer. It is also strictly bigger than the holes
  it fills: a bank that is exactly the answer has no decision in it.
- **``alsoValid`` is what the player can ACTUALLY enter.** A mask with more than
  one served answer is recorded rather than refused, on the same terms as the
  anagram's ``alsoValid`` (schemas.md: whether the tiles spell something else is
  RECORDED, not required) - but an alternative the choice bank cannot spell is
  bytes for a message that can never fire, so the contract requires every
  alternative to fit the mask AND be reachable from the bank.
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Self

from pydantic import Field, StringConstraints, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import Hint
from yen_tamizh_backend.ezhuthu import segment

# One ezhuthu: a non-empty grapheme-cluster string (core-loop.md). The generator
# produces these with the shared segmentation library; splitting a cluster is
# what this whole contract exists to prevent.
Ezhuthu = Annotated[str, StringConstraints(min_length=1)]


class MissingLettersPuzzle(SchemaModel):
    """One missing-letters puzzle: a word, its holes, and what may fill them.

    ``blanks`` are positions in ``segment(word)``, sorted and distinct. Every
    index is validated against the live segmentation, so a blank is always a
    WHOLE ezhuthu and never half a cluster - and a puzzle can never blank the
    whole word, because a word with no visible ezhuthu is not a puzzle, it is a
    blank.

    ``choices`` is the bank the player picks from, already ordered for display.
    It holds at least the blanked ezhuthu (counted with multiplicity, so a word
    that hides the same ezhuthu twice really does offer two of them) plus at
    least one decoy.

    ``meaning`` and ``translationEn`` are resolved at bake time and read by the
    summary, exactly as they are for the anagram: the player downloads finished
    display strings, never the lexicon columns they came from. ``translationEn``
    is the summary's demoted second line and never a hint - a paid rung the
    player cannot read is a rung that stole score.
    """

    word: str = Field(min_length=1)
    blanks: list[int] = Field(min_length=1)
    choices: list[Ezhuthu] = Field(min_length=2)
    attempts: int = Field(ge=1)
    hints: list[Hint] | None = None
    meaning: str | None = Field(default=None, min_length=1)
    translationEn: str | None = Field(default=None, min_length=1)
    alsoValid: list[str] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _blanks_index_whole_ezhuthu(self) -> Self:
        units = segment(self.word)
        if self.blanks != sorted(set(self.blanks)):
            raise ValueError(f"blanks must be sorted and distinct: {self.blanks}")
        out_of_range = [i for i in self.blanks if i < 0 or i >= len(units)]
        if out_of_range:
            raise ValueError(
                f"blanks {out_of_range} fall outside the {len(units)} ezhuthu of "
                f"{self.word!r}"
            )
        if len(self.blanks) >= len(units):
            raise ValueError(
                f"blanks hide all {len(units)} ezhuthu of {self.word!r}; a puzzle "
                "must show at least one"
            )
        return self

    @model_validator(mode="after")
    def _the_bank_can_fill_the_blanks_and_still_offer_a_choice(self) -> Self:
        units = segment(self.word)
        needed = Counter(units[i] for i in self.blanks)
        available = Counter(self.choices)
        short = {unit: count for unit, count in needed.items() if available[unit] < count}
        if short:
            raise ValueError(f"choices cannot fill the blanks of {self.word!r}: {short}")
        if len(self.choices) <= len(self.blanks):
            raise ValueError(
                f"choices holds {len(self.choices)} ezhuthu for {len(self.blanks)} "
                "blanks, which is an answer rather than a choice"
            )
        return self

    @model_validator(mode="after")
    def _alternatives_fit_the_mask_and_the_bank(self) -> Self:
        if self.alsoValid is None:
            return self
        units = segment(self.word)
        hidden = set(self.blanks)
        available = Counter(self.choices)
        for other in self.alsoValid:
            if other == self.word:
                raise ValueError(f"alsoValid repeats the answer {self.word!r}")
            parts = segment(other)
            if len(parts) != len(units):
                raise ValueError(
                    f"alsoValid {other!r} has {len(parts)} ezhuthu, not {len(units)}"
                )
            shown = [i for i in range(len(units)) if i not in hidden]
            if any(parts[i] != units[i] for i in shown):
                raise ValueError(
                    f"alsoValid {other!r} does not fit the mask of {self.word!r}"
                )
            fillers = Counter(parts[i] for i in sorted(hidden))
            if any(available[unit] < count for unit, count in fillers.items()):
                raise ValueError(
                    f"alsoValid {other!r} cannot be spelled from choices; an "
                    "alternative the player can never enter is a message that "
                    "can never fire"
                )
        return self
