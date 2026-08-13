import { test, expect } from "@playwright/test";

// Row 11 browser smoke: the SessionShell renders, the SessionRunner plays a
// two-item fake session end to end, the chrome is keyboard-reachable with a
// visible focus ring (v2 a11y), and the console stays clean (CLAUDE.md section
// 12). Driven through the `?harness=session` scaffold (Row 13 replaces it).
test("session harness: shell renders, a fake session plays, clean console", async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  const failedResponses: string[] = [];

  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => pageErrors.push(err.message));
  page.on("response", (res) => {
    if (res.status() >= 400) failedResponses.push(`${res.status()} ${res.url()}`);
  });

  await page.goto("/?harness=session", { waitUntil: "load" });

  // Shell chrome: semantic landmarks + title.
  await expect(page.getByRole("banner")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Session harness");
  await expect(page.getByTestId("session-stage")).toBeVisible();

  // The fake Game rendered into the stage (item 1 of 2).
  await expect(page.getByTestId("fake-game")).toBeVisible();

  // Keyboard reachability + visible focus: Tab lands on the header control, and
  // :focus-visible paints an outline.
  await page.keyboard.press("Tab");
  const focus = await page.evaluate(() => {
    const el = document.activeElement as HTMLElement | null;
    if (el === null) return null;
    const style = getComputedStyle(el);
    return {
      tag: el.tagName,
      label: el.getAttribute("aria-label"),
      outlineStyle: style.outlineStyle,
    };
  });
  expect(focus?.tag).toBe("BUTTON");
  expect(focus?.label).toBe("Back to home");
  expect(focus?.outlineStyle).not.toBe("none");

  // Play both items -> the summary.
  await page.getByTestId("fake-submit").click();
  await expect(page.getByTestId("fake-game")).toBeVisible(); // item 2 mounted
  await page.getByTestId("fake-submit").click();
  await expect(page.getByTestId("session-summary")).toBeVisible();

  expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
  expect(pageErrors, `page errors: ${pageErrors.join(" | ")}`).toEqual([]);
  expect(failedResponses, `failed responses: ${failedResponses.join(" | ")}`).toEqual([]);
});
