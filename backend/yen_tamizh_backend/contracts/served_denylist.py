"""The SERVED deny-list (row 16): the words that may never reach the board.

``config/served-denylist.json`` is a curated exclusion the DERIVED layer applies
after every automatic gate. It is the last gate, and it exists because the
automatic ones cannot express what it says.

The lexicon knows what a word IS; it does not know what makes a PUZZLE. The
highest-frequency Tamil surfaces are its grammar - the quotative particle, the
demonstratives, the pronoun paradigm - and because frequency is one axis of
difficulty they land in the EASY band, which is the band a player meets most. A
Daily whose answer is "and" or "this" is not a word puzzle. Beside them sit the
personal names and newspaper mastheads that a news corpus makes frequent and a
dictionary lists with a real sense, so nothing upstream can tell them from
vocabulary.

A part-of-speech rule was measured and REJECTED. ``pos`` is a UNION across 21
sources (docs/concepts/lexicon.md), so the same values appear on real
vocabulary: appa (father) and arasu (government) both carry ``interjection``,
and a rule keyed on the column would delete them. The union is correct - it is
what stops one authority's ranking from erasing another's true fact - and that
is exactly why it cannot double as a filter.

So the exclusion is NAMED, one word at a time, with the reason written beside
it. That is the honest shape for a judgement no column carries: a list of 72
words a reviewer can argue with, rather than a rule whose collateral damage is
invisible until a player meets it.

Two properties follow from what this file is NOT:

- It is not a word-hood verdict. Every word here is real Tamil, is attested, and
  STAYS in the published lexicon at ``datasets/lexicon/``. The exclusion is on
  SERVING only, so nothing downstream of the game - a dictionary lookup, a
  frequency study, a future Game that recognises rather than produces - loses a
  row.
- It is not a pattern. Matching is WHOLE-WORD and exact, never a prefix or a
  substring: ``entru`` denied must not take ``entrum`` with it, and a stem
  match over Tamil's agglutination would take dozens of real words per entry.

Both arrays are sorted, deduped across each other as well as within themselves,
and every entry carries a ``reason``, because a deny-list nobody can audit is a
list that grows by feel.
"""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yen_tamizh_backend.contracts.base import ChangelogEntry, SchemaModel

# The file that carries this schema is written by hand, so the date-stamp and
# its changelog live here: two writers of one schema picking their own dates is
# the drift CLAUDE.md section 11 exists to stop.
# Migration class is build-time rewrite-in-place.
SERVED_DENYLIST_VERSION = "2026-08-17T22:28"
SERVED_DENYLIST_CHANGELOG = (
    ChangelogEntry(
        version=SERVED_DENYLIST_VERSION,
        change=(
            "Three given names added to properNouns - anjanaa, sabaapathi, "
            "manimozhi - taking the list from 14 names to 17 and from 69 words "
            "to 72."
        ),
        why=(
            "A user playing the game was dealt them. All three sit below the "
            "frequency band the first pass screened: the list was curated from "
            "the top 400 by frequency and these rank 4,955, 7,967 and 10,841 "
            "in the served set. Each is also a real Tamil word - the chief of "
            "an assembly, gem-like speech, kohl - which is exactly why no "
            "automatic gate reaches them and why the entry has to be named by "
            "hand."
        ),
    ),
    ChangelogEntry(
        version="2026-08-17",
        change=(
            "Initial served deny-list: 55 function words and 14 proper nouns, "
            "each with the reason it is off the board."
        ),
        why=(
            "Row 16 - the 32,310 words the anagram served included Tamil's "
            "grammar and the personal names and mastheads a news corpus makes "
            "frequent, and because frequency is a difficulty axis they landed "
            "in the EASY band, which is the band a player meets most. No gate "
            "the lexicon can express separates them: a part-of-speech rule was "
            "measured and rejected because pos is a union across 21 sources, so "
            "appa and arasu both carry interjection. A named list with a reason "
            "per entry is the honest shape for a judgement no column carries."
        ),
    ),
)


class DeniedWord(BaseModel):
    """One denied surface and the reason it may not be a puzzle answer.

    ``reason`` is required and never rendered: it is for the reviewer deciding
    whether the next proposed entry belongs, which is the only thing standing
    between a curated list and a list that grows by feel. Where a word carries a
    real dictionary sense that is NOT what its frequency counts - ``kumaar`` is
    listed as "prince" and occurs 329,467 times because it is a surname - the
    reason says so, so nobody re-adds it as vocabulary that was wrongly cut.
    """

    model_config = ConfigDict(extra="forbid")

    word: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ServedDenylist(SchemaModel):
    """The words no Game may serve, split by WHY they are unservable.

    The split is not decoration. A function word is off the board because it is
    grammar rather than vocabulary, and that judgement is stable for the life of
    the language. A proper noun is off the board because a corpus made a name
    frequent, and that judgement follows whichever corpora are staged - so the
    two arrays age differently and a reviewer needs to know which kind of
    argument an entry is making before deciding whether it still holds.

    ``note`` is REQUIRED. The words deliberately KEPT are the whole difference
    between this list and the cruder rule it replaces, and a file that does not
    say which they are is a file the next contributor will "helpfully" widen.
    """

    note: str = Field(min_length=1)
    functionWords: list[DeniedWord] = Field(min_length=1)
    properNouns: list[DeniedWord] = Field(min_length=1)

    @model_validator(mode="after")
    def _entries_are_sorted_deduped_and_stated(self) -> Self:
        seen: set[str] = set()
        for name in ("functionWords", "properNouns"):
            entries: list[DeniedWord] = getattr(self, name)
            words = [entry.word for entry in entries]
            # A set written as a list: the order it is written in must not be
            # information, and sorted order is what makes the diff readable
            # when the next word lands.
            if words != sorted(words):
                raise ValueError(f"{name} must be sorted by word")
            for entry in entries:
                if not entry.word.strip():
                    raise ValueError(f"{name} has a blank word")
                if not entry.reason.strip():
                    raise ValueError(f"{entry.word} is denied with a blank reason")
                # Deduped ACROSS both arrays, not just within one: the same
                # word denied twice for two different reasons is two reviewers
                # disagreeing about which argument keeps it off the board.
                if entry.word in seen:
                    raise ValueError(f"{entry.word} is denied more than once")
                seen.add(entry.word)
        return self

    def words(self) -> frozenset[str]:
        """Every denied surface - the whole-word set the derived layer matches."""
        return frozenset(
            entry.word for entry in (*self.functionWords, *self.properNouns)
        )
