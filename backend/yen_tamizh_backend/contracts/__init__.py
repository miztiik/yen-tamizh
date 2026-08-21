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
    JourneyId,
    ModeId,
    PackId,
    RelPath,
    SourceId,
)
from yen_tamizh_backend.contracts.copy import Copy
from yen_tamizh_backend.contracts.crossword_puzzle import (
    CrosswordCell,
    CrosswordEntry,
    CrosswordPuzzle,
)
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
from yen_tamizh_backend.contracts.journey import (
    Journey,
    JourneyNode,
    UnlockRule,
)
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
from yen_tamizh_backend.contracts.pool_index import PoolEntry, PoolIndex, PoolItem
from yen_tamizh_backend.contracts.puzzle_file import PuzzleFile, PuzzleItem
from yen_tamizh_backend.contracts.save import Save, TimeTrialBest, compute_day_key
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
from yen_tamizh_backend.contracts.word_ladder_puzzle import (
    LadderRung,
    WordLadderPuzzle,
    added_ezhuthu,
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
# never an edit to ``puzzle-file``. Row 15 adds the sixth and last of them, and
# it is the only one registered before its Game: the ladder is PROVED at build
# time, so the graph and the contract that checks its climb land a row ahead of
# the board that renders it. Row 17 adds the first surface that is neither a
# knob nor a Game payload but a MODE's own content: a Journey is an ordered path
# of nodes, and registering it here is what makes authoring one a data change.
# Row 22 adds the second, and the only one that is a MANIFEST over content rather
# than the content itself: the Infinite pool is thousands of files and the index
# is what makes reaching one of them a single small request. The pooled puzzle's
# own shape rides in that schema's ``$defs`` rather than as a registered document
# of its own - see pool_index.py for the byte measurement that decided it.
REGISTRY: tuple[type[SchemaModel], ...] = (
    AnagramPuzzle,
    AppConfig,
    BankIndex,
    Copy,
    CrosswordPuzzle,
    DailyGenerator,
    DerivedWordlists,
    EventEnvelope,
    Example,
    GameWordlist,
    GlyphManifest,
    Journey,
    Lexicon,
    LexiconSources,
    MissingLettersPuzzle,
    PoolIndex,
    PuzzleFile,
    Save,
    ServedDenylist,
    Wordhood,
    WordLadderPuzzle,
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
    "CrosswordCell",
    "CrosswordEntry",
    "CrosswordPuzzle",
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
    "Journey",
    "JourneyId",
    "JourneyNode",
    "LadderRung",
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
    "PoolEntry",
    "PoolIndex",
    "PoolItem",
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
    "TimeTrialBest",
    "TimeTrialConfig",
    "TypoProfile",
    "UiConfig",
    "UnlockRule",
    "WordClass",
    "WordClassEvidence",
    "WordLadderPuzzle",
    "WordSearchPuzzle",
    "WordSearchTarget",
    "Wordhood",
    "WordlePuzzle",
    "added_ezhuthu",
    "compute_day_key",
]
