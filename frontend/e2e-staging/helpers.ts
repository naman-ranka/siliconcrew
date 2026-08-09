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
