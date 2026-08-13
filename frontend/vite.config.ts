import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { copyFileSync } from "node:fs";
import { resolve } from "node:path";

// Base path: "/" for local dev and preview; deploy sets GH_PAGES_BASE to the
// project path (e.g. "/yen-tamizh/"). See docs/how-to/ship-to-github-pages.md.
const base = process.env.GH_PAGES_BASE ?? "/";

// SPA history fallback: dist/404.html must mirror the BUILT index.html (hashed
// asset tags + base) so deep links boot the app on GitHub Pages. The full PWA /
// offline contract lands in Row 4; this is the minimal fallback the skeleton needs.
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
  plugins: [svelte(), spaFallback()],
});
