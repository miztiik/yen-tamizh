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


class Unbuildable(ValueError):
    """This ROW cannot become a puzzle, though the wordlist and band are fine.

    The shared vocabulary between the day loop and every builder, which is why
    it lives on the package rather than inside one Game. The loop already drops
    a row no band claims - the wordlist says what is SERVABLE and the bands say
    what is DRAWABLE - and this is the third question, asked one layer further
    in: can this particular word become this particular board.

    Only the crossword can answer no. Its board is an interlock, so an answer
    has to share letters with everything crossing it, and roughly one served
    word in a hundred has a letter at a crossed position that no other word in
    the set carries at the position it would have to. Raising rather than
    returning is what keeps a half-filled grid from ever being baked; the loop
    answers by dealing the next candidate from the same band, which is what
    keeps a rare unlucky word from failing a whole day's bake.
    """
