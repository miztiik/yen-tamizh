"""Fill one crossword mask with interlocking Tamil words, at BUILD time.

The Game (Row 21) knows how to write a letter into a cell; this knows how to
choose the letters so that every crossing works. It is the second builder that
deals more than one word - the search board was the first - and the first whose
words are not independent of each other: an entry's answer is constrained by
every other answer it touches.

**The measurement that shaped this row.** A crossword needs two words to share
an ezhuthu at a usable offset. Tamil's alphabet is 247 rather than 26, so the
obvious fear is that crossings are rare - and pairwise they ARE: only 32.7
percent of random served word pairs share any ezhuthu at all, where two English
words of the same length nearly always do. But that is the wrong statistic for a
solver, which never picks two words at random: it picks a word to FIT a
constraint. Measured over the served set, a single pinned position leaves a
median of 103 to 556 candidate words, because the effective alphabet is far
smaller than 247 - the twenty commonest ezhuthu cover 47.4 percent of all cells
and the commonest fifty cover 76.2. Two pinned positions leave a median of 3 to
11. THREE leave a median of ONE, and 55 to 69 percent of words are the only word
in the set with their own three letters in those places.

That last number is the whole design. It says a Tamil grid can be interlocked
but cannot be FULLY CHECKED - an American-style board where every cell belongs
to both an across and a down entry. Run against a real search budget, a 3x3 full
word square fills 12 times out of 12, a 4x4 twice out of 12, and a 5x5, a 6x6
and a 5x5 with blocked corners never once. So this Game ships the British-style
lattice instead: a mask with UNCHECKED cells, where each entry crosses two or
three others rather than all of them. Every legal mask of that shape filled 24
times out of 24 in under 15 milliseconds.

Four things this module owns:

- **The mask is config, the fill is code.** Which shape a band lays out is a
  game-balance decision and lives in ``config/daily-generator.json`` beside the
  other difficulty dials (Holy Law #6); the contract there refuses a mask whose
  runs its own words cannot fill, that strands a cell, that leaves an entry
  crossing nothing, or that falls into two pieces. This module only fills what
  it is given.
- **The search is bounded and it fails loudly.** ``budget`` counts the nodes it
  may expand and ``branch`` caps how many candidates it tries per entry. A
  crossword solver with no ceiling is a daily cron with no ceiling, and a CI job
  that hangs is worse than one that fails - so running out raises
  ``SolverExhausted`` naming what it was filling.
- **Everything is a pure function of the seed.** Which word lands in which entry
  comes from the shared FNV-1a + mulberry32 pair, never from ``random``, so two
  runs of the same date bake the same grid.
- **The clue is the lexicon's own sense, never an invention.** The derived set
  is cut so every served row's first sense can be printed as a question, which
  is what lets this module read ``definitionTa`` straight across; the contract
  then refuses a clue that spells its answer, so the two checks are independent.

Uniqueness is RECORDED, not required - the same ruling the four Games before
this one reached about what else their boards admit. Measured over 900 boards,
19 to 22 percent of entries on a three-crossing mask have a rival word that fits
the same crossings, and requiring the solver to avoid that costs the densest
band 4 fills in 40 and up to 1.8 seconds. It would also be the wrong puzzle: a
grid solvable from its crossings alone does not need its clues, and the clue is
what makes a crossword a word game rather than a lattice. What DOES travel is
the narrow case the player could rightly argue about - a rival that fits the
crossings AND is a listed synonym of the answer, so it arguably answers the same
clue. Those are 0.8 to 2.5 percent of rivals and turn up on 4 to 17 percent of
boards.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from yen_tamizh_backend.contracts.base import ChangelogEntry
from yen_tamizh_backend.contracts.common import Hint
from yen_tamizh_backend.contracts.crossword_puzzle import (
    CrosswordCell,
    CrosswordEntry,
    CrosswordPuzzle,
    canonical_numbers,
)
from yen_tamizh_backend.contracts.daily_generator import (
    DifficultyBand,
    GameGeneration,
    mask_entries,
)
from yen_tamizh_backend.contracts.game_wordlist import GameWord, GameWordlist
from yen_tamizh_backend.generate import Unbuildable
from yen_tamizh_backend.generate import hints as hint_ladder
from yen_tamizh_backend.generate.seed import seeded_shuffle

GAME_ID = "crossword"

_SCHEMA_VERSION = "2026-08-19"
_CHANGELOG = [
    ChangelogEntry(
        version=_SCHEMA_VERSION,
        change=(
            "Initial baked crossword payload: the board's extent and every "
            "answer on it, with where it starts and which way it runs."
        ),
        why=(
            "Row 21 - the fifth Game, and the first whose answers constrain "
            "each other. It costs a payload schema and a builder, not an edit "
            "to puzzle-file or to the day loop, which is the fifth time "
            "one-schema-per-Game has held. No solution grid travels: the grid "
            "is the union of the entries, so the contract BUILDS it from them "
            "and reads every answer back out of it, which is how a placement "
            "bug is caught against the board the player sees rather than "
            "against the solver's own bookkeeping. rows and cols do travel, "
            "unlike the search board's, because a crossword ships no grid array "
            "for its extent to be read off - blocked cells have no content to "
            "ship."
        ),
    )
]

# The CLOSED vocabulary a hint template may name for THIS Game: nothing.
#
# A crossword already SELLS meanings - that is what a clue is - and it prints
# one per entry, free, before the player has written anything. Every rung the
# shared ladder can render is therefore either a fact already on the screen (the
# meaning) or a fact about ONE of six to eight answers, which makes its worth
# depend on whether that answer is still outstanding when the rung is bought. A
# rung that can be worthless by timing is a rung that charges for nothing, which
# is the same test that emptied the search board's ladder.
#
# The help this Game gives instead is a per-entry REVEAL, priced in the answer
# it hands over: the player forfeits that entry's points and keeps the rest. Its
# cost depends on which entries are still open at the moment it is spent, so it
# lives in the Game rather than in the payload - and this Game consequently
# bakes no ``hints`` at all, which is why ``config/app-config.json`` needs no
# ``hints.perGame`` entry for it: the allowance defaults to zero.
HINT_FIELDS: frozenset[str] = frozenset()


class SolverExhausted(Unbuildable):
    """The search hit its ceiling, or proved this word cannot be crossed here.

    Raised rather than returned so a bake can never quietly ship a board with a
    hole in it, and bounded rather than open-ended so a daily cron and a
    time-limited CI job both terminate. It is an ``Unbuildable``, so the day
    loop answers a word it cannot place by dealing the next candidate rather
    than by failing the day.
    """


@dataclass(frozen=True)
class ServedIndex:
    """One served set, indexed the way a placement search interrogates it.

    ``by_length`` holds the rows a slot of each length may take, in a stable
    order. ``positions`` is the inverted index the search actually runs on:
    ``positions[length][offset][ezhuthu]`` is the SET of candidate indices whose
    word carries that ezhuthu at that offset, so narrowing an entry by a
    crossing is a set intersection rather than a scan of the wordlist. Building
    it once per day is what keeps the search in milliseconds.
    """

    by_length: dict[int, tuple[GameWord, ...]]
    positions: dict[int, tuple[dict[str, frozenset[int]], ...]]

    def candidates(self, length: int, pinned: Sequence[tuple[int, str]]) -> set[int]:
        """Which words of ``length`` carry every pinned ezhuthu at its offset."""
        pool = self.by_length.get(length)
        if pool is None:
            return set()
        found: set[int] | None = None
        for offset, unit in pinned:
            at = self.positions[length][offset].get(unit)
            if not at:
                return set()
            found = set(at) if found is None else (found & at)
            if not found:
                return found
        return set(range(len(pool))) if found is None else found


def index_served(wordlist: GameWordlist, spec: GameGeneration) -> ServedIndex:
    """Index one served set by length and by (offset, ezhuthu).

    ``spec`` is unread here and is part of the signature because the day loop
    prepares every Game's set the same way.
    """
    del spec
    rows = sorted(wordlist.words, key=lambda row: row.word)
    by_length: dict[int, list[GameWord]] = {}
    for row in rows:
        by_length.setdefault(len(row.ezhuthu), []).append(row)
    positions: dict[int, tuple[dict[str, frozenset[int]], ...]] = {}
    for length, pool in by_length.items():
        columns: list[dict[str, set[int]]] = [{} for _ in range(length)]
        for index, row in enumerate(pool):
            for offset, unit in enumerate(row.ezhuthu):
                columns[offset].setdefault(unit, set()).add(index)
        positions[length] = tuple(
            {unit: frozenset(members) for unit, members in column.items()}
            for column in columns
        )
    return ServedIndex(
        by_length={length: tuple(pool) for length, pool in by_length.items()},
        positions=positions,
    )


def band_pool(served: ServedIndex, band: DifficultyBand) -> ServedIndex:
    """Narrow a served index to the lengths one band's mask actually asks for.

    Length only, and that is a MEASURED ruling rather than an oversight. The
    search board narrows its companions to the band's own frequency quarter so
    an easy board is four familiar words; the same rule was tried here first and
    it does not survive contact with a crossword. An entry on a three-crossing
    lattice is pinned at three of its five positions, and over the whole served
    set that already leaves a median of ONE candidate word - cutting the pool to
    the most familiar quarter takes it to none, and the easy band filled 26
    boards out of 120 instead of every one.

    Familiarity is therefore spent where it still buys something: on the ANCHOR,
    the word the day loop picks, which is gated by the band's ``maxStratum`` in
    the ordinary way and is the word the player is guaranteed to recognise. The
    rest of the board has to interlock with it, and a crossword whose other
    answers had to be equally familiar is a crossword that cannot be built.
    """
    kept = {
        length: rows
        for length, rows in served.by_length.items()
        if band.minLength <= length <= band.maxLength
    }
    return ServedIndex(
        by_length=kept,
        positions={length: served.positions[length] for length in kept},
    )


def solve_mask(
    mask: Sequence[str],
    served: ServedIndex,
    seed_text: str,
    required: GameWord | None = None,
    budget: int = 60_000,
    branch: int = 400,
    restarts: int = 8,
    exclude: frozenset[str] = frozenset(),
) -> list[tuple[list[tuple[int, int]], GameWord]]:
    """Fill every entry of ``mask``, or raise ``SolverExhausted`` trying.

    The search is ordinary chronological backtracking with three refinements,
    each of which was added because a measurement said the one before it was not
    enough:

    - **Most-constrained-first.** At every node each unfilled entry is narrowed
      against the letters already on the board and the entry with the FEWEST
      surviving candidates is filled next. An entry with none left fails the
      node immediately, which turns a dead branch into one comparison rather
      than a subtree.
    - **A bounded fan-out.** Only the first ``branch`` candidates of an entry are
      tried, in seeded order. An unbounded fan turns a hard mask into an
      unbounded cron, and a daily bake that can hang is worse than one that
      fails.
    - **Seeded restarts.** The order the entries are visited in decides how early
      a bad choice is discovered, and one order can thrash where another walks
      straight through. Each restart reshuffles the entry order and the
      candidate order from a different seed. They share ONE node budget, so
      ``budget`` stays the single honest ceiling on the whole solve rather than
      a number to multiply.

    ``required`` is the word the day loop picked. It is placed FIRST, into an
    entry its length fits, because the loop already chose it against the whole
    bank's history and the difficulty curve, and letting the search pick freely
    would throw that away. Which entry it lands in is part of the search: if the
    first refuses to complete, the next is tried, and the restart reshuffles
    which is first.

    ``exclude`` is the day's ledger, and it enters the search as words already
    TAKEN - the same mechanism that stops one board asking for the same answer
    twice, widened to the whole bank. ``required`` is exempt by construction: it
    is placed directly rather than drawn from the candidate sets the exclusion
    filters, so a ledger holding the anchor cannot refuse the anchor.
    """
    entries = mask_entries(mask)
    if not entries:
        raise SolverExhausted(f"the mask lays out no entries: {list(mask)}")
    grid: dict[tuple[int, int], str] = {}
    taken: set[str] = set(exclude)
    placed: dict[int, GameWord] = {}
    spent = 0

    if required is not None:
        length = len(required.ezhuthu)
        if not any(len(entry) == length for entry in entries):
            raise SolverExhausted(
                f"{required.word!r} is {length} ezhuthu and the mask has no entry "
                f"that long: {sorted({len(entry) for entry in entries})}"
            )

    def pinned_for(cells: Sequence[tuple[int, int]]) -> list[tuple[int, str]]:
        return [
            (offset, grid[cell]) for offset, cell in enumerate(cells) if cell in grid
        ]

    def put(cells: Sequence[tuple[int, int]], row: GameWord) -> list[tuple[int, int]]:
        written: list[tuple[int, int]] = []
        for cell, unit in zip(cells, row.ezhuthu):
            if cell not in grid:
                grid[cell] = unit
                written.append(cell)
        taken.add(row.word)
        return written

    def undo(written: Sequence[tuple[int, int]], row: GameWord) -> None:
        for cell in written:
            del grid[cell]
        taken.discard(row.word)

    def fill(remaining: list[int], salt: str) -> bool:
        nonlocal spent
        if not remaining:
            return True
        spent += 1
        if spent > budget:
            raise SolverExhausted(
                f"no fill for a {len(entries)}-entry grid within {budget} steps "
                f"(seed {seed_text!r})"
            )
        chosen = -1
        fewest: set[int] = set()
        for index in remaining:
            cells = entries[index]
            options = {
                option
                for option in served.candidates(len(cells), pinned_for(cells))
                if served.by_length[len(cells)][option].word not in taken
            }
            if not options:
                return False
            if chosen < 0 or len(options) < len(fewest):
                chosen, fewest = index, options
                if len(options) == 1:
                    break
        rest = [index for index in remaining if index != chosen]
        cells = entries[chosen]
        pool = served.by_length[len(cells)]
        picks = seeded_shuffle(sorted(fewest), f"{salt}|{chosen}")[:branch]
        for pick in picks:
            row = pool[pick]
            written = put(cells, row)
            placed[chosen] = row
            if fill(rest, salt):
                return True
            del placed[chosen]
            undo(written, row)
        return False

    for attempt in range(restarts):
        salt = f"{seed_text}|try{attempt}"
        order = seeded_shuffle(list(range(len(entries))), f"{salt}|entries")
        if required is None:
            if fill(order, salt):
                return [(entries[index], placed[index]) for index in sorted(placed)]
            continue
        length = len(required.ezhuthu)
        for home in (index for index in order if len(entries[index]) == length):
            written = put(entries[home], required)
            placed[home] = required
            if fill([index for index in order if index != home], salt):
                return [(entries[index], placed[index]) for index in sorted(placed)]
            del placed[home]
            undo(written, required)
    named = "" if required is None else f" placing {required.word!r}"
    raise SolverExhausted(
        f"no fill{named} for a {len(entries)}-entry grid after {restarts} restarts "
        f"and {spent} steps (seed {seed_text!r})"
    )


def synonym_rivals(
    cells: Sequence[tuple[int, int]],
    answer: GameWord,
    crossed: Sequence[bool],
    served: ServedIndex,
    on_board: Sequence[str],
) -> list[str]:
    """The words that could fill this entry AND arguably answer its clue.

    Fitting the crossings is not enough: a word that fits them answers a
    DIFFERENT clue, and marking it right would make the clue list decoration. So
    the list is narrowed to rivals the answer's own lexicon row calls a synonym
    - the only ones a player can fairly say answer the same question. An answer
    already on the board is excluded: it is asked for under its own clue.
    """
    del cells
    synonyms = set(answer.synonymsTa or ())
    if not synonyms:
        return []
    pinned = [
        (offset, unit)
        for offset, unit in enumerate(answer.ezhuthu)
        if crossed[offset]
    ]
    pool = served.by_length.get(len(answer.ezhuthu), ())
    rivals = {
        pool[index].word
        for index in served.candidates(len(answer.ezhuthu), pinned)
        if pool[index].word != answer.word
    }
    return sorted(rivals & synonyms - set(on_board))


def build_hints(
    row: GameWord, spec: GameGeneration, limit: int, themed: bool = False
) -> list[Hint]:
    """Always empty - see ``HINT_FIELDS`` for why this Game's ladder has no rungs.

    It delegates to the shared machinery rather than returning ``[]`` outright,
    and that is the point: with an empty vocabulary, a hint template registered
    against this Game names a field it cannot sell and fails the bake loudly.
    """
    del themed
    return hint_ladder.build_hints(row, spec, limit, {}, HINT_FIELDS)


def build_puzzle(
    row: GameWord,
    spec: GameGeneration,
    seed_text: str,
    hint_limit: int,
    band: DifficultyBand,
    served: ServedIndex,
    themed: bool = False,
    used: frozenset[str] = frozenset(),
) -> CrosswordPuzzle:
    """Build one validated crossword from a derived-wordlist row and a band mask.

    ``used`` is the day's ledger - every word the bank has already asked for -
    and the solver treats it as words already taken, so a board's other answers
    are as unrepeated as its anchor. A mask the ledger makes unsolvable is
    re-solved without it: this Game's answers interlock, so the fallback cannot
    be per-entry the way the search board's is per-word, and shipping a board
    that repeats one word is a much smaller failure than failing the day
    (``pick_words``' own trade).

    ``themed`` is accepted and unused: this Game sells no rungs, so there is no
    ``category`` rung a theme could make redundant.
    """
    del themed
    # Not a no-op: with an empty vocabulary this raises when config has
    # registered a rung against this Game and raised its allowance to match.
    build_hints(row, spec, hint_limit)
    if band.grid is None:
        raise ValueError(
            f"band {band.id!r} lays out no grid, so {GAME_ID!r} has nothing to fill"
        )
    pool = band_pool(served, band)
    try:
        filled = solve_mask(band.grid, pool, seed_text, required=row, exclude=used)
    except SolverExhausted:
        if not used:
            raise
        filled = solve_mask(band.grid, pool, seed_text, required=row)
    numbers = canonical_numbers(
        [
            CrosswordEntry(
                number=1,
                direction=_direction_of(cells),
                start=CrosswordCell(row=cells[0][0], col=cells[0][1]),
                word=answer.word,
                clue=_clue_for(answer),
            )
            for cells, answer in filled
        ]
    )
    crossings: dict[tuple[int, int], int] = {}
    for cells, _ in filled:
        for cell in cells:
            crossings[cell] = crossings.get(cell, 0) + 1
    answers = [answer.word for _, answer in filled]
    entries = [
        CrosswordEntry(
            number=numbers[cells[0]],
            direction=_direction_of(cells),
            start=CrosswordCell(row=cells[0][0], col=cells[0][1]),
            word=answer.word,
            clue=_clue_for(answer),
            alsoValid=synonym_rivals(
                cells,
                answer,
                [crossings[cell] > 1 for cell in cells],
                pool,
                answers,
            )
            or None,
        )
        for cells, answer in filled
    ]
    return CrosswordPuzzle(
        version=_SCHEMA_VERSION,
        changelog=_CHANGELOG,
        rows=len(band.grid),
        cols=len(band.grid[0]),
        entries=entries,
    )


def _direction_of(cells: Sequence[tuple[int, int]]) -> str:
    """Which way a run of cells goes. A run of one would be neither, and the
    mask reader never produces one."""
    return "across" if cells[0][0] == cells[1][0] else "down"


def _clue_for(row: GameWord) -> str:
    """The clue this answer is asked by: the lexicon's own first Tamil sense.

    Read straight across rather than resolved, because the derived set this Game
    draws from is cut on ``requireClueableMeaning`` - so every served row's
    sense is already one that can be printed as a question. The contract then
    refuses a clue that spells its answer, which keeps the two checks
    independent: a mis-cut wordlist fails the bake rather than reaching a board.
    """
    if row.definitionTa is None:
        raise ValueError(
            f"{row.word!r} carries no sense, so this Game has nothing to ask about it"
        )
    return row.definitionTa
