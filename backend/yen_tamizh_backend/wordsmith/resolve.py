"""PUBLISH's resolution rules: many sources' facts into one row (Row 11).

STAGE deliberately resolves nothing - every fact keeps the ``source_id`` that
asserted it, and two sources contradicting each other keep two rows. That is
what makes the staged zone commutative. This module is where the contradiction
is settled, once, with the registry's precedence in hand. The rules and why each
is what it is live in ``docs/architecture/lexicon/pipeline.md``.

Two shapes of rule, and the difference is not arbitrary:

- **UNION** for a set-valued fact with no display slot - ``pos``,
  ``synonymsTa``, ``categories``. A Tamil verbal noun genuinely is both a noun
  and a verb, and resolving those by precedence would delete whichever a
  lower-ranked source held.
- **PRECEDENCE** for a fact that occupies ONE display slot - ``translationEn``.
  Exactly one can be shown, so exactly one source wins, and the winner is
  decided by an explicit per-source integer rather than by the order the
  registry array happens to be written in - with ATTESTED ahead of AUTHORED,
  because a source that recorded the meaning outranks a pass that wrote one
  (Row 4 decision 2a).

``definitionTa`` is a THIRD shape, and Row 12a is why. A word has more than one
meaning, and a dictionary page says so: the Tamil Wiktionary lists three senses
of ``vaakai`` - the tree, the garland a victor wears, and victory itself - under
one meaning block. Resolving it as a single slot published the tree and threw
the other two away, on a row whose own English translation described them. So it
is an ORDERED UNION: every sense any source asserted, ordered by exactly the
rule that used to pick the winner, deduplicated on the text. Element zero is
therefore the value the single-slot rule produced, so the one meaning a hint
spends is unchanged and nothing is discarded.

``frequency`` is none of the three: it SUMS over the frequency corpora, because
a count is evidence that adds up rather than a claim that competes.
``spokenRatio`` is the declared spoken corpora's share of that sum.

Attestation resolves to two COUNTS rather than to the list of names. Selection
gates on how many sources listed a surface and how many of those were
lexicographic; the names themselves are provenance, and provenance lives in the
store where a question about one word can be asked of it.

Everything is computed in SQLite over small keyed temp tables and streamed out
one row at a time, so peak Python memory is one row whatever the population is.
``definitionEn`` is never published: it is the one column the inventory carries
only as English prose, and the lexicon serves Tamil.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Final, get_args

from yen_tamizh_backend.contracts.lexicon import LexiconEntry, PartOfSpeech
from yen_tamizh_backend.contracts.lexicon_sources import (
    ATTESTING_ROLES,
    LexiconSources,
)
from yen_tamizh_backend.ezhuthu import segment

# ASCII unit separator. The joined values are Tamil words, closed part-of-speech
# names and theme slugs, so a control character cannot occur in one - and the
# guard below proves that rather than assuming it.
SEPARATOR: Final = "\x1f"

# The set-valued fact attributes, and the published column each becomes. A2's
# sideways gloss clique is staged as ``glossPeer`` rather than ``synonym`` (Row
# 9b) and so is deliberately absent: it is a list of words that share a gloss,
# not a list of words that mean the same thing.
UNION_ATTRS: Final[dict[str, str]] = {
    "pos": "pos",
    "synonym": "synonymsTa",
    "category": "categories",
}

# The single-slot fact attribute, resolved by precedence.
SINGLE_ATTRS: Final[tuple[str, ...]] = ("translation",)

# The ordered-union fact attribute: every value, in the single-slot order.
SENSE_ATTR: Final = "definitionTa"

# How many digits the rank prefix that carries sense order through SQLite's
# concatenation is written in. SQLite does not promise an aggregate's
# concatenation order, and the order IS the information here, so each value
# carries its own rank and Python sorts on it. Five digits is four more than any
# real row needs and is the same width whatever the count, so it never changes
# the sort.
_RANK_DIGITS: Final = 5

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
        tier1      INTEGER NOT NULL,
        authored   INTEGER NOT NULL,
        PRIMARY KEY (id)
    ) WITHOUT ROWID
    """,
    """
    CREATE TEMP TABLE publish_row (
        word         TEXT NOT NULL,
        wordClass    TEXT NOT NULL,
        baseEzhuthu  TEXT NOT NULL,
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
    CREATE TEMP TABLE publish_attestation (
        word    TEXT    NOT NULL,
        sources INTEGER NOT NULL,
        tier1   INTEGER NOT NULL,
        PRIMARY KEY (word)
    ) WITHOUT ROWID
    """,
    """
    CREATE TEMP TABLE publish_union (
        word   TEXT NOT NULL,
        attr   TEXT NOT NULL,
        joined TEXT NOT NULL,
        PRIMARY KEY (word, attr)
    ) WITHOUT ROWID
    """,
    """
    CREATE TEMP TABLE publish_single (
        word  TEXT NOT NULL,
        attr  TEXT NOT NULL,
        value TEXT NOT NULL,
        PRIMARY KEY (word, attr)
    ) WITHOUT ROWID
    """,
    """
    CREATE TEMP TABLE publish_sense (
        word   TEXT NOT NULL,
        joined TEXT NOT NULL,
        PRIMARY KEY (word)
    ) WITHOUT ROWID
    """,
)

_STREAM = """
SELECT p.word,
       p.wordClass,
       coalesce(f.total, 0),
       f.spoken,
       coalesce(a.sources, 0),
       coalesce(a.tier1, 0),
       (SELECT joined FROM publish_union u WHERE u.word = p.word AND u.attr = 'pos'),
       (SELECT joined FROM publish_union u
         WHERE u.word = p.word AND u.attr = 'synonym'),
       (SELECT joined FROM publish_union u
         WHERE u.word = p.word AND u.attr = 'category'),
       (SELECT value FROM publish_single g
         WHERE g.word = p.word AND g.attr = 'translation'),
       (SELECT joined FROM publish_sense d WHERE d.word = p.word)
  FROM publish_row p
  LEFT JOIN publish_frequency f ON f.word = p.word
  LEFT JOIN publish_attestation a ON a.word = p.word
 ORDER BY p.wordClass, p.baseEzhuthu, p.word
"""


class ResolutionError(ValueError):
    """A fact the closed vocabulary cannot hold, named with its row count."""


def base_ezhuthu(word: str) -> str:
    """The BASE letter the word opens on - the second half of a row's address.

    One code point: the uyir, the consonant or the aytham. A vowel sign or a
    pulli is a combining mark that rides on that letter, so ``ka``, ``kaa`` and
    ``ki`` share an address exactly as a dictionary files them together, and the
    key is always four hex digits.

    Deliberately pure and total: it is registered as a SQL function so the
    stream is ORDERED by the same value the writer names a file after, and a
    function that can raise inside SQLite loses its message on the way out. The
    checks that CAN fail belong to the writer, which knows the file it was about
    to name.
    """
    return segment(word)[0][0]


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


def _senses(joined: str | None) -> list[str] | None:
    """Split the sense column back into an ORDERED, deduplicated list.

    Each value arrives carrying its own zero-padded rank, because SQLite does
    not promise an aggregate's concatenation order and here the order is the
    information: element zero is the sense the single display slot shows. So the
    rank is sorted on and then stripped, and a repeated sense keeps its first
    (most authoritative) position.
    """
    if joined is None:
        return None
    ranked = sorted(piece for piece in joined.split(SEPARATOR) if piece)
    senses: dict[str, None] = {}
    for piece in ranked:
        senses.setdefault(piece[_RANK_DIGITS:], None)
    return list(senses) or None


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

    Roles, precedence, the tier and the spoken set are read from the REGISTRY
    rather than from the store's own copy, on Row 9a's rule: re-ruling a source
    is a config edit plus a re-publish, never a re-stage.
    """
    spoken = frozenset(registry.spokenSources)
    conn.create_function("base_ezhuthu", 1, base_ezhuthu, deterministic=True)
    for statement in _TEMP_SCHEMA:
        conn.execute(statement)
    conn.executemany(
        "INSERT INTO publish_source (id, role, precedence, spoken, tier1, authored) "
        "VALUES (?,?,?,?,?,?)",
        [
            (
                source.id,
                source.role,
                source.precedence,
                int(source.id in spoken),
                int(source.attestationTier == "lexicographic"),
                int(source.role == "authored"),
            )
            for source in registry.sources
        ],
    )
    staged = {str(row[0]) for row in conn.execute("SELECT id FROM source").fetchall()}
    unregistered = sorted(staged - {source.id for source in registry.sources})
    if unregistered:
        raise ResolutionError(
            f"the store holds sources the registry does not name: "
            f"{', '.join(unregistered)}"
        )

    classes = list(registry.publishedClasses)
    marks = ",".join("?" for _ in classes)
    conn.execute(
        # The address is stored beside the row rather than recomputed at stream
        # time, so the ORDER BY the writer depends on is a plain column read.
        f"INSERT INTO publish_row (word, wordClass, baseEzhuthu) "
        f"SELECT word, wordClass, base_ezhuthu(word) FROM classification "
        f"WHERE wordClass IN ({marks})",
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
    attesting_marks = ",".join("?" for _ in ATTESTING_ROLES)
    conn.execute(
        # Counted DISTINCT on the source rather than on the fact: one source
        # listing a surface twice is one source saying one thing.
        f"INSERT INTO publish_attestation (word, sources, tier1) "
        f"SELECT f.word, count(DISTINCT f.source_id), "
        f"       count(DISTINCT CASE WHEN s.tier1 = 1 THEN f.source_id END) "
        f"  FROM publish_row p "
        f"  JOIN fact f ON f.word = p.word "
        f"  JOIN publish_source s ON s.id = f.source_id "
        f" WHERE f.attr = 'headword' AND s.role IN ({attesting_marks}) "
        f" GROUP BY f.word",
        list(ATTESTING_ROLES),
    )
    union_marks = ",".join("?" for _ in UNION_ATTRS)
    conn.execute(
        f"INSERT INTO publish_union (word, attr, joined) "
        f"SELECT f.word, f.attr, group_concat(f.value, char(31)) "
        f"  FROM publish_row p "
        f"  JOIN fact f ON f.word = p.word "
        f" WHERE f.attr IN ({union_marks}) "
        f" GROUP BY f.word, f.attr",
        list(UNION_ATTRS),
    )
    single_marks = ",".join("?" for _ in SINGLE_ATTRS)
    conn.execute(
        # s.authored leads the order, so an ATTESTED value always outranks an
        # authored one however the precedence integers happen to be numbered -
        # which is what keeps Row 4 decision 2a true as sources are appended.
        # row_number rather than SQLite's bare-column-with-min() shorthand: one
        # source can assert the same attribute twice, and then min(precedence)
        # ties and the shorthand leaves the winner unspecified. A total order
        # cannot tie.
        f"INSERT INTO publish_single (word, attr, value) "
        f"SELECT word, attr, value FROM ( "
        f"  SELECT f.word AS word, f.attr AS attr, f.value AS value, "
        f"         row_number() OVER ( "
        f"           PARTITION BY f.word, f.attr "
        f"           ORDER BY s.authored, s.precedence, f.ordinal, f.value) AS rn "
        f"    FROM publish_row p "
        f"    JOIN fact f ON f.word = p.word "
        f"    JOIN publish_source s ON s.id = f.source_id "
        f"   WHERE f.attr IN ({single_marks}) "
        f") WHERE rn = 1",
        list(SINGLE_ATTRS),
    )
    conn.execute(
        # The SAME total order as the single slot, kept whole instead of cut to
        # its first row: element zero is what precedence would have published,
        # and the senses behind it are no longer dropped. The rank travels with
        # each value because group_concat's own order is unspecified, and the
        # reader sorts on it.
        f"INSERT INTO publish_sense (word, joined) "
        f"SELECT word, group_concat(printf('%0{_RANK_DIGITS}d', rn) || value, "
        f"       char(31)) FROM ( "
        f"  SELECT f.word AS word, f.value AS value, "
        f"         row_number() OVER ( "
        f"           PARTITION BY f.word "
        f"           ORDER BY s.authored, s.precedence, f.ordinal, f.value) AS rn "
        f"    FROM publish_row p "
        f"    JOIN fact f ON f.word = p.word "
        f"    JOIN publish_source s ON s.id = f.source_id "
        f"   WHERE f.attr = ? "
        f") GROUP BY word",
        (SENSE_ATTR,),
    )
    counted = conn.execute("SELECT count(*) FROM publish_row").fetchone()
    return 0 if counted is None else int(counted[0])


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
        attestations,
        tier1,
        parts,
        synonyms,
        categories,
        translation,
        senses,
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
        yield LexiconEntry(
            word=word,
            definitionTa=_senses(senses),
            translationEn=translation,
            synonymsTa=_values(synonyms, drop=word),
            pos=_values(parts),
            categories=_values(categories),
            frequency=frequency,
            length=len(segment(word)),
            wordClass=word_class,
            attestations=int(attestations),
            tier1Attestations=int(tier1),
            spokenRatio=ratio,
        )
