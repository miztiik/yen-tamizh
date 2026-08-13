import js from "@eslint/js";
import tseslint from "typescript-eslint";
import globals from "globals";

// Flat config. ESLint lints TS/JS source for code quality; svelte-check owns
// .svelte type + correctness checking (see the "check" script). The logger is
// the only sanctioned console sink (Row 11); game code emits via the event bus.
export default tseslint.config(
  {
    ignores: [
      "dist/**",
      "dev-dist/**",
      "node_modules/**",
      "coverage/**",
      "playwright-report/**",
      "test-results/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
    },
    rules: {
      "no-console": "error",
    },
  },
);
