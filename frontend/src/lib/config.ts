// The config boundary - where `config/` reaches the running game.
//
// Both files are IMPORTED, not fetched: they are small, they are needed before
// the first paint, and a bundled import means one source of truth (the same
// bytes the backend validates and `core-schemas.test.ts` checks against the
// generated schema), zero extra requests, and nothing to 404 offline (Holy Law
// #1, Carmack). Copying them into `public/` would have created a second copy
// free to drift; fetching them would have cost a round trip on the critical
// path for ~1 KB.
//
// A Game never imports this module - it receives a read-only config slice from
// the runner (the boundary `games/anagram/boundary.test.ts` enforces). Only the
// shell, the Home, and the Modes read config.

import appConfigJson from "../../../config/app-config.json";
import copyJson from "../../../config/copy.json";
import type { AppConfig, Copy } from "../contracts";

// The JSON's inferred literal type widens to the generated contract type; the
// schema + the contract test guarantee the shape (same precedent as the baked
// glyph manifest in designsystem/glyphs.ts).
export const APP_CONFIG = appConfigJson as unknown as AppConfig;
const COPY = copyJson as unknown as Copy;

/**
 * A player-facing string by slug. Missing copy renders its own slug rather than
 * an empty box, so a forgotten entry is visible in the UI instead of silently
 * blanking a control (fail loud, never blank).
 */
export function copyText(slug: string): string {
  return COPY.strings[slug] ?? slug;
}

/** Whether a Mode is switched on in `config/app-config.json`. */
export function isModeEnabled(modeId: string): boolean {
  return APP_CONFIG.ui.enabledModes.includes(modeId);
}
