import { test, expect, Page } from "@playwright/test";
import fs from "node:fs";
import { ARTIFACTS, shot, log, EMAIL, PASSWORD, signIn, newSession } from "./helpers";

/**
 * Post-merge verification of the three fixes in #85 (issue #93) against the
 * DEPLOYED app. Each assertion targets the exact symptom that was observed
 * live before the change, so a pass here means the bug is gone from staging —
 * not that a unit test agrees with itself:
 *
 *   Bug 1  the IDE had 0 `input[type=file]` and 0 upload buttons; uploads are
 *          now driven BOTH ways (header button, drag-drop) and the bytes are
 *          read back through the API to prove they reached the workspace.
 *   Bug 4  the frontend's own `/api/health` 502'd on 5/5 calls while the
 *          backend answered 200 — the proxy now resolves the backend at
 *          runtime. Needs no sign-in, so it runs unauthenticated too.
 *   Bug 5  ⌘O was dead on the "Session not found" screen, and every load
 *          failure claimed "not found". The failure screen is now honest
 *          (404 vs unreachable) and always a way out, never a trap.
 */

const UPLOAD_NAME = "uploaded_probe.v";
const UPLOAD_V = `// Uploaded through the file-explorer button (issue #93 bug 1).
module uploaded_probe (
    input  wire clk,
    output reg  tick
);
    always @(posedge clk) tick <= ~tick;
endmodule
`;

const DROP_NAME = "dropped_probe.v";
const DROP_V = `// Uploaded by dropping onto the explorer body (issue #93 bug 1).
module dropped_probe (
    input  wire clk,
    output reg  beat
);
    always @(posedge clk) beat <= ~beat;
endmodule
`;

/** Bug 4 needs no session, so it is its own test and runs even without creds. */
test("issue #93 bug 4: the frontend's /api/health proxy reaches the backend", async ({ page }) => {
  const codes: number[] = [];
  let body: unknown = null;
  for (let i = 0; i < 5; i++) {
    const res = await page.request.get("/api/health");
    codes.push(res.status());
    if (i === 0) body = await res.json().catch(() => null);
  }
  log("proxy /api/health statuses:", codes.join(","), "body:", JSON.stringify(body));
  // The live symptom was 502 on every call — assert all five, not just one.
  expect(codes).toEqual([200, 200, 200, 200, 200]);
  expect((body as { status?: string })?.status).toBe("healthy");
});

test("issue #93 bugs 1 & 5: uploads land, and a dead deep link is honest and escapable", async ({
  page,
}) => {
  test.skip(!EMAIL || !PASSWORD, "STAGING_EMAIL / STAGING_PASSWORD not provided");
  test.setTimeout(600_000);
  const results: Record<string, unknown> = {};

  await signIn(page);

  const sid = await newSession(page, `issue93_${Date.now().toString(36)}`);
  await expect(page.getByTestId("workbench-v2")).toBeVisible({ timeout: 60_000 });

  // ── Bug 1: the affordances that were absent on the live app ──────────────
  const uploadButton = page.getByRole("button", { name: "Upload files to workspace root" });
  const uploadInput = page.locator('input[type="file"]');
  await expect(uploadButton).toBeVisible({ timeout: 30_000 });
  await expect(uploadButton).toBeEnabled();
  await expect(uploadInput).toHaveCount(1);
  results.upload_affordances = { button: 1, fileInputs: await uploadInput.count() };
  log("upload affordances present (live app had 0 of each)");

  // ── Bug 1a: upload through the header button ─────────────────────────────
  // Capture the real request so the server-side read below uses the same
  // origin + bearer the app itself used, rather than a guessed API base.
  const uploadReq = page.waitForRequest(
    (r) => r.url().includes(`/files`) && r.method() === "POST",
    { timeout: 60_000 }
  );
  await uploadInput.setInputFiles({
    name: UPLOAD_NAME,
    mimeType: "text/plain",
    buffer: Buffer.from(UPLOAD_V),
  });
  const req = await uploadReq;
  const bearer = req.headers()["authorization"] ?? "";
  const apiOrigin = new URL(req.url()).origin;
  log("upload POST ->", req.url());

  await expect(page.getByText(/Uploaded 1 file\(s\)/)).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("treeitem", { name: new RegExp(UPLOAD_NAME) })).toBeVisible({
    timeout: 30_000,
  });
  await shot(page, "i93-01-uploaded-via-button");

  // ── Bug 1b: upload by dropping on the explorer body ──────────────────────
  // A real DragEvent carrying a real File — the same path a user's drop takes
  // (dragenter → dragover → drop), not a call into the store.
  await page.evaluate(
    ({ name, text }) => {
      const tree = document.querySelector('[role="tree"][aria-label="Workspace files"]');
      const target = tree?.parentElement;
      if (!target) throw new Error("explorer drop target not found");
      const dt = new DataTransfer();
      dt.items.add(new File([text], name, { type: "text/plain" }));
      for (const type of ["dragenter", "dragover", "drop"]) {
        target.dispatchEvent(new DragEvent(type, { dataTransfer: dt, bubbles: true, cancelable: true }));
      }
    },
    { name: DROP_NAME, text: DROP_V }
  );
  await expect(page.getByRole("treeitem", { name: new RegExp(DROP_NAME) })).toBeVisible({
    timeout: 60_000,
  });
  await shot(page, "i93-02-uploaded-via-drop");

  // ── Bug 1c: the bytes really reached the workspace ───────────────────────
  const readFile = async (name: string) => {
    const res = await page.request.get(
      `${apiOrigin}/api/workspace/${encodeURIComponent(sid)}/file/${encodeURIComponent(name)}`,
      { headers: bearer ? { authorization: bearer } : {} }
    );
    expect(res.ok()).toBeTruthy();
    return (await res.json()).content as string;
  };
  expect(await readFile(UPLOAD_NAME)).toContain("module uploaded_probe");
  expect(await readFile(DROP_NAME)).toContain("module dropped_probe");
  results.uploads_readable = [UPLOAD_NAME, DROP_NAME];
  log("both uploads read back from the workspace");

  // ── Bug 5a: a genuinely unknown id → "not found", with a way out ─────────
  const ghost = `definitely_not_a_real_session_${Date.now().toString(36)}`;
  await page.goto(`/w/${ghost}`);
  await expect(page.getByTestId("workbench-not-found")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Open another session/ })).toBeVisible();
  await shot(page, "i93-03-not-found");

  // The exact dead key: ⌘O did nothing here on the live app.
  await page.keyboard.press("ControlOrMeta+o");
  const switcher = page.getByRole("dialog");
  await expect(switcher).toBeVisible({ timeout: 15_000 });
  const switcherText = (await switcher.innerText()).slice(0, 200);
  log("⌘O on the not-found screen opened:", JSON.stringify(switcherText));
  results.cmd_o_on_error_page = switcherText;
  await shot(page, "i93-04-cmd-o-works");
  await page.keyboard.press("Escape");

  // ── Bug 5b: an unreachable backend must NOT be reported as "not found" ───
  // Fail the session reads (list + direct GET) so the deep link cannot
  // resolve — for a session that demonstrably EXISTS (just created above).
  await page.route("**/api/sessions**", (route) => route.abort("connectionfailed"));
  await page.goto(`/w/${encodeURIComponent(sid)}`);
  const unreachable = page.getByTestId("workbench-unreachable");
  const notFound = page.getByTestId("workbench-not-found");
  await expect(unreachable.or(notFound)).toBeVisible({ timeout: 60_000 });
  const bodyText = await page.evaluate(() => document.body.innerText.slice(0, 400));
  log("outage screen text:", JSON.stringify(bodyText));
  results.outage_screen = bodyText;
  await shot(page, "i93-05-unreachable");
  // The honesty claim: a live session behind a dead server is never "gone".
  await expect(unreachable).toBeVisible();
  await expect(page.getByText(/the session may still be there/)).toBeVisible();
  await expect(notFound).toHaveCount(0);
  await page.unroute("**/api/sessions**");

  fs.writeFileSync(`${ARTIFACTS}/issue93-results.json`, JSON.stringify(results, null, 2));
});
