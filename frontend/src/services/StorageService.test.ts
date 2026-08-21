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

describe("StorageService day-independent Mode progress", () => {
  const JOURNEY: DayContext = {
    date: "2026-08-21",
    modeId: "journey",
    gameId: "anagram",
    packId: "ta-core",
  };

  test("absent progress reads as null, never as an empty promise", () => {
    expect(new StorageService({ store: memStore() }).readModeProgress("journey")).toBeNull();
  });

  test("round-trips a record and survives a later DAY", () => {
    const svc = new StorageService({ store: memStore() });
    svc.writeModeProgress(JOURNEY, { completed: { path: ["one"] } });
    expect(svc.readModeProgress("journey")).toEqual({ completed: { path: ["one"] } });
    // A session state written on ANOTHER date is refused (the Daily's rule);
    // the progress record is not, because a path is not a calendar.
    svc.writeSessionState({ ...JOURNEY, date: "2026-09-01" }, {
      itemIndex: 0,
      completedCount: 0,
      totalScore: 0,
      currentGameState: null,
    });
    expect(svc.readSessionState({ ...JOURNEY, date: "2026-08-21" })).toBeNull();
    expect(svc.readModeProgress("journey")).toEqual({ completed: { path: ["one"] } });
  });

  test("progress and session state occupy different perMode keys", () => {
    const svc = new StorageService({ store: memStore() });
    svc.writeModeProgress(JOURNEY, { completed: { path: ["one"] } });
    svc.writeSessionState(JOURNEY, {
      itemIndex: 1,
      completedCount: 1,
      totalScore: 10,
      currentGameState: null,
    });
    const save = svc.loadSave();
    expect(Object.keys(save?.perMode ?? {}).sort()).toEqual(["journey", "journey-progress"]);
    expect(svc.readModeProgress("journey")).toEqual({ completed: { path: ["one"] } });
  });

  test("one Mode's progress leaves another Mode's alone", () => {
    const svc = new StorageService({ store: memStore() });
    svc.writeModeProgress(JOURNEY, { completed: { path: ["one"] } });
    svc.writeModeProgress({ ...JOURNEY, modeId: "infinite" }, { seen: 3 });
    expect(svc.readModeProgress("journey")).toEqual({ completed: { path: ["one"] } });
    expect(svc.readModeProgress("infinite")).toEqual({ seen: 3 });
  });
});

// The Infinite stream's anti-repeat memory. Kept here rather than in the Mode
// because StorageService is the only writer: the Mode decides WHICH board comes
// next, and this decides what "already seen" means and how long it lasts.
describe("StorageService: the seenInfiniteIds LRU", () => {
  const INFINITE = { ...DAY, modeId: "infinite" };
  const OTHER_MODE = { ...DAY, modeId: "journey" };

  test("an absent save reads as nothing seen, never as a crash", () => {
    expect(new StorageService({ store: memStore() }).readSeenInfiniteIds()).toEqual([]);
  });

  test("ids accumulate oldest-first", () => {
    const svc = new StorageService({ store: memStore() });
    svc.markInfiniteSeen(INFINITE, "anagram/00000", 10);
    svc.markInfiniteSeen(INFINITE, "wordle/00001", 10);
    expect(svc.readSeenInfiniteIds()).toEqual(["anagram/00000", "wordle/00001"]);
  });

  test("re-seeing an id MOVES it to the end (it is an LRU, not a capped set)", () => {
    const svc = new StorageService({ store: memStore() });
    for (const id of ["a/00000", "a/00001", "a/00002"]) {
      svc.markInfiniteSeen(INFINITE, id, 10);
    }
    svc.markInfiniteSeen(INFINITE, "a/00000", 10);
    expect(svc.readSeenInfiniteIds()).toEqual(["a/00001", "a/00002", "a/00000"]);
  });

  test("the window bounds the list, dropping the oldest first", () => {
    const svc = new StorageService({ store: memStore() });
    for (let n = 0; n < 6; n += 1) {
      svc.markInfiniteSeen(INFINITE, `a/${String(n).padStart(5, "0")}`, 3);
    }
    expect(svc.readSeenInfiniteIds()).toEqual(["a/00003", "a/00004", "a/00005"]);
  });

  test("a window of zero remembers nothing (slice(-0) would have kept everything)", () => {
    const svc = new StorageService({ store: memStore() });
    svc.markInfiniteSeen(INFINITE, "a/00000", 0);
    expect(svc.readSeenInfiniteIds()).toEqual([]);
  });

  test("marking a board seen leaves every other Mode's record alone", () => {
    const svc = new StorageService({ store: memStore() });
    svc.writeModeProgress(OTHER_MODE, { completed: { path: ["one"] } });
    svc.markInfiniteSeen(INFINITE, "a/00000", 10);
    expect(svc.readModeProgress("journey")).toEqual({ completed: { path: ["one"] } });
    expect(svc.readSeenInfiniteIds()).toEqual(["a/00000"]);
  });

  test("the bounded list still validates as a save (written through the schema)", () => {
    const svc = new StorageService({ store: memStore() });
    svc.markInfiniteSeen(INFINITE, "a/00000", 2);
    expect(svc.loadSave()).not.toBeNull();
  });
});

// The Time Trial's records. The claim that matters is not that they persist -
// it is that the field they persist into is ADDITIVE, so the save a player
// wrote yesterday still loads today (CLAUDE.md section 11). The backend half of
// the same claim runs the same committed fixture through Pydantic
// (backend/tests/test_core_schemas.py).
describe("StorageService: Time Trial best runs (local only)", () => {
  const TRIAL: DayContext = { ...DAY, modeId: "time-trial", date: "2026-08-21" };

  test("A PRE-ROW-23 SAVE STILL LOADS, and reads as no record set", () => {
    // These are the exact bytes the committed save fixture holds: a save minted
    // before bestTimeTrialRuns existed. It goes in through the store rather
    // than through writeSave, so ajv validates it on the READ path - which is
    // where an older save actually arrives.
    const store = memStore();
    const preRow23 = {
      version: "2026-08-13",
      changelog: [
        { version: "2026-08-13", change: "Initial save fixture.", why: "Row 7 contract Oracle." },
      ],
      dayKey: "2026-08-13|daily|anagram|ta-core",
      streak: 5,
      lastPlayed: "2026-08-13",
      perMode: { daily: { completed: true, stars: 3 } },
      seenInfiniteIds: ["anagram-0007", "anagram-0042"],
    };
    expect("bestTimeTrialRuns" in preRow23).toBe(false);
    store.setItem("yt:save", JSON.stringify(preRow23));

    const svc = new StorageService({ store });
    const loaded = svc.loadSave();
    expect(loaded).not.toBeNull(); // no migration needed - it just validates
    expect(loaded?.streak).toBe(5);
    expect(svc.readBestTimeTrialRuns()).toEqual([]);
  });

  test("a run written onto a pre-Row-23 save keeps everything that was there", () => {
    const store = memStore();
    store.setItem(
      "yt:save",
      JSON.stringify({
        version: "2026-08-13",
        changelog: [{ version: "2026-08-13", change: "old", why: "old" }],
        dayKey: "2026-08-13|daily|anagram|ta-core",
        streak: 5,
        lastPlayed: "2026-08-13",
        perMode: { daily: { completed: true } },
        seenInfiniteIds: ["anagram/00007"],
      }),
    );
    const svc = new StorageService({ store });
    svc.writeBestTimeTrialRuns(TRIAL, [
      { durationSec: 120, itemsCompleted: 6, achievedOn: "2026-08-21" },
    ]);
    const after = svc.loadSave();
    expect(after?.streak).toBe(5);
    expect(after?.perMode.daily).toEqual({ completed: true });
    expect(after?.seenInfiniteIds).toEqual(["anagram/00007"]);
    expect(after?.bestTimeTrialRuns).toEqual([
      { durationSec: 120, itemsCompleted: 6, achievedOn: "2026-08-21" },
    ]);
  });

  test("an absent save reads as no records, never as a crash", () => {
    expect(new StorageService({ store: memStore() }).readBestTimeTrialRuns()).toEqual([]);
  });

  test("records round-trip and survive an unrelated write", () => {
    const svc = new StorageService({ store: memStore() });
    svc.writeBestTimeTrialRuns(TRIAL, [
      { durationSec: 120, itemsCompleted: 6, achievedOn: "2026-08-21" },
      { durationSec: 30, itemsCompleted: 2, achievedOn: "2026-08-20" },
    ]);
    svc.markInfiniteSeen({ ...TRIAL, modeId: "infinite" }, "anagram/00000", 10);
    expect(svc.readBestTimeTrialRuns()).toHaveLength(2);
    expect(svc.readSeenInfiniteIds()).toEqual(["anagram/00000"]);
  });

  test("the save is written through the schema, so a bad record is refused", () => {
    const svc = new StorageService({ store: memStore() });
    expect(() =>
      svc.writeBestTimeTrialRuns(TRIAL, [
        // durationSec must be at least 1 - a contest with no length is not one.
        { durationSec: 0, itemsCompleted: 3, achievedOn: "2026-08-21" },
      ]),
    ).toThrow(/invalid save/i);
  });

  test("the stamped version matches the newest changelog entry", () => {
    // The save carries its own contract stamp, and ajv checks the date pattern
    // on every write; this pins that the two agree.
    const svc = new StorageService({ store: memStore() });
    svc.writeBestTimeTrialRuns(TRIAL, []);
    const save = svc.loadSave();
    expect(save?.version).toBe(save?.changelog[0]?.version);
    expect(save?.changelog.some((entry) => entry.change.includes("bestTimeTrialRuns"))).toBe(
      true,
    );
  });
});
