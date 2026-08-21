import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { test, expect, type Page } from "@playwright/test";

import { segment } from "../src/tamil/ezhuthu";

// THE headline e2e for Row 22: A STREAM THAT DOES NOT REPEAT ITSELF. A player
// opens the app, taps the Infinite card, plays two consecutive boards, and the
// second is a different board of a different Game - then reloads and finds the
// stream still remembers both. Against the production bundle, with a clean
// console and no 404 (CLAUDE.md sections 12 + 13).
//
// The real committed pool is the fixture: the same bytes the bundle ships.
const here = dirname(fileURLToPath(import.meta.url));
const poolDir = resolve(here, "../public/pool");

interface PoolIndexFile {
  gameId: string;
  totalCount: number;
  items: { id: string; difficulty: string }[];
}

interface PoolItemFile {
  id: string;
  gameId: string;
  difficulty: string;
  payload: { word?: string };
}

function readIndex(gameId: string): PoolIndexFile {
  return JSON.parse(
    readFileSync(resolve(poolDir, gameId, "index.json"), "utf-8"),
  ) as PoolIndexFile;
}

function readItem(gameId: string, id: string): PoolItemFile {
  return JSON.parse(
    readFileSync(resolve(poolDir, gameId, `${id}.json`), "utf-8"),
  ) as PoolItemFile;
}

// The stream opens on the first Game of the Daily's ring at the config'd default
// band, and that Game is the anagram - the one board this spec can drive to a
// real win through its own controls (the same reason journey.spec.ts opens on
// it). Its first medium board is therefore deterministic, and this is what the
// spec plays.
const anagramIndex = readIndex("anagram");
const firstMedium = anagramIndex.items.find((entry) => entry.difficulty === "medium");
if (firstMedium === undefined) throw new Error("the committed anagram pool has no medium band");
const firstBoard = readItem("anagram", firstMedium.id);
const firstWord = firstBoard.payload.word;
if (firstWord === undefined) throw new Error("the first pooled anagram has no word");

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

/** The seen list the save is keeping right now. */
async function seenIds(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const raw = window.localStorage.getItem("yt:save");
    if (raw === null) return [];
    const save = JSON.parse(raw) as { seenInfiniteIds?: string[] };
    return save.seenInfiniteIds ?? [];
  });
}

test("an endless stream: Home -> Infinite -> two boards, no repeat, and a save that remembers", async ({
  page,
}) => {
  const watched = watchConsole(page);

  // 1. LANDING, and the Infinite card is a real button now rather than a promise.
  await page.goto("/", { waitUntil: "load" });
  await expect(page.getByTestId("app-shell")).toBeVisible();
  const card = page.locator('[data-testid="mode-card"][data-mode="infinite"]');
  await expect(card).toHaveCount(1);

  // 2. ONE TAP INTO THE STREAM, which opens on the config'd default band.
  await card.click();
  await expect(page.getByTestId("session-stage")).toBeVisible({ timeout: 15_000 });
  expect(new URL(page.url()).searchParams.get("mode")).toBe("infinite");
  const first = page.getByTestId("infinite-game-name");
  await expect(first).toHaveAttribute("data-item", `anagram/${firstMedium.id}`);
  await expect(
    page.locator('[data-testid="infinite-band"][aria-pressed="true"]'),
  ).toHaveCount(1);

  // 3. THE BOARD WAS RECORDED THE MOMENT IT WAS DEALT, not when it was solved -
  //    an abandoned puzzle has still been seen.
  expect(await seenIds(page)).toEqual([`anagram/${firstMedium.id}`]);

  // 4. PLAY IT TO A WIN, through the board's own controls.
  await expect(page.getByTestId("anagram-game")).toBeVisible();
  for (const ezhuthu of segment(firstWord)) await placeEzhuthu(page, ezhuthu);
  await expect(page.getByTestId("anagram-feedback")).toBeVisible();

  // 5. THE NEXT BOARD ARRIVES BY ITSELF - a different item, and the next Game in
  //    the ring, because the stream rotates rather than emptying one pool.
  await expect
    .poll(async () => page.getByTestId("infinite-game-name").getAttribute("data-item"), {
      timeout: 20_000,
    })
    .not.toBe(`anagram/${firstMedium.id}`);
  const secondItem = await page.getByTestId("infinite-game-name").getAttribute("data-item");
  expect(secondItem).not.toBeNull();
  expect(secondItem?.startsWith("anagram/")).toBe(false);

  // 6. NO REPEAT: two consecutive boards, two distinct entries in the window.
  const seenAfterTwo = await seenIds(page);
  expect(seenAfterTwo).toHaveLength(2);
  expect(new Set(seenAfterTwo).size).toBe(2);
  expect(seenAfterTwo[0]).toBe(`anagram/${firstMedium.id}`);
  expect(seenAfterTwo[1]).toBe(secondItem);

  // 7. A RELOAD PRESERVES THE SEEN SET, and the stream moves on rather than
  //    dealing either of them again.
  await page.reload({ waitUntil: "load" });
  await expect(page.getByTestId("session-stage")).toBeVisible({ timeout: 15_000 });
  const seenAfterReload = await seenIds(page);
  expect(seenAfterReload.slice(0, 2)).toEqual(seenAfterTwo);
  const third = await page.getByTestId("infinite-game-name").getAttribute("data-item");
  expect(seenAfterTwo).not.toContain(third);

  // 8. THE DIFFICULTY FILTER IS THE ONE CONTROL AN ENDLESS STREAM NEEDS.
  await page.locator('[data-testid="infinite-band"][data-band="hard"]').click();
  await expect(
    page.locator('[data-testid="infinite-band"][data-band="hard"]'),
  ).toHaveAttribute("aria-pressed", "true");
  await expect
    .poll(async () => page.getByTestId("infinite-game-name").getAttribute("data-item"), {
      timeout: 20_000,
    })
    .not.toBe(third);

  // 9. A CLEAN RUN: no console errors, no 404s, and the Home is still one tap.
  //    The shell's back control is the first button in its header.
  await page.locator("header button").first().click();
  await expect(page.getByTestId("app-shell")).toBeVisible();
  expect(watched.errors, `console errors: ${watched.errors.join(" | ")}`).toEqual([]);
  expect(watched.failures, `failed requests: ${watched.failures.join(" | ")}`).toEqual([]);
});
