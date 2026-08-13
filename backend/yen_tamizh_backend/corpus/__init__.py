"""The corpus layer: raw Tamil word sources -> one ranked master wordlist.

The corpus and the daily puzzle are DIFFERENT things and this package is only
the first. It turns the sources registered in ``config/corpus-sources.json`` into
``datasets/wordlists/master/words_ranked.json`` - a big, ranked,
ezhuthu-segmented pile of Tamil words. Nothing here knows about a Game, a mode,
or a day: the per-Game derived sets (Row 9) read the master list, and the daily
puzzle engine (Row 13) reads those. That layering is what lets a corpus refresh
land without rebuilding a Game.

Adding a word source is a data change - see
``docs/how-to/add-a-corpus-source.md``.

``ingest`` and ``rank`` are imported by module path
(``from yen_tamizh_backend.corpus.ingest import ingest``) rather than re-exported
here, so the ``ingest`` module and the ``ingest`` function never shadow one
another.
"""

from __future__ import annotations
