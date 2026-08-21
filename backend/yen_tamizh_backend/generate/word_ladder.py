"""Build the add-one-ezhuthu reachability graph, and climb it, at BUILD time.

The Game (Row 16) knows how to drop a letter onto a row of tiles; this knows
which letters can be dropped and where the climb can go. It is the third builder
that deals more than one word - the search board and the crossword were the
first two - and, like the crossword, its whole reason to exist at build time is
that the browser must never search for anything (Holy Law #1). A ladder the
player is handed is a ladder that has already been proved to climb.

**The measurement that shaped this row.** The fear the plan recorded was that
Tamil short-word density would be too thin for pure search, and that a curated
seed list would be needed to guarantee content. Measured over the served set,
the graph IS thin - 35,991 ezhuthu multisets carry only 16,983 add-one edges, so
the average node has half an edge - but thin is not empty, and the shape of the
thinness is what matters: the edges concentrate at the bottom. Of the 1,812
two-ezhuthu multisets, 1,384 can climb at least one rung and 358 can climb three
more; of the 3,381 seven-ezhuthu ones, none can climb at all, which is only to
say the ladder has a top. Enumerated exhaustively, the served set holds 6,218
distinct four-rung climbs and 1,476 five-rung ones. Four rungs a day is
seventeen years of content. So the seed list is NOT built: this module's search
finds more ladders than a Daily can spend, and an unused curated file would be
one more thing to keep in step with a lexicon that changes underneath it.

Four things this module owns:

- **The graph is a multiset index, not an adjacency list of words.** Two words
  are one rung apart exactly when their ezhuthu MULTISETS are, so the nodes are
  multisets and the words hang off them. That collapses co-anagrams into one
  node - which is right, because they are the same tiles - and it turns edge
  building into "drop each letter of a signature and look up what is left",
  which is linear in the set rather than quadratic.
- **Reach is computed once, downward from the top.** ``reach[signature]`` is the
  most rungs a climb starting there can have. With it, choosing the next rung is
  a filter rather than a search: only a neighbour that can still finish the
  ladder is ever stepped onto, so the climb never backtracks and never ships a
  ladder that dead-ends.
- **A rung is the most familiar word its tiles spell.** The player has to GUESS
  each next word from letters and a bank, so the word chosen at each node is the
  one the lexicon says is most frequent; the other words those same tiles spell
  are recorded in that rung's ``alsoValid`` rather than thrown away.
- **Everything is a pure function of the seed.** Which neighbour is stepped onto
  and which decoys pad the bank come from the shared FNV-1a + mulberry32 pair,
  never from ``random``, so two runs of the same date bake the same bytes.

The bank exists for the reason the missing-letters board's does - there is no
Tamil keyboard in this game - and its decoys are drawn from the letters that
would REALLY have spelled another served word at that rung, so every option is a
step Tamil actually offers rather than a tile that could only ever be wrong.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from math import inf as INF

from yen_tamizh_backend.contracts.base import ChangelogEntry
from yen_tamizh_backend.contracts.common import Hint
from yen_tamizh_backend.contracts.daily_generator import DifficultyBand, GameGeneration
from yen_tamizh_backend.contracts.game_wordlist import GameWord, GameWordlist
from yen_tamizh_backend.contracts.word_ladder_puzzle import (
    LadderRung,
    WordLadderPuzzle,
)
from yen_tamizh_backend.generate import Unbuildable
from yen_tamizh_backend.generate import hints as hint_ladder
from yen_tamizh_backend.generate.seed import seeded_shuffle

GAME_ID = "word-ladder"

_SCHEMA_VERSION = "2026-08-21"
_CHANGELOG = [
    ChangelogEntry(
        version=_SCHEMA_VERSION,
        change=(
            "Initial baked word-ladder payload: the rungs in order, the ezhuthu "
            "bank they are climbed from, and the clock."
        ),
        why=(
            "Row 15 - the sixth Game's payload, and the second whose content is "
            "a proof rather than a deal: the browser is handed a climb the "
            "build already walked, because computing reachability at runtime is "
            "forbidden and would risk shipping a ladder that does not climb. "
            "Neither the per-rung segmentation, the added ezhuthu, nor a start "
            "length travels, though the plan sketched all three: each is a "
            "second statement of a fact the rung's own word already makes, and "
            "a stored copy of a derived value is a drift surface. What DOES "
            "travel and could not be derived is the bank - there is no Tamil "
            "keyboard, so an addition has to be picked from something - and what "
            "else that bank spells at each rung."
        ),
    )
]

# The CLOSED vocabulary a hint template may name for THIS Game: nothing.
#
# Every rung the shared ladder can render - a category, a first ezhuthu, a
# meaning - is a fact about ONE word, and on this board that word is always the
# NEXT rung, because a climb is answered in order. So the rung is never
# worthless by timing, which is what emptied the search board's ladder and the
# crossword's; it is worthless for the opposite reason. A ladder's difficulty is
# the STEP, and a baked rung about the next word would have to be bought at the
# only moment it is worth anything and would then hand over most of a word that
# is three or four letters long.
#
# The help this Game gives instead is a per-rung REVEAL, priced in the rung it
# hands over: the player forfeits that step's points and keeps the climb. Which
# rung is outstanding is a play-time fact, so it lives in the Game rather than
# in the payload - and this Game consequently bakes no ``hints`` at all, which
# is why ``config/app-config.json`` needs no ``hints.perGame`` entry for it: the
# allowance defaults to zero.
HINT_FIELDS: frozenset[str] = frozenset()

# The order-free key two words share exactly when the same tiles spell both.
# Sorting the EZHUTHU rather than the code points is what makes this a Tamil
# multiset rather than a byte one.
Signature = tuple[str, ...]


class NoLadder(Unbuildable):
    """This word cannot start a ladder of the length the band asks for.

    Raised rather than returned so a bake can never quietly ship a climb that
    stops short. It is an ``Unbuildable``, so the day loop answers a word it
    cannot climb from by dealing the next candidate rather than by failing the
    day - which is what it has to be, because most served words start no ladder
    at all: only 6,563 of the 35,991 multisets can be climbed from even once,
    and only 623 can carry a four-rung ladder.
    """


def signature(ezhuthu: Sequence[str]) -> Signature:
    """The multiset key: the tiles, order removed."""
    return tuple(sorted(ezhuthu))


def step(below: Signature, above: Signature) -> str:
    """The one ezhuthu ``above`` adds over ``below``, read off the multisets.

    The same value ``added_ezhuthu`` reads off the two WORDS, and it has to be:
    a signature IS ``sorted(segment(word))``. It is computed here rather than by
    joining the signatures back into strings, because a sorted run of ezhuthu is
    not a word and re-segmenting it could legitimately cluster two of them into
    one. The contract still states the rule over the words the player is shown -
    that is what a payload is validated against - so the two agree by
    construction and are checked against each other by test.
    """
    gained = Counter(above) - Counter(below)
    if sum(gained.values()) != 1:
        raise ValueError(f"{above} is not one ezhuthu above {below}")
    return next(iter(gained))


@dataclass(frozen=True)
class LadderGraph:
    """The served set as an add-one-ezhuthu graph over ezhuthu multisets.

    ``words`` maps a signature to the served rows those tiles spell, most
    frequent first. ``up`` maps a signature to the signatures exactly one
    ezhuthu above it. ``reach`` is the most rungs a climb starting at a
    signature can have, counting that signature as the first. ``promise[key][r]``
    is how familiar the RAREST of the ``r - 1`` rungs above ``key`` can be made,
    over every climb of ``r`` signatures that starts there. ``letters`` is every
    ezhuthu the set spells with anywhere, which is the last resort a bank is
    padded from.
    """

    words: dict[Signature, tuple[GameWord, ...]]
    up: dict[Signature, tuple[Signature, ...]]
    reach: dict[Signature, int]
    promise: dict[Signature, tuple[float, ...]]
    letters: tuple[str, ...]

    def best_word(self, key: Signature) -> GameWord:
        """The most familiar word those tiles spell - the rung a player can guess."""
        return self.words[key][0]


def index_served(wordlist: GameWordlist, spec: GameGeneration) -> LadderGraph:
    """Build the whole reachability graph once, for one served set.

    ``spec`` is unread here and is part of the signature because the day loop
    prepares every Game's set the same way.

    Edges are found by REMOVAL rather than by addition: for each signature, drop
    each of its letters in turn and look the remainder up. That is one pass over
    the index costing the total ezhuthu of the set, where trying every one of the
    247 letters against every signature would cost 247 times its size and find
    exactly the same edges.

    Two values are then folded downward from the top, in one pass each, and both
    turn a search into a filter. ``reach`` says whether a neighbour can still
    finish the ladder; ``promise`` says how good the rest of the climb can be if
    it is taken. Neither can be computed while climbing, because both are facts
    about everything ABOVE a node.
    """
    del spec
    words: dict[Signature, list[GameWord]] = {}
    for row in wordlist.words:
        words.setdefault(signature(row.ezhuthu), []).append(row)
    # Most frequent first, the word as the tie-break so the order is total and
    # the bytes are reproducible.
    ordered = {
        key: tuple(sorted(rows, key=lambda row: (-row.frequency, row.word)))
        for key, rows in words.items()
    }
    up: dict[Signature, list[Signature]] = {}
    for key in ordered:
        seen: set[Signature] = set()
        for index in range(len(key)):
            below = key[:index] + key[index + 1 :]
            if below in seen or below not in ordered:
                continue
            seen.add(below)
            up.setdefault(below, []).append(key)
    edges = {key: tuple(sorted(above)) for key, above in up.items()}
    # Downward from the longest signatures, so every neighbour is already known.
    reach: dict[Signature, int] = {}
    for key in sorted(ordered, key=len, reverse=True):
        reach[key] = 1 + max((reach[above] for above in edges.get(key, ())), default=0)
    tallest = max(reach.values(), default=1)
    # Index 0 is never read; index 1 is a climb of one signature, which adds no
    # rung at all and so has no rarest one to bound.
    table: dict[Signature, list[float]] = {
        key: [0.0, INF] + [0.0] * (tallest - 1) for key in ordered
    }
    for rungs in range(2, tallest + 1):
        for key in ordered:
            table[key][rungs] = max(
                (
                    min(float(ordered[above][0].frequency), table[above][rungs - 1])
                    for above in edges.get(key, ())
                    if reach[above] >= rungs - 1
                ),
                default=0.0,
            )
    return LadderGraph(
        words=ordered,
        up=edges,
        reach=reach,
        promise={key: tuple(row) for key, row in table.items()},
        letters=tuple(sorted({unit for key in ordered for unit in key})),
    )


def climb(
    graph: LadderGraph,
    start: Signature,
    rungs: int,
    seed_text: str,
    used: frozenset[str] = frozenset(),
) -> list[Signature]:
    """Walk ``rungs`` signatures up from ``start``, or raise ``NoLadder``.

    No backtracking, and none is needed: ``reach`` already says how far every
    neighbour can go, so the walk only ever steps onto one that can still finish.

    Among those it takes the step that leaves the RAREST rung of the finished
    climb as familiar as it can be - the neighbour maximising
    ``min(its own frequency, promise above it)``. That is not a tie-break dressed
    up: a ladder is played by guessing each next word from tiles and a bank, so
    one word nobody knows ends the climb however good the rest of it is, and the
    thing worth maximising is therefore the WEAKEST rung rather than the average.
    Measured over every eligible start, choosing this way lifts the median
    rarest rung of a four-rung climb from 3 occurrences to 9 and more than
    doubles the ladders whose every rung occurs at least 20 times (91 to 225),
    at no cost in how many ladders exist - it only ever reorders neighbours that
    already keep the climb alive. Taking the most familiar NEXT rung instead,
    without looking further up, recovers less than half of that (162).

    ``used`` is the day's ledger, and a neighbour whose word the bank has
    already served is stepped over. Only stepped OVER, not refused outright: a
    rung the ledger blocks is skipped while any other neighbour can still finish
    the climb, and taken when none can. ``reach`` is a fact about the graph, not
    about the ledger, so a ledger that emptied a node would strand a climb that
    reach promised would finish - and a ladder that stops three rungs up is a
    much bigger failure than one that repeats a word (``pick_words``' own
    trade). The step is therefore local: only the rungs that have to repeat do.

    Greedy is enough, and that is measured rather than assumed. Over 180 baked
    days, 75 ladders climbed clean and 7 had to repeat a rung - and an
    exhaustive backtracking search over the same starts and the same ledgers
    found an all-fresh climb for NONE of those 7. The graph is that thin: 16,983
    add-one edges over 35,991 multisets is half an edge a node, so a blocked
    step is usually the only step there was, and backtracking would buy nothing
    for the cost of abandoning the rarest-rung objective above.

    The seed breaks ties, and only ties. Variety across days comes from the day
    loop dealing a different START word - it never deals one twice - rather than
    from climbing one start two ways.
    """
    if rungs < 2:
        raise ValueError(f"a ladder needs at least two rungs, not {rungs}")
    if graph.reach.get(start, 0) < rungs:
        raise NoLadder(
            f"the tiles {list(start)} climb {graph.reach.get(start, 0)} rungs, not "
            f"{rungs}"
        )
    chain = [start]
    while len(chain) < rungs:
        left = rungs - len(chain)
        viable = [
            above for above in graph.up.get(chain[-1], ()) if graph.reach[above] >= left
        ]
        fresh = [above for above in viable if graph.best_word(above).word not in used]
        order = seeded_shuffle(fresh or viable, f"{seed_text}|rung{len(chain)}")
        chain.append(
            max(
                order,
                key=lambda above: min(
                    float(graph.best_word(above).frequency), graph.promise[above][left]
                ),
            )
        )
    return chain


def choose_bank(
    graph: LadderGraph, chain: Sequence[Signature], count: int, seed_text: str
) -> list[str]:
    """The bank an addition is picked from: what the climb needs, plus decoys.

    Decoys are drawn from the letters that would really have spelled ANOTHER
    served word at one of the rungs, so every option in the bank is a step Tamil
    offers rather than a tile that could only ever be wrong. A decoy that does
    spell a real word is not a defect - that word is in the rung's ``alsoValid``
    and the Game answers it - which is exactly the missing-letters ruling about
    a decoy completing a different served word.
    """
    needed = [step(below, above) for below, above in zip(chain, chain[1:])]
    if count <= len(needed):
        raise ValueError(
            f"choiceCount {count} leaves no decoy beside {len(needed)} additions"
        )
    plausible = {
        step(below, above)
        for below in chain[:-1]
        for above in graph.up.get(below, ())
    } - set(needed)
    pool = seeded_shuffle(sorted(plausible), f"{seed_text}|decoy")
    if len(pool) < count - len(needed):
        # Only reachable where every rung has almost no other step out of it:
        # top up from what the set spells anywhere rather than ship a short bank
        # (the missing-letters board's own last resort).
        spare = sorted(set(graph.letters) - set(needed) - set(pool))
        pool = pool + seeded_shuffle(spare, f"{seed_text}|spare")
    bank = needed + pool[: count - len(needed)]
    return seeded_shuffle(bank, f"{seed_text}|bank")


def alternatives(
    graph: LadderGraph, below: Signature, above: Signature, bank: Sequence[str]
) -> list[str]:
    """The other served words the bank reaches from ``below``, at ``above``'s height.

    Narrowed to what the player can actually enter: a letter not in the bank
    cannot be added, so a word needing one is a message that can never fire. The
    answer's own co-anagrams are included by construction - they hang off the
    same signature, which the real addition already reaches.
    """
    answer = graph.best_word(above).word
    reachable = {
        row.word
        for unit in set(bank)
        for row in graph.words.get(signature(list(below) + [unit]), ())
        if row.word != answer
    }
    return sorted(reachable)


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
    served: LadderGraph,
    themed: bool = False,
    used: frozenset[str] = frozenset(),
) -> WordLadderPuzzle:
    """Build one validated ladder from a derived-wordlist row and a band.

    The row the day loop picked is the ledge the player starts on, so the band's
    length range gates the START of the climb rather than its top - the rungs
    above it are whatever the graph proves reachable. ``band.targets`` is how
    many rungs the ladder holds, the same knob the search board uses for how many
    words its grid hides, because on both boards the number of words IS the
    difficulty.

    ``used`` is the day's ledger, and it steers which neighbour each step takes
    so the rungs above the ledge are as unrepeated as the ledge itself.

    ``themed`` is accepted and unused: this Game sells no rungs, so there is no
    ``category`` rung a theme could make redundant.
    """
    del themed
    # Not a no-op: with an empty vocabulary this raises when config has
    # registered a rung against this Game and raised its allowance to match.
    build_hints(row, spec, hint_limit)
    chain = climb(served, signature(row.ezhuthu), band.targets, seed_text, used)
    bank = choose_bank(served, chain, spec.choiceCount, seed_text)
    rungs = [
        LadderRung(
            word=row.word,
            meaning=hint_ladder.display_meaning(row),
            alsoValid=None,
        )
    ]
    for below, above in zip(chain, chain[1:]):
        answer = served.best_word(above)
        rungs.append(
            LadderRung(
                word=answer.word,
                meaning=hint_ladder.display_meaning(answer),
                alsoValid=alternatives(served, below, above, bank) or None,
            )
        )
    return WordLadderPuzzle(
        version=_SCHEMA_VERSION,
        changelog=_CHANGELOG,
        rungs=rungs,
        choices=bank,
        timeLimitSec=spec.timeLimitSec,
    )
