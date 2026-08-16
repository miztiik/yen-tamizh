"""PUBLISH's resolution rules: many sources' facts into one row (Row 11).

STAGE deliberately resolves nothing - every fact keeps the ``source_id`` that
asserted it, and two sources contradicting each other keep two rows. That is
what makes the staged zone commutative. This module is where the contradiction
is settled, once, with the registry's precedence in hand. The rules and why each
is what it is live in ``docs/architecture/lexicon/pipeline.md``.

Two shapes of rule, and the difference is not arbitrary:

- **UNION** for a set-valued fact with no display slot - ``pos``,
  ``synonymsTa``, ``categories``, ``attestedBy``. A Tamil verbal noun genuinely
  is both a noun and a verb, and resolving those by precedence would delete
  whichever a lower-ranked source held.
- **PRECEDENCE** for a fact that occupies ONE display slot - ``translationEn``,
  ``definitionTa``. Exactly one can be shown, so exactly one source wins, and
  the winner is decided by an explicit per-source integer rather than by the
  order the registry array happens to be written in.

``frequency`` is neither: it SUMS over the frequency corpora, because a count is
evidence that adds up rather than a claim that competes. ``spokenRatio`` is the
declared spoken corpora's share of that sum.

Everything is computed in SQLite over small keyed temp tables and streamed out
one row at a time, so peak Python memory is one row whatever the population is.
``definitionEn`` is never published: the lexicon takes the FACT a source
asserted, never its edited prose.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final, get_args

from yen_tamizh_backend.contracts.lexicon import (
    LexiconEntry,
    PartOfSpeech,
    ProvenanceState,
)
from yen_tamizh_backend.contracts.lexicon_sources import (
    ATTESTING_ROLES,
    LexiconSources,
)
from yen_tamizh_backend.ezhuthu import segment

# ASCII unit separator. The joined values are Tamil words, source slugs, closed
# part-of-speech names and theme slugs, so a control character cannot occur in
# one - and the guard below proves that rather than assuming it.
SEPARATOR: Final = "\x1f"

# The set-valued fact attributes, and the published column each becomes.
UNION_ATTRS: Final[dict[str, str]] = {
    "pos": "pos",
    "synonym": "synonymsTa",
    "category": "categories",
}

# The single-slot fact attributes, resolved by precedence.
SINGLE_ATTRS: Final[tuple[str, ...]] = ("translation", "definitionTa")

_PARTS_OF_SPEECH: Final[frozenset[str]] = frozenset(get_args(PartOfSpeech))

# Six decimal places on the spoken share. The denominator runs to millions, so
# a millionth is already far finer than the signal means anything at, and a
# ratio a reviewer can read is one of the three soft goals the published layout
# is chosen for. Deterministic either way: the same two integers round the same.
_RATIO_PLACES: Final = 6

_TEMP_SCHEMA: Final[tuple[str, ...]] = (
    """
    CREATE TEMP TABLE publish_source (
        id         TEXT    NOT NULL,
        role       TEXT    NOT NULL,
        precedence INTEGER NOT NULL,
        spoken     INTEGER NOT NULL,
        PRIMARY KEY (id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TEMP TABLE publish_row (
        word      TEXT NOT NULL,
        wordClass TEXT NOT NULL,
        PRIMARY KEY (word)
    ) WITHOUT ROWID
    """,
    """
    CREATE TEMP TABLE publish_frequency (
        word   TEXT    NOT NULL,
        total  INTEGER NOT NULL,
        spoken INTEGER,
        PRIMARY KEY (word)
    ) WITHOUT ROWID
    """,
    """
    CREATE TEMP TABLE publish_union (
        word     TEXT    NOT NULL,
        attr     TEXT    NOT NULL,
        joined   TEXT    NOT NULL,
        authored INTEGER NOT NULL,
        PRIMARY KEY (word, attr)
    ) WITHOUT ROWID
    """,
    """
    CREATE TEMP TABLE publish_single (
        word      TEXT NOT NULL,
        attr      TEXT NOT NULL,
        value     TEXT NOT NULL,
        source_id TEXT NOT NULL,
        role      TEXT NOT NULL,
        PRIMARY KEY (word, attr)
    ) WITHOUT ROWID
    """,
)

_STREAM = """
SELECT p.word,
       p.wordClass,
       coalesce(f.total, 0),
       f.spoken,
       (SELECT joined FROM publish_union u
         WHERE u.word = p.word AND u.attr = 'attestedBy'),
       (SELECT joined FROM publish_union u WHERE u.word = p.word AND u.attr = 'pos'),
       (SELECT joined FROM publish_union u
         WHERE u.word = p.word AND u.attr = 'synonym'),
       (SELECT authored FROM publish_union u
         WHERE u.word = p.word AND u.attr = 'synonym'),
       (SELECT joined FROM publish_union u
         WHERE u.word = p.word AND u.attr = 'category'),
       (SELECT authored FROM publish_union u
         WHERE u.word = p.word AND u.attr = 'category'),
       (SELECT value FROM publish_single g
         WHERE g.word = p.word AND g.attr = 'translation'),
       (SELECT source_id FROM publish_single g
         WHERE g.word = p.word AND g.attr = 'translation'),
       (SELECT value FROM publish_single g
         WHERE g.word = p.word AND g.attr = 'definitionTa'),
       (SELECT role FROM publish_single g
         WHERE g.word = p.word AND g.attr = 'definitionTa')
  FROM publish_row p
  LEFT JOIN publish_frequency f ON f.word = p.word
 ORDER BY p.wordClass, p.word
"""


class ResolutionError(ValueError):
    """A fact the closed vocabulary cannot hold, named with its row count."""


@dataclass(frozen=True, slots=True)
class VocabularyBreach:
    """One raw value no closed vocabulary admits, and how many rows carry it."""

    attr: str
    value: str
    rows: int


def _values(joined: str | None, drop: str | None = None) -> list[str] | None:
    """Split one joined column into the sorted, deduped list the row publishes.

    Deduping and sorting HERE rather than in SQL is deliberate: SQLite does not
    promise an aggregate's concatenation order, so a run that leaned on it would
    be reproducible only by luck - and byte-identity is this row's Oracle.
    """
    if joined is None:
        return None
    unique = {value for value in joined.split(SEPARATOR) if value and value != drop}
    return sorted(unique) or None


def check_the_closed_vocabularies(
    conn: sqlite3.Connection, registry: LexiconSources
) -> None:
    """Refuse to publish a fact no closed vocabulary admits.

    The tag maps translate a source's own orthography at EXTRACT, so a value
    reaching the store outside the vocabulary means the store was staged under a
    registry that has since changed. Never dropped - a silent boundary drop is
    the defect this pipeline exists to remove - and never passed through, which
    would defeat the closed enum. The message names the value AND its row count,
    so the fix is one config line and the cost of it is visible.

    Checked over the WHOLE store rather than only the published rows: a bad tag
    on a class this policy withholds still means the registry is wrong.
    """
    themes = frozenset(registry.categoryAliases.values())
    admitted = {"pos": _PARTS_OF_SPEECH, "category": themes}
    breaches: list[VocabularyBreach] = []
    for attr, allowed in admitted.items():
        rows = conn.execute(
            "SELECT value, count(*) FROM fact WHERE attr = ? GROUP BY value", (attr,)
        ).fetchall()
        breaches.extend(
            VocabularyBreach(attr=attr, value=str(value), rows=int(count))
            for value, count in rows
            if str(value) not in allowed
        )
    if breaches:
        named = "; ".join(
            f"{breach.attr} {breach.value!r} on {breach.rows} rows"
            for breach in sorted(breaches, key=lambda b: (b.attr, b.value))
        )
        raise ResolutionError(
            f"the store holds values no closed vocabulary admits: {named} - "
            f"register each in config/lexicon-sources.json with a destination "
            f"or an explicit reject reason, then re-extract and re-stage"
        )
    separated = conn.execute(
        "SELECT count(*) FROM fact WHERE instr(value, char(31)) > 0"
    ).fetchone()
    if separated is not None and int(separated[0]):
        raise ResolutionError(
            f"{int(separated[0])} fact values contain the unit separator this "
            f"stage joins on, so a union could not be split back apart"
        )


def prepare(conn: sqlite3.Connection, registry: LexiconSources) -> int:
    """Build the resolution temp tables. Returns the published population size.

    Roles, precedence and the spoken set are read from the REGISTRY rather than
    from the store's own copy, on Row 9a's rule: re-ruling a source is a config
    edit plus a re-publish, never a re-stage.
    """
    spoken = frozenset(registry.spokenSources)
    for statement in _TEMP_SCHEMA:
        conn.execute(statement)
    conn.executemany(
        "INSERT INTO publish_source (id, role, precedence, spoken) VALUES (?,?,?,?)",
        [
            (source.id, source.role, source.precedence, int(source.id in spoken))
            for source in registry.sources
        ],
    )
    staged = {
        str(row[0]) for row in conn.execute("SELECT id FROM source").fetchall()
    }
    unregistered = sorted(staged - {source.id for source in registry.sources})
    if unregistered:
        raise ResolutionError(
            f"the store holds sources the registry does not name: "
            f"{', '.join(unregistered)}"
        )

    classes = list(registry.publishedClasses)
    marks = ",".join("?" for _ in classes)
    conn.execute(
        f"INSERT INTO publish_row (word, wordClass) "
        f"SELECT word, wordClass FROM classification WHERE wordClass IN ({marks})",
        classes,
    )
    # A registry that names no spoken corpus has no numerator, so the column is
    # NULL and no row carries a spoken share. A zero would say "never spoken",
    # which is a different and false claim.
    spoken_share = (
        "sum(CASE WHEN s.spoken = 1 THEN o.count ELSE 0 END)"
        if registry.spokenSources
        else "NULL"
    )
    conn.execute(
        f"INSERT INTO publish_frequency (word, total, spoken) "
        f"SELECT p.word, sum(o.count), {spoken_share} "
        f"  FROM publish_row p "
        f"  JOIN observation o ON o.surface = p.word "
        f"  JOIN publish_source s ON s.id = o.source_id "
        f" WHERE s.role = 'frequency' "
        f" GROUP BY p.word"
    )
    union_marks = ",".join("?" for _ in UNION_ATTRS)
    conn.execute(
        f"INSERT INTO publish_union (word, attr, joined, authored) "
        f"SELECT f.word, f.attr, group_concat(f.value, char(31)), "
        f"       max(CASE WHEN s.role = 'authored' THEN 1 ELSE 0 END) "
        f"  FROM publish_row p "
        f"  JOIN fact f ON f.word = p.word "
        f"  JOIN publish_source s ON s.id = f.source_id "
        f" WHERE f.attr IN ({union_marks}) "
        f" GROUP BY f.word, f.attr",
        list(UNION_ATTRS),
    )
    attesting_marks = ",".join("?" for _ in ATTESTING_ROLES)
    conn.execute(
        f"INSERT INTO publish_union (word, attr, joined, authored) "
        f"SELECT f.word, 'attestedBy', group_concat(f.source_id, char(31)), 0 "
        f"  FROM publish_row p "
        f"  JOIN fact f ON f.word = p.word "
        f"  JOIN publish_source s ON s.id = f.source_id "
        f" WHERE f.attr = 'headword' AND s.role IN ({attesting_marks}) "
        f" GROUP BY f.word",
        list(ATTESTING_ROLES),
    )
    single_marks = ",".join("?" for _ in SINGLE_ATTRS)
    conn.execute(
        # row_number over (precedence, ordinal, value) rather than SQLite's
        # bare-column-with-min() shorthand: one source can assert the same
        # attribute twice, and then min(precedence) ties and the shorthand
        # leaves the winner unspecified. A total order cannot tie.
        f"INSERT INTO publish_single (word, attr, value, source_id, role) "
        f"SELECT word, attr, value, source_id, role FROM ( "
        f"  SELECT f.word AS word, f.attr AS attr, f.value AS value, "
        f"         f.source_id AS source_id, s.role AS role, "
        f"         row_number() OVER ( "
        f"           PARTITION BY f.word, f.attr "
        f"           ORDER BY s.precedence, f.ordinal, f.value) AS rn "
        f"    FROM publish_row p "
        f"    JOIN fact f ON f.word = p.word "
        f"    JOIN publish_source s ON s.id = f.source_id "
        f"   WHERE f.attr IN ({single_marks}) "
        f") WHERE rn = 1",
        list(SINGLE_ATTRS),
    )
    counted = conn.execute("SELECT count(*) FROM publish_row").fetchone()
    return 0 if counted is None else int(counted[0])


def _meaning_state(authored: bool) -> ProvenanceState:
    # "authored" is the weaker claim, so a meaning block any part of which was
    # written by the enrichment pass carries it. "reviewed" has no producer:
    # there is no human review pass yet, and an honest zero beats a flattering
    # guess. None of this reaches a player - an AI badge on some meanings makes
    # a player distrust all of them, including the dictionary's.
    return "authored" if authored else "attested"


def stream(conn: sqlite3.Connection) -> Iterator[LexiconEntry]:
    """Every published row, in ``wordClass`` then ``word`` ASC order.

    A generator over a cursor: nothing between the store and the writer holds
    more than one row.
    """
    for (
        word,
        word_class,
        total,
        spoken,
        attested,
        parts,
        synonyms,
        synonyms_authored,
        categories,
        categories_authored,
        translation,
        translation_source,
        definition,
        definition_role,
    ) in conn.execute(_STREAM):
        frequency = int(total)
        # A NULL numerator means no spoken corpus is declared, and a word no
        # frequency corpus counted has no ratio either - in both cases the
        # column is absent rather than zero.
        ratio = (
            round(int(spoken) / frequency, _RATIO_PLACES)
            if frequency > 0 and spoken is not None
            else None
        )
        synonym_list = _values(synonyms, drop=word)
        meaning = definition is not None or synonym_list is not None
        authored_meaning = definition_role == "authored" or bool(synonyms_authored)
        theme_list = _values(categories)
        yield LexiconEntry(
            word=word,
            length=len(segment(word)),
            wordClass=word_class,
            attestedBy=_values(attested),
            frequency=frequency,
            spokenRatio=ratio,
            definitionTa=definition,
            translationEn=translation,
            synonymsTa=synonym_list,
            meaningSource=_meaning_state(authored_meaning) if meaning else None,
            translationEnSource=translation_source,
            pos=_values(parts),
            categories=theme_list,
            categorySource=(
                _meaning_state(bool(categories_authored))
                if theme_list is not None
                else None
            ),
        )
