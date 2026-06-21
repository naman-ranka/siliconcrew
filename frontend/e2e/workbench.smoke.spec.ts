import { test, expect } from "@playwright/test";

/**
 * Tier-2 visual/E2E smoke. Requires a browser:
 *   npx playwright install chrome   (apt Chrome — bundled chromium CDN is blocked)
 * Note: the file: protocol is blocked in this environment; always test against
 * an HTTP server (the Next dev server here, via webServer in the config).
 */

// Proves the browser + harness work today (the app's existing entry renders).
test("app loads (smoke)", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("body")).toBeVisible();
  await page.screenshot({ path: "e2e-artifacts/home.png", fullPage: true });
});

// Phase 1 target flow — un-skip and flesh out as the workbench is built.
test.skip("workbench: upload → lint → sim (fail) → waveform → fix → synth → report", async ({ page }) => {
  await page.goto("/workbench");
  await expect(page.getByText(/Simulate/i)).toBeVisible();
  // upload RTL → manifest tags roles
  // click Run Lint  → console shows command + result
  // click Run Sim   → run timeline gets sim_NNNN, status fail
  // open waveform deep-link → WaveformViewer shows the failure cursor
  // apply agent fix → re-run sim → pass
  // click Run Synth → poll → Report shows timing slack (met)
  await page.screenshot({ path: "e2e-artifacts/workbench.png", fullPage: true });
});
