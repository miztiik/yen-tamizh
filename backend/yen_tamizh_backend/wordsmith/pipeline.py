"""The pipeline entry point: the four stages, in order, and nothing else (Row 11).

EXTRACT, STAGE, ENRICH and PUBLISH each own an artifact on disk, each has its
own CLI, and each is independently runnable, debuggable and restartable. This
module exists only so the whole run can be asked for in one command; it holds no
logic of its own, and it must not grow any. The moment sequencing knows
something the stages do not, a stage has stopped being runnable on its own -
which is the property ``docs/architecture/lexicon/pipeline.md`` opens with.

REVIEW is deliberately NOT sequenced here. It is a report over the derived zone
rather than a step that produces the next stage's input, and its output is
gitignored working material - so it stays a thing an operator asks for when they
want to read the residue, not a thing that runs because something else did.

The full run is an OPERATOR path (Row 11 decision 9). It reads hundreds of
megabytes of gitignored raw sources and takes the better part of an hour on a
developer laptop; CI runs type checks, the tests, and the fixture-pipeline
integration gate that drives these same four calls over the committed fixture
slices.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from yen_tamizh_backend.contracts.lexicon_sources import LexiconSources
from yen_tamizh_backend.contracts.wordhood import Wordhood
from yen_tamizh_backend.wordsmith.enrich import EnrichRun, enrich, load_config
from yen_tamizh_backend.wordsmith.extract import SourceResult, load_registry
from yen_tamizh_backend.wordsmith.extract import extract as extract_stage
from yen_tamizh_backend.wordsmith.publish import PublishRun
from yen_tamizh_backend.wordsmith.publish import publish as publish_stage
from yen_tamizh_backend.wordsmith.stage import StageRun, store_path
from yen_tamizh_backend.wordsmith.stage import stage as stage_stage


@dataclass(frozen=True, slots=True)
class PipelineRun:
    """What each stage did, kept apart so a failure names the stage it was in."""

    extracted: list[SourceResult]
    staged: StageRun
    enriched: EnrichRun
    published: PublishRun

    def notes(self) -> list[str]:
        return [
            f"extract: {len(self.extracted)} sources",
            f"stage: {len(self.staged.applied)} applied in {self.staged.seconds:.1f}s",
            f"enrich: {self.enriched.rows} signal rows, "
            f"{self.enriched.classified} verdicts",
            *self.published.notes(),
        ]


def run(
    registry: LexiconSources,
    config: Wordhood,
    repo_root: Path,
    db: Path | None = None,
    force: bool = False,
    workers: int | None = None,
) -> PipelineRun:
    """EXTRACT, then STAGE, then ENRICH, then PUBLISH."""
    path = store_path(registry, repo_root) if db is None else db
    return PipelineRun(
        extracted=extract_stage(registry, repo_root, force=force),
        staged=stage_stage(registry, repo_root, path),
        enriched=enrich(registry, config, path, workers=workers),
        published=publish_stage(registry, repo_root, path),
    )


def _repo_root() -> Path:
    # pipeline.py -> wordsmith -> yen_tamizh_backend -> backend -> <repo root>
    return Path(__file__).resolve().parents[3]


def main() -> None:
    root = _repo_root()
    parser = argparse.ArgumentParser(
        description="Run the whole lexicon pipeline: extract, stage, enrich, publish."
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=root / "config" / "lexicon-sources.json",
        help="the lexicon source registry every stage reads",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=root / "config" / "wordhood.json",
        help="the word-hood knobs ENRICH reads",
    )
    parser.add_argument("--db", type=Path, default=None, help="the store to build")
    parser.add_argument(
        "--root", type=Path, default=root, help="the repository root to work under"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-extract every source even when its bytes are unchanged",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="processes to score the neighbour search across (default: every core)",
    )
    args = parser.parse_args()

    completed = run(
        load_registry(args.registry),
        load_config(args.config),
        args.root,
        args.db,
        force=args.force,
        workers=args.workers,
    )
    for note in completed.notes():
        print(note)


if __name__ == "__main__":  # pragma: no cover - operator entry point
    main()
