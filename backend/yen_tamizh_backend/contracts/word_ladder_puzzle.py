"""The word-ladder Game's puzzle-payload contract (word-ladder-puzzle).

word-ladder (Tamil: sol eeni, சொல் ஏணி) hands the player a short Tamil word and
asks them to climb: add exactly ONE ezhuthu, rearrange the letters however they
like, and land on another real word - then do it again. This is the per-Game
``payload`` schema a puzzle-file item carries, and it is the SIXTH of them; the
five before it are unchanged, which is what one-schema-per-Game keeps promising.

**The rung rule is the whole contract, and it is checked over MULTISETS.**
Rung ``n+1`` differs from rung ``n`` by exactly one ADDED ezhuthu and nothing
else: formally ``Counter(next) - Counter(prev)`` totals one and
``Counter(prev) - Counter(next)`` is empty. Stated that way, rearrangement is
free by construction rather than by a second rule, and no ezhuthu can be
silently swapped out on the way up. It is a multiset over EZHUTHU and never over
code points, because ``கா`` is one letter that a code-point walk would read as
``க`` plus a floating vowel sign - which is how a "ladder" could climb from
``கம்`` to ``காம்`` while claiming to have added nothing at all.

Four more shape decisions, each closing a way this Game could lie to a player:

- **The segmentation does NOT travel, and neither does the added ezhuthu.**
  A rung ships its ``word``; its tiles are ``segment(word)`` and the letter it
  added is the multiset difference from the rung below. Both are derived values,
  and a stored copy of a derived value is a drift surface - the ruling the
  missing-letters board made about ``blanks`` and the published lexicon made
  about ``ezhuthu``. The plan sketched ``{ word, ezhuthu, added? }`` and a
  ``startEzhuthuCount`` beside it; all three are second statements of a fact the
  word already makes, and the one that could disagree with the word is the one
  the player would be shown.
- **The choice bank is REQUIRED, not optional.** There is no Tamil keyboard in
  this game and there is not going to be one, so a player asked to add one of
  247 letters has no way to say which. ``choices`` is what an addition is picked
  FROM, it holds every ezhuthu the climb needs counted with multiplicity, and it
  is strictly bigger than the climb needs - a bank that is exactly the answer
  has no decision in it. One bank serves the whole ladder rather than one per
  rung: it is the smaller payload, and WHICH letter to spend now is then part of
  the puzzle instead of a fresh eight-way guess at every step.
- **``alsoValid`` is what the player can ACTUALLY reach.** A bank letter added to
  the rung below often spells some OTHER served word, so a climber who lands on
  a real Tamil word must be told "that is a word, but not this rung's" rather
  than given a red cross - the settled precedent of the five boards before this
  one (schemas.md). Narrowed twice, for the same reason the missing-letters
  board narrowed its own list: an alternative must be reachable from the rung
  BELOW by adding one ezhuthu, and that ezhuthu must be in the bank, or it is
  bytes for a message that can never fire. The first rung is GIVEN, so it is the
  one rung that carries none.
- **There is no attempt budget and no baked hint ladder.** A wrong arrangement
  costs the climber time, not a life: the ladder is the one board here whose
  progress is a chain, so ending it mid-way would take away the rungs already
  earned. And every rung the shared ladder could sell is about ONE particular
  word - the next one - which the Game already knows how to price at play time
  as a reveal, exactly as the crossword prices an entry. So this payload carries
  neither field, which is what the search board and the crossword also concluded
  about ``hints`` for their own reasons.
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.ezhuthu import EZHUTHU_INVENTORY, segment

# One ezhuthu: a non-empty grapheme-cluster string (core-loop.md).
Ezhuthu = Annotated[str, StringConstraints(min_length=1)]

# The 247 ezhuthu, held as a set so a per-tile check is a membership test.
_LETTERS = frozenset(EZHUTHU_INVENTORY)


def added_ezhuthu(lower: str, higher: str) -> str:
    """The single ezhuthu ``higher`` adds over ``lower``, or a loud failure.

    The one definition of the rung rule, stated here beside the contract so the
    validator, the generator and the tests cannot each invent their own. It is a
    multiset difference in BOTH directions: the forward one says exactly one
    letter arrived, and the backward one says none left, which together are what
    make rearrangement free and substitution impossible.
    """
    below = Counter(segment(lower))
    above = Counter(segment(higher))
    gained = above - below
    lost = below - above
    if lost:
        raise ValueError(
            f"{higher!r} drops {sorted(lost.elements())} from {lower!r}; a rung may "
            "only add"
        )
    if sum(gained.values()) != 1:
        raise ValueError(
            f"{higher!r} adds {sorted(gained.elements())} to {lower!r}; a rung adds "
            "exactly one ezhuthu"
        )
    return next(iter(gained))


class LadderRung(BaseModel):
    """One step of the climb: the word, what it means, and what else reaches it.

    ``meaning`` is resolved at bake time and shown FREE beside the rung once the
    player has climbed it (the Row 14 rule that a solved word explains itself).
    It rides the RUNG rather than the puzzle because a ladder asks for several
    words at once and the session summary carries one line per item, so this
    board is the only place these meanings can ever be read - the same reasoning
    the search board's ``WordSearchTarget`` made. ``translationEn`` does not
    travel for the same reason it does not travel there: an English gloss under
    every rung of a Tamil ladder doubles the board's height to say something the
    paid ladder is banned from selling anyway.
    """

    model_config = ConfigDict(extra="forbid")

    word: str = Field(min_length=1)
    meaning: str | None = Field(default=None, min_length=1)
    alsoValid: list[str] | None = Field(default=None, min_length=1)


class WordLadderPuzzle(SchemaModel):
    """One climb: the rungs in order, the bank they are built from, and the clock.

    ``rungs`` are ordered from the shortest word up, and the first one is GIVEN -
    it is the ledge the player starts on rather than a word they are asked for.
    A ladder of two would be a single question, so three is the floor.
    """

    rungs: list[LadderRung] = Field(min_length=3)
    choices: list[Ezhuthu] = Field(min_length=2)
    timeLimitSec: int = Field(ge=0)

    @model_validator(mode="after")
    def _every_tile_is_a_letter_of_tamil(self) -> Self:
        """Two claims per tile, and they are different.

        ``segment(unit) == [unit]`` says the tile holds ONE grapheme cluster;
        membership in the 247 says that cluster is a LETTER of Tamil. A lone
        vowel sign - what splitting a cluster leaves behind - passes the first
        and fails the second, so both are needed. Checked on the bank as well as
        on the rungs, because the bank is what the player taps.
        """
        for word in [rung.word for rung in self.rungs]:
            for unit in segment(word):
                if unit not in _LETTERS:
                    raise ValueError(
                        f"{word!r} holds {unit!r}, which is not a letter of Tamil"
                    )
        for unit in self.choices:
            if segment(unit) != [unit]:
                raise ValueError(f"choices holds {unit!r}, which is not one ezhuthu")
            if unit not in _LETTERS:
                raise ValueError(
                    f"choices holds {unit!r}, which is not a letter of Tamil"
                )
        return self

    @model_validator(mode="after")
    def _each_rung_adds_exactly_one_ezhuthu(self) -> Self:
        """ORACLE - walk the ladder and prove every step is one added letter.

        Stated against the WORDS the player is shown rather than against the
        generator's bookkeeping, so a search bug cannot ship a ladder whose
        printed rungs do not actually climb. Strictly increasing length falls out
        of the rule rather than being asserted beside it.
        """
        for below, above in zip(self.rungs, self.rungs[1:]):
            added_ezhuthu(below.word, above.word)
        return self

    @model_validator(mode="after")
    def _the_bank_can_climb_and_still_offer_a_choice(self) -> Self:
        needed = Counter(
            added_ezhuthu(below.word, above.word)
            for below, above in zip(self.rungs, self.rungs[1:])
        )
        available = Counter(self.choices)
        short = {
            unit: count for unit, count in needed.items() if available[unit] < count
        }
        if short:
            raise ValueError(f"choices cannot climb the ladder: {short}")
        additions = sum(needed.values())
        if len(self.choices) <= additions:
            raise ValueError(
                f"choices holds {len(self.choices)} ezhuthu for {additions} additions, "
                "which is an answer rather than a choice"
            )
        return self

    @model_validator(mode="after")
    def _alternatives_are_reachable_from_the_rung_below(self) -> Self:
        """What else the bank spells is RECORDED - but only what it can spell.

        The first rung is given, so nothing was produced to reach it and an
        alternative there would name a word the player never had a chance to
        enter. Every other alternative has to be one added ezhuthu above the rung
        below AND that ezhuthu has to be in the bank, which is the Row 18 lesson
        transposed: an alternative the player can never enter is a message that
        can never fire.
        """
        if self.rungs[0].alsoValid is not None:
            raise ValueError(
                f"the first rung {self.rungs[0].word!r} is given, so it can carry no "
                "alternatives"
            )
        available = set(self.choices)
        for below, above in zip(self.rungs, self.rungs[1:]):
            if above.alsoValid is None:
                continue
            if len(set(above.alsoValid)) != len(above.alsoValid):
                raise ValueError(f"alsoValid repeats a word: {sorted(above.alsoValid)}")
            for other in above.alsoValid:
                if other == above.word:
                    raise ValueError(f"alsoValid repeats the answer {above.word!r}")
                unit = added_ezhuthu(below.word, other)
                if unit not in available:
                    raise ValueError(
                        f"alsoValid {other!r} needs {unit!r}, which the bank does not "
                        "hold; an alternative the player can never enter is a message "
                        "that can never fire"
                    )
        return self
