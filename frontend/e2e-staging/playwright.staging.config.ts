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
    // Sandboxed agent environments reach the internet only through an egress
    // proxy. Opt in with HTTPS_PROXY; plain CI leaves it unset and is
    // untouched.
    ...(process.env.HTTPS_PROXY ? { proxy: { server: process.env.HTTPS_PROXY } } : {}),
  },
  projects: [
    {
      name: "chromium",
      use: {
        // Same conditional idiom as playwright.config.ts: unset env leaves
        // CI on Playwright's defaults. Behind such a proxy, set
        // PW_CHANNEL=chromium (chrome-headless-shell can't complete the TLS
        // session) and PW_ARGS=--ssl-version-max=tls1.2 (the MITM resets
        // Chromium's TLS 1.3 handshake).
        ...(process.env.PW_CHANNEL ? { channel: process.env.PW_CHANNEL } : {}),
        launchOptions: {
          ...(process.env.PW_EXECUTABLE ? { executablePath: process.env.PW_EXECUTABLE } : {}),
          args: process.env.PW_ARGS ? process.env.PW_ARGS.split(/\s+/) : [],
        },
      },
    },
  ],
});
