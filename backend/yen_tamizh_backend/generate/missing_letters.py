"""Turn one derived-wordlist row into a playable ``missing-letters`` payload.

The Game (Row 18) knows how to fill a hole; this knows how to punch one. It
takes a word the derived layer already vouched for, hides whole ezhuthu of it,
and offers a bank the hidden ones can be picked out of.

Four guarantees this module owns:

- **A blank is a WHOLE ezhuthu.** Positions index the Row 6 segmentation, never
  code points, so a hole can never swallow half a cluster and leave a pulli
  floating on its own. The contract re-derives that segmentation and validates
  the indices against it, so this is checked rather than promised.
- **The mask is chosen, not accepted.** Blanking the middle of a short word can
  admit several real answers. Unlike the anagram, which is handed the tiles it
  must work with, this generator gets to pick WHICH ezhuthu to hide - so it
  scores every candidate mask against the served set and takes one that admits
  the fewest other words. When a mask with a single answer exists it wins.
- **What else fits the mask is RECORDED, not required.** On the words where no
  mask is unique the puzzle is still dealt, carrying the other served words the
  player could legitimately build. That is the repo's settled precedent for the
  anagram's ``alsoValid`` (schemas.md) and it earns its keep the same way: a
  player who spells a real Tamil word and is told "wrong" concludes the game
  cheated, while "that is a word, but not today's" teaches them one.
- **Everything is a pure function of the seed.** Which mask, which decoys, and
  what order the bank is shown in all come from the shared FNV-1a + mulberry32
  pair, never from ``random`` - two runs of the same date bake the same bytes.

The bank exists because there is no Tamil keyboard in this game and there is not
going to be one, so its SIZE is a real balance number rather than a layout
preference: it is the odds that a player who knows nothing still guesses right
inside the allowed attempts. It lives in ``config/daily-generator.json``
(Holy Law #6).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from itertools import combinations

from yen_tamizh_backend.contracts.base import ChangelogEntry
from yen_tamizh_backend.contracts.common import Hint
from yen_tamizh_backend.contracts.daily_generator import GameGeneration
from yen_tamizh_backend.contracts.game_wordlist import GameWord, GameWordlist
from yen_tamizh_backend.contracts.missing_letters_puzzle import MissingLettersPuzzle
from yen_tamizh_backend.generate import hints as hint_ladder
from yen_tamizh_backend.generate.seed import seeded_index, seeded_shuffle

GAME_ID = "missing-letters"

_SCHEMA_VERSION = "2026-08-19"
_CHANGELOG = [
    ChangelogEntry(
        version=_SCHEMA_VERSION,
        change="Initial baked missing-letters payload: a masked word and its choice bank.",
        why=(
            "Row 18 - the second Game, and the first one to prove the "
            "one-payload-schema-per-Game claim: it costs a payload schema and a "
            "builder, not an edit to puzzle-file or to the day loop. The "
            "segmentation deliberately does NOT travel - blanks index "
            "segment(word), which both sides already run - because a stored "
            "copy of a derived value is a drift surface."
        ),
    )
]

# The CLOSED vocabulary a hint template may name for THIS Game.
#
# ``firstEzhuthu`` is deliberately absent, and the reason is the mechanic rather
# than the data: this board has already PRINTED every ezhuthu it is not hiding.
# If the first ezhuthu is shown, the rung charges for a fact on the screen - the
# same mistake the deleted ``length`` rung made. If the first ezhuthu is the one
# hidden, the rung IS the answer. There is no third case, so the field can never
# be an honest rung here and the vocabulary refuses it outright rather than
# leaving it to a config template to get right.
HINT_FIELDS = frozenset({"category", "meaning"})

# Served rows grouped by ezhuthu count: the only rows that can fit another row's
# mask are the ones exactly as long as it. Built once per set per day.
ServedByLength = dict[int, tuple[tuple[str, tuple[str, ...]], ...]]


def index_by_length(wordlist: GameWordlist, spec: GameGeneration) -> ServedByLength:
    """Group one served set by ezhuthu count - what a mask is scored against.

    ``spec`` is unread here and is part of the signature because the day loop
    prepares every Game's set the same way; a Game that needs its own knobs to
    build the index reads them from it.
    """
    del spec
    grouped: dict[int, list[tuple[str, tuple[str, ...]]]] = {}
    for row in wordlist.words:
        grouped.setdefault(len(row.ezhuthu), []).append((row.word, tuple(row.ezhuthu)))
    return {length: tuple(rows) for length, rows in grouped.items()}


def _difference_bits(left: Sequence[str], right: Sequence[str]) -> int:
    """Which positions two equal-length ezhuthu sequences disagree on, as a bitmask."""
    bits = 0
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            bits |= 1 << index
    return bits


def near_words(
    row: GameWord, served: ServedByLength, max_blanks: int
) -> list[tuple[int, str, tuple[str, ...]]]:
    """Every other served word this one could be confused with, and where.

    A served word fits a mask exactly when the positions it disagrees with the
    answer on all fall INSIDE the mask - so one pass computing that disagreement
    set answers every candidate mask at once, instead of indexing the millions
    of masks the whole served set could be dealt under. Words disagreeing in
    more places than the mask has holes can never fit any of them and are
    dropped here.
    """
    target = tuple(row.ezhuthu)
    out: list[tuple[int, str, tuple[str, ...]]] = []
    for word, ezhuthu in served.get(len(target), ()):
        if word == row.word:
            continue
        bits = _difference_bits(target, ezhuthu)
        if bin(bits).count("1") <= max_blanks:
            out.append((bits, word, ezhuthu))
    return out


def choose_blanks(
    row: GameWord, served: ServedByLength, blank_count: int, seed_text: str
) -> tuple[tuple[int, ...], tuple[tuple[str, tuple[str, ...]], ...]]:
    """Pick which ezhuthu to hide, and say what else the resulting mask admits.

    Every mask of the requested size is scored by how many OTHER served words
    fit it, and the fewest wins - so a mask with exactly one answer is taken
    whenever the word has one. Ties are broken by the seed rather than by
    position order, or the hole would sit in the same place on every word of a
    given shape and the puzzle would become a habit instead of a read.

    Returns the blanked positions and the other served words the chosen mask
    admits, each with its own segmentation so the caller need not re-derive it.
    """
    length = len(row.ezhuthu)
    if blank_count >= length:
        raise ValueError(
            f"cannot hide {blank_count} of the {length} ezhuthu of {row.word!r}"
        )
    near = near_words(row, served, blank_count)
    scored: list[tuple[int, tuple[int, ...], tuple[tuple[str, tuple[str, ...]], ...]]] = []
    for positions in combinations(range(length), blank_count):
        mask = 0
        for position in positions:
            mask |= 1 << position
        fits = tuple(
            sorted(
                (word, ezhuthu) for bits, word, ezhuthu in near if bits & ~mask == 0
            )
        )
        scored.append((len(fits), positions, fits))
    fewest = min(count for count, _, _ in scored)
    tied = [entry for entry in scored if entry[0] == fewest]
    _, positions, fits = tied[seeded_index(len(tied), seed_text)]
    return positions, fits


def build_choices(
    row: GameWord,
    blanks: Sequence[int],
    served: ServedByLength,
    count: int,
    seed_text: str,
) -> list[str]:
    """The bank the player picks from: the hidden ezhuthu plus plausible decoys.

    Decoys are drawn from the ezhuthu that OTHER served words of the same length
    actually carry in one of the blanked slots, so every option is a shape Tamil
    really puts there. A bank padded with letters that could never stand in that
    position would be eight tiles pretending to be a choice between two.

    A decoy is free to complete a different SERVED word: that word already fits
    the mask, so it is in the puzzle's ``alsoValid`` and the Game answers it
    rather than rejecting it.
    """
    hidden = [row.ezhuthu[index] for index in blanks]
    needed = count - len(hidden)
    if needed < 1:
        raise ValueError(
            f"choiceCount {count} leaves no decoy beside {len(hidden)} hidden ezhuthu"
        )
    taken = set(hidden)
    plausible = {
        ezhuthu[index]
        for _, ezhuthu in served.get(len(row.ezhuthu), ())
        for index in blanks
    } - taken
    pool = seeded_shuffle(sorted(plausible), f"{seed_text}|decoy")
    if len(pool) < needed:
        # Only reachable on a served set too thin to fill a slot - top up from
        # everything the set spells anywhere rather than shipping a short bank.
        elsewhere = {
            unit
            for rows in served.values()
            for _, ezhuthu in rows
            for unit in ezhuthu
        } - taken - set(pool)
        pool = pool + seeded_shuffle(sorted(elsewhere), f"{seed_text}|spare")
    if len(pool) < needed:
        raise ValueError(
            f"only {len(pool)} decoys available for {row.word!r}, need {needed}"
        )
    return seeded_shuffle(hidden + pool[:needed], f"{seed_text}|bank")


def hint_values(row: GameWord, spec: GameGeneration, themed: bool) -> dict[str, str]:
    """Exactly the hint fields this row can honestly fill, on this kind of day.

    On a THEMED day ``category`` is absent for every row, not just the ones
    without one: the theme is announced free in the round header, so the rung
    would charge for a fact already on screen.
    """
    values: dict[str, str] = {}
    if not themed:
        category = hint_ladder.category_tag(row, spec)
        if category is not None:
            values["category"] = category
    meaning = hint_ladder.sellable_meaning(row)
    if meaning is not None:
        values["meaning"] = meaning
    return values


def build_hints(
    row: GameWord, spec: GameGeneration, limit: int, themed: bool = False
) -> list[Hint]:
    """Render the first ``limit`` rungs this row can HONESTLY answer."""
    return hint_ladder.build_hints(
        row, spec, limit, hint_values(row, spec, themed), HINT_FIELDS
    )


def build_puzzle(
    row: GameWord,
    spec: GameGeneration,
    seed_text: str,
    hint_limit: int,
    blank_count: int,
    served: ServedByLength,
    themed: bool = False,
) -> MissingLettersPuzzle:
    """Build one validated missing-letters puzzle from a derived-wordlist row.

    ``served`` is the set the day actually drew from, which on a themed day is
    the theme's own: what else a mask admits may only name words this Game would
    really deal.

    An alternative the bank cannot spell is DROPPED here rather than shipped. It
    fits the mask, but nobody was offered the ezhuthu it needs, so recording it
    would cost bytes for a message that can never fire. The bank is counted with
    MULTIPLICITY, not membership: a two-blank alternative that needs the same
    ezhuthu twice is unreachable from a bank holding one of it, and the contract
    refuses that payload - which is how this was found.
    """
    blanks, admits = choose_blanks(row, served, blank_count, seed_text)
    choices = build_choices(row, blanks, served, spec.choiceCount, seed_text)
    bank = Counter(choices)
    also_valid = sorted(
        word
        for word, ezhuthu in admits
        if not Counter(ezhuthu[index] for index in blanks) - bank
    )
    return MissingLettersPuzzle(
        version=_SCHEMA_VERSION,
        changelog=_CHANGELOG,
        word=row.word,
        blanks=list(blanks),
        choices=choices,
        attempts=spec.attempts,
        hints=build_hints(row, spec, hint_limit, themed) or None,
        meaning=hint_ladder.display_meaning(row),
        translationEn=row.translationEn,
        alsoValid=also_valid or None,
    )
