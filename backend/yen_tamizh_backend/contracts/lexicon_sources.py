"""The lexicon source registry contract (Row 3).

``config/lexicon-sources.json`` is the declarative registry every lexicon stage
reads. It is the whole extensibility story, inherited from the corpus registry
it supersedes: adding another Tamil source is a DATA change here plus a re-run,
never a code rewrite. Only an unseen source FORMAT costs code - a reader plus a
member of ``LexiconSourceKind``.

Five reader families cover every source in the inventory:

- ``delimited``     - one record per line (``delimiter``, ``hasHeader``,
  ``wordColumn``, ``countColumn``).
- ``delimited-quoted`` - the same four knobs, but the record is an RFC-4180
  FIELD sequence rather than a split line: a field may be quoted, and a quoted
  field may hold the delimiter, a quote, or a newline. It is a separate kind
  rather than a flag on ``delimited`` because the two disagree on real bytes -
  a tab inside a quoted field is one field to this reader and two to the other -
  and a knob that silently re-reads twelve already-staged sources is not a knob.
- ``json-array``    - a JSON document holding an array, read with
  ``JSONDecoder.raw_decode`` over a sliding buffer. ``rootKey`` names the key the
  array hangs under, and is ABSENT when the document ROOT is the array itself.
  ``elementKind`` says what one element IS.
- ``jsonl``         - one JSON object per line (``wordField`` and the other
  field mappings).
- ``mediawiki-xml`` - a MediaWiki export, one record per ``<page>`` in the
  namespace ``pageNamespace`` names. The record is the page, so no field mapping
  applies: the reader knows the export's own element names.

``rootKey`` is optional rather than required because a real acquired source has
no key: ``en-ta-dictionary`` is 56,856 elements inside a bare top-level ``[``.
An absent ``rootKey`` therefore MEANS "the document root is the array", which the
reader verifies against the bytes and fails loudly on - it is a claim about the
document, not a fallback.

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
LEXICON_SOURCES_VERSION = "2026-08-16T22:00"
LEXICON_SOURCES_CHANGELOG = (
    ChangelogEntry(
        version=LEXICON_SOURCES_VERSION,
        change=(
            "Added the delimited-quoted reader kind, and added notAWord to "
            "WordClassEvidence."
        ),
        why=(
            "Row 9b - IndoWordNet's linked release is a tab-separated file "
            "whose glosses are RFC-4180 quoted and hold embedded newlines, "
            "which the line-splitting delimited reader cannot see; and a "
            "source POS tag routed to reject notAWord is a source DENYING "
            "word-hood, which is evidence the classifier has to be able to "
            "read. notAWord is admissible on this deliberately narrow type "
            "because it is a NEGATIVE: the exclusion of headword exists so a "
            "config edit cannot let a weak source assert word-hood, and a "
            "denial asserts none."
        ),
    ),
    ChangelogEntry(
        version="2026-08-16T18:00",
        change=(
            "Added the mediawiki-xml reader kind and its pageNamespace knob, "
            "required on that kind and forbidden on every other."
        ),
        why=(
            "Row 4b - the Tamil Wiktionary CONTENT dump is a MediaWiki export, "
            "a format none of the three existing readers can stream. Which "
            "namespace holds the records is a property of the export rather "
            "than of the format (a dump interleaves articles with talk, "
            "template and project pages), so it is declared per source like "
            "hasHeader rather than assumed in the reader."
        ),
    ),
    ChangelogEntry(
        version="2026-08-16",
        change=(
            "Added attestationTier, required on every source whose role may "
            "assert word-hood and forbidden on every other."
        ),
        why=(
            "Row 9a - whether a source's UNIT is a lexicographic ENTRY or a "
            "bare listing is a property of the SOURCE, and the classifier's "
            "headword gate needs it per source rather than re-derived per row. "
            "It is a declared field rather than a Python literal or a hardcoded "
            "id list (Holy Law #6) so registering the next authority forces the "
            "ruling instead of silently inheriting one."
        ),
    ),
    ChangelogEntry(
        version="2026-08-14",
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

# The two roles that sentence names, stated once so the pipeline joins on the
# same tuple the registry validates against. A frequency list observing a
# surface a million times still cannot say it is a word.
ATTESTING_ROLES: tuple[SourceRole, ...] = ("authority", "authored")

# What a source's UNIT is, and so what its headword assertion is WORTH.
#
# ``lexicographic`` - the unit is an ENTRY. Somebody decided the string is a
#                     word and then said something about it - a gloss, a
#                     definition, a part of speech, a synonym, a theme. The
#                     bytes carry that description.
# ``enumerative``   - the unit is a bare string in a list. The source vouches
#                     that the string belongs in the list and says nothing
#                     else about it.
#
# The tier is a property of the SOURCE rather than of the row, which is the
# whole reason it is declared here: what a source's unit IS cannot be recovered
# from a single row of it, and a row-level test asks the wrong question - the
# largest lexicographic source describes only part of what it lists, and
# demoting the rest of its entries because one COLUMN was unusable is exactly
# the defect Row 9a exists to fix. It is the same split Row 12 decision 14
# draws over the attestation composition, asked one stage earlier.
AttestationTier = Literal["lexicographic", "enumerative"]

LexiconSourceKind = Literal[
    "delimited", "delimited-quoted", "json-array", "jsonl", "mediawiki-xml"
]

# The kinds whose knobs are the delimited four. Stated once, because every
# branch that asks "is this a delimited file" has to agree with every other.
DELIMITED_KINDS: tuple[LexiconSourceKind, ...] = ("delimited", "delimited-quoted")

# The self-terminating element grammars: ``{`` and ``"``.
ElementKind = Literal["object", "string"]

OutputFormat = Literal["ndjson", "csv", "sqlite"]

# What a raw source tag may be EVIDENCE FOR. Narrower than ``WordClass`` on
# purpose: ``headword`` is word-hood, which only a role=authority / authored
# source's headword fact may assert (Row 4 decision 1), and ``unclassified`` is
# the classifier's non-verdict, which nothing can be evidence FOR. Both are
# reachable from ``config/lexicon-sources.json``, so a one-line config edit on
# the wider type would let a category source assert word-hood.
#
# ``notAWord`` IS admissible here, and the asymmetry is the point. What the
# exclusions above protect is the POSITIVE claim: no config edit may let a weak
# source say "this is a word". A denial is the opposite claim, and it costs
# nothing to be wrong in the direction of not serving something. It reaches the
# store from the one place a source can state it - a POS tag the registry routes
# to ``reject: notAWord``, which is a lexicographer saying the unit is a script
# character or a symbol rather than a word (Row 9b).
WordClassEvidence = Literal[
    "inflected",
    "colloquial",
    "properNoun",
    "loanword",
    "boundStem",
    "sandhiArtifact",
    "suspectedTypo",
    "notAWord",
]

# Why a raw source POS tag yields no ``pos`` fact. Never a silent drop: the tag
# is registered, the reason is named, and a tag with no entry at all is a hard
# failure at publish.
#
# ``notAWord``           - the source itself says the unit is not a word (a
#                          script character, a symbol), so extracting a headword
#                          fact from it would assert what the source denied.
#                          Since Row 9b the denial is not merely withheld POS:
#                          it is emitted as ``wordClassEvidence: notAWord`` so
#                          the classifier can weigh it, because a source saying
#                          "this is a letter, not a word" is the strongest
#                          statement anyone in the inventory makes about a bare
#                          single ezhuthu.
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
_MEDIAWIKI_ONLY = ("pageNamespace",)


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
    # Required exactly where it is READ - on the roles that may assert
    # word-hood - and forbidden everywhere else, on the same rule elementKind
    # follows: a field set on a source nothing consults is a knob that reads as
    # a claim and changes nothing.
    attestationTier: AttestationTier | None = None
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

    # kind == "json-array". An absent rootKey asserts that the document ROOT is
    # the array; the reader checks that against the bytes and raises when it is
    # not, so the absence is a claim rather than a guess.
    rootKey: str | None = Field(default=None, min_length=1)
    elementKind: ElementKind | None = None

    # kind == "json-array" with elementKind "object", and kind == "jsonl"
    wordField: str | None = Field(default=None, min_length=1)
    countField: str | None = Field(default=None, min_length=1)
    categoryField: str | None = Field(default=None, min_length=1)
    posField: str | None = Field(default=None, min_length=1)

    # kind == "mediawiki-xml". Which MediaWiki namespace holds this source's
    # records; every other page in the export is not a record of it, on the same
    # rule hasHeader states for a delimited file's first line. There is no
    # default, because "0" would be a guess about somebody else's export.
    pageNamespace: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _the_tier_is_declared_exactly_where_it_is_read(self) -> Self:
        # The headword gate reads the tier off the source that asserted the
        # headword fact, so an attesting source without one would silently
        # never make an entry - the "column of zeros wearing a name" failure,
        # arrived at through an omission rather than a typo.
        attesting = self.role in ATTESTING_ROLES
        if attesting and self.attestationTier is None:
            raise ValueError(
                f"source {self.id!r}: role {self.role!r} may assert word-hood, so "
                f"it must declare whether its unit is a lexicographic entry or "
                f"a bare listing"
            )
        if not attesting and self.attestationTier is not None:
            raise ValueError(
                f"source {self.id!r}: role {self.role!r} cannot assert word-hood, "
                f"so an attestationTier on it is a claim nothing reads"
            )
        return self

    @model_validator(mode="after")
    def _fields_match_the_kind(self) -> Self:
        # Fail fast at the boundary: a mapping set on the wrong kind would be
        # silently ignored, and a silently ignored knob is a lie in the config.
        if self.kind != "json-array" and self.elementKind is not None:
            raise ValueError(
                f"source {self.id!r}: elementKind describes a json-array element "
                f"and has no meaning for kind {self.kind!r}"
            )
        if self.kind in DELIMITED_KINDS:
            if self.delimiter is None or self.wordColumn is None:
                raise ValueError(
                    f"source {self.id!r}: kind {self.kind!r} needs delimiter + wordColumn"
                )
            stray = self._set_among(_ARRAY_ONLY + _FIELD_MAPPINGS + _MEDIAWIKI_ONLY)
        elif self.kind == "jsonl":
            if self.wordField is None:
                raise ValueError(f"source {self.id!r}: kind 'jsonl' needs wordField")
            stray = self._set_among(_DELIMITED_ONLY + _ARRAY_ONLY + _MEDIAWIKI_ONLY)
        elif self.kind == "mediawiki-xml":
            if self.pageNamespace is None:
                raise ValueError(
                    f"source {self.id!r}: kind 'mediawiki-xml' needs pageNamespace - "
                    f"an export interleaves articles with talk, template and "
                    f"project pages, and which of them are records is a fact "
                    f"about the export rather than about the format"
                )
            # The record IS the page, so every field mapping is meaningless on
            # it: the reader knows the export's own element names.
            stray = self._set_among(_DELIMITED_ONLY + _ARRAY_ONLY + _FIELD_MAPPINGS)
        elif self.elementKind is None:
            raise ValueError(
                f"source {self.id!r}: kind 'json-array' needs an explicit "
                f"elementKind - a default would be the silent assumption the "
                f"self-terminating element rule exists to prevent"
            )
        elif self.elementKind == "object":
            if self.wordField is None:
                raise ValueError(
                    f"source {self.id!r}: json-array of objects needs wordField"
                )
            stray = self._set_among(_DELIMITED_ONLY + _MEDIAWIKI_ONLY)
        else:
            # A bare string element has no fields at all, so every field mapping
            # is meaningless on it - not merely the three the decision listed.
            stray = self._set_among(
                _DELIMITED_ONLY + _FIELD_MAPPINGS + _MEDIAWIKI_ONLY
            )
        if self.kind not in DELIMITED_KINDS and self.hasHeader:
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
