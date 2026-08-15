"""The five EXACT word-hood signals (Row 7) - the ones that are lookups.

Three of the eight signals need a model or a search and land in Row 8. These
five need only a table or a store query, which is what makes them a row of their
own: a linguistic table, a statistical model, an all-pairs search and a
classifier have four different risk profiles.

| Signal | What it asks | What it catches |
| --- | --- | --- |
| ``attested`` | does an authority list this as a headword? | the dictionary verdict |
| ``orthotactic`` | is this a shape Tamil builds? | sandhi artifacts, loanwords, fragments |
| ``breadth`` | how many sources saw it? | a typo appears in one source, a word in many |
| ``nannulValid`` | did a Nannul-rules spellchecker pass it? | a grammar judgement already in hand |
| ``knownVerbForm`` | is it a collected inflected verb form? | inflection by evidence, not by inference |

What each one MEANS to the classifier is
``docs/architecture/lexicon/word-hood.md``. What each one is WORTH is
``config/wordhood.json``. This module is only how each is computed.

Every signal is a SQL EXPRESSION plus the preparation it needs, never a Python
loop over the population. There are 6.25M staged surfaces; materialising them to
score one at a time would trade away the streaming property every stage before
this one paid for. The preparation builds a small keyed temp table, so the
expression is a primary-key probe rather than a correlated scan; the one signal
that cannot be expressed in SQL at all, ``orthotactic``, is a deterministic
user-defined function over the same single pass.

Row 8 appends three more signals to the runner's tuple. Two of them fit this
shape unchanged; the third needed one field on ``Signal`` and one on
``SignalContext``, and nothing else here moved.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Final

from yen_tamizh_backend.contracts.lexicon import SignalName
from yen_tamizh_backend.contracts.lexicon_sources import ATTESTING_ROLES, LexiconSources
from yen_tamizh_backend.contracts.wordhood import OrthotacticWeights, Wordhood
from yen_tamizh_backend.ezhuthu import analyse
from yen_tamizh_backend.wordsmith.store import quoted

_ATTESTED_TABLE: Final = "tmp_attested"
_BREADTH_TABLE: Final = "tmp_breadth"
_NANNUL_TABLE: Final = "tmp_nannul"
_VERB_FORM_TABLE: Final = "tmp_verb_form"

ORTHOTACTIC_UDF: Final = "orthotactic_score"

# What "an authority listed this as a headword" IS, as one query, because Row 8
# consults the same set to train its n-gram model and to build its dictionary of
# real words. Two statements of it would be two places for it to drift. Bind
# ``ATTESTING_ROLES`` as the parameters.
ATTESTED_WORDS_SQL: Final = (
    "SELECT f.word FROM fact f JOIN source s ON s.id = f.source_id "
    f"WHERE f.attr = 'headword' AND s.role IN ({','.join('?' for _ in ATTESTING_ROLES)})"
)

# What a signal's ``expression`` is when the column is not written by the one
# pass over the population at all. Row 8's ``neighbour`` prunes its query set on
# values that pass has only just computed, so it runs after it - and a row the
# prune skipped keeps the NULL this leaves behind, which is exactly the fact:
# not measured, as against measured and found nothing.
NOT_MEASURED: Final = "NULL"


@dataclass(frozen=True, slots=True)
class SignalContext:
    """What a signal's preparation is allowed to see: the store and the knobs.

    ``registry`` is the source registry the staged zone was built from. The
    derived zone is a function of the staged EVIDENCE and of the JUDGEMENTS the
    registry records about the sources that supplied it - which source may
    assert word-hood, and whether its unit is a lexicographic entry or a bare
    listing. Passed in rather than read back off the store on purpose: re-ruling
    a source must cost a re-classify, never a re-stage of its bytes.

    ``workers`` is how many processes the one signal with a search of its own
    may score across. It is a property of the machine rather than a tunable
    judgement, so it arrives as an argument and not from config - the same line
    the store draws around its bulk-load pragmas.

    ``state`` is where a preparation leaves what its own second pass will need,
    and it belongs to ONE run: two ENRICH calls in one process each get their
    own, so neither can read a model the other fitted.
    """

    conn: sqlite3.Connection
    registry: LexiconSources
    config: Wordhood
    workers: int = 1
    state: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Signal:
    """One word-hood signal.

    ``name`` is both the signal and its column in the store's ``signal`` table -
    one name, so a signal cannot be written into the wrong column.
    ``expression`` is SQL with a single ``{word}`` placeholder, which the runner
    fills with whichever surface expression its pass has: the population alias
    on a full rebuild, the row's own column on a single-signal recompute.

    ``second_pass`` is for the signal that cannot be one expression over the
    population, because its query set is decided by values that same pass is
    still computing. Such a signal declares ``NOT_MEASURED`` as its expression
    and fills its column afterwards, inside the same transaction.
    """

    name: SignalName
    expression: str
    prepare: Callable[[SignalContext], None]
    second_pass: Callable[[SignalContext], int] | None = None


def orthotactic_score(word: str, weights: OrthotacticWeights) -> float:
    """How well ``word`` obeys Tamil's own rules about word shape, in [0, 1].

    A surface holding anything that is not an ezhuthu - Latin, a digit, a space,
    punctuation - scores zero outright rather than by accumulated weights. It is
    not badly-shaped Tamil; it is not Tamil, and no weighting of the three
    letter rules should be able to argue otherwise.
    """
    shape = analyse(word)
    if shape.hasNonTamil:
        return 0.0
    penalty = 0.0
    if not shape.initialLegal:
        penalty += weights.initialWeight
    if not shape.finalLegal:
        penalty += weights.finalWeight
    if not shape.clustersLegal:
        penalty += weights.clusterWeight
    if shape.hasGrantha:
        penalty += weights.granthaPenalty
    return max(0.0, 1.0 - penalty)


def _membership_table(ctx: SignalContext, table: str, sources: Sequence[str]) -> None:
    """Collect every surface the named sources know, keyed for probing.

    Both emissions count. A source is registered as a word LIST, and whether its
    extractor happened to emit an observation, a fact, or both is a detail of
    its shape - the two verb-form sources emit observations only, the
    spellchecker emits both - so a membership signal that read one table would
    silently answer zero for the other kind.
    """
    conn = ctx.conn
    name = quoted(table)
    placeholders = ",".join("?" for _ in sources)
    values = tuple(sources)
    conn.execute(f"DROP TABLE IF EXISTS {name}")
    conn.execute(f"CREATE TEMP TABLE {name} (word TEXT PRIMARY KEY) WITHOUT ROWID")
    conn.execute(
        f"INSERT OR IGNORE INTO {name} (word) "
        f"SELECT surface FROM observation WHERE source_id IN ({placeholders})",
        values,
    )
    conn.execute(
        f"INSERT OR IGNORE INTO {name} (word) "
        f"SELECT word FROM fact WHERE source_id IN ({placeholders})",
        values,
    )


def prepare_attested(ctx: SignalContext) -> None:
    """Every word an attesting source carried a ``headword`` fact for."""
    name = quoted(_ATTESTED_TABLE)
    ctx.conn.execute(f"DROP TABLE IF EXISTS {name}")
    ctx.conn.execute(f"CREATE TEMP TABLE {name} (word TEXT PRIMARY KEY) WITHOUT ROWID")
    ctx.conn.execute(
        f"INSERT OR IGNORE INTO {name} (word) {ATTESTED_WORDS_SQL}",
        ATTESTING_ROLES,
    )


def prepare_breadth(ctx: SignalContext) -> None:
    """How many DISTINCT sources observed each surface.

    Stored as the raw count rather than a normalised score: the number is read
    as a count downstream - Row 8 prunes its neighbour search at three or more
    sources - and normalising it would make that threshold depend on how many
    sources happen to be registered today.
    """
    name = quoted(_BREADTH_TABLE)
    ctx.conn.execute(f"DROP TABLE IF EXISTS {name}")
    ctx.conn.execute(
        f"CREATE TEMP TABLE {name} "
        f"(word TEXT PRIMARY KEY, sources INTEGER NOT NULL) WITHOUT ROWID"
    )
    ctx.conn.execute(
        f"INSERT INTO {name} (word, sources) "
        f"SELECT surface, count(DISTINCT source_id) FROM observation GROUP BY surface"
    )


def prepare_nannul(ctx: SignalContext) -> None:
    """The words a Nannul-rules Tamil spellchecker already passed."""
    _membership_table(ctx, _NANNUL_TABLE, ctx.config.nannulSources)


def prepare_verb_form(ctx: SignalContext) -> None:
    """The collected inflected verb forms."""
    _membership_table(ctx, _VERB_FORM_TABLE, ctx.config.verbFormSources)


def prepare_orthotactic(ctx: SignalContext) -> None:
    """Register the shape analysis as a deterministic SQLite function.

    A user-defined function rather than a Python pass, so the one signal that
    cannot be written in SQL still runs inside the same single streamed
    statement as the four that can. ``deterministic`` is true because it is: the
    score is a pure function of the surface and the weights the run was given.
    """
    weights = ctx.config.orthotactic

    def score(word: str) -> float:
        return orthotactic_score(word, weights)

    ctx.conn.create_function(ORTHOTACTIC_UDF, 1, score, deterministic=True)


# Membership answers are cast to REAL because the column is REAL: SQLite would
# store the integer 1 there and a reader comparing it to 1.0 would still be
# right, but a column whose type is uniform is a column nobody has to reason
# about.
EXACT_SIGNALS: Final[tuple[Signal, ...]] = (
    Signal(
        name="attested",
        expression=(
            f"CAST(EXISTS (SELECT 1 FROM {_ATTESTED_TABLE} t "
            f"WHERE t.word = {{word}}) AS REAL)"
        ),
        prepare=prepare_attested,
    ),
    Signal(
        name="orthotactic",
        expression=f"{ORTHOTACTIC_UDF}({{word}})",
        prepare=prepare_orthotactic,
    ),
    Signal(
        name="breadth",
        expression=(
            f"CAST(COALESCE((SELECT b.sources FROM {_BREADTH_TABLE} b "
            f"WHERE b.word = {{word}}), 0) AS REAL)"
        ),
        prepare=prepare_breadth,
    ),
    Signal(
        name="nannulValid",
        expression=(
            f"CAST(EXISTS (SELECT 1 FROM {_NANNUL_TABLE} t "
            f"WHERE t.word = {{word}}) AS REAL)"
        ),
        prepare=prepare_nannul,
    ),
    Signal(
        name="knownVerbForm",
        expression=(
            f"CAST(EXISTS (SELECT 1 FROM {_VERB_FORM_TABLE} t "
            f"WHERE t.word = {{word}}) AS REAL)"
        ),
        prepare=prepare_verb_form,
    ),
)


def configured_sources(config: Wordhood) -> tuple[str, ...]:
    """Every source id these signals depend on, deduplicated and sorted.

    ENRICH checks these against the store before it computes anything: an id
    that is not staged produces a column of zeros, and a column of zeros looks
    exactly like a signal that found nothing.
    """
    return tuple(sorted({*config.nannulSources, *config.verbFormSources}))
