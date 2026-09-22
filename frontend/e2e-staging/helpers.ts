import { expect, Page } from "@playwright/test";
import fs from "node:fs";

/**
 * Shared staging helpers: artifact capture and the AuthKit sign-in flow.
 * Extracted so every staging spec drives the deployed app through ONE
 * login path — a second copy would drift the moment AuthKit's layout moves.
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
 *  two-step layouts. */
export async function signIn(page: Page) {
  await page.goto("/");
  await shot(page, "00-launcher-signed-out");
  await page.getByTestId("signin-button").click();
  await page.waitForURL(/authkit\.app|workos/i, { timeout: 60_000 });
  await shot(page, "01-authkit");
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
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
  await dumpAuthState(page, "after-email");

  const pwd = page.locator('input[type="password"]').first();
  await expect(pwd).toBeVisible({ timeout: 30_000 });
  await pwd.fill(PASSWORD);
  await shot(page, "02-authkit-filled");
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
  await shot(page, "03-post-submit");
  await page.waitForURL((u) => !/authkit\.app|workos/i.test(u.href), { timeout: 15_000 });
  await expect(page.getByTestId("account-chip")).toBeVisible({ timeout: 60_000 });
  await shot(page, "04-signed-in");
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

