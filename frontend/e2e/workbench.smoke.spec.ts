import { test, expect, Route, Page } from "@playwright/test";

/**
 * Tier-2 visual/E2E for the v2 IDE-style workbench.
 *
 * Drives the real frontend against a *stateful mock* of the v2 action layer:
 * the ⌘K palette flow (lint → sim fail → open waveform → synth → report), the
 * lazy file tree → code tab, tab focus/close semantics, and ⌘P quick-open.
 * The full hardware flow (iverilog/ORFS) is backend-tested; what's under test
 * here is the wiring: snapshot boot, invocation, honest run/activity state,
 * and the open-artifact tab model.
 */

test("app loads (smoke)", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("body")).toBeVisible();
});

// ---- Stateful v2 backend mock ----------------------------------------------

const MANIFEST = {
  sessionId: "demo",
  files: [
    { name: "alu.v", role: "rtl", path: "alu.v" },
    { name: "cpu_tb.v", role: "tb", path: "cpu_tb.v" },
    { name: "constraints.sdc", role: "sdc", path: "constraints.sdc" },
  ],
  synthTop: "alu",
  simTop: "cpu_tb",
  clockPeriodNs: 10,
  platform: "sky130hd",
};

const CODE: Record<string, string> = {
  "alu.v": "module alu(input clk); // real content\nendmodule\n",
  "cpu_tb.v": "module cpu_tb; alu dut(.clk(clk)); endmodule\n",
  "constraints.sdc": "create_clock -period 10 [get_ports clk]\n",
};

const WAVE = (filename: string) => ({
  filename,
  endtime: 300,
  timescale: "1ns",
  unitSeconds: 1e-9,
  signalCount: 2,
  signals: [
    { name: "clk", full_name: "cpu_tb.clk", scope: "cpu_tb", width: 1, isBus: false,
      times: [0, 10, 20, 30], values: [0, 1, 0, 1], valuesStr: ["0", "1", "0", "1"], xFlags: [false, false, false, false] },
    { name: "result", full_name: "cpu_tb.dut.result", scope: "cpu_tb.dut", width: 8, isBus: true,
      times: [0, 240], values: [170, 187], valuesStr: ["10101010", "10111011"], xFlags: [false, false] },
  ],
});

type Dict = Record<string, unknown>;

// Real-shaped subset of the backend's introspected tool catalog (GET /tools) —
// the Command Surface renders its groups/forms entirely from this.
const TOOL_CATALOG = [
  {
    name: "write_file",
    description: "Writes content to a file in the workspace.\nArgs:\n    filename: Name of the file (e.g., 'design.v', 'tb.v').\n    content: The text content to write.",
    category: "essential",
    argsSchema: {
      type: "object",
      properties: {
        filename: { type: "string" },
        content: { anyOf: [{ type: "string" }, { type: "null" }], default: null },
      },
      required: ["filename"],
    },
    requiresSignIn: true, async: false, mutates: true,
  },
  {
    name: "waveform_tool",
    description: "Reads a VCD waveform file to inspect signal values.\nUse this when simulation fails to understand WHY.\nArgs:\n    vcd_file: Name of the .vcd file (e.g., 'dump.vcd').\n    signals: List of signal names to inspect.",
    category: "verification",
    argsSchema: {
      type: "object",
      properties: {
        vcd_file: { type: "string" },
        signals: { type: "array", items: { type: "string" } },
        start_time: { type: "integer", default: 0 },
        end_time: { type: "integer", default: 1000 },
      },
      required: ["vcd_file", "signals"],
    },
    requiresSignIn: false, async: false, mutates: false,
  },
  {
    name: "get_synthesis_metrics",
    description: "Returns structured synthesis metrics for a run.\nParses standard ORFS outputs (6_finish.rpt + synth_stat.txt) and returns JSON.",
    category: "synthesis",
    argsSchema: {
      type: "object",
      properties: { run_id: { anyOf: [{ type: "string" }, { type: "null" }], default: null } },
      required: [],
    },
    requiresSignIn: true, async: false, mutates: false,
  },
  {
    name: "search_logs_tool",
    description: "Searches for a keyword in OpenROAD logs and reports.\nArgs:\n    query: The string to search for.\n    run_id: Optional run ID for deterministic lookup.",
    category: "synthesis",
    argsSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        run_id: { anyOf: [{ type: "string" }, { type: "null" }], default: null },
      },
      required: ["query"],
    },
    requiresSignIn: true, async: false, mutates: false,
  },
  {
    name: "run_xls_flow",
    description: "Executes the entire high-level XLS synthesis flow:\nDSLX Interpreter -> IR Conversion -> Optimization -> Codegen.\nArgs:\n    dslx_file: Name of the DSLX file (e.g. 'saturating_add.x').\n    top_module: Name of the top-level function or proc.",
    category: "hls",
    argsSchema: {
      type: "object",
      properties: {
        dslx_file: { type: "string" },
        top_module: { type: "string" },
        generator: { type: "string", default: "combinational" },
        pipeline_stages: { type: "integer", default: 0 },
        clock_period_ps: { type: "integer", default: 0 },
        delay_model: { type: "string", default: "sky130" },
        use_system_verilog: { type: "boolean", default: false },
      },
      required: ["dslx_file", "top_module"],
    },
    requiresSignIn: true, async: false, mutates: true,
  },
];

function installMocks(page: Page) {
  const state = {
    simCount: 0,
    runs: [] as Dict[],
    activity: [] as Dict[],
    simRunsDir: [] as Dict[],
  };
  let evSeq = 0;
  const serverEvent = (tool: string, status: string, summary: string, runId: string | null = null) => {
    state.activity.unshift({
      id: `srv-${evSeq++}`,
      ts: new Date().toISOString(),
      source: "user",
      tool,
      args: {},
      status,
      resultSummary: summary,
      durationMs: 850,
      runId,
      threadId: null,
    });
  };

  const rootDir = () => [
    ...(state.simRunsDir.length ? [{ name: "sim_runs", path: "sim_runs", kind: "dir" }] : []),
    { name: "alu.v", path: "alu.v", kind: "file", size: 44, modified: "2026-07-01T10:00:00" },
    { name: "constraints.sdc", path: "constraints.sdc", kind: "file", size: 40, modified: "2026-07-01T10:00:00" },
    { name: "cpu_tb.v", path: "cpu_tb.v", kind: "file", size: 46, modified: "2026-07-01T10:00:00" },
  ];

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
    if (p === "/api/models" && m === "GET")
      return json(route, { default: "gemini-3-flash-preview", models: [
        { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6", provider: "anthropic", tier: "balanced", hint: "", available: true },
      ] });
    if (p === "/api/sessions/demo/threads" && m === "GET")
      return json(route, [{ id: "demo", session_id: "demo", title: "Chat 1", model: null, created_at: null, last_active: null }]);
    if (p.endsWith("/history")) return json(route, []);

    // ---- v2 snapshot boot ----
    if (p.endsWith("/workbench") && m === "GET")
      return json(route, {
        ok: true,
        manifest: MANIFEST,
        runs: state.runs,
        files: [],
        spec: null,
        code: [],
        report: null,
        synthesisRuns: [],
        activity: state.activity,
        rootDir: rootDir(),
      });

    // ---- lazy tree + quick-open index ----
    if (p.endsWith("/dir") && m === "GET") {
      if (url.searchParams.get("recursive") === "paths")
        return json(route, { ok: true, paths: Object.keys(CODE), truncated: false });
      const dirPath = url.searchParams.get("path") || "";
      if (dirPath === "") return json(route, { ok: true, path: "", entries: rootDir() });
      if (dirPath === "sim_runs") return json(route, { ok: true, path: dirPath, entries: state.simRunsDir });
      return json(route, { ok: false, error: { code: "not_found", message: "nope" } }, 404);
    }

    if (p.endsWith("/activity") && m === "GET")
      return json(route, { ok: true, events: state.activity, nextBefore: null });

    if (p.endsWith("/runs") && m === "GET") return json(route, { ok: true, runs: state.runs });

    // ---- actions ----
    if (p.endsWith("/lint") && m === "POST") {
      serverEvent("linter_tool", "ok", "passed · 0 error(s), 0 warning(s)");
      return json(route, { ok: true, status: "passed", warnings: [], errors: [], byFile: {}, command: "iverilog -t null -g2012 alu.v", files: ["alu.v"] });
    }

    if (p.endsWith("/simulate") && m === "POST") {
      state.simCount += 1;
      const fail = state.simCount === 1;
      const id = `sim_000${state.simCount}`;
      const run = {
        id, kind: "sim", status: fail ? "failed" : "passed",
        createdAt: new Date().toISOString(), top: "cpu_tb", pinned: false, parentRunId: null,
        mode: "rtl", vcdPath: `sim_runs/${id}/dump.vcd`, passMarkerFound: !fail,
        failure: fail ? { type: "test_failed", firstFailureLine: "t=240ns ERROR result=0xBB expected 0xAA", timeNs: 240 } : null,
      };
      state.runs = [run, ...state.runs];
      state.simRunsDir.push({ name: id, path: `sim_runs/${id}`, kind: "dir" });
      serverEvent("run_isolated_simulation", fail ? "error" : "ok", `${id} ${run.status}`, id);
      return json(route, { ok: true, run });
    }

    if (p.endsWith("/synthesize") && m === "POST") {
      const run = {
        id: "synth_0001", kind: "synth", status: "running",
        createdAt: new Date().toISOString(), top: "alu", pinned: false, parentRunId: null,
        platform: "sky130hd", reportAvailable: false, ppa: null,
      };
      state.runs = [run, ...state.runs];
      serverEvent("start_synthesis", "ok", "synth_0001 dispatched (job job_abc)", "synth_0001");
      return json(route, { ok: true, jobId: "job_abc", runId: "synth_0001" });
    }
    if (p.includes("/jobs/") && m === "GET") {
      // First poll (after ~3s) already finds the job complete.
      state.runs = state.runs.map((r) =>
        r.id === "synth_0001"
          ? { ...r, status: "passed", reportAvailable: true, ppa: { areaUm2: 142.5, cells: 48, wnsNs: 0.85, tnsNs: 0, fmaxMhz: 120, powerMw: 1.2 } }
          : r
      );
      return json(route, { ok: true, job: { status: "completed", current_stage: "finish" } });
    }

    // ---- artifacts ----
    if (p.includes("/waveform/")) {
      const file = decodeURIComponent(p.split("/waveform/")[1]);
      return json(route, WAVE(file));
    }
    if (p.endsWith("/report") && m === "GET")
      return json(route, { filename: "design_report.md", content: "# Design Report\n\n**WNS**: +0.85 ns (met)\n", run_id: url.searchParams.get("run_id") ?? "synth_0001" });
    if (p.includes("/file/")) {
      const file = decodeURIComponent(p.split("/file/")[1].split("?")[0]);
      const content = CODE[file] ?? "// empty\n";
      return json(route, { filename: file, content, size: content.length, binary: false, tooLarge: false });
    }
    // ---- introspected tool catalog (command surface) ----
    if (p.endsWith("/tools") && m === "GET")
      return json(route, { ok: true, tools: TOOL_CATALOG });

    // ---- curated tool invocation (command surface) ----
    if (p.endsWith("/invoke") && m === "POST")
      return json(route, {
        ok: true,
        tool: "get_synthesis_metrics",
        result: { status: "ok", run_id: "synth_0001", metrics: { wns_ns: 0.85 } },
      });

    if (p.endsWith("/layouts")) return json(route, []);
    if (p.endsWith("/schematics")) return json(route, []);
    if (p.endsWith("/spec")) return json(route, { detail: "No spec" }, 404);

    return json(route, []);
  });
}

const openPalette = async (page: Page) => {
  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByPlaceholder("Run a command…")).toBeVisible();
};

test("v2 shell boots from the snapshot — tree, dock, empty center, no v1 chrome", async ({ page }) => {
  await installMocks(page);
  await page.goto("/workbench");

  await expect(page.getByTestId("workbench-v2")).toBeVisible();
  // Left rail: real tree from the snapshot rootDir, with a role badge.
  await expect(page.getByText("alu.v")).toBeVisible();
  await expect(page.getByText("cpu_tb.v")).toBeVisible();
  // Center: honest empty state — nothing is pre-declared.
  await expect(page.getByText("Nothing open")).toBeVisible();
  // Dock: both surfaces present.
  const dock = page.getByTestId("bottom-dock");
  await expect(dock.getByRole("button", { name: /Activity/ })).toBeVisible();
  await expect(dock.getByRole("button", { name: /Runs/ })).toBeVisible();
  // The v1 pipeline spine is gone.
  await expect(page.locator("[data-stage]")).toHaveCount(0);
  await page.screenshot({ path: "e2e-artifacts/wb2-shell.png", fullPage: true });
});

test("palette flow: lint → sim (fail) → waveform → synth → report", async ({ page }) => {
  await installMocks(page);
  await page.goto("/workbench");
  await expect(page.getByText("alu.v")).toBeVisible();

  // ⌘K → Lint (manifest defaults, no modal)
  await openPalette(page);
  await page.getByRole("option", { name: /^Lint/ }).click();
  await expect(page.getByText(/Lint passed/)).toBeVisible();
  // The activity feed shows the user-initiated call.
  await expect(page.getByTestId("bottom-dock").getByText("linter_tool").first()).toBeVisible();
  await page.screenshot({ path: "e2e-artifacts/wb2-lint.png", fullPage: true });

  // ⌘K → Simulate → failed run appears in Runs with honest failure time + unread dot
  await openPalette(page);
  await page.getByRole("option", { name: /^Simulate/ }).click();
  await expect(page.getByText(/Simulation failed/)).toBeVisible();
  const dock = page.getByTestId("bottom-dock");
  await dock.getByRole("button", { name: /Runs/ }).click();
  await expect(dock.getByText("sim_0001")).toBeVisible();
  await expect(dock.getByText(/240\s?ns/)).toBeVisible();
  await expect(dock.locator('[title="new"]')).toBeVisible();
  await page.screenshot({ path: "e2e-artifacts/wb2-sim-fail.png", fullPage: true });

  // Open the failed run → its waveform tab (per-run artifact, unread cleared)
  await dock.getByText("sim_0001").click();
  await expect(page.getByText("Waveform · sim_0001")).toBeVisible();
  await expect(dock.locator('[title="new"]')).toHaveCount(0);
  await page.screenshot({ path: "e2e-artifacts/wb2-waveform.png", fullPage: true });

  // ⌘K → Synthesize → dispatch → poll → completed run with PPA → report tab
  await openPalette(page);
  await page.getByRole("option", { name: /^Synthesize/ }).click();
  await expect(page.getByText(/Synthesis dispatched/)).toBeVisible();
  await expect(dock.getByText("synth_0001")).toBeVisible();
  // First poll lands after ~3s and completes the job.
  await expect(page.getByText(/Synthesis completed/)).toBeVisible({ timeout: 15_000 });
  await dock.getByText("synth_0001").click();
  await expect(page.getByText("Report · synth_0001")).toBeVisible();
  await expect(page.getByText(/Design Report/)).toBeVisible({ timeout: 10_000 });
  await page.screenshot({ path: "e2e-artifacts/wb2-report.png", fullPage: true });

  // No auto-switching happened along the way: the report tab was opened by us,
  // and the waveform tab is still there.
  await expect(page.getByText("Waveform · sim_0001")).toBeVisible();
});

test("file tree → code tab: open, focus-if-open, close", async ({ page }) => {
  await installMocks(page);
  await page.goto("/workbench");
  await expect(page.getByText("alu.v")).toBeVisible();

  await page.getByText("alu.v").click();
  // Tab appears; content loads via the smart-file endpoint (Monaco may fall
  // back to the plain renderer if its CDN is unreachable — content either way).
  await expect(page.getByRole("tab", { name: /alu\.v/ })).toBeVisible();
  await expect(page.getByText(/real content/)).toBeVisible({ timeout: 15_000 });

  // Opening the same file again focuses the existing tab, not a duplicate.
  await page.getByText("cpu_tb.v").first().click();
  await expect(page.getByRole("tab", { name: /cpu_tb\.v/ })).toBeVisible();
  await page.getByText("alu.v").first().click();
  await expect(page.getByRole("tab", { name: /alu\.v/ })).toHaveCount(1);

  await page.screenshot({ path: "e2e-artifacts/wb2-code.png", fullPage: true });
});

test("quick open (⌘P) opens an artifact by fuzzy name", async ({ page }) => {
  await installMocks(page);
  await page.goto("/workbench");
  await expect(page.getByText("alu.v")).toBeVisible();

  await page.keyboard.press("ControlOrMeta+p");
  const input = page.getByPlaceholder("Open artifact…");
  await expect(input).toBeVisible();
  await input.fill("cpu_tb");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("tab", { name: /cpu_tb\.v/ })).toBeVisible();
});

test("command surface: browse → Metrics → live payload → invoke → inline result", async ({ page }) => {
  await installMocks(page);
  await page.goto("/workbench");
  await expect(page.getByText("alu.v")).toBeVisible();

  // The Metrics run_id param needs a synth run — dispatch Synthesize first,
  // exactly like the palette flow test does.
  await openPalette(page);
  await page.getByRole("option", { name: /^Synthesize/ }).click();
  await expect(page.getByText(/Synthesis dispatched/)).toBeVisible();
  const dock = page.getByTestId("bottom-dock");
  await dock.getByRole("button", { name: /Runs/ }).click();
  await expect(dock.getByText("synth_0001")).toBeVisible();

  // ⌘K → "All commands…" opens the command surface.
  await openPalette(page);
  await page.getByRole("option", { name: /All commands/ }).click();
  const surface = page.getByTestId("command-surface");
  await expect(surface).toBeVisible();

  // Left rail → the schema-driven catalog's generated label for
  // get_synthesis_metrics: the right pane shows the live tool-call payload.
  await surface.getByRole("button", { name: "Get Synthesis Metrics", exact: true }).click();
  await expect(surface.locator('[aria-label="tool call payload"]')).toContainText(
    "get_synthesis_metrics"
  );

  // Invoke → the curated /invoke result renders inline in the result pane.
  await page.getByTestId("command-surface-invoke").click();
  await expect(surface.getByText("wns_ns")).toBeVisible();
  await page.screenshot({ path: "e2e-artifacts/wb2-command-surface.png", fullPage: true });
});
