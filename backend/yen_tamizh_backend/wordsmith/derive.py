"""Cut each Game's SERVED wordlist out of the published lexicon (rows 9 and 12).

This is the DERIVED layer, and only the derived layer. It reads the artifact the
lexicon pipeline publishes - ``datasets/lexicon/lexicon.meta.json`` plus the
NDJSON partitions that document names - applies the per-Game selection declared
in ``config/derived-wordlists.json``, and writes one ``game-wordlist`` per
registered Game. It generates no puzzles, writes nothing into
``frontend/public/``, and does not know what a day or a bank is - the daily
puzzle engine (Row 13) is a separate process that reads these sets::

    datasets/lexicon/**  ->  published lexicon  ->  per-Game sets  ->  daily puzzles
      (row 11 PUBLISH)         (read here)          (this module)      (Row 13)

PRESENT and SERVED are different populations, and this module is the whole
difference. The lexicon keeps every surface any source ever showed us, class and
facts intact. A player is asked to spell only what passes four gates - the word
CLASS, how many authorities attested it and how many of those were dictionaries,
how often it actually occurs, and whether the game can say what it means. Each
gate has its own counter bucket, so what a gate removed is a number in the
committed file rather than a claim in a commit message.

Adding a Game's set is a DATA change (see docs/how-to/add-a-derived-wordlist.md):
append an entry to ``config/derived-wordlists.json`` and re-run
``python -m yen_tamizh_backend.scripts.rebuild_wordlists``. The gates are config
because they are tunable game-balance numbers (Holy Law #6); this module is the
mechanism that interprets them. Only a Game needing a predicate the knobs cannot
express costs code.

Derived sets are BUILD ARTIFACTS. They are regenerated in full by one command
and never hand edited, and they are a pure function of the lexicon plus the
registry - no wall clock, so the same inputs always produce the same bytes.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Sequence
from pathlib import Path

from yen_tamizh_backend.contracts.base import ChangelogEntry
from yen_tamizh_backend.contracts.common import QUARTILES
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
from yen_tamizh_backend.contracts.lexicon import Lexicon, LexiconEntry
from yen_tamizh_backend.ezhuthu import segment
from yen_tamizh_backend.wordsmith.artifact import render_document, sha256_of

_SCHEMA_VERSION = "2026-08-16T23:30"
_CHANGELOG = [
    ChangelogEntry(
        version=_SCHEMA_VERSION,
        change=(
            "Cut the set from the published lexicon instead of the ranked "
            "master: source became {metaPath, version, sha256, rows} and lost "
            "generatedAt; the ledger became lexiconRows less outsideLength, "
            "outsideClass, belowAttestations, belowFrequency, withoutMeaning "
            "and capped, retiring masterRows, outsideBand and invalidWordFinal; "
            "every row carries frequency and frequencyStratum where it carried "
            "freqBand."
        ),
        why=(
            "Row 12 of the lexicon pipeline - the served set is now gated on "
            "what the lexicon knows about a word rather than on where it ranked "
            "in a scraped corpus. The committed set served a political party "
            "and a sitting politician because nothing it read could tell a "
            "proper noun from a word; the class gate is what removes them, and "
            "a bucket per gate is what makes each gate's cost a number rather "
            "than an assertion. A rank-relative band over a population where "
            "thousands of rows occur zero times was a different filter wearing "
            "the same name, so raw frequency plus an absolute floor replaces "
            "it, and the stratum carries the second difficulty axis because "
            "length alone is anti-correlated at both tails. The word-final rule "
            "goes with them, superseded by the orthotactic signal the "
            "classifier already applies."
        ),
    ),
    ChangelogEntry(
        version="2026-08-14",
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


class DeriveError(ValueError):
    """The derived layer refuses to cut a set, and the message says why."""


def multiset_key(ezhuthu: Sequence[str]) -> MultisetKey:
    """Return the order-free key two words share exactly when they are anagrams."""
    return tuple(sorted(ezhuthu))


def group_by_multiset(words: Iterable[str]) -> dict[MultisetKey, list[str]]:
    """Index words by their ezhuthu multiset - the words one scramble can spell.

    Built over the SERVED rows of one set, because that is the population a
    Game can say anything true about: telling a player their arrangement is
    another word only helps when the set actually serves that word.
    """
    groups: dict[MultisetKey, list[str]] = defaultdict(list)
    for word in words:
        groups[multiset_key(segment(word))].append(word)
    return dict(groups)


def load_meta(path: Path) -> Lexicon:
    """Load and validate the lexicon META document."""
    return Lexicon.model_validate_json(path.read_text(encoding="utf-8"))


def load_registry(path: Path) -> DerivedWordlists:
    """Load and validate ``config/derived-wordlists.json``."""
    return DerivedWordlists.model_validate_json(path.read_text(encoding="utf-8"))


def read_rows(
    meta: Lexicon, repo_root: Path, word_classes: Iterable[str]
) -> Iterator[LexiconEntry]:
    """Stream the published rows of the named classes, in partition-table order.

    Files are resolved from ``meta.partitions`` and never by globbing the
    directory. A glob would serve whatever happens to be on disk, including a
    file the meta document does not vouch for - which is exactly how a class the
    selection never named would reach a player. A class the lexicon does not
    publish is an error rather than an empty result, because a selection that
    silently serves nothing looks identical to one that works.
    """
    wanted = set(word_classes)
    published = {cell.wordClass for cell in meta.partitions}
    missing = sorted(wanted - published)
    if missing:
        raise DeriveError(
            f"the selection serves {', '.join(missing)}, which the lexicon at "
            f"{meta.version} does not publish - the set would be silently empty"
        )
    for cell in meta.partitions:
        if cell.wordClass not in wanted:
            continue
        with (repo_root / cell.path).open(encoding="utf-8") as handle:
            for line in handle:
                yield LexiconEntry.model_validate_json(line)


def select(
    meta: Lexicon,
    rows: Iterable[LexiconEntry],
    selection: DerivedSelection,
) -> tuple[list[LexiconEntry], DerivedCounters]:
    """Apply one Game's serving gates; return the rows and the ledger.

    ``rows`` carries only the classes the selection allows - the caller opens no
    others - so ``outsideClass`` is read off the lexicon's own partition table
    rather than counted line by line. Every other gate counts what it stopped,
    and a row failing more than one is charged to the first that stopped it.

    The kept rows come out most frequent first, with the word as the tie-break so
    the order is total and the bytes are reproducible. That is also the order the
    cap trims from the back of, so a capped set loses its rarest words rather
    than an arbitrary slice.
    """
    served_classes = set(selection.wordClasses)
    outside_class = sum(
        cell.rows for cell in meta.partitions if cell.wordClass not in served_classes
    )
    outside_length = below_attestations = below_frequency = without_meaning = 0
    kept: list[LexiconEntry] = []
    for row in rows:
        if not selection.minLength <= row.length <= selection.maxLength:
            outside_length += 1
            continue
        if (
            row.attestations < selection.minAttestations
            or row.tier1Attestations < selection.minTier1Attestations
        ):
            below_attestations += 1
            continue
        if row.frequency < selection.minFrequency:
            below_frequency += 1
            continue
        if selection.requireMeaning and row.definitionTa is None:
            without_meaning += 1
            continue
        kept.append(row)

    kept.sort(key=lambda row: (-row.frequency, row.word))

    capped = 0
    if selection.maxWords is not None and len(kept) > selection.maxWords:
        capped = len(kept) - selection.maxWords
        kept = kept[: selection.maxWords]

    counters = DerivedCounters(
        lexiconRows=meta.counters.published.rows,
        outsideLength=outside_length,
        outsideClass=outside_class,
        belowAttestations=below_attestations,
        belowFrequency=below_frequency,
        withoutMeaning=without_meaning,
        capped=capped,
        rowsKept=len(kept),
    )
    return kept, counters


def derive(
    meta: Lexicon,
    rows: Iterable[LexiconEntry],
    source: DerivedSource,
    spec: DerivedSet,
) -> GameWordlist:
    """Cut one Game's wordlist out of the published lexicon."""
    kept, counters = select(meta, rows, spec.selection)
    # Both derived signals are counted AFTER the cap, over the rows this set
    # really serves: a partner nobody is served cannot be the word a Game offers
    # back, and a quartile over a population wider than the served set would say
    # nothing about the words a player is actually offered.
    fan_out = Counter(multiset_key(segment(row.word)) for row in kept)
    total = len(kept)
    return GameWordlist(
        version=_SCHEMA_VERSION,
        changelog=_CHANGELOG,
        gameId=spec.gameId,
        source=source,
        selection=spec.selection,
        counters=counters,
        words=[
            _game_word(row, position, total, fan_out)
            for position, row in enumerate(kept)
        ],
    )


def _game_word(
    row: LexiconEntry,
    position: int,
    total: int,
    fan_out: Counter[MultisetKey],
) -> GameWord:
    """One served row: the lexicon's word plus the two signals a Game reads."""
    ezhuthu = segment(row.word)
    return GameWord(
        word=row.word,
        ezhuthu=ezhuthu,
        frequency=row.frequency,
        frequencyStratum=position * QUARTILES // total + 1,
        anagramFanOut=fan_out[multiset_key(ezhuthu)],
        hints=GameWordHints(firstEzhuthu=ezhuthu[0], length=len(ezhuthu)),
    )


def describe_source(meta: Lexicon, meta_path: Path, rel_path: str) -> DerivedSource:
    """Pin the exact lexicon a run read: its identity, not the time it was read."""
    digest, _ = sha256_of(meta_path)
    return DerivedSource(
        metaPath=rel_path,
        version=meta.version,
        sha256=digest,
        rows=meta.counters.published.rows,
    )


def render(wordlist: GameWordlist) -> str:
    """Render a derived set deterministically: pretty header, one word per line."""
    return render_document(wordlist.model_dump(mode="json", exclude_none=True), "words")
