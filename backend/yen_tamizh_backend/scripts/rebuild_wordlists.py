"""Regenerate every per-Game derived wordlist from the published lexicon (Row 9).

    python -m yen_tamizh_backend.scripts.rebuild_wordlists

ONE command rebuilds ALL of them. Derived sets are build artifacts: never hand
edited, always reproducible, and always regenerated together so no Game's set is
left cut from a stale lexicon. Run it after a lexicon refresh, or after tuning a
selection in ``config/derived-wordlists.json``, and commit what it writes.

The lexicon META document is read ONCE and every registered set streams the
partitions its own selection allows, so a set that serves one class never opens
the files of another.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from yen_tamizh_backend.contracts.game_wordlist import GameWordlist
from yen_tamizh_backend.wordsmith import derive
from yen_tamizh_backend.wordsmith.artifact import write_artifact


def _repo_root() -> Path:
    # rebuild_wordlists.py -> scripts -> yen_tamizh_backend -> backend -> <root>
    return Path(__file__).resolve().parents[3]


def rebuild(registry_path: Path, repo_root: Path) -> list[tuple[Path, GameWordlist]]:
    """Rebuild every registered derived set; return each output path and payload."""
    registry = derive.load_registry(registry_path)
    meta_path = repo_root / registry.lexiconPath
    meta = derive.load_meta(meta_path)
    source = derive.describe_source(meta, meta_path, registry.lexiconPath)
    denied = derive.load_denylist(repo_root / registry.denylistPath).words()

    written: list[tuple[Path, GameWordlist]] = []
    for spec in registry.sets:
        rows = derive.read_rows(meta, repo_root, spec.selection.wordClasses)
        wordlist = derive.derive(meta, rows, source, spec, denied)
        out_path = repo_root / spec.out
        write_artifact(out_path, derive.render(wordlist))
        written.append((out_path, wordlist))
    return written


def _report(wordlist: GameWordlist, rel_out: str) -> str:
    """One line per set: what it kept, which gate stopped the rest, and its spread."""
    counters = wordlist.counters
    lengths = Counter(len(row.ezhuthu) for row in wordlist.words)
    spread = " ".join(f"{n}:{lengths[n]}" for n in sorted(lengths))
    strata = Counter(row.frequencyStratum for row in wordlist.words)
    quarters = " ".join(f"q{n}:{strata[n]}" for n in sorted(strata))
    shared = sum(1 for row in wordlist.words if row.anagramFanOut > 1)
    return (
        f"{wordlist.gameId}: rowsKept={counters.rowsKept} "
        f"outsideLength={counters.outsideLength} "
        f"outsideClass={counters.outsideClass} "
        f"outsideCategories={counters.outsideCategories} "
        f"outsidePos={counters.outsidePos} "
        f"belowAttestations={counters.belowAttestations} "
        f"belowFrequency={counters.belowFrequency} "
        f"withoutMeaning={counters.withoutMeaning} "
        f"denylisted={counters.denylisted} capped={counters.capped} "
        f"sharedFanOut={shared} lengths[{spread}] strata[{quarters}] -> {rel_out}"
    )


def main() -> None:
    root = _repo_root()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--registry",
        type=Path,
        default=root / "config" / "derived-wordlists.json",
        help="the derived-wordlist registry to read",
    )
    args = parser.parse_args()

    for out_path, wordlist in rebuild(args.registry, root):
        # Paths leaving the process are relative + POSIX (CLAUDE.md section 2).
        print(_report(wordlist, out_path.resolve().relative_to(root).as_posix()))


if __name__ == "__main__":
    main()
