"""``wordsmith`` - the Tamil lexicon pipeline (build-time only).

Four stages, each independently runnable, each reading the previous stage's
on-disk artifact rather than an in-process value: EXTRACT, STAGE, ENRICH,
PUBLISH. Why it is four stages and not one pass is
``docs/architecture/lexicon/pipeline.md``; what the words mean is
``docs/concepts/lexicon.md``.

This package runs on a developer laptop and in CI's test suite. It is never a
runtime server (Holy Law #1) and the browser never reads anything it writes
except the published bank the puzzle engine bakes.

EXTRACT is the only stage that exists so far (Row 5).
"""

from __future__ import annotations

from yen_tamizh_backend.wordsmith.extract import (
    EXTRACTOR_VERSION,
    Fact,
    FactKind,
    Observation,
    SourceResult,
    Tally,
    emit,
    emit_from,
    extract,
    extract_source,
    load_registry,
    normalize,
)
from yen_tamizh_backend.wordsmith.readers import (
    DEFAULT_CHUNK,
    iter_delimited,
    iter_json_array,
    iter_jsonl,
    read_elements,
)

__all__ = [
    "DEFAULT_CHUNK",
    "EXTRACTOR_VERSION",
    "Fact",
    "FactKind",
    "Observation",
    "SourceResult",
    "Tally",
    "emit",
    "emit_from",
    "extract",
    "extract_source",
    "iter_delimited",
    "iter_json_array",
    "iter_jsonl",
    "load_registry",
    "normalize",
    "read_elements",
]
