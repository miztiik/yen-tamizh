import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, test, vi } from "vitest";

import appConfigJson from "../../../config/app-config.json";
import { loadValidated, type SchemaName, type SchemaPayload } from "../contracts";
import type { PoolIndex, PoolItem } from "../contracts";
import { StorageService, type KeyValueStore } from "../services/StorageService";
import type { DayContext } from "../session/dayKey";

import {
  INFINITE_MODE_ID,
  InfiniteStream,
  eligible,
  pickNext,
  poolIndexUrl,
  poolItemUrl,
  seenKey,
  toSession,
} from "./InfiniteMode";

// The committed config is the source of the two numbers this Mode turns on.
const LRU_WINDOW = appConfigJson.infinite.lruWindow;
const DEFAULT_BAND = appConfigJson.infinite.defaultDifficulty;

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const poolDir = resolve(repoRoot, "frontend/public/pool");

const DAY: DayContext = {
  date: "2026-08-21",
  modeId: INFINITE_MODE_ID,
  gameId: "anagram",
  packId: "ta-core",
};

function memStore(): KeyValueStore {
  const map = new Map<string, string>();
  return {
    getItem: (k) => (map.has(k) ? (map.get(k) as string) : null),
    setItem: (k, v) => void map.set(k, v),
    removeItem: (k) => void map.delete(k),
  };
}

/** A pool of `count` boards of one band for one Game - the shape, not the words. */
function fakeIndex(gameId: string, count: number, difficulty: string): PoolIndex {
  return {
    version: "2026-08-21T22:00",
    changelog: [{ version: "2026-08-21T22:00", change: "test", why: "test" }],
    gameId,
    totalCount: count,
    items: Array.from({ length: count }, (_, ordinal) => ({
      id: String(ordinal).padStart(5, "0"),
      difficulty,
    })),
  };
}

function fakeItem(gameId: string, id: string, difficulty: string): PoolItem {
  return {
    id,
    gameId,
    packId: "ta-core",
    difficulty,
    payload: { word: `${gameId}-${id}`, tiles: ["\u0b95"], attempts: 3 },
  };
}

/**
 * A loader over a fabricated pool - the ONLY thing faked here, and only because
 * the property under test is about which board is chosen over hundreds of
 * picks, which no committed pool of a fixed shape can pin. The real bytes are
 * exercised separately below through `loadValidated`.
 */
function poolLoader(
  indexes: Record<string, PoolIndex>,
): <K extends SchemaName>(url: string, name: K) => Promise<SchemaPayload[K]> {
  return async <K extends SchemaName>(url: string, name: K) => {
    const match = /\/pool\/([a-z0-9-]+)\/([^/]+)\.json$/.exec(url);
    if (match === null) throw new Error(`not a pool url: ${url}`);
    const gameId = match[1] as string;
    const stem = match[2] as string;
    const index = indexes[gameId];
    if (index === undefined) throw new Error(`no pool for ${gameId}`);
    if (name === "pool-index") return index as SchemaPayload[K];
    const entry = index.items.find((item) => item.id === stem);
    if (entry === undefined) throw new Error(`no item ${stem}`);
    return fakeItem(gameId, entry.id, entry.difficulty) as SchemaPayload[K];
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("InfiniteMode: urls and framing", () => {
  test("both urls are same-origin and base-aware (Holy Law #1)", () => {
    expect(poolIndexUrl("anagram", "/yen-tamizh/")).toBe(
      "/yen-tamizh/pool/anagram/index.json",
    );
    expect(poolItemUrl("wordle", "00042", "/")).toBe("/pool/wordle/00042.json");
  });

  test("a seen key is Game-qualified, because an id is only an ordinal", () => {
    expect(seenKey("anagram", "00042")).toBe("anagram/00042");
    expect(seenKey("wordle", "00042")).not.toBe(seenKey("anagram", "00042"));
  });

  test("a board becomes a one-item session with an id of its own", () => {
    const session = toSession(fakeItem("wordle", "00007", "hard"), "2026-08-21");
    expect(session.modeId).toBe(INFINITE_MODE_ID);
    expect(session.gameId).toBe("wordle");
    expect(session.sessionId).toBe("infinite-wordle-00007");
    expect(session.items).toHaveLength(1);
  });
});

describe("InfiniteMode: choosing the next board", () => {
  test("the difficulty filter admits only its own band", () => {
    const index: PoolIndex = {
      ...fakeIndex("anagram", 0, "easy"),
      totalCount: 3,
      items: [
        { id: "00000", difficulty: "easy" },
        { id: "00001", difficulty: "medium" },
        { id: "00002", difficulty: "medium" },
      ],
    };
    expect(eligible(index, "medium").map((entry) => entry.id)).toEqual([
      "00001",
      "00002",
    ]);
    expect(pickNext(index, "medium", [])).toBe("00001");
    expect(pickNext(index, "hard", [])).toBeNull();
  });

  test("an unseen board is always preferred, in index order", () => {
    const index = fakeIndex("anagram", 4, "medium");
    expect(pickNext(index, "medium", [])).toBe("00000");
    expect(pickNext(index, "medium", ["anagram/00000"])).toBe("00001");
    expect(pickNext(index, "medium", ["anagram/00000", "anagram/00001"])).toBe("00002");
  });

  test("another Game's seen ids never hide this Game's boards", () => {
    const index = fakeIndex("anagram", 2, "medium");
    expect(pickNext(index, "medium", ["wordle/00000", "wordle/00001"])).toBe("00000");
  });

  test("an exhausted band recycles the LEAST RECENTLY seen board", () => {
    const index = fakeIndex("anagram", 3, "medium");
    const seen = ["anagram/00001", "anagram/00002", "anagram/00000"];
    expect(pickNext(index, "medium", seen)).toBe("00001");
  });
});

describe("InfiniteMode: the stream", () => {
  test("it rotates the Games rather than emptying one", async () => {
    const games = ["anagram", "wordle", "crossword"];
    const stream = new InfiniteStream({
      games,
      date: DAY.date,
      difficulty: "medium",
      seen: () => [],
      base: "/",
      load: poolLoader(Object.fromEntries(games.map((g) => [g, fakeIndex(g, 5, "medium")]))),
    });
    const dealt: string[] = [];
    for (let pick = 0; pick < 3; pick += 1) {
      const outcome = await stream.next();
      expect(outcome.status).toBe("ready");
      if (outcome.status === "ready") dealt.push(outcome.step.gameId);
    }
    expect(dealt).toEqual(games);
  });

  test("it steps over a Game whose pool will not load", async () => {
    const stream = new InfiniteStream({
      games: ["broken", "wordle"],
      date: DAY.date,
      difficulty: "medium",
      seen: () => [],
      base: "/",
      load: poolLoader({ wordle: fakeIndex("wordle", 2, "medium") }),
    });
    const outcome = await stream.next();
    expect(outcome.status).toBe("ready");
    if (outcome.status === "ready") expect(outcome.step.gameId).toBe("wordle");
  });

  test("a difficulty no pool holds is an answer, not a spin", async () => {
    const stream = new InfiniteStream({
      games: ["anagram"],
      date: DAY.date,
      difficulty: "hard",
      seen: () => [],
      base: "/",
      load: poolLoader({ anagram: fakeIndex("anagram", 3, "easy") }),
    });
    expect(await stream.next()).toEqual({ status: "unavailable", reason: "empty-pool" });
  });

  test("no pool at all reads as load-failed, never as a crash", async () => {
    const stream = new InfiniteStream({
      games: ["anagram"],
      date: DAY.date,
      difficulty: DEFAULT_BAND,
      seen: () => [],
      base: "/",
      load: poolLoader({}),
    });
    expect(await stream.next()).toEqual({ status: "unavailable", reason: "load-failed" });
  });

  test("the difficulty filter can be changed mid-stream", async () => {
    const index: PoolIndex = {
      ...fakeIndex("anagram", 0, "easy"),
      totalCount: 2,
      items: [
        { id: "00000", difficulty: "easy" },
        { id: "00001", difficulty: "hard" },
      ],
    };
    const stream = new InfiniteStream({
      games: ["anagram"],
      date: DAY.date,
      difficulty: "easy",
      seen: () => [],
      base: "/",
      load: poolLoader({ anagram: index }),
    });
    const first = await stream.next();
    expect(first.status === "ready" && first.step.id).toBe("00000");
    stream.setDifficulty("hard");
    expect(stream.band).toBe("hard");
    const second = await stream.next();
    expect(second.status === "ready" && second.step.id).toBe("00001");
  });
});

// THE ORACLE. The Mode's whole promise, checked end to end against the real
// StorageService and the real committed window: over lruWindow + 1 consecutive
// picks, no board is ever dealt twice inside the window.
//
// The fabricated pool is deliberately only slightly larger than the window (210
// eligible boards against a window of 200), because a pool many times the
// window would pass the test without ever exercising the recycle path - the
// interesting picks are the ones taken AFTER every board has been seen once.
describe("InfiniteMode: the anti-repeat Oracle", () => {
  test(`no board recurs within ${LRU_WINDOW} picks, through the real save`, async () => {
    const games = ["anagram", "crossword", "missing-letters", "word-ladder", "word-search", "wordle"];
    const perGame = 35; // 6 x 35 = 210 eligible, against a window of 200
    const storage = new StorageService({ store: memStore() });
    const stream = new InfiniteStream({
      games,
      date: DAY.date,
      difficulty: DEFAULT_BAND,
      seen: () => storage.readSeenInfiniteIds(),
      base: "/",
      load: poolLoader(
        Object.fromEntries(games.map((g) => [g, fakeIndex(g, perGame, DEFAULT_BAND)])),
      ),
    });

    const dealt: string[] = [];
    for (let pick = 0; pick <= LRU_WINDOW; pick += 1) {
      const outcome = await stream.next();
      expect(outcome.status, `pick ${pick} stalled`).toBe("ready");
      if (outcome.status !== "ready") break;
      storage.markInfiniteSeen(DAY, outcome.step.seenKey, LRU_WINDOW);
      dealt.push(outcome.step.seenKey);
    }

    expect(dealt).toHaveLength(LRU_WINDOW + 1);
    for (let at = 0; at < dealt.length; at += 1) {
      const window = dealt.slice(Math.max(0, at - LRU_WINDOW), at);
      expect(window, `${dealt[at]} recurred inside the window at pick ${at}`).not.toContain(
        dealt[at],
      );
    }
    // The window is bounded, so a player who never stops does not grow the save.
    expect(storage.readSeenInfiniteIds()).toHaveLength(LRU_WINDOW);
  });

  test("a pool SMALLER than the window recycles oldest-first and never stalls", async () => {
    const storage = new StorageService({ store: memStore() });
    const stream = new InfiniteStream({
      games: ["anagram"],
      date: DAY.date,
      difficulty: DEFAULT_BAND,
      seen: () => storage.readSeenInfiniteIds(),
      base: "/",
      load: poolLoader({ anagram: fakeIndex("anagram", 3, DEFAULT_BAND) }),
    });
    const dealt: string[] = [];
    for (let pick = 0; pick < 12; pick += 1) {
      const outcome = await stream.next();
      expect(outcome.status, `pick ${pick} stalled on an exhausted pool`).toBe("ready");
      if (outcome.status !== "ready") break;
      storage.markInfiniteSeen(DAY, outcome.step.seenKey, LRU_WINDOW);
      dealt.push(outcome.step.id);
    }
    // The documented exhaustion behaviour: the least recently seen board comes
    // back, so three boards cycle in order for ever rather than dead-ending.
    expect(dealt).toEqual([
      "00000",
      "00001",
      "00002",
      "00000",
      "00001",
      "00002",
      "00000",
      "00001",
      "00002",
      "00000",
      "00001",
      "00002",
    ]);
  });
});

// The bridged validator, against the bytes the bundle actually ships. A pool
// item's shape lives in pool-index.schema.json's $defs rather than in a schema
// file of its own; this is what proves that indirection really validates.
describe("InfiniteMode: the committed pool passes the load boundary", () => {
  function stubFetch(body: string): void {
    // Mock carve-out (a): fetch is stubbed in a loader unit test (Holy Law #7).
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(body, {
            status: 200,
            headers: { "content-type": "application/json" },
          }),
      ),
    );
  }

  test("a committed index validates as pool-index", async () => {
    stubFetch(readFileSync(resolve(poolDir, "anagram/index.json"), "utf-8"));
    const index = await loadValidated("/pool/anagram/index.json", "pool-index");
    expect(index.gameId).toBe("anagram");
    expect(index.totalCount).toBe(index.items.length);
  });

  test("a committed board validates as pool-item", async () => {
    stubFetch(readFileSync(resolve(poolDir, "anagram/00000.json"), "utf-8"));
    const item = await loadValidated("/pool/anagram/00000.json", "pool-item");
    expect(item.id).toBe("00000");
    expect(item.gameId).toBe("anagram");
  });

  test("a board with a malformed id is REJECTED by the bridged validator", async () => {
    const real = JSON.parse(
      readFileSync(resolve(poolDir, "anagram/00000.json"), "utf-8"),
    ) as PoolItem;
    stubFetch(JSON.stringify({ ...real, id: "42" }));
    await expect(loadValidated("/pool/anagram/00000.json", "pool-item")).rejects.toThrow(
      /failed/i,
    );
  });
});
