import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, test, vi } from "vitest";

import { loadValidated } from "./index";

// The SAME shared fixtures the backend's test_contracts.py loads, resolved
// relative to this file. Both sides asserting against these exact bytes is the
// Oracle: a valid payload is accepted by BOTH the Pydantic model and the ajv
// validator; the malformed payload is REJECTED by both.
const here = dirname(fileURLToPath(import.meta.url));
const fixturesDir = resolve(here, "../../../datasets/fixtures/contracts");

function fixtureText(name: string): string {
  return readFileSync(resolve(fixturesDir, name), "utf-8");
}

function stubFetchResponding(body: string, status = 200): void {
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

describe("loadValidated (frontend contract boundary)", () => {
  test("accepts the shared valid fixture and returns typed data", async () => {
    stubFetchResponding(fixtureText("example_valid.json"));
    const data = await loadValidated("/example.json", "example");
    expect(data.label).toBe("demo");
    expect(data.count).toBe(3);
  });

  test("rejects the shared malformed fixture (Oracle rejection half)", async () => {
    // example_invalid.json is missing the required "label" and has count < 0.
    stubFetchResponding(fixtureText("example_invalid.json"));
    await expect(loadValidated("/example.json", "example")).rejects.toThrow(/invalid|failed/i);
  });

  test("throws a clear error on a non-ok response", async () => {
    stubFetchResponding("", 404);
    await expect(loadValidated("/missing.json", "example")).rejects.toThrow(/404/);
  });
});
