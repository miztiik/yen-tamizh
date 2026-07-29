# Design System

**Last Updated**: 2026-07-29

The visual vocabulary: the CSS-event-driven pattern, design tokens, the animation set, and the glyph rule. This is the shared language the [chrome](ui-shell.md) and every [Game](games.md) speak; the concrete token file and the glyph bake land with the design-system code row, and this page fixes the vocabulary that row builds to. The bounds are owned by Jony ([../../.github/agents/jony.agent.md](../../.github/agents/jony.agent.md), look) and Carmack ([../../.github/agents/carmack.agent.md](../../.github/agents/carmack.agent.md), frame budget).

## The CSS-event-driven pattern

The DOM state is the single source of truth for the view. Nothing is styled imperatively: **an event mutates state, state is reflected by toggling a class or a `data-` attribute, and CSS reacts declaratively.** In Svelte this is idiomatic (`class:correct`, `data-state`, scoped component styles over a global token layer). The event that drives it is the same one that feeds [telemetry](telemetry.md) - see the loop in [core-loop.md](core-loop.md).

- **State classes** carry the look: `selected`, `conflict`, `correct`, `present`, `absent`, `completed`, `loading`, `revealed`. JS toggles the class; CSS owns the pixels.
- **Data-attribute styling** carries variants: a difficulty tab keys its colour off `data-level`; a tooltip can render from `data-tooltip` with zero JS.
- **No inline styles** except genuinely dynamic values (a drag translate, a progress width). Everything else is a token or a class.

## Design tokens

Every colour, space, radius, shadow, font, easing, and duration is a CSS custom property in `:root`, named **by purpose**, not by value:

- **Fonts** - a Tamil-capable display face and a tile/grid face (the ezhuthu must render crisply at tile size).
- **Space / radius / shadow** - a small named scale.
- **Colour** - `bg` and elevated surfaces; `text` primary / secondary / tertiary; `accent`, `success`, `warning`, `danger`; the **difficulty ramp** (`diff-1..4`, easy -> extreme; [difficulty-and-scoring.md](difficulty-and-scoring.md)); the **tile-feedback** set (empty / present / correct / absent) for the Wordle-style Game.
- **Motion** - an `ease`, a spring `ease`, and a duration scale.

Theming is override, not a second set of names: dark mode overrides the same token values, and a **`[data-theme]` axis** lets a [Journey](journeys.md) carry its own palette. Tailwind's `theme.extend` **mirrors** these tokens so a utility (`bg-accent`, `text-danger`) resolves to the same `var(--...)` - one source of truth, not two - and a contract test asserts every non-exempt token has a mirror.

## Animation vocabulary

Motion is game feel, a first-class confirmation of input ([principles.md](principles.md)), inside hard bounds:

- **`transform` + `opacity` only.** Never animate a layout-triggering property - that is what holds 60fps on the target phone (Holy Law #2).
- **Spring easing** for anything that should feel alive; linear/ease for utility fades.
- **`prefers-reduced-motion` is a hard kill-switch** - a media query that zeroes durations and disables confetti. Respecting it is required.
- The named keyframe set: `pop` / `glow` (hint reveal), `flip` / `shake` (guess correct / invalid), `victoryPulse` + `confettiFall` + `trophyBounce` (win), `toastIn` / `modalIn` / `fadeIn` (chrome), `shimmer` (skeleton load), `gradientShift` (animated title), plus a Word-Ladder "rung climb".

## Glyphs

All icons are **vector glyphs referenced by id** from a generated manifest, never inline SVG, never a hardcoded path, never a PNG (Holy Law #10). `backend/` bakes the glyph pack at build time and writes the manifest into the served bundle (`frontend/public/assets/glyphs/index.json`); the frontend reads only the manifest and resolves a glyph by its `pack.slug` id. The manifest is a persisted surface with its own schema ([../architecture/contracts/schemas.md](../architecture/contracts/schemas.md)). The toolbar (hint, check, shuffle, undo) and a glyph-only difficulty indicator are built from glyphs. The mascot - a Tamil letter with eyes - is the one themeable inline motif that guides a [Journey](journeys.md).

## See also

- [core-loop.md](core-loop.md) - the event-to-state-to-pixels loop this pattern implements.
- [ui-shell.md](ui-shell.md) - the chrome that consumes these tokens and glyphs.
- [difficulty-and-scoring.md](difficulty-and-scoring.md) - the difficulty colour ramp.
- [journeys.md](journeys.md) - the per-Journey theme axis and mascot.
- [../architecture/contracts/schemas.md](../architecture/contracts/schemas.md) - the glyph / asset manifest schema.
- [../../CLAUDE.md](../../CLAUDE.md) - Holy Law #10 (glyphs) and the animation anti-patterns.
