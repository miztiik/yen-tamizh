import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { VitePWA } from "vite-plugin-pwa";
import { copyFileSync } from "node:fs";
import { resolve } from "node:path";

// Base path: "/" for local dev and preview; deploy sets GH_PAGES_BASE to the
// project path (e.g. "/yen-tamizh/"). See docs/how-to/ship-to-github-pages.md.
const base = process.env.GH_PAGES_BASE ?? "/";

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
        ],
      },
    }),
    spaFallback(),
  ],
});
