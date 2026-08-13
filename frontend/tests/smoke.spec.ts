import { test, expect } from "@playwright/test";

// e2e smoke: the empty shell boots, shows its title, and does so with a clean
// console (zero errors, zero uncaught exceptions, zero failed responses). This
// is the Row 3 acceptance surface AND the CLAUDE.md section 12 browser smoke;
// feature-level e2e (a level start-to-win, save-and-reload) lands in later rows.
test("app shell renders a visible title with a clean console", async ({ page }) => {
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

  await page.goto("/");

  const shell = page.getByTestId("app-shell");
  await expect(shell).toBeVisible();

  const heading = page.getByRole("heading", { level: 1 });
  await expect(heading).toHaveText("yen-tamizh");

  expect(consoleErrors, `console errors: ${consoleErrors.join(" | ")}`).toEqual([]);
  expect(pageErrors, `page errors: ${pageErrors.join(" | ")}`).toEqual([]);
  expect(failedResponses, `failed responses: ${failedResponses.join(" | ")}`).toEqual([]);
});
