import { describe, expect, test, vi } from "vitest";

import { NOOP_GLYPH_LOGGER, glyphIds, hasGlyph, resolveGlyph } from "./glyphs";

// The Glyph oracle (Row 10): the resolver behind Glyph.svelte resolves a KNOWN
// id to its baked geometry and REFUSES an unknown id (returns null + reports via
// the injected logger, never throwing, never touching console).

describe("resolveGlyph", () => {
  test("resolves a known id to its baked viewBox + path", () => {
    const shape = resolveGlyph("check");
    expect(shape).not.toBeNull();
    expect(shape?.viewBox).toMatch(/^\d+ \d+ \d+ \d+$/);
    expect(shape?.path.length).toBeGreaterThan(0);
  });

  test("refuses an unknown id: returns null and warns through the injected logger", () => {
    const logger = { warn: vi.fn() };
    const shape = resolveGlyph("does-not-exist", logger);
    expect(shape).toBeNull();
    expect(logger.warn).toHaveBeenCalledOnce();
    expect(logger.warn.mock.calls[0]?.[0]).toContain("does-not-exist");
  });

  test("the default logger makes an unknown id a silent no-op (no throw)", () => {
    expect(() => resolveGlyph("nope")).not.toThrow();
    expect(resolveGlyph("nope")).toBeNull();
    // The exported no-op logger swallows the warning.
    expect(() => NOOP_GLYPH_LOGGER.warn("x")).not.toThrow();
  });
});

describe("glyph manifest coverage", () => {
  test("the essential UI glyph pack is present", () => {
    for (const id of ["back", "check", "close", "hint", "settings", "share", "star"]) {
      expect(hasGlyph(id), `missing glyph "${id}"`).toBe(true);
    }
  });

  test("hasGlyph is false for an unknown id", () => {
    expect(hasGlyph("totally-unknown")).toBe(false);
  });

  test("glyphIds is sorted and non-empty", () => {
    const ids = glyphIds();
    expect(ids.length).toBeGreaterThan(0);
    expect(ids).toEqual([...ids].sort());
  });
});
