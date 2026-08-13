/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{svelte,ts,html}"],
  theme: {
    extend: {
      // Design tokens mirrored from app.css :root vars (Row 10). Every utility
      // resolves to the same var() so there is ONE source of truth, not two;
      // designsystem/app-tokens.test.ts fails if any non-exempt token loses its
      // mirror here. Do not inline literal colours - add a token + its mirror.
      colors: {
        bg: "var(--bg)",
        "bg-elevated": "var(--bg-elevated)",
        "text-primary": "var(--text-primary)",
        "text-secondary": "var(--text-secondary)",
        "text-tertiary": "var(--text-tertiary)",
        accent: "var(--accent)",
        success: "var(--success)",
        warning: "var(--warning)",
        danger: "var(--danger)",
        border: "var(--border)",
        "diff-1": "var(--diff-1)",
        "diff-2": "var(--diff-2)",
        "diff-3": "var(--diff-3)",
        "diff-4": "var(--diff-4)",
        "tile-empty": "var(--tile-empty)",
        "tile-present": "var(--tile-present)",
        "tile-correct": "var(--tile-correct)",
        "tile-absent": "var(--tile-absent)",
      },
      spacing: {
        xs: "var(--space-xs)",
        sm: "var(--space-sm)",
        md: "var(--space-md)",
        lg: "var(--space-lg)",
        xl: "var(--space-xl)",
        "2xl": "var(--space-2xl)",
      },
      borderRadius: {
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        full: "var(--radius-full)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
      },
      fontFamily: {
        display: "var(--font-display)",
        mono: "var(--font-mono)",
        tamil: ["Noto Sans Tamil", "Latha", "InaiMathi", "system-ui", "sans-serif"],
      },
      transitionTimingFunction: {
        smooth: "var(--ease)",
        spring: "var(--ease-spring)",
      },
      transitionDuration: {
        fast: "var(--dur-fast)",
        base: "var(--dur-base)",
        slow: "var(--dur-slow)",
      },
    },
  },
  plugins: [],
};
