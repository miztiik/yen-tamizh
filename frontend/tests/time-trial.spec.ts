import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { test, expect, type Page } from "@playwright/test";

// THE headline e2e for Row 23: A SPRINT THAT ENDS BY ITSELF. A player opens the
// app, taps the Time Trial card, starts a run, watches the clock count down,
// and the run ends without anyone touching it - then the record it set is still
// there after a reload. Against the production bundle, with a clean console and
// no 404 (CLAUDE.md sections 12 + 13).
//
// The clock is driven by Playwright's own `page.clock`, which fakes the page's
// monotonic clock and its animation frames. That is the only way to test a
// two-minute run without waiting two minutes, and it is the SAME technique the
// unit Oracle uses: assert what the run does at a named instant rather than
// asking a real machine to be punctual.
const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(here, "../..");
const appConfig = JSON.parse(
  readFileSync(resolve(repoRoot, "config/app-config.json"), "utf-8"),
) as { timeTrial: { durationSec: number } };

const DURATION_SEC = appConfig.timeTrial.durationSec;

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

/** The best runs the save is keeping right now. */
async function bestRuns(page: Page): Promise<{ durationSec: number; itemsCompleted: number }[]> {
  return page.evaluate(() => {
    const raw = window.localStorage.getItem("yt:save");
    if (raw === null) return [];
    const save = JSON.parse(raw) as {
      bestTimeTrialRuns?: { durationSec: number; itemsCompleted: number }[];
    };
    return save.bestTimeTrialRuns ?? [];
  });
}

test("a timed sprint: Home -> Time Trial -> the clock runs out by itself -> a record that survives a reload", async ({
  page,
}) => {
  const watched = watchConsole(page);
  // Install BEFORE navigating so the page never sees the real clock.
  await page.clock.install();

  // 1. LANDING, and the last coming-soon tile is a real button now.
  await page.goto("/", { waitUntil: "load" });
  await expect(page.getByTestId("app-shell")).toBeVisible();
  await expect(page.getByTestId("mode-card-locked")).toHaveCount(0);
  const card = page.locator('[data-testid="mode-card"][data-mode="time-trial"]');
  await expect(card).toHaveCount(1);

  // 2. ONE TAP TO THE START CARD. The clock has NOT started - a countdown that
  //    began while the first board was still arriving would charge the player
  //    for the network.
  await card.click();
  await expect(page.getByTestId("time-trial-ready")).toBeVisible({ timeout: 15_000 });
  expect(new URL(page.url()).searchParams.get("mode")).toBe("time-trial");
  await expect(page.getByTestId("countdown")).toHaveCount(0);

  // 3. START THE RUN. A board arrives and the clock appears in the header,
  //    reading the whole configured duration.
  await page.getByTestId("time-trial-start").click();
  await expect(page.getByTestId("session-stage")).toBeVisible({ timeout: 15_000 });
  const clock = page.getByTestId("countdown-clock");
  await expect(clock).toBeVisible();
  const minutes = Math.floor(DURATION_SEC / 60);
  const seconds = DURATION_SEC % 60;
  await expect(clock).toHaveText(`${minutes}:${String(seconds).padStart(2, "0")}`);
  // The readout is named, so it is not a bare number to a screen reader.
  await expect(page.getByTestId("countdown")).toHaveAttribute("aria-label", /.+/);
  await expect(page.getByTestId("countdown")).toHaveAttribute("data-low", "false");

  // 4. IT COUNTS DOWN. Ten seconds of frames, and the readout has moved.
  await page.clock.runFor(10_000);
  await expect(clock).not.toHaveText(`${minutes}:${String(seconds).padStart(2, "0")}`);

  // 5. THE LAST SECONDS ARE MARKED - and the mark is not the only channel: the
  //    digits carry the value, colour only emphasises it.
  await page.clock.fastForward((DURATION_SEC - 14) * 1000);
  await expect(page.getByTestId("countdown")).toHaveAttribute("data-low", "true");
  await expect(clock).toHaveText("0:04");

  // 6. THE RUN ENDS BY ITSELF - nobody clicks anything.
  //
  //    The run is JUMPED rather than stepped, which is not a shortcut:
  //    fastForward delivers a single frame after a long gap, which is exactly
  //    what a browser does to a tab that was not in front. A countdown that
  //    decremented per frame would come back owing the player every second it
  //    was not painted; this one derives its remaining time from the clock and
  //    ends on the first frame after the deadline.
  await page.clock.fastForward(5000);
  await expect(page.getByTestId("time-trial-over")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("time-trial-score")).toBeVisible();
  const scored = Number(await page.getByTestId("time-trial-score").innerText());
  expect(Number.isNaN(scored)).toBe(false);

  // 7. A RECORD WAS WRITTEN, AGAINST THE RUN LENGTH IT WAS SET AT.
  const runs = await bestRuns(page);
  expect(runs).toHaveLength(1);
  expect(runs[0]?.durationSec).toBe(DURATION_SEC);
  expect(runs[0]?.itemsCompleted).toBe(scored);
  await expect(page.getByTestId("time-trial-best")).toHaveText(new RegExp(String(scored)));

  // 8. IT SURVIVES A RELOAD - the record is on the start card of the next run.
  await page.reload({ waitUntil: "load" });
  await expect(page.getByTestId("time-trial-ready")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId("time-trial-best")).toHaveText(new RegExp(String(scored)));
  expect(await bestRuns(page)).toEqual(runs);

  // 9. A CLEAN RUN: no console errors, no 404s, and the Home is still one tap.
  await page.getByTestId("time-trial-home").click();
  await expect(page.getByTestId("app-shell")).toBeVisible();
  expect(watched.errors, `console errors: ${watched.errors.join(" | ")}`).toEqual([]);
  expect(watched.failures, `failed requests: ${watched.failures.join(" | ")}`).toEqual([]);
});
