import { describe, expect, test } from "vitest";

import { previousDayIso, todayIso } from "./dates";

describe("todayIso", () => {
  test("formats the LOCAL calendar day, zero-padded", () => {
    // Local-time construction on purpose: the player's day is the one on their
    // own phone, which is what the bank lookup keys on.
    expect(todayIso(new Date(2026, 7, 13, 23, 59))).toBe("2026-08-13");
    expect(todayIso(new Date(2026, 0, 1, 0, 0))).toBe("2026-01-01");
    expect(todayIso(new Date(2026, 11, 9, 12, 0))).toBe("2026-12-09");
  });
});

describe("previousDayIso", () => {
  test("steps back one day across month and year boundaries", () => {
    expect(previousDayIso("2026-08-13")).toBe("2026-08-12");
    expect(previousDayIso("2026-08-01")).toBe("2026-07-31");
    expect(previousDayIso("2026-01-01")).toBe("2025-12-31");
    expect(previousDayIso("2028-03-01")).toBe("2028-02-29"); // leap year
  });

  test("an unparseable date is returned unchanged rather than becoming NaN", () => {
    expect(previousDayIso("not-a-date")).toBe("not-a-date");
  });
});
