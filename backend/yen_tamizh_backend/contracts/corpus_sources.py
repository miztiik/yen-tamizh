"""The corpus source registry contract (Row 8).

`config/corpus-sources.json` is the declarative registry the corpus ingest
reads. It is the whole extensibility story: adding another Tamil word source is
a DATA change here plus a re-run of the ingest - never a code rewrite, and never
a change to a Game or to the puzzle engine, which sit two layers away (corpus ->
derived per-Game sets (Row 9) -> daily puzzle engine (Row 13)).

Two reader kinds cover every source currently on disk:

- ``delimited``  - one record per line, e.g. ``word,count`` or ``word count``
  (``delimiter``, ``hasHeader``, ``wordColumn``, ``countColumn``).
- ``json-array`` - a JSON document holding an array of records under
  ``rootKey`` (``wordField``, ``countField``, ``categoryField``).

A source whose format matches neither is the ONE case that needs code: add a
reader to ``corpus/ingest.py`` and a member to ``SourceKind`` here.
"""

from __future__ import annotations

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from yen_tamizh_backend.contracts.base import SchemaModel

# A stable source identifier slug, matching the guardrails identifier discipline
# used by the core contracts: "wiki", "ta-dedup", "opensubtitles-ta".
SourceId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]*$")]

# A repo-relative POSIX path (CLAUDE.md section 2: no absolute paths, no drive
# letters, no backslashes in anything that leaves the process). The leading
# character class excludes "/" so an absolute path cannot match, and ":" is
# absent throughout so "C:/x" cannot match either.
RelPath = Annotated[
    str, StringConstraints(pattern=r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._+-]+)*$")
]

SourceKind = Literal["delimited", "json-array"]

_DELIMITED_ONLY = ("delimiter", "hasHeader", "wordColumn", "countColumn")
_JSON_ONLY = ("rootKey", "wordField", "countField", "categoryField")


class CorpusFilters(BaseModel):
    """What the ingest keeps. Every knob is tunable data (Holy Law #6).

    ``minLength`` / ``maxLength`` count EZHUTHU (Tamil grapheme clusters), not
    code points - the same unit every Game plays in (Row 6).
    ``dropCategories`` suppresses source category tags that carry no signal.
    ``maxWords`` caps the committed artifact; ``null`` means uncapped.
    """

    model_config = ConfigDict(extra="forbid")

    minLength: int = Field(ge=1)
    maxLength: int = Field(ge=1)
    minTotalFrequency: int = Field(ge=0)
    maxWords: int | None = Field(default=None, ge=1)
    dropCategories: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _length_range_is_ordered(self) -> Self:
        if self.minLength > self.maxLength:
            raise ValueError(
                f"minLength {self.minLength} must be <= maxLength {self.maxLength}"
            )
        return self


class CorpusBands(BaseModel):
    """Where the ``freqBand`` cuts fall, as fractions of the ranked list.

    A word's band is decided by its rank percentile, not by a raw count, so the
    bands stay meaningful when a new source shifts every absolute frequency.
    """

    model_config = ConfigDict(extra="forbid")

    commonMaxPercentile: float = Field(gt=0.0, lt=1.0)
    midMaxPercentile: float = Field(gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _cuts_are_ordered(self) -> Self:
        if self.commonMaxPercentile >= self.midMaxPercentile:
            raise ValueError(
                f"commonMaxPercentile {self.commonMaxPercentile} must be < "
                f"midMaxPercentile {self.midMaxPercentile}"
            )
        return self


class CorpusSource(BaseModel):
    """One registered word source: where its bytes are and how to read them."""

    model_config = ConfigDict(extra="forbid")

    id: SourceId
    name: str = Field(min_length=1)
    origin: str = Field(min_length=1)
    kind: SourceKind
    path: RelPath
    enabled: bool = True
    note: str | None = None

    # kind == "delimited"
    delimiter: str | None = Field(default=None, min_length=1, max_length=1)
    hasHeader: bool = False
    wordColumn: int | None = Field(default=None, ge=0)
    countColumn: int | None = Field(default=None, ge=0)

    # kind == "json-array"
    rootKey: str | None = Field(default=None, min_length=1)
    wordField: str | None = Field(default=None, min_length=1)
    countField: str | None = Field(default=None, min_length=1)
    categoryField: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _fields_match_the_kind(self) -> Self:
        # Fail fast at the boundary: a mapping set on the wrong kind would be
        # silently ignored, and a silently ignored knob is a lie in the config.
        if self.kind == "delimited":
            if self.delimiter is None or self.wordColumn is None:
                raise ValueError(
                    f"source {self.id!r}: kind 'delimited' needs delimiter + wordColumn"
                )
            stray = [f for f in _JSON_ONLY if getattr(self, f) is not None]
        else:
            if self.rootKey is None or self.wordField is None:
                raise ValueError(
                    f"source {self.id!r}: kind 'json-array' needs rootKey + wordField"
                )
            stray = [
                f
                for f in _DELIMITED_ONLY
                if f != "hasHeader" and getattr(self, f) is not None
            ]
        if stray:
            raise ValueError(
                f"source {self.id!r}: kind {self.kind!r} ignores {', '.join(stray)}"
            )
        return self


class CorpusSources(SchemaModel):
    """The declarative corpus source registry read by ``corpus/ingest.py``."""

    corpusRoot: RelPath
    filters: CorpusFilters
    bands: CorpusBands
    sources: list[CorpusSource] = Field(min_length=1)

    @model_validator(mode="after")
    def _source_ids_are_unique(self) -> Self:
        seen: set[str] = set()
        for source in self.sources:
            if source.id in seen:
                raise ValueError(f"duplicate source id {source.id!r}")
            seen.add(source.id)
        return self
