import { expect, Page } from "@playwright/test";
import fs from "node:fs";

/**
 * Shared staging-e2e harness: the proven AuthKit sign-in, session creation,
 * IDE file authoring and palette-driven simulate used by every staging spec.
 * Extracted verbatim from staging.spec.ts (the first spec proven against the
 * deployed app) so a second spec reuses the SAME gestures instead of a
 * near-copy that drifts.
 *
 * Nothing here mocks anything: every helper drives the real deployed UI.
 */

export const ARTIFACTS = "e2e-staging/artifacts";
fs.mkdirSync(ARTIFACTS, { recursive: true });

export const shot = (page: Page, name: string) =>
  page.screenshot({ path: `${ARTIFACTS}/${name}.png`, fullPage: true });

export const log = (...a: unknown[]) => console.log("[STAGING]", ...a);

export const EMAIL = process.env.STAGING_EMAIL || "";
export const PASSWORD = process.env.STAGING_PASSWORD || "";

/** Dump the current auth page state into the run log (URL + visible text) —
 *  artifacts aren't reachable from every diagnosing environment, stdout is. */
export async function dumpAuthState(page: Page, tag: string) {
  const text = await page
    .evaluate(() => document.body?.innerText?.slice(0, 900) ?? "")
    .catch(() => "<no body>");
  log(`[auth:${tag}] url=${page.url()}`);
  log(`[auth:${tag}] text=${JSON.stringify(text)}`);
}

/** AuthKit hosted login: email → (continue) → password → submit. Submits with
 *  Enter on the focused input — clicking a name-matched button risks hitting
 *  the "Sign in with Google" SSO button instead. Tolerant of one-step and
 *  two-step layouts.
 *
 *  `prefix` namespaces this run's screenshots so two specs writing into the
 *  same artifacts directory don't overwrite each other's evidence. */
export async function signIn(page: Page, prefix = "") {
  await page.goto("/");
  await shot(page, `${prefix}00-launcher-signed-out`);
  await page.getByTestId("signin-button").click();
  await page.waitForURL(/authkit\.app|workos/i, { timeout: 60_000 });
  await shot(page, `${prefix}01-authkit`);
  await dumpAuthState(page, "landing");

  // Some AuthKit layouts lead with SSO buttons and hide the email form
  // behind an "email" toggle.
  const emailToggle = page.getByRole("button", { name: /email/i });
  const emailNow = page.locator('input[type="email"], input[name="email"]');
  if (!(await emailNow.count()) && (await emailToggle.count())) {
    await emailToggle.first().click();
  }

  const email = page.locator('input[type="email"], input[name="email"]').first();
  await expect(email).toBeVisible({ timeout: 30_000 });
  await email.fill(EMAIL);
  await email.press("Enter");
  // No networkidle wait: AuthKit keeps connections open, so "networkidle"
  // can simply never fire — with Playwright's unlimited default navigation
  // timeout that ate an entire 35-minute test budget once. The password
  // field appearing IS the after-email signal (the web-assertion pattern
  // Playwright's own docs recommend over networkidle).
  const pwd = page.locator('input[type="password"]').first();
  await expect(pwd).toBeVisible({ timeout: 30_000 });
  await dumpAuthState(page, "after-email");
  await pwd.fill(PASSWORD);
  await shot(page, `${prefix}02-authkit-filled`);
  await pwd.press("Enter");

  // Poll rather than one long wait, logging the page state as it evolves —
  // a wrong-password banner, a verification-code challenge, or a captcha
  // each need a different remedy and must be visible in the run log.
  for (let i = 0; i < 18; i++) {
    await page.waitForTimeout(5_000);
    const href = page.url();
    if (!/authkit\.app|workos/i.test(href)) break;
    await dumpAuthState(page, `post-submit-${(i + 1) * 5}s`);
  }
  await shot(page, `${prefix}03-post-submit`);
  await page.waitForURL((u) => !/authkit\.app|workos/i.test(u.href), { timeout: 15_000 });
  await expect(page.getByTestId("account-chip")).toBeVisible({ timeout: 60_000 });
  await shot(page, `${prefix}04-signed-in`);
  log("signed in as", EMAIL.replace(/(.).*(@.*)/, "$1***$2"));
}

export async function newSession(page: Page, name: string): Promise<string> {
  await page.goto("/");
  await page.getByRole("button", { name: "New session" }).first().click();
  const nameInput = page.getByPlaceholder("Workspace name — e.g. sync_fifo");
  await expect(nameInput).toBeVisible();
  await nameInput.fill(name);
  await page.getByRole("button", { name: /Create session/ }).click();
  await page.waitForURL((u) => /^\/w\//.test(u.pathname), { timeout: 60_000 });
  const sid = decodeURIComponent(new URL(page.url()).pathname.replace("/w/", ""));
  log("session created:", sid);
  return sid;
}

export async function createFileViaUi(page: Page, path: string, content: string) {
  await page.getByRole("button", { name: "New file" }).first().click();
  const input = page.getByLabel("New file path");
  await expect(input).toBeVisible();
  await input.fill(path);
  await input.press("Enter");

  const tab = page.getByRole("tab", { name: new RegExp(path.split("/").pop()!.replace(".", "\\.")) });
  await expect(tab).toBeVisible({ timeout: 30_000 });

  const monaco = page.locator(".monaco-editor:visible").first();
  const fallback = page.getByLabel("Code editor");
  await expect(monaco.or(fallback)).toBeVisible({ timeout: 45_000 });

  if (await fallback.count()) {
    await fallback.fill(content);
  } else {
    await monaco.click();
    await page.keyboard.press("ControlOrMeta+a");
    await page.keyboard.press("Delete");
    await page.keyboard.insertText(content);
  }

  const save = page.getByRole("button", { name: /^Save/ });
  await expect(save).toBeEnabled({ timeout: 15_000 });
  await save.click();
  await expect(page.getByText("Saved").first()).toBeVisible({ timeout: 30_000 });
}

/** Run Simulate from the ⌘K palette; return {apiOrigin, bearer, body}.
 *  The bearer is read off the app's OWN request — the test never mints a
 *  token, so what it asserts against the API is exactly what the UI is
 *  allowed to do. */
export async function simulateViaPalette(page: Page) {
  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByPlaceholder("Run a command…")).toBeVisible();
  const [req, resp] = await Promise.all([
    page.waitForRequest((r) => r.url().includes("/simulate") && r.method() === "POST", { timeout: 30_000 }),
    page.waitForResponse((r) => r.url().includes("/simulate") && r.request().method() === "POST", {
      timeout: 240_000,
    }),
    page.getByRole("option", { name: /^Simulate/ }).click(),
  ]);
  const bearer = req.headers()["authorization"] ?? "";
  const apiOrigin = new URL(req.url()).origin;
  const body = await resp.json();
  return { apiOrigin, bearer, body };
}

// ---------------------------------------------------------------------------
// Auth freshness
//
// The app's bearer is a WorkOS access token with a ~5-minute TTL; the AuthKit
// SDK refreshes it in the page (lib/auth.tsx: onRefresh -> tokenRef). A bearer
// copied once out of one request is therefore STALE after ~5 minutes — which is
// exactly what happened on staging run 31341766743: every poll past t+302s was
// an unauthorized response the spec parsed into `status=undefined`.
//
// Fix: never hold a token, hold a *subscription*. This listener records the
// authorization header off EVERY request the app makes, so the holder always
// carries the freshest token the page has minted. It is passive — no gesture,
// no interception, nothing the app can notice.
// ---------------------------------------------------------------------------

export interface BearerHolder {
  /** Latest `authorization` header seen from the app (empty until first seen). */
  value: string;
  /** Origin of the API the app is talking to (captured alongside the token). */
  origin: string;
  /** Wall-clock ms of the last capture — logged so staleness is visible. */
  seenAt: number;
  /** How many distinct tokens we've seen — proof the refresh loop is alive. */
  rotations: number;
}

export function attachBearerCapture(page: Page): BearerHolder {
  const holder: BearerHolder = { value: "", origin: "", seenAt: 0, rotations: 0 };
  page.on("request", (req) => {
    const auth = req.headers()["authorization"];
    if (!auth || !req.url().includes("/api/")) return;
    if (auth !== holder.value) holder.rotations += 1;
    holder.value = auth;
    holder.origin = new URL(req.url()).origin;
    holder.seenAt = Date.now();
  });
  return holder;
}

/** Age of the captured bearer, in seconds (Infinity when nothing captured). */
export function bearerAgeSec(holder: BearerHolder): number {
  return holder.seenAt ? Math.round((Date.now() - holder.seenAt) / 1000) : Infinity;
}

/** Open the bottom dock's Runs tab (expanding the dock if collapsed) so the
 *  per-run Refresh affordance is on screen. Best-effort: the caller has an
 *  API fallback and must not die because a dock didn't open. */
export async function openRunsDock(page: Page): Promise<boolean> {
  try {
    const expand = page.getByRole("button", { name: "Expand dock" });
    if (await expand.count()) await expand.first().click();
    const runsTab = page.getByRole("button", { name: /^Runs\b/ }).first();
    await runsTab.click({ timeout: 10_000 });
    return true;
  } catch {
    return false;
  }
}

/** Make the app issue an authenticated request of its own — the dock's
 *  "Refresh activity and runs" gesture (loadActivity + loadRuns). Two jobs:
 *  it re-hydrates the runs table (so a run dispatched over the API appears as
 *  a row), and it forces the page to send a request, which is how the passive
 *  capture above learns the freshest token. Returns false if the affordance
 *  wasn't there. */
export async function warmAuth(page: Page): Promise<boolean> {
  try {
    const btn = page.getByRole("button", { name: "Refresh activity and runs" }).first();
    await btn.click({ timeout: 10_000 });
    await page
      .waitForResponse((r) => r.url().includes("/runs") && r.request().method() === "GET", { timeout: 20_000 })
      .catch(() => {});
    return true;
  } catch {
    return false;
  }
}

/** The shape both response kinds share: `page.request` returns an APIResponse,
 *  a captured network response is a Response. Structural, so one reader serves
 *  the direct-API poll and the app's-own-gesture poll alike. */
export interface BodyLike {
  status(): number;
  ok(): boolean;
  text(): Promise<string>;
}

/** Read a response ONCE, keeping the raw text next to the parsed JSON.
 *  Never poll blind: callers log `status` + `raw` whenever the field they
 *  expected is missing, so an auth failure can never masquerade as an
 *  undefined status again. */
export async function readBody(resp: BodyLike): Promise<{
  status: number;
  ok: boolean;
  json: any;
  raw: string;
}> {
  const raw = await resp.text();
  let json: any = null;
  try {
    json = JSON.parse(raw);
  } catch {
    /* not JSON — `raw` is the evidence */
  }
  return { status: resp.status(), ok: resp.ok(), json, raw };
}

/** Does this response look like an expired/absent token? Covers the HTTP
 *  codes and the app's typed error envelope (`_err("signin_required"…)`). */
export function looksUnauthorized(res: { status: number; raw: string }): boolean {
  if (res.status === 401 || res.status === 403) return true;
  return /signin_required|unauthorized|not authenticated|invalid.{0,12}token|expired/i.test(
    res.raw.slice(0, 600)
  );
}

/** /invoke and every tool wrapper may return the tool result as an object or
 *  as a JSON string (mirrors frontend parseToolJsonResult). */
export function parseToolResult(result: unknown): Record<string, any> | null {
  if (result && typeof result === "object" && !Array.isArray(result)) return result as Record<string, any>;
  if (typeof result === "string") {
    try {
      const parsed = JSON.parse(result);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) return parsed;
    } catch {
      /* not JSON */
    }
  }
  return null;
}
