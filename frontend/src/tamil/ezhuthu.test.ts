import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

import { classify, segment, type EzhuthuKind } from "./ezhuthu";

interface GoldenRow {
  word: string;
  ezhuthu: string[];
}

// The SAME golden corpus the Python twin loads, resolved relative to this file
// (repo-root independent of the vitest cwd). Both suites asserting against this
// one file is the cross-language parity Oracle.
const here = dirname(fileURLToPath(import.meta.url));
const goldenPath = resolve(here, "../../../datasets/fixtures/ezhuthu_golden.jsonl");

function loadGolden(): GoldenRow[] {
  const text = readFileSync(goldenPath, "utf-8");
  const rows: GoldenRow[] = [];
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (trimmed !== "") rows.push(JSON.parse(trimmed) as GoldenRow);
  }
  return rows;
}

const golden = loadGolden();

describe("ezhuthu golden corpus (shared with the Python twin)", () => {
  test("has at least 20 hand-verified rows", () => {
    expect(golden.length).toBeGreaterThanOrEqual(20);
  });

  test("segments every golden row exactly (parity Oracle)", () => {
    for (const row of golden) {
      expect(segment(row.word)).toEqual(row.ezhuthu);
    }
  });

  test("round-trips every golden row: join(segment(w)) === w", () => {
    for (const row of golden) {
      expect(segment(row.word).join("")).toBe(row.word);
    }
  });
});

describe("ezhuthu round-trip property (incl. decomposed NFD forms)", () => {
  const words = [
    "", // empty input
    "abc123", // pure ASCII
    "\u0b95\u0bc6\u0bbe", // NFD ko (ka + e-sign + aa-sign)
    "\u0b95\u0bc6\u0bd7", // NFD kau (ka + e-sign + au-length)
    "\u0b92\u0bd7", // NFD au vowel (o + au-length)
    "\u0bbe", // a leading combining mark on its own
    "\u0ba4\u0bae\u0bbf\u0bb4\u0bcd 2024", // tamizh + space + digits
  ];
  for (const w of words) {
    test(`join(segment(${JSON.stringify(w)})) === input`, () => {
      expect(segment(w).join("")).toBe(w);
    });
  }
});

describe("ezhuthu decomposed clusters", () => {
  test("NFD ko is a single uyirmei ezhuthu", () => {
    expect(segment("\u0b95\u0bc6\u0bbe")).toEqual(["\u0b95\u0bc6\u0bbe"]);
    expect(classify("\u0b95\u0bc6\u0bbe")).toBe("uyirmei");
  });

  test("NFD au vowel is a single uyir ezhuthu", () => {
    expect(segment("\u0b92\u0bd7")).toEqual(["\u0b92\u0bd7"]);
    expect(classify("\u0b92\u0bd7")).toBe("uyir");
  });
});

describe("ezhuthu classify", () => {
  const cases: Array<[string, EzhuthuKind]> = [
    ["\u0b85", "uyir"], // a
    ["\u0b94", "uyir"], // au
    ["\u0b83", "aytham"], // aytham
    ["\u0b95", "uyirmei"], // ka (bare consonant, inherent /a/)
    ["\u0b95\u0bcd", "mei"], // k (consonant + pulli)
    ["\u0b95\u0bbe", "uyirmei"], // kaa
    ["\u0b95\u0bcb", "uyirmei"], // koo (two-part matra)
    ["\u0bb7", "uyirmei"], // Grantha ssa
    ["1", "other"],
    [" ", "other"],
    ["", "other"],
  ];
  for (const [input, kind] of cases) {
    test(`classify(${JSON.stringify(input)}) === ${kind}`, () => {
      expect(classify(input)).toBe(kind);
    });
  }
});
