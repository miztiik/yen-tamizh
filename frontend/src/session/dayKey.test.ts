import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

import { computeDayKey, dayKeyOf } from "./dayKey";

// Parity Oracle: the TypeScript twin must reproduce the backend's
// compute_day_key exactly. We assert against the committed shared fixture the
// backend test also loads (datasets/fixtures/contracts/save_valid.json), so
// py-intent == fixture == ts.
const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const saveFixture = JSON.parse(
  readFileSync(resolve(repoRoot, "datasets/fixtures/contracts/save_valid.json"), "utf-8"),
) as { dayKey: string };

describe("computeDayKey (TS twin of backend compute_day_key)", () => {
  test("reproduces the date|modeId|gameId|packId form", () => {
    expect(computeDayKey("2026-08-13", "daily", "anagram", "ta-core")).toBe(
      "2026-08-13|daily|anagram|ta-core",
    );
  });

  test("recomputes the committed save fixture's dayKey byte-for-byte", () => {
    const [date, modeId, gameId, packId] = saveFixture.dayKey.split("|");
    expect(computeDayKey(date!, modeId!, gameId!, packId!)).toBe(saveFixture.dayKey);
  });

  test("dayKeyOf agrees with computeDayKey", () => {
    const ctx = { date: "2026-08-13", modeId: "daily", gameId: "anagram", packId: "ta-core" };
    expect(dayKeyOf(ctx)).toBe(computeDayKey(ctx.date, ctx.modeId, ctx.gameId, ctx.packId));
  });
});
