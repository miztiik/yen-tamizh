// ORACLE (contract tier) - the crossword Game's import boundary.
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
//
// This Game has two extra things to prove. Its answers are words, so nothing in
// it may open a wordlist to decide whether what the player wrote is one - the
// only words it knows are the ones its payload names, and the payload already
// names the alternatives it will accept. And it may not reach into the wordle
// for the composer keyboard, however close the two look: a Game reaching into a
// Game is exactly what one-schema-per-Game exists to prevent, and the two
// keyboards answer different questions - the wordle's carries per-letter mark
// state accumulated over guesses, and this one carries none.

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
  "../../contracts/crossword-puzzle", // the generated payload contract (types only)
  "../../designsystem/Glyph.svelte", // Row 10 glyphs (no inline SVG - Holy Law #10)
]);

/** Specifiers that would break a named invariant, with the invariant they break. */
const FORBIDDEN: ReadonlyArray<{ pattern: RegExp; why: string }> = [
  { pattern: /appConfig|app-config/i, why: "a Game must not read the app config" },
  { pattern: /StorageService|\/services\//i, why: "storage has a single writer (the runner)" },
  { pattern: /telemetry\//i, why: "telemetry arrives as ctx.logger, never as a singleton" },
  { pattern: /\/shell\//i, why: "a Game renders into `stage`; it never reaches the shell" },
  { pattern: /SessionRunner|\/session\/(?!types)/i, why: "a Game never sees the runner or the Mode" },
  // A Game may not read another Game's mechanic either: one payload schema per
  // Game is what lets them evolve independently (schemas.md).
  { pattern: /\/games\//i, why: "a Game never reaches into another Game" },
  // Row 21's own rule: the only words this board knows are the ones its payload
  // names, so no dataset may be opened at play time.
  { pattern: /datasets|wordlist/i, why: "this Game knows only the words in its payload" },
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

describe("crossword Game import boundary (Oracle)", () => {
  const sources = gameSources();

  it("ships the Game's source files", () => {
    expect(sources.map((s) => s.name).sort()).toEqual([
      "CrosswordGame.svelte",
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
        expect(pattern.test(specifier), `${name} imports "${specifier}" - ${why}`).toBe(
          false,
        );
      }
    }
  });

  it.each(sources.map((s) => s.name))("%s touches no storage or network API", (name) => {
    const source = sources.find((s) => s.name === name);
    // Not imports, but the same invariants: the runner is the only writer, and a
    // static-first Game never calls home (Holy Law #1).
    expect(/\b(localStorage|sessionStorage|indexedDB)\b/.test(source?.text ?? "")).toBe(false);
    expect(/\b(fetch|XMLHttpRequest)\s*\(/.test(source?.text ?? "")).toBe(false);
  });

  it("reads its puzzle only from the payload and its context", () => {
    const view = sources.find((s) => s.name === "CrosswordGame.svelte");
    expect(view).toBeDefined();
    // The view's props ARE the GameContext slice it is allowed to see.
    expect(view?.text).toContain("payload: CrosswordPayload");
    expect(view?.text).toContain('logger: GameContext["logger"]');
    expect(view?.text).toContain('config: GameContext["config"]');
    expect(view?.text).toContain('now: GameContext["now"]');
  });

  it("emits only event names the catalog already defines", () => {
    // A Game that minted its own event name would be a private protocol between
    // it and nothing (docs/reference/event-catalog.md).
    const known = new Set([
      "puzzle.started",
      "puzzle.attempt.submitted",
      "puzzle.hint.used",
      "puzzle.completed",
      "puzzle.abandoned",
    ]);
    for (const source of sources) {
      for (const match of source.text.matchAll(/emit\(\s*"([^"]+)"/g)) {
        const name = match[1];
        expect(known.has(name ?? ""), `${source.name} emits "${name}"`).toBe(true);
      }
    }
  });
});
