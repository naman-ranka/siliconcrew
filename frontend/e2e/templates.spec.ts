import { test, expect, Route, Page } from "@playwright/test";

/**
 * Wave 11 — templates (bundles) & forks.
 *
 * Drives the real frontend against a stateful mock: the Launcher Examples
 * gallery → preview slide-over ("what's inside") → Fork → lands in /w/{fork}
 * with the file tree, the Activity dock showing the bundle's tool trajectory,
 * and the "forked from" provenance chip. The fork backend (copy + rewrites) is
 * pytest-covered; what's under test here is the wiring.
 */

const TEMPLATE_SUMMARY = {
  id: "sync_fifo",
  name: "Synchronous FIFO",
  description: "A parameterized single-clock FIFO — lint plus a fail→fix→pass sim.",
  highlights: ["Lint clean (iverilog)", "Self-checking testbench", "Real trajectory: fail → fix → pass"],
  top_module: "sync_fifo",
  platform: "sky130hd",
  source_note: "Dogfood-authored",
  file_count: 12,
  run_count: 2,
};

const TEMPLATE_DETAIL = {
  ...TEMPLATE_SUMMARY,
  files: ["sync_fifo.v", "sync_fifo_tb.v", "spec.md", "sim_runs/sim_0001/run_meta.json"],
  conversations: ["chat-1-design.md"],
};

const FORK_SESSION = {
  id: "synchronous-fifo",
  name: "Synchronous FIFO",
  model_name: "gemini-3-flash-preview",
  project_id: null,
  created_at: "2026-07-06T10:00:00Z",
  updated_at: "2026-07-06T10:00:00Z",
  total_tokens: 0,
  total_cost: 0,
  thread_count: 1,
  source_template: { id: "sync_fifo", name: "Synchronous FIFO", forked_at: "2026-07-06T10:00:00+00:00" },
};

// The bundle's copied trajectory (lint → failing sim → passing sim), surfaced
// in the forked workspace's Activity dock exactly as the template recorded it.
const FORK_ACTIVITY = [
  { id: "e3", ts: "2026-07-06T05:16:46Z", source: "ui", tool: "run_isolated_simulation", args: {}, status: "ok", resultSummary: "sim_0002 passed", durationMs: 100, runId: "sim_0002", threadId: null },
  { id: "e2", ts: "2026-07-06T05:16:46Z", source: "ui", tool: "run_isolated_simulation", args: {}, status: "error", resultSummary: "sim_0001 failed", durationMs: 560, runId: "sim_0001", threadId: null },
  { id: "e1", ts: "2026-07-06T05:16:45Z", source: "ui", tool: "linter_tool", args: {}, status: "ok", resultSummary: "passed (iverilog)", durationMs: 880, runId: null, threadId: null },
];

const ROOT_DIR = [
  { name: "sim_runs", path: "sim_runs", kind: "dir" },
  { name: "spec.md", path: "spec.md", kind: "file", size: 300, modified: "2026-07-06T05:16:00" },
  { name: "sync_fifo.v", path: "sync_fifo.v", kind: "file", size: 900, modified: "2026-07-06T05:16:00" },
  { name: "sync_fifo_tb.v", path: "sync_fifo_tb.v", kind: "file", size: 1200, modified: "2026-07-06T05:16:00" },
];

function installMocks(page: Page) {
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  return page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const m = route.request().method();

    // Launcher boot — no existing sessions, so the Examples gallery is the
    // primary content for a fresh user.
    if (p === "/api/sessions" && m === "GET") return json(route, []);
    if (p === "/api/projects" && m === "GET") return json(route, []);
    if (p === "/api/models" && m === "GET")
      return json(route, { default: "gemini-3-flash-preview", models: [
        { id: "gemini-3-flash-preview", label: "Gemini 3 Flash", provider: "google", tier: "fast", hint: "", available: true },
      ] });

    // Templates surface.
    if (p === "/api/templates" && m === "GET") return json(route, { templates: [TEMPLATE_SUMMARY] });
    if (p === "/api/templates/sync_fifo" && m === "GET") return json(route, TEMPLATE_DETAIL);
    if (p === "/api/templates/sync_fifo/fork" && m === "POST")
      return json(route, { sessionId: FORK_SESSION.id });

    // Forked session boot.
    if (p === `/api/sessions/${FORK_SESSION.id}` && m === "GET") return json(route, FORK_SESSION);
    if (p === `/api/sessions/${FORK_SESSION.id}/threads` && m === "GET")
      return json(route, [{ id: FORK_SESSION.id, session_id: FORK_SESSION.id, title: "Chat 1", model: null, created_at: null, last_active: null }]);
    if (p.endsWith("/history")) return json(route, []);
    if (p.endsWith("/workbench") && m === "GET")
      return json(route, {
        ok: true,
        manifest: {
          sessionId: FORK_SESSION.id,
          files: [
            { name: "sync_fifo.v", role: "rtl", path: "sync_fifo.v" },
            { name: "sync_fifo_tb.v", role: "tb", path: "sync_fifo_tb.v" },
          ],
          synthTop: "sync_fifo", simTop: "sync_fifo_tb", clockPeriodNs: 10, platform: "sky130hd",
          testbenches: [], ignore: [],
        },
        runs: [], files: [], spec: null, code: [], report: null, synthesisRuns: [],
        activity: FORK_ACTIVITY, rootDir: ROOT_DIR,
      });
    if (p.endsWith("/activity") && m === "GET")
      return json(route, { ok: true, events: FORK_ACTIVITY, nextBefore: null });
    if (p.endsWith("/runs") && m === "GET") return json(route, { ok: true, runs: [] });
    if (p.endsWith("/dir") && m === "GET") {
      if (url.searchParams.get("recursive") === "paths")
        return json(route, { ok: true, paths: ["sync_fifo.v", "sync_fifo_tb.v", "spec.md"], truncated: false });
      return json(route, { ok: true, path: "", entries: ROOT_DIR });
    }
    if (p.endsWith("/tools") && m === "GET") return json(route, { ok: true, tools: [] });
    if (p.endsWith("/layouts") || p.endsWith("/schematics")) return json(route, []);
    if (p.endsWith("/spec")) return json(route, { detail: "No spec" }, 404);

    return json(route, []);
  });
}

test("examples → preview → fork → lands in the forked workbench with the trajectory", async ({ page }) => {
  await installMocks(page);
  await page.goto("/");

  // The Examples gallery renders the bundle card with its highlights.
  const section = page.getByTestId("examples-section");
  await expect(section).toBeVisible();
  const card = page.getByTestId("example-card-sync_fifo");
  await expect(card).toBeVisible();
  await expect(card.getByText("Synchronous FIFO")).toBeVisible();
  await expect(card.getByText("Lint clean (iverilog)")).toBeVisible();

  // Card → the preview slide-over shows "what's inside".
  await card.click();
  const preview = page.getByTestId("template-preview");
  await expect(preview).toBeVisible();
  await expect(preview.getByText("sync_fifo.v")).toBeVisible();
  await expect(preview.getByText("chat-1-design.md")).toBeVisible();

  // Fork → POST /fork → navigate into /w/{fork}.
  const [req] = await Promise.all([
    page.waitForRequest((r) => r.url().includes("/api/templates/sync_fifo/fork") && r.method() === "POST"),
    page.getByTestId("fork-template").click(),
  ]);
  expect(req.method()).toBe("POST");
  await page.waitForURL((u) => u.pathname === `/w/${FORK_SESSION.id}`);

  // The forked workbench boots: file tree from the copied workspace…
  await expect(page.getByText("sync_fifo.v")).toBeVisible();
  // …the Activity dock shows the copied tool trajectory…
  const dock = page.getByTestId("bottom-dock");
  await expect(dock.getByText("linter_tool").first()).toBeVisible();
  await expect(dock.getByText("run_isolated_simulation").first()).toBeVisible();
  // …and the breadcrumb carries the "forked from" provenance chip.
  await expect(page.getByTestId("forked-from-chip")).toContainText("forked from Synchronous FIFO");
  await page.screenshot({ path: "e2e-artifacts/templates-fork.png", fullPage: true });
});
