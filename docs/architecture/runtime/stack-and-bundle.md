# Runtime Stack and Bundle

**Last Updated**: 2026-08-21

The player-facing runtime and how it is delivered: the frontend stack, the PWA/offline contract (service worker + caches), and base-path handling under the GitHub Pages project path. This is the runtime subsystem doc referenced by [../../how-to/ship-to-github-pages.md](../../how-to/ship-to-github-pages.md); the how-to is the runbook, this page is the *why*. The boundary this runtime sits behind is fixed in [../overview.md](../overview.md).

## The stack

The frontend is a static Svelte 5 + Vite 7 + Tailwind bundle. There is no runtime backend and no runtime fetch to an external host (Holy Law #1): everything the game needs ships in the bundle and works offline. Vite builds `frontend/dist`, GitHub Pages serves it, and the browser is the only runtime.

- **Svelte + Vite** compile the shell to a small hashed asset graph; `main.ts` mounts `App.svelte` into `#app`.
- **Tailwind** styles the chrome (HUD, menu, modal). It does not style game-canvas internals - those are the renderer's job when a Game lands.
- The build is **base-path aware**: `base` comes from the `GH_PAGES_BASE` env (`/yen-tamizh/` in the deploy build, `/` for local dev and preview).

## PWA and the offline contract

The shell is an installable PWA. `vite-plugin-pwa` (workbox `generateSW`) produces a service worker at build time; `frontend/src/sw-register.ts` registers it and `main.ts` calls that on boot.

The service worker is the offline contract - it either caches the playable shell correctly or it does not; there is no half (Carmack, engine-and-runtime doctrine). Two cache tiers:

- **Precache (shell).** Every built asset - HTML, JS, CSS, the manifest, the app icons, and the default theme - is precached by revision. An offline reload of a visited route boots the shell entirely from the precache. `navigateFallback` maps navigations to the precached `index.html`, which is also the SPA fallback GitHub Pages serves as `404.html`.
- **Runtime cache (bank).** Same-origin requests under `bank/` use `StaleWhileRevalidate`, bounded by an entry-count expiration so the cache cannot grow without limit. Recent bank days are precached with the shell; older days load same-origin on demand and are runtime-cached the first time they are opened. The bank directory does not exist yet (it lands in Row 13); the rule matches nothing until then and is inert when the directory is absent.
- **Runtime cache (journeys and the Infinite pool).** Same terms, same reason, and for the pool the reason is the whole design. `globPatterns` does not list `json`, so no data file is ever precached; `pool/` and `journeys/` each get their own `StaleWhileRevalidate` rule so a board a player has OPENED still opens offline while none of the ones they have not are downloaded at all. The pool is 1,765 files and 1.39 MB - precaching it would spend the entire install budget on content a player may never reach, on a phone, before the first puzzle. Measured on the real build, the precache manifest is **27 entries / 397,863 bytes both with the pool present and with it absent**: the pool adds exactly nothing to the install. Its runtime cache is bounded at 200 entries, matching the Mode's anti-repeat window, so the cache holds about as many boards as the Mode promises not to repeat (roughly 200 KB at 0.4 to 1.6 KB a board).

The matcher is guarded to **same-origin only**, so the worker never caches or reaches a cross-origin host (Holy Law #1).

### Update flow

`registerType` is `autoUpdate`: a new build's worker installs in the background and applies on the next load. There is no update toast to interrupt play (Jony: defaults are the product, remove before adding). `sw-register.ts` re-broadcasts worker lifecycle as `window` `CustomEvent`s (`pwa:offline-ready`, `pwa:registered`, `pwa:register-error`) - a serializable payload on the window per the event-bus rule (`CLAUDE.md` section 1a) - so later chrome can surface an update affordance without this module owning UI.

## Base-path handling

Under GitHub Pages the site is a project page at `/yen-tamizh/`, so nothing may assume the origin root.

- Runtime code resolves same-origin paths through `withBase()` in [../../../frontend/src/lib/base.ts](../../../frontend/src/lib/base.ts), which prefixes `import.meta.env.BASE_URL`.
- `index.html` references the manifest and apple-touch icon with Vite's `%BASE_URL%` placeholder, so the emitted URLs carry the build's base.
- `frontend/public/manifest.webmanifest` keeps `start_url`, `scope`, and icon `src` **relative**, so an installed launch resolves them against the manifest's own URL under any base - the app is base-agnostic without a rebuild difference in the manifest itself.

## Bundle cost

`vite-plugin-pwa` is a build-time dev dependency: it ships zero bytes of its own to the player. The runtime cost is the generated workbox service worker (a few KB gzipped, running in the worker thread) plus a ~1 KB registration shim in the main bundle. This keeps the main-thread shell well inside the runtime byte budget; the shell stays the small, fast first paint the target device needs (Holy Law #2).

## Design rationale

- **`vite-plugin-pwa` (workbox `generateSW`) over a hand-written service worker.** Workbox generates the precache manifest with per-asset revisions from the actual build graph, so cache invalidation is correct by construction on every deploy. A hand-written worker would re-implement revisioning and precache routing for no benefit at this scale; the plugin is build-time-only and adds no runtime framework. Authority: Carmack worldview (name the beneficiary; the smallest stack that delivers it).
- **`StaleWhileRevalidate` for `bank/`.** Bank files are same-origin and date-seeded/immutable, so serving from cache first keeps them out of the input-to-photon path (no network round-trip before data the player already has), while the background revalidate is a near-free conditional GET that self-heals if a day is ever re-baked. Bounded by an entry-count expiration so the runtime bank cache cannot grow unbounded.
- **Relative manifest URLs + `%BASE_URL%` link.** Keeping the manifest's internal URLs relative makes an installed launch work under `/yen-tamizh/` without baking the base into the manifest; the `<link rel="manifest">` uses `%BASE_URL%` so the document reference is base-correct in the built HTML.
- **`autoUpdate` over an update prompt.** There is no in-session game state to protect in the shell yet, so a background update that applies on the next load is the zero-chrome default; a prompt would be UI that has to earn its place, and it does not yet.

## Rejected alternatives

- **Precache the entire bank archive.** Rejected: the archive grows daily without bound, so precaching all of it makes the install and every update heavier forever. Recent days are precached; older days are runtime-cached on demand. Authority: Carmack (bundle is the runtime; bound the cache).
- **Precache the Infinite pool.** Rejected on the same principle and a larger number: 1.39 MB of boards, of which a session touches a few kilobytes. A pool item is fetched when it is dealt and cached then. Authority: Carmack.
- **Fetch daily puzzles from an external CDN (e.g. `raw.githubusercontent.com`).** Rejected: it is a runtime fetch to an external host - it breaks offline play and violates Holy Law #1. The bank is baked into the bundle and loaded same-origin. Authority: the committed contract (`CLAUDE.md` Holy Law #1) and [../overview.md](../overview.md).
- **`NetworkFirst` for `bank/`.** Rejected: it puts a network round-trip in front of immutable data the player already has, which is exactly the latency Holy Law #2 forbids on patchy 4G. `StaleWhileRevalidate` serves from cache first and revalidates in the background.
- **Precache theme/motif art with the shell.** Rejected: the default theme ships in the shell, but non-default motif art is a runtime (non-precached) asset so the shell stays small (Carmack + Jony). It lands with the design system (Row 10).

## See also

- [../../how-to/ship-to-github-pages.md](../../how-to/ship-to-github-pages.md) - the deploy runbook for base path, SPA fallback, and service-worker smoke.
- [../overview.md](../overview.md) - the two-runtime split and why data is baked into the bundle, never fetched.
- [../../concepts/ui-shell.md](../../concepts/ui-shell.md) - the screens and routing the shell serves.
- [../../concepts/principles.md](../../concepts/principles.md) - the ethos (static-first, the player's phone is the architecture) this runtime serves.
- [../../../CLAUDE.md](../../../CLAUDE.md) - the engineering contract (Holy Law #1, section 1a).
