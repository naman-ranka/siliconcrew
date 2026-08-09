import { test, expect, Page } from "@playwright/test";
import fs from "node:fs";

/**
 * Staging smoke: sign in through WorkOS AuthKit, then drive a real design
 * through the deployed app — session creation, RTL written through the IDE,
 * a real simulation — and assert the honest-state surfaces:
 *   - `module automatic counter` resolves synthTop "counter" (not a phantom);
 *   - a duplicate module produces the collision warning naming both files;
 *   - `// disabled: /*` does not swallow the following module;
 *   - the sim run's logFile is workspace-relative and readable.
 * Mirrors the locally-proven real.flow spec; the only staging addition is
 * AuthKit login and bearer capture for direct API asserts.
 */

const ARTIFACTS = "e2e-staging/artifacts";
fs.mkdirSync(ARTIFACTS, { recursive: true });
const shot = (page: Page, name: string) =>
  page.screenshot({ path: `${ARTIFACTS}/${name}.png`, fullPage: true });
const log = (...a: unknown[]) => console.log("[STAGING]", ...a);

const EMAIL = process.env.STAGING_EMAIL || "";
const PASSWORD = process.env.STAGING_PASSWORD || "";

const COUNTER_V = `// 8-bit counter — lifetime qualifier on the module keyword.
module automatic counter (
    input  wire       clk,
    input  wire       rst,
    output reg  [7:0] q
);
    always @(posedge clk) begin
        if (rst) q <= 8'd0;
        else     q <= q + 8'd1;
    end
endmodule
`;

const COUNTER_TB_V = `\`timescale 1ns/1ps
module counter_tb;
    reg clk = 1'b0;
    reg rst = 1'b1;
    wire [7:0] q;

    counter dut (.clk(clk), .rst(rst), .q(q));

    always #5 clk = ~clk;

    initial begin
        $dumpfile("counter_tb.vcd");
        $dumpvars(0, counter_tb);
        #12 rst = 1'b0;
        #100;
        if (q !== 8'd0) begin
            $display("TEST PASSED");
        end else begin
            $display("TEST FAILED: counter did not advance");
        end
        $finish;
    end
endmodule
`;

const DUP_V = `// A second, conflicting definition of the same module.
module counter (
    input  wire       clk,
    input  wire       rst,
    output reg  [7:0] q
);
    always @(posedge clk) q <= rst ? 8'd0 : q - 8'd1;
endmodule
`;

const TRICKY_V = `// disabled: /*
module gadget (
    input  wire clk,
    input  wire rst,
    output reg  toggle
);
    always @(posedge clk) begin
        if (rst) toggle <= 1'b0;
        else     toggle <= ~toggle;
    end
endmodule
`;

/** Dump the current auth page state into the run log (URL + visible text) —
 *  artifacts aren't reachable from every diagnosing environment, stdout is. */
async function dumpAuthState(page: Page, tag: string) {
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
async function signIn(page: Page) {
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
  await page.waitForLoadState("networkidle").catch(() => {});
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

async function newSession(page: Page, name: string): Promise<string> {
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

async function createFileViaUi(page: Page, path: string, content: string) {
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

/** Run Simulate from the ⌘K palette; return {apiOrigin, bearer, body}. */
async function simulateViaPalette(page: Page) {
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

test("staging: sign in and drive a real design end to end", async ({ page }) => {
  test.skip(!EMAIL || !PASSWORD, "STAGING_EMAIL / STAGING_PASSWORD not provided");
  const results: Record<string, unknown> = {};

  await signIn(page);

  // --- session + RTL through the IDE ---------------------------------------
  const sid = await newSession(page, `e2e_${Date.now().toString(36)}`);
  await expect(page.getByTestId("workbench-v2")).toBeVisible({ timeout: 60_000 });
  await createFileViaUi(page, "counter.v", COUNTER_V);
  await createFileViaUi(page, "counter_tb.v", COUNTER_TB_V);
  await shot(page, "04-files-created");

  // --- simulate (real gesture, real hosted run) ----------------------------
  const sim1 = await simulateViaPalette(page);
  results.sim_dispatch_1 = sim1.body;
  log("sim #1:", JSON.stringify(sim1.body).slice(0, 800));
  expect(sim1.body.run.status).toBe("passed");
  await shot(page, "05-sim-passed");

  const api = (path: string) =>
    page.request.get(`${sim1.apiOrigin}${path}`, {
      headers: sim1.bearer ? { authorization: sim1.bearer } : {},
    });

  // --- manifest truth: lifetime qualifier is not a module name -------------
  const m1 = await (await api(`/api/workspace/${encodeURIComponent(sid)}/manifest`)).json();
  results.manifest_after_create = m1.manifest;
  expect(m1.manifest.synthTop).toBe("counter");
  expect(m1.manifest.simTop).toBe("counter_tb");
  expect(m1.manifest.warnings).toEqual([]);

  // --- logFile: workspace-relative and readable ----------------------------
  const run1 = sim1.body.run;
  expect(run1.logFile).toBe(`sim_runs/${run1.id}/sim.log`);
  const logResp = await api(
    `/api/workspace/${encodeURIComponent(sid)}/file/${encodeURIComponent(run1.logFile)}`
  );
  expect(logResp.ok()).toBeTruthy();
  expect((await logResp.json()).content).toContain("TEST PASSED");

  // --- duplicate module → collision warning on both surfaces ---------------
  await createFileViaUi(page, "dup.v", DUP_V);
  const m2 = await (await api(`/api/workspace/${encodeURIComponent(sid)}/manifest`)).json();
  results.manifest_after_dup = m2.manifest;
  const joined = (m2.manifest.warnings || []).join("\n");
  expect(joined).toContain("counter.v");
  expect(joined).toContain("dup.v");
  expect(joined).toContain("'counter'");
  await shot(page, "06-collision-warning");

  // --- comment-stripper blocker case, fresh session ------------------------
  const sid2 = await newSession(page, `strip_${Date.now().toString(36)}`);
  await expect(page.getByTestId("workbench-v2")).toBeVisible({ timeout: 60_000 });
  await createFileViaUi(page, "tricky.v", TRICKY_V);
  const m3 = await (await api(`/api/workspace/${encodeURIComponent(sid2)}/manifest`)).json();
  results.tricky_manifest = m3.manifest;
  expect(m3.manifest.synthTop).toBe("gadget");
  expect(m3.manifest.warnings).toEqual([]);
  await shot(page, "07-tricky-ok");

  fs.writeFileSync(`${ARTIFACTS}/results.json`, JSON.stringify(results, null, 2));
});
