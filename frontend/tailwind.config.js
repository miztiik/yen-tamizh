/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{svelte,ts,html}"],
  theme: {
    extend: {
      // Design tokens (colour ramp, spacing, easing, glyph fonts) are mirrored
      // here from app.css :root vars in Row 10 (design system). Empty for the
      // skeleton so utilities resolve against Tailwind defaults.
      fontFamily: {
        tamil: ["Noto Sans Tamil", "Latha", "InaiMathi", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
