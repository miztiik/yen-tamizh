"""The word-search Game's puzzle-payload contract (word-search-puzzle).

word-search hides a handful of words in a grid of ezhuthu and asks the player to
trace each one out, in any of the eight straight-line directions - forwards,
backwards, and along both diagonals (games.md ``word-search``). This is the
per-Game ``payload`` schema a puzzle-file item carries, and it is the FOURTH of
them; the three before it are unchanged, which is what one-schema-per-Game keeps
promising.

**A grid cell holds exactly ONE ezhuthu, and that is the whole contract.**
Everything else here is framing. A grid built over code points rather than
ezhuthu would put a bare consonant in one cell and its vowel sign in the next,
which is not a harder puzzle - it is an unreadable one, because neither cell is
a letter a Tamil reader can name and no straight line through them spells
anything. So every cell is checked against the shared Row 6 segmentation AND
against the closed 247-ezhuthu inventory: ``segment(cell) == [cell]`` proves the
cell is one cluster, and membership proves that cluster is a letter of Tamil
rather than a digit, a Latin character or a piece of legacy mojibake that
happens to survive segmentation (row 11 found eight of those in the published
lexicon).

Three things this payload deliberately does NOT carry:

- **No ``rows``/``cols``.** The grid's shape is ``len(grid)`` by
  ``len(grid[0])``. A stored copy of a derived value is a drift surface (row 11
  took ``ezhuthu`` off the published lexicon row on these grounds, Row 18 kept
  the segmentation out of ``missing-letters-puzzle`` and Row 19 the board width
  out of ``wordle-puzzle``), and here the drift would be player-visible: a
  declared width the grid did not have would put every recorded start in the
  wrong cell.
- **No per-target ``ezhuthu`` array.** A target's cells are
  ``len(segment(word))`` steps from its ``start``, and the validator below reads
  them back OUT OF THE GRID and compares them to that segmentation. The
  traceability of a word is therefore proven against the grid the player sees
  rather than against the generator's own bookkeeping.
- **No ``attempts``.** A wrong trace on a word search costs nothing anywhere in
  the world, and it should not here either: tracing IS how a player looks, and
  charging for looking would turn the one exploratory mechanic in the game into
  a guessing game. Row 18's rule stands - a new contract does not mint a field
  with no reader.

``alsoValid`` is the same idea the anagram and the missing-letters board already
ship (schemas.md: whether the board spells something else is RECORDED, not
required), and here it is not a possibility but a measured fact: filling the
cells a target does not use makes unintended words, and 69 percent of generated
grids hold at least one. Recording them is what lets the Game answer "that is a
word, but not on today's list" instead of a red cross. Every entry has to be
traceable in the grid, because Row 18's lesson was that an alternative the input
method cannot reach is bytes for a message that can never fire.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.ezhuthu import EZHUTHU_INVENTORY, segment

# One ezhuthu: a non-empty grapheme-cluster string (core-loop.md). The generator
# produces these with the shared segmentation library; a cell split across a
# cluster boundary is what this whole contract exists to prevent.
Ezhuthu = Annotated[str, StringConstraints(min_length=1)]

# The eight straight lines a word may run along, named by where the NEXT cell
# lies rather than by a compass point. A grid's origin is its top-left corner, so
# "north" would have to mean "towards a smaller row index" - true, and one more
# thing for a reader to hold. ``down-right`` needs no such note.
Direction = Literal[
    "right",
    "down-right",
    "down",
    "down-left",
    "left",
    "up-left",
    "up",
    "up-right",
]

# Each direction as the (row, col) step it takes. The set is closed under
# negation - every direction's opposite is also in it - which is what makes a
# backwards trace the same trace read the other way rather than a special case.
STEPS: dict[str, tuple[int, int]] = {
    "right": (0, 1),
    "down-right": (1, 1),
    "down": (1, 0),
    "down-left": (1, -1),
    "left": (0, -1),
    "up-left": (-1, -1),
    "up": (-1, 0),
    "up-right": (-1, 1),
}

# The 247 ezhuthu, held as a set so the per-cell check is a membership test.
_LETTERS = frozenset(EZHUTHU_INVENTORY)


def path_cells(
    row: int, col: int, direction: str, length: int
) -> list[tuple[int, int]]:
    """The cells a trace of ``length`` covers, starting at ``(row, col)``."""
    step_row, step_col = STEPS[direction]
    return [(row + step_row * i, col + step_col * i) for i in range(length)]


def read_path(
    grid: list[list[str]], row: int, col: int, direction: str, length: int
) -> list[str] | None:
    """The ezhuthu a trace spells, or ``None`` when it runs off the grid."""
    height = len(grid)
    width = len(grid[0]) if height else 0
    units: list[str] = []
    for cell_row, cell_col in path_cells(row, col, direction, length):
        if not (0 <= cell_row < height and 0 <= cell_col < width):
            return None
        units.append(grid[cell_row][cell_col])
    return units


def occurrences(grid: list[list[str]], word: str) -> list[tuple[int, int, str]]:
    """Every start and direction from which ``word`` can be traced in the grid."""
    units = segment(word)
    found: list[tuple[int, int, str]] = []
    for row in range(len(grid)):
        for col in range(len(grid[row])):
            for direction in sorted(STEPS):
                if read_path(grid, row, col, direction, len(units)) == units:
                    found.append((row, col, direction))
    return found


class GridPoint(BaseModel):
    """One cell address: a row and a column, both counted from the top-left."""

    model_config = ConfigDict(extra="forbid")

    row: int = Field(ge=0)
    col: int = Field(ge=0)


class WordSearchTarget(BaseModel):
    """One word hidden in the grid: where it starts and which way it runs.

    ``meaning`` is resolved at bake time and shown FREE beside the word once the
    player has traced it (the Row 14 rule that a solved word explains itself).
    It rides the TARGET rather than the puzzle because a word search asks for
    several words at once and the session summary carries one line per item, so
    this board is the only place these meanings can ever be read.

    ``translationEn`` deliberately does not travel. On the other three Games it
    is the summary's demoted second line; here there is no such line, so its only
    possible reader would be this board - and an English gloss under every word
    of a Tamil grid doubles the list's height on a 360px screen to say something
    the paid ladder is banned from selling anyway.
    """

    model_config = ConfigDict(extra="forbid")

    word: str = Field(min_length=1)
    start: GridPoint
    direction: Direction
    meaning: str | None = Field(default=None, min_length=1)


class WordSearchPuzzle(SchemaModel):
    """One word-search board: the grid, the words hidden in it, and their places.

    The grid is a list of rows, each a list of single ezhuthu. It must be
    rectangular, because a ragged grid has no columns to run a vertical or
    diagonal trace down.

    Every target must be recoverable BY READING THE GRID: stepping
    ``len(segment(word))`` cells from its ``start`` in its ``direction`` has to
    spell the word exactly. That is this contract's Oracle, and it is stated
    against the grid rather than against the generator so a placement bug cannot
    ship a word the player is asked to find and cannot.
    """

    grid: list[list[Ezhuthu]] = Field(min_length=1)
    targets: list[WordSearchTarget] = Field(min_length=1)
    alsoValid: list[str] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _the_grid_is_rectangular(self) -> Self:
        widths = {len(row) for row in self.grid}
        if len(widths) != 1:
            raise ValueError(
                f"the grid's rows are {sorted(widths)} cells wide; a ragged grid has "
                "no column to trace down"
            )
        if widths == {0}:
            raise ValueError("the grid has no columns")
        return self

    @model_validator(mode="after")
    def _every_cell_is_exactly_one_ezhuthu(self) -> Self:
        """The row's central correctness property, checked cell by cell.

        Two claims, and they are different. ``segment(cell) == [cell]`` says the
        cell is ONE cluster - not two letters crammed together, and not half of
        one. Membership in the 247 says that cluster is a LETTER OF TAMIL: a
        digit, a Latin character, a grantha base or the legacy mojibake row 11
        found in the published lexicon all survive segmentation as a single unit
        and would sail past the first check while being unreadable in a grid.
        """
        broken: list[str] = []
        foreign: list[str] = []
        for row in self.grid:
            for cell in row:
                if segment(cell) != [cell]:
                    broken.append(cell)
                elif cell not in _LETTERS:
                    foreign.append(cell)
        if broken:
            raise ValueError(
                f"{sorted(set(broken))} are not single ezhuthu; a grid cell that holds "
                "part of a cluster spells nothing in any direction"
            )
        if foreign:
            raise ValueError(
                f"{sorted(set(foreign))} are not among the 247 ezhuthu, so they cannot "
                "be read as Tamil letters in a grid"
            )
        return self

    @model_validator(mode="after")
    def _every_target_is_traceable_from_where_it_says(self) -> Self:
        words = [target.word for target in self.targets]
        if len(set(words)) != len(words):
            raise ValueError(f"targets repeats a word: {sorted(words)}")
        for target in self.targets:
            units = segment(target.word)
            traced = read_path(
                self.grid,
                target.start.row,
                target.start.col,
                target.direction,
                len(units),
            )
            if traced is None:
                raise ValueError(
                    f"{target.word!r} runs off the grid from "
                    f"({target.start.row}, {target.start.col}) going {target.direction}"
                )
            if traced != units:
                raise ValueError(
                    f"tracing {target.direction} from ({target.start.row}, "
                    f"{target.start.col}) spells {''.join(traced)!r}, not "
                    f"{target.word!r}"
                )
        return self

    @model_validator(mode="after")
    def _alternatives_are_in_the_grid_and_are_not_targets(self) -> Self:
        """An alternative the player cannot trace is a message that can never fire.

        The Row 18 lesson transposed: there an ``alsoValid`` word the choice bank
        could not spell was unreachable, and here an ``alsoValid`` word that is
        not actually in the grid is the same mistake wearing a different costume.
        The check re-scans the grid rather than trusting the generator, which is
        also what makes the field impossible to hand-edit into a lie.
        """
        if self.alsoValid is None:
            return self
        if len(set(self.alsoValid)) != len(self.alsoValid):
            raise ValueError(f"alsoValid repeats a word: {sorted(self.alsoValid)}")
        targets = {target.word for target in self.targets}
        for other in self.alsoValid:
            if other in targets:
                raise ValueError(f"alsoValid repeats the target {other!r}")
            if not occurrences(self.grid, other):
                raise ValueError(
                    f"alsoValid names {other!r}, which cannot be traced anywhere in "
                    "the grid"
                )
        return self
