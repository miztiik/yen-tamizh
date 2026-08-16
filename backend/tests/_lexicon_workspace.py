"""Where a registered source's readable bytes live, for a test workspace.

Every store-backed wordsmith test builds its own extracts by running the REAL
extractor over committed bytes, so no test needs the gitignored raw sources.
For the acquired sources those bytes are the row-4 fixture slice; for the ONE
authored source they are the committed file itself.

Both helpers live in ``yen_tamizh_backend.scripts.rebuild_lexicon_fixture``
rather than here, and this module only re-exports them. That script REGENERATES
the committed expectation the row-11 integration gate byte-compares against, so
the gate and the thing it compares to must be built by ONE piece of code - two
copies that drift make the comparison meaningless in the exact case it exists to
catch.

Not a test module: it holds no assertion and pytest does not collect it. The
leading underscore is what says so.
"""

from __future__ import annotations

from yen_tamizh_backend.scripts.rebuild_lexicon_fixture import (
    fixture_registry,
    source_bytes,
)

__all__ = ["fixture_registry", "source_bytes"]
