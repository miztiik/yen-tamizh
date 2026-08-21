import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { test, expect, type Page } from "@playwright/test";

import { segment } from "../src/tamil/ezhuthu";

// THE headline e2e for Row 17: A PATH THAT REMEMBERS. A player opens the app,
// taps the Journey card, sees the winding map with one node open and the rest
// shut, plays that node to a win, watches the NEXT node open - and reloads to
// find it still open. Against the production bundle, with a clean console
// (CLAUDE.md sections 12 + 13).
//
// The real committed path is the fixture: the same bytes the bundle ships.
const here = dirname(fileURLToPath(import.meta.url));
const journeyPath = resolve(here, "../../datasets/journeys/beginners-ladder.json");

interface JourneyNode {
  id: string;
  gameId: string;
  payload: { word: string; tiles: string[] };
}

const journey = JSON.parse(readFileSync(journeyPath, "utf-8")) as {
  id: string;
  titleTa: string;
  nodes: JourneyNode[];
};

const firstNode = journey.nodes[0];
if (firstNode === undefined) throw new Error("the committed path has no nodes");
// The path opens on the anagram board by design (Palm: the fastest win in the
// game is the right first step), which is also what lets this test drive a real
// node to a real win through the board's own controls.
if (firstNode.gameId !== "anagram") {
  throw new Error(`the first node is a ${firstNode.gameId}; this spec drives an anagram`);
}

function watchConsole(page: Page): { errors: string[]; failures: string[] } {
  const errors: string[] = [];
  const failures: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });
  page.on("pageerror", (err) => errors.push(`pageerror: ${err.message}`));
  page.on("response", (res) => {
    if (res.status() >= 400) failures.push(`${res.status()} ${res.url()}`);
  });
  return { errors, failures };
}

/** Click the tray tile carrying exactly this ezhuthu (never a prefix of one). */
async function placeEzhuthu(page: Page, ezhuthu: string): Promise<void> {
  const clicked = await page.evaluate((target) => {
    const tiles = Array.from(
      document.querySelectorAll<HTMLButtonElement>('[data-testid="anagram-tile"]'),
    );
    const tile = tiles.find((button) => button.textContent?.trim() === target);
    tile?.click();
    return tile !== undefined;
  }, ezhuthu);
  expect(clicked, `no tray tile carries "${ezhuthu}"`).toBe(true);
}

/** The state attribute of every node on the map, in walking order. */
async function mapStates(page: Page): Promise<(string | null)[]> {
  return page
    .getByTestId("journey-node")
    .evaluateAll((els) => els.map((el) => el.getAttribute("data-state")));
}

test("a path that remembers: Home -> Journey -> a cleared node -> the next one opens", async ({
  page,
}) => {
  const watched = watchConsole(page);

  // 1. LANDING, and the Journey is a real button now rather than a promise.
  await page.goto("/", { waitUntil: "load" });
  await expect(page.getByTestId("app-shell")).toBeVisible();
  const card = page.locator('[data-testid="mode-card"][data-mode="journey"]');
  await expect(card).toHaveCount(1);

  // 2. ONE TAP TO THE MAP.
  await card.click();
  await expect(page.getByTestId("journey-shell")).toBeVisible();
  await expect(page.getByTestId("journey-map")).toBeVisible();
  expect(new URL(page.url()).searchParams.get("mode")).toBe("journey");
  await expect(page.getByRole("heading", { level: 1 })).toHaveText(journey.titleTa);

  // 3. THE PATH IS SHUT EXCEPT FOR ITS ENTRANCE.
  await expect(page.getByTestId("journey-node")).toHaveCount(journey.nodes.length);
  expect(await mapStates(page)).toEqual([
    "available",
    ...journey.nodes.slice(1).map(() => "locked"),
  ]);
  await expect(page.getByTestId("journey-progress")).toContainText(
    `0/${journey.nodes.length}`,
  );

  // 4. KEYBOARD REACHABILITY, with a visible focus ring and a real name.
  const reached = await page.evaluate(() => {
    // A locked node is not a button at all, so the only tab stop on the map
    // that is a node is the one the player may actually open.
    const stops = Array.from(
      document.querySelectorAll<HTMLElement>('button[data-testid="journey-node"]'),
    );
    return stops.length;
  });
  expect(reached).toBe(1);
  let focus: { testid: string | null; label: string | null; outline: string } | null = null;
  for (let press = 0; press < 12 && focus?.testid !== "journey-node"; press += 1) {
    await page.keyboard.press("Tab");
    focus = await page.evaluate(() => {
      const el = document.activeElement as HTMLElement | null;
      return el === null
        ? null
        : {
            testid: el.getAttribute("data-testid"),
            label: el.getAttribute("aria-label"),
            outline: getComputedStyle(el).outlineStyle,
          };
    });
  }
  expect(focus?.testid).toBe("journey-node");
  expect(focus?.label).toBeTruthy();
  expect(focus?.outline).not.toBe("none");

  // 5. PLAY THE OPEN NODE TO A WIN, through the board's own controls.
  await page.locator(`[data-testid="journey-node"][data-node-id="${firstNode.id}"]`).click();
  await expect(page.getByTestId("session-stage")).toBeVisible();
  await expect(page.getByTestId("anagram-game")).toBeVisible();
  for (const ezhuthu of segment(firstNode.payload.word)) await placeEzhuthu(page, ezhuthu);
  await expect(page.getByTestId("anagram-feedback")).toBeVisible();

  // 6. THE NEXT NODE OPENS - and only the next one.
  await expect(page.getByTestId("journey-map")).toBeVisible({ timeout: 15_000 });
  await expect
    .poll(async () => (await mapStates(page))[0], { timeout: 15_000 })
    .toBe("completed");
  expect(await mapStates(page)).toEqual([
    "completed",
    "available",
    ...journey.nodes.slice(2).map(() => "locked"),
  ]);
  await expect(page.getByTestId("journey-progress")).toContainText(
    `1/${journey.nodes.length}`,
  );

  // 7. A RELOAD PRESERVES IT. The path is not a calendar and not a session.
  await page.reload({ waitUntil: "load" });
  await expect(page.getByTestId("journey-map")).toBeVisible();
  await expect
    .poll(async () => (await mapStates(page))[0], { timeout: 15_000 })
    .toBe("completed");
  expect(await mapStates(page)).toEqual([
    "completed",
    "available",
    ...journey.nodes.slice(2).map(() => "locked"),
  ]);

  // 8. A CLEAN RUN: no console errors, no 404s, and the Home is still one tap.
  await page.getByTestId("journey-home").click();
  await expect(page.getByTestId("app-shell")).toBeVisible();
  expect(watched.errors, `console errors: ${watched.errors.join(" | ")}`).toEqual([]);
  expect(watched.failures, `failed requests: ${watched.failures.join(" | ")}`).toEqual([]);
});
