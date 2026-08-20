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
bank-index, anagram-puzzle; Row 9: derived-wordlists, game-wordlist; row 16:
served-denylist).
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
    RelPath,
    SourceId,
)
from yen_tamizh_backend.contracts.copy import Copy
from yen_tamizh_backend.contracts.daily_generator import (
    DailyGenerator,
    DifficultyBand,
    GameGeneration,
    HintSpec,
    ThemedSet,
)
from yen_tamizh_backend.contracts.derived_wordlists import (
    DerivedSelection,
    DerivedSet,
    DerivedWordlists,
    ParticipialSuffix,
    ServingRules,
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
from yen_tamizh_backend.contracts.lexicon import (
    LEXICON_CHANGELOG,
    LEXICON_VERSION,
    PARTITION_KEYS,
    EzhuthuIndexEntry,
    Lexicon,
    LexiconCensus,
    LexiconCounters,
    LexiconEntry,
    LexiconPartition,
    LexiconProvenance,
    PartOfSpeech,
    SignalName,
    WordClass,
)
from yen_tamizh_backend.contracts.lexicon_sources import (
    LEXICON_SOURCES_CHANGELOG,
    LEXICON_SOURCES_VERSION,
    AttestationTier,
    ElementKind,
    LexiconSource,
    LexiconSourceKind,
    LexiconSources,
    OutputFormat,
    PosAlias,
    PosRejection,
    SourceRole,
    WordClassEvidence,
)
from yen_tamizh_backend.contracts.missing_letters_puzzle import MissingLettersPuzzle
from yen_tamizh_backend.contracts.puzzle_file import PuzzleFile, PuzzleItem
from yen_tamizh_backend.contracts.save import Save, compute_day_key
from yen_tamizh_backend.contracts.served_denylist import (
    SERVED_DENYLIST_CHANGELOG,
    SERVED_DENYLIST_VERSION,
    DeniedWord,
    ServedDenylist,
)
from yen_tamizh_backend.contracts.wordhood import (
    WORDHOOD_CHANGELOG,
    WORDHOOD_VERSION,
    ClassifierSettings,
    DiscoveryProfile,
    NeighbourSettings,
    NgramSettings,
    NotAWordProfile,
    OrthotacticWeights,
    TypoProfile,
    Wordhood,
)
from yen_tamizh_backend.contracts.word_search_puzzle import (
    GridPoint,
    WordSearchPuzzle,
    WordSearchTarget,
)
from yen_tamizh_backend.contracts.wordle_puzzle import WordlePuzzle

# Explicit registry (not auto-discovery) so the exporter's output set is
# deterministic and reviewed. Export sorts by name; order here is not
# load-bearing. Row 7 adds the six core surfaces plus copy alongside the Row 5
# demonstrator and the Row 10 glyph manifest; Row 9 adds the derived layer
# between the word inventory and the puzzle engine, and Row 13 the daily
# engine's own registry. The lexicon layer that replaced the retired corpus one
# registers its meta document, its source registry and the word-hood knobs its
# enrich stage reads; row 16 adds the served deny-list the derived layer applies
# after every automatic gate, and defect 2 adds the derivable pair beside it -
# the participial suffixes and the obscenity labels - inside the derived
# registry's own schema. ``LexiconEntry`` is NOT here - a data row carries
# no ``version`` / ``changelog``, so it is not a ``SchemaModel``, and it reaches
# the schema through ``Lexicon.rowSchema``. Row 18 adds the second per-Game
# payload beside the anagram's, Row 19 the third and Row 20 the fourth, which is
# the whole point of one schema per Game: a new Game costs a payload schema,
# never an edit to ``puzzle-file``.
REGISTRY: tuple[type[SchemaModel], ...] = (
    AnagramPuzzle,
    AppConfig,
    BankIndex,
    Copy,
    DailyGenerator,
    DerivedWordlists,
    EventEnvelope,
    Example,
    GameWordlist,
    GlyphManifest,
    Lexicon,
    LexiconSources,
    MissingLettersPuzzle,
    PuzzleFile,
    Save,
    ServedDenylist,
    Wordhood,
    WordSearchPuzzle,
    WordlePuzzle,
)

__all__ = [
    "LEXICON_CHANGELOG",
    "LEXICON_SOURCES_CHANGELOG",
    "LEXICON_SOURCES_VERSION",
    "LEXICON_VERSION",
    "PARTITION_KEYS",
    "REGISTRY",
    "SERVED_DENYLIST_CHANGELOG",
    "SERVED_DENYLIST_VERSION",
    "WORDHOOD_CHANGELOG",
    "WORDHOOD_VERSION",
    "AnagramPuzzle",
    "AppConfig",
    "AttestationTier",
    "BankDay",
    "BankIndex",
    "ChangelogEntry",
    "ClassifierSettings",
    "Copy",
    "CopySlug",
    "DailyConfig",
    "DailyGenerator",
    "DeniedWord",
    "DerivedCounters",
    "DerivedSelection",
    "DerivedSet",
    "DerivedSource",
    "DerivedWordlists",
    "DifficultyBand",
    "DifficultyId",
    "DiscoveryProfile",
    "ElementKind",
    "EventEnvelope",
    "Example",
    "EzhuthuIndexEntry",
    "GameGeneration",
    "GameId",
    "GameWord",
    "GameWordHints",
    "GameWordlist",
    "GlyphManifest",
    "GlyphShape",
    "GridPoint",
    "Hint",
    "HintSpec",
    "HintsConfig",
    "InfiniteConfig",
    "Lexicon",
    "LexiconCensus",
    "LexiconCounters",
    "LexiconEntry",
    "LexiconPartition",
    "LexiconProvenance",
    "LexiconSource",
    "LexiconSourceKind",
    "LexiconSources",
    "MissingLettersPuzzle",
    "ModeId",
    "NeighbourSettings",
    "NgramSettings",
    "NotAWordProfile",
    "OrthotacticWeights",
    "OutputFormat",
    "PackId",
    "PartOfSpeech",
    "ParticipialSuffix",
    "PosAlias",
    "PosRejection",
    "PuzzleFile",
    "PuzzleItem",
    "RelPath",
    "Save",
    "SchemaModel",
    "ServedDenylist",
    "ServingRules",
    "SignalName",
    "SourceId",
    "SourceRole",
    "ThemedSet",
    "TimeTrialConfig",
    "TypoProfile",
    "UiConfig",
    "WordClass",
    "WordClassEvidence",
    "WordSearchPuzzle",
    "WordSearchTarget",
    "Wordhood",
    "WordlePuzzle",
    "compute_day_key",
]
