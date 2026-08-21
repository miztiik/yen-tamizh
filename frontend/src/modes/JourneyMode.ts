// JourneyMode - the curated-path Mode (docs/concepts/journeys.md).
//
// A Mode owns SESSION FRAMING and nothing else. Where DailyMode frames the day
// the calendar names, this one frames the NODE the player's own progress names:
// it reads the authored path, decides which nodes are reachable, and hands the
// SessionRunner the one node the player tapped.
//
// Three rules shape it:
//
//   - SAME-ORIGIN ONLY. A Journey ships inside the bundle under `journeys/` and
//     is read through `withBase` + `loadValidated`, so it works offline, is
//     schema-validated at the boundary, and never reaches a CDN (Holy Law #1).
//   - THE PATH IS DATA. Everything about which node comes next, which Game it
//     holds and what its board is comes from the file; nothing here knows the
//     name of a Journey or of a Game. Adding a path is dropping a file.
//   - THE SAVE IS THE ONLY AUTHORITY ON PROGRESS, and it is UNTRUSTED. What
//     comes back from storage is parsed rather than cast: a record of the wrong
//     shape unlocks nothing, because "I could not read it" must never be read as
//     "everything is cleared".
//
// A node is ONE session of one item. That is what makes the progression claim
// checkable - a node is complete exactly when its session completed - and it is
// also what the map needs: a path the player leaves and returns to.

import { loadValidated, type SchemaName, type SchemaPayload } from "../contracts";
import type { Journey } from "../contracts";
import { withBase } from "../lib/base";
import type { Session } from "../session/types";

/** The Mode's stable identifier (the `modeId` in the save and in telemetry). */
export const JOURNEY_MODE_ID = "journey";

/** One node of the path, as the file spells it. */
export type JourneyNode = Journey["nodes"][number];

/** Where a node stands for this player. */
export type NodeState = "completed" | "available" | "locked";

/** The typed loader JourneyMode needs; tests inject a local one (no network). */
export type ValidatedLoader = <K extends SchemaName>(
  url: string,
  schemaName: K,
) => Promise<SchemaPayload[K]>;

export interface JourneyModeDeps {
  /** The id of the path to open - `ui.defaultJourney`, never a constant here. */
  journeyId: string;
  /** Defaults to the schema-validating same-origin fetch. */
  load?: ValidatedLoader;
  /** Defaults to the bundle's base path. */
  base?: string;
}

/** What the shell gets back: a walkable path, or a reason there is none. */
export type JourneyOutcome =
  | { status: "ready"; journey: Journey }
  | { status: "unavailable"; reason: "load-failed" | "empty-path" };

/** Where one authored Journey lives, base-path aware. */
export function journeyUrl(journeyId: string, base?: string): string {
  return withBase(`journeys/${journeyId}.json`, base);
}

/** Load one authored path; never throws. */
export async function loadJourney(deps: JourneyModeDeps): Promise<JourneyOutcome> {
  const load = deps.load ?? loadValidated;
  let journey: Journey;
  try {
    journey = await load(journeyUrl(deps.journeyId, deps.base), "journey");
  } catch {
    return { status: "unavailable", reason: "load-failed" };
  }
  if (journey.nodes.length === 0) return { status: "unavailable", reason: "empty-path" };
  return { status: "ready", journey };
}

/**
 * The node ids this save records as cleared for one path.
 *
 * Deliberately paranoid, because `perMode` values are an OPEN object in the save
 * schema: ajv proves the save is a save and says nothing about what a Mode kept
 * inside its own slot. Anything that is not a list of strings reads as no
 * progress at all, which is the safe direction - a player replays a node they
 * had cleared, rather than being handed a path they never walked.
 */
export function completedNodeIds(progress: unknown, journeyId: string): string[] {
  if (typeof progress !== "object" || progress === null) return [];
  const completed = (progress as Record<string, unknown>).completed;
  if (typeof completed !== "object" || completed === null) return [];
  const forPath = (completed as Record<string, unknown>)[journeyId];
  if (!Array.isArray(forPath)) return [];
  return forPath.filter((id): id is string => typeof id === "string");
}

/**
 * The progress record to persist after clearing one node.
 *
 * Returns a NEW record rather than mutating: the caller hands it straight to
 * StorageService, which is the only writer, and every other path's progress
 * rides along untouched. Recording the same node twice is a no-op.
 */
export function withNodeCompleted(
  progress: unknown,
  journeyId: string,
  nodeId: string,
): Record<string, unknown> {
  const existing = completedNodeIds(progress, journeyId);
  const cleared = existing.includes(nodeId) ? existing : [...existing, nodeId];
  const previous =
    typeof progress === "object" && progress !== null
      ? ((progress as Record<string, unknown>).completed as unknown)
      : null;
  const others =
    typeof previous === "object" && previous !== null
      ? (previous as Record<string, unknown>)
      : {};
  return { completed: { ...others, [journeyId]: cleared } };
}

/**
 * Where every node of the path stands, in walking order.
 *
 * THE PROGRESSION RULE, stated once: a node is `completed` when the save says
 * so; otherwise it is `available` when its own rule says it opens - `open`
 * needs nothing, `previous-complete` needs the node IMMEDIATELY before it to be
 * completed - and `locked` when it does not. Clearing a node therefore opens
 * exactly the one after it and nothing further along, because every other node
 * is still waiting on its own predecessor.
 *
 * A `previous-complete` node in first position has no predecessor and stays
 * locked. The contract refuses that path, so this is the belt to its braces:
 * the file could have been served by an older build.
 */
export function nodeStates(
  journey: Journey,
  completed: readonly string[],
): NodeState[] {
  const cleared = new Set(completed);
  return journey.nodes.map((node, index) => {
    if (cleared.has(node.id)) return "completed";
    if (node.unlockRule === "open") return "available";
    const previous = journey.nodes[index - 1];
    return previous !== undefined && cleared.has(previous.id) ? "available" : "locked";
  });
}

/** Whether one node can be opened right now. A cleared node may be replayed. */
export function isPlayable(
  journey: Journey,
  completed: readonly string[],
  nodeId: string,
): boolean {
  const index = journey.nodes.findIndex((node) => node.id === nodeId);
  if (index === -1) return false;
  return nodeStates(journey, completed)[index] !== "locked";
}

/** The node the player should meet next: the first that is not yet cleared. */
export function nextNodeId(
  journey: Journey,
  completed: readonly string[],
): string | null {
  const states = nodeStates(journey, completed);
  const index = states.indexOf("available");
  return index === -1 ? null : (journey.nodes[index]?.id ?? null);
}

/**
 * Frame one node as a Session the runner can walk.
 *
 * `date` is the player's calendar day. A Journey is not calendar-bound - that
 * is the whole difference from the Daily - but the save's `dayKey` is derived
 * from a date, and mid-node resume should expire the same way every other
 * in-progress puzzle does. What must NOT expire is which nodes are cleared, and
 * that lives in the Mode's own progress record instead (StorageService).
 */
export function toSession(journey: Journey, node: JourneyNode, date: string): Session {
  return {
    modeId: JOURNEY_MODE_ID,
    packId: node.packId,
    gameId: node.gameId,
    sessionId: `${JOURNEY_MODE_ID}-${journey.id}-${node.id}`,
    date,
    items: [{ gameId: node.gameId, payload: node.payload }],
  };
}
