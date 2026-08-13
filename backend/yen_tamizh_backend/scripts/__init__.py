"""Operator entry points for the build-time pipeline.

Each module here is ONE command a maintainer runs by hand or CI runs on a
schedule. They are thin: the behaviour lives in the layer packages
(``corpus``, ``ezhuthu``, ``glyphs``), and a script only wires paths, prints a
report, and writes artifacts.
"""

from __future__ import annotations
