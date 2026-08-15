"""Where a registered source's readable bytes live, for a test workspace.

Every store-backed wordsmith test builds its own extracts by running the REAL
extractor over committed bytes, so no test needs the gitignored raw sources.
For the acquired sources those bytes are the row-4 fixture slice; for the ONE
authored source they are the committed file itself.

Not a test module: it holds no assertion and pytest does not collect it. The
leading underscore is what says so.
"""

from __future__ import annotations

from pathlib import Path

from yen_tamizh_backend.contracts.lexicon_sources import LexiconSource
from yen_tamizh_backend.wordsmith.llm_enrich import AUTHORED_SOURCE_ID


def source_bytes(repo_root: Path, fixtures: Path, source: LexiconSource) -> Path:
    """The committed bytes a workspace should stage for ``source``.

    A fixture exists because a raw source is gitignored. The authored source is
    not: its bytes ARE the review artifact, so it has no acquisition ledger row,
    no fixture slice, and nothing to slice - the real file is always on disk and
    is what the tests must exercise.
    """
    if source.id == AUTHORED_SOURCE_ID:
        return repo_root / source.path
    return fixtures / f"{source.id}.1x{Path(source.path).suffix}"
