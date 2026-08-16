"""The word-hood CLASSIFIER (Row 9) - eight signals in, one ``wordClass`` out.

Rows 7 and 8 measured the evidence. This module reaches the verdict, and it is
the last thing that runs inside ENRICH's rebuild transaction. What each signal
MEANS, and why a classification rather than a filter, is
``docs/architecture/lexicon/word-hood.md``; what a ``wordClass`` IS is
``docs/concepts/lexicon.md``. This module is the cascade and how it is applied
to six and a quarter million surfaces.

THE VERDICT IS A CASCADE, NOT A SCORE. Nine classes are not nine points on a
line - a proper noun and an inflected form are both non-headwords for entirely
unrelated reasons - so there is nothing for a weighted sum to be a sum OF. An
ordered cascade also has the property a score does not: every verdict can be
traced to the ONE rule that produced it, which is what makes a misclassification
a reviewable diff rather than a tuning session.

Four phases, in this order, and the order is the design:

0. **Is this a word at all?** A precondition, weighed before every signal and
   before every source assertion. A statement about the STRING outranks a
   statement about the word it is not: a scraped paragraph tagged as a name is
   still a scraped paragraph. ``notAWord`` is a CONFIDENT NEGATIVE and is
   deliberately a different verdict from ``unclassified``, which is an ABSENT
   one.
1. **What a source SAID.** ``wordClassEvidence`` facts are assertions, not
   inferences, and Row 3 built the alias map so a source tag that names no part
   of speech lands here instead of being thrown away. Inferring what is already
   asserted would be strictly worse evidence.
2. **The headword gate**, which must be EARNED. It is the only class Row 12
   serves, so it is the only class with a conjunction of requirements rather
   than a single test.
3. **The reasons a surface is NOT a headword**, strongest evidence first.
4. **The residue**, where the honest answer is that nobody can tell yet.

TWO INPUTS BEYOND THE EIGHT SIGNALS, both free and both required by the row:

- the surface's SHAPE, recomputed from ``ezhuthu/word_shape.py``. The stored
  ``orthotactic`` column is a single number and three different defects are
  collapsed into it; the classifier needs them apart, because a surface that
  ends wrong is a sandhi artifact and one that opens wrong is a borrowing. Row 7
  separated those facts on ``WordShape`` for exactly this reader, and exposed
  ``hasGrantha`` rather than persisting a ninth signal column for the same
  reason. The score is still read, where a single number is what the question
  wants;
- whether the surface has an ENTRY rather than a bare listing. See
  ``prepare_entry``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final, get_args

from yen_tamizh_backend.contracts.lexicon import WordClass
from yen_tamizh_backend.contracts.lexicon_sources import (
    ATTESTING_ROLES,
    LexiconSources,
    WordClassEvidence,
)
from yen_tamizh_backend.contracts.wordhood import Wordhood
from yen_tamizh_backend.ezhuthu import analyse
from yen_tamizh_backend.ezhuthu.word_shape import WordShape
from yen_tamizh_backend.wordsmith.signals_exact import SignalContext
from yen_tamizh_backend.wordsmith.store import quoted

_ENTRY_TABLE: Final = "tmp_entry"
# The temp table the evidence collector fills. Exported so a test can read the
# collector's own output rather than a second copy of its query.
EVIDENCE_TABLE: Final = "tmp_evidence"

CLASSIFY_UDF: Final = "word_class"

# How a word's evidence values are joined in the one column the pass carries
# them in. A separator that cannot occur inside a value, because every value is
# a member of a closed Literal.
EVIDENCE_SEPARATOR: Final = ","

# The one evidence value that is a DENIAL rather than a description, named once
# because both the SQL that collects it and the cascade that weighs it have to
# mean the same string.
NOT_A_WORD: Final[WordClassEvidence] = "notAWord"

# The nine verdicts and the seven a source may assert, taken from the contracts
# rather than restated. A second copy of a closed vocabulary is a second place
# for it to be wrong.
WORD_CLASSES: Final[tuple[WordClass, ...]] = get_args(WordClass)
_EVIDENCE_BY_NAME: Final[dict[str, WordClassEvidence]] = {
    value: value for value in get_args(WordClassEvidence)
}

# The order the signal columns reach the classification function in. One
# statement of it, so the SELECT below and the function that reads its arguments
# cannot drift apart.
SIGNAL_ARGUMENTS: Final[tuple[str, ...]] = (
    "attested",
    "orthotactic",
    "breadth",
    "nannulValid",
    "knownVerbForm",
    "ngram",
    "neighbour",
    "zipf",
)


@dataclass(frozen=True, slots=True)
class Surface:
    """Everything the classifier is allowed to see about one surface.

    The eight signals as Rows 7 and 8 measured them, plus the two facts read
    from the staged zone. Two of the signals are optional and the ``None`` is
    load-bearing rather than a convenience: ``neighbour`` is ``None`` for a
    surface Row 8's prune never queried, and ``zipf`` for a surface no source
    ever counted. Reading either as a zero would turn "nobody asked" into
    "we looked and found nothing".

    This is deliberately a plain value, so the cascade can be run over one
    committed fixture row with no store, no connection and no fixture-only code
    path. The Oracle depends on that: a classifier that could only be exercised
    against a 1.8 GB store could not be regression-tested in CI at all.
    """

    word: str
    attested: float
    orthotactic: float
    breadth: float
    nannulValid: float
    knownVerbForm: float
    ngram: float
    neighbour: float | None
    zipf: float | None
    entry: bool
    evidence: tuple[WordClassEvidence, ...]


def asserted(surface: Surface, config: Wordhood) -> WordClassEvidence | None:
    """The evidence class a source asserted, or ``None`` when none did.

    When two sources assert different classes the configured priority decides,
    and it is validated to rank every value exactly once - so this can never
    depend on the order the facts came back in.
    """
    if not surface.evidence:
        return None
    priority = config.classifier.evidencePriority
    return min(surface.evidence, key=priority.index)


def not_a_word_reason(shape: WordShape, config: Wordhood) -> str | None:
    """Which precondition the STRING fails, or ``None`` when it fails none.

    One implementation of the rule, read two ways: the cascade only needs to
    know THAT a surface failed, and the review dump needs to know WHICH clause
    it failed on. Deriving the reason a second time somewhere else would let the
    published verdict and the reviewed reason disagree.

    Three rejections, each a threshold in config, and each with a real producer
    measured over the store: a unit that is not an ezhuthu at all, a length no
    Tamil word reaches, and one character repeated.
    """
    settings = config.classifier.notAWord
    units = shape.ezhuthu
    if not units:
        return "empty"
    if settings.rejectNonTamil and shape.hasNonTamil:
        return "nonTamil"
    if len(units) > settings.maxEzhuthu:
        return "tooLong"
    # Only a surface of more than one ezhuthu can fail this: a one-ezhuthu word
    # holds exactly one distinct ezhuthu and is an ordinary Tamil word.
    if len(units) > 1 and len(set(units)) < settings.minDistinctEzhuthu:
        return "repeatedEzhuthu"
    return None


def is_not_a_word(shape: WordShape, config: Wordhood) -> bool:
    """Whether the STRING disqualifies itself before any evidence is read.

    This is a CONFIDENT NEGATIVE, which is why it does not go to
    ``unclassified``. That class is the enrichment queue - an absent verdict a
    later pass may fill - and a queue holding 642,000 strings no amount of
    enrichment can fix is a queue nobody can size.
    """
    return not_a_word_reason(shape, config) is not None


def classify_surface(surface: Surface, config: Wordhood) -> WordClass:
    """Reach exactly one verdict about one surface.

    Pure: the same surface and the same knobs give the same class, on any
    machine, in any process, in any order. That is what lets ENRICH run it as a
    deterministic SQLite function inside one streamed statement and lets the
    test run it over a committed fixture.

    ``zipf`` IS DELIBERATELY NEVER CONSULTED. It is a frequency residual, and
    the founding observation of this whole layer is that frequency and word-hood
    are independent axes - a rule keyed on it would re-import the exact defect
    the lexicon exists to remove. It stays on ``Surface`` because it is one of
    the eight and a reader comparing the record to the store should find it
    there; a test asserts that no value of it can change a verdict.
    """
    settings = config.classifier
    shape = analyse(surface.word)

    # ---- 0. is this a word at all? --------------------------------------
    if is_not_a_word(shape, config):
        return "notAWord"

    # ---- 1. what a source SAID ------------------------------------------
    # Including a source saying the unit is NOT a word. That denial is ranked
    # first in `evidencePriority`, so it outranks every other assertion and
    # vetoes the headword gate below - which is the point: another authority
    # merely LISTING the same single letter is not an answer to the dictionary
    # that looked at it and called it a character.
    said = asserted(surface, config)
    if said is not None:
        return said

    # ---- 2. the headword gate, earned rather than defaulted -------------
    # Every clause is doing work over the real store: the ENTRY test is what
    # keeps the three bare wordlists from ruling on word-hood, the shape tests
    # are what keep a borrowing or a scrape artifact out, and the score is the
    # one number a future weight could move.
    if (
        surface.entry
        and not shape.hasNonTamil
        and not shape.hasGrantha
        and shape.initialLegal
        and shape.finalLegal
        and shape.clustersLegal
        and surface.orthotactic >= settings.headwordMinOrthotactic
    ):
        return "headword"

    # ---- 3. why it is not a headword, strongest evidence first ----------
    if surface.knownVerbForm > 0:
        # Direct evidence beats every inference below it: these are collected,
        # labelled forms, and a source whose role is formEvidence is telling us
        # the one thing it is allowed to tell us.
        return "inflected"
    if shape.hasNonTamil:
        # Reachable only when `notAWord.rejectNonTamil` is off. With it on, a
        # surface carrying a Latin letter, a digit or a space never gets this
        # far - it is not badly-shaped Tamil, it is not Tamil. Left standing so
        # the knob genuinely selects between two behaviours rather than
        # switching one off.
        return "suspectedTypo"
    if shape.hasGrantha:
        # The five grantha consonants were borrowed to write sounds Tamil does
        # not have, so carrying one is evidence about the word's ORIGIN. That is
        # a different question from whether its SHAPE is legal, which is why
        # `granthaPenalty` prices it at zero inside the score and the classifier
        # still reads the fact here.
        return "loanword"
    if not shape.finalLegal:
        # The sandhi signature. A Tamil word ends on a vowel-bearing ezhuthu or
        # one of eight mei; a surface ending on any other mei is carrying the
        # euphonic doubling that belonged to the NEXT word.
        return "sandhiArtifact"
    if not shape.initialLegal or not shape.clustersLegal:
        # An opening no native word takes, or a cluster Tamil does not build.
        # Row 7 reconciled this table against every multi-attested headword and
        # found the rejections were Sanskrit clusters, English transliterations
        # and compounds scraped without their space - borrowings, all of them.
        return "loanword"

    # ---- 4. the residue -------------------------------------------------
    if is_discovery(surface, config):
        # Clean, corroborated, well-formed and unattested. That is a modern word
        # the acquired dictionaries are too old or too thin to hold, and it goes
        # to the enrichment queue - never to a discard, and never labelled a
        # misspelling on the way.
        return "unclassified"
    if (
        surface.attested == 0
        and surface.nannulValid == 0
        and surface.ngram < settings.typo.maxNgram
        and surface.neighbour is not None
        and surface.neighbour >= settings.typo.minNeighbour
    ):
        # An improbable sequence with a real word one ezhuthu away, that no
        # authority lists and no spellchecker passed. All four clauses earn
        # their place: without the n-gram ceiling this accuses ordinary Tamil,
        # because an agglutinative language generates real forms one ezhuthu
        # apart by the thousand. NULL is excluded before the comparison, so a
        # surface the prune never asked about is never accused on evidence
        # nobody gathered.
        return "suspectedTypo"
    return "unclassified"


def is_discovery(surface: Surface, config: Wordhood) -> bool:
    """Whether this is the high-value case: a real word the dictionaries missed.

    Reported as its own count because it is the size of what the enrichment pass
    stands to gain, and because it is the profile that must never be mistaken
    for junk. Row 8's prune happens to skip most of these already - it does not
    query a surface several sources agree on - but relying on that would make
    this guarantee a side effect of a performance knob.
    """
    discovery = config.classifier.discovery
    return (
        surface.attested == 0
        and surface.orthotactic >= discovery.minOrthotactic
        and surface.breadth >= discovery.minBreadth
        and surface.ngram >= discovery.minNgram
    )


# --------------------------------------------------------------------------
# Applying the cascade to the whole store
# --------------------------------------------------------------------------


def tier_one_sources(registry: LexiconSources) -> tuple[str, ...]:
    """The registered sources whose unit is a lexicographic ENTRY.

    Read off the registry rather than the store, so re-ruling a source's tier
    is a config edit and a ``--classify`` re-run - never a re-stage of the
    source's bytes. The tier is a JUDGEMENT the derived zone applies to
    evidence, not part of the evidence.
    """
    return tuple(
        source.id
        for source in registry.sources
        if source.enabled
        and source.role in ATTESTING_ROLES
        and source.attestationTier == "lexicographic"
    )


def prepare_entry(ctx: SignalContext) -> None:
    """Collect the surfaces a TIER-1 authority gave an ENTRY, not a listing.

    ``docs/concepts/lexicon.md`` defines an attestation as "this authority lists
    this as an ENTRY", and over the real inventory those are two different
    events. Eight sources may assert word-hood; four of them are bare word LISTS
    that emit a headword fact and nothing else, and between them they attest a
    political party, a sitting politician, a bound stem that is not a word, and
    a great many case-marked nouns. Attestation alone would rule every one of
    them a headword.

    So an entry is a headword fact from a source whose declared
    ``attestationTier`` is ``lexicographic`` - a meaning-bearing source
    asserting a headword - and it does NOT depend on whether that source also
    described THIS row.

    Row 9 asked the question per ROW, requiring a describing fact from the same
    source as the headword fact. That was wrong in a way only the measurement
    showed: the largest curated dictionary's part-of-speech column was a blanket
    ``nouns`` stamp on 99.81 percent of its rows, correctly rejected at EXTRACT,
    so it supplied no describing fact at all and 82.6 percent of its 104,073
    headwords were demoted to ``unclassified``. What a source's unit IS cannot
    be recovered from one row of it, and asking per row punished a real
    dictionary for one unusable COLUMN.
    """
    conn = ctx.conn
    sources = tier_one_sources(ctx.registry)
    if not sources:
        # A store with no lexicographic authority would classify zero headwords
        # in silence, which reads exactly like a corpus with no real words in
        # it. The same reason ENRICH checks its configured source ids.
        raise ValueError(
            "no enabled source declares attestationTier 'lexicographic', so no "
            "surface could ever be an entry - check config/lexicon-sources.json"
        )
    name = quoted(_ENTRY_TABLE)
    placeholders = ",".join("?" for _ in sources)
    conn.execute(f"DROP TABLE IF EXISTS {name}")
    conn.execute(f"CREATE TEMP TABLE {name} (word TEXT PRIMARY KEY) WITHOUT ROWID")
    conn.execute(
        f"INSERT OR IGNORE INTO {name} (word) "
        f"SELECT word FROM fact "
        f"WHERE attr = 'headword' AND source_id IN ({placeholders})",
        sources,
    )


def prepare_evidence(ctx: SignalContext) -> None:
    """Collect every ``wordClassEvidence`` a source asserted, one row per word.

    The values are joined into one cell because the classification pass reads
    them through a single function argument. Their ORDER inside that cell is
    whatever SQLite produced and is deliberately not relied on - the cascade
    resolves them by the configured priority, so the verdict is a function of
    the SET.

    One value is filtered rather than collected as written, and the word ONLY
    in Row 9b's ruling is what it implements. ``notAWord`` reaches the store
    when a source's part-of-speech tag routes to ``reject: notAWord`` - a
    lexicographer saying the unit is a script character or a symbol. That is a
    DENIAL of word-hood, and it stands only when it is everything that source
    said about the surface: the Wiktionary extract files the vowel AA as both a
    character and a noun, in two separate rows, and the noun has to win. So a
    ``notAWord`` row is dropped when the SAME source also asserted a part of
    speech for the SAME word. Asking per source is what makes that possible -
    one source's denial is not answered by another source's bare listing, which
    is exactly the case the veto exists for.
    """
    conn = ctx.conn
    name = quoted(EVIDENCE_TABLE)
    conn.execute(f"DROP TABLE IF EXISTS {name}")
    conn.execute(
        f"CREATE TEMP TABLE {name} "
        f"(word TEXT PRIMARY KEY, evidence TEXT NOT NULL) WITHOUT ROWID"
    )
    conn.execute(
        f"INSERT INTO {name} (word, evidence) "
        f"SELECT word, group_concat(DISTINCT value) FROM fact AS said "
        f"WHERE attr = 'wordClassEvidence' AND ("
        f"  value <> '{NOT_A_WORD}' OR NOT EXISTS ("
        f"    SELECT 1 FROM fact AS described "
        f"    WHERE described.word = said.word "
        f"      AND described.source_id = said.source_id "
        f"      AND described.attr = 'pos'"
        f"  )"
        f") GROUP BY word"
    )


def parse_evidence(cell: str | None) -> tuple[WordClassEvidence, ...]:
    """Read one evidence cell back into its values, refusing anything else.

    Fail fast at the boundary: a value that is not in the closed vocabulary means
    the staged zone holds something the contract forbids, and silently dropping
    it would classify on evidence nobody can see.
    """
    if not cell:
        return ()
    values: list[WordClassEvidence] = []
    for raw in cell.split(EVIDENCE_SEPARATOR):
        value = _EVIDENCE_BY_NAME.get(raw)
        if value is None:
            raise ValueError(f"{raw!r} is not a wordClassEvidence value")
        values.append(value)
    return tuple(values)


def register(ctx: SignalContext) -> None:
    """Register the cascade as a deterministic SQLite function.

    Deterministic because it is: the class is a pure function of the surface,
    its signals, its evidence and the knobs the run was given.
    """
    config = ctx.config

    def verdict(
        word: str,
        attested: float,
        orthotactic: float,
        breadth: float,
        nannulValid: float,
        knownVerbForm: float,
        ngram: float,
        neighbour: float | None,
        zipf: float | None,
        entry: int,
        evidence: str | None,
    ) -> str:
        return classify_surface(
            Surface(
                word=word,
                attested=attested,
                orthotactic=orthotactic,
                breadth=breadth,
                nannulValid=nannulValid,
                knownVerbForm=knownVerbForm,
                ngram=ngram,
                neighbour=neighbour,
                zipf=zipf,
                entry=bool(entry),
                evidence=parse_evidence(evidence),
            ),
            config,
        )

    ctx.conn.create_function(CLASSIFY_UDF, 11, verdict, deterministic=True)


def prepare(ctx: SignalContext) -> None:
    """Everything the classification pass needs, before it opens a statement."""
    prepare_entry(ctx)
    prepare_evidence(ctx)
    register(ctx)


def classify_population(ctx: SignalContext) -> int:
    """Write one ``wordClass`` for every row in the derived zone's ``signal``.

    One streamed statement over the signal table, joined to the two small keyed
    temp tables, exactly as the signals themselves are computed. Nothing
    materialises the population in Python; the classifier is called once per row
    by SQLite and its answer goes straight into ``classification``.

    Runs inside the caller's transaction. A row in ``signal`` with no row in
    ``classification`` is a state ENRICH must never commit, because Row 12
    selects on a class and a missing one reads as "not served" rather than as
    the failure it is.
    """
    conn = ctx.conn
    arguments = ", ".join(f's.{quoted(name)}' for name in SIGNAL_ARGUMENTS)
    cursor = conn.execute(
        f"INSERT INTO classification (word, wordClass) "
        f"SELECT s.word, {CLASSIFY_UDF}(s.word, {arguments}, "
        f"CASE WHEN t.word IS NULL THEN 0 ELSE 1 END, e.evidence) "
        f"FROM signal s "
        f"LEFT JOIN {quoted(_ENTRY_TABLE)} t ON t.word = s.word "
        f"LEFT JOIN {quoted(EVIDENCE_TABLE)} e ON e.word = s.word"
    )
    return int(cursor.rowcount)


def distribution(conn: sqlite3.Connection) -> dict[str, int]:
    """How many surfaces landed in each class - the run's headline measurement.

    Every class is reported, including the ones nothing reached, because a class
    that suddenly holds zero rows is the interesting event and a dict that
    simply omits it hides exactly that.
    """
    counted = {
        str(row[0]): int(row[1])
        for row in conn.execute(
            "SELECT wordClass, count(*) FROM classification GROUP BY wordClass"
        )
    }
    unknown = sorted(set(counted) - set(WORD_CLASSES))
    if unknown:
        raise ValueError(f"the store holds classes no contract names: {unknown}")
    return {name: counted.get(name, 0) for name in WORD_CLASSES}


def discoveries(conn: sqlite3.Connection, config: Wordhood) -> int:
    """How many surfaces hit the discovery profile - the enrichment queue's prize."""
    discovery = config.classifier.discovery
    row = conn.execute(
        'SELECT count(*) FROM signal WHERE "attested" = 0 '
        'AND "orthotactic" >= ? AND "breadth" >= ? AND "ngram" >= ?',
        (discovery.minOrthotactic, discovery.minBreadth, discovery.minNgram),
    ).fetchone()
    if row is None:
        raise ValueError("counting the discovery profile returned no row")
    return int(row[0])


def tally(classes: Iterable[WordClass]) -> dict[str, int]:
    """Bucket an iterable of verdicts, with a bucket for every class."""
    counts: dict[str, int] = dict.fromkeys(WORD_CLASSES, 0)
    for name in classes:
        counts[name] += 1
    return counts
