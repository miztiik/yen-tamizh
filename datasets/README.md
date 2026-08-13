# datasets/

**Last Updated**: 2026-07-29

Raw and cleaned source corpora the backend reads at build time (`CLAUDE.md`
section 3 topology). The Tamil vocabulary, frequency lists, and the curated
master + per-Game wordlists live here.

`datasets/` is **never read directly by the game**. The backend ingests these
sources, ranks and curates them, and bakes only the finished puzzle bank + level
data into `frontend/public/`; the frontend reads that baked output, nothing here
(Holy Law #1, section 1a data-delivery model).

The corpus ingest and the curated wordlists land in later rows - this directory
is a placeholder until then.

## See also

- [`../CLAUDE.md`](../CLAUDE.md) - section 3 (repository topology), Holy Law #1.
- [`../TODO/README.md`](../TODO/README.md) - section 3.5 (data + generation pipeline).
