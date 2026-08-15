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

Row 8 adds three more entries to ``INEXACT_SIGNALS`` and appends them to the
runner's tuple. Nothing here needs to change for that.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

from yen_tamizh_backend.contracts.lexicon import SignalName
from yen_tamizh_backend.contracts.lexicon_sources import SourceRole
from yen_tamizh_backend.contracts.wordhood import OrthotacticWeights, Wordhood
from yen_tamizh_backend.ezhuthu import analyse
from yen_tamizh_backend.wordsmith.store import quoted

# The roles that may assert word-hood. A frequency list observing a surface a
# million times still cannot say it is a word, and ``formEvidence`` can only
# ever assert the NEGATIVE (docs/concepts/lexicon.md). This is a fact about what
# the roles MEAN, so it is a constant here rather than a knob in config.
ATTESTING_ROLES: Final[tuple[SourceRole, ...]] = ("authority", "authored")

_ATTESTED_TABLE: Final = "tmp_attested"
_BREADTH_TABLE: Final = "tmp_breadth"
_NANNUL_TABLE: Final = "tmp_nannul"
_VERB_FORM_TABLE: Final = "tmp_verb_form"

ORTHOTACTIC_UDF: Final = "orthotactic_score"


@dataclass(frozen=True, slots=True)
class SignalContext:
    """What a signal's preparation is allowed to see: the store and the knobs."""

    conn: sqlite3.Connection
    config: Wordhood


@dataclass(frozen=True, slots=True)
class Signal:
    """One word-hood signal.

    ``name`` is both the signal and its column in the store's ``signal`` table -
    one name, so a signal cannot be written into the wrong column.
    ``expression`` is SQL with a single ``{word}`` placeholder, which the runner
    fills with whichever surface expression its pass has: the population alias
    on a full rebuild, the row's own column on a single-signal recompute.
    """

    name: SignalName
    expression: str
    prepare: Callable[[SignalContext], None]


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
    placeholders = ",".join("?" for _ in ATTESTING_ROLES)
    ctx.conn.execute(f"DROP TABLE IF EXISTS {name}")
    ctx.conn.execute(f"CREATE TEMP TABLE {name} (word TEXT PRIMARY KEY) WITHOUT ROWID")
    ctx.conn.execute(
        f"INSERT OR IGNORE INTO {name} (word) "
        f"SELECT f.word FROM fact f JOIN source s ON s.id = f.source_id "
        f"WHERE f.attr = 'headword' AND s.role IN ({placeholders})",
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
