import { defineConfig, devices } from "@playwright/test";

// Tier-2 verification: real browser, visual + E2E.
// First-time setup in this environment:
//   npx playwright install chrome      <-- apt Chrome (the bundled-chromium CDN
//                                          download is egress-blocked here)
// Run: npm run e2e
export default defineConfig({
  testDir: "./e2e",
  outputDir: "./e2e-artifacts",
  timeout: 60_000,
  use: {
    baseURL: "http://localhost:3000",
    channel: "chrome", // use the apt Chrome install, not bundled chromium
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
    { name: "chrome", use: { ...devices["Desktop Chrome"], channel: "chrome" } },
  ],
});
