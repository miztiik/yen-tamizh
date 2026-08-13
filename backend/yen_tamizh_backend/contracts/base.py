"""Base Pydantic models for the evolutionary contract pipeline.

The backend's Pydantic models are the single source of truth for every
persisted shape (CLAUDE.md sections 1a, 3, 11). From them ``export.py`` emits
flat ``schemas/<name>.schema.json`` files, and the frontend derives TypeScript
types + ajv validators. A CI drift gate regenerates both and fails on any diff.

Every schema carries a date-stamp ``version`` and a newest-first ``changelog``
(CLAUDE.md section 11): ``version`` records *when* the shape last changed and
equals ``changelog[0].version``.
"""

from __future__ import annotations

import re
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

# A schema version is a date-stamp, never an integer or epoch (CLAUDE.md
# section 11): YYYY-MM-DD, optionally extended to the minute or second when more
# than one change lands on the same day.
_DATESTAMP = r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?$"

# PascalCase model name -> kebab-case schema stem (Example -> example,
# AnagramPuzzle -> anagram-puzzle).
_WORD_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")

_DIALECT_2020_12 = "https://json-schema.org/draft/2020-12/schema"


class ChangelogEntry(BaseModel):
    """One dated entry in a schema's in-file change log (newest first).

    ``version`` is the date-stamp of the change; ``change`` is what changed;
    ``why`` is the reason it changed (CLAUDE.md section 11).
    """

    model_config = ConfigDict(extra="forbid")

    version: str = Field(pattern=_DATESTAMP)
    change: str = Field(min_length=1)
    why: str = Field(min_length=1)


class SchemaModel(BaseModel):
    """Base for every persisted contract: carries ``version`` + ``changelog``.

    Subclasses add their own fields. ``version`` must equal the newest changelog
    entry's version (CLAUDE.md section 11). ``json_schema()`` emits a canonical
    draft 2020-12 schema with a relative ``$id`` so offline IDE plugins validate
    without a network call.
    """

    model_config = ConfigDict(extra="forbid")

    version: str = Field(pattern=_DATESTAMP)
    changelog: list[ChangelogEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _version_matches_newest_changelog(self) -> Self:
        newest = self.changelog[0].version
        if self.version != newest:
            raise ValueError(
                f"version {self.version!r} must equal changelog[0].version {newest!r}"
            )
        return self

    @classmethod
    def schema_name(cls) -> str:
        """The kebab-case stem used for ``schemas/<stem>.schema.json``."""
        return _WORD_BOUNDARY.sub("-", cls.__name__).lower()

    @classmethod
    def json_schema(cls) -> dict[str, Any]:
        """Draft 2020-12 JSON Schema with a relative, offline-validatable ``$id``."""
        body = cls.model_json_schema()
        schema: dict[str, Any] = {
            "$schema": _DIALECT_2020_12,
            "$id": f"{cls.schema_name()}.schema.json",
        }
        schema.update(body)
        return schema
