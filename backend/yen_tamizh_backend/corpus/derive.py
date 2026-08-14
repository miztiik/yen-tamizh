"""Derive the per-Game wordlists from the ranked master (Row 9).

This is the DERIVED layer, and only the derived layer. It reads the one artifact
the corpus layer produces, ``datasets/wordlists/master/words_ranked.json``,
applies the per-Game selection declared in ``config/derived-wordlists.json``, and
writes one ``game-wordlist`` per registered Game. It generates no puzzles, writes
nothing into ``frontend/public/``, and does not know what a day or a bank is -
the daily puzzle engine (Row 13) is a separate process that reads these sets::

    datasets/corpus/**  ->  master wordlist  ->  per-Game sets  ->  daily puzzles
       (raw sources)          (Row 8)             (this module)      (Row 13)

Adding a Game's set is a DATA change (see docs/how-to/add-a-derived-wordlist.md):
append an entry to ``config/derived-wordlists.json`` and re-run
``python -m yen_tamizh_backend.scripts.rebuild_wordlists``. The selection knobs -
ezhuthu length range, frequency bands, the word-final rule, the cap - are config
because they are tunable game-balance numbers (Holy Law #6); this module is the
mechanism that interprets them. Only a Game needing a predicate the knobs cannot
express costs code, which is the same line the corpus layer draws at an unseen
source FORMAT.

Derived sets are BUILD ARTIFACTS. They are regenerated in full by one command
and never hand edited, and they are a pure function of the master plus the
registry - no wall clock, so the same inputs always produce the same bytes.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path

from yen_tamizh_backend.contracts.base import ChangelogEntry
from yen_tamizh_backend.contracts.derived_wordlists import (
    DerivedSelection,
    DerivedSet,
    DerivedWordlists,
)
from yen_tamizh_backend.contracts.game_wordlist import (
    DerivedCounters,
    DerivedSource,
    GameWord,
    GameWordHints,
    GameWordlist,
)
from yen_tamizh_backend.contracts.master_wordlist import MasterWord, MasterWordlist
from yen_tamizh_backend.corpus.artifact import render_document, sha256_of
from yen_tamizh_backend.ezhuthu import ends_like_a_word

_SCHEMA_VERSION = "2026-08-14"
_CHANGELOG = [
    ChangelogEntry(
        version=_SCHEMA_VERSION,
        change=(
            "Removed the counters.withoutCoAnagram bucket along with the "
            "requireCoAnagram selection knob; added anagramFanOut to every row."
        ),
        why=(
            "Row 1 of the lexicon pipeline - demanding a second arrangement cut "
            "the served set 106-fold and selected for bound stems, because "
            "fragments are what collide with real words. The multiset index was "
            "measuring something worth keeping, so it now records fan-out on "
            "the row instead of deciding admission."
        ),
    ),
    ChangelogEntry(
        version="2026-08-13T20:08",
        change=(
            "Renamed hints.first_ezhuthu to hints.firstEzhuthu; added the "
            "counters.invalidWordFinal rejection bucket."
        ),
        why=(
            "Row 13 - every other persisted shape in the repo is camelCase, and "
            "the new word-final quality rule needs its own bucket so the "
            "counters still reconcile against the master."
        ),
    ),
    ChangelogEntry(
        version="2026-08-13",
        change="Initial per-Game derived wordlist cut from the ranked master.",
        why="Row 9 derived layer - the words one Game's generator draws from.",
    ),
]

# The canonical anagram key: an ezhuthu multiset, order removed. Sorting the
# ezhuthu (not the code points) is what makes it a Tamil anagram rather than a
# byte one - the tiles a player rearranges are ezhuthu.
MultisetKey = tuple[str, ...]


def multiset_key(ezhuthu: Sequence[str]) -> MultisetKey:
    """Return the order-free key two words share exactly when they are anagrams."""
    return tuple(sorted(ezhuthu))


def group_by_multiset(words: Iterable[MasterWord]) -> dict[MultisetKey, list[MasterWord]]:
    """Index words by their ezhuthu multiset - the rows one scramble can spell.

    Built over the SERVED rows of one set, because that is the population a
    Game can say anything true about: telling a player their arrangement is
    another word only helps when the set actually serves that word.
    """
    groups: dict[MultisetKey, list[MasterWord]] = defaultdict(list)
    for row in words:
        groups[multiset_key(row.ezhuthu)].append(row)
    return dict(groups)


def select(
    master: MasterWordlist,
    selection: DerivedSelection,
) -> tuple[list[MasterWord], DerivedCounters]:
    """Apply one Game's selection to the master; return the rows and the ledger.

    Rows stay in master rank order (most common first), which is a total order
    because ``freqRank`` is unique - so the output needs no tie-break to be
    reproducible, and a Game wanting an easier slice can take it off the front.

    Every rejection is counted under exactly one heading, so the counters
    reconcile against the master's row count and a selection bug cannot quietly
    drop words.
    """
    bands = frozenset(selection.bands)
    outside_length = outside_band = invalid_word_final = 0
    kept: list[MasterWord] = []
    for row in master.words:
        if not selection.minLength <= row.length <= selection.maxLength:
            outside_length += 1
            continue
        if row.freqBand not in bands:
            outside_band += 1
            continue
        if selection.requireValidWordFinal and not ends_like_a_word(row.ezhuthu):
            invalid_word_final += 1
            continue
        kept.append(row)

    capped = 0
    if selection.maxWords is not None and len(kept) > selection.maxWords:
        capped = len(kept) - selection.maxWords
        kept = kept[: selection.maxWords]

    counters = DerivedCounters(
        masterRows=len(master.words),
        outsideLength=outside_length,
        outsideBand=outside_band,
        invalidWordFinal=invalid_word_final,
        capped=capped,
        rowsKept=len(kept),
    )
    return kept, counters


def derive(
    master: MasterWordlist,
    source: DerivedSource,
    spec: DerivedSet,
) -> GameWordlist:
    """Cut one Game's wordlist out of the master."""
    kept, counters = select(master, spec.selection)
    # Indexed AFTER the cap, so the recorded fan-out counts rows this set really
    # serves rather than rows the cap threw away.
    fan_out = {key: len(rows) for key, rows in group_by_multiset(kept).items()}
    return GameWordlist(
        version=_SCHEMA_VERSION,
        changelog=_CHANGELOG,
        gameId=spec.gameId,
        source=source,
        selection=spec.selection,
        counters=counters,
        words=[
            GameWord(
                word=row.word,
                ezhuthu=row.ezhuthu,
                freqBand=row.freqBand,
                anagramFanOut=fan_out[multiset_key(row.ezhuthu)],
                hints=GameWordHints(
                    firstEzhuthu=row.ezhuthu[0], length=len(row.ezhuthu)
                ),
            )
            for row in kept
        ],
    )


def describe_source(master: MasterWordlist, master_path: Path, rel_path: str) -> DerivedSource:
    """Pin the exact master a run read: its identity, not the time it was read."""
    digest, _ = sha256_of(master_path)
    return DerivedSource(
        path=rel_path,
        version=master.version,
        generatedAt=master.generatedAt,
        sha256=digest,
        rows=len(master.words),
    )


def render(wordlist: GameWordlist) -> str:
    """Render a derived set deterministically: pretty header, one word per line."""
    return render_document(wordlist.model_dump(mode="json", exclude_none=True), "words")


def load_master(path: Path) -> MasterWordlist:
    """Load and validate the ranked master wordlist."""
    return MasterWordlist.model_validate_json(path.read_text(encoding="utf-8"))


def load_registry(path: Path) -> DerivedWordlists:
    """Load and validate ``config/derived-wordlists.json``."""
    return DerivedWordlists.model_validate_json(path.read_text(encoding="utf-8"))
