"""Regenerate every per-Game derived wordlist from the ranked master (Row 9).

    python -m yen_tamizh_backend.scripts.rebuild_wordlists

ONE command rebuilds ALL of them. Derived sets are build artifacts: never hand
edited, always reproducible, and always regenerated together so no Game's set is
left cut from a stale master. Run it after a corpus refresh, or after tuning a
selection in ``config/derived-wordlists.json``, and commit what it writes.

The master is loaded ONCE and every registered set is cut from that one in-memory
copy, so adding the fifth Game costs a filter pass, not a fifth 12 MB parse.
"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from yen_tamizh_backend.contracts.game_wordlist import GameWordlist
from yen_tamizh_backend.corpus import derive
from yen_tamizh_backend.corpus.artifact import write_artifact


def _repo_root() -> Path:
    # rebuild_wordlists.py -> scripts -> yen_tamizh_backend -> backend -> <root>
    return Path(__file__).resolve().parents[3]


def rebuild(registry_path: Path, repo_root: Path) -> list[tuple[Path, GameWordlist]]:
    """Rebuild every registered derived set; return each output path and payload."""
    registry = derive.load_registry(registry_path)
    master_path = repo_root / registry.masterPath
    master = derive.load_master(master_path)
    source = derive.describe_source(master, master_path, registry.masterPath)

    written: list[tuple[Path, GameWordlist]] = []
    for spec in registry.sets:
        wordlist = derive.derive(master, source, spec)
        out_path = repo_root / spec.out
        write_artifact(out_path, derive.render(wordlist))
        written.append((out_path, wordlist))
    return written


def _report(wordlist: GameWordlist, rel_out: str) -> str:
    """One line per set: what it kept, why the rest went, and its length spread."""
    counters = wordlist.counters
    lengths = Counter(len(row.ezhuthu) for row in wordlist.words)
    spread = " ".join(f"{n}:{lengths[n]}" for n in sorted(lengths))
    shared = sum(1 for row in wordlist.words if row.anagramFanOut > 1)
    return (
        f"{wordlist.gameId}: rowsKept={counters.rowsKept} "
        f"outsideLength={counters.outsideLength} outsideBand={counters.outsideBand} "
        f"invalidWordFinal={counters.invalidWordFinal} capped={counters.capped} "
        f"sharedFanOut={shared} lengths[{spread}] -> {rel_out}"
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
