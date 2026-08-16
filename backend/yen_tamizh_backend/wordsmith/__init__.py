"""``wordsmith`` - the Tamil lexicon pipeline (build-time only).

Four stages, each independently runnable, each reading the previous stage's
on-disk artifact rather than an in-process value: EXTRACT, STAGE, ENRICH,
PUBLISH. REVIEW sits beside them as a REPORT over the derived zone, writing
nothing back. Why it is four stages and not one pass is
``docs/architecture/lexicon/pipeline.md``; what the words mean is
``docs/concepts/lexicon.md``.

This package runs on a developer laptop and in CI's test suite. It is never a
runtime server (Holy Law #1) and the browser never reads anything it writes
except the published bank the puzzle engine bakes.

EXTRACT and STAGE exist so far (Rows 5 and 6); ENRICH writes the store's
derived zone from row 7, REVIEW dumps it for a human from row 9b, and PUBLISH
renders the artifact from row 11, with ``pipeline`` sequencing the four stages
and holding no logic of its own.
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
from yen_tamizh_backend.wordsmith.pipeline import PipelineRun, run
from yen_tamizh_backend.wordsmith.publish import (
    BY_CLASS,
    META_NAME,
    README_NAME,
    PublishRun,
    WrittenPartition,
    partition_hex,
    partition_path,
    publish,
    render,
    render_meta,
    render_readme,
    write_rows,
)
from yen_tamizh_backend.wordsmith.readers import (
    DEFAULT_CHUNK,
    iter_delimited,
    iter_delimited_quoted,
    iter_json_array,
    iter_jsonl,
    read_elements,
)
from yen_tamizh_backend.wordsmith.resolve import (
    SENSE_ATTR,
    SINGLE_ATTRS,
    UNION_ATTRS,
    ResolutionError,
    base_ezhuthu,
    check_the_closed_vocabularies,
)
from yen_tamizh_backend.wordsmith.review import ReviewRun, review
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
    "BY_CLASS",
    "DEFAULT_CHUNK",
    "EXACT_SIGNALS",
    "EXTRACTOR_VERSION",
    "META_NAME",
    "README_NAME",
    "SENSE_ATTR",
    "SIGNALS",
    "SIGNAL_COLUMNS",
    "SINGLE_ATTRS",
    "STORE_VERSION",
    "UNION_ATTRS",
    "ApplyResult",
    "EnrichRun",
    "ExtractHeader",
    "Fact",
    "FactKind",
    "Observation",
    "PipelineRun",
    "PublishRun",
    "RemoveResult",
    "ResolutionError",
    "ReviewRun",
    "Signal",
    "SignalContext",
    "SignalResult",
    "SourceResult",
    "StageRun",
    "StoreStats",
    "Tally",
    "WrittenPartition",
    "apply_extract",
    "base_ezhuthu",
    "canonical_digest",
    "canonical_dump",
    "check_the_closed_vocabularies",
    "derived_epoch",
    "derived_is_current",
    "distribution",
    "emit",
    "emit_from",
    "enrich",
    "extract",
    "extract_source",
    "iter_delimited",
    "iter_delimited_quoted",
    "iter_json_array",
    "iter_jsonl",
    "load_config",
    "load_registry",
    "normalize",
    "open_store",
    "orthotactic_score",
    "partition_hex",
    "partition_path",
    "publish",
    "read_elements",
    "remove_source",
    "render",
    "render_meta",
    "render_readme",
    "review",
    "run",
    "stage",
    "stage_epoch",
    "store_stats",
    "transaction",
    "write_rows",
]
