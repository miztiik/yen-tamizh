"""Deterministic ranking and banding for the corpus master wordlist (Row 8).

Pure functions over accumulated corpus entries, kept apart from ``ingest.py`` so
the ordering rule and the band cuts can be tested without touching a file.

Ranks are assigned AFTER selection, so ``freqRank`` runs 1..N contiguously over
the words actually kept. That is what makes percentile banding honest: a band is
a fraction of the published list, not of a filtered-away tail nobody can see.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from yen_tamizh_backend.contracts.corpus_sources import CorpusBands
from yen_tamizh_backend.contracts.master_wordlist import FreqBand


@dataclass(slots=True)
class CorpusEntry:
    """One accumulated word: its merged frequency and where it was attested."""

    word: str
    total: int
    sources: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)


def order(entries: Iterable[CorpusEntry]) -> list[CorpusEntry]:
    """Order by descending merged frequency, ties broken deterministically.

    The tie-break (shorter word first, then code-point order) matters: a rank
    that depends on dict insertion order would make the committed artifact
    irreproducible, and the drift gate would flap.
    """
    return sorted(entries, key=lambda entry: (-entry.total, len(entry.word), entry.word))


def apply_floor(
    ordered: Sequence[CorpusEntry], min_total: int
) -> tuple[list[CorpusEntry], int]:
    """Drop entries below the merged-frequency floor; return them and the count.

    The floor is a quality gate as much as a size one: the long tail of a news
    corpus is overwhelmingly typos, proper nouns, and one-off inflections that no
    Tamil speaker would accept as a puzzle answer.
    """
    kept = [entry for entry in ordered if entry.total >= min_total]
    return kept, len(ordered) - len(kept)


def apply_cap(
    ordered: Sequence[CorpusEntry], max_words: int | None
) -> tuple[list[CorpusEntry], int]:
    """Keep at most ``max_words`` highest-ranked entries; return them and the cut."""
    if max_words is None or len(ordered) <= max_words:
        return list(ordered), 0
    return list(ordered[:max_words]), len(ordered) - max_words


def band_for(position: int, total: int, bands: CorpusBands) -> FreqBand:
    """Band a 1-based rank ``position`` within a list of ``total`` ranked words."""
    percentile = position / total
    if percentile <= bands.commonMaxPercentile:
        return "common"
    if percentile <= bands.midMaxPercentile:
        return "mid"
    return "rare"
