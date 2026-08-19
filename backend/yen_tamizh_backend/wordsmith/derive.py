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

A set may also narrow itself on a DIMENSION - ``categories`` or ``pos`` - which
is how a THEMED set is cut. A dimension is not a gate: it never applies unless a
set asks for it, because barely any published row carries a category and a set
that narrowed on one by accident would collapse to a few hundred rows. It gets
its own bucket for the same reason a gate does.

One exclusion is not derivable from the lexicon at all, and it runs last: the
curated deny-list in ``config/served-denylist.json`` (row 16). The lexicon knows
what a word IS; it cannot know that Tamil's grammar and a newspaper masthead
make bad puzzle answers even though both are attested, frequent, and carry a
dictionary sense. Matching is WHOLE-WORD and exact, and the exclusion is on
SERVING only - every denied word stays in the published lexicon.

Two more exclusions ARE derivable, and they run just before it. A participial
adjective - ``mozhiyaana`` from ``mozhi`` - is an inflected form wearing a
headword's clothes, and the surface says so: it ends in a participial suffix
over a stem long enough to be a word. A row the SOURCE labelled obscene says so
too, in its own first sense. Both are stated in
``config/derived-wordlists.json`` under ``servingRules`` (Holy Law #6) and both
are SERVING decisions on the same terms as the deny-list: the word keeps its
published class and its published facts, and is simply never dealt.

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
    ParticipialSuffix,
    ServingRules,
)
from yen_tamizh_backend.contracts.game_wordlist import (
    DerivedCounters,
    DerivedSource,
    GameWord,
    GameWordHints,
    GameWordlist,
)
from yen_tamizh_backend.contracts.lexicon import Lexicon, LexiconEntry
from yen_tamizh_backend.contracts.served_denylist import ServedDenylist
from yen_tamizh_backend.ezhuthu import segment
from yen_tamizh_backend.wordsmith.artifact import render_document, sha256_of

_SCHEMA_VERSION = "2026-08-19"
_CHANGELOG = [
    ChangelogEntry(
        version=_SCHEMA_VERSION,
        change=(
            "Added the obscene and participial ledger buckets, charged after "
            "every automatic gate and before the deny-list, for the rows the "
            "registry's servingRules refuse."
        ),
        why=(
            "Defect 2 - the board dealt mozhiyaana, migudhiyaana, "
            "urundaiyaana and thavaRillaadha, which are participial adjectives "
            "rather than headwords, and it dealt a surface the source itself "
            "glosses as an obscene word. Neither is reachable from the existing "
            "knobs: the word-hood classifier labels inflection from collected "
            "verb-form lists, and a peyareccham those lists do not contain "
            "arrives with a tier-1 listing and a clean shape, while no column "
            "says a word is coarse - the source writes that into the gloss as a "
            "usage label. Both get their own bucket because the ledger's whole "
            "claim is that every published row is accounted for under exactly "
            "one heading, and they are charged before the deny-list so that "
            "list's number stays the honest measure of what curation ALONE "
            "removed."
        ),
    ),
    ChangelogEntry(
        version="2026-08-17T18:00",
        change=(
            "Every served row now carries definitionTa, translationEn, "
            "synonymsTa and categories from the published lexicon. "
            "definitionTa is the FIRST sense rather than the lexicon's list of "
            "senses."
        ),
        why=(
            "Row 14 of the lexicon pipeline - the hint ladder's dearest rung "
            "is what a word MEANS and the summary shows the same phrase free "
            "once the word is solved, so the meaning columns have to reach the "
            "layer that bakes a puzzle. They are carried raw, not resolved, so "
            "the rule that turns them into one display string lives in the "
            "generator beside the wording rather than frozen into this "
            "artifact. definitionTa keeps only sense zero because the lexicon "
            "orders senses most-authoritative-first and a Game has exactly one "
            "display slot: the other senses have no reader and cost 4.89 MB "
            "across the served set. synonymsTa travels whole instead, because "
            "it is not a ranked list - every member is an equally correct "
            "answer - and the generator reads down it to step over a synonym "
            "that would spell the answer out."
        ),
    ),
    ChangelogEntry(
        version="2026-08-17T12:00",
        change=(
            "Added the denylisted ledger bucket, charged after every automatic "
            "gate and before the cap, for the words config/served-denylist.json "
            "names."
        ),
        why=(
            "Row 16 - the served set opened with Tamil's grammar and with the "
            "personal names and mastheads a news corpus makes frequent, and "
            "because frequency is a difficulty axis they landed in the EASY "
            "band, which is the band a player meets most. No lexicon column "
            "separates them: pos is a union across 21 sources, so a "
            "part-of-speech rule would have deleted appa and arasu with them. "
            "The exclusion is therefore a named list, and it needs its own "
            "bucket because the ledger's whole claim is that every published "
            "row is accounted for under exactly one heading. It is charged "
            "last so its number is what the deny-list ALONE removed rather "
            "than what some other gate would have removed anyway."
        ),
    ),
    ChangelogEntry(
        version="2026-08-17",
        change=(
            "Added the categories and pos SELECTION dimensions to the selection, "
            "each keeping the rows whose own set-valued column intersects the "
            "one named, and gave each its own ledger bucket - outsideCategories "
            "and outsidePos - charged before the four serving gates."
        ),
        why=(
            "Row 15 of the lexicon pipeline - a themed round is the Daily's "
            "variety mechanism, and it costs no new engine because a theme is "
            "just a derived set cut on a dimension the lexicon already carries. "
            "Neither dimension may ever gate admission for an ordinary set - "
            "under 3,000 published headwords carry a category at all - so both "
            "are optional and absent means not applied. They get their own "
            "buckets because the ledger's whole claim is that every published "
            "row is accounted for under exactly one heading, and burying a "
            "theme's reach inside an existing gate would make that gate's "
            "number a lie."
        ),
    ),
    ChangelogEntry(
        version="2026-08-16T23:30",
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


def load_denylist(path: Path) -> ServedDenylist:
    """Load and validate ``config/served-denylist.json``."""
    return ServedDenylist.model_validate_json(path.read_text(encoding="utf-8"))


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


def ends_in_participial_suffix(
    ezhuthu: Sequence[str], suffixes: Iterable[ParticipialSuffix]
) -> bool:
    """True when a surface is a participial adjective built on a real stem.

    The test is the SHAPE of the ending, not a lookup of the stem. Requiring the
    stem to be an attested headword was measured over the committed set and
    rejected: Tamil's sandhi rewrites the stem's last ezhuthu when the suffix
    lands - ``azhagu`` becomes ``azhagaana``, ``mozhi`` takes a glide - so
    undoing it means guessing which of several spellings the writer started
    from, and every guess that misses keeps a participle on the board. It left
    186 of 1,063 matches there, ``mozhiyaana`` and ``thavaRillaadha`` among
    them, and those are two of the four surfaces this rule exists to remove.

    What the ending alone catches is far cleaner than a suffix rule usually is,
    and the reason is structural: a participial suffix is a statement about
    Tamil MORPHOLOGY, where a name suffix is a statement about a referent. The
    linking vowel plus ``minStemEzhuthu`` is what keeps it honest - it is the
    difference between ``mozhiyaana`` and ``vaan`` (sky).
    """
    for suffix in suffixes:
        span = len(suffix.tail) + 1
        if len(ezhuthu) < span + suffix.minStemEzhuthu:
            continue
        if list(ezhuthu[-len(suffix.tail) :]) != suffix.tail:
            continue
        link = ezhuthu[-span]
        # A one-code-point ezhuthu is a bare uyir or mei and carries no matra,
        # so it can never be the consonant-plus-vowel a suffix links through.
        if len(link) > 1 and link[1:] == suffix.linkVowel:
            return True
    return False


def is_marked_obscene(senses: Sequence[str] | None, markers: Iterable[str]) -> bool:
    """True when the row's FIRST sense carries a lexicographic obscenity label.

    Sense zero only. The lexicon orders senses most-authoritative-first and it is
    the sense a Game displays, so a label there is the source labelling the WORD.
    Reading every sense was measured and rejected: it turns ``vanmai``
    (harshness) and ``theettu`` into obscenities because a later sense of each
    DISCUSSES coarse speech, which is the same failure a bare ``aabaasa``
    substring makes on ``aruvaruppu`` (disgust).
    """
    if not senses:
        return False
    return any(marker in senses[0] for marker in markers)


def select(
    meta: Lexicon,
    rows: Iterable[LexiconEntry],
    selection: DerivedSelection,
    denied: frozenset[str],
    rules: ServingRules,
) -> tuple[list[LexiconEntry], DerivedCounters]:
    """Apply one Game's selection dimensions and serving gates; return the ledger.

    ``rows`` carries only the classes the selection allows - the caller opens no
    others - so ``outsideClass`` is read off the lexicon's own partition table
    rather than counted line by line. Every other bucket counts what it stopped,
    and a row failing more than one is charged to the first that stopped it.

    The two DIMENSIONS - ``categories`` and ``pos`` - are read before the gates.
    Each keeps the rows whose own set-valued column intersects the one named, and
    a row carrying neither column can never intersect one, so a set that names a
    dimension serves only rows the lexicon actually tagged. Reading them first is
    what makes a themed ledger legible: it says how far the theme reaches, and
    then what each gate removed from inside it.

    ``rules`` runs after every gate and before the deny-list. The obscenity
    label is read first of the two because it is the graver refusal, and both
    are read before ``denied`` so the curated list is charged only for what
    nothing derivable caught.

    ``denied`` is read LAST, and the match is WHOLE-WORD: a denied surface must
    not take its inflections with it, and a stem match over an agglutinative
    language would take dozens of real words per entry. Running it after the
    automatic gates is what makes its bucket the honest measure of the list -
    the words it ALONE keeps off the board, rather than the ones some gate
    would have stopped anyway.

    The kept rows come out most frequent first, with the word as the tie-break so
    the order is total and the bytes are reproducible. That is also the order the
    cap trims from the back of, so a capped set loses its rarest words rather
    than an arbitrary slice.
    """
    served_classes = set(selection.wordClasses)
    outside_class = sum(
        cell.rows for cell in meta.partitions if cell.wordClass not in served_classes
    )
    wanted_categories = set(selection.categories or ())
    wanted_pos = set(selection.pos or ())
    outside_categories = outside_pos = 0
    outside_length = below_attestations = below_frequency = without_meaning = 0
    obscene = participial = denylisted = 0
    kept: list[LexiconEntry] = []
    for row in rows:
        if wanted_categories and not wanted_categories.intersection(row.categories or ()):
            outside_categories += 1
            continue
        if wanted_pos and not wanted_pos.intersection(row.pos or ()):
            outside_pos += 1
            continue
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
        if is_marked_obscene(row.definitionTa, rules.obscenityMarkers):
            obscene += 1
            continue
        if ends_in_participial_suffix(segment(row.word), rules.participialSuffixes):
            participial += 1
            continue
        if row.word in denied:
            denylisted += 1
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
        outsideCategories=outside_categories,
        outsidePos=outside_pos,
        belowAttestations=below_attestations,
        belowFrequency=below_frequency,
        withoutMeaning=without_meaning,
        obscene=obscene,
        participial=participial,
        denylisted=denylisted,
        capped=capped,
        rowsKept=len(kept),
    )
    return kept, counters


def derive(
    meta: Lexicon,
    rows: Iterable[LexiconEntry],
    source: DerivedSource,
    spec: DerivedSet,
    denied: frozenset[str],
    rules: ServingRules,
) -> GameWordlist:
    """Cut one Game's wordlist out of the published lexicon.

    ``denied`` and ``rules`` are required rather than defaulted: an empty
    deny-list and a forgotten one produce identical output, and the one this
    layer exists to prevent is the forgotten one.
    """
    kept, counters = select(meta, rows, spec.selection, denied, rules)
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
    """One served row: the lexicon's word, what it means, and the two signals."""
    ezhuthu = segment(row.word)
    return GameWord(
        word=row.word,
        ezhuthu=ezhuthu,
        frequency=row.frequency,
        frequencyStratum=position * QUARTILES // total + 1,
        anagramFanOut=fan_out[multiset_key(ezhuthu)],
        # Sense zero, not the list: the lexicon orders senses most-authoritative
        # first and a Game has one display slot, so the rest have no reader here.
        definitionTa=None if row.definitionTa is None else row.definitionTa[0],
        translationEn=row.translationEn,
        synonymsTa=row.synonymsTa,
        categories=row.categories,
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
