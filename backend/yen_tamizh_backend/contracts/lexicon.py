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
enforced by the model, and it carries TWO families: ``classified`` is a census
of the WHOLE population the store holds, and ``published`` is what the committed
files carry. That pair is what proves the artifact's thesis - a class the
publish policy withholds is still counted in the repository at its real size, so
"nothing was discarded, only unpublished" is a checkable statement.
"""

from __future__ import annotations

from typing import Annotated, Final, Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yen_tamizh_backend.contracts.base import ChangelogEntry, SchemaModel
from yen_tamizh_backend.contracts.common import RelPath, SourceId
from yen_tamizh_backend.ezhuthu import EzhuthuKind, segment

# The address of a published file, declared IN the artifact so a consumer learns
# it from the document rather than from the code that wrote it. Both keys are
# immutable per word - the class is the classifier's verdict and the base
# ezhuthu is the word's own opening consonant or vowel - so a refresh INSERTS a
# line into a file that already exists, and only a changed verdict moves a row
# between them.
PARTITION_KEYS: Final[tuple[str, ...]] = ("wordClass", "baseEzhuthu")

# The initial mint. The lexicon has no writer yet, so the date-stamp and its
# first changelog entry live here rather than in a data file: two writers of one
# schema picking their own dates is exactly the drift section 11 exists to stop.
# Migration class is build-time rewrite-in-place - a later change appends an
# entry and moves the stamp, and needs no read-side migration, because the only
# reader is the backend and every artifact regenerates in the same commit.
LEXICON_VERSION = "2026-08-17"
LEXICON_CHANGELOG = (
    ChangelogEntry(
        version=LEXICON_VERSION,
        change=(
            "definitionTa became a LIST of senses; the row serializes in an "
            "explicit human-first field order instead of sorted keys; the "
            "second partition key became baseEzhuthu, one file per BASE "
            "letter, so a partition key is always four hex digits."
        ),
        why=(
            "Row 12a. A Tamil Wiktionary page carries every sense of its word "
            "under one meaning block and the resolver kept the first, so the "
            "row for vaakai published the tree and dropped the garland and the "
            "victory - while its own translationEn described the two it "
            "dropped. A single display slot is still what a hint spends, and "
            "it is element zero, so nothing about what a player sees changes "
            "and no sense is discarded. The order is the reader's: a row now "
            "opens on the word and its meaning and closes on the counts a gate "
            "reads, and it is the CONTRACT's field order rather than a sort, "
            "so the bytes stay reproducible. One file per FULL ezhuthu split "
            "one letter across up to thirteen files, which is 115 files for "
            "the headword class and no reader wanting ka without kaa; the base "
            "letter is the unit a person looks a word up under."
        ),
    ),
    ChangelogEntry(
        version="2026-08-16T23:00",
        change=(
            "Split counters into a classified and a published census; made "
            "firstEzhuthu the second and final partition key and dropped "
            "length from the partition table; added partitionKeys and "
            "ezhuthuIndex; cut the row to word, wordClass, length, frequency, "
            "attestations, tier1Attestations, spokenRatio, translationEn, "
            "definitionTa, synonymsTa, pos and categories; renamed provenance "
            "rowsIn / factsOut to observations / facts."
        ),
        why=(
            "Row 11, the first writer. The publish policy commits four servable "
            "classes of ten, so a single counter would have made the withheld "
            "classes unprovable - classified counts the whole population and "
            "published counts the files, and publication is all-or-nothing per "
            "class, so a partial count is rows lost rather than rows withheld. "
            "The address is one file per (wordClass, first ezhuthu), so the "
            "length key it was authored with addresses nothing and a partition "
            "key that is sometimes absent is worse than one that is always "
            "there. The row carries what a consumer reads and nothing else: "
            "attestedBy became the count row 12 actually gates on, the three "
            "provenance stamps and compound had no reader, and ezhuthu is "
            "segment(word) - a stored copy of a derived value is a drift "
            "surface as well as 66.5 B a row. observations / facts are what "
            "the store can prove about a source; no stage keeps a raw row "
            "count, so rowsIn could only ever have been one of them misnamed."
        ),
    ),
    ChangelogEntry(
        version="2026-08-16",
        change="Added notAWord to the WordClass vocabulary.",
        why=(
            "Row 9a - the classifier had no verdict for a surface that is not a "
            "word at all, so 641,819 scrape artifacts wore real classes: "
            "repeated aytham as loanword, leading-dot strings as inflected, a "
            "1,212-ezhuthu paragraph as suspectedTypo. notAWord is a CONFIDENT "
            "NEGATIVE and is deliberately distinct from unclassified, which is "
            "an ABSENT verdict - collapsing them would destroy the only "
            "counters that say whether the classifier works. Additive: every "
            "existing row still validates, and selection stays an allow-list "
            "so nothing reaches a player by omission."
        ),
    ),
    ChangelogEntry(
        version="2026-08-14",
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
#
# ``notAWord`` and ``unclassified`` are the two ends of the same axis and are
# kept apart on purpose. ``notAWord`` is a CONFIDENT NEGATIVE - the shape pass
# looked at the string and ruled it is not a Tamil word at all - while
# ``unclassified`` is an ABSENT verdict, the enrichment queue, where a later
# pass may still find a real word. Collapsing them would hide both the size of
# the junk the corpus carries and the size of the work left to do.
WordClass = Literal[
    "headword",
    "inflected",
    "colloquial",
    "properNoun",
    "loanword",
    "boundStem",
    "sandhiArtifact",
    "suspectedTypo",
    "notAWord",
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

# A partition key is the code point of ONE BASE ezhuthu - the uyir, the
# consonant or the aytham a word opens on - as lowercase 4-digit hex. Always
# four digits, because a base character is always one code point: a vowel sign
# or a pulli is a combining mark that attaches to it, and a word does not change
# what CONSONANT it starts with when it changes which vowel rides on it. The
# fixed width is what makes ASCII filename order equal code-point order, so a
# directory listing is the row order.
_EZHUTHU_HEX = r"^[0-9a-f]{4}$"

_RowCount = Annotated[int, Field(ge=0)]

_WORD_CLASSES: tuple[WordClass, ...] = get_args(WordClass)


def _sorted_unique(values: list[str], field: str, word: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"{field} holds duplicates for {word!r}: {values}")
    if list(values) != sorted(values):
        raise ValueError(f"{field} must be sorted for {word!r}: {values}")


class LexiconEntry(BaseModel):
    """One lexicon row: what a consumer of the lexicon reads about one surface.

    Not a ``SchemaModel`` - see the module docstring.

    Every sparse column is OPTIONAL and never a defaulted empty list.
    ``model_dump(exclude_none=True)`` drops ``None`` but keeps ``[]``, so a
    defaulted empty list would write an empty pair on every row that lacks the
    fact.

    The row carries facts and counts, not provenance. ``attestedBy`` was a list
    of source slugs on every row and what selection actually gates on is the
    COUNT, so it is published as one; the three ``*Source`` stamps and
    ``compound`` had no reader at all. ``wordhood`` and ``freqRank`` are gone on
    the same principle they were always going to be omitted under - a derived
    diagnostic whose verdict (``wordClass``) or whose input (``frequency``) is
    itself published. ``ezhuthu`` is ``segment(word)``, a pure function of a
    published column, so storing it would mint a drift surface as well as spend
    bytes; ``length`` stays because selection reads it, and it is checked
    against the live segmentation on every row.

    THE FIELD ORDER IS THE SERIALIZED ORDER, and that is why it is worth
    reading. ``model_dump`` returns fields in declaration order, so the writer
    dumps this dict as it stands rather than sorting the keys - which is just as
    deterministic and puts the row in the order a person reads it: the word,
    what it MEANS, then the machine columns a selection gate gets its answer
    from. Sorted keys opened every row on ``attestations`` and buried ``word``
    eight fields in.
    """

    model_config = ConfigDict(extra="forbid")

    word: str = Field(min_length=1)

    # Every sense the inventory holds, most authoritative source first and that
    # source's own sense order within it. A LIST because a Tamil word has more
    # than one meaning and a dictionary page says so: one display slot is still
    # one display slot - it is element zero, which is exactly the value the
    # single-slot precedence rule used to publish - but the senses that slot
    # does not show are no longer thrown away at the last stage of the pipeline.
    definitionTa: list[str] | None = Field(default=None, min_length=1)
    translationEn: str | None = Field(default=None, min_length=1)
    synonymsTa: list[str] | None = Field(default=None, min_length=1)

    pos: list[PartOfSpeech] | None = Field(default=None, min_length=1)
    categories: list[str] | None = Field(default=None, min_length=1)

    frequency: int = Field(ge=0)
    length: int = Field(ge=1)
    wordClass: WordClass
    # How many sources allowed to assert word-hood said this surface is a word,
    # and how many of those were lexicographic rather than a bare listing. Two
    # integers rather than one integer plus a flag: a boolean costs the same
    # bytes on the line and says strictly less, and the pair lets a selection
    # gate on breadth and on quality without re-reading the store.
    attestations: int = Field(ge=0)
    tier1Attestations: int = Field(ge=0)
    spokenRatio: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _length_is_the_word_own_ezhuthu_count(self) -> Self:
        # Segmentation is non-destructive and total, so a row whose declared
        # length disagrees with its word's own is corrupt and must never reach a
        # selector. Recomputing rather than trusting a stored list is what lets
        # the ezhuthu column go without the check going with it.
        counted = len(segment(self.word))
        if self.length != counted:
            raise ValueError(
                f"length {self.length} != ezhuthu count {counted} for {self.word!r}"
            )
        return self

    @model_validator(mode="after")
    def _tier_one_attestations_are_a_subset(self) -> Self:
        if self.tier1Attestations > self.attestations:
            raise ValueError(
                f"tier1Attestations {self.tier1Attestations} exceeds attestations "
                f"{self.attestations} for {self.word!r}"
            )
        return self

    @model_validator(mode="after")
    def _set_valued_columns_are_sorted_and_deduped(self) -> Self:
        # Every one of these resolves as a UNION across sources, so ordering is
        # not information. Fixing the order in the contract is what makes a
        # republish byte-comparable.
        if self.pos is not None:
            _sorted_unique(list(self.pos), "pos", self.word)
        if self.synonymsTa is not None:
            _sorted_unique(self.synonymsTa, "synonymsTa", self.word)
        if self.categories is not None:
            _sorted_unique(self.categories, "categories", self.word)
        return self

    @model_validator(mode="after")
    def _the_senses_are_ordered_and_distinct(self) -> Self:
        # Deliberately NOT sorted. Order IS information here: element zero is
        # the sense the single display slot shows, and it is chosen by the same
        # precedence rule that used to choose the only sense - most
        # authoritative source first, that source's own sense order within it.
        # Sorting would put whichever sense happens to start with the earliest
        # code point in front of a player.
        if self.definitionTa is not None and len(set(self.definitionTa)) != len(
            self.definitionTa
        ):
            raise ValueError(
                f"definitionTa repeats a sense for {self.word!r}: "
                f"{self.definitionTa}"
            )
        return self


class LexiconProvenance(BaseModel):
    """One source's contribution, and the exact bytes it contributed from.

    ``sha256`` + ``bytes`` identify the input, so a later run can prove it read
    the same file and CI can compare the declared set against the registry with
    no network and no raw bytes on disk.

    ``observations`` and ``facts`` are what the STORE can prove about the
    source - the surfaces it contributed and the typed assertions it made. They
    are named for what they are: no stage retains a raw input row count once the
    extract is written, so a field called ``rowsIn`` could only ever have been
    filled with one of these two wearing the wrong name.
    """

    model_config = ConfigDict(extra="forbid")

    id: SourceId
    name: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    path: RelPath
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=_SHA256)
    observations: int = Field(ge=0)
    facts: int = Field(ge=0)


class LexiconCensus(BaseModel):
    """A per-class ledger: every counted row lands under exactly one class.

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


class LexiconCounters(BaseModel):
    """The two censuses, and the rule that binds them.

    ``classified`` counts the WHOLE population the store holds, class by class,
    including every class the publish policy withholds. ``published`` counts
    what the committed files carry. Committing both is what makes "nothing was
    discarded" a checkable statement rather than a claim: a withheld class is
    still on the record here, at its real size, in the repository.

    Publication is ALL-OR-NOTHING per class, and that is the rule the model
    enforces. A class is published whole or not at all, so a published count
    that is neither zero nor the classified count means rows went missing
    between the classifier and the writer - the one failure a per-class policy
    would otherwise hide.
    """

    model_config = ConfigDict(extra="forbid")

    classified: LexiconCensus
    published: LexiconCensus

    @model_validator(mode="after")
    def _publication_is_all_or_nothing_per_class(self) -> Self:
        for name in _WORD_CLASSES:
            published = self.published.byClass[name]
            classified = self.classified.byClass[name]
            if published not in (0, classified):
                raise ValueError(
                    f"{name}: {published} published of {classified} classified - "
                    f"a class is published whole or withheld whole, so a partial "
                    f"count is rows lost rather than rows withheld"
                )
        return self


class EzhuthuIndexEntry(BaseModel):
    """What one partition's hex key stands for, spelled out for a human.

    This is where the Tamil letter and its ASCII spelling live: as correctable
    DATA in a document a reviewer already opens, never as a path component. A
    code point is fixed by an external standard, so it can carry an address; a
    romanization is a judgement call, and correcting one must not rename a
    published file.

    ``ezhuthu`` is a BASE letter - the uyir, the consonant or the aytham a word
    opens on, one code point. It is deliberately not the whole opening ezhuthu:
    a vowel sign rides on the consonant and does not change which letter the
    word is filed under, exactly as a dictionary files ka, kaa and ki together.
    ``kind`` classifies that base letter, so a bare consonant reads ``uyirmei``
    (the inherent /a/).
    """

    model_config = ConfigDict(extra="forbid")

    ezhuthu: str = Field(min_length=1, max_length=1)
    roman: str = Field(min_length=1, pattern=r"^[A-Za-z]+$")
    kind: EzhuthuKind

    @model_validator(mode="after")
    def _the_value_is_exactly_one_base_letter(self) -> Self:
        # A base letter is one code point by construction, so the length bound
        # above is the whole shape check. What is left to prove is that the code
        # point is a letter rather than a combining mark that happened to lead a
        # string: a mark segments as its own unit, and a file addressed by one
        # would decode to something no reader could pronounce.
        units = segment(self.ezhuthu)
        if units != [self.ezhuthu]:
            raise ValueError(
                f"ezhuthu {self.ezhuthu!r} is {len(units)} ezhuthu, not one"
            )
        return self


class LexiconPartition(BaseModel):
    """One published NDJSON file, and what it holds.

    Addressed by ``wordClass`` then ``baseEzhuthu`` - the code point of the
    letter the word opens on, as lowercase 4-digit hex. Both keys are immutable
    per word, so a refresh INSERTS into a file and never reshuffles one; only a
    changed ``wordClass`` moves a row, and that is a reviewable semantic event.
    Hex keeps every path ASCII; ``ezhuthuIndex`` on the meta document is what
    maps it back to the letter.
    """

    model_config = ConfigDict(extra="forbid")

    path: RelPath
    wordClass: WordClass
    baseEzhuthu: str = Field(pattern=_EZHUTHU_HEX)
    rows: int = Field(ge=0)
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=_SHA256)


class Lexicon(SchemaModel):
    """The lexicon META document (``datasets/lexicon/lexicon.meta.json``).

    It carries no ``words`` list. The lexicon is streamed NDJSON with no
    in-memory row list, so the reconciliation reads ``counters.published.rows``
    and the partition table's declared counts rather than ``len(words)`` - a
    document model holding every row could not be constructed at this size and
    would quietly re-introduce the materialization the publisher exists to
    avoid.
    """

    partitionKeys: list[str] = Field(min_length=1)
    provenance: list[LexiconProvenance] = Field(min_length=1)
    counters: LexiconCounters
    partitions: list[LexiconPartition] = Field(min_length=1)
    ezhuthuIndex: dict[str, EzhuthuIndexEntry] = Field(min_length=1)
    rowSchema: LexiconEntry | None = None

    @model_validator(mode="after")
    def _the_declared_address_is_the_one_the_partitions_use(self) -> Self:
        if tuple(self.partitionKeys) != PARTITION_KEYS:
            raise ValueError(
                f"partitionKeys {self.partitionKeys} is not the address this "
                f"contract defines, {list(PARTITION_KEYS)} - a declared address "
                f"nothing enforces is a comment wearing a field's clothes"
            )
        return self

    @model_validator(mode="after")
    def _provenance_ids_are_unique(self) -> Self:
        seen: set[str] = set()
        for source in self.provenance:
            if source.id in seen:
                raise ValueError(f"duplicate provenance id {source.id!r}")
            seen.add(source.id)
        return self

    @model_validator(mode="after")
    def _every_partition_key_decodes_through_the_index(self) -> Self:
        # No probe-and-fallback and no globbing: a reader resolves a file from
        # this table alone, so a hex it cannot decode - or an index entry no
        # file uses - is a document that describes something other than itself.
        for hex_key, entry in self.ezhuthuIndex.items():
            expected = "".join(f"{ord(point):04x}" for point in entry.ezhuthu)
            if hex_key != expected:
                raise ValueError(
                    f"ezhuthuIndex key {hex_key!r} != {expected!r} for "
                    f"{entry.ezhuthu!r}"
                )
        used = {cell.baseEzhuthu for cell in self.partitions}
        undeclared = sorted(used - set(self.ezhuthuIndex))
        if undeclared:
            raise ValueError(
                f"partitions use {', '.join(undeclared)} with no ezhuthuIndex entry"
            )
        unused = sorted(set(self.ezhuthuIndex) - used)
        if unused:
            raise ValueError(f"ezhuthuIndex declares unused {', '.join(unused)}")
        return self

    @model_validator(mode="after")
    def _partitions_reconcile_with_the_counters(self) -> Self:
        # The integrity Oracle's second leg: the files on disk declare the same
        # population the published ledger does, class by class. A row lost
        # between the classifier and the writer cannot validate.
        seen: set[str] = set()
        declared: dict[str, int] = {}
        for cell in self.partitions:
            if cell.path in seen:
                raise ValueError(f"duplicate partition path {cell.path!r}")
            seen.add(cell.path)
            declared[cell.wordClass] = declared.get(cell.wordClass, 0) + cell.rows
        for name in _WORD_CLASSES:
            counted = self.counters.published.byClass.get(name, 0)
            if declared.get(name, 0) != counted:
                raise ValueError(
                    f"partitions declare {declared.get(name, 0)} {name} rows, "
                    f"counters.published.byClass says {counted}"
                )
        total = sum(cell.rows for cell in self.partitions)
        if total != self.counters.published.rows:
            raise ValueError(
                f"partitions declare {total} rows, counters.published.rows says "
                f"{self.counters.published.rows}"
            )
        return self
