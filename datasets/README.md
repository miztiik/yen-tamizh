# datasets/

**Last Updated**: 2026-08-13

Raw and cleaned source corpora the backend reads at build time (`CLAUDE.md`
section 3 topology). The Tamil vocabulary, frequency lists, and the curated
master + per-Game wordlists live here.

`datasets/` is **never read directly by the game**. The backend ingests these
sources, ranks and curates them, and bakes only the finished puzzle bank + level
data into `frontend/public/`; the frontend reads that baked output, nothing here
(Holy Law #1, section 1a data-delivery model).

## Layout

| Path | What it holds |
| --- | --- |
| [`corpus/`](corpus/README.md) | The raw word sources the ingest streams. **Gitignored** - hundreds of MB of third-party lists. |
| `wordlists/master/words_ranked.json` | The ranked, ezhuthu-segmented master wordlist the ingest generates (Row 8). Committed. |
| `wordlists/by-length/` | The curated `game_words_{2..6}_letter.json` sets carried over from `yen-tamizh_OLD`, pending the derived-set pipeline (Row 9). |
| `fixtures/` | Shared test fixtures - the ezhuthu golden corpus and the contract valid/invalid payloads both runtimes assert against. |

## See also

- [`corpus/README.md`](corpus/README.md) - the raw-source directory and how to repopulate it.
- [`../docs/how-to/add-a-corpus-source.md`](../docs/how-to/add-a-corpus-source.md) - adding a word source in three steps.
- [`../CLAUDE.md`](../CLAUDE.md) - section 3 (repository topology), Holy Law #1.
- [`../TODO/README.md`](../TODO/README.md) - section 3.5 (data + generation pipeline).
