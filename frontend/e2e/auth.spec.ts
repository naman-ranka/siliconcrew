import { test, expect, Route, Page } from "@playwright/test";

/**
 * Tier-2 auth verification (real browser). Two mutually-exclusive paths, gated on
 * whether OAuth is configured for the dev server under test:
 *
 *   • UNSET  (default dev server) — no sign-in UI renders and NO request carries
 *     an Authorization header (the zero-config / self-host guarantee).
 *   • SET    — run with `GOOGLE_CLIENT_ID=<id> npm run e2e`. GIS is
 *     mocked via addInitScript; clicking sign-in flips the UI to the account chip
 *     and a subsequent gated request carries `Authorization: Bearer <token>`.
 *
 * The header is asserted from the /api/** route interceptor (equivalent to
 * inspecting browser_network_requests).
 */

const CLIENT_ID =
  process.env.GOOGLE_CLIENT_ID || process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

const SESSIONS = [
  { id: "demo", name: "demo", model_name: "claude-sonnet-4-6", project_id: null, created_at: null, updated_at: null, total_tokens: 0, total_cost: 0 },
];
const MANIFEST = {
  ok: true,
  manifest: { sessionId: "demo", files: [{ name: "alu.v", role: "rtl", path: "alu.v" }], synthTop: "alu", simTop: null, clockPeriodNs: 10, platform: "sky130hd" },
};

/** Mock the action layer and record the Authorization header seen on gated
 *  requests (the /workbench snapshot fires on load; /lint on user action). */
function installMocks(page: Page) {
  const seen: { snapshotAuth: string | null; lintAuth: string | null } = { snapshotAuth: null, lintAuth: null };
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  page.route("**/api/**", async (route) => {
    const p = new URL(route.request().url()).pathname;
    const m = route.request().method();
    if (p.endsWith("/workbench") && m === "GET") {
      seen.snapshotAuth = route.request().headers()["authorization"] ?? null;
      return json(route, {
        ok: true, manifest: MANIFEST.manifest, runs: [], files: [], spec: null, code: [],
        report: null, synthesisRuns: [], activity: [],
        rootDir: [{ name: "alu.v", path: "alu.v", kind: "file", size: 22, modified: "2026-07-01T10:00:00" }],
      });
    }
    if (p.endsWith("/lint") && m === "POST") {
      seen.lintAuth = route.request().headers()["authorization"] ?? null;
      return json(route, { ok: true, status: "passed", warnings: [], errors: [], byFile: {}, command: "iverilog", files: ["alu.v"] });
    }
    if (p.endsWith("/runs") && m === "GET") return json(route, { ok: true, runs: [] });
    if (p.endsWith("/dir") && m === "GET")
      return json(route, { ok: true, path: "", entries: [{ name: "alu.v", path: "alu.v", kind: "file", size: 22, modified: "2026-07-01T10:00:00" }] });
    if (p.endsWith("/activity")) return json(route, { ok: true, events: [], nextBefore: null });
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
    await expect(page.getByTestId("workbench-v2")).toBeVisible();
    await expect(page.getByText("alu.v")).toBeVisible();
    // Zero auth chrome: no standalone sign-in button; the profile menu shows no
    // sign-in entry when auth is unconfigured.
    await expect(page.getByTestId("signin-button")).toHaveCount(0);
    await page.getByTestId("profile-menu-button").click();
    await expect(page.getByTestId("profile-menu")).toBeVisible();
    await expect(page.getByTestId("profile-menu").getByText(/sign in/i)).toHaveCount(0);
    await page.keyboard.press("Escape");
    // And the gated snapshot request carried no auth header.
    await expect.poll(() => seen.snapshotAuth).toBeNull();
  });
});

test.describe("auth — configured (Google sign-in)", () => {
  test.skip(!CLIENT_ID, "set NEXT_PUBLIC_GOOGLE_CLIENT_ID to run this path");

  test("sign-in via the profile menu; a gated request carries the Bearer token", async ({ page }) => {
    await mockGis(page);
    const seen = installMocks(page);
    await page.goto("/workbench");
    await expect(page.getByTestId("workbench-v2")).toBeVisible();

    // Signed-out: the profile menu offers Google sign-in (mocked GIS resolves
    // immediately) and then shows the account identity.
    await page.getByTestId("profile-menu-button").click();
    await page.getByTestId("profile-menu").getByText(/sign in with google/i).click();
    await page.getByTestId("profile-menu-button").click();
    await expect(page.getByTestId("profile-menu").getByText("dev@siliconcrew.test")).toBeVisible();
    await page.keyboard.press("Escape");

    // A subsequent user action carries Authorization: Bearer <token>.
    await page.keyboard.press("ControlOrMeta+k");
    await page.getByRole("option", { name: /^Lint/ }).click();
    await expect.poll(() => seen.lintAuth).toMatch(/^Bearer .+/);
  });
});
