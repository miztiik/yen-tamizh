import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, test, vi } from "vitest";

import { loadValidated, type SchemaName } from "./index";

// The SAME shared fixtures the backend's test_core_schemas.py loads, resolved
// relative to this file. Both sides asserting against these exact bytes is the
// contract Oracle: a valid payload is accepted by BOTH the Pydantic model and
// the ajv validator; the malformed payload is REJECTED by both.
const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../../..");
const fixturesDir = resolve(repoRoot, "datasets/fixtures/contracts");
const configDir = resolve(repoRoot, "config");

function fileText(path: string): string {
  return readFileSync(path, "utf-8");
}

function stubFetchResponding(body: string, status = 200): void {
  // Mock carve-out (a): fetch is stubbed in a loader unit test (Holy Law #7).
  vi.stubGlobal(
    "fetch",
    vi.fn(
      async () =>
        new Response(body, {
          status,
          headers: { "content-type": "application/json" },
        }),
    ),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

// The six core contracts plus copy, and one payload schema per Game. Each ships
// a valid and a malformed fixture under datasets/fixtures/contracts/; the
// malformed one omits or mistypes a required field the backend rejects too.
const CORE_SCHEMAS: SchemaName[] = [
  "app-config",
  "event-envelope",
  "save",
  "puzzle-file",
  "bank-index",
  "anagram-puzzle",
  "missing-letters-puzzle",
  "copy",
];

describe("core contract schemas (frontend ajv boundary)", () => {
  for (const name of CORE_SCHEMAS) {
    test(`${name}: accepts the shared valid fixture (Oracle acceptance half)`, async () => {
      stubFetchResponding(fileText(resolve(fixturesDir, `${name}_valid.json`)));
      const data = await loadValidated(`/${name}.json`, name);
      expect(data).toBeTypeOf("object");
    });

    test(`${name}: rejects the shared malformed fixture (Oracle rejection half)`, async () => {
      stubFetchResponding(fileText(resolve(fixturesDir, `${name}_invalid.json`)));
      await expect(loadValidated(`/${name}.json`, name)).rejects.toThrow(/failed/i);
    });
  }

  test("config/app-config.json validates against app-config (fresh clone runs on defaults)", async () => {
    stubFetchResponding(fileText(resolve(configDir, "app-config.json")));
    const cfg = await loadValidated("/config/app-config.json", "app-config");
    expect(cfg.ui.enabledModes.length).toBeGreaterThan(0);
  });

  test("config/copy.json validates against copy", async () => {
    stubFetchResponding(fileText(resolve(configDir, "copy.json")));
    const copy = await loadValidated("/config/copy.json", "copy");
    expect(copy.strings).toBeTypeOf("object");
  });
});
