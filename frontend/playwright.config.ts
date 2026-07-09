import { defineConfig, devices } from "@playwright/test";

// Tier-2 verification: real browser, visual + E2E.
// Uses the Playwright-managed chromium by default (preinstalled in CI/cloud
// environments via PLAYWRIGHT_BROWSERS_PATH). Where that download is blocked
// and an apt Chrome exists instead, opt in with:
//   npx playwright install chrome && PW_CHANNEL=chrome npm run e2e
const channel = process.env.PW_CHANNEL; // e.g. "chrome"; undefined → bundled chromium
// Environments that preinstall a chromium at a fixed path (and block the
// version-pinned download) can point straight at the binary:
//   PW_EXECUTABLE=/opt/pw-browsers/chromium npm run e2e
const executablePath = process.env.PW_EXECUTABLE;
const launchOverride = executablePath ? { launchOptions: { executablePath } } : {};

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./e2e-artifacts",
  timeout: 60_000,
  use: {
    baseURL: "http://localhost:3000",
    ...(channel ? { channel } : {}),
    screenshot: "only-on-failure",
    trace: "on-first-retry",
  },
  webServer: {
    command: "npm run dev",
    url: "http://localhost:3000",
    reuseExistingServer: true,
    timeout: 120_000,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"], ...(channel ? { channel } : {}), ...launchOverride } },
  ],
});
