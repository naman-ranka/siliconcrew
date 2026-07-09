import { test, expect, Route } from "@playwright/test";

/**
 * Tier-2 E2E for the model picker (per chat thread).
 * Verifies: grouped-by-provider popover, capability hints, unavailable models
 * greyed with "needs key", and that selecting a model updates the active thread.
 * Screenshots the grouped popover for the deliverable.
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

const MODELS = {
  default: "gemini-3-flash-preview",
  models: [
    { id: "claude-sonnet-4-6", label: "Claude Sonnet 4.6", provider: "anthropic", tier: "balanced", hint: "Balanced quality/speed.", pricing: { input: 0.3, output: 2.5 }, available: true },
    { id: "claude-opus-4-6", label: "Claude Opus 4.6", provider: "anthropic", tier: "capable", hint: "Most capable.", pricing: { input: 2, output: 12 }, available: true },
    { id: "gpt-5.4", label: "GPT-5.4", provider: "openai", tier: "capable", hint: "Strong reasoning.", available: false },
    { id: "gemini-3-flash-preview", label: "Gemini 3 Flash", provider: "gemini", tier: "fast", hint: "Fast, low-cost default.", available: true },
  ],
};

function installMocks(page: import("@playwright/test").Page) {
  const state = {
    threads: [{ id: "demo", session_id: "demo", title: "Chat 1", model: null as string | null, created_at: null, last_active: null }],
  };
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  return page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const m = route.request().method();

    if (p === "/api/sessions" && m === "GET") return json(route, [SESSION]);
    if (p === "/api/models" && m === "GET") return json(route, MODELS);
    if (p === "/api/sessions/demo/threads" && m === "GET") return json(route, state.threads);
    const patch = p.match(/^\/api\/sessions\/demo\/threads\/([^/]+)$/);
    if (patch && m === "PATCH") {
      const body = JSON.parse(route.request().postData() || "{}");
      state.threads = state.threads.map((t) => (t.id === patch[1] ? { ...t, ...body } : t));
      return json(route, state.threads.find((t) => t.id === patch[1]));
    }
    if (p.endsWith("/history")) return json(route, []);
    if (p.endsWith("/workbench") && m === "GET")
      return json(route, {
        ok: true,
        manifest: { sessionId: "demo", files: [{ name: "alu.v", role: "rtl", path: "alu.v" }], synthTop: "t", simTop: "tb", clockPeriodNs: 10, platform: "sky130hd" },
        runs: [], files: [], spec: null, code: [], report: null, synthesisRuns: [], activity: [],
        rootDir: [{ name: "alu.v", path: "alu.v", kind: "file", size: 22, modified: "2026-07-01T10:00:00" }],
      });
    if (p.endsWith("/dir") && m === "GET")
      return json(route, { ok: true, path: "", entries: [{ name: "alu.v", path: "alu.v", kind: "file", size: 22, modified: "2026-07-01T10:00:00" }] });
    if (p.endsWith("/activity") && m === "GET") return json(route, { ok: true, events: [], nextBefore: null });
    if (p.endsWith("/manifest") && m === "GET")
      return json(route, { ok: true, manifest: { sessionId: "demo", files: [{ name: "alu.v", role: "rtl", path: "alu.v" }], synthTop: "t", simTop: "tb", clockPeriodNs: 10, platform: "sky130hd" } });
    if (p.endsWith("/runs") && m === "GET") return json(route, { ok: true, runs: [] });
    if (p.endsWith("/code") && m === "GET") return json(route, []);
    if (p.endsWith("/files") && m === "GET") return json(route, []);
    if (p.endsWith("/spec")) return json(route, { detail: "No spec" }, 404);
    return json(route, []);
  });
}

test("model picker: grouped popover, unavailable greyed, switch model", async ({ page }) => {
  await installMocks(page);
  await page.goto("/w/demo");

  // The picker button shows the current model (the session's default thread model).
  const picker = page.getByRole("button", { name: /Change model/i });
  await expect(picker).toBeVisible();
  await expect(picker).toContainText("Claude Sonnet 4.6");

  // Open the grouped popover.
  await picker.click();
  const menu = page.getByRole("menu", { name: "Select model" });
  await expect(menu).toBeVisible();
  await expect(menu.getByText("Anthropic")).toBeVisible();
  await expect(menu.getByText("OpenAI")).toBeVisible();
  await expect(menu.getByText("Google")).toBeVisible();
  // Capability hint is shown.
  await expect(menu.getByText("Fast, low-cost default.")).toBeVisible();
  // Unavailable model is greyed with "needs key" and disabled.
  await expect(menu.getByText("needs key")).toBeVisible();
  await expect(menu.getByRole("menuitemradio", { name: /GPT-5\.4/ })).toBeDisabled();

  await page.screenshot({ path: "e2e-artifacts/model-picker-popover.png", fullPage: true });

  // Switch to an available model → the button label updates.
  await menu.getByRole("menuitemradio", { name: /Gemini 3 Flash/ }).click();
  await expect(picker).toContainText("Gemini 3 Flash");
});
