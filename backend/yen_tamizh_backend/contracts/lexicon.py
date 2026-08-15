"""The lexicon contracts (Row 3): the row shape and the meta document.

The lexicon is the all-words artifact that replaces the corpus layer's
destructive funnel: every surface any source ever showed us keeps its row, its
class and every fact a source asserted about it. The vocabulary - what a
``wordClass`` is, what attestation means, why ``length`` counts ezhuthu - is
defined once in ``docs/concepts/lexicon.md``; the shape decisions behind this
module are in ``docs/architecture/contracts/schemas.md``.

TWO contracts, because the artifact is a streamed NDJSON set with a sibling
header:

- ``Lexicon`` is the META document written to ``datasets/lexicon/lexicon.meta.json``
  - ``version``, ``changelog``, ``provenance``, ``counters`` and the partition
  table. It is a ``SchemaModel`` and is registered, so it gets a schema file.
- ``LexiconEntry`` is the ROW shape, one per NDJSON line. It is deliberately
  NOT a ``SchemaModel``: ``base.py`` forces ``version`` + ``changelog`` onto
  every ``SchemaModel``, and repeating a schema stamp on 3.97M data rows is
  exactly the kind of bytes-for-nothing this artifact cannot afford. It reaches
  ``schemas/lexicon.schema.json`` through ``Lexicon.rowSchema``, which exists so
  Pydantic emits the row shape into the schema's ``$defs`` - without that
  reference the row shape would ship with no schema at all (Holy Law #3).

There is deliberately no ``generatedAt``. Identity is content-addressed through
``provenance[].sha256`` plus the row count, so a rebuild byte-compares and a
hand-edit is detectable; git records when. ``counters`` is the integrity Oracle,
enforced by the model: every ``wordClass`` has a bucket, the buckets sum to
``counters.rows``, and the partition table's declared rows agree class by class.
That reconciliation is what proves the artifact's thesis - nothing is discarded.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yen_tamizh_backend.contracts.base import ChangelogEntry, SchemaModel
from yen_tamizh_backend.contracts.common import RelPath, SourceId

# The initial mint. The lexicon has no writer yet, so the date-stamp and its
# first changelog entry live here rather than in a data file: two writers of one
# schema picking their own dates is exactly the drift section 11 exists to stop.
# Migration class is build-time rewrite-in-place - a later change appends an
# entry and moves the stamp, and needs no read-side migration, because the only
# reader is the backend and every artifact regenerates in the same commit.
LEXICON_VERSION = "2026-08-14"
LEXICON_CHANGELOG = (
    ChangelogEntry(
        version=LEXICON_VERSION,
        change=(
            "Initial lexicon contracts: the LexiconEntry row shape and the "
            "Lexicon meta document (provenance, per-class counters, partition "
            "table)."
        ),
        why=(
            "Row 3 - contracts before logic (Holy Law #3): the all-words "
            "artifact that replaces the corpus funnel gets its typed shape "
            "before any stage reads or writes it."
        ),
    ),
)

# What KIND of thing a surface is. Every word carries exactly one. Closed,
# because the classifier's whole job is to reach one of these verdicts and an
# open set means an unreviewed value reaches a player through a selection that
# never named it. Selection is an allow-list of these values, so a word the
# classifier could not place (``unclassified``) can never be served by omission.
WordClass = Literal[
    "headword",
    "inflected",
    "colloquial",
    "properNoun",
    "loanword",
    "boundStem",
    "sandhiArtifact",
    "suspectedTypo",
    "unclassified",
]

# The parts of speech Tamil actually has. Closed, because a part of speech is a
# fact about the language rather than a tunable knob, and an open set means a
# mapping typo silently mints a tag no schema rejects and no selector matches.
# The members are fixed by the Row 4 census over every row of A2, A7 and C1 -
# never guessed from a sample - and every member has a producer on disk today.
#
# ``properNoun`` is NOT here: it is a ``wordClass``. One fact, one home. Nor is
# ``preposition``: Tamil has POSTpositions, and minting a member for a category
# the language lacks would mirror an English-side source label rather than
# describe Tamil. The raw-tag MAPPING is config (``lexicon-sources``); the
# VOCABULARY is contract.
PartOfSpeech = Literal[
    "adjective",
    "adverb",
    "conjunction",
    "determiner",
    "interjection",
    "noun",
    "numeral",
    "particle",
    "postposition",
    "pronoun",
    "verb",
]

# The word-hood signals the classifier reads. ``wordhood`` is a NAME-KEYED MAP
# over this enum rather than a fixed-arity object, so the exact-signal row and
# the inexact-signal row each land their own keys without either shipping a
# half-populated struct.
SignalName = Literal[
    "attested",
    "orthotactic",
    "breadth",
    "nannulValid",
    "knownVerbForm",
    "ngram",
    "neighbour",
    "zipf",
]

# How a value got here. ``attested`` - a source asserted it; ``authored`` - the
# enrichment pass wrote it from retained evidence; ``reviewed`` - a human
# checked it. Build-time provenance only: none of it is ever rendered to a
# player, because an AI badge on some meanings makes a player distrust all of
# them.
ProvenanceState = Literal["attested", "authored", "reviewed"]

_SHA256 = r"^[0-9a-f]{64}$"
_HEX4 = r"^[0-9a-f]{4}$"

_RowCount = Annotated[int, Field(ge=0)]

_WORD_CLASSES: tuple[WordClass, ...] = get_args(WordClass)


def _sorted_unique(values: list[str], field: str, word: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{field} holds duplicates for {word!r}: {values}")
    if list(values) != sorted(values):
        raise ValueError(f"{field} must be sorted for {word!r}: {values}")


class LexiconEntry(BaseModel):
    """One lexicon row: every published fact about one Tamil surface.

    Not a ``SchemaModel`` - see the module docstring.

    Every sparse column is OPTIONAL and never a defaulted empty list.
    ``model_dump(exclude_none=True)`` drops ``None`` but keeps ``[]``, so a
    defaulted empty list writes an empty pair on every row that lacks the fact -
    roughly 200 MB of nothing across the published set.

    ``wordhood`` and ``freqRank`` are optional for the same reason the publisher
    omits them: both are derived diagnostics rather than facts a source
    asserted, ``freqRank`` is a sort of the published ``frequency`` and
    ``wordClass`` IS ``wordhood``'s verdict, so neither can cost the project a
    fact. The contract still types them, because the store-side renderings carry
    them and an untyped diagnostic is an untyped diagnostic.
    """

    model_config = ConfigDict(extra="forbid")

    word: str = Field(min_length=1)
    ezhuthu: list[str] = Field(min_length=1)
    length: int = Field(ge=1)
    wordClass: WordClass

    wordhood: dict[SignalName, float] | None = Field(default=None, min_length=1)
    attestedBy: list[SourceId] | None = Field(default=None, min_length=1)
    frequency: int = Field(ge=0)
    spokenRatio: float | None = Field(default=None, ge=0.0, le=1.0)
    freqRank: int | None = Field(default=None, ge=1)
    compound: bool | None = None

    definitionTa: str | None = Field(default=None, min_length=1)
    translationEn: str | None = Field(default=None, min_length=1)
    synonymsTa: list[str] | None = Field(default=None, min_length=1)
    meaningSource: ProvenanceState | None = None
    translationEnSource: SourceId | None = None

    pos: list[PartOfSpeech] | None = Field(default=None, min_length=1)
    categories: list[str] | None = Field(default=None, min_length=1)
    categorySource: ProvenanceState | None = None

    @model_validator(mode="after")
    def _ezhuthu_rejoins_to_the_word(self) -> Self:
        # Segmentation is non-destructive, so a row whose parts do not rebuild
        # its word is corrupt and must never reach a selector.
        if "".join(self.ezhuthu) != self.word:
            raise ValueError(f"ezhuthu does not rejoin to {self.word!r}")
        if self.length != len(self.ezhuthu):
            raise ValueError(
                f"length {self.length} != ezhuthu count {len(self.ezhuthu)} "
                f"for {self.word!r}"
            )
        return self

    @model_validator(mode="after")
    def _set_valued_columns_are_sorted_and_deduped(self) -> Self:
        # Every one of these resolves as a UNION across sources, so ordering is
        # not information. Fixing the order in the contract is what makes a
        # republish byte-comparable.
        if self.attestedBy is not None:
            _sorted_unique(self.attestedBy, "attestedBy", self.word)
        if self.pos is not None:
            _sorted_unique(list(self.pos), "pos", self.word)
        if self.synonymsTa is not None:
            _sorted_unique(self.synonymsTa, "synonymsTa", self.word)
        if self.categories is not None:
            _sorted_unique(self.categories, "categories", self.word)
        return self

    @model_validator(mode="after")
    def _provenance_accompanies_the_value_it_describes(self) -> Self:
        # A value whose provenance is unknown, or a provenance state describing
        # nothing, are both lies - and the second is worse, because a category
        # renders as a PAID hint and its state is what suppresses an unreviewed
        # one. The pairing is enforced rather than trusted.
        meaning = self.definitionTa is not None or self.synonymsTa is not None
        if meaning != (self.meaningSource is not None):
            raise ValueError(
                f"meaningSource must accompany definitionTa / synonymsTa exactly "
                f"for {self.word!r}"
            )
        if (self.translationEn is not None) != (self.translationEnSource is not None):
            raise ValueError(
                f"translationEnSource must accompany translationEn exactly for "
                f"{self.word!r}"
            )
        if (self.categories is not None) != (self.categorySource is not None):
            raise ValueError(
                f"categorySource must accompany categories exactly for {self.word!r}"
            )
        return self


class LexiconProvenance(BaseModel):
    """One source's contribution, and the exact bytes it contributed from.

    ``sha256`` + ``bytes`` identify the input, so a later run can prove it read
    the same file and CI can compare the declared set against the registry with
    no network and no raw bytes on disk.
    """

    model_config = ConfigDict(extra="forbid")

    id: SourceId
    name: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    path: RelPath
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=_SHA256)
    rowsIn: int = Field(ge=0)
    factsOut: int = Field(ge=0)


class LexiconCounters(BaseModel):
    """The per-class ledger: every published row lands under exactly one class.

    ``byClass`` carries a bucket for EVERY ``wordClass`` - a missing bucket and
    a zero bucket say different things, and only one of them is a measurement.
    """

    model_config = ConfigDict(extra="forbid")

    rows: int = Field(ge=0)
    byClass: dict[WordClass, _RowCount]

    @model_validator(mode="after")
    def _counters_reconcile(self) -> Self:
        missing = [name for name in _WORD_CLASSES if name not in self.byClass]
        if missing:
            raise ValueError(f"byClass is missing a bucket for {', '.join(missing)}")
        total = sum(self.byClass.values())
        if total != self.rows:
            raise ValueError(f"byClass sums to {total}, not rows {self.rows}")
        return self


class LexiconPartition(BaseModel):
    """One published NDJSON cell, and what it holds.

    The split keys - ``wordClass``, then ezhuthu ``length``, then the word's
    BASE first ezhuthu - are all immutable per word, so a refresh INSERTS into a
    cell and never reshuffles one. Only a changed ``wordClass`` moves a row, and
    that is a reviewable semantic event. ``firstEzhuthuHex`` renders the base
    ezhuthu as lowercase 4-digit hex so every path stays ASCII; this document is
    what maps the hex back to the ezhuthu it stands for.
    """

    model_config = ConfigDict(extra="forbid")

    path: RelPath
    wordClass: WordClass
    length: int | None = Field(default=None, ge=1)
    firstEzhuthuHex: str | None = Field(default=None, pattern=_HEX4)
    firstEzhuthu: str | None = Field(default=None, min_length=1, max_length=1)
    rows: int = Field(ge=0)
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=_SHA256)

    @model_validator(mode="after")
    def _split_keys_are_nested_and_self_describing(self) -> Self:
        if (self.firstEzhuthuHex is None) != (self.firstEzhuthu is None):
            raise ValueError(
                f"partition {self.path!r}: firstEzhuthuHex and firstEzhuthu are "
                f"set together or not at all"
            )
        if self.firstEzhuthuHex is not None and self.length is None:
            raise ValueError(
                f"partition {self.path!r}: an ezhuthu split only ever subdivides a "
                f"length split, so length must be set too"
            )
        if self.firstEzhuthu is not None:
            expected = f"{ord(self.firstEzhuthu):04x}"
            if self.firstEzhuthuHex != expected:
                raise ValueError(
                    f"partition {self.path!r}: firstEzhuthuHex "
                    f"{self.firstEzhuthuHex!r} != {expected!r} for "
                    f"{self.firstEzhuthu!r}"
                )
        return self


class Lexicon(SchemaModel):
    """The lexicon META document (``datasets/lexicon/lexicon.meta.json``).

    It carries no ``words`` list. The lexicon is streamed NDJSON with no
    in-memory row list, so the reconciliation reads ``counters.rows`` and the
    partition table's declared counts rather than ``len(words)`` - a document
    model holding every row could not be constructed at this size and would
    quietly re-introduce the materialization the publisher exists to avoid.
    """

    provenance: list[LexiconProvenance] = Field(min_length=1)
    counters: LexiconCounters
    partitions: list[LexiconPartition] = Field(min_length=1)
    rowSchema: LexiconEntry | None = None

    @model_validator(mode="after")
    def _provenance_ids_are_unique(self) -> Self:
        seen: set[str] = set()
        for source in self.provenance:
            if source.id in seen:
                raise ValueError(f"duplicate provenance id {source.id!r}")
            seen.add(source.id)
        return self

    @model_validator(mode="after")
    def _partitions_reconcile_with_the_counters(self) -> Self:
        # The integrity Oracle's second leg: the files on disk declare the same
        # population the class ledger does, class by class. A row lost between
        # the classifier and the writer cannot validate.
        seen: set[str] = set()
        declared: dict[str, int] = {}
        for cell in self.partitions:
            if cell.path in seen:
                raise ValueError(f"duplicate partition path {cell.path!r}")
            seen.add(cell.path)
            declared[cell.wordClass] = declared.get(cell.wordClass, 0) + cell.rows
        for name in _WORD_CLASSES:
            counted = self.counters.byClass.get(name, 0)
            if declared.get(name, 0) != counted:
                raise ValueError(
                    f"partitions declare {declared.get(name, 0)} {name} rows, "
                    f"counters.byClass says {counted}"
                )
        total = sum(cell.rows for cell in self.partitions)
        if total != self.counters.rows:
            raise ValueError(
                f"partitions declare {total} rows, counters.rows says "
                f"{self.counters.rows}"
            )
        return self
