// The Game registry - the single place a `gameId` is bound to an implementation
// (docs/concepts/ui-shell.md "SessionRunner and the Game registry"). The
// SessionRunner depends on this map, never on a concrete Game class, so adding a
// Game is a one-line registration, not a runner edit.
//
// Each entry is a lazy loader: `load()` dynamically imports the Game's module so
// its bytes arrive only when the Game is first opened (route-level code-split,
// Carmack / Holy Law #2). The runner takes the registry by injection, so tests
// and the Row 11 harness supply their own without touching this file.

import type { GameModule } from "../session/types";

/** Builds a fresh Game instance (one per session item). */
export type GameFactory = () => GameModule;

/** A registry entry: a lazy, code-split loader for a Game's factory. */
export interface GameRegistryEntry {
  load(): Promise<GameFactory>;
}

export type GameRegistry = Readonly<Record<string, GameRegistryEntry>>;

/**
 * The production registry. Games register here as their rows land; `anagram` is
 * the first (Row 12), `missing-letters` the second (Row 18), `wordle` the third
 * (Row 19), `word-search` the fourth (Row 20), `crossword` the fifth (Row 21)
 * and `word-ladder` the sixth (Row 16). Each entry stays a lazy `import()` so a
 * Game's bytes arrive only when it is first opened; the runner resolves against
 * whatever registry it is given, so tests and harnesses supply their own.
 */
export const GAME_REGISTRY: GameRegistry = {
  anagram: { load: () => import("./anagram").then((m) => m.anagramGameFactory) },
  "missing-letters": {
    load: () => import("./missing-letters").then((m) => m.missingLettersGameFactory),
  },
  wordle: { load: () => import("./wordle").then((m) => m.wordleGameFactory) },
  "word-search": {
    load: () => import("./word-search").then((m) => m.wordSearchGameFactory),
  },
  crossword: {
    load: () => import("./crossword").then((m) => m.crosswordGameFactory),
  },
  "word-ladder": {
    load: () => import("./word-ladder").then((m) => m.wordLadderGameFactory),
  },
};

/** Look a Game up in a registry, or `null` if it is not registered. */
export function resolveGame(
  registry: GameRegistry,
  gameId: string,
): GameRegistryEntry | null {
  return Object.prototype.hasOwnProperty.call(registry, gameId)
    ? (registry[gameId] ?? null)
    : null;
}
