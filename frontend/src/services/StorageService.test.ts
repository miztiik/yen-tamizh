import { describe, expect, test } from "vitest";

import type { Save } from "../contracts/save";
import { computeDayKey, type DayContext } from "../session/dayKey";
import type { SessionState } from "../session/types";

import { StorageService, type KeyValueStore } from "./StorageService";

function memStore(): KeyValueStore & { map: Map<string, string> } {
  const map = new Map<string, string>();
  return {
    map,
    getItem: (k) => (map.has(k) ? (map.get(k) as string) : null),
    setItem: (k, v) => void map.set(k, v),
    removeItem: (k) => void map.delete(k),
  };
}

const DAY: DayContext = {
  date: "2026-08-13",
  modeId: "daily",
  gameId: "anagram",
  packId: "ta-core",
};

function validSave(): Save {
  return {
    version: "2026-08-13",
    changelog: [{ version: "2026-08-13", change: "test", why: "test" }],
    dayKey: computeDayKey(DAY.date, DAY.modeId, DAY.gameId, DAY.packId),
    streak: 2,
    lastPlayed: "2026-08-13",
    perMode: { daily: { completed: true } },
    seenInfiniteIds: [],
  };
}

describe("StorageService (the only persistence writer)", () => {
  test("write -> load round-trips a valid save deep-equal", () => {
    const svc = new StorageService({ store: memStore() });
    const save = validSave();
    svc.writeSave(save);
    expect(svc.loadSave()).toEqual(save);
  });

  test("uses the yt: key prefix", () => {
    const store = memStore();
    new StorageService({ store }).writeSave(validSave());
    expect([...store.map.keys()]).toEqual(["yt:save"]);
  });

  test("loadSave returns null when absent or corrupt", () => {
    const store = memStore();
    const svc = new StorageService({ store });
    expect(svc.loadSave()).toBeNull();
    store.setItem("yt:save", "{not json");
    expect(svc.loadSave()).toBeNull();
  });

  test("writeSave refuses an invalid shape (fail fast at the boundary)", () => {
    const svc = new StorageService({ store: memStore() });
    const bad = { ...validSave(), streak: -1 } as unknown as Save; // streak must be >= 0
    expect(() => svc.writeSave(bad)).toThrow(/invalid save/i);
  });

  test("session state round-trips within the same day", () => {
    const svc = new StorageService({ store: memStore() });
    const state: SessionState = {
      itemIndex: 1,
      completedCount: 1,
      totalScore: 5,
      currentGameState: { placed: ["a", "b"] },
    };
    svc.writeSessionState(DAY, state);
    expect(svc.readSessionState(DAY)).toEqual(state);
  });

  test("writeSessionState stamps a freshly recomputed dayKey", () => {
    const svc = new StorageService({ store: memStore() });
    svc.writeSessionState(DAY, {
      itemIndex: 0,
      completedCount: 0,
      totalScore: 0,
      currentGameState: null,
    });
    expect(svc.loadSave()?.dayKey).toBe("2026-08-13|daily|anagram|ta-core");
  });

  test("a save from another day does not resume (new-day guard)", () => {
    const svc = new StorageService({ store: memStore() });
    svc.writeSessionState(DAY, {
      itemIndex: 1,
      completedCount: 1,
      totalScore: 5,
      currentGameState: null,
    });
    expect(svc.readSessionState({ ...DAY, date: "2026-08-14" })).toBeNull();
  });

  test("resume never trusts the stored dayKey - a tampered key is ignored", () => {
    const store = memStore();
    const svc = new StorageService({ store });
    const state: SessionState = {
      itemIndex: 1,
      completedCount: 1,
      totalScore: 5,
      currentGameState: { placed: ["x"] },
    };
    svc.writeSessionState(DAY, state);

    // Tamper the persisted dayKey; the reader recomputes freshness from the
    // value fields, so it still resolves the same-day state.
    const tampered = svc.loadSave() as Save;
    tampered.dayKey = "9999-01-01|evil|evil|evil";
    svc.writeSave(tampered);
    expect(svc.readSessionState(DAY)).toEqual(state);
  });
});

describe("the streak ticks once per completed day", () => {
  test("a first completion starts the run at 1", () => {
    const svc = new StorageService({ store: memStore() });
    expect(svc.tickStreak(DAY)).toEqual({ before: 0, after: 1, ticked: true });
    expect(svc.loadSave()?.streak).toBe(1);
    expect(svc.loadSave()?.lastStreakDay).toBe(DAY.date);
  });

  test("re-completing the same day does NOT tick again (idempotent)", () => {
    const svc = new StorageService({ store: memStore() });
    svc.tickStreak(DAY);
    expect(svc.tickStreak(DAY)).toEqual({ before: 1, after: 1, ticked: false });
    expect(svc.tickStreak(DAY)).toEqual({ before: 1, after: 1, ticked: false });
    expect(svc.loadSave()?.streak).toBe(1);
  });

  test("finishing the next day extends the run", () => {
    const svc = new StorageService({ store: memStore() });
    svc.tickStreak(DAY);
    expect(svc.tickStreak({ ...DAY, date: "2026-08-14" })).toEqual({
      before: 1,
      after: 2,
      ticked: true,
    });
    expect(svc.tickStreak({ ...DAY, date: "2026-08-15" }).after).toBe(3);
  });

  test("a skipped day restarts the run at 1 (an honest streak)", () => {
    const svc = new StorageService({ store: memStore() });
    svc.tickStreak(DAY);
    svc.tickStreak({ ...DAY, date: "2026-08-14" });
    expect(svc.tickStreak({ ...DAY, date: "2026-08-16" })).toEqual({
      before: 2,
      after: 1,
      ticked: true,
    });
  });

  test("ticking preserves the day's session progress (single writer, no clobber)", () => {
    const svc = new StorageService({ store: memStore() });
    const state: SessionState = {
      itemIndex: 3,
      completedCount: 3,
      totalScore: 90,
      currentGameState: null,
    };
    svc.writeSessionState(DAY, state);
    svc.tickStreak(DAY);
    expect(svc.readSessionState(DAY)).toEqual(state);
    expect(svc.loadSave()?.streak).toBe(1);
  });

  test("a pre-Row-13 save without lastStreakDay still loads and ticks", () => {
    const store = memStore();
    const legacy = validSave();
    delete (legacy as { lastStreakDay?: string }).lastStreakDay;
    store.setItem("yt:save", JSON.stringify(legacy));
    const svc = new StorageService({ store });
    expect(svc.loadSave()).not.toBeNull();
    expect(svc.tickStreak(DAY)).toEqual({ before: 2, after: 1, ticked: true });
  });
});
