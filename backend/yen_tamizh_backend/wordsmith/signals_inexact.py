"""The three INEXACT word-hood signals (Row 8) - the ones that need a search.

Row 7 landed the five signals that are lookups. These three are not: one needs
a statistical model fitted over the corpus, one needs a nearest-neighbour search
over every headword, and one needs the whole frequency distribution before it
can say anything about a single word.

| Signal | What it asks | What it catches |
| --- | --- | --- |
| ``ngram`` | how likely is this ezhuthu sequence? | an unlikely sequence is a typo |
| ``neighbour`` | how close is the nearest headword? | a near-miss on a real word |
| ``zipf`` | does its frequency fit its rank? | a diagnostic, and the weakest |

What each one MEANS to the classifier is
``docs/architecture/lexicon/word-hood.md``. What each one is WORTH is
``config/wordhood.json``. This module is only how each is computed, and it adds
nothing to the runner that Row 7 did not already build a seam for.

Two of the three still fit Row 7's shape exactly - a preparation that leaves a
small keyed structure behind, and one SQL expression evaluated in the single
streamed pass over the population. ``neighbour`` does not, and the reason is
worth stating: its query set is decided by ``attested``, ``knownVerbForm`` and
``breadth``, which that same pass is still computing. It therefore declares
``NOT_MEASURED`` as its expression and fills its column in a pass of its own
afterwards, inside the same transaction - which also means a surface the prune
skipped keeps a NULL, and NULL is the honest answer for a question nobody asked.

THE DICTIONARY BOTH INEXACT SIGNALS CONSULT IS THE SAME ONE, and it is narrower
than "every attested headword": it is every attested headword that is WHOLLY
TAMIL. Row 7 measured that 128,648 of the 589,862 attested headwords - 21.8
percent - carry a unit that is not an ezhuthu at all: a Latin transliteration, a
digit, a compound scraped without its space. Training an ezhuthu model on a set
that is a fifth not-Tamil teaches it the very shapes it exists to flag, and a
dictionary of "real words" holding them would call a scrape artifact the nearest
real word to another scrape artifact. The filter is the same ``hasNonTamil``
test ``orthotactic`` already uses to score such a surface zero outright, so
there is one definition of "is this Tamil" rather than two.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final

from yen_tamizh_backend.wordsmith import ngram as ngram_model
from yen_tamizh_backend.wordsmith import neighbours
from yen_tamizh_backend.wordsmith.signals_exact import (
    ATTESTED_WORDS_SQL,
    ATTESTING_ROLES,
    NOT_MEASURED,
    Signal,
    SignalContext,
)
from yen_tamizh_backend.wordsmith.store import quoted

_HEADWORD_TABLE: Final = "tmp_headword"
_ZIPF_TABLE: Final = "tmp_zipf"

NGRAM_UDF: Final = "ngram_score"
_TAMIL_UDF: Final = "is_fully_tamil"

# Where a preparation leaves what its pass needs. Keyed on the run's context
# rather than parked in a module global: two ENRICH calls in one process - which
# is what the tests do - must not be able to see each other's model.
HEADWORDS: Final = "headwords"
NGRAM_MODEL: Final = "ngramModel"
NEIGHBOUR_INDEX: Final = "neighbourIndex"
ZIPF_FIT: Final = "zipfFit"


@dataclass(frozen=True, slots=True)
class HeadwordCensus:
    """How many headwords there are, and how many of them are Tamil.

    Both numbers, because the gap between them is the measurement that decided
    the training set: reporting only the filtered count would hide the size of
    the filter.
    """

    attested: int
    tamil: int

    def note(self) -> str:
        dropped = self.attested - self.tamil
        share = 100.0 * dropped / self.attested if self.attested else 0.0
        return (
            f"headwords: attested={self.attested} wholly Tamil={self.tamil} "
            f"(dropped {dropped}, {share:.1f}%)"
        )


def ensure_headwords(ctx: SignalContext) -> HeadwordCensus:
    """Collect the dictionary both inexact signals consult, once per run.

    Built by inserting every attested headword and then deleting the ones that
    are not wholly Tamil, rather than by filtering on the way in: the two counts
    either side of that delete are exactly the raw and filtered training-set
    sizes, and they cost nothing extra to have.
    """
    conn = ctx.conn
    name = quoted(_HEADWORD_TABLE)
    existing = conn.execute(
        "SELECT count(*) FROM temp.sqlite_master WHERE type = 'table' AND name = ?",
        (_HEADWORD_TABLE,),
    ).fetchone()
    if existing is not None and int(existing[0]):
        held = ctx.state.get(HEADWORDS)
        if isinstance(held, HeadwordCensus):
            return held
    conn.create_function(_TAMIL_UDF, 1, neighbours.is_fully_tamil, deterministic=True)
    conn.execute(f"DROP TABLE IF EXISTS {name}")
    conn.execute(f"CREATE TEMP TABLE {name} (word TEXT PRIMARY KEY) WITHOUT ROWID")
    conn.execute(
        f"INSERT OR IGNORE INTO {name} (word) {ATTESTED_WORDS_SQL}", ATTESTING_ROLES
    )
    attested = _scalar(conn, f"SELECT count(*) FROM {name}")
    conn.execute(f"DELETE FROM {name} WHERE NOT {_TAMIL_UDF}(word)")
    census = HeadwordCensus(
        attested=attested, tamil=_scalar(conn, f"SELECT count(*) FROM {name}")
    )
    if not census.tamil:
        raise ValueError(
            "no attested headword is wholly Tamil - the inexact signals have "
            "no dictionary to measure against"
        )
    ctx.state[HEADWORDS] = census
    return census


def headwords(conn: sqlite3.Connection) -> Iterator[str]:
    """Stream the dictionary in key order, so nothing materialises it twice."""
    for row in conn.execute(f"SELECT word FROM {quoted(_HEADWORD_TABLE)} ORDER BY word"):
        yield str(row[0])


def _scalar(conn: sqlite3.Connection, sql: str) -> int:
    row = conn.execute(sql).fetchone()
    if row is None:
        raise ValueError(f"{sql!r} returned no row")
    return int(row[0])


# --------------------------------------------------------------------------
# ngram - how likely the ezhuthu sequence is
# --------------------------------------------------------------------------


def prepare_ngram(ctx: SignalContext) -> None:
    """Fit the model over the dictionary and register it as a SQL function.

    A deterministic user-defined function for the same reason ``orthotactic``
    is one: the score is a pure function of the surface and the fitted model, so
    it can run inside the single streamed pass rather than as another walk over
    six and a quarter million rows.
    """
    ensure_headwords(ctx)
    settings = ctx.config.ngram
    model = ngram_model.train(
        headwords(ctx.conn), order=settings.order, smoothing=settings.smoothing
    )
    ctx.state[NGRAM_MODEL] = model

    def score(word: str) -> float:
        return ngram_model.score(model, word)

    ctx.conn.create_function(NGRAM_UDF, 1, score, deterministic=True)


# --------------------------------------------------------------------------
# zipf - whether a surface's frequency fits its rank
# --------------------------------------------------------------------------

# Rank is a function of the observed total, and thousands of surfaces share a
# total, so the prepared table is keyed on the TOTAL rather than on the word.
# Keyed on the word it would be one row per surface - a temp table the size of
# the whole population, held in memory beside the population write that is
# already the heaviest thing this stage does.
#
# ``total > 0`` is not a filter on quality, it is what a logarithm needs. A
# dictionary is a word LIST rather than a count, so its surfaces arrive observed
# with a count of zero; zero occurrences is not a measured frequency, so those
# surfaces get no rank, no residual, and a NULL that says exactly that.
_ZIPF_GROUPS_SQL: Final = (
    "SELECT total, count(*) AS surfaces FROM "
    "(SELECT surface, SUM(count) AS total FROM observation GROUP BY surface) "
    "WHERE total > 0 GROUP BY total ORDER BY total DESC"
)


@dataclass(frozen=True, slots=True)
class ZipfFit:
    """The line fitted through the corpus's own rank-frequency plot."""

    intercept: float
    exponent: float
    surfaces: int
    groups: int

    def note(self) -> str:
        return (
            f"zipf: log10(f) = {self.intercept:.4f} - {self.exponent:.4f} * "
            f"log10(r) over {self.surfaces} surfaces in {self.groups} rank groups"
        )


def fit_zipf(groups: list[tuple[int, int]]) -> tuple[ZipfFit, list[tuple[int, float]]]:
    """Fit ``log10(f) = a - s * log10(r)`` and return each total's residual.

    Competition ranking: every surface sharing an observed total shares its
    rank, and the next distinct total takes the rank after all of them. Ties
    broken by anything else - the surface's own spelling, say - would make the
    exponent depend on collation rather than on the corpus.

    The fit is weighted by how many surfaces sit at each total, so the line is
    the one through all six and a quarter million points rather than through the
    few thousand distinct frequencies.
    """
    count = 0.0
    sumX = 0.0
    sumY = 0.0
    sumXX = 0.0
    sumXY = 0.0
    ranked: list[tuple[int, float, float]] = []
    seen = 0
    for total, surfaces in groups:
        rank = seen + 1
        seen += surfaces
        x = math.log10(rank)
        y = math.log10(total)
        weight = float(surfaces)
        count += weight
        sumX += weight * x
        sumY += weight * y
        sumXX += weight * x * x
        sumXY += weight * x * y
        ranked.append((total, x, y))
    spread = count * sumXX - sumX * sumX
    if spread == 0.0:
        # One distinct frequency, or one rank group: there is no rank structure
        # for a surface to deviate from, so nothing deviates from it.
        fit = ZipfFit(intercept=0.0, exponent=0.0, surfaces=seen, groups=len(ranked))
        return fit, [(total, 0.0) for total, _, _ in ranked]
    slope = (count * sumXY - sumX * sumY) / spread
    intercept = (sumY - slope * sumX) / count
    fit = ZipfFit(
        intercept=intercept,
        exponent=-slope,
        surfaces=seen,
        groups=len(ranked),
    )
    return fit, [(total, y - (intercept + slope * x)) for total, x, y in ranked]


def prepare_zipf(ctx: SignalContext) -> None:
    """Rank every observed total, fit the line, and store each one's residual."""
    conn = ctx.conn
    name = quoted(_ZIPF_TABLE)
    conn.execute(f"DROP TABLE IF EXISTS {name}")
    conn.execute(
        f"CREATE TEMP TABLE {name} "
        f"(total INTEGER PRIMARY KEY, residual REAL NOT NULL) WITHOUT ROWID"
    )
    groups = [(int(row[0]), int(row[1])) for row in conn.execute(_ZIPF_GROUPS_SQL)]
    fit, residuals = fit_zipf(groups)
    ctx.state[ZIPF_FIT] = fit
    conn.executemany(f"INSERT INTO {name} (total, residual) VALUES (?, ?)", residuals)


# --------------------------------------------------------------------------
# neighbour - how close the nearest headword is
# --------------------------------------------------------------------------


def prepare_neighbour(ctx: SignalContext) -> None:
    """Build the deletion neighbourhood over the dictionary."""
    ensure_headwords(ctx)
    ctx.state[NEIGHBOUR_INDEX] = neighbours.build_index(
        headwords(ctx.conn), ctx.config.neighbour.maxEditDistance
    )


def prune_predicate(ctx: SignalContext) -> tuple[str, tuple[object, ...]]:
    """Which surfaces are worth querying, and which are skipped outright.

    The signal's only consumer is the ``suspectedTypo`` verdict, so a surface an
    authority attested, a surface that is a collected verb form, and a surface
    several independent sources agree on are all skipped: none of them can be
    the thing this signal is looking for, and together they are the difference
    between a pass that finishes and one that does not.
    """
    columns = " OR ".join(
        (
            f"{quoted('attested')} > 0",
            f"{quoted('knownVerbForm')} > 0",
            f"{quoted('breadth')} >= ?",
        )
    )
    return f"NOT ({columns})", (ctx.config.neighbour.pruneBreadth,)


def neighbour_pass(ctx: SignalContext) -> int:
    """Score the pruned query set against the index the preparation built."""
    index = ctx.state.get(NEIGHBOUR_INDEX)
    if not isinstance(index, neighbours.NeighbourIndex):
        raise RuntimeError("the neighbour index was never built for this run")
    predicate, values = prune_predicate(ctx)
    return neighbours.score_population(
        ctx.conn, index, predicate, values, ctx.workers
    )


INEXACT_SIGNALS: Final[tuple[Signal, ...]] = (
    Signal(
        name="ngram",
        expression=f"{NGRAM_UDF}({{word}})",
        prepare=prepare_ngram,
    ),
    Signal(
        # No COALESCE: a surface no source ever OBSERVED has no frequency, so it
        # has no rank and no residual, and NULL says that where a zero would
        # claim it sits exactly on the line.
        name="zipf",
        expression=(
            f"(SELECT z.residual FROM {_ZIPF_TABLE} z WHERE z.total = "
            f"(SELECT SUM(o.count) FROM observation o WHERE o.surface = {{word}}))"
        ),
        prepare=prepare_zipf,
    ),
    Signal(
        name="neighbour",
        expression=NOT_MEASURED,
        prepare=prepare_neighbour,
        second_pass=neighbour_pass,
    ),
)
