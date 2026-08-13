import { expect, test } from "vitest";
import { withBase } from "./base";

test("prefixes a relative path with the root base", () => {
  expect(withBase("bank/2026-08-13.json", "/")).toBe("/bank/2026-08-13.json");
});

test("prefixes a relative path with the project base", () => {
  expect(withBase("bank/2026-08-13.json", "/yen-tamizh/")).toBe("/yen-tamizh/bank/2026-08-13.json");
});

test("normalizes a leading slash on the path so the base is not doubled", () => {
  expect(withBase("/sw.js", "/yen-tamizh/")).toBe("/yen-tamizh/sw.js");
});

test("tolerates a base without a trailing slash", () => {
  expect(withBase("assets/x.png", "/yen-tamizh")).toBe("/yen-tamizh/assets/x.png");
});

test("returns the base itself for an empty path", () => {
  expect(withBase("", "/yen-tamizh/")).toBe("/yen-tamizh/");
  expect(withBase("", "/")).toBe("/");
});

test("uses the ambient BASE_URL by default", () => {
  const base = import.meta.env.BASE_URL;
  expect(withBase("assets/x.png")).toBe(withBase("assets/x.png", base));
});
