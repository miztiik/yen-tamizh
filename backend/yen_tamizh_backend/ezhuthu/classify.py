"""Classify a single ezhuthu as uyir / mei / uyirmei / aytham / other.

- ``uyir``    - an independent vowel (a .. au), including the NFD au vowel.
- ``mei``     - a pure consonant (consonant + pulli, no vowel sign).
- ``uyirmei`` - a consonant carrying a vowel: a bare consonant (inherent /a/) or
  a consonant with any vowel matra.
- ``aytham``  - the aytham (U+0B83).
- ``other``   - anything else (digits, spaces, punctuation, non-Tamil, or a
  stray combining mark passed as its own unit).

Classification keys off the ezhuthu's base (first) code point and, for a
consonant base, whether the cluster carries a pulli or a vowel sign.
"""

from __future__ import annotations

from typing import Literal

EzhuthuKind = Literal["uyir", "mei", "uyirmei", "aytham", "other"]

_AYTHAM = 0x0B83
_PULLI = 0x0BCD


def _is_uyir(cp: int) -> bool:
    return 0x0B85 <= cp <= 0x0B94  # independent vowels a .. au


def _is_consonant(cp: int) -> bool:
    return 0x0B95 <= cp <= 0x0BB9  # mei letters ka .. ha (incl. Grantha)


def _is_vowel_sign(cp: int) -> bool:
    # matras that carry a vowel onto a consonant, incl. the au length mark
    return 0x0BBE <= cp <= 0x0BCC or cp == 0x0BD7


def classify(ezhuthu: str) -> EzhuthuKind:
    """Classify one ezhuthu (as produced by ``segment``)."""
    if not ezhuthu:
        return "other"
    base = ord(ezhuthu[0])
    if base == _AYTHAM:
        return "aytham"
    if _is_uyir(base):
        return "uyir"
    if _is_consonant(base):
        rest = [ord(c) for c in ezhuthu[1:]]
        has_vowel_sign = any(_is_vowel_sign(c) for c in rest)
        has_pulli = _PULLI in rest
        if has_pulli and not has_vowel_sign:
            return "mei"
        return "uyirmei"
    return "other"
