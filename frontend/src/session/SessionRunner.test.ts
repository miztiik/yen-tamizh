import { describe, expect, test } from "vitest";

import { createEventBus } from "../telemetry/bus";
import { createLogger } from "../telemetry/logger";
import { StorageService, type KeyValueStore } from "../services/StorageService";
import type { GameFactory, GameRegistry } from "../games/registry";

import { SessionRunner, type SessionHost } from "./SessionRunner";
import { FakeGame } from "./__fixtures__/fakeGame";
import type { GameContext, GameModule, Session, SessionResult } from "./types";

const flush = () => new Promise<void>((r) => setTimeout(r, 0));

function memStore(): KeyValueStore {
  const map = new Map<string, string>();
  return {
    getItem: (k) => (map.has(k) ? (map.get(k) as string) : null),
    setItem: (k, v) => void map.set(k, v),
    removeItem: (k) => void map.delete(k),
  };
}

function fakeHost() {
  let summary: SessionResult | null = null;
  let progress: { completed: number; total: number } | null = null;
  const stage = { textContent: "" } as unknown as HTMLElement;
  const host: SessionHost = {
    get stage() {
      return stage;
    },
    setProgress(completed, total) {
      progress = { completed, total };
    },
    showSummary(result) {
      summary = result;
    },
    clearStage() {
      (stage as unknown as { textContent: string }).textContent = "";
    },
  };
  return { host, summary: () => summary, progress: () => progress };
}

const twoItem: Session = {
  modeId: "daily",
  packId: "ta-core",
  gameId: "fake",
  sessionId: "run-1",
  date: "2026-08-13",
  items: [
    { gameId: "fake", payload: { label: "one", score: 1 } },
    { gameId: "fake", payload: { label: "two", score: 1 } },
  ],
};

const DAY = { date: "2026-08-13", modeId: "daily", gameId: "fake", packId: "ta-core" };

describe("SessionRunner", () => {
  test("advances item-by-item and shows a summary at the end", async () => {
    const bus = createEventBus();
    const logger = createLogger({ bus, src: "test", session: "s", now: () => 1 });
    const storage = new StorageService({ store: memStore() });
    const created: FakeGame[] = [];
    const factory: GameFactory = () => {
      const g = new FakeGame();
      created.push(g);
      return g;
    };
    const registry: GameRegistry = { fake: { load: async () => factory } };
    const h = fakeHost();

    const runner = new SessionRunner({
      session: twoItem,
      registry,
      storage,
      logger,
      bus,
      host: h.host,
      now: () => 1,
    });

    await runner.start();
    expect(created).toHaveLength(1);

    created[0]!.complete();
    await flush();
    expect(created).toHaveLength(2);

    created[1]!.complete();
    await flush();

    expect(h.summary()).toMatchObject({
      itemsCompleted: 2,
      itemsTotal: 2,
      totalScore: 2,
      reason: "completed",
    });
  });

  test("skips an unknown gameId rather than crashing the session", async () => {
    const bus = createEventBus();
    const logger = createLogger({ bus, src: "test", session: "s", now: () => 1 });
    const storage = new StorageService({ store: memStore() });
    const registry: GameRegistry = {}; // nothing registered
    const h = fakeHost();

    const runner = new SessionRunner({
      session: twoItem,
      registry,
      storage,
      logger,
      bus,
      host: h.host,
      now: () => 1,
    });
    await runner.start();
    await flush();

    // Both items skipped -> straight to the summary, nothing thrown.
    expect(h.summary()).toMatchObject({ itemsCompleted: 0, reason: "completed" });
  });

  test("ORACLE: a reload resumes at the same item with preserved state", async () => {
    const store = memStore(); // shared "browser storage" across the reload

    // Runner A: mount item 0 and place one tile (which snapshots its state).
    const busA = createEventBus();
    const loggerA = createLogger({ bus: busA, src: "test", session: "s", now: () => 1 });
    const storageA = new StorageService({ store });
    const createdA: FakeGame[] = [];
    const factoryA: GameFactory = () => {
      const g = new FakeGame();
      createdA.push(g);
      return g;
    };
    const runnerA = new SessionRunner({
      session: twoItem,
      registry: { fake: { load: async () => factoryA } },
      storage: storageA,
      logger: loggerA,
      bus: busA,
      host: fakeHost().host,
      now: () => 1,
    });
    await runnerA.start();
    expect(createdA).toHaveLength(1);
    createdA[0]!.attempt("A");
    await flush();

    // The mid-item snapshot is durable.
    expect(storageA.readSessionState(DAY)).toMatchObject({
      itemIndex: 0,
      currentGameState: { placed: ["A"] },
    });

    // Runner B: a brand-new runtime over the SAME storage - it must resume.
    const busB = createEventBus();
    const loggerB = createLogger({ bus: busB, src: "test", session: "s", now: () => 2 });
    const storageB = new StorageService({ store });
    const createdB: FakeGame[] = [];
    const factoryB: GameFactory = () => {
      const g = new FakeGame();
      createdB.push(g);
      return g;
    };
    const runnerB = new SessionRunner({
      session: twoItem,
      registry: { fake: { load: async () => factoryB } },
      storage: storageB,
      logger: loggerB,
      bus: busB,
      host: fakeHost().host,
      now: () => 2,
    });
    await runnerB.start();

    // One game mounted (still item 0), and its state was restored.
    expect(createdB).toHaveLength(1);
    expect(createdB[0]!.getState()).toEqual({ placed: ["A"] });
  });

  test("a Game receives only a GameContext - no storage, no app config (boundary)", async () => {
    let captured: GameContext | null = null;
    class RecordingGame implements GameModule {
      mount(stage: HTMLElement, ctx: GameContext) {
        captured = ctx;
        (stage as unknown as { textContent: string }).textContent = "rec";
        ctx.logger.emit("puzzle.started");
      }
      destroy() {}
      getState() {
        return {};
      }
      restoreState() {}
    }

    const bus = createEventBus();
    const logger = createLogger({ bus, src: "test", session: "s", now: () => 1 });
    const storage = new StorageService({ store: memStore() });
    const registry: GameRegistry = { fake: { load: async () => () => new RecordingGame() } };

    const runner = new SessionRunner({
      session: twoItem,
      registry,
      storage,
      logger,
      bus,
      host: fakeHost().host,
      config: { hintsEnabled: true },
      now: () => 1,
    });
    await runner.start();

    expect(captured).not.toBeNull();
    const ctx = captured as unknown as GameContext;
    expect(Object.keys(ctx).sort()).toEqual(["config", "logger", "now", "payload"]);
    expect("storage" in ctx).toBe(false);
    expect(ctx.config).toEqual({ hintsEnabled: true });
  });
});

// The summary must be able to name every word the day held, including the ones
// the player lost - hiding the meaning of a word you lost punishes twice. The
// runner is the SOLE producer of that list, so the summary never reaches into
// `SessionItem.payload`, which is typed `unknown`.
describe("SessionResult.items", () => {
  const wordSession: Session = {
    modeId: "daily",
    packId: "ta-core",
    gameId: "fake",
    sessionId: "run-words",
    date: "2026-08-13",
    items: [
      {
        gameId: "fake",
        payload: { word: "one", meaning: "porul", translationEn: "first", score: 5 },
      },
      { gameId: "fake", payload: { word: "two", meaning: "irandu", score: 5 } },
      { gameId: "fake", payload: { word: "three", score: 5 } },
    ],
  };
  const WORD_DAY = { date: "2026-08-13", modeId: "daily", gameId: "fake", packId: "ta-core" };

  function runnerOver(session: Session, store: KeyValueStore, created: FakeGame[]) {
    const bus = createEventBus();
    const logger = createLogger({ bus, src: "test", session: "s", now: () => 1 });
    const factory: GameFactory = () => {
      const g = new FakeGame();
      created.push(g);
      return g;
    };
    const h = fakeHost();
    const runner = new SessionRunner({
      session,
      registry: { fake: { load: async () => factory } },
      storage: new StorageService({ store }),
      logger,
      bus,
      host: h.host,
      now: () => 1,
    });
    return { runner, host: h };
  }

  test("carries every resolved word in play order, with a solved flag", async () => {
    const created: FakeGame[] = [];
    const { runner, host } = runnerOver(wordSession, memStore(), created);
    await runner.start();

    created[0]!.complete();
    await flush();
    created[1]!.abandon(); // attempts ran out - still a word the player met
    await flush();
    created[2]!.complete();
    await flush();

    // A word with no meaning carries no meaning KEY at all: an empty slot would
    // advertise a hole in the data, so there is nothing for the summary to draw.
    expect(host.summary()?.items).toEqual([
      { word: "one", meaning: "porul", translationEn: "first", solved: true },
      { word: "two", meaning: "irandu", solved: false },
      { word: "three", solved: true },
    ]);
  });

  test("survives a mid-session reload, so a resumed day still names every word", async () => {
    const store = memStore(); // one browser's storage across the reload

    const first: FakeGame[] = [];
    const a = runnerOver(wordSession, store, first);
    await a.runner.start();
    first[0]!.complete();
    await flush();
    expect(new StorageService({ store }).readSessionState(WORD_DAY)?.itemIndex).toBe(1);

    // A brand-new runtime over the same storage picks the list back up.
    const second: FakeGame[] = [];
    const b = runnerOver(wordSession, store, second);
    await b.runner.start();
    second[0]!.complete();
    await flush();
    second[1]!.complete();
    await flush();

    expect(b.host.summary()?.items.map((item) => item.word)).toEqual(["one", "two", "three"]);
  });

  test("leaves out an item whose payload names no word", async () => {
    const created: FakeGame[] = [];
    const { runner, host } = runnerOver(twoItem, memStore(), created); // payloads have labels
    await runner.start();
    created[0]!.complete();
    await flush();
    created[1]!.complete();
    await flush();

    expect(host.summary()?.items).toEqual([]);
    expect(host.summary()?.itemsCompleted).toBe(2);
  });
});
