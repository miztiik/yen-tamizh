<script lang="ts">
  // Renders a vector glyph BY ID from the baked manifest (Holy Law #10). An
  // unknown id renders nothing and reports through the injected logger - never a
  // crash, never a console write. The resolution logic is unit-tested in
  // glyphs.test.ts (vitest has no Svelte compiler, so the logic lives in a .ts).
  import { NOOP_GLYPH_LOGGER, resolveGlyph, type GlyphLogger } from "./glyphs";

  interface Props {
    /** Glyph id from the manifest (e.g. "back", "check", "settings"). */
    id: string;
    /** Rendered box size (any CSS length or a number of px). */
    size?: number | string;
    /** Accessible label; when omitted the glyph is decorative (aria-hidden). */
    title?: string;
    /** Injected sink for the unknown-id warning (the shell provides one). */
    logger?: GlyphLogger;
    /** Extra classes - e.g. `text-accent` colours the glyph via currentColor. */
    class?: string;
  }

  let {
    id,
    size = "1.25rem",
    title,
    logger = NOOP_GLYPH_LOGGER,
    class: className = "",
  }: Props = $props();

  const glyph = $derived(resolveGlyph(id, logger));
</script>

{#if glyph}
  <svg
    class={className}
    width={size}
    height={size}
    viewBox={glyph.viewBox}
    fill="none"
    stroke="currentColor"
    stroke-width="2"
    stroke-linecap="round"
    stroke-linejoin="round"
    role={title ? "img" : undefined}
    aria-label={title}
    aria-hidden={title ? undefined : "true"}
    focusable="false"
  >
    <path d={glyph.path} />
  </svg>
{/if}
