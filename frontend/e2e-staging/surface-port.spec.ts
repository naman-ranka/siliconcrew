import { test, expect, Page, Locator } from "@playwright/test";
import fs from "node:fs";
import { ARTIFACTS, shot, log, EMAIL, PASSWORD, signIn, newSession } from "./helpers";

/**
 * Staging drive of the Command Surface simplification port (PR #90 re-expressed
 * on current main — plans/command-surface-simplification-v2.md §2). One
 * sequential journey against the DEPLOYED app, screenshots at every step
 * (`surface-NN-*.png`), every assertion outcome in the run log.
 *
 * Steps are wrapped so a failing step is LOGGED and the drive continues — the
 * report needs pass/fail per step, not the first failure — and the test still
 * fails at the end if any step failed. A step that cannot be driven from the
 * UI logs "NOT DRIVABLE: <why>" instead of pretending.
 *
 * Nothing paid is dispatched: synthesis is only screenshotted disarmed.
 */

// ---- the nested design -------------------------------------------------------
// Nested on purpose: `rtl/alu.v` resolving to its ws-relative path in the
// override picker is the bug PR #90 fixed (LN11/FA2 — `name` vs `path`).

const ALU_V = `// A tiny ALU — instantiated by top, so a lint of top.v ALONE cannot elaborate it.
module alu (
    input  wire [7:0] a,
    input  wire [7:0] b,
    input  wire       op,
    output reg  [7:0] y
);
    always @(*) begin
        if (op) y = a - b;
        else    y = a + b;
    end
endmodule
`;

const TOP_V = `// Design top: registers the ALU result.
module top (
    input  wire       clk,
    input  wire       rst,
    input  wire [7:0] a,
    input  wire [7:0] b,
    input  wire       op,
    output reg  [7:0] y
);
    wire [7:0] alu_y;
    alu u_alu (.a(a), .b(b), .op(op), .y(alu_y));
    always @(posedge clk) begin
        if (rst) y <= 8'd0;
        else     y <= alu_y;
    end
endmodule
`;

const TOP_TB_V = `\`timescale 1ns/1ps
module top_tb;
    reg        clk = 1'b0;
    reg        rst = 1'b1;
    reg  [7:0] a = 8'd3;
    reg  [7:0] b = 8'd4;
    reg        op = 1'b0;
    wire [7:0] y;

    top dut (.clk(clk), .rst(rst), .a(a), .b(b), .op(op), .y(y));

    always #5 clk = ~clk;

    initial begin
        $dumpfile("top_tb.vcd");
        $dumpvars(0, top_tb);
        #12 rst = 1'b0;
        #20;
        if (y === 8'd7) begin
            $display("TEST PASSED");
        end else begin
            $display("TEST FAILED: y=%0d expected 7", y);
        end
        $finish;
    end
endmodule
`;

// ---- drive helpers ------------------------------------------------------------

let shotSeq = 0;
/** Numbered screenshot under the `surface-` prefix, so the artifact folder
 *  reads in journey order. */
const snap = (page: Page, name: string) =>
  shot(page, `surface-${String(shotSeq++).padStart(2, "0")}-${name}`);

/** The api origin + bearer the app itself used — captured off its own
 *  requests so direct reads use exactly the credentials the UI used. */
const api = { origin: "", bearer: "" };

const results: Record<string, unknown> = {};
const failures: string[] = [];
let serverManifest: Manifest | null = null;

/** Run one journey step; a throw is logged (with a screenshot) and recorded,
 *  and the drive continues so every later step still reports. */
async function step(page: Page, name: string, fn: () => Promise<void>) {
  log(`── step ${name} ──`);
  try {
    await fn();
    log(`STEP PASS: ${name}`);
    results[`step ${name}`] = "pass";
  } catch (e) {
    const msg = e instanceof Error ? e.message.split("\n").slice(0, 6).join("\n") : String(e);
    log(`STEP FAIL: ${name} — ${msg}`);
    failures.push(name);
    results[`step ${name}`] = `fail: ${msg}`;
    await snap(page, `FAIL-${name.replace(/[^a-z0-9]+/gi, "-").toLowerCase()}`).catch(() => {});
    // Leave no modal behind for the next step (best effort).
    await page.keyboard.press("Escape").catch(() => {});
  }
}

/** Assert + log in one move, so the run log carries every outcome. */
async function check(label: string, assertion: () => void | Promise<void>) {
  await assertion();
  log(`  ok: ${label}`);
}

async function createFileViaUi(page: Page, path: string, content: string) {
  await page.getByRole("button", { name: "New file" }).first().click();
  const input = page.getByLabel("New file path");
  await expect(input).toBeVisible();
  await input.fill(path);
  await input.press("Enter");

  const base = path.split("/").pop()!;
  const tab = page.getByRole("tab", { name: new RegExp(base.replace(/\./g, "\\.")) });
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
  log("created", path);
}

const apiGet = (page: Page, path: string) =>
  page.request.get(`${api.origin}${path}`, {
    headers: api.bearer ? { authorization: api.bearer } : {},
  });

type ManifestFile = { path: string; name: string; role: string };
type Manifest = {
  synthTop: string;
  simTop: string;
  files: ManifestFile[];
  testbenches: { file: string; module: string }[];
  warnings: string[];
};

async function readManifest(page: Page, sid: string): Promise<Manifest> {
  const res = await apiGet(page, `/api/workspace/${encodeURIComponent(sid)}/manifest`);
  expect(res.ok()).toBeTruthy();
  return (await res.json()).manifest as Manifest;
}

const surfaceOf = (page: Page) => page.getByTestId("command-surface");
const payloadOf = (page: Page) => surfaceOf(page).locator('[aria-label="tool call payload"]');

async function openPalette(page: Page) {
  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByPlaceholder("Run a command…")).toBeVisible({ timeout: 15_000 });
}

/** The Surface is opened the way the local smoke test opens it: ⌘K → "All
 *  commands…". Idempotent, so every step can start from a known state. */
async function ensureSurfaceOpen(page: Page) {
  const surface = surfaceOf(page);
  if (await surface.isVisible().catch(() => false)) return;
  await openPalette(page);
  await page.getByRole("option", { name: /All commands/ }).click();
  await expect(surface).toBeVisible({ timeout: 15_000 });
}

async function closeSurface(page: Page) {
  const surface = surfaceOf(page);
  if (!(await surface.isVisible().catch(() => false))) return;
  await surface.getByRole("button", { name: "Close command surface" }).click();
  await expect(surface).toHaveCount(0);
}

async function selectRailCommand(page: Page, label: string) {
  const surface = surfaceOf(page);
  // The rail filter is stateful for the life of the dialog (R67: the
  // selection is never forced into the filtered set, but hidden rows cannot
  // be clicked). Run 2 left "lint" in it from step 3 and waited 13 minutes
  // for a Simulate row that was filtered away — clear it first.
  const filter = page.getByTestId("command-surface-filter");
  if ((await filter.inputValue().catch(() => "")) !== "") await filter.fill("");
  await surface.getByRole("button", { name: label, exact: true }).click();
  await expect(surface.getByRole("heading", { name: label, exact: true })).toBeVisible();
}

/** Add a chip through the override combo by typing a query and picking the
 *  first suggestion with ↓ + Enter. NOTE: a bare Enter on typed text commits
 *  the TEXT as a free-entry chip (ComboInput contract — free entry is always
 *  allowed), so the suggestion has to be highlighted first. */
async function pickOverride(page: Page, combo: Locator, query: string, expectValue: string) {
  await combo.fill(query);
  const option = surfaceOf(page).getByRole("option", { name: expectValue, exact: true });
  await expect(option).toBeVisible({ timeout: 10_000 });
  await combo.press("ArrowDown");
  await combo.press("Enter");
}

/** Click Invoke and wait for the matching action POST. The "Running — Ns"
 *  client clock is raced against the response: a fast lint may land before
 *  it can be seen, so its absence is reported, never failed. */
async function invokeAndWait(page: Page, urlPart: string, timeout = 240_000) {
  const respP = page.waitForResponse(
    (r) => r.url().includes(urlPart) && r.request().method() === "POST",
    { timeout }
  );
  await page.getByTestId("command-surface-invoke").click();
  const elapsed = page.getByTestId("command-surface-elapsed");
  let sawElapsed = "";
  await elapsed
    .waitFor({ state: "visible", timeout: 4_000 })
    .then(async () => {
      sawElapsed = await elapsed.innerText().catch(() => "Running — ?s");
    })
    .catch(() => {});
  const resp = await respP;
  return { resp, sawElapsed };
}

/** Expand `dir` in the explorer if needed and return the row for `path`. */
async function explorerRow(page: Page, path: string): Promise<Locator> {
  const tree = page.getByRole("tree", { name: "Workspace files" });
  const parts = path.split("/");
  let prefix = "";
  for (const part of parts.slice(0, -1)) {
    prefix = prefix ? `${prefix}/${part}` : part;
    const dir = tree.locator(`[role="treeitem"][title="${prefix}"]`);
    await expect(dir).toBeVisible({ timeout: 30_000 });
    if ((await dir.getAttribute("aria-expanded")) !== "true") await dir.click();
    await expect(dir).toHaveAttribute("aria-expanded", "true", { timeout: 15_000 });
  }
  const row = tree.locator(`[role="treeitem"][title="${path}"]`);
  await expect(row).toBeVisible({ timeout: 30_000 });
  return row;
}

// ---- the journey ---------------------------------------------------------------

test("surface port: nested design, overrides, file-scoped lint, sim, context menu, synth guard, ⌘K fast path", async ({
  page,
}) => {
  test.skip(!EMAIL || !PASSWORD, "STAGING_EMAIL / STAGING_PASSWORD not provided");
  test.setTimeout(900_000);

  page.on("request", (r) => {
    if (!api.origin && r.url().includes("/api/workspace/")) {
      api.origin = new URL(r.url()).origin;
      api.bearer = r.headers()["authorization"] ?? "";
      log("api origin captured:", api.origin, api.bearer ? "(bearer present)" : "(no bearer)");
    }
  });

  let sid = "";

  // Playwright Test's default NAVIGATION timeout is 0 (unbounded). signIn's
  // `waitForLoadState("networkidle").catch(...)` (helpers.ts) rides on that
  // timeout, and AuthKit's password page never goes network-idle behind this
  // sandbox proxy — the first run hung there for the full 15 minutes. A
  // bounded navigation timeout turns that wait into the tolerated no-op it
  // was written to be; explicit per-call timeouts elsewhere are unaffected.
  page.setDefaultNavigationTimeout(30_000);
  // Likewise the ACTION timeout defaults to 0: a click on a row that never
  // appears (run 2, a filtered-away rail entry) ate the entire test budget
  // and turned every later step into cascade noise. Bound it so a wrong
  // selector fails its own step in 30 s and the drive keeps reporting.
  page.setDefaultTimeout(30_000);

  // ── 1. sign in + fresh session ──────────────────────────────────────────
  await step(page, "1 sign-in + new session", async () => {
    await signIn(page);
    sid = await newSession(page, `surface_port_${Date.now().toString(36)}`);
    await expect(page.getByTestId("workbench-v2")).toBeVisible({ timeout: 60_000 });
    results.session = sid;
    await snap(page, "session-created");
  });

  // ── 2. nested design through the IDE; wait for the manifest ─────────────
  await step(page, "2 nested design + manifest", async () => {
    await createFileViaUi(page, "rtl/alu.v", ALU_V);
    await createFileViaUi(page, "rtl/top.v", TOP_V);
    await createFileViaUi(page, "tb/top_tb.v", TOP_TB_V);
    await snap(page, "files-created");

    // Server truth FIRST (so it is on record even if the UI assertions below
    // fail): nested PATHS with roles — the `name` vs `path` distinction is
    // the whole point of the nested layout.
    expect(api.origin, "api origin captured off the app's own requests").toBeTruthy();
    const m0 = await readManifest(page, sid);
    results.manifest = m0;
    serverManifest = m0;
    log(
      "manifest (server):",
      JSON.stringify({
        files: Object.fromEntries(m0.files.map((f) => [f.path, f.role])),
        synthTop: m0.synthTop,
        simTop: m0.simTop,
        testbenches: m0.testbenches,
        warnings: m0.warnings,
      })
    );

    // The explorer footer renders the manifest's two anchors — poll it (the
    // inference runs on save; the store refreshes from the save response).
    await check("footer synthTop = top", () =>
      expect(page.getByTitle("Top module used for synthesis")).toHaveText(/\btop\b/, {
        timeout: 60_000,
      })
    );
    await check("footer simTop = top_tb", () =>
      expect(page.getByTitle("Testbench top used for simulation")).toHaveText(/\btop_tb\b/, {
        timeout: 60_000,
      })
    );

    // Re-read after the footer settled (the store and the server must agree).
    const m = await readManifest(page, sid);
    results.manifest = m;
    serverManifest = m;
    const byPath = Object.fromEntries(m.files.map((f) => [f.path, f.role]));
    log("manifest files:", JSON.stringify(byPath), "synthTop:", m.synthTop, "simTop:", m.simTop);
    await check("manifest roles rtl/alu.v=rtl, rtl/top.v=rtl, tb/top_tb.v=tb", async () => {
      expect(byPath["rtl/alu.v"]).toBe("rtl");
      expect(byPath["rtl/top.v"]).toBe("rtl");
      expect(byPath["tb/top_tb.v"]).toBe("tb");
    });
    await check("manifest tops", async () => {
      expect(m.synthTop).toBe("top");
      expect(m.simTop).toBe("top_tb");
    });
    await check("manifest testbench top_tb → tb/top_tb.v", async () => {
      expect(m.testbenches).toContainEqual({ file: "tb/top_tb.v", module: "top_tb" });
    });
    log("manifest warnings:", JSON.stringify(m.warnings));
    await snap(page, "manifest-ready");
  });

  // ── 3. open the Surface: no KeyRound, rail filter, type-to-select ───────
  await step(page, "3 surface: no KeyRound, rail filter → Lint", async () => {
    await ensureSurfaceOpen(page);
    const surface = surfaceOf(page);
    await snap(page, "surface-open");

    // The port deletes both KeyRound render sites (the rail's
    // title="requires sign-in" icon and the detail-header chip). lucide
    // stamps `lucide-key-round` on the svg — assert none in the dialog.
    const keyRound = surface.locator("svg.lucide-key-round");
    const signInTitle = surface.locator('[title="requires sign-in"]');
    await check("no KeyRound svg in the Surface", () => expect(keyRound).toHaveCount(0));
    await check('no title="requires sign-in" in the Surface', () =>
      expect(signInTitle).toHaveCount(0)
    );
    // Stop-the-line marker for Phase 2: the OLD UI has these. Say so loudly.
    if ((await keyRound.count()) > 0 || (await signInTitle.count()) > 0) {
      log("STAGING NOT UPDATED: the KeyRound sign-in badge is still rendered");
    }

    const filter = page.getByTestId("command-surface-filter");
    await check("rail filter input present (aria-label 'Filter commands')", async () => {
      await expect(filter).toBeVisible();
      await expect(filter).toHaveAttribute("aria-label", "Filter commands");
      await expect(filter).toHaveAttribute("placeholder", "Filter commands…");
    });
    await check("rail filter is focused on open", () => expect(filter).toBeFocused());

    await filter.fill("lint");
    await check("filter 'lint' hides Synthesize, keeps Lint", async () => {
      await expect(surface.getByRole("button", { name: "Lint", exact: true })).toBeVisible();
      await expect(surface.getByRole("button", { name: "Synthesize", exact: true })).toHaveCount(0);
    });
    await filter.press("Enter");
    await check("Enter selects Lint (aria-current) and opens its detail", async () => {
      await expect(surface.getByRole("button", { name: "Lint", exact: true })).toHaveAttribute(
        "aria-current",
        "true"
      );
      await expect(surface.getByRole("heading", { name: "Lint", exact: true })).toBeVisible();
    });
    await snap(page, "surface-lint-selected");
  });

  // ── 4. Lint detail: override box, suggested tier, nested path, payload ──
  await step(page, "4 lint override box + nested suggestion", async () => {
    await ensureSurfaceOpen(page);
    await selectRailCommand(page, "Lint");
    const surface = surfaceOf(page);
    const box = surface.getByTestId("command-surface-override-files");
    await check("override box for `files` present", () => expect(box).toBeVisible());
    await check("collapsed: 'Supplied by manifest · files' with chips rtl/alu.v, rtl/top.v", async () => {
      await expect(box).toContainText("Supplied by manifest");
      await expect(box).toContainText("rtl/alu.v");
      await expect(box).toContainText("rtl/top.v");
      await expect(box).not.toContainText("tb/top_tb.v"); // lint set = rtl + include
    });
    await check("payload has no `files` key while collapsed", () =>
      expect(payloadOf(page)).not.toContainText('"files"')
    );
    await snap(page, "lint-override-collapsed");

    await box.getByRole("button", { name: "Override…" }).click();
    const combo = surface.getByRole("combobox", { name: "Override files" });
    await check("Override… opens the multi-combo", async () => {
      await expect(combo).toBeVisible();
      await expect(box).toContainText("Overriding the manifest set");
    });
    await check("placeholder names the REAL manifest count", () =>
      expect(combo).toHaveAttribute("placeholder", "manifest set (2 files) — type to override")
    );

    await combo.click();
    const listbox = surface.getByRole("listbox", { name: "Override files suggestions" });
    await check("focus shows ONLY the suggested tier (manifest files, no divider)", async () => {
      await expect(listbox).toBeVisible();
      await expect(listbox.getByRole("option", { name: "rtl/alu.v", exact: true })).toBeVisible();
      await expect(listbox.getByRole("option", { name: "rtl/top.v", exact: true })).toBeVisible();
      await expect(listbox.getByRole("option")).toHaveCount(2);
      await expect(listbox.getByTestId("combo-tier-divider")).toHaveCount(0);
    });
    await check("suggestion rows carry the role subtitle", () =>
      expect(listbox.getByRole("option", { name: "rtl/alu.v", exact: true })).toContainText("rtl")
    );
    await snap(page, "lint-override-suggested-tier");

    await combo.fill("alu");
    await check("typing 'alu' suggests rtl/alu.v (aria-label = ws-relative path)", async () => {
      await expect(listbox.getByRole("option", { name: "rtl/alu.v", exact: true })).toBeVisible();
      await expect(listbox.getByRole("option", { name: "alu.v", exact: true })).toHaveCount(0);
    });
    await snap(page, "lint-override-typed-alu");

    // ↓ + Enter picks the highlighted suggestion (a bare Enter would commit
    // the typed text "alu" as a free-entry chip — that is by design).
    await combo.press("ArrowDown");
    await combo.press("Enter");
    await check("chip rtl/alu.v added", () =>
      expect(box.getByRole("button", { name: "Remove rtl/alu.v" })).toBeVisible()
    );
    await check("chips placeholder switches to 'type or pick + Enter'", () =>
      expect(combo).toHaveAttribute("placeholder", "type or pick + Enter")
    );
    const payloadText = await payloadOf(page).innerText();
    log("payload:", JSON.stringify(payloadText));
    results.lint_payload_alu = payloadText;
    await check('payload shows "files": ["rtl/alu.v"]', async () => {
      const flat = payloadText.replace(/\s+/g, "");
      expect(flat).toContain('"files":["rtl/alu.v"]');
    });
    await snap(page, "lint-override-alu-chip");
  });

  // ── 5. invoke: file-scoped lint, honest notes, honest verdicts ──────────
  await step(page, "5 invoke lint alu.v → notes; lint top.v alone → pass with note", async () => {
    await ensureSurfaceOpen(page);
    await selectRailCommand(page, "Lint");
    const surface = surfaceOf(page);
    const box = surface.getByTestId("command-surface-override-files");
    // Make the state explicit regardless of what step 4 left behind.
    if (!(await box.getByRole("button", { name: "Remove rtl/alu.v" }).count())) {
      if (await box.getByRole("button", { name: "Override…" }).count()) {
        await box.getByRole("button", { name: "Override…" }).click();
      }
      await pickOverride(page, surface.getByRole("combobox", { name: "Override files" }), "alu", "rtl/alu.v");
    }
    for (const stale of await box.getByRole("button", { name: /^Remove (?!rtl\/alu\.v$)/ }).all()) {
      await stale.click();
    }

    const { resp: resp1, sawElapsed } = await invokeAndWait(page, "/lint");
    log(
      sawElapsed
        ? `'Running — Ns' indicator observed: ${JSON.stringify(sawElapsed)}`
        : "'Running — Ns' indicator not caught (lint returned within the 4s probe — accepted)"
    );
    results.saw_running_indicator = Boolean(sawElapsed);
    await snap(page, "lint-alu-invoked");
    const body1 = await resp1.json();
    results.lint_alu_only = body1;
    log("lint(rtl/alu.v) →", JSON.stringify(body1).slice(0, 900));

    await check("lint request was file-scoped to rtl/alu.v", () =>
      expect(body1.files).toEqual(["rtl/alu.v"])
    );
    await check("alu.v alone passes (no unresolved modules in it)", () =>
      expect(body1.status).toBe("passed")
    );
    const warn1: string[] = body1.manifestWarnings ?? [];
    await check("manifestWarnings names the dropped manifest file rtl/top.v", () =>
      expect(warn1.join("\n")).toContain("rtl/top.v")
    );
    await check("inline result renders in the pane with the warning count", async () => {
      const pane = surface.getByText(/passed \(/).first();
      await expect(pane).toBeVisible({ timeout: 15_000 });
      await expect(surface.getByText(/manifest warning/)).toBeVisible();
    });
    // The note itself travels as a toast (5s TTL) — best effort, logged.
    const toast = page.getByRole("status").filter({ hasText: "Manifest warning" }).first();
    if (await toast.isVisible().catch(() => false)) {
      log("toast:", JSON.stringify(await toast.innerText()));
    } else {
      log("Manifest-warning toast not caught in time (5s TTL) — the response body above is the proof");
    }
    await snap(page, "lint-alu-result");

    // Now rtl/top.v ALONE: alu is instantiated but not in the file set. The
    // false-verdict fix: PASSED with a scope note naming alu, not FAILED.
    //
    // Engine = iverilog, deliberately. Run 1 showed that `auto` picks
    // verilator on staging, and run_linter passes `-I<dir of each file>` to
    // verilator, which ALSO searches -I dirs for unresolved modules — so a
    // "file-scoped" verilator lint of rtl/top.v silently elaborated
    // rtl/alu.v from the same directory: verdict passed, no unresolved
    // module, no scope note, and a drop note claiming alu.v "is not part of
    // this run" that was not true. iverilog gets no library flag, so it is
    // the engine that actually exercises the unresolved-module path.
    await box.getByRole("button", { name: "Remove rtl/alu.v" }).click();
    const combo = surface.getByRole("combobox", { name: "Override files" });
    await pickOverride(page, combo, "top.v", "rtl/top.v");
    await check("chip rtl/top.v added, alu.v gone", async () => {
      await expect(box.getByRole("button", { name: "Remove rtl/top.v" })).toBeVisible();
      await expect(box.getByRole("button", { name: "Remove rtl/alu.v" })).toHaveCount(0);
    });
    await surface.getByRole("button", { name: "iverilog", exact: true }).click();
    await check("payload carries engine iverilog", () =>
      expect(payloadOf(page)).toContainText('"iverilog"')
    );
    await snap(page, "lint-top-chip-iverilog");

    const { resp: resp2, sawElapsed: saw2 } = await invokeAndWait(page, "/lint");
    if (saw2) log(`'Running — Ns' indicator observed on the second lint: ${JSON.stringify(saw2)}`);
    const body2 = await resp2.json();
    results.lint_top_only = body2;
    log("lint(rtl/top.v, iverilog) →", JSON.stringify(body2).slice(0, 1200));
    await check("lint request was file-scoped to rtl/top.v", () =>
      expect(body2.files).toEqual(["rtl/top.v"])
    );
    await check("the engine that ran is iverilog", () => expect(body2.engine).toBe("iverilog"));
    const warn2: string[] = body2.manifestWarnings ?? [];
    await check("verdict is PASSED, not FAILED (alu is a scope note)", () =>
      expect(body2.status).toBe("passed")
    );
    await check("notes name the dropped rtl/alu.v", () =>
      expect(warn2.join("\n")).toContain("rtl/alu.v")
    );
    await check("notes carry the file-scoped note naming `alu` as unelaborated", () =>
      expect(warn2.join("\n")).toMatch(/File-scoped lint:.*\balu\b.*not elaborated/)
    );
    await check("no unresolved-module error survives in `errors`", () =>
      expect(JSON.stringify(body2.errors ?? [])).not.toMatch(/Unknown module type|Cannot find file containing module/)
    );
    await check("inline result says passed", () =>
      expect(surface.getByText(/^passed \(/).first()).toBeVisible({ timeout: 15_000 })
    );
    await snap(page, "lint-top-result");
  });

  // ── 6. Use manifest set → chips back, payload without files ──────────────
  await step(page, "6 use manifest set", async () => {
    await ensureSurfaceOpen(page);
    await selectRailCommand(page, "Lint");
    const surface = surfaceOf(page);
    const box = surface.getByTestId("command-surface-override-files");
    const useManifest = box.getByRole("button", { name: "Use manifest set" });
    if (!(await useManifest.count())) {
      // Step 5 didn't leave an override active — activate one so the
      // gesture under test actually has something to undo.
      await box.getByRole("button", { name: "Override…" }).click();
      await pickOverride(page, surface.getByRole("combobox", { name: "Override files" }), "alu", "rtl/alu.v");
    }
    await expect(useManifest).toBeVisible();
    await useManifest.click();
    await check("box collapsed to 'Supplied by manifest' with both chips", async () => {
      await expect(box).toContainText("Supplied by manifest");
      await expect(box).toContainText("rtl/alu.v");
      await expect(box).toContainText("rtl/top.v");
      await expect(box.getByRole("button", { name: "Override…" })).toBeVisible();
      await expect(surface.getByRole("combobox", { name: "Override files" })).toHaveCount(0);
    });
    await check("payload no longer has `files`", () =>
      expect(payloadOf(page)).not.toContainText('"files"')
    );
    await snap(page, "lint-use-manifest-set");
  });

  // ── 7. Simulate detail: Testbench (module) combo + real run ──────────────
  await step(page, "7 simulate: Testbench (module) combo + run", async () => {
    await ensureSurfaceOpen(page);
    await selectRailCommand(page, "Simulate");
    const surface = surfaceOf(page);
    const tb = surface.getByRole("combobox", { name: "Testbench (module)" });
    await check("'Testbench (module)' combo present", () => expect(tb).toBeVisible());
    await check("defaults to the manifest simTop top_tb", () => expect(tb).toHaveValue("top_tb"));
    await tb.click();
    const listbox = surface.getByRole("listbox", { name: "Testbench (module) suggestions" });
    await check("suggestion top_tb with subtitle tb/top_tb.v", async () => {
      await expect(listbox).toBeVisible();
      const opt = listbox.getByRole("option", { name: "top_tb", exact: true });
      await expect(opt).toBeVisible();
      await expect(opt).toContainText("tb/top_tb.v");
    });
    await snap(page, "sim-tb-combo");
    await tb.press("Escape"); // consumed by the combo: dropdown closes, Surface stays
    await check("Esc on the open dropdown did NOT close the Surface", () =>
      expect(surface).toBeVisible()
    );
    await check("sim override box for `files` shows rtl + tb set", async () => {
      const box = surface.getByTestId("command-surface-override-files");
      await expect(box).toContainText("rtl/alu.v");
      await expect(box).toContainText("rtl/top.v");
      await expect(box).toContainText("tb/top_tb.v");
    });

    const { resp, sawElapsed } = await invokeAndWait(page, "/simulate", 300_000);
    log(
      sawElapsed
        ? `'Running — Ns' indicator observed during sim: ${JSON.stringify(sawElapsed)}`
        : "'Running — Ns' indicator not caught during sim (returned within the 4s probe)"
    );
    const body = await resp.json();
    results.sim = body;
    log("simulate →", JSON.stringify(body).slice(0, 900));
    const run = body.run ?? {};
    log(`sim run ${run.id}: status=${run.status}`);
    await check("simulate returned a run with a terminal status", async () => {
      expect(typeof run.id).toBe("string");
      expect(["passed", "failed"]).toContain(run.status);
    });
    await check("inline result names the run and its verdict", () =>
      expect(surface.getByText(new RegExp(`${run.id} (passed|failed)`))).toBeVisible({ timeout: 15_000 })
    );
    if (run.status === "passed") {
      log("sim verdict: TEST PASSED (run.status = passed)");
    } else {
      log("sim verdict: FAILED — honest failure reported, not hidden:", JSON.stringify(run.failure ?? null));
    }
    // Sync command: never gated by the paid-run guard.
    await check("no re-arm block for a sync command", () =>
      expect(surface.getByTestId("command-surface-rearm")).toHaveCount(0)
    );
    await snap(page, "sim-result");
  });

  // ── 8. explorer context menu → Lint this file (file-scoped) ──────────────
  await step(page, "8 explorer 'Lint this file' on rtl/top.v", async () => {
    await closeSurface(page);
    const row = await explorerRow(page, "rtl/top.v");
    await row.click({ button: "right" });
    const item = page.getByRole("menuitem", { name: "Lint this file" });
    await check("context menu offers 'Lint this file' (no ⌘L badge)", async () => {
      await expect(item).toBeVisible();
      await expect(item).not.toContainText("⌘L");
    });
    await snap(page, "context-menu");
    const [resp] = await Promise.all([
      page.waitForResponse(
        (r) => r.url().includes("/lint") && r.request().method() === "POST",
        { timeout: 120_000 }
      ),
      item.click(),
    ]);
    const req = resp.request().postDataJSON() as { files?: string[]; engine?: string };
    const body = await resp.json();
    results.context_menu_lint = { request: req, response: body };
    log("context-menu lint request:", JSON.stringify(req), "→", JSON.stringify(body).slice(0, 900));
    await check("request scoped to the clicked file", () => expect(req.files).toEqual(["rtl/top.v"]));
    const notes8: string[] = body.manifestWarnings ?? [];
    await check("verdict PASSED (not FAILED)", () => expect(body.status).toBe("passed"));
    await check("drop note names the manifest file left out (rtl/alu.v)", () =>
      expect(notes8.join("\n")).toContain("rtl/alu.v")
    );
    // The context menu cannot choose an engine (engine "auto"). On staging
    // that is verilator, whose -I dirs resolve same-directory modules — so
    // `alu` may be elaborated after all and no scope note is produced. Both
    // outcomes are recorded; the engine-dependent one is a DISCREPANCY
    // (the drop note then overstates what was left out), not a pass.
    const scopeNote = /File-scoped lint:.*\balu\b/.test(notes8.join("\n"));
    log(`context-menu lint engine=${body.engine}; scope note naming alu present: ${scopeNote}`);
    if (!scopeNote) {
      if (body.engine === "verilator") {
        log(
          "DISCREPANCY: verilator elaborated `alu` via -I (same directory) — no scope note, yet the drop note says rtl/alu.v was not part of this run"
        );
        results.context_menu_discrepancy = "verilator -I resolved the dropped file; scope note absent";
      } else {
        throw new Error(`engine ${body.engine} produced no scope note naming alu: ${JSON.stringify(notes8)}`);
      }
    }
    await check("toast reports 'Lint passed'", () =>
      expect(page.getByRole("status").filter({ hasText: /Lint passed/ }).first()).toBeVisible({
        timeout: 10_000,
      })
    );
    const warnToast = page.getByRole("status").filter({ hasText: "Manifest warning" }).first();
    if (await warnToast.isVisible().catch(() => false)) {
      log("manifest-warning toast:", JSON.stringify(await warnToast.innerText()));
    } else {
      log("manifest-warning toast not caught (5s TTL) — response body is the proof");
    }
    await snap(page, "context-menu-lint-result");
  });

  // ── 9. Synthesize detail: override + facts, NOT dispatched ────────────────
  await step(page, "9 synthesize: verilogFiles override + facts (no dispatch)", async () => {
    await ensureSurfaceOpen(page);
    await selectRailCommand(page, "Synthesize");
    const surface = surfaceOf(page);
    const box = surface.getByTestId("command-surface-override-verilogFiles");
    await check("override box for verilogFiles present with the rtl set", async () => {
      await expect(box).toBeVisible();
      await expect(box).toContainText("rtl/alu.v");
      await expect(box).toContainText("rtl/top.v");
      await expect(box).not.toContainText("tb/top_tb.v");
    });
    const facts = surface.getByText("Supplied by manifest — not asked of the user").locator("..").locator("..");
    const factsText = (await facts.innerText()).replace(/\s+/g, " ");
    log("facts box text:", JSON.stringify(factsText));
    await check("facts box shows a 'top module' row", async () => {
      await expect(facts).toBeVisible();
      await expect(facts).toContainText(/top module/i);
    });
    // The fact must state what the manifest says (UI = viewer of the
    // manifest); whether the manifest's synthTop is the RIGHT module is step
    // 2's finding, not this box's.
    const shownTop = /top module\s+(\S+)/i.exec(factsText)?.[1] ?? "";
    log(`facts 'top module' = ${JSON.stringify(shownTop)}; server manifest synthTop = ${JSON.stringify(serverManifest?.synthTop)}`);
    await check("facts 'top module' equals the server manifest's synthTop", () => {
      expect(shownTop).toBe(serverManifest?.synthTop ?? "");
    });
    await check("plan R71 label casing ('Top module') vs rendered label", () => {
      const label = /top module/i.exec(factsText)?.[0];
      log(`  rendered label: ${JSON.stringify(label)} (plan R71 says "Top module"; commands.ts says "top module")`);
    });
    const dispatch = page.getByTestId("command-surface-invoke");
    await check("Dispatch job button present and armed (async core)", async () => {
      await expect(dispatch).toHaveText(/Dispatch job/);
      await expect(dispatch).toBeEnabled();
    });
    await check("no re-arm block / no dispatch note before any dispatch", async () => {
      await expect(surface.getByTestId("command-surface-rearm")).toHaveCount(0);
      await expect(surface.getByTestId("command-surface-dispatch-note")).toHaveCount(0);
    });
    await check("no path-index error / truncation notice (informational)", async () => {
      const err = surface.getByTestId("command-surface-pathindex-error");
      const trunc = surface.getByText(/Workspace file index truncated/);
      log(`  pathindex-error present: ${await err.count()}, truncation notice present: ${await trunc.count()}`);
    });
    // Deliberately NOT clicking Dispatch — a synthesis is a paid ORFS run.
    log("NOT DISPATCHED by design: synthesis is a paid ORFS run — screenshot only");
    await snap(page, "synth-detail-disarmed");
  });

  // ── 10. ⌘K palette: Lint modal = read-only facts, no override editor ─────
  await step(page, "10 palette Lint modal: read-only files fact, no override", async () => {
    await closeSurface(page);
    await openPalette(page);
    await snap(page, "palette-open");
    // Choosing Lint runs it directly (fast path); the gear opens its modal.
    await page.getByRole("button", { name: "Lint options" }).click();
    const dialog = page.getByRole("dialog").filter({ hasText: "Supplied by manifest" });
    await check("Lint modal opens with the 'Supplied by manifest' facts box", () =>
      expect(dialog).toBeVisible({ timeout: 15_000 })
    );
    await check("files shown as a read-only fact (rtl/alu.v, rtl/top.v)", async () => {
      await expect(dialog).toContainText("files:");
      await expect(dialog).toContainText("rtl/alu.v, rtl/top.v");
    });
    await check("no override editor in the modal", async () => {
      await expect(dialog.getByRole("button", { name: "Override…" })).toHaveCount(0);
      await expect(dialog.getByRole("combobox", { name: /Override/ })).toHaveCount(0);
      await expect(dialog.getByTestId("command-surface-override-files")).toHaveCount(0);
    });
    await check("footer says files & tops come from the manifest", () =>
      expect(dialog).toContainText("files & tops from manifest")
    );
    await snap(page, "palette-lint-modal");
    await page.keyboard.press("Escape");
  });

  fs.writeFileSync(`${ARTIFACTS}/surface-port-results.json`, JSON.stringify(results, null, 2));
  log("failed steps:", failures.length ? failures.join(" | ") : "none");
  expect(failures, `steps that failed: ${failures.join(", ")}`).toEqual([]);
});
