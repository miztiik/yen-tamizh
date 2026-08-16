"""Where a registered source's readable bytes live, for a test workspace.

Every store-backed wordsmith test builds its own extracts by running the REAL
extractor over committed bytes, so no test needs the gitignored raw sources.
For the acquired sources those bytes are the row-4 fixture slice; for the ONE
authored source they are the committed file itself.

The implementations live in ``scripts/rebuild_lexicon_fixture.py`` and are only
RE-EXPORTED here. The integration gate compares a fresh pipeline run against a
committed expectation, so the gate and the expectation it compares against have
to be built by ONE piece of code - a second copy living in the tests could
disagree with the writer in exactly the case the gate exists to catch.

Not a test module: it holds no assertion and pytest does not collect it. The
leading underscore is what says so.
"""

from __future__ import annotations

from typing import Any

from yen_tamizh_backend.contracts.lexicon_sources import LexiconSource, LexiconSources
from yen_tamizh_backend.scripts.rebuild_lexicon_fixture import (
    EXPECTED,
    FIXTURES,
    fixture_registry,
    rebuild,
    source_bytes,
)


def narrowed(
    registry: LexiconSources, sources: list[LexiconSource], **overrides: Any
) -> LexiconSources:
    """``registry`` re-validated over a SUBSET of its sources.

    A probe that keeps one source has to stay a LEGAL registry, and
    ``spokenSources`` names sources by id - so narrowing the source list without
    narrowing that one too builds a registry naming a corpus it does not have.
    Re-validated rather than patched in place, on the same rule the probes
    already follow: if the narrowed registry would be illegal, the test should
    find out here rather than three stages later.
    """
    kept = {source.id for source in sources}
    return LexiconSources.model_validate(
        registry.model_dump(exclude_none=True)
        | {
            "sources": [source.model_dump(exclude_none=True) for source in sources],
            "spokenSources": sorted(kept & set(registry.spokenSources)),
        }
        | overrides
    )


__all__ = [
    "EXPECTED",
    "FIXTURES",
    "fixture_registry",
    "narrowed",
    "rebuild",
    "source_bytes",
]
