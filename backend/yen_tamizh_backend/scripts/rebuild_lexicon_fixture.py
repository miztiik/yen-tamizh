"""Rebuild the committed fixture lexicon the integration gate compares against.

The gate in ``backend/tests/test_wordsmith_publish.py`` runs the whole pipeline
over the byte-exact fixture slices under ``datasets/fixtures/lexicon/`` and
byte-compares the result against ``datasets/fixtures/lexicon-expected/``. That
expectation has to be regenerated whenever a stage's output legitimately
changes - a new source, an edited authored batch, a classifier rule - and this
is the one command that does it, so the expectation is never hand-edited.

The workspace builder below is shared with the tests rather than copied into
them: the gate and the expectation it compares against have to be produced by
ONE piece of code, or they can drift apart in exactly the case the gate exists
to catch.

Run it, then READ THE DIFF. A change here is a change to what the pipeline
produces, and the diff is the review.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Any

from yen_tamizh_backend.contracts.lexicon_sources import LexiconSource, LexiconSources
from yen_tamizh_backend.wordsmith.enrich import load_config
from yen_tamizh_backend.wordsmith.extract import load_registry, sha256_of
from yen_tamizh_backend.wordsmith.llm_enrich import AUTHORED_SOURCE_ID
from yen_tamizh_backend.wordsmith.pipeline import run
from yen_tamizh_backend.wordsmith.publish import BY_CLASS, META_NAME, README_NAME

EXPECTED = Path("datasets") / "fixtures" / "lexicon-expected"
FIXTURES = Path("datasets") / "fixtures" / "lexicon"


def source_bytes(repo_root: Path, source: LexiconSource) -> Path:
    """The committed bytes a workspace should stage for ``source``.

    A fixture slice exists because a raw source is gitignored. The authored
    source is not: its bytes ARE the review artifact, so it has no acquisition
    ledger row, no fixture slice, and nothing to slice - the real file is always
    on disk and is what the pipeline must be exercised against.
    """
    if source.id == AUTHORED_SOURCE_ID:
        return repo_root / source.path
    return repo_root / FIXTURES / f"{source.id}.1x{Path(source.path).suffix}"


def fixture_registry(
    repo_root: Path, registry: LexiconSources, root: Path
) -> LexiconSources:
    """The real registry, re-pointed at fixture bytes copied under ``root``.

    Every source is enabled and every digest is recomputed from the copy, so the
    workspace is the REAL registry over REAL committed bytes at a smaller scale
    - not a hand-written stand-in for either (Holy Law #7).
    """
    entries: list[dict[str, Any]] = []
    for source in registry.sources:
        fixture = source_bytes(repo_root, source)
        staged = root / "sources" / fixture.name
        staged.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(fixture, staged)
        digest, size = sha256_of(staged)
        entries.append(
            source.model_dump(exclude_none=True)
            | {
                "path": f"sources/{fixture.name}",
                "sha256": digest,
                "bytes": size,
                "enabled": True,
            }
        )
    return LexiconSources.model_validate(
        registry.model_dump(exclude_none=True)
        | {"lexiconRoot": "out", "sources": entries}
    )


def rebuild(repo_root: Path, workspace: Path) -> list[Path]:
    """Run all four stages over the fixtures and copy the output into the repo."""
    registry = load_registry(repo_root / "config" / "lexicon-sources.json")
    config = load_config(repo_root / "config" / "wordhood.json")
    scoped = fixture_registry(repo_root, registry, workspace)
    run(
        scoped, config, workspace, workspace / "out" / "cache" / "lexicon.db", force=True
    )

    produced = workspace / "out"
    target = repo_root / EXPECTED
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    written: list[Path] = []
    for path in sorted((produced / BY_CLASS).rglob("*.ndjson")):
        landing = target / path.relative_to(produced)
        landing.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, landing)
        written.append(landing)
    for name in (META_NAME, README_NAME):
        shutil.copyfile(produced / name, target / name)
        written.append(target / name)
    return written


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workspace",
        type=Path,
        required=True,
        help="a scratch directory to run the pipeline in (it is written to freely)",
    )
    args = parser.parse_args()
    written = rebuild(root, args.workspace)
    for path in written:
        print(f"wrote {path.relative_to(root).as_posix()}")
    print(f"{len(written)} files - review the diff before committing", file=sys.stderr)


if __name__ == "__main__":  # pragma: no cover - operator entry point
    main()
