import { defineConfig } from "@playwright/test";

/**
 * Staging e2e — runs against the DEPLOYED app (no webServer, no mocks).
 * Driven by .github/workflows/staging-e2e.yml; needs STAGING_BASE_URL and
 * real AuthKit credentials (STAGING_EMAIL / STAGING_PASSWORD) in the env.
 */
export default defineConfig({
  testDir: ".",
  outputDir: "../test-results/staging",
  timeout: 300_000,
  expect: { timeout: 30_000 },
  workers: 1,
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.STAGING_BASE_URL || "https://siliconcrew-frontend-psp2dkllmq-uc.a.run.app",
    screenshot: "on",
    trace: "retain-on-failure",
    video: "retain-on-failure",
  },
});
