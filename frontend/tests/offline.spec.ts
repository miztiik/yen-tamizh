import { test, expect } from "@playwright/test";

// Row 4 Oracle - the offline app-shell boot. After one online load the service
// worker precaches the shell; with the network cut, a reload still boots the
// shell from cache with no uncaught errors. Runs against the production preview
// (see playwright.config.ts webServer) because the install/update contract is
// only real in a built bundle, not the dev server (CLAUDE.md section 12).
//
// The roadmap Oracle also says "replays the last opened puzzle from cache". That
// leg needs the baked bank and a Game to open, which land in Row 13; this proves
// the service-worker + offline half that Row 4 owns.
test("offline reload boots the app shell from the service-worker cache", async ({
  page,
  context,
}) => {
  const pageErrors: string[] = [];
  const failedResponses: string[] = [];
  page.on("pageerror", (err) => pageErrors.push(err.message));
  page.on("response", (res) => {
    if (res.status() >= 400) failedResponses.push(`${res.status()} ${res.url()}`);
  });

  // 1. Online load registers the service worker and precaches the shell.
  await page.goto("/");
  await expect(page.getByTestId("app-shell")).toBeVisible();

  // 2. Wait for the service worker to reach "activated".
  await page.waitForFunction(
    async () => {
      if (!("serviceWorker" in navigator)) return false;
      const reg = await navigator.serviceWorker.ready;
      return reg.active?.state === "activated";
    },
    null,
    { timeout: 30_000 },
  );

  // 3. Reload while online so this client is controlled by the worker; its next
  //    document request is then served from the precache, not the network.
  await page.reload();
  await expect(page.getByTestId("app-shell")).toBeVisible();
  const controlled = await page.evaluate(() => !!navigator.serviceWorker.controller);
  expect(controlled, "service worker controls the page after reload").toBe(true);

  // 4. Cut the network and reload: the shell must still boot from cache.
  await context.setOffline(true);
  await page.reload();

  await expect(page.getByTestId("app-shell")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("yen-tamizh");

  expect(pageErrors, `page errors while offline: ${pageErrors.join(" | ")}`).toEqual([]);
  expect(failedResponses, `failed responses while offline: ${failedResponses.join(" | ")}`).toEqual(
    [],
  );

  await context.setOffline(false);
});
