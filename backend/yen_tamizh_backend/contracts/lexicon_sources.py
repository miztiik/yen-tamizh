"""The lexicon source registry contract (Row 3).

``config/lexicon-sources.json`` is the declarative registry every lexicon stage
reads. It is the whole extensibility story, inherited from the corpus registry
it supersedes: adding another Tamil source is a DATA change here plus a re-run,
never a code rewrite. Only an unseen source FORMAT costs code - a reader plus a
member of ``LexiconSourceKind``.

Three reader families cover every source in the inventory:

- ``delimited``  - one record per line (``delimiter``, ``hasHeader``,
  ``wordColumn``, ``countColumn``).
- ``json-array`` - a JSON document holding an array under ``rootKey``, read with
  ``JSONDecoder.raw_decode`` over a sliding buffer. ``elementKind`` says what
  one element IS.
- ``jsonl``      - one JSON object per line (``wordField`` and the other field
  mappings).

``elementKind`` is REQUIRED on ``json-array`` and forbidden everywhere else,
with no default. The reader's element rule is not "elements must be objects" -
it is that an element grammar must be SELF-TERMINATING, so that a proper prefix
of a complete element is never itself a complete element and a decode failure
therefore means "read more" rather than "silently wrong value". A JSON string
has that property in full (``raw_decode('"abc')`` raises), which is why the two
bare-string sources are admissible; a bare number does not, which is why no
third member exists. A DEFAULT would be exactly the silent assumption the rule
exists to prevent, so there is none.

Two things the corpus registry carried are deliberately absent: ``filters``,
because extraction never filters, and ``bands``, because rank-relative frequency
bands were replaced by an absolute floor.

See ``docs/architecture/contracts/schemas.md`` for the shape decisions and
``docs/concepts/lexicon.md`` for the vocabulary the aliases map into.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from yen_tamizh_backend.contracts.base import ChangelogEntry, SchemaModel
from yen_tamizh_backend.contracts.common import RelPath, SourceId
from yen_tamizh_backend.contracts.lexicon import PartOfSpeech

# The initial mint - see the note on ``LEXICON_VERSION``. The registry file that
# carries this stamp is written in the row that adds the readers.
LEXICON_SOURCES_VERSION = "2026-08-14"
LEXICON_SOURCES_CHANGELOG = (
    ChangelogEntry(
        version=LEXICON_SOURCES_VERSION,
        change=(
            "Initial lexicon source registry: per-source role, precedence, "
            "sha256 and reader mapping across the delimited / json-array / "
            "jsonl kinds, plus the POS and category alias maps."
        ),
        why=(
            "Row 3 - contracts before logic (Holy Law #3). elementKind lands in "
            "the initial mint rather than with the readers: two acquired "
            "sources hold bare string array elements, and reopening a contract "
            "three rows after it shipped is a Holy Law #3 inversion."
        ),
    ),
)

# What a source is allowed to assert. Only ``authority`` and ``authored`` can
# assert word-hood; ``formEvidence`` can only assert that a surface is NOT a
# headword; ``frequency`` and ``category`` assert neither.
SourceRole = Literal["authority", "formEvidence", "frequency", "category", "authored"]

LexiconSourceKind = Literal["delimited", "json-array", "jsonl"]

# The self-terminating element grammars: ``{`` and ``"``.
ElementKind = Literal["object", "string"]

OutputFormat = Literal["ndjson", "csv", "sqlite"]

# What a raw source tag may be EVIDENCE FOR. Narrower than ``WordClass`` on
# purpose: ``headword`` is word-hood, which only a role=authority / authored
# source's headword fact may assert (Row 4 decision 1), and ``unclassified`` is
# the classifier's non-verdict, which nothing can be evidence FOR. Both are
# reachable from ``config/lexicon-sources.json``, so a one-line config edit on
# the wider type would let a category source assert word-hood.
WordClassEvidence = Literal[
    "inflected",
    "colloquial",
    "properNoun",
    "loanword",
    "boundStem",
    "sandhiArtifact",
    "suspectedTypo",
]

# Why a raw source POS tag yields no ``pos`` fact. Never a silent drop: the tag
# is registered, the reason is named, and a tag with no entry at all is a hard
# failure at publish.
#
# ``notAWord``           - the source itself says the unit is not a word (a
#                          script character, a symbol), so extracting a headword
#                          fact from it would assert what the source denied.
# ``multiWordUnit``      - a proverb or a phrase attests the PHRASE, not the
#                          words inside it.
# ``noTamilCounterpart`` - an English-side label naming a category Tamil does
#                          not have in any form, so there is nothing to map onto
#                          and the Tamil side's part of speech is unknown.
# ``notAPosLabel``       - a value that RECURS in a structured POS field and
#                          names no part of speech, such as A7's
#                          romanization-class entry-type labels. A row carrying
#                          no POS prefix at all is NOT this: it is a counted
#                          parse reject at EXTRACT, where Row 5's Oracle already
#                          accounts for it (rows out == rows in - counted parse
#                          rejects). Fail fast at the boundary means extract,
#                          not publish three stages later, so parse junk is
#                          never enumerated into the registry.
PosRejection = Literal[
    "notAWord",
    "multiWordUnit",
    "noTamilCounterpart",
    "notAPosLabel",
]

_SHA256 = r"^[0-9a-f]{64}$"

_DELIMITED_ONLY = ("delimiter", "hasHeader", "wordColumn", "countColumn")
_ARRAY_ONLY = ("rootKey", "elementKind")
_FIELD_MAPPINGS = ("wordField", "countField", "categoryField", "posField")


class PosAlias(BaseModel):
    """Where one raw source POS tag lands.

    The census tags are not all parts of speech, so one destination is not
    enough. A tag routes to ``pos`` (it names a part of speech Tamil has), to
    ``wordClassEvidence`` (it is a fact about what KIND of surface this is - a
    proper name, a bound morpheme, a contracted form - which is the classifier's
    input, never its verdict), or it carries an explicit ``reject`` naming why
    it yields no part of speech. A tag may route to both of the first two: a
    plural-noun tag carries two facts and each goes to its own home.
    """

    model_config = ConfigDict(extra="forbid")

    pos: list[PartOfSpeech] | None = Field(default=None, min_length=1)
    wordClassEvidence: list[WordClassEvidence] | None = Field(
        default=None, min_length=1
    )
    reject: PosRejection | None = None
    note: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _tag_has_exactly_one_kind_of_destination(self) -> Self:
        routed = self.pos is not None or self.wordClassEvidence is not None
        if self.reject is not None and routed:
            raise ValueError(
                "a rejected tag cannot also route to pos / wordClassEvidence"
            )
        if self.reject is None and not routed:
            raise ValueError(
                "a tag must route to pos, to wordClassEvidence, or name a reject "
                "reason - a tag with no destination is the silent drop the "
                "registry exists to prevent"
            )
        if self.pos is not None and list(self.pos) != sorted(set(self.pos)):
            raise ValueError(f"pos must be sorted and deduped: {list(self.pos)}")
        evidence = self.wordClassEvidence
        if evidence is not None and list(evidence) != sorted(set(evidence)):
            raise ValueError(
                f"wordClassEvidence must be sorted and deduped: {list(evidence)}"
            )
        return self


class LexiconSource(BaseModel):
    """One registered source: where its bytes are, what it may assert, how to read it."""

    model_config = ConfigDict(extra="forbid")

    id: SourceId
    name: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    role: SourceRole
    kind: LexiconSourceKind
    path: RelPath
    bytes: int = Field(ge=0)
    sha256: str = Field(pattern=_SHA256)
    # An explicit integer rather than the array's order, so reordering the
    # registry for readability can never silently change a published value.
    precedence: int = Field(ge=0)
    enabled: bool = True
    note: str | None = Field(default=None, min_length=1)

    # kind == "delimited"
    delimiter: str | None = Field(default=None, min_length=1, max_length=1)
    hasHeader: bool = False
    wordColumn: int | None = Field(default=None, ge=0)
    countColumn: int | None = Field(default=None, ge=0)

    # kind == "json-array"
    rootKey: str | None = Field(default=None, min_length=1)
    elementKind: ElementKind | None = None

    # kind == "json-array" with elementKind "object", and kind == "jsonl"
    wordField: str | None = Field(default=None, min_length=1)
    countField: str | None = Field(default=None, min_length=1)
    categoryField: str | None = Field(default=None, min_length=1)
    posField: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _fields_match_the_kind(self) -> Self:
        # Fail fast at the boundary: a mapping set on the wrong kind would be
        # silently ignored, and a silently ignored knob is a lie in the config.
        if self.kind != "json-array" and self.elementKind is not None:
            raise ValueError(
                f"source {self.id!r}: elementKind describes a json-array element "
                f"and has no meaning for kind {self.kind!r}"
            )
        if self.kind == "delimited":
            if self.delimiter is None or self.wordColumn is None:
                raise ValueError(
                    f"source {self.id!r}: kind 'delimited' needs delimiter + wordColumn"
                )
            stray = self._set_among(_ARRAY_ONLY + _FIELD_MAPPINGS)
        elif self.kind == "jsonl":
            if self.wordField is None:
                raise ValueError(f"source {self.id!r}: kind 'jsonl' needs wordField")
            stray = self._set_among(_DELIMITED_ONLY + _ARRAY_ONLY)
        elif self.elementKind is None:
            raise ValueError(
                f"source {self.id!r}: kind 'json-array' needs an explicit "
                f"elementKind - a default would be the silent assumption the "
                f"self-terminating element rule exists to prevent"
            )
        elif self.elementKind == "object":
            if self.rootKey is None or self.wordField is None:
                raise ValueError(
                    f"source {self.id!r}: json-array of objects needs rootKey + wordField"
                )
            stray = self._set_among(_DELIMITED_ONLY)
        else:
            if self.rootKey is None:
                raise ValueError(
                    f"source {self.id!r}: json-array of strings needs rootKey"
                )
            # A bare string element has no fields at all, so every field mapping
            # is meaningless on it - not merely the three the decision listed.
            stray = self._set_among(_DELIMITED_ONLY + _FIELD_MAPPINGS)
        if self.kind != "delimited" and self.hasHeader:
            # hasHeader defaults to False, so only a True value is an assertion -
            # and on a JSON kind it is one nothing reads.
            stray.append("hasHeader")
        if stray:
            raise ValueError(
                f"source {self.id!r}: kind {self.kind!r} ignores {', '.join(stray)}"
            )
        return self

    def _set_among(self, names: tuple[str, ...]) -> list[str]:
        # hasHeader is checked separately: it carries a non-None default, so
        # "is not None" cannot tell an assertion from the default.
        return [
            name
            for name in names
            if name != "hasHeader" and getattr(self, name) is not None
        ]


class LexiconSources(SchemaModel):
    """The declarative lexicon source registry, read by every stage."""

    lexiconRoot: RelPath
    outputs: list[OutputFormat] = Field(min_length=1)
    # Every raw POS tag any source emits gets an entry. A tag with no entry is a
    # hard publish failure naming the tag and its row count - never dropped, and
    # never passed through, which would defeat the closed vocabulary.
    posAliases: dict[str, PosAlias] = Field(min_length=1)
    # Raw category label -> normalized theme, so "Birds" and "birds" collapse.
    categoryAliases: dict[str, str] = Field(default_factory=dict)
    sources: list[LexiconSource] = Field(min_length=1)

    @model_validator(mode="after")
    def _outputs_are_deduped(self) -> Self:
        if len(set(self.outputs)) != len(self.outputs):
            raise ValueError(f"duplicate output format in {list(self.outputs)}")
        return self

    @model_validator(mode="after")
    def _sources_are_uniquely_identified_and_ordered(self) -> Self:
        seen: set[str] = set()
        ranks: dict[int, str] = {}
        for source in self.sources:
            if source.id in seen:
                raise ValueError(f"duplicate source id {source.id!r}")
            seen.add(source.id)
            # Precedence must be a TOTAL order, or the source that wins a
            # single-slot value (the English translation) is decided by array
            # position after all - the thing the explicit integer exists to stop.
            if source.precedence in ranks:
                raise ValueError(
                    f"sources {ranks[source.precedence]!r} and {source.id!r} share "
                    f"precedence {source.precedence}"
                )
            ranks[source.precedence] = source.id
        return self
