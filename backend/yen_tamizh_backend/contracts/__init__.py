"""The evolutionary contract pipeline: Pydantic is the single source of truth.

The Pydantic models under this package are authoritative for every persisted
shape in yen-tamizh (CLAUDE.md sections 1a, 3, 11). ``export.py`` writes each
registered model to a flat ``schemas/<name>.schema.json`` (date-stamp
``version`` + ``changelog``, draft 2020-12, relative ``$id``); the frontend's
``scripts/gen-contracts.mjs`` derives TypeScript types + ajv validators from
those schemas. A CI drift gate regenerates both and fails on any diff, so the
schema, the types, and the validators can never drift from the models.

``REGISTRY`` is the explicit list of models the exporter walks. Later rows
append their models here (Row 7: app-config, event-envelope, save, puzzle-file,
bank-index, anagram-puzzle; Row 8: corpus-sources, master-wordlist; Row 9:
derived-wordlists, game-wordlist).
"""

from __future__ import annotations

from yen_tamizh_backend.contracts.anagram_puzzle import AnagramPuzzle
from yen_tamizh_backend.contracts.app_config import (
    AppConfig,
    DailyConfig,
    HintsConfig,
    InfiniteConfig,
    TimeTrialConfig,
    UiConfig,
)
from yen_tamizh_backend.contracts.bank_index import BankDay, BankIndex
from yen_tamizh_backend.contracts.base import ChangelogEntry, SchemaModel
from yen_tamizh_backend.contracts.common import (
    CopySlug,
    DifficultyId,
    GameId,
    Hint,
    ModeId,
    PackId,
)
from yen_tamizh_backend.contracts.copy import Copy
from yen_tamizh_backend.contracts.corpus_sources import (
    CorpusBands,
    CorpusFilters,
    CorpusSource,
    CorpusSources,
    RelPath,
    SourceId,
    SourceKind,
)
from yen_tamizh_backend.contracts.daily_generator import (
    DailyGenerator,
    DifficultyBand,
    GameGeneration,
    HintSpec,
)
from yen_tamizh_backend.contracts.derived_wordlists import (
    DerivedSelection,
    DerivedSet,
    DerivedWordlists,
)
from yen_tamizh_backend.contracts.event_envelope import EventEnvelope
from yen_tamizh_backend.contracts.example import Example
from yen_tamizh_backend.contracts.game_wordlist import (
    DerivedCounters,
    DerivedSource,
    GameWord,
    GameWordHints,
    GameWordlist,
)
from yen_tamizh_backend.contracts.glyph_manifest import GlyphManifest, GlyphShape
from yen_tamizh_backend.contracts.master_wordlist import (
    FreqBand,
    IngestCounters,
    MasterWord,
    MasterWordlist,
    SourceProvenance,
)
from yen_tamizh_backend.contracts.puzzle_file import PuzzleFile, PuzzleItem
from yen_tamizh_backend.contracts.save import Save, compute_day_key

# Explicit registry (not auto-discovery) so the exporter's output set is
# deterministic and reviewed. Export sorts by name; order here is not
# load-bearing. Row 7 adds the six core surfaces plus copy alongside the Row 5
# demonstrator and the Row 10 glyph manifest; Row 8 adds the corpus layer, Row 9
# the derived layer between the corpus and the puzzle engine, and Row 13 the
# daily engine's own registry.
REGISTRY: tuple[type[SchemaModel], ...] = (
    AnagramPuzzle,
    AppConfig,
    BankIndex,
    Copy,
    CorpusSources,
    DailyGenerator,
    DerivedWordlists,
    EventEnvelope,
    Example,
    GameWordlist,
    GlyphManifest,
    MasterWordlist,
    PuzzleFile,
    Save,
)

__all__ = [
    "REGISTRY",
    "AnagramPuzzle",
    "AppConfig",
    "BankDay",
    "BankIndex",
    "ChangelogEntry",
    "Copy",
    "CopySlug",
    "CorpusBands",
    "CorpusFilters",
    "CorpusSource",
    "CorpusSources",
    "DailyConfig",
    "DailyGenerator",
    "DerivedCounters",
    "DerivedSelection",
    "DerivedSet",
    "DerivedSource",
    "DerivedWordlists",
    "DifficultyBand",
    "DifficultyId",
    "EventEnvelope",
    "Example",
    "FreqBand",
    "GameGeneration",
    "GameId",
    "GameWord",
    "GameWordHints",
    "GameWordlist",
    "GlyphManifest",
    "GlyphShape",
    "Hint",
    "HintSpec",
    "HintsConfig",
    "InfiniteConfig",
    "IngestCounters",
    "MasterWord",
    "MasterWordlist",
    "ModeId",
    "PackId",
    "PuzzleFile",
    "PuzzleItem",
    "RelPath",
    "Save",
    "SchemaModel",
    "SourceId",
    "SourceKind",
    "SourceProvenance",
    "TimeTrialConfig",
    "UiConfig",
    "compute_day_key",
]
