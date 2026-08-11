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
        // chrome-headless-shell (Playwright's headless default) cannot get a
        // TLS session through such a proxy — use the full chromium build, and
        // set PW_TLS_MAX=tls1.2 where the proxy's MITM also resets Chromium's
        // TLS 1.3 handshake. Neither is needed against a direct connection.
        channel: process.env.PW_CHANNEL || "chromium",
        launchOptions: {
          ...(process.env.PW_EXECUTABLE ? { executablePath: process.env.PW_EXECUTABLE } : {}),
          args: [
            ...(process.env.PW_NO_SANDBOX ? ["--no-sandbox"] : []),
            ...(process.env.PW_TLS_MAX ? [`--ssl-version-max=${process.env.PW_TLS_MAX}`] : []),
          ],
        },
      },
    },
  ],
});
