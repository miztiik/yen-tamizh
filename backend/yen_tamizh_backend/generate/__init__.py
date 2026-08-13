"""The daily puzzle ENGINE (Row 13).

This package is the layer BELOW the corpus. It consumes a per-Game derived
wordlist (Row 9) and produces committed puzzle files::

    datasets/corpus/**  ->  master wordlist  ->  per-Game sets  ->  daily puzzles
       (raw sources)          (Row 8)             (Row 9)          (this package)

It never re-ingests, re-ranks, or re-derives: a corpus refresh re-runs the two
layers above it and this engine reads whatever they committed. That separation
is the point - refreshing the words must never mean rebuilding the game.

Everything here is a pure function of (a date, a wordlist, a config), seeded so
the same inputs always produce the same bytes; the only impure edges are the
entry point in ``scripts/generate_today.py`` (which reads the clock and writes
files) and the bank it writes into ``frontend/public/``.
"""

from __future__ import annotations
