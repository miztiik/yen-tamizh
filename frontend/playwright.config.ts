import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;

// e2e smoke: boot the vite dev server and load the shell. Only the smoke spec is
// matched (unit tests live under tests/unit and run in vitest). In CI the browser
// is installed via `npx playwright install --with-deps chromium`.
export default defineConfig({
  testDir: "./tests",
  testMatch: "**/smoke.spec.ts",
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
    command: `npm run dev -- --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
