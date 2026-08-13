import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

// The design-token coverage Oracle (Row 10): every design token declared in
// app.css :root MUST be mirrored into tailwind.config.js as a `var(--token)`, so
// a Tailwind utility (bg-accent, rounded-md) and a raw var() resolve to the SAME
// value - one source of truth, not two (docs/concepts/design-system.md). A token
// that is intentionally NOT mirrored must be named in `exemptFromMirror` with a
// reason, so an orphan token can never slip in silently.

const here = dirname(fileURLToPath(import.meta.url));
const appCss = readFileSync(resolve(here, "../app.css"), "utf-8");
const tailwindConfig = readFileSync(resolve(here, "../../tailwind.config.js"), "utf-8");

// Tokens INTENTIONALLY not mirrored into Tailwind (bare values consumed only by
// JS or by raw CSS, never via a utility). Empty today: every token has a mirror.
// Add `["--name", "why"]` here when a token is deliberately JS-/CSS-only.
const exemptFromMirror = new Map<string, string>([]);

/** Custom-property DECLARATIONS (`--name:`), not uses (`var(--name)`). */
function declaredTokens(css: string): Set<string> {
  const found = new Set<string>();
  for (const match of css.matchAll(/(--[a-z0-9-]+)\s*:/g)) {
    const token = match[1];
    if (token !== undefined) found.add(token);
  }
  return found;
}

/** Tokens referenced as `var(--name)`. */
function mirroredTokens(source: string): Set<string> {
  const found = new Set<string>();
  for (const match of source.matchAll(/var\((--[a-z0-9-]+)\)/g)) {
    const token = match[1];
    if (token !== undefined) found.add(token);
  }
  return found;
}

const declared = declaredTokens(appCss);
const mirrored = mirroredTokens(tailwindConfig);

describe("design-token mirror coverage (Row 10 Oracle)", () => {
  test("app.css declares a non-trivial token set", () => {
    expect(declared.size).toBeGreaterThan(20);
  });

  test("every declared token is mirrored in tailwind.config.js or explicitly exempt", () => {
    const orphans = [...declared].filter(
      (token) => !mirrored.has(token) && !exemptFromMirror.has(token),
    );
    expect(
      orphans,
      `Unmirrored design tokens: ${orphans.join(", ")}. Add a var(${orphans[0] ?? "--x"}) ` +
        "mirror to tailwind.config.js theme.extend, or add the token to exemptFromMirror with a reason.",
    ).toEqual([]);
  });

  test("every var() referenced in tailwind.config.js is a real declared token", () => {
    const dangling = [...mirrored].filter((token) => !declared.has(token));
    expect(
      dangling,
      `tailwind.config.js references tokens not declared in app.css: ${dangling.join(", ")}`,
    ).toEqual([]);
  });

  test("every exemption names a token that actually exists (no stale exemptions)", () => {
    const stale = [...exemptFromMirror.keys()].filter((token) => !declared.has(token));
    expect(stale, `Stale exemptFromMirror entries (no such token): ${stale.join(", ")}`).toEqual(
      [],
    );
  });
});
