"""Export the registered contract models to flat ``schemas/<name>.schema.json``.

Output is DETERMINISTIC - sorted keys, 2-space indent, trailing newline, ASCII
(``json.dumps`` escapes non-ASCII) - so the CI drift gate reproduces
byte-identical files across machines and Python versions. Run it with::

    python -m yen_tamizh_backend.contracts.export
"""

from __future__ import annotations

import json
from pathlib import Path

from yen_tamizh_backend.contracts import REGISTRY
from yen_tamizh_backend.contracts.base import SchemaModel


def render(model: type[SchemaModel]) -> str:
    """Return the canonical JSON text for one model's schema (deterministic)."""
    return json.dumps(model.json_schema(), indent=2, sort_keys=True) + "\n"


def export_all(schemas_dir: Path) -> list[Path]:
    """Write every registered model's schema into ``schemas_dir``; return paths."""
    schemas_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for model in REGISTRY:
        path = schemas_dir / f"{model.schema_name()}.schema.json"
        # newline="\n" forces LF on every OS (Path.write_text would translate to
        # CRLF on Windows), so the CI drift gate compares byte-identical output.
        path.write_text(render(model), encoding="utf-8", newline="\n")
        written.append(path)
    return written


def _repo_root() -> Path:
    # export.py -> contracts -> yen_tamizh_backend -> backend -> <repo root>
    return Path(__file__).resolve().parents[3]


def main() -> None:
    root = _repo_root()
    for path in export_all(root / "schemas"):
        # Paths leaving the process are relative + POSIX (CLAUDE.md section 2).
        print(f"wrote {path.relative_to(root).as_posix()}")


if __name__ == "__main__":
    main()
