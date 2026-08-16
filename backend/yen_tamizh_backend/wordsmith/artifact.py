"""How a committed row-per-line artifact is rendered and fingerprinted.

The large committed documents of small uniform rows - the ranked master wordlist
(Row 8) and the per-Game derived sets (Row 9) - are reviewed as git diffs. They
therefore share one rendering rule and one fingerprinting rule, defined here once
rather than copied per writer: a duplicated byte-determinism rule is exactly the
kind that drifts silently, and a drifted one turns every regeneration into a
whole-file diff.

It lives in ``wordsmith`` rather than in ``corpus`` because ``corpus`` is retired
in row 13 while the derived layer that reads the lexicon keeps writing through
this renderer; the retiring package imports it on its way out, never the reverse.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

# 64 KB: large enough that hashing a 12 MB artifact is a handful of reads, small
# enough that peak memory does not track file size.
_CHUNK = 1 << 16

_ROWS_PLACEHOLDER = "__ROWS__"


def render_document(payload: dict[str, Any], rows_key: str) -> str:
    """Render ``payload`` with a pretty header and one compact row per line.

    ``json.dumps`` alone gives either a multi-megabyte single line (unreadable,
    and a whole-file churn on every regeneration) or a fully indented file
    several times larger. Splicing the compact rows into the indented header
    keeps the header greppable, the git delta proportional to the rows that
    actually changed, and the bytes reproducible.

    ``rows_key`` names the top-level list of rows; every other key is rendered
    normally. Output is deterministic - sorted keys, 2-space indent, trailing
    newline - so the same input always produces the same bytes.
    """
    spliced = dict(payload)
    rows: list[Any] = spliced[rows_key]
    spliced[rows_key] = _ROWS_PLACEHOLDER
    text = json.dumps(spliced, ensure_ascii=False, indent=2, sort_keys=True)
    token = json.dumps(_ROWS_PLACEHOLDER)
    if text.count(token) != 1:
        raise ValueError(f"rows placeholder is not unique in the {rows_key!r} payload")
    if rows:
        body = (
            "[\n"
            + ",\n".join(
                "    " + json.dumps(row, ensure_ascii=False, sort_keys=True)
                for row in rows
            )
            + "\n  ]"
        )
    else:
        body = "[]"
    return text.replace(token, body) + "\n"


def sha256_of(path: Path) -> tuple[str, int]:
    """Return a file's sha256 digest and its size in bytes, reading in chunks."""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(_CHUNK):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def write_artifact(path: Path, text: str) -> None:
    """Write a rendered artifact, creating its directory.

    ``newline="\\n"`` forces LF on every OS (``Path.write_text`` would translate
    to CRLF on Windows), so a Windows and a Linux run commit the same bytes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
