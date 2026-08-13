// The Game registry - the single place a `gameId` is bound to an implementation
// (docs/concepts/ui-shell.md "SessionRunner and the Game registry"). The
// SessionRunner depends on this map, never on a concrete Game class, so adding a
// Game is a one-line registration, not a runner edit.
//
// Each entry is a lazy loader: `load()` dynamically imports the Game's module so
// its bytes arrive only when the Game is first opened (route-level code-split,
// Carmack / Holy Law #2). The map is empty until Row 12 registers `anagram`; the
// runner takes the registry by injection, so tests and the Row 11 harness supply
// their own without touching this file.

import type { GameModule } from "../session/types";

/** Builds a fresh Game instance (one per session item). */
export type GameFactory = () => GameModule;

/** A registry entry: a lazy, code-split loader for a Game's factory. */
export interface GameRegistryEntry {
  load(): Promise<GameFactory>;
}

export type GameRegistry = Readonly<Record<string, GameRegistryEntry>>;

/**
 * The production registry. Games register here as their rows land, e.g.:
 *   anagram: { load: () => import("./anagram/AnagramGame").then((m) => m.factory) }
 * Empty until Row 12; the runner resolves against whatever registry it is given.
 */
export const GAME_REGISTRY: GameRegistry = {};

/** Look a Game up in a registry, or `null` if it is not registered. */
export function resolveGame(
  registry: GameRegistry,
  gameId: string,
): GameRegistryEntry | null {
  return Object.prototype.hasOwnProperty.call(registry, gameId)
    ? (registry[gameId] ?? null)
    : null;
}
