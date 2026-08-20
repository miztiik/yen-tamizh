"""The crossword Game's puzzle-payload contract (crossword-puzzle).

crossword (Tamil: sorkattam, சொற்கட்டம்) lays several Tamil words across and down
one board so that wherever two of them meet they agree on the ezhuthu in the
shared cell, and asks the player to write each word in from its clue. This is
the per-Game ``payload`` schema a puzzle-file item carries, and it is the FIFTH
of them; the four before it are unchanged, which is what one-schema-per-Game
keeps promising.

**The interlock is the whole contract, and it is checked by reading the GRID.**
The payload does not ship a solution grid: it ships where each word starts and
which way it runs, and this model BUILDS the grid from those entries. Two
entries that disagree about a shared cell cannot both write it, so the build
itself is the check - and then every entry is read back OUT of the grid it
helped build and compared to its own segmentation. A placement bug therefore
cannot ship a board whose across and down answers contradict each other, and the
proof is stated against the board the player sees rather than against the
solver's bookkeeping.

Four more things this model refuses, each of them a way a grid can be wrong
while every individual word is right:

- **A run must be MAXIMAL.** The cell before an entry's start and the cell after
  its end must be off the board or blocked. Without that, a board could print
  five open cells in a row and call four of them the answer, and the player
  would be filling a slot the puzzle never described.
- **The board must be CONNECTED.** Every entry has to reach every other one
  through shared cells. Two independent clusters on one board are two puzzles
  printed on the same paper, and the crossings are the only reason a crossword
  is more than a list of definitions.
- **The numbers must be CANONICAL.** Numbering is not free-form: the cells that
  START an entry are numbered in reading order, and an across and a down
  starting on the same cell share a number. That is what the player reads down
  the clue list, so a number that disagreed with the board would be a wrong
  answer printed in the right place.
- **A clue may not SPELL its answer.** The lexicon's own definitions
  occasionally contain their own headword - measured at 3.7 percent of the
  served set - and a clue that prints the word is not a clue.

``rows`` and ``cols`` DO travel here, which is the opposite of what
``word-search-puzzle`` decided, and the difference is real rather than a
change of mind: a search board ships its grid as a list of lists, so its shape
is ``len(grid)`` by ``len(grid[0])`` and storing it again would be a second copy
of a derived value. A crossword ships no grid at all - blocked cells have no
content to ship - so the board's extent is a fact only the payload can state.
Every entry is then checked to lie inside it.

``alsoValid`` is the same idea the other four boards already ship (schemas.md:
whether the board also admits something else is RECORDED, not required). Here it
is narrow on purpose. A word that merely fits the crossings answers a DIFFERENT
clue and is simply wrong; what earns a place on this list is a word that fits
the crossings AND is a listed synonym of the answer, because that one arguably
answers the same clue. Measured over 900 generated boards, 0.8 to 2.5 percent of
crossing-rivals are such a synonym and 4 to 17 percent of boards hold at least
one, so the list is rarely long and never empty for nothing.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.ezhuthu import EZHUTHU_INVENTORY, segment

# One ezhuthu: a non-empty grapheme-cluster string (core-loop.md).
Ezhuthu = Annotated[str, StringConstraints(min_length=1)]

# The two ways an entry can run. A crossword has no diagonals: an entry has to
# be readable as a row or a column of the printed board, and the numbering the
# player reads down the clue list is defined over exactly these two.
Direction = Literal["across", "down"]

# Each direction as the (row, col) step it takes.
STEPS: dict[str, tuple[int, int]] = {"across": (0, 1), "down": (1, 0)}

# The 247 ezhuthu, held as a set so the per-cell check is a membership test.
_LETTERS = frozenset(EZHUTHU_INVENTORY)


class CrosswordCell(BaseModel):
    """One cell address: a row and a column, both counted from the top-left."""

    model_config = ConfigDict(extra="forbid")

    row: int = Field(ge=0)
    col: int = Field(ge=0)


class CrosswordEntry(BaseModel):
    """One answer on the board: where it starts, which way it runs, and its clue.

    ``clue`` is resolved at bake time from the lexicon's own Tamil sense for the
    answer. It is not invented and it is not translated: an English gloss under
    a Tamil grid asks the player to solve a puzzle in a language the board is
    not written in. A word whose only recorded sense spells the word out, or
    carries Latin script, is not servable to this Game at all and is cut from
    the wordlist rather than clued badly here.

    ``alsoValid`` holds the words that fit this entry's CROSSED cells and are a
    listed synonym of the answer - the only rivals that can be said to answer
    the same clue. It travels so the Game can say "that is a word for the same
    thing, but not the one this grid was built on" instead of a red cross.
    """

    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1)
    direction: Direction
    start: CrosswordCell
    word: str = Field(min_length=1)
    clue: str = Field(min_length=1)
    alsoValid: list[str] | None = Field(default=None, min_length=1)


def entry_cells(entry: CrosswordEntry) -> list[tuple[int, int]]:
    """The cells one entry covers, from its start along its direction."""
    step_row, step_col = STEPS[entry.direction]
    return [
        (entry.start.row + step_row * index, entry.start.col + step_col * index)
        for index in range(len(segment(entry.word)))
    ]


def canonical_numbers(
    entries: list[CrosswordEntry],
) -> dict[tuple[int, int], int]:
    """The number every starting cell carries, in reading order.

    Standard crossword numbering, stated once so the model and the generator
    cannot each invent their own: the cells that begin an entry are collected,
    read left-to-right then top-to-bottom, and numbered from one. An across and
    a down beginning on the same cell therefore share a number, which is what
    lets a clue list say "3 across" and "3 down" of one square.
    """
    starts = sorted({(entry.start.row, entry.start.col) for entry in entries})
    return {cell: index for index, cell in enumerate(starts, start=1)}


class CrosswordPuzzle(SchemaModel):
    """One mini crossword: how big the board is, and every answer on it.

    Blocked cells are not listed. A cell is OPEN exactly when some entry covers
    it, so the mask is the union of the entries and there is no second statement
    of it that could disagree with the first.
    """

    rows: int = Field(ge=2)
    cols: int = Field(ge=2)
    entries: list[CrosswordEntry] = Field(min_length=2)

    @model_validator(mode="after")
    def _every_entry_is_on_the_board(self) -> Self:
        for entry in self.entries:
            for row, col in entry_cells(entry):
                if not (0 <= row < self.rows and 0 <= col < self.cols):
                    raise ValueError(
                        f"{entry.word!r} runs {entry.direction} from "
                        f"({entry.start.row},{entry.start.col}) off a "
                        f"{self.rows}x{self.cols} board"
                    )
        return self

    @model_validator(mode="after")
    def _every_cell_is_exactly_one_ezhuthu(self) -> Self:
        """Two claims per cell, and they are different.

        ``segment(unit) == [unit]`` says the cell holds ONE grapheme cluster;
        membership in the 247 says that cluster is a LETTER of Tamil. A lone
        vowel sign - what splitting a cluster leaves behind - passes the first
        and fails the second, so both are needed.
        """
        for entry in self.entries:
            units = segment(entry.word)
            if len(units) < 2:
                raise ValueError(
                    f"{entry.word!r} is {len(units)} ezhuthu; an entry a clue can "
                    "describe and another word can cross needs at least two"
                )
            for unit in units:
                if segment(unit) != [unit]:
                    raise ValueError(
                        f"{entry.word!r} holds {unit!r}, which is not one ezhuthu"
                    )
                if unit not in _LETTERS:
                    raise ValueError(
                        f"{entry.word!r} holds {unit!r}, which is not a letter of Tamil"
                    )
        return self

    @model_validator(mode="after")
    def _the_interlock_holds(self) -> Self:
        """ORACLE - build the grid from the entries, then read them back out of it.

        Writing the board is the first half of the check: two entries that want
        different ezhuthu in one cell cannot both write it, and that is exactly
        the failure a crossword must never ship. Reading each entry back out is
        the second half, and it is the half that matters, because it states the
        property against the CELLS rather than against the words the generator
        thought it placed.
        """
        grid: dict[tuple[int, int], str] = {}
        for entry in self.entries:
            for cell, unit in zip(entry_cells(entry), segment(entry.word)):
                seen = grid.get(cell)
                if seen is not None and seen != unit:
                    raise ValueError(
                        f"cell ({cell[0]},{cell[1]}) must hold {seen!r} and {unit!r} "
                        f"at once: {entry.word!r} contradicts a word crossing it"
                    )
                grid[cell] = unit
        for entry in self.entries:
            spelled = [grid[cell] for cell in entry_cells(entry)]
            if spelled != segment(entry.word):
                raise ValueError(
                    f"reading the grid from ({entry.start.row},{entry.start.col}) "
                    f"{entry.direction} spells {''.join(spelled)!r}, not {entry.word!r}"
                )
        return self

    @model_validator(mode="after")
    def _every_entry_is_a_maximal_run(self) -> Self:
        """No entry may sit inside a longer run of open cells.

        A board that printed five open cells in a row and described four of them
        would be asking the player to fill a slot it never named. The cell
        before an entry and the cell after it must therefore be off the board or
        blocked - and BLOCKED here means "covered by no entry", which is the
        only definition of the mask this payload has.
        """
        open_cells = {cell for entry in self.entries for cell in entry_cells(entry)}
        for entry in self.entries:
            step_row, step_col = STEPS[entry.direction]
            cells = entry_cells(entry)
            before = (cells[0][0] - step_row, cells[0][1] - step_col)
            after = (cells[-1][0] + step_row, cells[-1][1] + step_col)
            for neighbour, where in ((before, "before"), (after, "after")):
                if neighbour in open_cells:
                    raise ValueError(
                        f"the cell {where} {entry.word!r} is open, so the run it sits "
                        f"in is longer than the entry the board describes"
                    )
        return self

    @model_validator(mode="after")
    def _the_board_is_connected(self) -> Self:
        """Every entry reaches every other one through shared cells.

        Two clusters that never meet are two puzzles printed on one sheet, and
        the crossings are the only thing that makes a crossword more than a list
        of definitions.
        """
        cells = [set(entry_cells(entry)) for entry in self.entries]
        seen = {0}
        frontier = [0]
        while frontier:
            index = frontier.pop()
            for other in range(len(cells)):
                if other not in seen and cells[other] & cells[index]:
                    seen.add(other)
                    frontier.append(other)
        if len(seen) != len(cells):
            stranded = sorted(
                self.entries[i].word for i in range(len(cells)) if i not in seen
            )
            raise ValueError(f"these entries cross nothing on the board: {stranded}")
        return self

    @model_validator(mode="after")
    def _the_numbers_are_canonical(self) -> Self:
        numbers = canonical_numbers(self.entries)
        for entry in self.entries:
            expected = numbers[(entry.start.row, entry.start.col)]
            if entry.number != expected:
                raise ValueError(
                    f"{entry.word!r} starts at ({entry.start.row},{entry.start.col}) "
                    f"and is numbered {entry.number}; reading order makes it {expected}"
                )
        placed = {(entry.direction, entry.start.row, entry.start.col) for entry in self.entries}
        if len(placed) != len(self.entries):
            raise ValueError("two entries start on the same cell in the same direction")
        return self

    @model_validator(mode="after")
    def _no_answer_is_asked_for_twice(self) -> Self:
        words = [entry.word for entry in self.entries]
        if len(set(words)) != len(words):
            raise ValueError(f"the same answer appears twice on the board: {sorted(words)}")
        return self

    @model_validator(mode="after")
    def _a_clue_never_spells_its_answer(self) -> Self:
        for entry in self.entries:
            if entry.word in entry.clue:
                raise ValueError(
                    f"the clue for {entry.word!r} contains the answer: {entry.clue!r}"
                )
        return self

    @model_validator(mode="after")
    def _every_alternative_really_fits(self) -> Self:
        """An alternative must be enterable without breaking any crossing word.

        Same length, different word, and identical to the answer at every cell
        this entry SHARES with another - read out of the grid, on Row 18's
        lesson that an alternative the board cannot actually accept is bytes for
        a message that can never fire. An answer another entry already asks for
        is refused outright: it is on the board under its own clue.
        """
        crossed: dict[tuple[int, int], int] = {}
        for entry in self.entries:
            for cell in entry_cells(entry):
                crossed[cell] = crossed.get(cell, 0) + 1
        answers = {entry.word for entry in self.entries}
        for entry in self.entries:
            if entry.alsoValid is None:
                continue
            units = segment(entry.word)
            cells = entry_cells(entry)
            if len(set(entry.alsoValid)) != len(entry.alsoValid):
                raise ValueError(f"{entry.word!r} lists an alternative twice")
            for other in entry.alsoValid:
                rival = segment(other)
                if other == entry.word or other in answers:
                    raise ValueError(
                        f"{other!r} is already an answer on this board, so it is not "
                        f"an alternative to {entry.word!r}"
                    )
                if len(rival) != len(units):
                    raise ValueError(
                        f"{other!r} is {len(rival)} ezhuthu and cannot fill the "
                        f"{len(units)}-cell entry {entry.word!r}"
                    )
                for index, cell in enumerate(cells):
                    if crossed[cell] > 1 and rival[index] != units[index]:
                        raise ValueError(
                            f"{other!r} would break the word crossing {entry.word!r} "
                            f"at ({cell[0]},{cell[1]})"
                        )
        return self
