import { test, expect, Route, Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * Tier-2 E2E for the interactive web-sim viewer — and the one place the WHOLE
 * loop runs for real: the SHIPPED traffic_light example bundle (dashboard html
 * + websim netlist, read from examples/ on disk) in a REAL browser, with the
 * digitaljs engine simulating the synthesized netlist and the sandboxed
 * agent dashboard rendering its output pins. If the lights change phase here,
 * spec → RTL → yosys → browser is genuinely working end to end.
 */

const BUNDLE = path.resolve(__dirname, "../../examples/traffic_light/workspace");
const DASHBOARD = readFileSync(path.join(BUNDLE, "traffic_light.dashboard.html"), "utf8");
const WEBSIM = readFileSync(path.join(BUNDLE, "traffic_light.websim.json"));
const RTL = readFileSync(path.join(BUNDLE, "traffic_light.v"));

const MOCKUP_HTML = "<html><body><h1>Pretty but fake</h1></body></html>";

const FILES: Record<string, { bytes: Buffer; text: string }> = {
  "traffic_light.dashboard.html": { bytes: Buffer.from(DASHBOARD), text: DASHBOARD },
  "traffic_light.websim.json": { bytes: WEBSIM, text: WEBSIM.toString("utf8") },
  "traffic_light.v": { bytes: RTL, text: RTL.toString("utf8") },
  "mockup.dashboard.html": { bytes: Buffer.from(MOCKUP_HTML), text: MOCKUP_HTML },
};

function installMocks(page: Page) {
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  const rootDir = Object.keys(FILES).map((name) => ({
    name,
    path: name,
    kind: "file",
    size: FILES[name].bytes.length,
    modified: "2026-07-01T10:00:00",
  }));

  return page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    const p = url.pathname;
    const m = route.request().method();

    if (p === "/api/sessions" && m === "GET")
      return json(route, [
        { id: "demo", name: "demo", model_name: "claude-sonnet-4-6", project_id: null, created_at: null, updated_at: null, total_tokens: 0, total_cost: 0 },
      ]);
    if (p === "/api/sessions/demo/threads" && m === "GET")
      return json(route, [{ id: "demo", session_id: "demo", title: "Chat 1", model: null, created_at: null, last_active: null }]);
    if (p.endsWith("/history")) return json(route, []);
    if (p.endsWith("/workbench") && m === "GET")
      return json(route, {
        ok: true,
        manifest: { sessionId: "demo", files: [], synthTop: null, simTop: null, clockPeriodNs: 10, platform: "sky130hd", ignore: [], testbenches: [] },
        runs: [], files: [], spec: null, code: [], report: null, synthesisRuns: [], activity: [],
        rootDir,
      });
    if (p.endsWith("/dir") && m === "GET") {
      if (url.searchParams.get("recursive") === "paths")
        return json(route, { ok: true, paths: Object.keys(FILES), truncated: false });
      return json(route, { ok: true, path: "", entries: rootDir });
    }

    if (p.includes("/file/")) {
      const name = decodeURIComponent(p.split("/file/")[1].split("?")[0]);
      const f = FILES[name];
      if (!f) return json(route, { detail: "File not found" }, 404);
      if (url.searchParams.get("raw") === "1")
        return route.fulfill({ status: 200, contentType: "application/octet-stream", body: f.bytes });
      return json(route, { filename: name, content: f.text, size: f.bytes.length, binary: false, tooLarge: false });
    }

    if (p.endsWith("/tools") && m === "GET") return json(route, { ok: true, tools: [] });
    if (p.endsWith("/layouts")) return json(route, { layouts: [], missing_binaries: [] });
    if (p.endsWith("/schematics")) return json(route, []);
    if (p.endsWith("/spec")) return json(route, { detail: "No spec" }, 404);
    return json(route, []);
  });
}

async function openByQuickOpen(page: Page, name: string) {
  await page.keyboard.press("ControlOrMeta+p");
  const input = page.getByPlaceholder("Open artifact…");
  await expect(input).toBeVisible();
  await input.fill(name);
  await page.keyboard.press("Enter");
}

test("shipped traffic_light dashboard runs the REAL netlist sim in the browser", async ({ page }) => {
  await installMocks(page);
  await page.goto("/w/demo");
  await expect(page.getByText("traffic_light.v")).toBeVisible();

  await openByQuickOpen(page, "dashboard");
  // quick-open may match both dashboards — pick the real one explicitly if a
  // list is showing; otherwise Enter already opened the top hit.
  const tab = page.getByRole("tab", { name: /traffic_light\.dashboard\.html/ });
  if (!(await tab.isVisible().catch(() => false))) {
    await openByQuickOpen(page, "traffic_light.dashboard");
  }
  await expect(tab).toBeVisible();

  // Sandbox discipline: allow-scripts EXACTLY — never same-origin.
  const frame = page.getByTestId("websim-frame");
  await expect(frame).toBeVisible();
  await expect(frame).toHaveAttribute("sandbox", "allow-scripts");

  // Provenance strip (shell-side, unspoofable): live + hashes verified fresh
  // (raw bytes served are the exact shipped sources) + fidelity label.
  const strip = page.getByTestId("websim-provenance");
  await expect(strip).toContainText("live gate-level sim");
  await expect(strip).toContainText("traffic_light.websim.json");
  await expect(strip).toContainText("no timing");
  await expect(strip).not.toContainText("STALE", { timeout: 10_000 });
  await expect(strip).not.toContainText("freshness unverified", { timeout: 10_000 });

  // The heartbeat: cycles advance, so the engine is genuinely ticking.
  await expect(page.getByTestId("websim-cycles")).not.toHaveText(/^0 cycles$/, { timeout: 10_000 });

  // Inside the sandboxed agent dashboard: output pins drive the lamps. The
  // FSM holds GREEN 8 ticks → YELLOW 3 → RED 8; at the dashboard's 4 Hz the
  // phase label must change within a few seconds — that transition can ONLY
  // come from the simulated netlist (the page has no animation logic).
  const inner = frame.contentFrame();
  await expect(inner.locator("#phase")).toHaveText("GREEN", { timeout: 10_000 });
  await expect(inner.locator("#phase")).toHaveText("YELLOW", { timeout: 10_000 });
  await expect(inner.locator("#phase")).toHaveText("RED", { timeout: 10_000 });
});

test("a dashboard without a sim declaration is branded a static mockup", async ({ page }) => {
  await installMocks(page);
  await page.goto("/w/demo");
  await expect(page.getByText("traffic_light.v")).toBeVisible();

  await openByQuickOpen(page, "mockup");
  await expect(page.getByRole("tab", { name: /mockup\.dashboard\.html/ })).toBeVisible();

  const strip = page.getByTestId("websim-provenance");
  await expect(strip).toContainText(/static mockup/i);
  await expect(strip).toContainText(/NOT connected/i);
  // still sandboxed, still renders — but never pretends to be live
  await expect(page.getByTestId("websim-frame")).toHaveAttribute("sandbox", "allow-scripts");
  await expect(strip).not.toContainText("live gate-level sim");
});
