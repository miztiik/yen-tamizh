import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

// Carmack's animation invariant + Jony's reduced-motion kill-switch, as an
// automated gate over animations.css (docs/concepts/design-system.md):
//   1. every @keyframes animates ONLY `transform`/`opacity` (never a layout- or
//      paint-heavy property) so motion holds 60fps on the target phone;
//   2. `prefers-reduced-motion: reduce` collapses every duration to ~0.

const here = dirname(fileURLToPath(import.meta.url));
const animationsCss = readFileSync(resolve(here, "./animations.css"), "utf-8");

const ALLOWED_ANIMATED_PROPS = new Set(["transform", "opacity"]);

/** Map each `@keyframes name` to the CSS properties it animates. */
function keyframeProps(css: string): Map<string, string[]> {
  const byName = new Map<string, string[]>();
  // Non-greedy up to the keyframes-level closing brace (`\n}` at column 0); the
  // indented step-block closers (`\n  }`) do not match, so the body is whole.
  for (const block of css.matchAll(/@keyframes\s+([\w-]+)\s*\{([\s\S]*?)\n\}/g)) {
    const name = block[1];
    const body = block[2];
    if (name === undefined || body === undefined) continue;
    const props = [...body.matchAll(/([a-z-]+)\s*:/g)]
      .map((m) => m[1])
      .filter((prop): prop is string => prop !== undefined);
    byName.set(name, props);
  }
  return byName;
}

const keyframes = keyframeProps(animationsCss);

describe("animation frame-budget invariant (Row 10)", () => {
  test("animations.css defines a keyframe set", () => {
    expect(keyframes.size).toBeGreaterThan(5);
  });

  test("every keyframe animates only transform/opacity", () => {
    const violations: string[] = [];
    for (const [name, props] of keyframes) {
      for (const prop of props) {
        if (!ALLOWED_ANIMATED_PROPS.has(prop)) {
          violations.push(`@keyframes ${name} animates "${prop}"`);
        }
      }
    }
    expect(
      violations,
      `Layout/paint-heavy keyframe properties (use transform/opacity only): ${violations.join("; ")}`,
    ).toEqual([]);
  });
});

describe("reduced-motion kill-switch (Row 10)", () => {
  test("a prefers-reduced-motion block exists", () => {
    expect(animationsCss).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  });

  test("the reduced-motion block collapses animation + transition durations to ~0", () => {
    const block = animationsCss.match(
      /@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{[\s\S]*?\n\}/,
    )?.[0];
    expect(block, "no prefers-reduced-motion block found").toBeTruthy();
    expect(block).toMatch(/animation-duration:\s*0\.01ms\s*!important/);
    expect(block).toMatch(/transition-duration:\s*0\.01ms\s*!important/);
    expect(block).toMatch(/animation-iteration-count:\s*1\s*!important/);
  });
});
