import { test, expect } from "vitest";
import { APP_TITLE, APP_TAGLINE } from "../../src/lib/meta";

test("shell exposes a non-empty app title", () => {
  expect(APP_TITLE).toBe("yen-tamizh");
});

test("shell exposes a tagline", () => {
  expect(APP_TAGLINE.length).toBeGreaterThan(0);
});
