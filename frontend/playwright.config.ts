import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;

// e2e smoke: build the production bundle and serve it with `vite preview`, then
// load the shell. A production-like build is required because the PWA service
// worker (install/precache/offline) is only real in a built bundle, not the dev
// server (CLAUDE.md section 12, Carmack offline-contract doctrine). Both specs
// under tests/*.spec.ts run against this server. In CI the browser is installed
// via `npx playwright install --with-deps chromium`.
export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.spec.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `npm run build && npm run preview -- --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
