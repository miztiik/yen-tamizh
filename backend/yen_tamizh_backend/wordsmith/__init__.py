"""``wordsmith`` - the Tamil lexicon pipeline (build-time only).

Four stages, each independently runnable, each reading the previous stage's
on-disk artifact rather than an in-process value: EXTRACT, STAGE, ENRICH,
PUBLISH. Why it is four stages and not one pass is
``docs/architecture/lexicon/pipeline.md``; what the words mean is
``docs/concepts/lexicon.md``.

This package runs on a developer laptop and in CI's test suite. It is never a
runtime server (Holy Law #1) and the browser never reads anything it writes
except the published bank the puzzle engine bakes.

EXTRACT and STAGE exist so far (Rows 5 and 6); ENRICH writes the store's
derived zone from row 7, and PUBLISH renders the artifact from row 11.
"""

from __future__ import annotations

from yen_tamizh_backend.wordsmith.enrich import (
    SIGNALS,
    EnrichRun,
    SignalResult,
    distribution,
    enrich,
    load_config,
)
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
from yen_tamizh_backend.wordsmith.signals_exact import (
    EXACT_SIGNALS,
    Signal,
    SignalContext,
    orthotactic_score,
)
from yen_tamizh_backend.wordsmith.stage import (
    ApplyResult,
    ExtractHeader,
    RemoveResult,
    StageRun,
    apply_extract,
    remove_source,
    stage,
)
from yen_tamizh_backend.wordsmith.store import (
    SIGNAL_COLUMNS,
    STORE_VERSION,
    StoreStats,
    canonical_digest,
    canonical_dump,
    derived_epoch,
    derived_is_current,
    open_store,
    stage_epoch,
    store_stats,
    transaction,
)

__all__ = [
    "DEFAULT_CHUNK",
    "EXACT_SIGNALS",
    "EXTRACTOR_VERSION",
    "SIGNALS",
    "SIGNAL_COLUMNS",
    "STORE_VERSION",
    "ApplyResult",
    "EnrichRun",
    "ExtractHeader",
    "Fact",
    "FactKind",
    "Observation",
    "RemoveResult",
    "Signal",
    "SignalContext",
    "SignalResult",
    "SourceResult",
    "StageRun",
    "StoreStats",
    "Tally",
    "apply_extract",
    "canonical_digest",
    "canonical_dump",
    "derived_epoch",
    "derived_is_current",
    "distribution",
    "emit",
    "emit_from",
    "enrich",
    "extract",
    "extract_source",
    "iter_delimited",
    "iter_json_array",
    "iter_jsonl",
    "load_config",
    "load_registry",
    "normalize",
    "open_store",
    "orthotactic_score",
    "read_elements",
    "remove_source",
    "stage",
    "stage_epoch",
    "store_stats",
    "transaction",
]
