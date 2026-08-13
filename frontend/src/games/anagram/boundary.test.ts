// ORACLE (contract tier) - the anagram Game's import boundary.
//
// A Game is a PURE MECHANIC: it may read its `payload` and the injected
// `GameContext` (logger, config slice, clock) and nothing else (CLAUDE.md
// section 1a "payloads, not calls"; docs/concepts/ui-shell.md). If a Game could
// reach the app config it would fork the tuning knobs; if it could reach
// StorageService it would break the single-writer invariant; if it could reach a
// telemetry singleton it would emit outside its session scope.
//
// That boundary is structural, so it is tested structurally: this reads the
// Game's own source files and asserts (a) none of the forbidden specifiers
// appears, and (b) every module it imports from outside its own folder is on a
// short allowlist. A future edit that reaches across the boundary fails here.

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const GAME_DIR = fileURLToPath(new URL(".", import.meta.url));

/** Import specifiers a Game may reach for; everything else is a boundary break. */
const ALLOWED_IMPORTS = new Set([
  "svelte", // the view layer the adapter mounts
  "../../session/types", // GameContext + GameModule - the contract itself
  "../../tamil/ezhuthu", // the shared Row 6 ezhuthu library
  "../../contracts/anagram-puzzle", // the generated payload contract (types only)
  "../../designsystem/Glyph.svelte", // Row 10 glyphs (no inline SVG - Holy Law #10)
]);

/** Specifiers that would break a named invariant, with the invariant they break. */
const FORBIDDEN: ReadonlyArray<{ pattern: RegExp; why: string }> = [
  { pattern: /appConfig|app-config/i, why: "a Game must not read the app config" },
  { pattern: /StorageService|\/services\//i, why: "storage has a single writer (the runner)" },
  { pattern: /telemetry\//i, why: "telemetry arrives as ctx.logger, never as a singleton" },
  { pattern: /\/shell\//i, why: "a Game renders into `stage`; it never reaches the shell" },
  { pattern: /SessionRunner|\/session\/(?!types)/i, why: "a Game never sees the runner or the Mode" },
];

/** Source files that make up the shipped Game (its tests are not shipped). */
function gameSources(): { name: string; text: string }[] {
  return readdirSync(GAME_DIR)
    .filter((name) => /\.(ts|svelte)$/.test(name) && !name.endsWith(".test.ts"))
    .map((name) => ({ name, text: readFileSync(join(GAME_DIR, name), "utf8") }));
}

/** Every static and dynamic import specifier in a source file. */
function importSpecifiers(text: string): string[] {
  const specifiers: string[] = [];
  const patterns = [/\bfrom\s+["']([^"']+)["']/g, /\bimport\s*\(\s*["']([^"']+)["']\s*\)/g];
  for (const pattern of patterns) {
    for (const match of text.matchAll(pattern)) {
      const specifier = match[1];
      if (specifier !== undefined) specifiers.push(specifier);
    }
  }
  return specifiers;
}

describe("anagram Game import boundary (Oracle)", () => {
  const sources = gameSources();

  it("ships the Game's source files", () => {
    expect(sources.map((s) => s.name).sort()).toEqual([
      "AnagramGame.svelte",
      "index.ts",
      "logic.ts",
    ]);
  });

  it.each(sources.map((s) => s.name))(
    "%s imports nothing outside the Game's allowlist",
    (name) => {
      const source = sources.find((s) => s.name === name);
      expect(source).toBeDefined();
      const outside = importSpecifiers(source?.text ?? "").filter(
        (specifier) => !specifier.startsWith("./"),
      );
      for (const specifier of outside) {
        expect(ALLOWED_IMPORTS.has(specifier), `${name} imports "${specifier}"`).toBe(true);
      }
    },
  );

  it.each(sources.map((s) => s.name))("%s imports no forbidden module", (name) => {
    const source = sources.find((s) => s.name === name);
    for (const specifier of importSpecifiers(source?.text ?? "")) {
      for (const { pattern, why } of FORBIDDEN) {
        expect(
          pattern.test(specifier),
          `${name} imports "${specifier}" - ${why}`,
        ).toBe(false);
      }
    }
  });

  it.each(sources.map((s) => s.name))("%s touches no storage API directly", (name) => {
    const source = sources.find((s) => s.name === name);
    // Not an import, but the same invariant: the runner is the only writer.
    expect(/\b(localStorage|sessionStorage|indexedDB)\b/.test(source?.text ?? "")).toBe(false);
  });

  it("reads its puzzle only from the payload and its context", () => {
    const view = sources.find((s) => s.name === "AnagramGame.svelte");
    expect(view).toBeDefined();
    // The view's props ARE the GameContext slice it is allowed to see.
    expect(view?.text).toContain("payload: AnagramPayload");
    expect(view?.text).toContain('logger: GameContext["logger"]');
    expect(view?.text).toContain('config: GameContext["config"]');
    expect(view?.text).toContain('now: GameContext["now"]');
  });
});
