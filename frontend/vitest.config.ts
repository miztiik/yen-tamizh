import { defineConfig } from "vitest/config";

// Unit tests only (node env). Component-render coverage is provided by the
// Playwright e2e smoke (tests/smoke.spec.ts), which is deliberately excluded
// here so vitest never tries to run a Playwright spec.
export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/unit/**/*.{test,spec}.ts", "src/**/*.{test,spec}.ts"],
  },
});
