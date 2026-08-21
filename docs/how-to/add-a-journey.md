# Add a Journey

**Last Updated**: 2026-08-21

A [Journey](../concepts/journeys.md) is a curated, ordered path of levels, and it is DATA. Adding one is dropping a file and running one command; no Mode, no map, no schema and no Game moves. This is that loop.

## 1. Author the path

Write `datasets/journeys/<id>.json`. The file stem must be the Journey's own `id` - the id is what the Mode asks for and the stem is what it fetches, so a disagreement is a path that validates and cannot be opened.

```json
{
  "id": "my-path",
  "titleTa": "...",
  "theme": "light",
  "nodes": [
    { "id": "first-step", "gameId": "anagram", "difficulty": "easy", "unlockRule": "open" },
    { "id": "second-step", "gameId": "wordle", "difficulty": "easy", "unlockRule": "previous-complete" }
  ]
}
```

- `gameId` must be a Game registered in `config/daily-generator.json`, and `difficulty` must be a band THAT Game registers. Both are checked, loudly, at build time - a typo is an error, never a silently short path.
- `unlockRule` is `open` or `previous-complete`, and the first node must be `open` or the path has no entrance.
- `theme` is a design-system palette name (the `[data-theme]` axis).
- `titleTa` rides the file rather than `config/copy.json`, so a new path needs no new copy entry.

## 2. Build its boards

```bash
cd backend
python -m yen_tamizh_backend.scripts.build_journeys --journey my-path
```

This fills in every node's `payload` from the committed wordlists and rewrites the file in place. Omit `--journey` to rebuild every path. Each board is seeded by `<journeyId>|<nodeId>`, so the run is idempotent: re-running reproduces the same bytes, which is also the hand-edit gate - a payload corrected by hand does not survive the next run.

A word is never asked for twice inside one path. The ledger is journey-local: the bank is not consulted in either direction, because a path that avoided every word the Daily had served would stop being reproducible the moment the cron ran.

Read the diff. Then commit the file.

## 3. Point the Mode at it (only if it is the one players should land on)

`config/app-config.json`:

```json
"ui": { "enabledModes": ["daily", "journey"], "defaultJourney": "my-path" }
```

Bump the config's `version` and append a `changelog` entry in the same commit (CLAUDE.md section 11).

## What a new Journey does NOT cost

No entry in the Game registry, no branch in `JourneyMode.ts`, no case in `JourneyMap.svelte`, and no schema change. A Game refusing a band is the only thing that can fail, and it fails at build time with the list of bands that Game does register.

## See also

- [../concepts/journeys.md](../concepts/journeys.md) - what a Journey is, and the progression rule.
- [generate-the-daily-bank.md](generate-the-daily-bank.md) - the sibling bake, for the calendar-bound Mode.
- [add-a-derived-wordlist.md](add-a-derived-wordlist.md) - the sets a node's board is drawn from.
- [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) - the `journey` schema.
