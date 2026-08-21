import { defineConfig, type ViteDevServer } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { VitePWA } from "vite-plugin-pwa";
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

// Base path: "/" for local dev and preview; deploy sets GH_PAGES_BASE to the
// project path (e.g. "/yen-tamizh/"). See docs/how-to/ship-to-github-pages.md.
const base = process.env.GH_PAGES_BASE ?? "/";

// The authored Journeys (Row 17). They live in datasets/journeys/ with the rest
// of the game's data and are READ from there rather than copied into public/: a
// second committed copy is a second authority, and the one thing a Journey may
// never be is two files that disagree about how many nodes it has. The game
// still fetches them same-origin from its own bundle (Holy Law #1).
const journeysDir = resolve(process.cwd(), "..", "datasets", "journeys");

// A journey id is a slug, and the pattern is what makes the dev middleware safe:
// it can only ever name a file inside journeysDir, so no request can traverse
// out of it.
const JOURNEY_URL = /^\/journeys\/([a-z][a-z0-9-]*)\.json$/;

function journeyFiles(): string[] {
  return existsSync(journeysDir)
    ? readdirSync(journeysDir).filter((name) => name.endsWith(".json")).sort()
    : [];
}

function journeyData() {
  return {
    name: "journey-data",
    configureServer(server: ViteDevServer) {
      server.middlewares.use((req, res, next) => {
        const match = JOURNEY_URL.exec((req.url ?? "").split("?")[0] ?? "");
        const file = match === null ? null : resolve(journeysDir, `${match[1]}.json`);
        if (file === null || !existsSync(file)) {
          next();
          return;
        }
        res.setHeader("content-type", "application/json; charset=utf-8");
        res.end(readFileSync(file));
      });
    },
    closeBundle() {
      const out = resolve(process.cwd(), "dist", "journeys");
      const names = journeyFiles();
      if (names.length === 0) return;
      mkdirSync(out, { recursive: true });
      for (const name of names) {
        copyFileSync(resolve(journeysDir, name), resolve(out, name));
      }
    },
  };
}

// SPA history fallback: dist/404.html must mirror the BUILT index.html (hashed
// asset tags + base + injected PWA link tags) so deep links boot the app on
// GitHub Pages. Runs in closeBundle AFTER vite-plugin-pwa, so the generated
// service worker has already globbed dist (404.html is not itself precached -
// it is byte-identical to the precached index.html).
function spaFallback() {
  return {
    name: "spa-404-fallback",
    closeBundle() {
      const out = resolve(process.cwd(), "dist");
      copyFileSync(resolve(out, "index.html"), resolve(out, "404.html"));
    },
  };
}

export default defineConfig({
  base,
  plugins: [
    svelte(),
    journeyData(),
    // Installable PWA + offline app shell (Row 4). generateSW precaches the
    // built shell; a same-origin bank/ runtime cache serves opened days offline
    // (the bank lands in Row 13; the rule is inert until the directory exists).
    // See docs/architecture/runtime/stack-and-bundle.md.
    VitePWA({
      registerType: "autoUpdate",
      // Registration is owned by src/sw-register.ts (imported from main.ts).
      injectRegister: false,
      // The manifest is the static, base-agnostic public/manifest.webmanifest
      // (relative start_url/scope/icons); do not generate a second one.
      manifest: false,
      workbox: {
        globPatterns: ["**/*.{js,css,html,svg,png,ico,webmanifest,woff2}"],
        navigateFallback: "index.html",
        cleanupOutdatedCaches: true,
        clientsClaim: true,
        runtimeCaching: [
          {
            // Same-origin only (Holy Law #1: never reach a cross-origin host).
            urlPattern: ({ url, sameOrigin }) => sameOrigin && url.pathname.includes("/bank/"),
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "yen-tamizh-bank",
              // Bound the runtime bank cache; the archive is never fully cached.
              expiration: { maxEntries: 60, purgeOnQuotaError: true },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            // The Journeys, on the same terms as the bank. They are not in
            // globPatterns because precaching every JSON would precache the
            // whole bank; a path a player has opened should still open offline.
            urlPattern: ({ url, sameOrigin }) =>
              sameOrigin && url.pathname.includes("/journeys/"),
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "yen-tamizh-journeys",
              expiration: { maxEntries: 20, purgeOnQuotaError: true },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            // The Infinite pool (Row 22), on the same terms - and this is the
            // one where the terms matter most. The pool is ~1,800 files and
            // 1.4 MB: precaching it would spend the entire install budget on
            // content a player may never reach, on a phone, before the first
            // puzzle. globPatterns already excludes JSON, so this rule is what
            // makes an opened board work offline WITHOUT any of it being
            // downloaded up front. The entry bound is the anti-repeat window's
            // 200, so the cache holds about as many boards as the Mode promises
            // not to repeat - roughly 200 KB at the measured 0.4-1.6 KB a board.
            urlPattern: ({ url, sameOrigin }) =>
              sameOrigin && url.pathname.includes("/pool/"),
            handler: "StaleWhileRevalidate",
            options: {
              cacheName: "yen-tamizh-pool",
              expiration: { maxEntries: 200, purgeOnQuotaError: true },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
    }),
    spaFallback(),
  ],
});
