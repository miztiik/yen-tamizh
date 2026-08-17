# UI Shell

**Last Updated**: 2026-08-17

The game chrome - the frame that hosts every [Game](games.md) and [Mode](modes.md) - stated as vocabulary. The shell is drawn once and reused; a Game never draws chrome and the chrome never knows a Game's rules. This is the concept tier; the shell code lands with its own row, and this page fixes the slots and components that row builds to. Chrome craft is owned by Jony ([../../.github/agents/jony.agent.md](../../.github/agents/jony.agent.md)); the tokens and animation it uses live in [design-system.md](design-system.md).

## SessionShell slots

The shell is one `SessionShell` with four named slots:

| Slot | Holds | Owner |
| --- | --- | --- |
| `header` | Identity, day/level nav, timer or countdown, settings entry. | The shell. |
| `rail` | Secondary controls and status; collapses to a bottom sheet on mobile. | The shell. |
| `stage` | The puzzle surface itself. | **The Game** - the only slot a Game renders into. |
| `footer` | The toolbar (hint, check, shuffle, undo) and progress. | The shell. |

Responsive behaviour lives in the shell once (the rail becoming a bottom sheet on a phone), never per Game - the DRY-UI invariant. A Game that tried to draw its own header or footer would be a smell.

## SessionRunner and the Game registry

The **SessionRunner** is the small piece that walks a Mode's `Session`: it pulls each item with `next()`, looks the item's `gameId` up in the **Game registry** (`gameId -> component + lazy loader`), mounts that Game into `stage`, shows the inter-item "X of N" and the end-of-session summary, and emits the session and telemetry events on the Mode's behalf ([telemetry.md](telemetry.md)). Per-Game code is lazy-loaded through the registry so a Game's bytes arrive only when first opened, keeping the shell light (Holy Law #2, [principles.md](principles.md)).

The runner is also the SOLE producer of `SessionResult`, and that result carries `items`: one entry per word the session resolved, in play order, each with the word, its optional already-rendered `meaning` and `translationEn`, and a `solved` flag. The summary reads that array and never `SessionItem.payload`, which is typed `unknown` - the runner reads the three display strings structurally, so it still never branches on which Game it is hosting. The array is part of the persisted session state, or a player who reloads mid-day would reach a summary missing the words they already played.

## StorageService

**StorageService** is the *only* writer to `localStorage` and `IndexedDB`. Games and Modes never touch storage directly; they hand state to the runner, which persists it. The save key is recomputed on read from its value fields (`date | modeId | gameId | packId`), never trusted from the payload - the derived-key rule in [../agents/guardrails.md](../agents/guardrails.md). The save is a persisted surface with a schema ([../architecture/contracts/schemas.md](../architecture/contracts/schemas.md)); it is the one migrating surface (a save from yesterday must still load today).

It also owns the **streak**, which ticks once per COMPLETED day - not per item, and not again when a finished day is re-opened. The idempotence comes from a `lastStreakDay` marker rather than `lastPlayed`, which moves on every write; a skipped day restarts the run at 1, because a streak that survives a gap is not a streak. The tick happens in the Daily screen when the runner reports the day complete, and emits `streak.updated {before, after}`.

## Bus and logger by context

Every Game and Mode is handed an event bus and a structured logger through context - no `console.log`, no global singleton in game code. The bus is the one from [core-loop.md](core-loop.md); the logger writes the [telemetry](telemetry.md) envelope.

## Screens

- **Home** - the Mode's own chrome: Daily's month calendar path, [Journey](journeys.md)'s winding path, Infinite's single start node with a difficulty picker, Time Trial's start-a-run node. The default view lets the player play; 95% of players never open settings (Jony worldview #1). What ships today is the Mode picker itself: one card per Mode in the catalog, the live ones (from `ui.enabledModes`) as real buttons that start play in one tap, the rest as static cards marked "coming soon". They are deliberately NOT disabled buttons - a dead control invites a tap and then punishes it, while a card that is plainly not a button never lies. The player's current streak sits under the title when there is one to brag about.
- **Session** - the SessionRunner: the current Game in `stage`, progress in `footer`, day/timer in `header`, an inter-item screen between items.
- **Summary** - the end-of-session result: score, streak, a share card designed to look good in a screenshot, and a countdown to the next puzzle ([difficulty-and-scoring.md](difficulty-and-scoring.md)). It takes the WHOLE screen rather than a panel inside the stage: the win moment is the reward, and it has to be worth a screenshot (Player worldview #8). Below the stats it lists the day's WORDS - Tamil word, then its Tamil meaning, then, demoted to `font-display text-text-tertiary` with `lang="en"`, its English translation. The stats stay above because they are the glance and they hold the screenshot composition; the words sit last because they are the dwell content and sitting above the exit is what buys the read. A word the lexicon has nothing to say about renders alone rather than beside an empty slot, and a word the player LOST still shows its meaning - hiding it would punish twice and break the promise that a day teaches three words. No meaning is ever badged with how it was authored.
- **Settings** - sound, appearance, and a credits view reachable in two taps (attribution is UX, Jony worldview #6).

## Component discipline

Components are metadata-driven and generic, not per-screen bespoke (Jony worldview #4): one tile component skinned by its data, one result card, one toolbar. Colour is one signal among several - a difficulty marker carries a number or glyph, not only a tint (Jony worldview #8; this is visual clarity, not a11y tooling). All icons are [glyphs](design-system.md) referenced by id (Holy Law #10). Chrome is styled with Tailwind; the `stage` internals are the Game's own concern, never styled by the shell.

A surface with exactly one call site is written INLINE, not extracted: there is one summary in the app, so its word list lives in the summary screen rather than in a generic list component nothing else mounts (CLAUDE.md section 10 - no pre-creating modules for later).

## See also

- [core-loop.md](core-loop.md) - the verb and bus the shell hosts.
- [games.md](games.md) - the Game contract that owns only `stage`.
- [modes.md](modes.md) - the Mode that supplies the Session the runner walks.
- [journeys.md](journeys.md) - the winding-path home the shell draws.
- [difficulty-and-scoring.md](difficulty-and-scoring.md) - the summary and streak the shell shows.
- [design-system.md](design-system.md) - the tokens, state classes, and glyphs the chrome uses.
- [telemetry.md](telemetry.md) - the envelope the shell's logger writes.
- [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) - the save surface StorageService owns.
