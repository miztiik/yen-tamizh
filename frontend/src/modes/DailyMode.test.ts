import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

import type { BankIndex, PuzzleFile, SchemaName, SchemaPayload } from "../contracts";
import {
  DAILY_MODE_ID,
  bankDayUrl,
  bankIndexUrl,
  loadDailySession,
  pickDay,
  toSession,
} from "./DailyMode";

// The REAL committed bank, read straight off disk (Holy Law #7: real fixtures,
// no mocks). The loader is INJECTED rather than stubbed, so these tests prove
// the Mode's framing without pretending to be a browser - and prove it against
// the same bytes the deployed bundle ships.
const here = dirname(fileURLToPath(import.meta.url));
const bankDir = resolve(here, "../../public/bank");

function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, "utf-8")) as T;
}

const committedIndex = readJson<BankIndex>(resolve(bankDir, "index.json"));
const firstDay = committedIndex.days[0]?.date ?? "";

/** A loader that serves the committed bank from disk by URL. */
function diskLoader(missing: string[] = []) {
  // Fewer parameters than the signature: the disk loader needs no schema name,
  // because the bytes it returns are the same ones ajv validates in the browser.
  return async <K extends SchemaName>(url: string): Promise<SchemaPayload[K]> => {
    if (missing.includes(url)) throw new Error(`404 ${url}`);
    const relative = url.slice(url.indexOf("bank/") + "bank/".length);
    return readJson<SchemaPayload[K]>(resolve(bankDir, relative));
  };
}

describe("DailyMode over the committed bank", () => {
  test("the bank ships at least today's day", () => {
    expect(committedIndex.days.length).toBeGreaterThan(0);
    expect(firstDay).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  test("builds a Session from a real baked day", async () => {
    const outcome = await loadDailySession({ today: firstDay, load: diskLoader() });
    expect(outcome.status).toBe("ready");
    if (outcome.status !== "ready") return;

    expect(outcome.date).toBe(firstDay);
    expect(outcome.isToday).toBe(true);
    expect(outcome.session.modeId).toBe(DAILY_MODE_ID);
    expect(outcome.session.sessionId).toBe(`${DAILY_MODE_ID}-${firstDay}`);
    expect(outcome.session.date).toBe(firstDay);
    expect(outcome.session.items.length).toBeGreaterThan(0);

    const day = readJson<PuzzleFile>(resolve(bankDir, firstDay.slice(0, 4), `${firstDay}.json`));
    expect(outcome.session.items.map((item) => item.gameId)).toEqual(
      day.items.map((item) => item.gameId),
    );
    // The payload reaches the Game untouched - the Mode frames, it never edits.
    expect(outcome.session.items[0]?.payload).toEqual(day.items[0]?.payload);
    expect(outcome.session.gameId).toBe(day.items[0]?.gameId);
    expect(outcome.session.packId).toBe(day.items[0]?.packId);
  });

  test("a day's theme reaches the Session, and an ordinary day carries none", () => {
    // The slug travels, never the Tamil label: the shell already reads copy,
    // and a baked label could only be corrected by a rebuild.
    const dates = committedIndex.days.map((day) => day.date);
    const days = dates.map((date) =>
      readJson<PuzzleFile>(resolve(bankDir, date.slice(0, 4), `${date}.json`)),
    );
    const themed = days.find((day) => day.theme !== undefined);
    const ordinary = days.find((day) => day.theme === undefined);
    expect(themed, "the committed bank holds no themed day").toBeDefined();
    expect(ordinary, "the committed bank holds no ordinary day").toBeDefined();

    expect(toSession(themed!, themed!.date).theme).toBe(themed!.theme);
    expect(toSession(ordinary!, ordinary!.date).theme).toBeUndefined();
  });

  test("a day holds several Games and each item keeps its own", () => {
    const dates = committedIndex.days.map((day) => day.date);
    const mixed = dates
      .map((date) => readJson<PuzzleFile>(resolve(bankDir, date.slice(0, 4), `${date}.json`)))
      .find((day) => new Set(day.items.map((item) => item.gameId)).size > 1);
    expect(mixed, "the committed bank holds no multi-Game day").toBeDefined();

    const session = toSession(mixed!, mixed!.date);
    expect(session.items.map((item) => item.gameId)).toEqual(
      mixed!.items.map((item) => item.gameId),
    );
    // The day key is scoped by the FIRST item's Game; every other item still
    // names its own, which is what the runner mounts on.
    expect(session.gameId).toBe(mixed!.items[0]?.gameId);
  });

  test("a player whose calendar ran ahead still gets the newest baked day", async () => {
    const outcome = await loadDailySession({ today: "2999-01-01", load: diskLoader() });
    expect(outcome.status).toBe("ready");
    if (outcome.status !== "ready") return;
    const newest = committedIndex.days[committedIndex.days.length - 1]?.date;
    expect(outcome.date).toBe(newest);
    expect(outcome.isToday).toBe(false);
  });

  test("a day baked for tomorrow is never opened early", () => {
    const index: BankIndex = {
      ...committedIndex,
      days: [
        { date: "2026-08-13", itemCount: 3 },
        { date: "2026-08-14", itemCount: 3 },
      ],
    };
    expect(pickDay(index, "2026-08-13")).toBe("2026-08-13");
    expect(pickDay(index, "2026-08-12")).toBeNull();
  });

  test("an unreachable bank is a message, not an exception", async () => {
    const outcome = await loadDailySession({
      today: firstDay,
      load: diskLoader([bankIndexUrl("/")]),
      base: "/",
    });
    expect(outcome).toEqual({ status: "unavailable", reason: "load-failed" });
  });

  test("an unreachable day is a message, not an exception", async () => {
    const outcome = await loadDailySession({
      today: firstDay,
      load: diskLoader([bankDayUrl(firstDay, "/")]),
      base: "/",
    });
    expect(outcome).toEqual({ status: "unavailable", reason: "load-failed" });
  });

  test("an empty bank reports itself", async () => {
    const load = async <K extends SchemaName>(): Promise<SchemaPayload[K]> =>
      ({ ...committedIndex, days: [] }) as unknown as SchemaPayload[K];
    const outcome = await loadDailySession({ today: firstDay, load });
    expect(outcome).toEqual({ status: "unavailable", reason: "empty-bank" });
  });
});

describe("DailyMode URLs stay same-origin and base-aware", () => {
  test("the bank is addressed under the deployment base", () => {
    expect(bankIndexUrl("/yen-tamizh/")).toBe("/yen-tamizh/bank/index.json");
    expect(bankDayUrl("2026-08-13", "/yen-tamizh/")).toBe(
      "/yen-tamizh/bank/2026/2026-08-13.json",
    );
    expect(bankIndexUrl("/")).toBe("/bank/index.json");
  });

  test("no URL the Mode builds is absolute (Holy Law #1)", () => {
    for (const url of [bankIndexUrl("/"), bankDayUrl(firstDay, "/")]) {
      expect(url.startsWith("http")).toBe(false);
      expect(url.startsWith("//")).toBe(false);
    }
  });
});

describe("session framing", () => {
  test("an empty day cannot become a session", async () => {
    const load = async <K extends SchemaName>(url: string): Promise<SchemaPayload[K]> => {
      if (url.endsWith("index.json")) return committedIndex as unknown as SchemaPayload[K];
      const day = readJson<PuzzleFile>(
        resolve(bankDir, firstDay.slice(0, 4), `${firstDay}.json`),
      );
      return { ...day, items: [] } as unknown as SchemaPayload[K];
    };
    const outcome = await loadDailySession({ today: firstDay, load });
    expect(outcome).toEqual({ status: "unavailable", reason: "no-day" });
  });

  test("toSession keeps the playlist order", () => {
    const day = readJson<PuzzleFile>(resolve(bankDir, firstDay.slice(0, 4), `${firstDay}.json`));
    const session = toSession(day, firstDay);
    expect(session.items.length).toBe(day.items.length);
    session.items.forEach((item, index) => {
      expect(item.payload).toEqual(day.items[index]?.payload);
    });
  });
});
