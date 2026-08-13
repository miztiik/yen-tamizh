// Glyph resolution - the pure, testable core behind Glyph.svelte.
//
// All icons are vector glyphs referenced BY ID from the baked manifest, never
// inline SVG (Holy Law #10). The backend bakes assets/glyphs/*.svg into the
// served frontend/public/assets/glyphs/index.json (a glyph-manifest payload);
// we import those bytes here so a glyph resolves synchronously with no runtime
// fetch (the served copy is still emitted for SW precache + Row 11's loader).
//
// vitest runs in a node environment with no Svelte compiler, so the component's
// logic lives here as plain functions the unit tests exercise directly.
import manifestJson from "../../public/assets/glyphs/index.json";
import type { GlyphManifest, GlyphShape } from "../contracts/glyph-manifest";

// The JSON's inferred literal type widens to the generated contract type; the
// bake + glyph-manifest schema guarantee the shape (proven by test_glyphs.py).
const MANIFEST = manifestJson as unknown as GlyphManifest;

export type { GlyphShape };

/**
 * A place for a Glyph to report an unknown id. The shell injects a real logger
 * (Row 11); game chrome must never write to `console` directly (eslint
 * no-console), so the default is a silent no-op rather than a console warning.
 */
export interface GlyphLogger {
  warn(message: string, context?: Record<string, unknown>): void;
}

export const NOOP_GLYPH_LOGGER: GlyphLogger = {
  warn() {
    // no-op default; the shell injects a real logger in Row 11
  },
};

/** Every glyph id present in the baked manifest (sorted, stable). */
export function glyphIds(): string[] {
  return Object.keys(MANIFEST.glyphs).sort();
}

/** Whether the manifest contains a glyph with this id. */
export function hasGlyph(id: string): boolean {
  return Object.prototype.hasOwnProperty.call(MANIFEST.glyphs, id);
}

/**
 * Resolve a glyph's geometry by id, or `null` if unknown. An unknown id is a
 * caller bug, so it is reported through the injected logger and the caller
 * renders nothing (fail-safe: a missing icon never crashes the chrome).
 */
export function resolveGlyph(id: string, logger: GlyphLogger = NOOP_GLYPH_LOGGER): GlyphShape | null {
  const shape = MANIFEST.glyphs[id];
  if (shape === undefined) {
    logger.warn(`Glyph: unknown id "${id}"`, { id, known: glyphIds() });
    return null;
  }
  return shape;
}
