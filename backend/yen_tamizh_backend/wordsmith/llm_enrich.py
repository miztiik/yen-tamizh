"""The authored lexicon source - reader and validator (Row 10).

Tamil meanings, Tamil synonyms, English translations, parts of speech and themes
are AUTHORED, in batches, by the agent executing the pipeline, and committed as
``datasets/lexicon/sources/llm-authored/entries.jsonl``. This module reads and
validates that file. It is NOT a network client: it holds no API client, no key
and no new dependency, and it never calls a model. The reasoning, the evidence
tiers and the human review loop are in ``docs/how-to/enrich-the-lexicon.md``;
the stage this source feeds is ``docs/architecture/lexicon/pipeline.md``.

**The model is a SOURCE, not a stage.** A model is not reproducible, so it can
never sit inside a stage whose Oracle is byte-identity. A committed file is: the
same bytes produce the same facts on every run, on every machine, forever, and a
bad batch is visible in a per-line diff and revertible by one commit.

The file is therefore raw INPUT, like every other registered source, and this
module is its reader in the same sense ``readers.py`` holds the others - which
is why it carries no generated JSON Schema. What makes a source trustworthy is
its reader failing loudly at the boundary, and every rule below does exactly
that: an unknown key, an unknown theme, a part of speech outside the closed
vocabulary, a row that asserts nothing, a repeated or out-of-order word.

Two rules a reviewer should be able to check by reading a diff:

1. **No hedged meaning.** A word whose Tamil meaning could not be authored
   confidently carries NO ``definitionTa``. A wrong meaning shown on the summary
   reads as a broken game; a wrong meaning the player PAID an attempt for is
   worse. The row-12 ``requireMeaning`` gate then decides admission.
2. **Themes are chosen from a closed set.** ``categories`` may only hold themes
   the registry's ``categoryAliases`` already normalizes to. A theme is
   player-facing copy, and minting one is a human decision.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, get_args

from yen_tamizh_backend.contracts.lexicon import PartOfSpeech
from yen_tamizh_backend.contracts.lexicon_sources import LexiconSources

# The registry id and the path its bytes live at. Committed, not acquired: this
# is the one source in the registry whose bytes are IN the repository, so it has
# no acquisition ledger row and no fixture slice - the real file is always there.
AUTHORED_SOURCE_ID: Final = "llm-authored"
AUTHORED_SOURCE_PATH: Final = "datasets/lexicon/sources/llm-authored/entries.jsonl"

# The date-stamp of the authoring instructions in
# docs/how-to/enrich-the-lexicon.md. A row records the version it was written
# under, so a later batch authored under revised instructions is distinguishable
# from an earlier one without re-reading either.
PROMPT_VERSION: Final = "2026-08-15"

# The closed part-of-speech vocabulary, taken from the contract rather than
# restated. An authored row writes these canonical names directly and does NOT
# route through `posAliases`: that map exists to translate a third-party
# source's own orthography into this vocabulary, and a source that writes the
# vocabulary natively has nothing to translate. The validator below is what
# keeps that honest.
PARTS_OF_SPEECH: Final[frozenset[str]] = frozenset(get_args(PartOfSpeech))

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_REQUIRED_KEYS: Final[tuple[str, ...]] = ("word", "model", "promptVersion", "authoredOn")
_AUTHORED_KEYS: Final[tuple[str, ...]] = (
    "pos",
    "translationEn",
    "definitionTa",
    "synonymsTa",
    "categories",
)
_KNOWN_KEYS: Final[frozenset[str]] = frozenset(_REQUIRED_KEYS + _AUTHORED_KEYS)


@dataclass(slots=True, frozen=True)
class AuthoredEntry:
    """One validated authored row.

    ``model``, ``promptVersion`` and ``authoredOn`` are build-time provenance and
    are NEVER rendered to a player: an "AI-written" mark on some meanings makes a
    player distrust all of them, including the dictionary's.
    """

    word: str
    model: str
    promptVersion: str
    authoredOn: str
    pos: tuple[str, ...] = ()
    translationEn: str | None = None
    definitionTa: str | None = None
    synonymsTa: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()


class AuthoredEntryError(ValueError):
    """One authored row is not admissible, and the message says which and why."""


def themes_of(registry: LexiconSources) -> frozenset[str]:
    """The closed set of themes an authored row may use.

    The VALUES of ``categoryAliases`` - the normalized forms every other source's
    labels already collapse into - so authoring can never mint a theme by
    spelling one differently.
    """
    return frozenset(registry.categoryAliases.values())


def _text(payload: Mapping[str, Any], key: str, where: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AuthoredEntryError(f"{where}: {key} must be a non-empty string")
    if value != value.strip():
        raise AuthoredEntryError(f"{where}: {key} carries leading or trailing space")
    return value


def _list(payload: Mapping[str, Any], key: str, where: str) -> tuple[str, ...]:
    raw = payload.get(key)
    if raw is None:
        return ()
    if not isinstance(raw, list) or not raw:
        raise AuthoredEntryError(
            f"{where}: {key} must be a non-empty list when present - an empty "
            f"list is a value that says nothing, so the key is omitted instead"
        )
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip() or item != item.strip():
            raise AuthoredEntryError(f"{where}: {key} holds {item!r}")
        values.append(item)
    if len(set(values)) != len(values):
        raise AuthoredEntryError(f"{where}: {key} repeats a value: {values}")
    return tuple(values)


def parse_entry(
    payload: Any, themes: frozenset[str], where: str, previous: str | None = None
) -> AuthoredEntry:
    """Validate one decoded row, or raise naming the row and the rule it broke.

    ``previous`` is the word on the row before, and the check that ``word``
    exceeds it does two jobs at once: it rejects a duplicate (an unreviewable
    conflict between two rows for the same word) and it pins the file to ``word``
    ASC, so a later batch INSERTS lines rather than reshuffling the file.
    """
    if not isinstance(payload, dict):
        raise AuthoredEntryError(f"{where}: expected an object, got {type(payload).__name__}")
    unknown = sorted(set(payload) - _KNOWN_KEYS)
    if unknown:
        raise AuthoredEntryError(
            f"{where}: unknown key(s) {unknown} - a key nothing reads is a "
            f"silent drop, so the reader refuses it rather than ignoring it"
        )

    word = _text(payload, "word", where)
    if unicodedata.normalize("NFC", word) != word:
        raise AuthoredEntryError(
            f"{where}: {word!r} is not NFC-normalized, so it would never join the "
            f"store's rows for the same surface"
        )
    if any(character.isspace() for character in word):
        raise AuthoredEntryError(f"{where}: {word!r} holds whitespace - a row is one surface")
    if previous is not None and word <= previous:
        raise AuthoredEntryError(
            f"{where}: {word!r} does not follow {previous!r} - entries are sorted "
            f"by word ASC and each word appears once"
        )

    model = _text(payload, "model", where)
    prompt_version = _text(payload, "promptVersion", where)
    authored_on = _text(payload, "authoredOn", where)
    for name, value in (("promptVersion", prompt_version), ("authoredOn", authored_on)):
        if not _DATE.match(value):
            raise AuthoredEntryError(f"{where}: {name} {value!r} is not a YYYY-MM-DD date-stamp")

    pos = _list(payload, "pos", where)
    unknown_pos = sorted(set(pos) - PARTS_OF_SPEECH)
    if unknown_pos:
        raise AuthoredEntryError(
            f"{where}: pos {unknown_pos} is outside the closed vocabulary - "
            f"parts of speech are a fact about the language, not a knob"
        )
    if list(pos) != sorted(pos):
        raise AuthoredEntryError(f"{where}: pos must be sorted: {list(pos)}")

    categories = _list(payload, "categories", where)
    unknown_themes = sorted(set(categories) - themes)
    if unknown_themes:
        raise AuthoredEntryError(
            f"{where}: theme(s) {unknown_themes} are not in categoryAliases - a "
            f"theme is player-facing copy and authoring may not mint one"
        )
    if list(categories) != sorted(categories):
        raise AuthoredEntryError(f"{where}: categories must be sorted: {list(categories)}")

    synonyms = _list(payload, "synonymsTa", where)
    if word in synonyms:
        raise AuthoredEntryError(f"{where}: {word!r} is listed as its own synonym")
    if list(synonyms) != sorted(synonyms):
        raise AuthoredEntryError(f"{where}: synonymsTa must be sorted: {list(synonyms)}")

    translation = _text(payload, "translationEn", where) if "translationEn" in payload else None
    definition = _text(payload, "definitionTa", where) if "definitionTa" in payload else None

    if not any(key in payload for key in _AUTHORED_KEYS):
        raise AuthoredEntryError(
            f"{where}: the row authors nothing. A row that carries only word-hood "
            f"is a model attesting a word on no evidence, which is exactly what "
            f"the serving gates exist to keep out"
        )
    return AuthoredEntry(
        word=word,
        model=model,
        promptVersion=prompt_version,
        authoredOn=authored_on,
        pos=pos,
        translationEn=translation,
        definitionTa=definition,
        synonymsTa=synonyms,
        categories=categories,
    )


def authored_facts(entry: AuthoredEntry) -> Iterator[tuple[str, str, int]]:
    """The ``(attr, value, ordinal)`` facts one authored row asserts.

    The ``headword`` fact is NOT emitted here: asserting word-hood is a function
    of the source's ROLE, and that check belongs to the extractor that already
    performs it for every other source.
    """
    for ordinal, part in enumerate(entry.pos):
        yield "pos", part, ordinal
    if entry.translationEn is not None:
        yield "translation", entry.translationEn, 0
    if entry.definitionTa is not None:
        yield "definitionTa", entry.definitionTa, 0
    for ordinal, synonym in enumerate(entry.synonymsTa):
        yield "synonym", synonym, ordinal
    for ordinal, theme in enumerate(entry.categories):
        yield "category", theme, ordinal


def read_entries(path: Path, themes: frozenset[str]) -> Iterator[AuthoredEntry]:
    """Stream and validate the committed file, one line at a time."""
    previous: str | None = None
    with path.open("r", encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            where = f"{AUTHORED_SOURCE_PATH}:{number}"
            try:
                payload: Any = json.loads(stripped)
            except ValueError as error:
                raise AuthoredEntryError(f"{where}: not valid JSON: {error}") from error
            entry = parse_entry(payload, themes, where, previous)
            previous = entry.word
            yield entry


def census(entries: Iterator[AuthoredEntry]) -> dict[str, int]:
    """What one authoring batch actually asserts, counted."""
    counts = Counter({"rows": 0, "definitionTa": 0, "synonymsTa": 0, "translationEn": 0,
                      "pos": 0, "categories": 0})
    for entry in entries:
        counts["rows"] += 1
        counts["definitionTa"] += entry.definitionTa is not None
        counts["synonymsTa"] += bool(entry.synonymsTa)
        counts["translationEn"] += entry.translationEn is not None
        counts["pos"] += bool(entry.pos)
        counts["categories"] += bool(entry.categories)
    return dict(counts)


def main(argv: list[str] | None = None) -> int:
    """Validate the committed authored source and print what it asserts."""
    parser = argparse.ArgumentParser(
        prog="python -m yen_tamizh_backend.wordsmith.llm_enrich",
        description=(
            "Validate the committed authored lexicon source. It reads a file; it "
            "never calls a model. See docs/how-to/enrich-the-lexicon.md."
        ),
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[3],
        help="repository root (default: inferred from this file)",
    )
    args = parser.parse_args(argv)
    root: Path = args.repo_root
    registry = LexiconSources.model_validate_json(
        (root / "config" / "lexicon-sources.json").read_text(encoding="utf-8")
    )
    path = root / AUTHORED_SOURCE_PATH
    try:
        counts = census(read_entries(path, themes_of(registry)))
    except AuthoredEntryError as error:
        print(f"INVALID {error}", file=sys.stderr)
        return 1
    print(f"{AUTHORED_SOURCE_PATH}: {counts['rows']} rows")
    for key in ("definitionTa", "synonymsTa", "translationEn", "pos", "categories"):
        print(f"  {key}: {counts[key]}")
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entry point
    raise SystemExit(main())
