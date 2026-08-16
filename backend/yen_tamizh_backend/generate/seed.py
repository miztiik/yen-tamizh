"""The seeded randomness the daily engine is built on.

A daily puzzle must be reproducible: two runs for the same date must produce the
same bytes, on any machine, on any Python version, forever - that is the Row 13
Oracle. Python's ``random`` module is explicitly documented as free to change
its algorithms between versions, so a bank baked on the author's 3.14 and
re-baked by CI on 3.12 could silently differ. This module therefore carries its
own 32-bit generator in a dozen lines of arithmetic: FNV-1a to turn a seed
STRING into a seed number, and mulberry32 to turn that number into a stream.

The same pair runs in the frontend (``frontend/src/games/anagram/logic.ts``),
so a scramble reasons identically on both sides of the boundary.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

_MASK32 = 0xFFFFFFFF
_FNV_OFFSET = 2166136261
_FNV_PRIME = 16777619

T = TypeVar("T")


def hash_seed(text: str) -> int:
    """FNV-1a over the text's UTF-16 code units - a stable 32-bit seed.

    Code units, not bytes, so the seed matches the TypeScript twin, where
    ``charCodeAt`` yields exactly these values.
    """
    digest = _FNV_OFFSET
    for unit in _utf16_units(text):
        digest ^= unit
        digest = (digest * _FNV_PRIME) & _MASK32
    return digest


def _utf16_units(text: str) -> list[int]:
    """The UTF-16 code units of a string (surrogate pairs stay two units)."""
    raw = text.encode("utf-16-le")
    return [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)]


class Mulberry32:
    """A tiny deterministic PRNG: one seed always replays one stream."""

    def __init__(self, seed: int) -> None:
        self._state = seed & _MASK32

    def next_float(self) -> float:
        """The next value in [0, 1)."""
        self._state = (self._state + 0x6D2B79F5) & _MASK32
        t = self._state
        t = (t ^ (t >> 15)) * (t | 1) & _MASK32
        t ^= (t + ((t ^ (t >> 7)) * (t | 61) & _MASK32)) & _MASK32
        t &= _MASK32
        return ((t ^ (t >> 14)) & _MASK32) / 4294967296


def seeded_shuffle(items: Sequence[T], seed_text: str) -> list[T]:
    """Fisher-Yates driven by the seed: same seed and input, same order."""
    out = list(items)
    rand = Mulberry32(hash_seed(seed_text))
    for i in range(len(out) - 1, 0, -1):
        j = int(rand.next_float() * (i + 1))
        out[i], out[j] = out[j], out[i]
    return out


def seeded_index(count: int, seed_text: str) -> int:
    """Pick one of ``count`` positions from a seed - mixed, never truncated.

    ``hash_seed(text) % count`` will not do, and the reason is worth stating
    because it is invisible until it bites: FNV-1a multiplies by an ODD prime,
    so the low bit of its digest is simply the XOR of the low bits of its
    inputs. Two seeds whose texts share that parity therefore share the parity
    of their digest, and any caller taking the digest modulo a power of two gets
    two perfectly correlated "random" choices. That is exactly what happened to
    the daily draw: ``|medium`` and ``|hard`` have the same low-bit parity, so
    the two bands rotated their frequency strata in lockstep on every date.
    Running the digest through the generator mixes it.
    """
    if count <= 0:
        raise ValueError(f"count must be positive, not {count}")
    # next_float() is in [0, 1), so the product is below count - the clamp is a
    # guard against a float rounding up at the very top of the range.
    return min(int(Mulberry32(hash_seed(seed_text)).next_float() * count), count - 1)
