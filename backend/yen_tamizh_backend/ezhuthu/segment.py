"""Tamil ezhuthu (grapheme-cluster) segmentation.

An *ezhuthu* is the atomic written unit of Tamil: an independent vowel (uyir), a
pure consonant (mei = consonant + pulli), a consonant+vowel (uyirmei), or the
aytham. ``segment`` groups a string's Unicode code points into ezhuthu without
altering them, so ``"".join(segment(w)) == w`` holds for every input (including
non-Tamil characters, which pass through as their own units).

The walk is a deterministic code-point scan - not ``unicodedata`` or an ICU
segmenter - so this Python twin and the TypeScript twin in
``frontend/src/tamil/ezhuthu.ts`` are provably identical regardless of the host
ICU version. The shared golden corpus ``datasets/fixtures/ezhuthu_golden.jsonl``
proves the parity (Row 6).
"""

from __future__ import annotations


def _is_combining(cp: int) -> bool:
    """Tamil combining marks that attach to the preceding base character.

    U+0B82 anusvara (nonspacing); U+0BBE..U+0BCD vowel signs (matras) and the
    pulli/virama; U+0BD7 au length mark (the second half of the decomposed au
    matra and of the decomposed au vowel).
    """
    return cp == 0x0B82 or 0x0BBE <= cp <= 0x0BCD or cp == 0x0BD7


def segment(word: str) -> list[str]:
    """Split ``word`` into ezhuthu (grapheme clusters), code-point preserving."""
    clusters: list[str] = []
    current = ""
    for ch in word:
        if current and _is_combining(ord(ch)):
            current += ch
        else:
            if current:
                clusters.append(current)
            current = ch
    if current:
        clusters.append(current)
    return clusters
