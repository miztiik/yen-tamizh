"""Tamil ezhuthu (grapheme-cluster) segmentation + classification.

The ezhuthu is the atomic written unit of Tamil and the atomic gameplay unit
everywhere in yen-tamizh (tiles, wordle letters, ladder rungs, crossword cells).
This package has a TypeScript twin at ``frontend/src/tamil/ezhuthu.ts`` kept in
lockstep by the shared golden corpus
``datasets/fixtures/ezhuthu_golden.jsonl`` (Row 6).
"""

from __future__ import annotations

from yen_tamizh_backend.ezhuthu.classify import EzhuthuKind, classify
from yen_tamizh_backend.ezhuthu.segment import segment
from yen_tamizh_backend.ezhuthu.word_shape import (
    BASE_ROMAN,
    CLUSTER_FOLLOWERS,
    CONSONANTS,
    EZHUTHU_INVENTORY,
    FINAL_MEI,
    GRANTHA,
    IDAIYINAM,
    INITIAL_CONSONANTS,
    MELLINAM,
    UYIR,
    VALLINAM,
    WordShape,
    analyse,
    begins_like_a_word,
    cluster_is_legal,
    ends_like_a_word,
    is_word_final,
)

__all__ = [
    "BASE_ROMAN",
    "CLUSTER_FOLLOWERS",
    "CONSONANTS",
    "EZHUTHU_INVENTORY",
    "FINAL_MEI",
    "GRANTHA",
    "IDAIYINAM",
    "INITIAL_CONSONANTS",
    "MELLINAM",
    "UYIR",
    "VALLINAM",
    "EzhuthuKind",
    "WordShape",
    "analyse",
    "begins_like_a_word",
    "classify",
    "cluster_is_legal",
    "ends_like_a_word",
    "is_word_final",
    "segment",
]
