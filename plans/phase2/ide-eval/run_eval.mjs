// Headless human-path IDE evaluation harness.
// Usage: node run_eval.mjs <designDir> <sessionName> <outDir>
// Drives the LIVE UI exactly as a human would: create session -> workbench ->
// upload RTL+TB -> Lint -> Simulate -> Synthesize -> inspect every viewer.
// Captures screenshots + a structured timeline (with timings, result text,
// console output, JS errors) so we can evaluate real usability + the pipeline
// ceiling. Resilient: each step is isolated so one failure never aborts the run.
import { createRequire } from "module";
import fs from "fs";
import path from "path";
const require = createRequire("/home/user/siliconcrew/frontend/");
const { chromium } = require("playwright");

const [, , designDir, sessionName, outDir] = process.argv;
if (!designDir || !sessionName || !outDir) {
  console.error("usage: node run_eval.mjs <designDir> <sessionName> <outDir>");
  process.exit(2);
}
const BASE = "http://localhost:3001";
const EXE = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome";

fs.mkdirSync(outDir, { recursive: true });
const designFiles = fs
  .readdirSync(designDir)
  .filter((f) => f.endsWith(".v"))
  .map((f) => path.join(designDir, f));

const timeline = [];
const t0 = Date.now();
const rel = () => Date.now() - t0;
const log = (action, info = {}) => {
  const e = { ms: rel(), action, ...info };
  timeline.push(e);
  console.log(`[${e.ms}ms] ${action} ${JSON.stringify(info)}`);
};

const browser = await chromium.launch({ headless: true, executablePath: EXE });
const ctx = await browser.newContext({ viewport: { width: 1500, height: 950 } });
const page = await ctx.newPage();
const jsErrors = [];
const netErrors = [];
page.on("console", (m) => { if (m.type() === "error") jsErrors.push(m.text()); });
page.on("pageerror", (e) => jsErrors.push("pageerror: " + e.message));
page.on("response", (r) => { if (r.status() >= 400) netErrors.push({ status: r.status(), url: r.url() }); });
page.on("requestfailed", (r) => netErrors.push({ status: "failed", url: r.url(), err: r.failure()?.errorText }));

const shot = async (name) => {
  try { await page.screenshot({ path: path.join(outDir, name + ".png") }); log("screenshot", { name }); }
  catch (e) { log("screenshot_FAIL", { name, err: e.message }); }
};
const txt = async (sel) => {
  try { const el = await page.$(sel); return el ? (await el.innerText()).slice(0, 1200) : null; }
  catch { return null; }
};
const consoleText = () => txt('[data-testid="console"]');
const step = async (name, fn) => {
  const s = Date.now();
  try { const r = await fn(); log(name, { ok: true, ms_step: Date.now() - s, ...(r || {}) }); return r; }
  catch (e) { log(name, { ok: false, ms_step: Date.now() - s, err: e.message }); return null; }
};

try {
  // 1) Create a session through the UI.
  await step("create_session", async () => {
    await page.goto(BASE + "/", { waitUntil: "networkidle", timeout: 30000 });
    await page.getByRole("button", { name: "New Session" }).click();
    await page.getByRole("textbox", { name: /counter_4bit_run1/ }).fill(sessionName);
    await page.getByRole("button", { name: "Create" }).click();
    await page.waitForTimeout(1800);
  });

  // 2) Open the workbench (the real IDE surface).
  await step("open_workbench", async () => {
    await page.goto(BASE + "/workbench", { waitUntil: "networkidle", timeout: 30000 });
    await page.waitForTimeout(1200);
  });
  // GUARD: the workbench auto-loads the *latest* session, which may not be the
  // one we just created. Verify; if wrong, switch to ours via the picker. This
  // prevents uploading into a stale workspace (the duplicate-name failure mode).
  await step("verify_session", async () => {
    const switcher = page.getByRole("button", { name: /Switch session/ });
    const shown = (await switcher.textContent().catch(() => "")) || "";
    if (!shown.includes(sessionName)) {
      await switcher.click();
      await page.waitForTimeout(500);
      await page.getByRole("menuitem", { name: new RegExp(sessionName) }).first().click().catch(async () => {
        await page.getByText(sessionName, { exact: false }).first().click();
      });
      await page.waitForTimeout(1000);
      const now = (await switcher.textContent().catch(() => "")) || "";
      if (!now.includes(sessionName)) throw new Error(`session mismatch: wanted ${sessionName}, shows "${now.trim()}"`);
    }
    return { active: sessionName };
  });
  await shot("01-workbench-empty");

  // 3) Upload RTL + testbench via the Files-panel Upload button (file chooser).
  await step("upload_files", async () => {
    const [chooser] = await Promise.all([
      page.waitForEvent("filechooser", { timeout: 8000 }),
      page.getByRole("button", { name: "Upload", exact: true }).first().click(),
    ]);
    await chooser.setFiles(designFiles);
    await page.waitForTimeout(2500);
    return { files: designFiles.map((f) => path.basename(f)) };
  });
  await shot("02-files-uploaded");
  // Capture the Files panel state (did roles / simTop / synthTop auto-detect?).
  log("files_panel", { text: await txt("body") ? null : null, filesArea: await txt('text=synthTop') });

  // 4) Lint.
  await step("run_lint", async () => {
    await page.getByRole("button", { name: /Run Lint/ }).click();
    await page.waitForTimeout(4500);
  });
  // make sure the Lint console tab is shown
  await step("show_lint_console", async () => { await page.getByRole("tab", { name: "Lint" }).click(); await page.waitForTimeout(400); });
  log("lint_result", { console: await consoleText() });
  await shot("03-lint");

  // 5) Simulate.
  await step("run_sim", async () => {
    await page.getByRole("button", { name: /Run Simulate/ }).click();
    await page.waitForTimeout(6000);
  });
  await step("show_sim_console", async () => { await page.getByRole("tab", { name: "Sim" }).click(); await page.waitForTimeout(400); });
  log("sim_result", { console: await consoleText() });
  await shot("04-sim");

  // 6) Inspect the waveform from the passed sim (Artifacts → Wave tab).
  await step("view_wave", async () => { await page.getByRole("tab", { name: "Wave" }).click(); await page.waitForTimeout(1200); });
  await shot("05-wave");

  // 7) Synthesize (expected to fail: no OpenROAD/Docker here — capture the UX).
  await step("run_synth", async () => {
    await page.getByRole("button", { name: /Run Synthesize/ }).click();
    await page.waitForTimeout(15000); // long enough to see if it errors or just hangs
  });
  await step("show_synth_console", async () => { await page.getByRole("tab", { name: "Synth" }).click(); await page.waitForTimeout(400); });
  log("synth_result", { console: await consoleText() });
  await shot("06-synth");

  // 8) Inspect viewers from the pipeline bar.
  for (const [name, file] of [["View RTL", "07-view-rtl"], ["View Spec", "08-view-spec"], ["View Signoff", "09-view-signoff"]]) {
    await step("nav_" + name, async () => { await page.getByRole("button", { name: new RegExp(name) }).click(); await page.waitForTimeout(900); });
    await shot(file);
  }

  // 8) Also capture the chat-first route's Artifacts tabs (Wave/Schem/Layout/Report).
  await step("open_chat_route", async () => { await page.goto(BASE + "/", { waitUntil: "networkidle", timeout: 30000 }); await page.waitForTimeout(1200); });
  await shot("10-chat-route");
} catch (e) {
  log("FATAL", { err: e.message });
} finally {
  fs.writeFileSync(path.join(outDir, "timeline.json"), JSON.stringify({ sessionName, designDir, designFiles, jsErrors, netErrors, timeline }, null, 2));
  log("done", { jsErrors: jsErrors.length, outDir });
  await browser.close();
}
