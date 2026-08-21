"""Turn one derived-wordlist row into a playable ``word-search`` payload.

The Game (Row 20) knows how to trace a line; this knows how to hide one. It is
the first builder that deals MORE THAN ONE word: the day loop picks a slot's
anchor word the way it does for every other Game, and this draws the rest of the
board's words from the same served set, the same difficulty band, and the same
seed.

Five things this module owns:

- **A grid cell is a WHOLE ezhuthu.** Every cell is one unit of
  ``segment(word)``, so a trace reads letters a Tamil reader can name. Splitting
  a cluster across two cells would make the target untraceable and the grid
  unreadable at the same time; the contract re-checks it cell by cell, so this
  is proven rather than promised.
- **Placement is exhaustive, not hopeful.** Every (cell, direction) start is
  tried in a seeded order and the first one that fits wins - fitting meaning the
  word stays on the grid and every cell it wants is either empty or already
  holds the same ezhuthu. Crossing words therefore share their letters, which is
  what a word search is supposed to look like.
- **The filler is drawn from the TARGETS' own letters.** See ``fill_grid``: it
  is the one filler with no elimination leak, and it was measured to make FEWER
  unintended words than sampling the whole served set, not more.
- **An unintended word is RECORDED, not designed out.** After the grid is full
  it is scanned against the served set, and whatever it happens to spell beyond
  the targets is carried in ``alsoValid`` - the repo's settled precedent
  (schemas.md), and here a measured 69 percent of grids have at least one.
- **Everything is a pure function of the seed.** Which companions, where each
  word lands, and which letter falls in which empty cell all come from the
  shared FNV-1a + mulberry32 pair, never from ``random`` - two runs of the same
  date bake the same bytes.

The grid's SHAPE is a config knob because it is a phone-screen number: eight
columns of 36px with a 4px gutter is 316px, which fits the 328px a 360px phone
leaves after its margins, and a ninth column does not. How many words a band
hides is a config knob for the opposite reason - it is the difficulty dial, and
difficulty is declared in ``config/daily-generator.json`` (Holy Law #6).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from yen_tamizh_backend.contracts.base import ChangelogEntry
from yen_tamizh_backend.contracts.common import Hint
from yen_tamizh_backend.contracts.daily_generator import DifficultyBand, GameGeneration
from yen_tamizh_backend.contracts.game_wordlist import GameWord, GameWordlist
from yen_tamizh_backend.contracts.word_search_puzzle import (
    STEPS,
    GridPoint,
    WordSearchPuzzle,
    WordSearchTarget,
    path_cells,
)
from yen_tamizh_backend.generate import hints as hint_ladder
from yen_tamizh_backend.generate.seed import seeded_shuffle

GAME_ID = "word-search"

_SCHEMA_VERSION = "2026-08-19"
_CHANGELOG = [
    ChangelogEntry(
        version=_SCHEMA_VERSION,
        change="Initial baked word-search payload: a grid of ezhuthu and the words hidden in it.",
        why=(
            "Row 20 - the fourth Game, and the first whose payload holds more "
            "than one answer. It costs a payload schema and a builder, not an "
            "edit to puzzle-file or to the day loop, which is the fourth time "
            "one-schema-per-Game has held. The grid's shape and each word's "
            "segmentation are both derived rather than stored, on the "
            "precedent that a stored copy of a derived value is a drift "
            "surface; what does travel is where each word starts and which way "
            "it runs, because reading that back out of the grid is how the "
            "contract proves the player can find it."
        ),
    )
]

# The CLOSED vocabulary a hint template may name for THIS Game: nothing.
#
# This board PRINTS the words it is asking for. Every rung the shared ladder can
# render is therefore a fact already on the player's screen - the category of a
# word they can read, the first ezhuthu of a word they can read, or the meaning
# of a word they can read - and none of the three brings a player one cell
# closer to finding it. What a player actually lacks is a LOCATION, and a
# location cannot be a baked rung: its text would have to name one particular
# word, so whether it is worth anything depends on whether that word is still
# unfound when the rung is bought, and a rung that can be worthless by timing is
# a rung that charges for nothing. That is the same test that deleted the
# ``length`` rung and refused ``firstEzhuthu`` twice, applied to the whole
# ladder.
#
# The help this Game gives instead is a REVEAL, priced in the word it hands
# over: the player forfeits that word's points and keeps the rest. It cannot be
# expressed as a ``Hint`` because its cost depends on which words are still
# unfound at the moment it is spent, so it lives in the Game rather than in the
# payload - and this Game consequently bakes no ``hints`` at all, which is why
# ``config/app-config.json`` needs no ``hints.perGame`` entry for it: the
# allowance defaults to zero.
HINT_FIELDS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class ServedIndex:
    """One served set, indexed for the two questions this Game asks of it.

    ``rows`` is every servable word in a stable order, because a board needs
    several of them and the day loop only picks one. ``words`` is the same set
    as strings, because after the grid is filled it has to be scanned for what
    it accidentally spells.
    """

    rows: tuple[GameWord, ...]
    words: frozenset[str]
    lengths: tuple[int, ...]


def index_served(wordlist: GameWordlist, spec: GameGeneration) -> ServedIndex:
    """Index one served set: its rows, its words, and the lengths it holds.

    ``spec`` is unread here and is part of the signature because the day loop
    prepares every Game's set the same way; a Game that needs its own knobs to
    build the index reads them from it.
    """
    del spec
    rows = tuple(sorted(wordlist.words, key=lambda row: row.word))
    return ServedIndex(
        rows=rows,
        words=frozenset(row.word for row in rows),
        lengths=tuple(sorted({len(row.ezhuthu) for row in rows})),
    )


def band_candidates(served: ServedIndex, band: DifficultyBand) -> list[GameWord]:
    """The served rows this band is willing to hide: its lengths, its quarters."""
    return [
        row
        for row in served.rows
        if band.minLength <= len(row.ezhuthu) <= band.maxLength
        and row.frequencyStratum <= band.maxStratum
    ]


def choose_words(
    anchor: GameWord,
    served: ServedIndex,
    band: DifficultyBand,
    count: int,
    seed_text: str,
    used: frozenset[str] = frozenset(),
) -> list[GameWord]:
    """The board's whole word list: the day's anchor plus its companions.

    The anchor leads because it is the row the day loop chose - stratified,
    unrepeated, and already checked against everything the bank has served - and
    dropping it would throw all of that away. Its companions come from the same
    band, so an easy board is four familiar words rather than one familiar word
    and three from the tail.

    They are also drawn against the same ledger the anchor was. A companion is a
    word the player is asked to find, so hiding one the bank has already hidden
    is the same repeat as dealing the anchor twice - it is only less visible.
    When the band does not hold enough fresh words the shortfall is TOPPED UP
    from the served ones rather than the board shipping short, which is the day
    loop's own policy (``pick_words``: a repeat is a much smaller failure than a
    playlist that does not add up) and the ladder bank's last resort.

    Words are returned LONGEST FIRST, because that is the order they will be
    placed in: a long word has the fewest positions that fit it, so placing it
    into an empty grid and letting the short ones fill in around it is what
    keeps the packing from failing on the last word.
    """
    if count < 1:
        raise ValueError(f"a board needs at least one word, not {count}")
    pool = [row for row in band_candidates(served, band) if row.word != anchor.word]
    if len(pool) < count - 1:
        raise ValueError(
            f"the {band.id!r} band offers {len(pool) + 1} words for a {count}-word board"
        )
    fresh = [row for row in pool if row.word not in used]
    order = seeded_shuffle(fresh, f"{seed_text}|companions")
    if len(order) < count - 1:
        served_before = [row for row in pool if row.word in used]
        order = order + seeded_shuffle(served_before, f"{seed_text}|repeat")
    chosen = [anchor, *order[: count - 1]]
    return sorted(chosen, key=lambda row: (-len(row.ezhuthu), row.word))


def place_word(
    grid: list[list[str | None]],
    units: Sequence[str],
    seed_text: str,
) -> tuple[int, int, str] | None:
    """Put one word on the grid, or answer ``None`` when nothing fits.

    Every start is tried, in an order the seed fixes, and the first that fits
    wins. "Fits" is two conditions: the whole word stays on the grid, and every
    cell it wants is either empty or already holds the same ezhuthu - which is
    what lets two words CROSS on a shared letter instead of one of them being
    refused. A grid without crossings is a grid of parallel stripes, and it is
    also a much emptier one, because every word then needs cells of its own.
    """
    height = len(grid)
    width = len(grid[0]) if height else 0
    starts = [
        (row, col, direction)
        for row in range(height)
        for col in range(width)
        for direction in sorted(STEPS)
    ]
    for row, col, direction in seeded_shuffle(starts, seed_text):
        cells = path_cells(row, col, direction, len(units))
        if any(not (0 <= y < height and 0 <= x < width) for y, x in cells):
            continue
        if any(
            grid[y][x] is not None and grid[y][x] != unit
            for (y, x), unit in zip(cells, units)
        ):
            continue
        for (y, x), unit in zip(cells, units):
            grid[y][x] = unit
        return (row, col, direction)
    return None


def fill_grid(
    grid: list[list[str | None]], letters: Sequence[str], seed_text: str
) -> int:
    """Fill every empty cell from the TARGETS' own multiset of ezhuthu.

    Three fillers were considered and this one was measured against the other
    two over 400 generated grids:

    - Uniform over the 247 would put letters in the grid that Tamil barely uses
      and the result would not read as Tamil at all.
    - Sampling the whole served set's ezhuthu distribution reads correctly, but
      it LEAKS: 30.7 percent of all cells then hold a letter that appears in no
      target, and a player can strike those out on sight without searching. Over
      the filler cells alone that is most of them.
    - Sampling the placed words' own letters leaks nothing by construction - every
      filler cell holds a letter some target really uses - and it was also
      measured to produce FEWER unintended words (a mean of 1.04 per grid
      against 1.19), because a smaller alphabet drawn from six real words is a
      narrower target than the whole language.

    The bag is dealt rather than sampled: the letters are repeated to cover the
    empty cells and shuffled once, so the grid's letter proportions are the
    targets' own exactly rather than approximately, and no rare letter goes
    missing to sampling noise on a 64-cell board.
    """
    empty = [
        (row, col)
        for row in range(len(grid))
        for col in range(len(grid[row]))
        if grid[row][col] is None
    ]
    if not empty:
        return 0
    if not letters:
        raise ValueError("no letters to fill from")
    base = seeded_shuffle(sorted(letters), f"{seed_text}|pool")
    repeats = math.ceil(len(empty) / len(base))
    bag = seeded_shuffle((base * repeats)[: len(empty)], f"{seed_text}|fill")
    for (row, col), unit in zip(empty, bag):
        grid[row][col] = unit
    return len(empty)


def unintended_words(
    grid: list[list[str]], served: ServedIndex, targets: Sequence[str]
) -> list[str]:
    """Every served word the finished grid spells that nobody asked it to.

    Scanned against the set this Game SERVES rather than against the language,
    on the same terms as the anagram's alternatives index: telling a player that
    what they traced is a word only helps when it is a word this game would
    actually deal. Both directions are covered without special-casing, because
    the eight directions are closed under negation.

    A run of ezhuthu is not a run of characters, so the scan compares JOINED
    cells rather than a substring of a rendered row: two adjacent cells holding
    a mei and a uyir spell a two-ezhuthu string that a character-wise scan would
    also find inside a longer cluster sequence that is not there at all.
    """
    height = len(grid)
    width = len(grid[0]) if height else 0
    asked = set(targets)
    wanted = set(served.lengths)
    longest = max(wanted)
    found: set[str] = set()
    for row in range(height):
        for col in range(width):
            for direction in sorted(STEPS):
                step_row, step_col = STEPS[direction]
                # One walk per line rather than one per length: the prefixes of
                # a single walk ARE the runs of every length that starts here.
                run = ""
                for step in range(longest):
                    y, x = row + step_row * step, col + step_col * step
                    if not (0 <= y < height and 0 <= x < width):
                        break
                    run += grid[y][x]
                    if step + 1 in wanted and run in served.words and run not in asked:
                        found.add(run)
    return sorted(found)


def build_hints(
    row: GameWord, spec: GameGeneration, limit: int, themed: bool = False
) -> list[Hint]:
    """Always empty - see ``HINT_FIELDS`` for why this Game's ladder has no rungs.

    It delegates to the shared machinery rather than returning ``[]`` outright,
    and that is the point: with an empty vocabulary, a hint template registered
    against this Game names a field it cannot sell and fails the bake loudly.
    An early ``return []`` would swallow the same config mistake in silence.
    """
    del themed
    return hint_ladder.build_hints(row, spec, limit, {}, HINT_FIELDS)


def _hide(
    words: Sequence[GameWord], spec: GameGeneration, seed_text: str
) -> tuple[list[list[str]], list[WordSearchTarget]] | None:
    """Hide every word on an empty grid, or ``None`` when one of them will not fit.

    ``None`` rather than a raise because the caller has a second word list to
    try: which words a board holds is now a preference (see ``choose_words``),
    and a preference that cannot be packed has to be able to fall back.
    """
    grid: list[list[str | None]] = [
        [None] * spec.gridCols for _ in range(spec.gridRows)
    ]
    targets: list[WordSearchTarget] = []
    for word in words:
        units = list(word.ezhuthu)
        spot = place_word(grid, units, f"{seed_text}|{word.word}")
        if spot is None:
            return None
        start_row, start_col, direction = spot
        targets.append(
            WordSearchTarget(
                word=word.word,
                start=GridPoint(row=start_row, col=start_col),
                direction=direction,
                meaning=hint_ladder.display_meaning(word),
            )
        )
    letters = [unit for word in words for unit in word.ezhuthu]
    fill_grid(grid, letters, seed_text)
    return [[cell for cell in line if cell is not None] for line in grid], targets


def build_puzzle(
    row: GameWord,
    spec: GameGeneration,
    seed_text: str,
    hint_limit: int,
    band: DifficultyBand,
    served: ServedIndex,
    themed: bool = False,
    used: frozenset[str] = frozenset(),
) -> WordSearchPuzzle:
    """Build one validated word-search board from a derived-wordlist row.

    ``used`` is the day's ledger - every word the bank has already asked for -
    and it narrows which companions this board hides. An empty ledger is the
    honest default for a board built outside a bake: nothing has been served, so
    nothing is off limits.

    ``themed`` is accepted and unused: this Game sells no rungs, so there is no
    ``category`` rung a theme could make redundant. Taking it and saying so
    keeps every Game's builder callable the same way (Row 19's ``seed_text``
    did the same for the opposite reason).
    """
    del themed
    # Not a no-op: with an empty vocabulary this raises when config has
    # registered a rung against this Game and raised its allowance to match.
    build_hints(row, spec, hint_limit)
    packed = _hide(
        choose_words(row, served, band, band.targets, seed_text, used), spec, seed_text
    )
    if packed is None and used:
        # Fresh companions that will not pack are worth less than a repeat: fall
        # back to the draw this board would have made with an empty ledger.
        packed = _hide(
            choose_words(row, served, band, band.targets, seed_text), spec, seed_text
        )
    if packed is None:
        raise ValueError(
            f"a {spec.gridRows}x{spec.gridCols} grid does not hold the {band.id!r} "
            f"band's {band.targets} words anchored on {row.word!r}"
        )
    filled, targets = packed
    extra = unintended_words(filled, served, [target.word for target in targets])
    return WordSearchPuzzle(
        version=_SCHEMA_VERSION,
        changelog=_CHANGELOG,
        grid=filled,
        targets=targets,
        alsoValid=extra or None,
    )
