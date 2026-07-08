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

// ---- Launcher (S2) ----------------------------------------------------------
// `/` is the Launcher: recency-first cards (name · thread count · updated ·
// group tag), search, the lazy thread drawer (manifest + threads fetched only
// for the selected card) and the create modal → /w/{id}.

const LAUNCHER_SESSIONS = [
  {
    id: "sync_fifo", name: "sync_fifo", model_name: "claude-sonnet-4-6", project_id: "g1",
    created_at: "2026-07-01T10:00:00Z", updated_at: "2026-07-03T09:00:00Z",
    total_tokens: 48213, total_cost: 0.82, thread_count: 3,
  },
  {
    id: "uart_tx", name: "uart_tx", model_name: "gemini-3-flash-preview", project_id: null,
    created_at: "2026-06-30T10:00:00Z", updated_at: "2026-07-02T10:00:00Z",
    total_tokens: 22100, total_cost: 0.31, thread_count: 2,
  },
];

const NEW_SESSION = {
  id: "new_block", name: "new_block", model_name: "gemini-3-flash-preview", project_id: null,
  created_at: "2026-07-03T10:00:00Z", updated_at: "2026-07-03T10:00:00Z",
  total_tokens: 0, total_cost: 0, thread_count: 1,
};

function installLauncherMocks(page: Page) {
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  return page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const m = route.request().method();

    if (p === "/api/sessions" && m === "GET") return json(route, LAUNCHER_SESSIONS);
    if (p === "/api/sessions" && m === "POST") return json(route, NEW_SESSION);
    if (p === "/api/projects" && m === "GET")
      return json(route, [{ id: "g1", name: "asu_hackathon", created_at: null }]);
    if (p === "/api/models" && m === "GET")
      return json(route, {
        default: "gemini-3-flash-preview",
        models: [
          { id: "gemini-3-flash-preview", label: "Gemini 3 Flash", provider: "google", tier: "fast", hint: "", available: true },
        ],
      });

    // Drawer hydration (lazy, selected session only): threads + manifest.
    if (p === "/api/sessions/sync_fifo/threads" && m === "GET")
      return json(route, [
        { id: "t1", session_id: "sync_fifo", title: "FIFO signoff", model: null, created_at: "2026-07-01T10:00:00Z", last_active: "2026-07-03T09:00:00Z" },
        { id: "t2", session_id: "sync_fifo", title: "Debug overflow assert", model: null, created_at: "2026-07-01T11:00:00Z", last_active: "2026-07-03T08:30:00Z" },
        { id: "t3", session_id: "sync_fifo", title: "Timing exploration", model: null, created_at: "2026-07-01T12:00:00Z", last_active: "2026-07-02T18:00:00Z" },
      ]);
    if (p.endsWith("/threads") && m === "GET") return json(route, []);
    if (p.endsWith("/threads") && m === "POST")
      return json(route, { id: "t-new", session_id: "sync_fifo", title: null, model: null, created_at: null, last_active: null });
    if (p.endsWith("/manifest") && m === "GET")
      return json(route, {
        ok: true,
        manifest: {
          sessionId: "sync_fifo",
          files: [
            { name: "sync_fifo.v", role: "rtl", path: "sync_fifo.v" },
            { name: "fifo_mem.v", role: "rtl", path: "fifo_mem.v" },
            { name: "spec.yaml", role: "spec", path: "spec.yaml" },
            { name: "constraints.sdc", role: "sdc", path: "constraints.sdc" },
          ],
          synthTop: "sync_fifo", simTop: null, clockPeriodNs: 10, platform: "sky130hd",
          testbenches: [], ignore: [],
        },
      });

    // Post-create boot of /w/new_block (only the shape matters here).
    if (p === "/api/sessions/new_block" && m === "GET") return json(route, NEW_SESSION);
    if (p.endsWith("/workbench") && m === "GET")
      return json(route, { ok: true, manifest: null, runs: [], files: [], spec: null, code: [], report: null, synthesisRuns: [] });
    if (p.endsWith("/history")) return json(route, []);

    return json(route, []);
  });
}

test("launcher boot: cards render, search filters, drawer hydrates, modal opens", async ({ page }) => {
  await installLauncherMocks(page);
  await page.goto("/");

  // Cards lead with recency truth: mono name + thread count (no run verdicts,
  // no file chips at this level — revision 1).
  const fifo = page.getByTestId("session-card-sync_fifo");
  const uart = page.getByTestId("session-card-uart_tx");
  await expect(fifo).toBeVisible();
  await expect(fifo.getByTitle("3 chats")).toBeVisible();
  await expect(uart.getByTitle("2 chats")).toBeVisible();
  // Recent view shows the group tag.
  await expect(fifo.getByText("asu_hackathon")).toBeVisible();

  // Search filters by name.
  const search = page.getByPlaceholder("Search workspaces…");
  await search.fill("uart");
  await expect(fifo).toHaveCount(0);
  await expect(uart).toBeVisible();
  await search.fill("");
  await expect(fifo).toBeVisible();

  // Card click → drawer with the ONE lazy hydration: manifest (file count +
  // chips) and the chats list.
  await fifo.click();
  const drawer = page.getByTestId("thread-drawer");
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("4 files")).toBeVisible();
  await expect(drawer.getByText("3 chats")).toBeVisible();
  await expect(drawer.getByText("sync_fifo.v")).toBeVisible(); // file chip
  await expect(drawer.getByText("+1")).toBeVisible(); // 4 files → 3 chips + overflow
  await expect(drawer.getByText("FIFO signoff")).toBeVisible();
  await expect(drawer.getByRole("button", { name: /Open in IDE/ })).toBeVisible();
  await page.screenshot({ path: "e2e-artifacts/launcher-drawer.png", fullPage: true });

  // "New session" opens the create modal with the live slug preview.
  await page.getByRole("button", { name: "New session" }).click();
  await expect(page.getByPlaceholder("Workspace name — e.g. sync_fifo")).toBeVisible();
  await expect(page.getByText("untitled")).toBeVisible(); // workspace/untitled/ preview
});

test("launcher create flow: modal → POST /api/sessions → lands on /w/{id}", async ({ page }) => {
  await installLauncherMocks(page);
  await page.goto("/");
  await expect(page.getByTestId("session-card-sync_fifo")).toBeVisible();

  await page.getByRole("button", { name: "New session" }).click();
  await page.getByPlaceholder("Workspace name — e.g. sync_fifo").fill("New Block");
  // Live slug preview follows the name.
  await expect(page.getByText("new_block")).toBeVisible();

  const [req] = await Promise.all([
    page.waitForRequest((r) => r.url().includes("/api/sessions") && r.method() === "POST"),
    page.getByRole("button", { name: /Create session/ }).click(),
  ]);
  expect(req.postDataJSON()).toMatchObject({ name: "new_block" });

  await page.waitForURL((u) => u.pathname === "/w/new_block");
  expect(new URL(page.url()).pathname).toBe("/w/new_block");
});

// S1: /workbench is a redirect shim. With no lastSessionId persisted (fresh
// browser context) it must land on `/` — never a half-booted workbench.
test("legacy /workbench redirects to / when no session is known", async ({ page }) => {
  await installMocks(page);
  await page.goto("/workbench");
  await page.waitForURL((u) => u.pathname === "/");
  expect(new URL(page.url()).pathname).toBe("/");
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
  testbenches: [{ file: "cpu_tb.v", module: "cpu_tb" }],
  ignore: [],
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

  // Optional JSON request body (POST /lint, /simulate now carry one).
  const bodyOf = (route: Route): Dict => {
    try {
      return (route.request().postDataJSON() as Dict) ?? {};
    } catch {
      return {};
    }
  };

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
      // Body is optional ({ engine } when present); auto resolves server-side.
      const requested = String(bodyOf(route).engine ?? "auto");
      const engine = requested === "auto" ? "iverilog" : requested;
      const warnings = [
        { file: "alu.v", line: 1, severity: "warning", message: "operator width mismatch", code: "WIDTH" },
      ];
      serverEvent("linter_tool", "ok", `passed (${engine}) · 0 error(s), 1 warning(s)`);
      return json(route, {
        ok: true, status: "passed", engine,
        warnings, errors: [], byFile: { "alu.v": warnings },
        command: `${engine} alu.v`, files: ["alu.v"],
      });
    }

    if (p.endsWith("/simulate") && m === "POST") {
      state.simCount += 1;
      const fail = state.simCount === 1;
      const id = `sim_000${state.simCount}`;
      // Echo the chosen testbench back as the run's top (backend behavior).
      const top = String(bodyOf(route).simTop ?? "") || "cpu_tb";
      const run = {
        id, kind: "sim", status: fail ? "failed" : "passed",
        createdAt: new Date().toISOString(), top, pinned: false, parentRunId: null,
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
      serverEvent("start_synthesis", "ok", "synth_0001 dispatched", "synth_0001");
      // Dispatch-only contract: { runId, pollAfterSec } — no jobId.
      return json(route, { ok: true, runId: "synth_0001", pollAfterSec: 2 });
    }
    // Self-healing run status (rich job shape). The UI never calls this on its
    // own — it exists for actor-style reads; the user-gesture Refresh goes
    // through /invoke get_synthesis_status below.
    const synthStatusJob = (status: string) => ({
      run_id: "synth_0001",
      status,
      stage: status === "completed" ? "finish" : "synthesis",
      current_stage: "finish",
      stages: {},
      stage_history: [
        { stage: "synth", status: "completed", ended_at: new Date().toISOString() },
        { stage: "finish", status, ended_at: status === "completed" ? new Date().toISOString() : null },
      ],
      dispatched_at: new Date().toISOString(),
      timeout_sec: 1800,
      top_module: "alu",
      elapsed_sec: 42,
      last_log_lines: ["Finished 6_report"],
      artifacts_found: status === "completed",
      summary_metrics: { wns_ns: 0.85 },
      auto_checks: {},
      check_notes: "",
      next_action: null,
      poll_after_sec: 5,
      backend: "local_docker",
      remote: false,
      execution_label: "local",
    });
    const completeSynthRun = () => {
      state.runs = state.runs.map((r) =>
        r.id === "synth_0001"
          ? { ...r, status: "passed", reportAvailable: true, ppa: { areaUm2: 142.5, cells: 48, wnsNs: 0.85, tnsNs: 0, fmaxMhz: 120, powerMw: 1.2 } }
          : r
      );
    };
    if (/\/runs\/[^/]+\/status$/.test(p) && m === "GET") {
      completeSynthRun();
      return json(route, { ok: true, job: synthStatusJob("completed") });
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

    // ---- curated tool invocation (command surface + run Refresh gesture) ----
    if (p.endsWith("/invoke") && m === "POST") {
      const body = bodyOf(route);
      if (body.tool === "get_synthesis_status") {
        // The user-gesture Refresh: the tool's status read reconciles the run
        // to completed and is itself logged as a source-ui activity event.
        completeSynthRun();
        serverEvent("get_synthesis_status", "ok", "synth_0001 completed", "synth_0001");
        return json(route, {
          ok: true,
          tool: "get_synthesis_status",
          // /invoke returns the tool's raw result — a JSON STRING, like the
          // real registry does; the frontend must parse it defensively.
          result: JSON.stringify(synthStatusJob("completed")),
        });
      }
      return json(route, {
        ok: true,
        tool: "get_synthesis_metrics",
        result: { status: "ok", run_id: "synth_0001", metrics: { wns_ns: 0.85 } },
      });
    }

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
  await page.goto("/w/demo");

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
  await page.goto("/w/demo");
  await expect(page.getByText("alu.v")).toBeVisible();

  // ⌘K → Lint (manifest defaults, no modal). The toast names the engine the
  // backend resolved (auto → iverilog in the mock).
  await openPalette(page);
  await page.getByRole("option", { name: /^Lint/ }).click();
  await expect(page.getByText(/Lint passed \(iverilog\)/)).toBeVisible();
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
  // Anchor on the status chip — the run-reason line also mentions 240ns, so a
  // bare /240ns/ is ambiguous under strict mode.
  await expect(dock.getByText(/failed @ 240\s?ns/)).toBeVisible();
  await expect(dock.locator('[title="new"]')).toBeVisible();
  await page.screenshot({ path: "e2e-artifacts/wb2-sim-fail.png", fullPage: true });

  // Open the failed run → its waveform tab (per-run artifact, unread cleared)
  await dock.getByText("sim_0001").click();
  await expect(page.getByText("Waveform · sim_0001")).toBeVisible();
  await expect(dock.locator('[title="new"]')).toHaveCount(0);
  await page.screenshot({ path: "e2e-artifacts/wb2-waveform.png", fullPage: true });

  // ⌘K → Synthesize → DISPATCH-ONLY: the running row appears and the UI does
  // NOT poll. The user-gesture Refresh on the row (→ /invoke
  // get_synthesis_status, logged as a ui activity event) applies the terminal
  // status: unread marker + completion toast, then the report opens on click.
  await openPalette(page);
  await page.getByRole("option", { name: /^Synthesize/ }).click();
  await expect(page.getByText(/Synthesis dispatched/)).toBeVisible();
  await expect(dock.getByText("synth_0001")).toBeVisible();
  await expect(dock.locator('[data-run-id="synth_0001"]').getByText("running")).toBeVisible();
  await dock.getByTestId("run-refresh-synth_0001").click();
  await expect(page.getByText(/Synthesis completed/)).toBeVisible();
  // running → terminal marked the run unread (no auto-switching).
  await expect(dock.locator('[title="new"]')).toBeVisible();
  await dock.getByText("synth_0001").click();
  await expect(page.getByText("Report · synth_0001")).toBeVisible();
  await expect(page.getByText(/Design Report/)).toBeVisible({ timeout: 10_000 });
  await page.screenshot({ path: "e2e-artifacts/wb2-report.png", fullPage: true });

  // No auto-switching happened along the way: the report tab was opened by us,
  // and the waveform tab is still there.
  await expect(page.getByText("Waveform · sim_0001")).toBeVisible();
});

test("sim options: TB combobox suggests manifest testbenches; POST carries simTop", async ({ page }) => {
  await installMocks(page);
  await page.goto("/w/demo");
  await expect(page.getByText("alu.v")).toBeVisible();

  // ⌘K → gear on Simulate opens the param modal instead of running.
  await openPalette(page);
  await page.getByRole("button", { name: "Simulate options" }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByText("run_isolated_simulation")).toBeVisible();

  // The TB combo defaults to the manifest simTop and suggests the manifest's
  // derived testbench modules on focus.
  const combo = dialog.getByRole("combobox", { name: "Testbench" });
  await expect(combo).toHaveValue("cpu_tb");
  await combo.fill("");
  await combo.click();
  await expect(dialog.getByRole("option", { name: "cpu_tb" })).toBeVisible();
  await dialog.getByRole("option", { name: "cpu_tb" }).click();
  await expect(combo).toHaveValue("cpu_tb");

  // Run → the POST /simulate body carries the chosen testbench.
  const [req] = await Promise.all([
    page.waitForRequest((r) => r.url().includes("/simulate") && r.method() === "POST"),
    dialog.getByRole("button", { name: /^Run/ }).click(),
  ]);
  expect(req.postDataJSON()).toMatchObject({ simTop: "cpu_tb", mode: "rtl" });

  // The mock echoes simTop into run.top; the run lands in the Runs panel.
  const dock = page.getByTestId("bottom-dock");
  await dock.getByRole("button", { name: /Runs/ }).click();
  await expect(dock.getByText("sim_0001")).toBeVisible();
});

test("file tree → code tab: open, focus-if-open, close", async ({ page }) => {
  await installMocks(page);
  await page.goto("/w/demo");
  await expect(page.getByText("alu.v")).toBeVisible();

  await page.getByText("alu.v").click();
  // Tab appears; content loads via the smart-file endpoint (Monaco may fall
  // back to the plain renderer if its CDN is unreachable — content either way).
  await expect(page.getByRole("tab", { name: /alu\.v/ })).toBeVisible();
  // String matching (not regex): Monaco renders spaces as &nbsp; — Playwright
  // normalizes whitespace for string matchers but not for regexes.
  await expect(page.getByText("real content")).toBeVisible({ timeout: 15_000 });

  // Opening the same file again focuses the existing tab, not a duplicate.
  await page.getByText("cpu_tb.v").first().click();
  await expect(page.getByRole("tab", { name: /cpu_tb\.v/ })).toBeVisible();
  await page.getByText("alu.v").first().click();
  await expect(page.getByRole("tab", { name: /alu\.v/ })).toHaveCount(1);

  await page.screenshot({ path: "e2e-artifacts/wb2-code.png", fullPage: true });
});

test("quick open (⌘P) opens an artifact by fuzzy name", async ({ page }) => {
  await installMocks(page);
  await page.goto("/w/demo");
  await expect(page.getByText("alu.v")).toBeVisible();

  await page.keyboard.press("ControlOrMeta+p");
  const input = page.getByPlaceholder("Open artifact…");
  await expect(input).toBeVisible();
  await input.fill("cpu_tb");
  await page.keyboard.press("Enter");
  await expect(page.getByRole("tab", { name: /cpu_tb\.v/ })).toBeVisible();
});

// S3: ⌘O session quick-switch — grouped list (left) + detail pane (right) with
// the shell choice and the lazily-fetched chat list; Esc closes.
test("quick switch (⌘O): current session, detail pane, empty state, esc closes", async ({ page }) => {
  await installMocks(page);
  await page.goto("/w/demo");
  await expect(page.getByText("alu.v")).toBeVisible();

  await page.keyboard.press("ControlOrMeta+o");
  const qs = page.getByTestId("quick-switch");
  await expect(qs).toBeVisible();

  // The active session row carries the "current" chip.
  const row = qs.getByTestId("qs-session-demo");
  await expect(row).toBeVisible();
  await expect(row.getByText("current")).toBeVisible();

  // Detail pane: shell buttons (stored default = IDE) and the
  // jump-to-chat list, hydrated lazily (debounced threadsApi.list).
  const detail = qs.getByTestId("qs-detail");
  await expect(detail.getByRole("button", { name: "Open in IDE" })).toBeVisible();
  await expect(detail.getByRole("button", { name: "Open in Chat" })).toBeVisible();
  await expect(detail.getByText("Chat 1")).toBeVisible();

  // Nonsense query → honest empty state (and the detail pane goes blank).
  await page.getByPlaceholder("Switch to a session…").fill("zzznope");
  await expect(qs.getByTestId("qs-empty")).toHaveText('No sessions match "zzznope"');

  await page.keyboard.press("Escape");
  await expect(qs).toHaveCount(0);
});

// Wave 8: the agent-first shell (`?view=agent`) — prompt + view only
// (revision 3), Codex-style resting state: header + conversation. The nav
// rail is a closed-by-default overlay (☰/⌘O); the artifact panel is an
// animated split whose home tab is the Runs/Files Index. NO command palette
// (⌘K falls through); the mode toggle routes back to the IDE with the dock.
test("agent shell: header + Index panel + nav rail, no ⌘K palette, file→tab, toggle → IDE", async ({ page }) => {
  await installMocks(page);
  await page.goto("/w/demo?view=agent");

  await expect(page.getByTestId("workbench-agent")).toBeVisible();
  // Center: the conversation (composer enabled for the selected session).
  await expect(page.getByPlaceholder("Describe your RTL design requirements...")).toBeVisible();

  // Header carries the chrome; the old fixed sidebar is gone. The panel
  // rests CLOSED (resting state = header + conversation, locked decision).
  const header = page.getByTestId("agent-header");
  await expect(header.getByTestId("agent-session-button")).toBeVisible();
  await expect(page.getByTestId("agent-sidebar")).toHaveCount(0);
  const panel = page.getByTestId("agent-artifacts-panel");
  await expect(panel).toHaveAttribute("data-open", "false");

  // The chip opens the panel on the Index home = Runs + Files.
  await page.getByTestId("agent-artifacts-chip").click();
  await expect(panel).toHaveAttribute("data-open", "true");
  await expect(panel.getByTestId("agent-runs-section")).toBeVisible();
  await expect(panel.getByTestId("agent-files-section")).toBeVisible();
  await expect(page.getByTestId("agent-file-alu.v")).toBeVisible();
  await expect(page.getByTestId("agent-file-cpu_tb.v")).toBeVisible();

  // ⌘K must NOT open a palette here (prompt + view only).
  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByPlaceholder("Run a command…")).toHaveCount(0);

  // Index file click → a code tab opens; "Back to index" returns home.
  await page.getByTestId("agent-file-alu.v").click();
  await expect(panel.getByRole("tab", { name: /alu\.v/ })).toBeVisible();
  // String matcher: Monaco renders spaces as &nbsp; (see the file-tree test).
  await expect(panel.getByText("real content")).toBeVisible({ timeout: 15_000 });
  await page.getByTestId("artifact-back-to-index").click();
  await expect(panel.getByTestId("artifact-index")).toBeVisible();

  // Esc dismisses the panel (width-0 keep-alive, still mounted); the chip
  // brings it back.
  await page.keyboard.press("Escape");
  await expect(panel).toHaveAttribute("data-open", "false");
  await page.getByTestId("agent-artifacts-chip").click();
  await expect(panel).toHaveAttribute("data-open", "true");

  // ☰ opens the nav rail overlay: sessions + nested chats; Esc closes it
  // WITHOUT also closing the artifact panel (consumed Esc).
  await page.getByTestId("agent-rail-toggle").click();
  const rail = page.getByTestId("agent-nav-rail");
  await expect(rail).toHaveAttribute("data-open", "true");
  await expect(rail.getByTestId("rail-session-demo")).toBeVisible();
  await expect(rail.getByTestId("rail-new-session")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(rail).toHaveAttribute("data-open", "false");
  await expect(panel).toHaveAttribute("data-open", "true");
  await page.screenshot({ path: "e2e-artifacts/wb2-agent-shell.png", fullPage: true });

  // Mode toggle → ?view=ide with the full IDE chrome (dock) — same session.
  await page.getByTestId("mode-toggle-ide").click();
  await page.waitForURL((u) => u.searchParams.get("view") === "ide");
  await expect(page.getByTestId("workbench-v2")).toBeVisible();
  await expect(page.getByTestId("bottom-dock")).toBeVisible();
});

test("command surface: browse → Metrics → live payload → invoke → inline result", async ({ page }) => {
  await installMocks(page);
  await page.goto("/w/demo");
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

