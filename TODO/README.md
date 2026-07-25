# yen-tamizh - System Design Proposal

**Last Updated**: 2026-07-24
**Status**: Proposal / pre-alpha (no game code yet). Not an execution-ready plan-doc - it is the vision + architecture this repo should build toward. Once accepted, the durable parts move into `CLAUDE.md`, `docs/concepts/`, and `docs/architecture/`, and the buildable parts become dated `TODO/<YYYYMMDD>-<slug>-plan.md` plan-docs per [../docs/how-to/author-a-plan.md](../docs/how-to/author-a-plan.md).

> This document distills three sibling repos (`yen-doku`, `yen-neram`, `yen-cinthanai`) and the previous-generation `yen-tamizh_OLD` into one proposal: what to learn, and what to build. It is a proposal because a system design has real rejected alternatives, cross-system consequences, and non-trivial reversal cost (CLAUDE.md Holy Law #4) - so it argues, it does not just list.

---

## 0. TL;DR

yen-tamizh is a small, daily **Tamil word-puzzle game**: a static PWA on GitHub Pages, no server, no accounts, no ads, no tracking. A build-time Python pipeline generates and validates puzzles; a Svelte + Vite + Tailwind frontend renders and plays them; the browser persists progress locally. The product is not one game - it is a **shell that hosts many word Games, framed by several Modes, threaded into player Journeys**:

- **Games** (the verb, what you do): Word Ladder, Anagram, Missing Letters, Wordle-style, Word Search, Crossword.
- **Modes** (how a session is framed): Daily, Journey/Path, Infinite, Time Trial.
- **Journeys** (the path a player walks): a curated, ordered map of levels - the winding-path home screen - so different players can take different routes through the same Games.

Everything the three siblings converged on - the engineering contract, the Diataxis docs, the CSS-token + state-class design system, the glyph rule, the two-runtime backend/frontend split - is adopted and adapted for Tamil. The Tamil twist that touches every layer: the atomic unit is the **ezhuthu (grapheme cluster)**, never the Unicode codepoint.

---

## 1. What each sibling teaches us (distillation)

The single most important finding: **all three siblings, and the new yen-tamizh scaffold, already share one engineering contract.** They are the same project wearing different game mechanics. We do not invent a new architecture; we specialise the shared one for Tamil words.

| Repo | Genre | Stack | The one thing to steal |
| --- | --- | --- | --- |
| `yen-doku` | Daily Sudoku (Classic + Gattai) | Vanilla JS, Python CI generator, static `docs/` on Pages | The **CSS design-token + state-class + keyframe** system, and the **date-seeded, unique-solution-validated** generator that fails CI on a bad puzzle. |
| `yen-neram` | Multi-game shell (first game 5-in-a-row) | TS monorepo (pnpm), `size-limit` bundle budgets | The **static multi-game shell** idea itself - one shell, many games, lazy-loaded - which is exactly our Mode x Game x Journey spine. |
| `yen-cinthanai` | Daily logic puzzle | Svelte + Vite + TS front, Python OR-Tools `tools/` | The **newest, richest realization of the contract**: `config/` + `datasets/` + `schemas/`, glyph-only difficulty, the command bar, the persona roster. This is our template. |
| `yen-tamizh_OLD` | Daily Tamil word puzzle (Anagram) | Vanilla TS + DOM + Tailwind, Python generator | The **Mode x Game architecture** in full: `SessionShell` slots, Game registry, pure-mechanic Games, first-class hints, the telemetry envelope, and the winding-path home concept. |

### 1.1 Product ethos (identical across all four)

- Static-first. A daily ritual, not a product. Language is a public good - free, no ads, no tracking, no accounts.
- Non-goals are load-bearing and explicit: no production backend, no login, no push, no runtime analytics SDK, no monetisation patterns (ads, IAP, timers, lives-with-IAP, pay-to-skip, streak-savers).
- Persistence is browser-only: `localStorage` for small flags + streak, `IndexedDB` for cached puzzle/level data (offline replay). Clearing the browser clears the user.

### 1.2 Backend / frontend separation (two runtimes, strict boundary)

This is the spine of every sibling and must be ours:

```
AUTHOR (you, locally / in CI)                GITHUB (the storage layer)             PLAYER (browser)
  tools/ (Python, BUILD-TIME ONLY)             frontend/dist -> GitHub Pages          Svelte app loads shell
    ingest  raw corpora -> clean wordlist        (static HTML/JS/CSS)                   computes today's date
    rank    wordlist -> difficulty/freq tiers   data/puzzles/ -> raw.githubusercontent   fetches puzzle (CDN) or
    generate ranked list -> puzzle JSON           .com (free CDN)                          reads level data (bundle)
    solve/validate (unique solution, gate CI)                                            caches in IndexedDB
              |  commits JSON to git                The frontend bundle contains          persists progress + streak
              v                                      ZERO generator logic.                 emits structured events
```

- **Python runs only in CI / locally** (generate, solve, validate, score, bake glyphs). It never runs in the browser.
- **JavaScript runs only in the browser** (render, interact, persist). It is never authoritative over puzzle correctness - the committed JSON is the source of truth.
- Frontend is a **stateless consumer** (reads only); backend is a **stateless producer** (writes only to a frozen data location). No live API ever crosses the boundary.
- **Determinism**: generation is date-seeded and idempotent - same input, same output - which makes bugs and tests tractable. A puzzle that fails validation fails CI and never ships.

### 1.3 The engineering contract (14 sections, already in our `CLAUDE.md`)

All four repos carry the same non-negotiable contract. Cite Holy Laws by number:

1. Static-first production. 2. The player's phone is the architecture (mid-tier Android, patchy 4G, input-to-photon <50ms, 60fps). 3. Contracts before logic (typed schema before code). 4. docs/ = agent memory; a decision lives on the page it impacts (no ADR tree). 5. Structural fixes only. 6. No hardcoding (tunables in `config/`). 7. No mocks unless asked. 8. Open source first (name the bytes + the beneficiary). 9. Tests ship with the feature. **10. Use Glyphs for all icons.**

Plus: Correction Levels 0-5 (Level 5 = core design / save format = pause for sign-off), Diataxis docs, schema versioning with read-side migration, browser-smoke verification, four test tiers (unit / contract / integration / e2e), and the five-persona roster (Player, Jony, Palm, Fowler, Carmack).

### 1.4 Docs discipline (Diataxis, decision-on-the-page)

- Four tiers: `architecture/` (why designed this way), `how-to/` (do a task), `concepts/` (what a term means), `reference/` (exact values/contracts). Max depth `docs/<tier>/<topic>/<file>.md`.
- One concept defined once; everywhere else links to it. Every doc: H1 + `Last Updated` + "See also".
- No `decisions/` directory. A choice that clears the Holy Law #4 bar becomes a `## Design rationale` / `## Rejected alternatives` section on the living doc it impacts. Git history is the change log.
- ASCII-only for punctuation and structure (`-`, `->`, `>=`, "section"). Tamil script is allowed where it is the content (game names, example words), exactly as `yen-tamizh_OLD` docs did.

### 1.5 CI / automation (the three workflows already stubbed here)

Every sibling ships the same trio, matching our existing `.github/workflows/{ci,daily,deploy}.yml`:

| Workflow | When | What |
| --- | --- | --- |
| `ci.yml` | every PR + push | typecheck + unit/contract/e2e (frontend), mypy + pytest (tools), schema validation |
| `daily.yml` | cron (00:05 UTC) | generate the day's puzzle(s), validate, commit |
| `deploy.yml` | push to main | build frontend, deploy to Pages (base-path aware, SPA `404.html` fallback) |

---

## 2. The design system to steal (CSS event-driven architecture, animation, color, glyphs)

This is where the siblings are most worth copying line-for-line. `yen-doku`'s `style.css` is the reference implementation; we port its ideas into Svelte + Tailwind.

### 2.1 The "CSS event-driven" pattern

The state of the DOM is the single source of truth for the view. Nothing is imperatively styled; **an event mutates state, state is reflected by toggling classes and data-attributes, and CSS reacts declaratively.**

```
input / timer tick / solver check
        |  emit on the event bus (same bus that feeds telemetry)
        v
   reducer updates the one state object
        |  Svelte reactivity (class:selected={..}, data-state={tile.state})
        v
   DOM node gains/loses a state class or data-attr
        |  CSS transition on the base rule OR a keyframe animation class
        v
   pixels move (transform + opacity only - never layout props)
```

Concrete patterns observed in `yen-doku` to adopt:

- **State classes**: `.cell.selected`, `.cell.conflict`, `.cell.correct`, `.grid.completed`, `.grid.loading`, `.grid.revealed`. JS toggles the class; CSS owns the look.
- **Data-attribute styling**: `.tab[data-level="3"].active { background: var(--diff-3); }`, and tooltips with zero JS via `[data-tooltip]:hover::after { content: attr(data-tooltip); }`.
- **No inline styles** except genuinely dynamic values (a drag translate, a progress width). Everything else is a token or a class.
- In Svelte this is idiomatic: `class:correct`, `data-state`, scoped component `<style>` over a global token layer. Svelte's reactivity IS the "JS toggles classes" pattern, made declarative and leak-free.

### 2.2 Design tokens in `:root`; theming by override

`yen-doku` puts every color, space, radius, shadow, font, easing, and duration in `:root` as a CSS custom property named **by purpose**, then overrides the token values for dark mode. We do the same, and add a `[data-theme]` axis so a Journey can carry its own palette:

```css
:root {
  --font-display: 'Mukta Malar', 'Nunito', sans-serif;   /* Tamil-capable display */
  --font-mono: 'Noto Sans Tamil', system-ui, sans-serif; /* tile / grid glyphs */
  --space-xs..xl; --radius-sm..full;
  --bg; --bg-elevated; --text-primary/secondary/tertiary;
  --accent; --success; --warning; --danger;
  --diff-1..4;                 /* easy->extreme ramp: green -> yellow -> orange -> red */
  --tile-empty/present/correct/absent;   /* wordle-style feedback */
  --ease: cubic-bezier(0.25,0.1,0.25,1);
  --ease-spring: cubic-bezier(0.175,0.885,0.32,1.275);
  --dur-fast..slow;
}
@media (prefers-color-scheme: dark) { :root { /* override the same names */ } }
[data-theme="sangam"] :root { /* a Journey's palette */ }
```

Tailwind's `theme.extend` mirrors these tokens so utilities (`bg-accent`, `text-danger`) resolve to `var(--...)` - one source of truth, not two. (This exact "every var has a Tailwind mirror or is exempt" gate is a known pattern in the `yen-gov` sibling and worth a contract test.)

### 2.3 Animation vocabulary (Jony + Carmack own the bounds)

- **transform + opacity only.** Never animate a layout-triggering property (CLAUDE.md anti-pattern). GPU-friendly, holds 60fps on the target phone.
- **Spring easing** for anything that should feel alive (`--ease-spring`); linear/ease for utility fades.
- **`prefers-reduced-motion` is a hard kill-switch** - a full media query that zeroes durations and disables confetti. Respecting it is a requirement, not a nicety.
- The named keyframe set to port: `pop`/`glow` (hint reveal), `flip`/`shake` (wordle guess correct/invalid), `victoryPulse` + `confettiFall` + `trophyBounce` (win), `toastIn` / `modalIn` / `fadeIn` (chrome), `shimmer` (skeleton load), `gradientShift` (animated title). Tune Word-Ladder its own "rung climb" transition.

### 2.4 Glyphs (Holy Law #10)

- All icons are **vector glyphs referenced by id from a generated manifest** (`frontend/public/assets/glyphs/index.json`), never inline SVG, never a hardcoded path, never a PNG. `tools/` bakes the glyph pack at build time; the frontend reads only the manifest.
- `yen-cinthanai` ships a **glyph-only difficulty** indicator and a compact command bar - both good models for our toolbar (undo, hint, check, shuffle, note).
- Mascot opportunity (from `yen-tamizh_OLD` Phase 8 and the One More Letter reference): a Tamil letter with eyes (e.g. an anthropomorphic "ஓ") as the Journey guide. Inline SVG, themeable, tiny.

---

## 3. Proposed architecture for yen-tamizh

### 3.1 The three axes (locked vocabulary)

Use these exact identifiers in code, schemas, docs, and UI copy. Two orthogonal axes from `yen-tamizh_OLD`, plus a data dimension:

| Axis | Identifier | Meaning | Values |
| --- | --- | --- | --- |
| **Mode** | `modeId` | How a session is framed - what the player picks | `daily`, `journey`, `infinite`, `time-trial` |
| **Game** | `gameId` | The puzzle mechanic - the verb | `word-ladder`, `anagram`, `missing-letters`, `wordle`, `word-search`, `crossword` |
| **Pack** | `packId` | The content/language pack a Game draws from | `ta-core` (Tamil) now; other packs later |

A play session = **one Mode x one-or-more Games x a Pack.** A **Journey** is a Mode whose Session is a curated, ordered path of levels (the winding-path map) - as opposed to Daily (calendar), Infinite (endless anti-repeat), or Time Trial (sprint).

### 3.2 Game catalog

Every Game is a **pure mechanic**: it receives a `payload` + a `GameContext`, renders into the `stage` slot only, emits standard events, never reads global config beyond its payload, never writes storage directly, and round-trips its state (`getState`/`restoreState`) so a mid-puzzle reload is recoverable. Each carries an optional first-class `hints[]` array (`{ kind, text, cost }`).

| `gameId` | Tamil (working name) | Mechanic | Tamil-specific note |
| --- | --- | --- | --- |
| `word-ladder` | `ezhuthu ' etru` (ஒரு எழுத்து ஏற்று, "add one letter") | Add exactly one ezhuthu and rearrange to reach the next valid word (AS -> SEA -> CASE ...). | Ladder rungs are ezhuthu-count, not codepoint-count. See section 6. |
| `anagram` | `sol kalaippu` (சொல் கலைப்பு) | Unscramble ezhuthu tiles into the target word. | Ported directly from `yen-tamizh_OLD`. |
| `missing-letters` | `idaiveli nirappu` (இடைவெளி நிரப்பு) | Fill the blanked ezhuthu(s) of a partially shown word. | Blank whole ezhuthu, not half a cluster. |
| `wordle` | `sol yugi` (சொல் யூகி) | Guess an N-ezhuthu word in N tries; per-tile present/correct/absent feedback. | "Letter" = ezhuthu; keyboard is an ezhuthu picker (uyir + mei + uyirmei). |
| `word-search` | `sol thedal` (சொல் தேடல்) | Trace hidden words in an ezhuthu grid (8 directions). | Grid cells are ezhuthu; tracing is drag/keyboard. |
| `crossword` | `sorkatam` (சொற்கட்டம்) | Fill a mini crossword from clues; entries interlock on shared ezhuthu. | Interlock is on ezhuthu identity. Build-time solver (`tools/`) places words. |

### 3.3 Mode catalog

Every Mode **owns session framing** (builds a `Session` with `next()`, `totalItems`, `puzzleDate`), reads config instead of hardcoding, never renders DOM (the shell does), and emits `mode.session.started` / `mode.session.completed` via the runner.

| `modeId` | Tamil | Session shape | Home-screen chrome |
| --- | --- | --- | --- |
| `daily` | `indraya puthir` (இன்றைய புதிர்) | Today's committed playlist of N items (mix config-driven). One streak tick per completed day. Shareable result card + "next puzzle in HH:MM" countdown. | Month calendar path (today highlighted; past = done/missed; future = locked). |
| `journey` | `payanam` (பயணம், "journey") | A curated, ordered list of levels from a `journey` definition (a themed pack: Beginner's Ladder, Sangam words, place-names...). Progress unlocks the next node. | The winding-path map with numbered nodes + mascot guide (Phase-8 motif). |
| `infinite` | `mudivillaa` (முடிவில்லா, "endless") | Lazy stream, anti-repeat over an LRU window (from `config`), difficulty-bucket pickable. | A single "start" node; difficulty picker (glyph-only). |
| `time-trial` | `nera saval` (நேர சவால், "time challenge") | As many items as fit in `config.timeTrial.durationSec`; local-only best runs. | A single "start a run" node + countdown in the header slot. |

### 3.4 Frontend architecture (Svelte + Vite + Tailwind)

Adopt the `yen-tamizh_OLD` shell model wholesale, expressed in Svelte:

- **One `SessionShell` with named slots** (`header`, `rail`, `stage`, `footer`). Games own only `stage`. Responsive behaviour (rail collapses to a bottom sheet on mobile) lives in the shell once, never per Game. (This is the DRY-UI invariant.)
- **`SessionRunner`** (~100 lines) walks the Session, hands each item to the right Game via a **Game registry** (`gameId -> component + loader`), shows inter-item "X of N" and the end-of-session summary, and emits session/telemetry events on the Mode's behalf.
- **`StorageService`** is the only writer to `localStorage` / `IndexedDB`. Save `dayKey` is recomputed on read from its value fields (`date|modeId|gameId|packId`), never trusted from the payload (matches the guardrails' derived-key rule).
- **Event bus + structured logger** given to every Game/Mode via context - no `console.log`, no global singletons in game code.
- **SPA routing + PWA**: base-path aware (`import.meta.env.BASE_URL`), `404.html` == `index.html` for deep links, service worker precaches the shell + opened-game chunks; Journey/theme art is a runtime (non-precached) asset. (Already specified in [../docs/how-to/ship-to-github-pages.md](../docs/how-to/ship-to-github-pages.md).)
- **Code-split per Game** so the shell stays light and a Game's bytes load only when first opened (the `yen-neram` multi-game-shell lesson; propose a modest bundle budget - see section 7, open question O3).

### 3.5 Data + generation pipeline (`tools/`, Python)

- **Corpus -> curated wordlists.** Tamil vocabulary is finite and the gameplay-relevant subset is small; curate it once. A streaming ingest (never `json.load` a multi-MB corpus) produces a frequency-ranked master list, then per-Game derived sets (anagram-friendly, wordle-friendly 5-ezhuthu, ladder-reachable, search-placeable, crossword-placeable). This is the `yen-tamizh_OLD` "data consolidation" epic.
- **Generators are idempotent pure functions of their inputs**, date-seeded for Daily. Each writes puzzle JSON to the frozen data location and updates an index.
- **Validation gates CI**: a generated puzzle that is unsolvable, non-unique (where uniqueness applies, e.g. crossword), or malformed fails CI and never ships (the `yen-doku` discipline).
- **Ezhuthu segmentation is a shared library** used by both `tools/` (to build/validate) and the frontend (to render/score). One implementation, one test suite. See section 6.

### 3.6 Persisted schemas (contracts before logic)

Each gets a typed schema in `schemas/` with a `schemaVersion` integer + an `evolution` array before any logic is written (Holy Law #3, and the guardrails' schema rules):

- `app-config` - all tunables (playlist length + mix, hint visibility per Game, infinite LRU window, time-trial duration, enabled Modes/Games).
- `puzzle-file` - the Daily playlist file (array of `{ gameId, packId, difficulty, payload, hints? }`).
- `journey` - a Journey definition (ordered nodes, theme, unlock rule).
- One payload schema per Game: `word-ladder-puzzle`, `anagram-puzzle`, `missing-letters-puzzle`, `wordle-puzzle`, `word-search-puzzle`, `crossword-puzzle`.
- `game-wordlist` / `master-wordlist` - the curated data the generators consume.
- `progress-record` / `save` - the browser-owned save format (the one migrating surface).
- `event-envelope` - the telemetry shape (section 3.7).
- `asset-manifest` / `glyph-manifest` - the baked glyph + asset index.

### 3.7 Telemetry (structured events, no network sink)

Port the `yen-tamizh_OLD` envelope verbatim: `{ ts, src, v, session, name, level, ctx, data }`. Standard names (`app.started`, `puzzle.started`, `puzzle.attempt.submitted`, `puzzle.hint.used`, `puzzle.completed`, `puzzle.abandoned`, `streak.updated`, `mode.session.started/completed`). **No network sink** - dev logs to console, prod ring-buffers in memory for `window.__yt_dump()`. This is the debugging + replay backbone and the same bus that drives the CSS-event-driven view (section 2.1). A new Game is "wired up" the moment it emits the standard events - no central switch statement.

---

## 4. The Word Ladder journey (the playonemoreletter.com reference)

The reference (playonemoreletter.com) is the clearest single "journey" to model, so it gets its own section.

**The mechanic** (observed): start from a 2-letter word; each rung **adds exactly one letter and may rearrange all letters** to form the next valid word, e.g. `AS -> SEA (+E) -> CASE (+C) -> ACRES (+R) -> SCARED (+D) -> SCARRED (+R)`. Complete all rungs before the timer runs out. The completion screen ("A perfect ladder.") shows four stats - **TIME, INSTINCT, RETRIES, STREAK** - a **Share result** button, and a **next-puzzle countdown**, with a small mascot.

**Why it fits our spine**: it is a Game (`word-ladder`) that can be served by any Mode - Daily (one ladder/day, shareable), Journey (a path of ever-longer ladders), Infinite (endless ladders), Time Trial (how many rungs in 90s). The chrome (stats row, share card, countdown, mascot) is shell-level and reused by every Game.

**Tamil adaptation**: a rung adds one **ezhuthu** and rearranges, e.g. a ladder over increasingly long valid Tamil words. Reachability (does a one-ezhuthu-add path exist between consecutive words?) is computed and validated **at build time** in `tools/`, so the browser only ever plays a proven-valid ladder. The "+letter" badge on each rung shows the added ezhuthu.

**Scoring/stats mapping**: TIME (elapsed), INSTINCT (first-try rungs), RETRIES (wrong submissions), STREAK (consecutive days) - all derivable from the standard telemetry events; no new persistence beyond the save record.

---

## 5. Phased rollout (proposed)

Each phase is an independently shippable slice. Phase 0-2 are the architectural commitment; 3+ are mechanical adds. Detailed rows become dated plan-docs per the house authoring ritual.

- **Phase 0 - Rebrand + right-size the contract.** Fix `CLAUDE.md` (it is still a verbatim `yen-cinthanai` copy - see section 8), write the root `README.md`, and record the "DOM word game, not a canvas/physics game" decision (open question O1). Create the empty-but-referenced `docs/concepts/` + `docs/architecture/` docs.
- **Phase 1 - Shell + one Game + Daily.** `SessionShell` slots, `SessionRunner`, Game registry, `StorageService`, event bus, the ezhuthu library, `app-config` + `puzzle-file` + first Game schema. Ship **Daily x Anagram** end-to-end (the proven `yen-tamizh_OLD` mechanic). Home shows Mode cards (Daily enabled, others "coming soon").
- **Phase 2 - Daily as a playlist + hints.** Daily plays N items with a progress bar, inter-item screen, summary, and the footer hint widget. Backfill recent days.
- **Phase 3 - Word Ladder Game + the Journey Mode + the winding-path home.** The headline journey (section 4) plus the Phase-8 path map as the Journey/level-select chrome. This is where "different journeys" becomes real.
- **Phase 4 - Missing Letters** (proves the Game abstraction with a second mechanic; Daily mix starts interleaving).
- **Phase 5 - Wordle-style** (ezhuthu keyboard + flip/shake animations).
- **Phase 6 - Word Search** (drag/keyboard trace, 8 directions).
- **Phase 7 - Crossword** (build-time placement solver in `tools/`).
- **Phase 8 - Infinite + Time Trial Modes** (reuse the Game pools; new session framings only).
- **Cross-cutting - Data consolidation** runs in parallel: master wordlist -> per-Game derived sets, feeding each Game phase just-in-time.

---

## 6. The Tamil-specific crux: ezhuthu segmentation

Because the app is Tamil-only, one technical decision touches every layer and must be settled first (it is the reason a naive port of the English reference breaks):

- The unit a player manipulates - a tile, a grid cell, a wordle "letter", a ladder rung's added character - is the **ezhuthu (grapheme cluster)**, not the Unicode codepoint. Example: "தமிழ்" is **3** ezhuthu (த + மி + ழ்) but more codepoints; "க்ஷ" and uyirmei combos (consonant + vowel sign) are single units.
- Build a small, well-tested **ezhuthu segmentation + reconstruction library** (uyir / mei-with-pulli / uyirmei), shared by `tools/` and `frontend/`. Every Game's scoring, blanking, shuffling, tracing, and interlock is defined over ezhuthu, and every wordlist is stored with its ezhuthu segmentation precomputed.
- The `yen-tamizh_OLD` corpus and its "grapheme multiset" anagram logic are the starting point; do not re-derive Tamil vocabulary from scratch.

---

## 7. Open questions (Level-5 - need your sign-off before building)

Per Correction Level 5, these pause for a decision; they are the genuine forks a system design carries:

- **O1 - Right-size the inherited contract.** The current `CLAUDE.md` is tuned for a **canvas/physics "richer game"** (renderer, physics engine, WASM, `gltf-pipeline`, KTX2 textures, "style canvas internals" rules). A Tamil word game is **DOM + Tailwind + CSS transitions** - no canvas, no physics, no 3D assets. Proposal: keep the contract's spine but replace the renderer/physics/asset-pipeline language with DOM/CSS/word-data language, and reinstate a **modest bundle budget** (the `yen-neram` 50KB-shell model) since we have no heavy assets to justify dropping it. Authority: Fowler + Carmack.
- **O2 - Journey as a Mode vs a third axis.** Proposal (section 3.1): Journey is a Mode (a curated ordered Session), not a new top-level axis - it composes cleanly with the existing Game registry and needs no new engine. Confirm. Authority: Fowler + Palm.
- **O3 - Bundle budget number.** If O1 reinstates a budget, pick the shell cap (proposal: 50KB gzipped shell, per-Game chunk lazy-loaded) and enforce it in CI via `size-limit`. Authority: Carmack.
- **O4 - Word Ladder in Tamil - difficulty of the corpus.** Add-one-ezhuthu-and-rearrange ladders require a dense enough validated word graph. Proposal: build the ladder graph offline in `tools/` and, if Tamil density is thin at short lengths, seed ladders from a curated list rather than pure search. Confirm acceptable. Authority: Palm + Fowler.
- **O5 - Final Tamil display names.** The Tamil Mode/Game names in sections 3.2-3.3 are working names; they need a native-speaker pass before they land in `config/copy.json`. Authority: Player + you.

---

## 8. Missing contract files (checklist - flagged, not created)

Per the agreed deliverable scope, this is the gap list, not the work. The current tree on disk is only `.claude/`, `.github/` (5 agents + `ci`/`daily`/`deploy` workflows), `docs/` (with `architecture/` and `concepts/` **empty**), and `CLAUDE.MD`.

**Broken / stale (fix first):**
- [ ] `CLAUDE.md` is a **verbatim `yen-cinthanai` copy**: the H1 says "yen-cinthanai Engineering Contract", section 11 says "yen-cinthanai cares about", and its Repository Topology marks `frontend/`, `config/`, `.github/agents/` as "created" though `frontend/`/`config/`/`tools/` do **not** exist on disk. Rebrand to yen-tamizh and correct the topology statuses. (Also: the file is `CLAUDE.MD`; normalise to `CLAUDE.md`.)

**Missing top-level files:**
- [ ] `README.md` (root entry point - marked "TBD" in the contract).
- [ ] `AGENTS.md` (referenced by the contract's Definition of Done).

**Empty doc tiers the bootstrap/guardrails already link to (dangling links today):**
- [ ] `docs/concepts/`: `core-loop.md`, `ui-shell.md`, `difficulty-and-scoring.md` (all three are linked from `docs/agents/bootstrap.md`), plus the design docs this proposal implies: `vision.md`, `games.md`, `modes.md`, `journeys.md`, `principles.md`, `telemetry.md`, `config.md`, `design-system.md`.
- [ ] `docs/architecture/`: `overview.md`, `contracts/schemas.md` (linked from guardrails), `runtime/stack-and-bundle.md` (linked from `ship-to-github-pages.md`), `generator/pipeline.md`, `design/` (tokens + animation + glyphs).
- [ ] `docs/how-to/`: `execute-a-plan.md` and `handle-scope-change.md` are referenced by `author-a-plan.md` / `bootstrap.md` but not present - confirm and add.

**Source trees not yet created (per Topology, land with their first PR):**
- [ ] `frontend/` (Svelte + Vite + Tailwind app), `tools/` (Python pipeline), `config/` (tunables + `copy.json`), `schemas/` (the section 3.6 list), `datasets/` (curated wordlists), `data/puzzles/` (generated JSON), `TODO/` plan-docs.

---

## See also

- [../CLAUDE.md](../CLAUDE.md) - the engineering contract (needs the section-8 rebrand).
- [../docs/agents/bootstrap.md](../docs/agents/bootstrap.md) - the load ritual every persona runs first.
- [../docs/agents/guardrails.md](../docs/agents/guardrails.md) - the rules digest (Holy Laws, non-goals, schema + path discipline).
- [../docs/reference/documentation-structure.md](../docs/reference/documentation-structure.md) - Diataxis tiers + the plan-doc single-snapshot rule.
- [../docs/how-to/author-a-plan.md](../docs/how-to/author-a-plan.md) - how the buildable parts of this proposal become dated plan-docs.
- [../docs/how-to/ship-to-github-pages.md](../docs/how-to/ship-to-github-pages.md) - base-path, SPA fallback, PWA + service-worker contract.
</content>
</invoke>
