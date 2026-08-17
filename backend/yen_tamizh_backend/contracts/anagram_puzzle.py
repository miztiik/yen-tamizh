"""The anagram Game's puzzle-payload contract (anagram-puzzle).

anagram is the proven starter Game (games.md): unscramble ezhuthu tiles into the
target word. This is the per-Game ``payload`` schema a puzzle-file item carries;
its ``tiles`` are ezhuthu strings ALREADY segmented by the generator (Row 13) via
the shared ezhuthu library - segmentation is not this schema's job. Per-Game
payload schemas keep Games evolving independently (Fowler, schemas.md).
"""

from __future__ import annotations

from typing import Annotated, Self

from pydantic import Field, StringConstraints, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import Hint

# One ezhuthu tile is a non-empty grapheme-cluster string (core-loop.md), produced
# by the shared ezhuthu segmentation library at generation time.
Ezhuthu = Annotated[str, StringConstraints(min_length=1)]


class AnagramPuzzle(SchemaModel):
    """One anagram puzzle: a target word, its scrambled ezhuthu tiles, and rules.

    ``meaning``, ``translationEn`` and ``alsoValid`` are RESOLVED at bake time,
    never at play time. The generator holds the lexicon columns and the whole
    served wordlist; the player downloads what those resolved to, not the inputs
    they resolved from - so all three are finished display values, never arrays
    the Game would have to pick from.

    ``meaning`` is one already-rendered Tamil display string - what the word
    means, shown free on the summary once the word is revealed. It is absent
    when the lexicon has nothing to say, and an absent meaning renders as the
    word alone: an empty slot would advertise a hole in the data.

    ``translationEn`` is the summary's DEMOTED second line and nothing else. It
    is never a hint and never the meaning line: a paid rung the player cannot
    read is a rung that stole score, so the meaning rung is omitted rather than
    answered in English.

    ``alsoValid`` lists the OTHER served words the same tiles spell. It has to
    be baked because the Game cannot derive it - ``anagramFanOut`` is a count,
    and reading a wordlist at runtime is forbidden - and without it a player who
    arranges a real Tamil word gets a flat rejection instead of "that is a word,
    but not today's". It is absent for the overwhelming majority of words: true
    Tamil co-anagrams are rare.
    """

    word: str = Field(min_length=1)
    tiles: list[Ezhuthu] = Field(min_length=1)
    reveal: int | None = Field(default=None, ge=0)
    timeLimitSec: int = Field(ge=0)
    attempts: int = Field(ge=1)
    hints: list[Hint] | None = None
    meaning: str | None = Field(default=None, min_length=1)
    translationEn: str | None = Field(default=None, min_length=1)
    alsoValid: list[str] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _alternatives_exclude_the_answer(self) -> Self:
        # A puzzle that lists its own answer as an alternative arrangement would
        # have the Game tell a player their correct solve was "a word, but not
        # today's".
        if self.alsoValid is not None and self.word in self.alsoValid:
            raise ValueError(f"alsoValid repeats the answer {self.word!r}")
        return self
