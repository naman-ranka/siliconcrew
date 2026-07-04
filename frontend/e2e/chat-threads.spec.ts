import { test, expect, Route } from "@playwright/test";

/**
 * Tier-2 E2E for chat threads (many conversations per workspace).
 *
 * THE ONE RULE under test: threads share the LIVE workspace. Switching chats
 * swaps the conversation only — the left rail (files) and center never change.
 *
 * Drives the real frontend against a stateful mock of the thread + workspace
 * REST layer (the WS/agent stream is out of scope here; the claim being verified
 * is the switcher UX + workspace-unchanged-across-chats + per-thread history).
 */

const SESSION = {
  id: "demo",
  name: "demo",
  model_name: "claude-sonnet-4-6",
  project_id: null,
  created_at: null,
  updated_at: null,
  total_tokens: 0,
  total_cost: 0,
};

const MANIFEST = {
  ok: true,
  manifest: {
    sessionId: "demo",
    files: [
      { name: "alu.v", role: "rtl", path: "alu.v" },
      { name: "cpu_tb.v", role: "tb", path: "cpu_tb.v" },
    ],
    synthTop: "cpu_top",
    simTop: "cpu_tb",
    clockPeriodNs: 10,
    platform: "sky130hd",
  },
};

function installMocks(page: import("@playwright/test").Page) {
  const state = {
    threads: [
      { id: "demo", session_id: "demo", title: "Chat 1", model: null, created_at: "2026-06-22T09:00:00Z", last_active: "2026-06-22T09:30:00Z" },
    ] as any[],
    histories: {
      demo: [{ role: "user", content: "first chat message" }, { role: "assistant", content: "reply in chat one" }],
    } as Record<string, any[]>,
  };

  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  return page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const m = route.request().method();

    if (p === "/api/sessions" && m === "GET") return json(route, [SESSION]);

    // Threads list / create
    if (p === "/api/sessions/demo/threads" && m === "GET") return json(route, state.threads);
    if (p === "/api/sessions/demo/threads" && m === "POST") {
      const t = { id: "t2", session_id: "demo", title: "Chat 2", model: null, created_at: "2026-06-22T10:00:00Z", last_active: "2026-06-22T10:00:00Z" };
      state.threads = [t, ...state.threads];
      state.histories["t2"] = [];
      return json(route, t);
    }
    // Per-thread history
    const histMatch = p.match(/^\/api\/sessions\/demo\/threads\/([^/]+)\/history$/);
    if (histMatch && m === "GET") return json(route, state.histories[histMatch[1]] ?? []);
    if (p.endsWith("/history")) return json(route, state.histories["demo"]);

    // Workspace (must remain identical across chat switches)
    if (p.endsWith("/workbench") && m === "GET")
      return json(route, {
        ok: true, manifest: MANIFEST.manifest, runs: [], files: [], spec: null, code: [],
        report: null, synthesisRuns: [], activity: [],
        rootDir: [
          { name: "alu.v", path: "alu.v", kind: "file", size: 22, modified: "2026-07-01T10:00:00" },
          { name: "cpu_tb.v", path: "cpu_tb.v", kind: "file", size: 24, modified: "2026-07-01T10:00:00" },
        ],
      });
    if (p.endsWith("/dir") && m === "GET")
      return json(route, { ok: true, path: "", entries: [
        { name: "alu.v", path: "alu.v", kind: "file", size: 22, modified: "2026-07-01T10:00:00" },
        { name: "cpu_tb.v", path: "cpu_tb.v", kind: "file", size: 24, modified: "2026-07-01T10:00:00" },
      ] });
    if (p.endsWith("/activity") && m === "GET") return json(route, { ok: true, events: [], nextBefore: null });
    if (p.endsWith("/manifest") && m === "GET") return json(route, MANIFEST);
    if (p.endsWith("/runs") && m === "GET") return json(route, { ok: true, runs: [] });
    if (p.endsWith("/code") && m === "GET")
      return json(route, [{ filename: "alu.v", content: "module alu; endmodule", language: "verilog" }]);
    if (p.endsWith("/files") && m === "GET") return json(route, []);
    if (p.endsWith("/spec")) return json(route, { detail: "No spec" }, 404);

    return json(route, []);
  });
}

test("chat threads: new chat → switch back → history intact, workspace unchanged", async ({ page }) => {
  await installMocks(page);
  await page.goto("/w/demo");

  // Workspace is present (left rail).
  await expect(page.getByText("alu.v")).toBeVisible();
  await expect(page.getByText("cpu_tb.v")).toBeVisible();

  // The switcher shows the default chat. (The breadcrumb's duplicate chat
  // crumb is gone — the ChatArea's ThreadSwitcher is the only "Switch chat".)
  const switcher = page.locator('button[aria-label="Switch chat"]');
  await expect(switcher).toBeVisible();
  await expect(switcher).toContainText("Chat 1");

  // First chat's history is loaded.
  await expect(page.getByText("first chat message")).toBeVisible();

  // Open the switcher, start a New chat → empty conversation, same workspace.
  await switcher.click();
  await page.getByRole("menu").getByRole("button", { name: /New chat/i }).click();
  await expect(switcher).toContainText("Chat 2");
  await expect(page.getByText("first chat message")).toHaveCount(0); // empty new chat
  // Workspace files unchanged across the switch.
  await expect(page.getByText("alu.v")).toBeVisible();
  await expect(page.getByText("cpu_tb.v")).toBeVisible();

  // Screenshot the switcher (open) for the deliverable.
  await switcher.click();
  await page.screenshot({ path: "e2e-artifacts/chat-threads-switcher.png", fullPage: true });

  // Switch back to Chat 1 → its history is intact; workspace still unchanged.
  await page.getByRole("menuitemradio", { name: /Chat 1/i }).click();
  await expect(page.getByText("first chat message")).toBeVisible();
  await expect(page.getByText("alu.v")).toBeVisible();
});
