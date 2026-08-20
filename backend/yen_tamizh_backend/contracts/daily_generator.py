"""The daily puzzle ENGINE's registry contract (Row 13).

``config/daily-generator.json`` is what the build-time daily generator reads.
It is deliberately a SEPARATE surface from ``config/app-config.json``: the app
config is runtime framing the browser ships with (how many items a day holds,
which Modes are enabled), while this file holds the knobs that decide how a word
becomes a puzzle - attempts, time limit, revealed head start, hint costs, and
which ezhuthu lengths at which familiarity count as which difficulty.

That split is the lexicon-versus-puzzle boundary drawn one layer lower: the
generator CONSUMES a derived wordlist (Row 9) and PRODUCES puzzle files, and it
must be tunable without touching either the words above it or the runtime below
it. Adding a second Game's generator is a DATA change here (another ``games``
entry) plus the Game's own payload builder - never a rewrite of the day loop.

A Game may also register THEMED wordlists beside its ordinary one. That is the
Daily's variety mechanism and it is data too: a themed day draws every slot from
one theme's own derived set, and which themes exist is a registry edit rather
than a branch in the day loop.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel
from yen_tamizh_backend.contracts.common import (
    QUARTILES,
    CopySlug,
    DifficultyId,
    GameId,
    PackId,
    RelPath,
)

# A bare one-word tag: non-empty and holding no whitespace of any kind.
BareTag = Annotated[str, StringConstraints(min_length=1, pattern=r"^\S+$")]

# One row of a crossword mask: open cells and blocked ones, nothing else.
MaskRow = Annotated[str, StringConstraints(min_length=2, pattern=r"^[.#]+$")]

# What a mask writes for a cell a word may run through.
OPEN_CELL = "."


def mask_entries(grid: Sequence[str]) -> list[list[tuple[int, int]]]:
    """Every maximal run of open cells in a crossword mask, longer than one.

    Defined once, here beside the mask itself, because three readers have to
    agree about it: the validator that refuses an unusable mask, the solver that
    fills it, and the test that reads a baked board back. A run of ONE open cell
    is not an entry - it is an unchecked cell, the square a British-style grid
    leaves for one word alone - so it is skipped rather than reported.
    """
    rows, cols = len(grid), len(grid[0]) if grid else 0
    entries: list[list[tuple[int, int]]] = []
    for row in range(rows):
        run: list[tuple[int, int]] = []
        for col in range(cols + 1):
            if col < cols and grid[row][col] == OPEN_CELL:
                run.append((row, col))
            else:
                if len(run) > 1:
                    entries.append(run)
                run = []
    for col in range(cols):
        run = []
        for row in range(rows + 1):
            if row < rows and grid[row][col] == OPEN_CELL:
                run.append((row, col))
            else:
                if len(run) > 1:
                    entries.append(run)
                run = []
    return entries


class DifficultyBand(BaseModel):
    """One difficulty bucket: the ezhuthu lengths and the familiarity it covers.

    Difficulty is TWO-AXIS - length and familiarity - because length alone is
    anti-correlated at both tails. A long Tamil headword is usually a compound
    that decomposes into recognisable chunks and is EASIER than its ezhuthu
    count suggests, while a short rare word is brutal; a length-only easy bucket
    therefore forces the generator into the shortest words, which are
    disproportionately literary. A 3-ezhuthu answer also has only six
    arrangements against three attempts, so it is brute-forceable by shuffling
    without the player ever recognising the word.

    ``maxStratum`` is the coarsest frequency quarter the band admits, 1 being
    the most familiar quarter of the SERVED set. Bands deliberately OVERLAP on
    length and tile on familiarity: what separates easy from hard is mostly how
    well the player knows the word, not how many tiles it has.

    ``blanks`` is how many ezhuthu a band HIDES, and it is read only by the
    Games whose mechanic hides letters. It defaults to 1 so a Game that shows
    every tile - the anagram - never has to mention it, and so every day baked
    before this knob existed still validates. Hiding a second ezhuthu is the
    honest way to make a band harder without reaching for a rarer word: it
    multiplies the guess space instead of narrowing the vocabulary.

    ``targets`` is how many WORDS a band hides, read only by the Games whose
    board holds more than one. It defaults to 1, which is what every other Game
    deals. On a search board it is the main difficulty dial, and the reason is
    an inversion worth stating: length is NOT a difficulty axis here. A longer
    word occupies more cells and is more distinctive, so it is EASIER to spot
    than a short one, which is the opposite of what length does to a scramble or
    a wordle board. What makes a search harder is how many words are still
    outstanding and how well the player knows them.

    ``grid`` is the crossword's MASK - one string per row, ``.`` for a cell a
    word runs through and ``#`` for a blocked one - and it is the crossword's
    difficulty dial for the same reason ``targets`` is the search board's: what
    makes a grid harder is how many answers it asks for and how much of each one
    the crossings give away, not how long the words are. It is a band's own
    field rather than one shape for the whole Game because those two things are
    exactly what a band is allowed to change. Games with no crossings never read
    it.

    Where the cuts fall is a game-balance number, so it lives here rather than
    in Python (Holy Law #6).
    """

    model_config = ConfigDict(extra="forbid")

    id: DifficultyId
    minLength: int = Field(ge=1)
    maxLength: int = Field(ge=1)
    maxStratum: int = Field(ge=1, le=QUARTILES)
    blanks: int = Field(default=1, ge=1)
    targets: int = Field(default=1, ge=1)
    grid: list[MaskRow] | None = Field(default=None, min_length=2)

    @model_validator(mode="after")
    def _band_is_coherent(self) -> Self:
        if self.minLength > self.maxLength:
            raise ValueError(
                f"minLength {self.minLength} must be <= maxLength {self.maxLength}"
            )
        if self.blanks >= self.minLength:
            # A band that could hide every ezhuthu of its shortest word would
            # deal a row of empty boxes, which is not a puzzle about a word.
            raise ValueError(
                f"blanks {self.blanks} must be < minLength {self.minLength}, or the "
                f"band's shortest word has nothing showing"
            )
        return self

    @model_validator(mode="after")
    def _the_mask_is_a_crossword(self) -> Self:
        """Refuse a mask that cannot become a fair grid, before anything fills it.

        Five conditions, and each of them is a way a mask can look fine and be
        unusable:

        - **Rectangular.** A ragged mask has no columns to run a down entry
          through.
        - **Every run is one cell or an entry the band can fill.** A run of two
          when the band's floor is four is a slot no word can enter and no clue
          can describe; a run longer than the band's ceiling is the same failure
          from the other side. A run of exactly ONE cell is legal and is what
          makes this a British-style lattice rather than an American grid -
          measured, a fully-checked Tamil grid is impossible past three by three.
        - **Every length the band admits really occurs.** The day loop picks one
          word per slot by length and familiarity, and that word has to fit
          somewhere on this board; a band admitting a length its own grid never
          asks for would deal an answer with nowhere to go.
        - **Every entry crosses another.** An entry crossing nothing is a
          standalone word printed on a crossword.
        - **Connected.** Two clusters that never meet are two puzzles on one
          sheet.
        """
        if self.grid is None:
            return self
        widths = {len(row) for row in self.grid}
        if len(widths) != 1:
            raise ValueError(
                f"band {self.id!r} has a ragged grid: rows are {sorted(widths)} wide"
            )
        entries = mask_entries(self.grid)
        covered = {cell for entry in entries for cell in entry}
        stranded = [
            (row, col)
            for row, line in enumerate(self.grid)
            for col, cell in enumerate(line)
            if cell == OPEN_CELL and (row, col) not in covered
        ]
        if stranded:
            raise ValueError(
                f"band {self.id!r} leaves {len(stranded)} open cell(s) in no entry at "
                f"all, starting at {stranded[0]}; nothing on the board can fill them"
            )
        allowed = set(range(self.minLength, self.maxLength + 1))
        lengths = {len(entry) for entry in entries}
        bad = sorted(length for length in lengths if length not in allowed)
        if bad:
            raise ValueError(
                f"band {self.id!r} has runs of {bad} cells, which its words "
                f"({self.minLength}-{self.maxLength} ezhuthu) cannot fill"
            )
        missing = sorted(allowed - lengths)
        if missing:
            raise ValueError(
                f"band {self.id!r} admits {missing}-ezhuthu words its grid never "
                f"asks for, so a word the day picks would have nowhere to go"
            )
        if len(entries) < 2:
            raise ValueError(f"band {self.id!r} has {len(entries)} entries; a crossword needs two")
        cells = [set(entry) for entry in entries]
        for index, entry in enumerate(cells):
            if not any(entry & other for pos, other in enumerate(cells) if pos != index):
                raise ValueError(
                    f"band {self.id!r} has an entry at {sorted(entries[index])[0]} that "
                    f"crosses nothing"
                )
        seen, frontier = {0}, [0]
        while frontier:
            index = frontier.pop()
            for other in range(len(cells)):
                if other not in seen and cells[other] & cells[index]:
                    seen.add(other)
                    frontier.append(other)
        if len(seen) != len(cells):
            raise ValueError(
                f"band {self.id!r} has {len(cells) - len(seen)} entries that never "
                f"reach the rest of the board"
            )
        return self


class HintSpec(BaseModel):
    """One rung of the ladder: its kind, its wording, and what it costs.

    ``template`` is a Python format string over the CLOSED vocabulary of fields
    the Game it is registered under can fill from a served row. The vocabulary
    is PER GAME and lives in that Game's builder, because what counts as a hint
    depends on the board: the anagram sells ``{firstEzhuthu}`` because its tiles
    are shuffled and knowing which one leads is real progress, while a
    missing-letters board has already printed every ezhuthu it is not hiding, so
    the same field is either a fact on the screen or the answer. ``{category}``
    and ``{meaning}`` are common to both. The rendered TEXT is per-puzzle data
    and ships inside the puzzle payload, but the WORDING is player-facing copy,
    so it lives here and the generator only fills in the values.

    A template naming a field OUTSIDE its Game's vocabulary fails the bake
    loudly; a template naming one INSIDE it that a particular row cannot fill
    has its rung skipped for that row. Those are different mistakes: the first is
    a typo in config, the second is the honest state of a lexicon where barely
    one word in fifteen carries a category.

    ``{length}`` is deliberately in NO Game's vocabulary. A rung charging for the
    tile count already on the player's screen was deleted, and leaving the field
    fillable would let one config line put it back.
    """

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1)
    template: str = Field(min_length=1)
    cost: int = Field(ge=0)


class ThemedSet(BaseModel):
    """One themed wordlist this Game may run a whole day from.

    A theme is the Daily's VARIETY mechanism, not a Mode and not a Game: three
    unrelated anagrams are a list, three sharing a theme are a round. It costs no
    new engine - it is one derived set cut on the ``categories`` dimension, and
    ``wordlist`` is where that set landed.

    ``copySlug`` names the theme's player-facing Tamil label in
    ``config/copy.json``. The SLUG travels in the baked day, never the label: a
    Tamil category name is copy, and copy never gets baked into a dataset where
    it could only be changed by a rebuild.

    A themed day is OPPORTUNISTIC. The day runs a theme only when a whole
    playlist can be drawn from that theme's own wordlist without repeating a
    word the bank has already served; otherwise the day is ordinary. A theme is
    never padded out with an off-theme word, because the round's whole claim is
    that the three words belong together.
    """

    model_config = ConfigDict(extra="forbid")

    wordlist: RelPath
    copySlug: CopySlug


class GameGeneration(BaseModel):
    """How one Game turns a wordlist row into a playable puzzle."""

    model_config = ConfigDict(extra="forbid")

    gameId: GameId
    packId: PackId
    wordlist: RelPath
    attempts: int = Field(ge=1)
    timeLimitSec: int = Field(ge=0)
    # How many leading ezhuthu the puzzle starts with already placed. 0 keeps the
    # scramble whole; a positive value is the gentlest honest difficulty dial.
    reveal: int = Field(ge=0)
    # How many ezhuthu the choice bank holds, for the Games that offer one. It
    # is a real balance number and not a layout preference: there is no Tamil
    # keyboard in this game, so the bank is how a hidden ezhuthu gets entered at
    # all, and its size IS the odds a player who knows nothing can still guess
    # the answer inside the allowed attempts. Games that hand out no bank - the
    # anagram, whose tiles are the word's own - never read it.
    choiceCount: int = Field(default=8, ge=2)
    # The board a Game that hides words in a grid lays them out on. Both are
    # phone-screen numbers rather than taste: a cell has to be wide enough for
    # the widest ezhuthu, which is 36px at a readable size, and eight of those
    # with a 4px gutter is 316px against the 328px a 360px phone leaves after
    # its margins - a ninth column is 356px and does not fit. The row count
    # follows the column count because a square grid is the shape whose
    # diagonals are as long as its sides, which is what makes all eight
    # directions equally usable. Games with no grid never read either.
    gridRows: int = Field(default=8, ge=2)
    gridCols: int = Field(default=8, ge=2)
    difficulties: list[DifficultyBand] = Field(min_length=1)
    hints: list[HintSpec] = Field(default_factory=list)
    # The Tamil tag the ``category`` rung renders for each lexicon category
    # slug. The lexicon's categories column holds English slugs because a
    # category is a machine dimension there - it is what a themed set is cut on
    # - while what a player reads is hint wording, and hint wording lives beside
    # the templates. A slug with no entry here has no rung: the ladder is
    # shorter for that word rather than English on a Tamil stage.
    categoryLabels: dict[CopySlug, BareTag] = Field(default_factory=dict)
    # The themed sets this Game may run a whole day from. Empty is the normal
    # state and means this Game never runs a themed day.
    themes: list[ThemedSet] = Field(default_factory=list)

    @model_validator(mode="after")
    def _difficulty_ids_are_distinct(self) -> Self:
        ids = [band.id for band in self.difficulties]
        if len(set(ids)) != len(ids):
            raise ValueError(f"difficulties has a repeated id: {ids}")
        kinds = [hint.kind for hint in self.hints]
        if len(set(kinds)) != len(kinds):
            raise ValueError(f"hints has a repeated kind: {kinds}")
        slugs = [theme.copySlug for theme in self.themes]
        if len(set(slugs)) != len(slugs):
            raise ValueError(f"themes has a repeated copySlug: {slugs}")
        paths = [theme.wordlist for theme in self.themes] + [self.wordlist]
        if len(set(paths)) != len(paths):
            # A theme pointing at the ordinary set would make every day themed
            # and say so in the header, which is a lie about the round.
            raise ValueError(f"themes has a repeated wordlist: {paths}")
        return self

    @model_validator(mode="after")
    def _the_ladder_is_monotonic(self) -> Self:
        # The ladder is walked in order, not chosen from, so its order IS its
        # pricing: each rung must cost at least what the one before it did. A
        # cheaper rung further down would be unreachable without buying the
        # dearer one first, which is a shop with the prices swapped.
        costs = [hint.cost for hint in self.hints]
        if costs != sorted(costs):
            raise ValueError(f"hints must be ordered by non-decreasing cost: {costs}")
        return self

    @model_validator(mode="after")
    def _a_band_fits_on_the_board(self) -> Self:
        # A floor, not a packing model: a band whose words need more cells than
        # the grid HAS can never be dealt, whatever the placement does. What the
        # grid can really take is lower and was measured rather than derived (an
        # 8x8 board places up to seven words every time and eight words 88.5
        # percent of the time), so the number that matters is in config; this
        # only refuses the configuration that is impossible by counting.
        cells = self.gridRows * self.gridCols
        for band in self.difficulties:
            if band.grid is not None:
                # A crossword's own mask states its shape, so the Game-wide grid
                # knob is read here as the CEILING that shape has to fit inside -
                # which is what keeps the phone-screen number in one place
                # instead of once per band.
                height, width = len(band.grid), len(band.grid[0])
                if height > self.gridRows or width > self.gridCols:
                    raise ValueError(
                        f"band {band.id!r} lays out a {height}x{width} grid, which does "
                        f"not fit the {self.gridRows}x{self.gridCols} board"
                    )
                continue
            needed = band.targets * band.maxLength
            if needed > cells:
                raise ValueError(
                    f"band {band.id!r} hides {band.targets} words of up to "
                    f"{band.maxLength} ezhuthu, which needs {needed} cells on a "
                    f"{self.gridRows}x{self.gridCols} grid of {cells}"
                )
            if band.maxLength > max(self.gridRows, self.gridCols):
                raise ValueError(
                    f"band {band.id!r} admits {band.maxLength}-ezhuthu words, which do "
                    f"not fit a {self.gridRows}x{self.gridCols} grid in any direction"
                )
        return self


class DailyGenerator(SchemaModel):
    """The daily engine's knobs: where the bank lands and how a day is filled."""

    # Where the baked bank is written, relative to the repo root. It lives under
    # frontend/public/ so the game reads it same-origin from its own bundle
    # (Holy Law #1) - never from a CDN.
    bankDir: RelPath
    # How many days AHEAD of the run date to bake. The player's calendar day is
    # local, the cron's is UTC, and a phone that is hours ahead must still find
    # today in the bank - plus a pre-baked run keeps the game playable offline
    # across midnight.
    daysAhead: int = Field(ge=0)
    # How often the Daily MAY run a themed round: every Nth date, counted on the
    # proleptic Gregorian day number so the cadence is a pure function of the
    # date and needs no phase knob. 0 turns themed days off entirely.
    #
    # A cadence is needed because "themed whenever a theme can fill the day" is
    # not the same design at 429 servable themed rows as it was at the ~30 the
    # theme was sized for: without it the Daily would be the same theme every day
    # for months, which is the opposite of the variety a theme exists to add.
    themeEveryNDays: int = Field(ge=0)
    games: list[GameGeneration] = Field(min_length=1)

    @model_validator(mode="after")
    def _games_are_distinct(self) -> Self:
        ids = [entry.gameId for entry in self.games]
        if len(set(ids)) != len(ids):
            raise ValueError(f"games has a repeated gameId: {ids}")
        return self
