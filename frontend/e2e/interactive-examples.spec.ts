import { test, expect, Route, Page, FrameLocator } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * Every shipped interactive example bundle, driven end-to-end in a real
 * browser: shipped dashboard html + shipped websim netlist + the real
 * digitaljs engine. Each case makes one design-specific assertion that can
 * only pass if the dashboard's widgets are truly wired to the netlist's pins
 * — a port-name typo or a dead bridge fails here, not in front of a user.
 * (traffic_light has its own richer spec in interactive-sim.spec.ts.)
 */

const EXAMPLES = path.resolve(__dirname, "../../examples");

function bundleFiles(id: string, names: string[]) {
  const files: Record<string, Buffer> = {};
  for (const name of names) {
    files[name] = readFileSync(path.join(EXAMPLES, id, "workspace", name));
  }
  return files;
}

function installMocks(page: Page, files: Record<string, Buffer>) {
  const json = (route: Route, body: unknown, status = 200) =>
    route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

  const rootDir = Object.keys(files).map((name) => ({
    name,
    path: name,
    kind: "file",
    size: files[name].length,
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
        return json(route, { ok: true, paths: Object.keys(files), truncated: false });
      return json(route, { ok: true, path: "", entries: rootDir });
    }

    if (p.includes("/file/")) {
      const name = decodeURIComponent(p.split("/file/")[1].split("?")[0]);
      const f = files[name];
      if (!f) return json(route, { detail: "File not found" }, 404);
      if (url.searchParams.get("raw") === "1")
        return route.fulfill({ status: 200, contentType: "application/octet-stream", body: f });
      return json(route, { filename: name, content: f.toString("utf8"), size: f.length, binary: false, tooLarge: false });
    }

    if (p.endsWith("/tools") && m === "GET") return json(route, { ok: true, tools: [] });
    if (p.endsWith("/layouts")) return json(route, { layouts: [], missing_binaries: [] });
    if (p.endsWith("/schematics")) return json(route, []);
    if (p.endsWith("/spec")) return json(route, { detail: "No spec" }, 404);
    return json(route, []);
  });
}

async function openDashboard(
  page: Page,
  id: string,
  files: Record<string, Buffer>,
  dashboardName: string
): Promise<FrameLocator> {
  await installMocks(page, files);
  await page.goto("/w/demo");
  await expect(page.getByText(Object.keys(files).find((n) => n.endsWith(".v"))!)).toBeVisible();

  // quick-open loads its artifact list asynchronously — pressing Enter before
  // the matching option renders is a no-op. Wait for the option, then commit.
  const namePattern = new RegExp(dashboardName.replace(/\./g, "\\."));
  await page.keyboard.press("ControlOrMeta+p");
  const input = page.getByPlaceholder("Open artifact…");
  await expect(input).toBeVisible();
  await input.fill(dashboardName);
  const option = page.getByRole("option", { name: namePattern });
  await expect(option).toBeVisible({ timeout: 10_000 });
  await option.click();
  await expect(page.getByRole("tab", { name: namePattern })).toBeVisible();

  // shell-side, unspoofable: live sim + verified-fresh provenance
  const strip = page.getByTestId("websim-provenance");
  await expect(strip).toContainText("live gate-level sim");
  await expect(strip).not.toContainText("STALE", { timeout: 10_000 });

  const frame = page.getByTestId("websim-frame");
  await expect(frame).toHaveAttribute("sandbox", "allow-scripts");
  return frame.contentFrame();
}

test("lfsr8: the register visibly walks its sequence", async ({ page }) => {
  const files = bundleFiles("lfsr8", ["lfsr8.dashboard.html", "lfsr8.websim.json", "lfsr8.v"]);
  const inner = await openDashboard(page, "lfsr8", files, "lfsr8.dashboard.html");

  const hex = inner.locator("#hexv");
  await expect(hex).toHaveText(/^0x[0-9A-F]{2}$/, { timeout: 10_000 });
  const first = await hex.textContent();
  // at 8 Hz the state must move on — only the netlist can change it
  await expect(hex).not.toHaveText(first!, { timeout: 10_000 });
});

test("seq_detector_0011: hand-fed 0,0,1,1 fires the real detected pin", async ({ page }) => {
  const files = bundleFiles("seq_detector_0011", [
    "seq_detector_0011.dashboard.html", "seq_detector_0011.websim.json", "seq_detector_0011.v",
  ]);
  const inner = await openDashboard(page, "seq_detector_0011", files, "seq_detector_0011.dashboard.html");

  // din=0 ticks in at 2 Hz; after two zeros, flip to 1 → window reaches 0011
  await expect(inner.locator("#cyc")).toContainText(/cycle [2-9]/, { timeout: 10_000 });
  await inner.locator("#din").click();
  await expect(inner.locator("#det")).toHaveClass(/on/, { timeout: 10_000 });
});

test("alu4: 7 + 5 computes 0x0C on the netlist's registered result", async ({ page }) => {
  const files = bundleFiles("alu4", ["alu4.dashboard.html", "alu4.websim.json", "alu4.v"]);
  const inner = await openDashboard(page, "alu4", files, "alu4.dashboard.html");

  // a = 7 (bits 2,1,0 — buttons are rendered MSB first)
  const aBits = inner.locator("#a .bitbtn");
  await aBits.nth(1).click();
  await aBits.nth(2).click();
  await aBits.nth(3).click();
  // b = 5 (bits 2,0)
  const bBits = inner.locator("#b .bitbtn");
  await bBits.nth(1).click();
  await bBits.nth(3).click();

  await expect(inner.locator("#rhex")).toHaveText("0x0C", { timeout: 10_000 });
  await expect(inner.locator("#meaning")).toContainText("result = 12");
});

test("sn74169: undefined at power-on, defined after load, then counts", async ({ page }) => {
  const files = bundleFiles("sn74169", ["sn74169.dashboard.html", "sn74169.websim.json", "sn74169.v"]);
  const inner = await openDashboard(page, "sn74169", files, "sn74169.dashboard.html");

  // the dashboard starts in load posture; the first tick defines Q
  await expect(inner.locator("#Qhex")).toHaveText("Q = 0", { timeout: 10_000 });

  // release LOAD̄, assert both enables → counts up
  await inner.locator("#LOADB").click();
  await inner.locator("#ENPB").click();
  await inner.locator("#ENTB").click();
  await expect(inner.locator("#Qhex")).toHaveText(/Q = [1-9]/, { timeout: 10_000 });
});

test("simon_game: attract pattern runs, a pad press starts the game, strip shows the override", async ({ page }) => {
  const files = bundleFiles("simon_game", [
    "simon_game.dashboard.html", "simon_game.websim.json", "simon.v", "simon_game.v",
  ]);
  const inner = await openDashboard(page, "simon_game", files, "simon_game.dashboard.html");

  // the re-parameterized netlist must be labeled, shell-side and unspoofable
  await expect(page.getByTestId("websim-provenance")).toContainText("TICKS_PER_MILLI=1");

  // power-on attract: state label from the real dbg_state pins
  await expect(inner.locator("#state")).toHaveText("POWER-ON", { timeout: 10_000 });

  // hold a pad down long enough for the 1 kHz game clock to sample it
  const pad = inner.locator(".pad0");
  await pad.dispatchEvent("mousedown");
  await page.waitForTimeout(300);
  await pad.dispatchEvent("mouseup");

  // seeded → INIT (500 game-ms) → sequence playback lights a pad
  await expect(inner.locator("#state")).toHaveText(/PLAY|YOUR TURN/, { timeout: 15_000 });
  await expect(inner.locator("#level")).not.toHaveText("x");
});

test("ubcd_decoder: value A in the hex family lights the real segment pins", async ({ page }) => {
  const files = bundleFiles("ubcd_decoder", [
    "universal_bcd_decoder.dashboard.html", "universal_bcd_decoder.websim.json", "ubcd.v",
  ]);
  const inner = await openDashboard(page, "ubcd_decoder", files, "universal_bcd_decoder.dashboard.html");

  // hex family default, value 0 → '0': segment g dark
  await expect(inner.locator("#sa")).toHaveClass(/on/, { timeout: 10_000 });
  await expect(inner.locator("#sg")).not.toHaveClass(/on/);

  // click 'A' (0x77): g lights, d goes dark — combinational, no clock at all
  await inner.locator("#values button").nth(10).click();
  await expect(inner.locator("#sg")).toHaveClass(/on/, { timeout: 5_000 });
  await expect(inner.locator("#sd")).not.toHaveClass(/on/);
  await expect(inner.locator("#sb")).toHaveClass(/on/);
});
