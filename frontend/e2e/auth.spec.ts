import { test, expect, Route, Page } from "@playwright/test";

/**
 * Tier-2 auth verification (real browser). Two mutually-exclusive paths, gated on
 * whether OAuth is configured for the dev server under test:
 *
 *   • UNSET  (default dev server) — no sign-in UI renders and NO request carries
 *     an Authorization header (the zero-config / self-host guarantee).
 *   • SET    — run with `NEXT_PUBLIC_GOOGLE_CLIENT_ID=<id> npm run e2e`. GIS is
 *     mocked via addInitScript; clicking sign-in flips the UI to the account chip
 *     and a subsequent gated request carries `Authorization: Bearer <token>`.
 *
 * The header is asserted from the /api/** route interceptor (equivalent to
 * inspecting browser_network_requests).
 */

const CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

const SESSIONS = [
  { id: "demo", name: "demo", model_name: "claude-sonnet-4-6", project_id: null, created_at: null, updated_at: null, total_tokens: 0, total_cost: 0 },
];
const MANIFEST = {
  ok: true,
  manifest: { sessionId: "demo", files: [{ name: "alu.v", role: "rtl", path: "alu.v" }], synthTop: "alu", simTop: null, clockPeriodNs: 10, platform: "sky130hd" },
};

/** Mock the action layer and record the Authorization header seen on a gated
 *  request (the unified /runs poll fires on load). */
function installMocks(page: Page) {
  const seen: { runsAuth: string | null } = { runsAuth: null };
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  page.route("**/api/**", async (route) => {
    const p = new URL(route.request().url()).pathname;
    const m = route.request().method();
    if (p.endsWith("/runs") && m === "GET") {
      seen.runsAuth = route.request().headers()["authorization"] ?? null;
      return json(route, { ok: true, runs: [] });
    }
    if (p === "/api/sessions" && m === "GET") return json(route, SESSIONS);
    if (p.endsWith("/manifest")) return json(route, MANIFEST);
    if (p.endsWith("/history")) return json(route, []);
    if (p.endsWith("/code") && m === "GET") return json(route, [{ filename: "alu.v", content: "module alu; endmodule", language: "verilog" }]);
    if (p.endsWith("/spec")) return json(route, { detail: "No spec" }, 404);
    return json(route, []);
  });
  return seen;
}

/** Mock Google Identity Services so prompt() immediately yields a fake ID token. */
async function mockGis(page: Page, email = "dev@siliconcrew.test") {
  await page.addInitScript((em) => {
    const b64url = (o: unknown) =>
      btoa(JSON.stringify(o)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
    const token = `${b64url({ alg: "none" })}.${b64url({ email: em, name: "Dev", exp: Math.floor(Date.now() / 1000) + 3600 })}.sig`;
    let cb: ((r: { credential: string }) => void) | null = null;
    (window as unknown as { google: unknown }).google = {
      accounts: {
        id: {
          initialize: (cfg: { callback: (r: { credential: string }) => void }) => { cb = cfg.callback; },
          prompt: () => cb?.({ credential: token }),
          disableAutoSelect: () => {},
        },
      },
    };
  }, email);
}

test.describe("auth — unconfigured (zero-config self-host)", () => {
  test.skip(!!CLIENT_ID, "runs only when NEXT_PUBLIC_GOOGLE_CLIENT_ID is unset");

  test("no sign-in UI and no Authorization header is sent", async ({ page }) => {
    const seen = installMocks(page);
    await page.goto("/workbench");
    await expect(page.getByTestId("wb-brand")).toBeVisible();
    await expect(page.locator('[data-stage="synth"]')).toBeVisible();
    // Zero auth chrome.
    await expect(page.getByTestId("signin-button")).toHaveCount(0);
    await expect(page.getByTestId("account-chip")).toHaveCount(0);
    // Synth stage is NOT gated to a sign-in prompt — it reads "run synth".
    await expect(page.locator('[data-stage="synth"]')).not.toContainText(/sign in/i);
    // And the gated request carried no auth header.
    await expect.poll(() => seen.runsAuth).toBeNull();
  });
});

test.describe("auth — configured (Google sign-in)", () => {
  test.skip(!CLIENT_ID, "set NEXT_PUBLIC_GOOGLE_CLIENT_ID to run this path");

  test("sign-in flips to the account chip and a gated request carries the Bearer token", async ({ page }) => {
    await mockGis(page);
    const seen = installMocks(page);
    await page.goto("/workbench");

    // Signed-out: the sign-in button shows; synth is gated.
    await expect(page.getByTestId("signin-button")).toBeVisible();
    await expect(page.locator('[data-stage="synth"]')).toContainText(/sign in/i);

    // Sign in (mocked GIS resolves immediately) → account chip appears.
    await page.getByTestId("signin-button").click();
    await expect(page.getByTestId("account-chip")).toBeVisible();
    await expect(page.getByTestId("signin-button")).toHaveCount(0);

    // A subsequent gated request carries Authorization: Bearer <token>.
    await page.locator('[data-stage="synth"]').click(); // now unlocked → triggers a run/poll
    await expect.poll(() => seen.runsAuth).toMatch(/^Bearer .+/);
  });
});
