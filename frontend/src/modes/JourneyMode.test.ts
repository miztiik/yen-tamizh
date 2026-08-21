import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

import type { Journey, SchemaName, SchemaPayload } from "../contracts";
import { StorageService, type KeyValueStore } from "../services/StorageService";
import type { DayContext } from "../session/dayKey";

import {
  JOURNEY_MODE_ID,
  completedNodeIds,
  isPlayable,
  journeyUrl,
  loadJourney,
  nextNodeId,
  nodeStates,
  toSession,
  withNodeCompleted,
} from "./JourneyMode";

// The REAL committed path, read straight off disk (Holy Law #7: real fixtures,
// no mocks). The loader is INJECTED rather than stubbed, so these tests prove
// the Mode's framing against the same bytes the deployed bundle ships.
const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const journeysDir = resolve(repoRoot, "datasets/journeys");

const JOURNEY_ID = "beginners-ladder";
const committed = JSON.parse(
  readFileSync(resolve(journeysDir, `${JOURNEY_ID}.json`), "utf-8"),
) as Journey;

/** A loader that serves the committed journeys from disk by URL. */
function diskLoader(missing: string[] = []) {
  return async <K extends SchemaName>(url: string): Promise<SchemaPayload[K]> => {
    if (missing.includes(url)) throw new Error(`404 ${url}`);
    const name = url.slice(url.lastIndexOf("/") + 1);
    return JSON.parse(
      readFileSync(resolve(journeysDir, name), "utf-8"),
    ) as SchemaPayload[K];
  };
}

function memStore(): KeyValueStore {
  const map = new Map<string, string>();
  return {
    getItem: (k) => (map.has(k) ? (map.get(k) as string) : null),
    setItem: (k, v) => void map.set(k, v),
    removeItem: (k) => void map.delete(k),
  };
}

const ids = committed.nodes.map((node) => node.id);

function ctxFor(index: number): DayContext {
  const node = committed.nodes[index];
  return {
    date: "2026-08-21",
    modeId: JOURNEY_MODE_ID,
    gameId: node?.gameId ?? "anagram",
    packId: node?.packId ?? "ta-core",
  };
}

/** Read the path's cleared nodes back out of a real save. */
function clearedIn(storage: StorageService): string[] {
  return completedNodeIds(storage.readModeProgress(JOURNEY_MODE_ID), JOURNEY_ID);
}

/** Clear one node through the ONE writer, exactly as the shell does. */
function clear(storage: StorageService, index: number): void {
  storage.writeModeProgress(
    ctxFor(index),
    withNodeCompleted(
      storage.readModeProgress(JOURNEY_MODE_ID),
      JOURNEY_ID,
      ids[index] as string,
    ),
  );
}

describe("JourneyMode over the committed path", () => {
  test("the path ships with more than one node", () => {
    expect(committed.id).toBe(JOURNEY_ID);
    expect(committed.nodes.length).toBeGreaterThan(1);
  });

  test("the journey URL is same-origin and base-aware", () => {
    expect(journeyUrl(JOURNEY_ID, "/")).toBe("/journeys/beginners-ladder.json");
    expect(journeyUrl(JOURNEY_ID, "/yen-tamizh/")).toBe(
      "/yen-tamizh/journeys/beginners-ladder.json",
    );
  });

  test("loads the real path", async () => {
    const outcome = await loadJourney({ journeyId: JOURNEY_ID, load: diskLoader() });
    expect(outcome.status).toBe("ready");
    if (outcome.status !== "ready") return;
    expect(outcome.journey.nodes.map((node) => node.id)).toEqual(ids);
  });

  test("an unreachable path is a reason, never a thrown error", async () => {
    const outcome = await loadJourney({
      journeyId: JOURNEY_ID,
      base: "/",
      load: diskLoader(["/journeys/beginners-ladder.json"]),
    });
    expect(outcome).toEqual({ status: "unavailable", reason: "load-failed" });
  });

  test("builds a one-item Session from a node, payload untouched", () => {
    const node = committed.nodes[0];
    if (node === undefined) throw new Error("no first node");
    const session = toSession(committed, node, "2026-08-21");
    expect(session.modeId).toBe(JOURNEY_MODE_ID);
    expect(session.sessionId).toBe(`journey-${JOURNEY_ID}-${node.id}`);
    expect(session.gameId).toBe(node.gameId);
    expect(session.packId).toBe(node.packId);
    expect(session.items).toHaveLength(1);
    expect(session.items[0]?.payload).toEqual(node.payload);
  });

  test("every node names a Game the session can carry", () => {
    for (const node of committed.nodes) {
      expect(node.gameId).toMatch(/^[a-z][a-z0-9-]*$/);
      expect(Object.keys(node.payload).length).toBeGreaterThan(0);
    }
  });
});

// --------------------------------------------------------------------------
// THE ORACLE - the progression invariant, driven through the real save
// --------------------------------------------------------------------------

describe("the progression invariant (real StorageService, real path)", () => {
  test("a fresh player is offered the entrance and nothing else", () => {
    const storage = new StorageService({ store: memStore() });
    const states = nodeStates(committed, clearedIn(storage));
    expect(states[0]).toBe("available");
    expect(states.slice(1).every((state) => state === "locked")).toBe(true);
    expect(nextNodeId(committed, clearedIn(storage))).toBe(ids[0]);
  });

  test("node N+1 is playable IF AND ONLY IF node N is recorded complete", () => {
    // Walked one node at a time, asserting the WHOLE path's shape at each step:
    // exactly the cleared prefix is completed, exactly the next node is
    // available, and everything beyond it is still locked. That is the "only
    // if" half and the "if" half in one sweep - a rule that opened the whole
    // path, or that opened nothing, fails on the very first step.
    const storage = new StorageService({ store: memStore() });
    for (let cleared = 0; cleared < ids.length; cleared += 1) {
      const before = nodeStates(committed, clearedIn(storage));
      expect(before[cleared]).toBe("available");
      if (cleared + 1 < ids.length) expect(before[cleared + 1]).toBe("locked");
      expect(isPlayable(committed, clearedIn(storage), ids[cleared] as string)).toBe(true);
      if (cleared + 1 < ids.length) {
        expect(isPlayable(committed, clearedIn(storage), ids[cleared + 1] as string)).toBe(
          false,
        );
      }

      clear(storage, cleared);

      const after = nodeStates(committed, clearedIn(storage));
      expect(after.slice(0, cleared + 1).every((state) => state === "completed")).toBe(true);
      if (cleared + 1 < ids.length) {
        expect(after[cleared + 1]).toBe("available");
        // ...and NOT the whole path: everything past the newly opened node is
        // still waiting on its own predecessor.
        expect(after.slice(cleared + 2).every((state) => state === "locked")).toBe(true);
      }
    }
    expect(nextNodeId(committed, clearedIn(storage))).toBeNull();
  });

  test("clearing a node out of order opens only the node after it", () => {
    // The rule is about the node BEFORE, not about how many are cleared: a save
    // naming only node 5 must open node 6 and leave 2, 3 and 4 shut.
    const storage = new StorageService({ store: memStore() });
    clear(storage, 4);
    const states = nodeStates(committed, clearedIn(storage));
    expect(states[4]).toBe("completed");
    expect(states[5]).toBe("available");
    expect(states[1]).toBe("locked");
    expect(states[2]).toBe("locked");
    expect(states[3]).toBe("locked");
  });

  test("progress survives a reload, and a new day does not reset it", () => {
    const store = memStore();
    clear(new StorageService({ store }), 0);
    // A brand-new service over the SAME bytes is what a reload is.
    const reloaded = new StorageService({ store });
    expect(clearedIn(reloaded)).toEqual([ids[0]]);
    // The Daily's own record expires with the date; a path's must not.
    expect(reloaded.readSessionState({ ...ctxFor(0), date: "2026-09-01" })).toBeNull();
    expect(clearedIn(reloaded)).toEqual([ids[0]]);
    expect(nodeStates(committed, clearedIn(reloaded))[1]).toBe("available");
  });

  test("recording the same node twice does not record it twice", () => {
    const storage = new StorageService({ store: memStore() });
    clear(storage, 0);
    clear(storage, 0);
    expect(clearedIn(storage)).toEqual([ids[0]]);
  });

  test("a Journey's progress and the runner's session record do not collide", () => {
    const storage = new StorageService({ store: memStore() });
    clear(storage, 0);
    // The runner snapshots under perMode[modeId]; progress lives under its own
    // key, so a snapshot cannot wipe the path.
    storage.writeSessionState(ctxFor(1), {
      itemIndex: 0,
      completedCount: 0,
      totalScore: 0,
      currentGameState: null,
      sessionId: `journey-${JOURNEY_ID}-${ids[1] as string}`,
    });
    expect(clearedIn(storage)).toEqual([ids[0]]);
  });

  test("an ABSENT record unlocks nothing beyond the entrance", () => {
    const storage = new StorageService({ store: memStore() });
    expect(storage.readModeProgress(JOURNEY_MODE_ID)).toBeNull();
    expect(clearedIn(storage)).toEqual([]);
    expect(isPlayable(committed, clearedIn(storage), ids[1] as string)).toBe(false);
  });

  test("a TAMPERED record unlocks nothing - unreadable is not cleared", () => {
    // Every shape a hand-edited save could take, ending in a plausible one
    // whose value is a string rather than a list. `perMode` is an OPEN object
    // in the save schema, so ajv passes all of these: refusing them is the
    // Mode's job, and it must refuse by locking rather than by opening.
    const tampered: unknown[] = [
      "everything",
      42,
      [],
      { completed: "everything" },
      { completed: { [JOURNEY_ID]: "everything" } },
      { completed: { [JOURNEY_ID]: [1, 2, 3] } },
      { cleared: { [JOURNEY_ID]: ids } },
    ];
    for (const value of tampered) {
      expect(completedNodeIds(value, JOURNEY_ID)).toEqual([]);
      expect(nodeStates(committed, completedNodeIds(value, JOURNEY_ID))[1]).toBe("locked");
    }
    // A record for ANOTHER path is not this path's progress either.
    expect(completedNodeIds({ completed: { "some-other-path": ids } }, JOURNEY_ID)).toEqual(
      [],
    );
  });

  test("a name that is not a node of this path unlocks nothing", () => {
    const cleared = ["not-a-node", "neither-is-this"];
    expect(nodeStates(committed, cleared)).toEqual([
      "available",
      ...ids.slice(1).map(() => "locked"),
    ]);
    expect(isPlayable(committed, cleared, "not-a-node")).toBe(false);
  });

  test("one path's progress leaves another path's alone", () => {
    const storage = new StorageService({ store: memStore() });
    clear(storage, 0);
    storage.writeModeProgress(
      ctxFor(0),
      withNodeCompleted(
        storage.readModeProgress(JOURNEY_MODE_ID),
        "another-path",
        "its-own-node",
      ),
    );
    expect(clearedIn(storage)).toEqual([ids[0]]);
    expect(
      completedNodeIds(storage.readModeProgress(JOURNEY_MODE_ID), "another-path"),
    ).toEqual(["its-own-node"]);
  });

  test("a path whose first node waits on nothing before it stays shut", () => {
    // The contract refuses this file; the Mode still refuses to guess, because
    // an older build could have served it. Rebuilt head-and-tail rather than
    // mapped: the generated `nodes` type is a tuple with a required first
    // element, and `.map` widens it to a plain array.
    const [first, ...rest] = committed.nodes;
    if (first === undefined) throw new Error("no first node");
    const orphaned: Journey = {
      ...committed,
      nodes: [{ ...first, unlockRule: "previous-complete" as const }, ...rest],
    };
    expect(nodeStates(orphaned, [])[0]).toBe("locked");
    expect(nextNodeId(orphaned, [])).toBeNull();
  });
});
