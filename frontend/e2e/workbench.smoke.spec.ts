import { test, expect, Route } from "@playwright/test";

/**
 * Tier-2 visual/E2E. Requires a browser:
 *   npx playwright install chrome   (apt Chrome — bundled chromium CDN is blocked)
 * Note: the file: protocol is blocked in this environment; always test against
 * an HTTP server (the Next dev server here, via webServer in the config).
 *
 * The full hardware flow needs a backend + iverilog; here we drive the real
 * frontend against a *stateful mock* of the action layer so the slice deliverable
 * — upload → lint → sim (fail) → waveform → fix → sim (pass) → synth → report —
 * is exercised end to end in the browser, screenshotting each stage.
 */

test("app loads (smoke)", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("body")).toBeVisible();
  await page.screenshot({ path: "e2e-artifacts/home.png", fullPage: true });
});

// ---- Stateful backend mock -------------------------------------------------

const MANIFEST = {
  ok: true,
  manifest: {
    sessionId: "demo",
    files: [
      { name: "alu.v", role: "rtl", path: "alu.v" },
      { name: "cpu_tb.v", role: "tb", path: "cpu_tb.v" },
      { name: "constraints.sdc", role: "sdc", path: "constraints.sdc" },
    ],
    synthTop: "cpu_top",
    simTop: "cpu_tb",
    clockPeriodNs: 10,
    platform: "sky130hd",
  },
};

function installMocks(page: import("@playwright/test").Page) {
  const state = { simCount: 0, runs: [] as any[] };

  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  return page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const m = route.request().method();

    if (p === "/api/sessions" && m === "GET")
      return json(route, [
        { id: "demo", name: "demo", model_name: "claude-sonnet-4-6", project_id: null, created_at: null, updated_at: null, total_tokens: 0, total_cost: 0 },
      ]);
    if (p.endsWith("/history")) return json(route, []);
    if (p.endsWith("/manifest") && m === "GET") return json(route, MANIFEST);
    if (p.endsWith("/manifest") && m === "PUT") return json(route, MANIFEST);
    if (p.endsWith("/files") && m === "POST") return json(route, { ...MANIFEST, uploaded: ["alu.v", "cpu_tb.v"] });

    if (p.endsWith("/runs") && m === "GET") return json(route, { ok: true, runs: state.runs });

    if (p.endsWith("/lint") && m === "POST")
      return json(route, {
        ok: true,
        status: "passed",
        warnings: [],
        errors: [],
        byFile: {},
        command: "iverilog -t null -g2012 alu.v",
        files: ["alu.v"],
      });

    if (p.endsWith("/simulate") && m === "POST") {
      state.simCount += 1;
      const fail = state.simCount === 1;
      const id = `sim_000${state.simCount}`;
      const run = {
        id,
        kind: "sim",
        status: fail ? "failed" : "passed",
        createdAt: new Date().toISOString(),
        top: "cpu_tb",
        pinned: false,
        mode: "rtl",
        vcdPath: `sim_runs/${id}/dump.vcd`,
        passMarkerFound: !fail,
        failure: fail ? { type: "test_failed", firstFailureLine: "t=240ns ERROR result=0xBB expected 0xAA", timeNs: 240 } : null,
        compileCommand: "iverilog -g2012 -o cpu_tb.out -f files.f",
        simCommand: "vvp cpu_tb.out",
        stdoutTail: fail ? "t=240ns ERROR" : "TEST PASSED",
      };
      state.runs = [run, ...state.runs];
      return json(route, { ok: true, run });
    }

    if (p.endsWith("/synthesize") && m === "POST") {
      const run = {
        id: "synth_0001",
        kind: "synth",
        status: "passed",
        createdAt: new Date().toISOString(),
        top: "cpu_top",
        pinned: false,
        platform: "sky130hd",
        reportAvailable: true,
        ppa: { areaUm2: 142.5, cells: 48, wnsNs: 0.85, tnsNs: 0, fmaxMhz: 120, powerMw: 1.2 },
      };
      state.runs = [run, ...state.runs];
      return json(route, { ok: true, jobId: "job_abc", runId: "synth_0001" });
    }
    if (p.includes("/jobs/") && m === "GET")
      return json(route, { ok: true, job: { status: "completed", current_stage: "finish" } });

    if (p.includes("/waveform/"))
      return json(route, {
        filename: "dump.vcd",
        endtime: 300,
        signals: [
          { name: "clk", full_name: "cpu_tb.clk", times: [0, 10, 20, 30], values: [0, 1, 0, 1] },
          { name: "result", full_name: "cpu_tb.result", times: [0, 240], values: [170, 187] },
        ],
      });

    if (p.endsWith("/report") && m === "GET")
      return json(route, { filename: "design_report.md", content: "# Report\n\n**WNS**: 0.85 ns (met)\n", run_id: "synth_0001" });

    if (p.endsWith("/code") && m === "GET")
      return json(route, [{ filename: "alu.v", content: "module alu; endmodule", language: "verilog" }]);
    if (p.endsWith("/files") && m === "GET") return json(route, []);
    if (p.endsWith("/spec")) return json(route, { detail: "No spec" }, 404);

    // default: empty lists / ok
    return json(route, []);
  });
}

test("workbench: shell renders the pipeline spine + rails", async ({ page }) => {
  await installMocks(page);
  await page.goto("/workbench");

  await expect(page.getByTestId("wb-brand")).toBeVisible();
  // Pipeline spine doubles as run actions.
  await expect(page.locator('[data-stage="sim"]')).toBeVisible();
  await expect(page.locator('[data-stage="synth"]')).toBeVisible();
  // Left rail: manifest file tree with role badges (TB/SDC are unique to the
  // file tree; "RTL" also names a pipeline stage, so assert the files instead).
  await expect(page.getByText("alu.v")).toBeVisible();
  await expect(page.getByText("cpu_tb.v")).toBeVisible();
  await expect(page.getByText("TB", { exact: true })).toBeVisible();
  await expect(page.getByText("SDC", { exact: true })).toBeVisible();
  // Agent rail shares everything.
  await expect(page.getByText("AI Assistant")).toBeVisible();
  await page.screenshot({ path: "e2e-artifacts/workbench-shell.png", fullPage: true });
});

test("workbench: upload → lint → sim (fail) → waveform → fix → re-run (pass) → synth → report", async ({ page }) => {
  await installMocks(page);
  await page.goto("/workbench");
  await expect(page.locator('[data-stage="sim"]')).toBeVisible();
  // Wait for the session + manifest to settle before acting (mount load).
  await expect(page.getByText("alu.v")).toBeVisible();

  // upload RTL → server auto-tags roles (drive the hidden file input)
  await page.setInputFiles('input[aria-label="Upload design files"]', [
    { name: "alu.v", mimeType: "text/plain", buffer: Buffer.from("module alu; endmodule") },
    { name: "cpu_tb.v", mimeType: "text/plain", buffer: Buffer.from("module cpu_tb; endmodule") },
  ]);
  await expect(page.getByText("cpu_tb.v")).toBeVisible();
  await page.screenshot({ path: "e2e-artifacts/wb-1-upload.png", fullPage: true });

  // Run Lint → console shows the exact command
  await page.getByTitle("Run Lint").click();
  await expect(page.getByText(/Lint passed/i)).toBeVisible();
  await page.screenshot({ path: "e2e-artifacts/wb-2-lint.png", fullPage: true });

  // Run Sim → run timeline gets sim_0001 (fail), banner + waveform appear
  await page.getByTitle("Run Sim").click();
  await expect(page.getByTestId("viewing-banner")).toBeVisible();
  await expect(page.locator('[data-run-id="sim_0001"]')).toBeVisible();
  await page.screenshot({ path: "e2e-artifacts/wb-3-sim-fail.png", fullPage: true });

  // "fix" → re-run sim → pass (sim_0002)
  await page.getByTitle("Run Sim").click();
  await expect(page.locator('[data-run-id="sim_0002"]')).toBeVisible();
  await page.screenshot({ path: "e2e-artifacts/wb-4-sim-pass.png", fullPage: true });

  // Run Synth → poll → completed → report shows timing slack (met)
  await page.getByTitle("Run Synth").click();
  await expect(page.locator('[data-run-id="synth_0001"]')).toBeVisible({ timeout: 15000 });
  await expect(page.getByText(/met/i).first()).toBeVisible({ timeout: 15000 });
  await page.screenshot({ path: "e2e-artifacts/wb-5-report.png", fullPage: true });
});
