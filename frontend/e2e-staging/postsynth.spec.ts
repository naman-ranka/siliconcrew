import { test, expect, APIResponse } from "@playwright/test";
import fs from "node:fs";
import {
  ARTIFACTS,
  EMAIL,
  PASSWORD,
  createFileViaUi,
  newSession,
  shot,
  signIn,
  simulateViaPalette,
} from "./helpers";

/**
 * Staging: POST-SYNTHESIS SIMULATION — the sc#59 surface.
 *
 * Issue #59 ("stdcell path derives from RTL_WORKSPACE, which the agent
 * legitimately re-points") is a *resolution* bug: the standard-cell models are
 * looked for under a workspace-shaped pointer, so any caller that re-points
 * that pointer gets `outcome: stdcell_cache_missing` from an otherwise fine
 * synthesis run. This spec drives the whole real chain on the deployed app —
 * design → RTL sim → hosted ORFS synthesis (bounded at `synth`) → post-synth
 * sim — and reports what post-synth resolution actually produced:
 * `resolvedNetlist`, `stdcellSource`, `outcome`.
 *
 * Honest scope (read this before trusting a green run): the tool call below
 * goes through REST `/invoke`, i.e. the BACKEND MAIN PROCESS — per the issue's
 * own evidence table that is the leg which already worked (`RTL_WORKSPACE` =
 * the container default). The leg that #59 breaks is the agent turn, which
 * runs the tools in a codex SUBPROCESS with `RTL_WORKSPACE` re-pointed to the
 * scratch base. So a pass here proves post-synth sim works for UI/REST/MCP
 * callers on this deployment; it does NOT by itself prove the agent leg is
 * fixed. What it does prove, on any build, is whether the deployed image can
 * resolve stdcells for a real ORFS netlist at all — the failure shape #59
 * describes is asserted against explicitly, with the evidence in the message.
 *
 * Cost: one real Cloud Run ORFS job. `max_stage='synth'` keeps it bounded —
 * it still writes 1_synth.v and the sim contract post-synth resolution reads,
 * without paying for place & route.
 */

const log = (...a: unknown[]) => console.log("[POSTSYNTH]", ...a);

/** 4-bit synchronous-reset counter. Plain `module counter` (no lifetime
 *  qualifier — that trick belongs to the smoke spec), no parameters: a
 *  parameter-free design is what a gate netlist can honestly stand in for. */
const COUNTER_V = `// 4-bit counter — small, synthesizable, parameter-free.
module counter (
    input  wire       clk,
    input  wire       rst,
    output reg  [3:0] q
);
    always @(posedge clk) begin
        if (rst) q <= 4'd0;
        else     q <= q + 4'd1;
    end
endmodule
`;

/**
 * Testbench that runs unchanged against the RTL and against the sky130hd gate
 * netlist: it instantiates `counter` BY PORT NAME with no parameter overrides
 * (a parameterized instantiation of a parameter-free gate netlist is the known
 * out-of-scope failure called out in #59), and it checks a value the two are
 * required to agree on.
 *
 * Timeline: clock posedges at 5,15,25,35,… ns. rst falls at t=32, so the
 * posedges at 5/15/25 load 0 and the ones at 35,45,55,65,75 count 1..5. The
 * check happens at t=80 — 5 ns clear of either neighbouring edge, so it is
 * insensitive to whether the models are zero-delay.
 */
const COUNTER_TB_V = `\`timescale 1ns/1ps
module counter_tb;
    reg clk = 1'b0;
    reg rst = 1'b1;
    wire [3:0] q;

    counter dut (.clk(clk), .rst(rst), .q(q));

    always #5 clk = ~clk;

    initial begin
        $dumpfile("counter_tb.vcd");
        $dumpvars(0, counter_tb);
        #32 rst = 1'b0;   // three reset edges taken (t=5,15,25)
        #48;              // five counting edges taken (t=35..75); now t=80
        if (^q === 1'bx) begin
            $display("TEST FAILED: q is unknown (x/z) at t=80");
        end else if (q !== 4'd5) begin
            $display("TEST FAILED: expected q=5 at t=80, got q=%0d", q);
        end else begin
            $display("TEST PASSED");
        end
        $finish;
    end
endmodule
`;

/** The sc#59 failure shape, as it reaches a caller.
 *  - `outcome: "stdcell_cache_missing"` — src/tools/run_simulation.py:453,
 *    carried onto the run record at src/tools/sim_manager.py:412.
 *  - the message text raised by src/tools/stdcells.py resolve_stdcell_models
 *    and matched by `_is_stdcell_cache_error` (run_simulation.py:13-15).
 *  - unresolved gate primitives: the models were not compiled in at all, so
 *    iverilog reports the cells as unknown module types. */
const STDCELL_OUTCOME = "stdcell_cache_missing";
const STDCELL_TEXT = [
  /Standard-cell cache missing/i,
  /No stdcell model files found/i,
  /Unknown module type:\s*sky130_fd_sc_hd__/i,
  /bootstrap_stdcells/i,
];

interface SimRunRecord {
  id?: string;
  status?: string;
  mode?: string;
  outcome?: string;
  recovery?: { kind?: string; label?: string; detail?: string } | null;
  resolvedRunId?: string | null;
  resolvedNetlist?: string | null;
  stdcellSource?: string | null;
  passMarkerFound?: boolean;
  failure?: { type?: string; firstFailureLine?: string; timeNs?: number | null } | null;
  logFile?: string;
  stdoutTail?: string;
  stderrTail?: string;
  compileCommand?: string;
}

test("staging: post-synthesis simulation resolves stdcells and reaches a verdict (sc#59)", async ({
  page,
}) => {
  test.skip(!EMAIL || !PASSWORD, "STAGING_EMAIL / STAGING_PASSWORD not provided");
  // A real hosted ORFS job dominates this test; the global 300s timeout is for
  // the UI-only spec. Bounded at `synth` a sky130hd counter is minutes, but a
  // cold Cloud Run job + image pull has been 20+.
  test.setTimeout(35 * 60_000);

  const evidence: Record<string, unknown> = {};
  const dump = () => fs.writeFileSync(`${ARTIFACTS}/postsynth-results.json`, JSON.stringify(evidence, null, 2));

  // --- 1. sign in ----------------------------------------------------------
  await signIn(page, "ps-");

  // --- 2. session + a small synthesizable design ---------------------------
  const sid = await newSession(page, `psynth_${Date.now().toString(36)}`);
  evidence.sessionId = sid;
  await expect(page.getByTestId("workbench-v2")).toBeVisible({ timeout: 60_000 });
  await createFileViaUi(page, "counter.v", COUNTER_V);
  await createFileViaUi(page, "counter_tb.v", COUNTER_TB_V);
  await shot(page, "ps-05-files-created");

  // --- 3. one RTL sim: sanity check AND the app's own bearer + API origin ---
  // (proven pattern from staging.spec.ts — the token is captured off the app's
  // request, never minted by the test)
  const sim1 = await simulateViaPalette(page);
  evidence.rtlSim = sim1.body;
  log("rtl sim:", JSON.stringify(sim1.body?.run ?? sim1.body).slice(0, 600));
  expect(sim1.body.run.status, "RTL sim must pass before post-synth is meaningful").toBe("passed");
  await shot(page, "ps-06-rtl-sim-passed");

  const { apiOrigin, bearer } = sim1;
  const authHeaders: Record<string, string> = bearer ? { authorization: bearer } : {};
  const wsPath = `/api/workspace/${encodeURIComponent(sid)}`;
  const apiGet = (path: string, timeout = 60_000) =>
    page.request.get(`${apiOrigin}${path}`, { headers: authHeaders, timeout });
  const apiPost = (path: string, data: unknown, timeout = 120_000) =>
    page.request.post(`${apiOrigin}${path}`, { headers: authHeaders, data, timeout });
  const jsonOf = async (r: APIResponse) => {
    const text = await r.text();
    try {
      return JSON.parse(text);
    } catch {
      return { ok: false, parseError: true, raw: text.slice(0, 2000) };
    }
  };

  // The manifest is the single source of truth for the tops — assert what the
  // synthesis dispatch below will actually resolve, rather than assuming it.
  const manifest = (await jsonOf(await apiGet(`${wsPath}/manifest`))).manifest;
  evidence.manifest = manifest;
  log("manifest:", JSON.stringify({ synthTop: manifest?.synthTop, simTop: manifest?.simTop, platform: manifest?.platform }));
  expect(manifest.synthTop).toBe("counter");
  expect(manifest.simTop).toBe("counter_tb");

  // --- 4. dispatch synthesis, the same route the Synthesize command uses ----
  // frontend/lib/commands.ts:350 -> workbenchApi.synthesize (frontend/lib/api.ts:489)
  // -> POST /api/workspace/{sid}/synthesize (src/api/actions.py:647), which
  // calls start_synthesis_job with the manifest's synth set.
  const dispatchResp = await apiPost(`${wsPath}/synthesize`, {
    platform: "sky130hd",
    maxStage: "synth", // bounded: writes 1_synth.v + the sim contract, skips PnR
    clockPeriodNs: 10,
  });
  const dispatch = await jsonOf(dispatchResp);
  evidence.synthDispatch = dispatch;
  log("synthesize dispatch:", dispatchResp.status(), JSON.stringify(dispatch).slice(0, 800));
  expect(dispatchResp.ok(), `synthesize dispatch failed: ${JSON.stringify(dispatch).slice(0, 600)}`).toBeTruthy();
  const runId: string = dispatch.runId;
  expect(runId, "no runId returned by /synthesize").toBeTruthy();
  log("synthesis run_id:", runId);
  await shot(page, "ps-07-synth-dispatched");

  // --- 5. poll get_synthesis_status until terminal --------------------------
  // The user-gesture Refresh does exactly this: invokeTool("get_synthesis_status",
  // { run_id }) — frontend/components/workbench/runStatus.ts:62 ->
  // POST /api/workspace/{sid}/invoke (src/api/actions.py:778).
  const POLL_CAP_MS = 25 * 60_000;
  const startedAt = Date.now();
  let status: Record<string, any> = {};
  let lastReported = "";
  const transitions: { atSec: number; status: string; stage: string }[] = [];

  for (;;) {
    const elapsed = Date.now() - startedAt;
    if (elapsed > POLL_CAP_MS) {
      evidence.synthStatus = status;
      evidence.synthTransitions = transitions;
      dump();
      throw new Error(
        `synthesis ${runId} did not reach a terminal state within ${Math.round(POLL_CAP_MS / 60_000)} min ` +
          `(last status=${status.status} stage=${status.stage}); last log lines:\n` +
          `${(status.last_log_lines || []).slice(-15).join("\n")}`
      );
    }

    const res = await jsonOf(await apiPost(`${wsPath}/invoke`, {
      tool: "get_synthesis_status",
      arguments: { run_id: runId },
    }, 180_000));
    status = (res?.result ?? {}) as Record<string, any>;

    const line = `${status.status}/${status.stage}`;
    if (line !== lastReported) {
      const atSec = Math.round((Date.now() - startedAt) / 1000);
      transitions.push({ atSec, status: String(status.status), stage: String(status.stage) });
      log(`t+${atSec}s status=${status.status} stage=${status.stage} backend=${status.backend} elapsed=${status.elapsed_sec}`);
      lastReported = line;
    }
    if (status.status === "completed" || status.status === "failed") break;

    // Honor the server's own backoff guidance (poll_after_sec / retry_after_sec
    // when rate limited) — invariant #6: the client never invents a cadence.
    const suggested = Number(status.retry_after_sec ?? status.poll_after_sec ?? 15);
    const waitMs = Math.min(Math.max(Number.isFinite(suggested) ? suggested : 15, 5), 60) * 1000;
    await page.waitForTimeout(waitMs);
  }

  evidence.synthStatus = status;
  evidence.synthTransitions = transitions;
  dump();
  log(
    "synthesis terminal:",
    JSON.stringify({
      status: status.status,
      stage: status.stage,
      elapsed_sec: status.elapsed_sec,
      artifacts: status.artifacts_found,
      next_action: status.next_action,
    }).slice(0, 1200)
  );
  await shot(page, "ps-08-synth-terminal");
  expect(
    status.status,
    `synthesis ${runId} ended '${status.status}' at stage '${status.stage}'. Last log lines:\n` +
      `${(status.last_log_lines || []).slice(-20).join("\n")}`
  ).toBe("completed");

  // --- 6. THE sc#59 SURFACE: post-synth simulation --------------------------
  // run_isolated_simulation(sim_top, mode='post_synth', run_id) — the same
  // @tool the agent calls (src/tools/wrappers.py:318), executed through the one
  // registry via /invoke. `run_id` pins which synthesis run's sim contract
  // resolves the netlist (src/tools/sim_contract.py:144 resolve_post_synth).
  const simResp = await apiPost(`${wsPath}/invoke`, {
    tool: "run_isolated_simulation",
    arguments: { sim_top: "counter_tb", mode: "post_synth", run_id: runId },
  }, 10 * 60_000);
  const simEnvelope = await jsonOf(simResp);
  evidence.postSynthEnvelope = simEnvelope;
  dump();

  log("post-synth /invoke http:", simResp.status());
  log("post-synth result:", JSON.stringify(simEnvelope).slice(0, 3000));
  await shot(page, "ps-09-postsynth-invoked");

  expect(
    simResp.ok(),
    `post-synth /invoke failed (${simResp.status()}): ${JSON.stringify(simEnvelope).slice(0, 900)}`
  ).toBeTruthy();

  const run: SimRunRecord = (simEnvelope.result ?? {}) as SimRunRecord;

  // --- 7. report honestly ---------------------------------------------------
  const failureText = [
    run.failure?.firstFailureLine ?? "",
    run.stderrTail ?? "",
    run.stdoutTail ?? "",
    JSON.stringify(run.recovery ?? {}),
  ].join("\n");

  log("post-synth verdict:", run.status, "| outcome:", run.outcome);
  log("resolved run:", run.resolvedRunId, "| netlist:", run.resolvedNetlist, "| stdcellSource:", run.stdcellSource);
  if (run.failure) log("failure:", JSON.stringify(run.failure).slice(0, 800));
  if (run.stderrTail) log("stderr tail:", run.stderrTail.slice(0, 1500));

  // The bootstrap hint prints the workspace the resolver looked in — on the
  // #59 build that string is the smoking gun (it read the scratch ROOT, not
  // the PDK location). Surface it verbatim when present.
  const looked = /--workspace\s+"?([^"\s]+)"?/.exec(failureText);
  if (looked) log("resolver looked for stdcells under:", looked[1]);

  // Pull the run's own log — the durable evidence, workspace-relative.
  if (run.logFile) {
    const logResp = await apiGet(`${wsPath}/file/${encodeURIComponent(run.logFile)}`, 60_000);
    if (logResp.ok()) {
      const content = String((await jsonOf(logResp)).content ?? "");
      evidence.postSynthLogTail = content.slice(-4000);
      log("sim.log tail:\n" + content.slice(-2500));
    }
  }
  dump();

  // (a) A definitive verdict: the run reached a real status, in post_synth
  //     mode, against a real gate netlist. No ambiguity (invariant #4).
  expect(run.mode).toBe("post_synth");
  expect(["passed", "failed"], `post-synth run has no definitive verdict: ${JSON.stringify(run).slice(0, 900)}`)
    .toContain(String(run.status));
  expect(run.resolvedRunId, "post-synth did not resolve a synthesis run").toBe(runId);
  expect(run.resolvedNetlist, "post-synth resolved no gate netlist").toBeTruthy();

  // (b) The sc#59 assertion: it must NOT be a stdcell-resolution failure.
  //     Fail loudly, with the evidence in the message — on the unfixed build
  //     this is exactly what reproduces.
  const sc59 = [
    run.outcome === STDCELL_OUTCOME ? `outcome=${STDCELL_OUTCOME}` : "",
    ...STDCELL_TEXT.filter((re) => re.test(failureText)).map((re) => `matched ${re}`),
    run.recovery?.kind === "infra" ? `recovery.kind=infra ("${run.recovery?.label ?? ""}")` : "",
  ].filter(Boolean);

  expect(
    sc59,
    "sc#59 REPRODUCED — post-synth simulation failed on standard-cell resolution.\n" +
      `  session      : ${sid}\n` +
      `  synth run    : ${runId} (status ${status.status}, stage ${status.stage})\n` +
      `  sim run      : ${run.id} (status ${run.status}, outcome ${run.outcome})\n` +
      `  resolvedNetlist: ${run.resolvedNetlist}\n` +
      `  stdcellSource  : ${run.stdcellSource}\n` +
      (looked ? `  looked under   : ${looked[1]}\n` : "") +
      `  evidence     :\n${failureText.slice(0, 2000)}`
  ).toEqual([]);

  // (c) With the models resolved, this TB and this netlist must agree. A
  //     failure here is a design/TB problem, not a platform one — say so.
  expect(
    run.status,
    `post-synth sim ran with stdcells resolved (${run.stdcellSource}) but did not pass — ` +
      `this is a design/TB-level failure, not sc#59: ${run.failure?.firstFailureLine ?? run.stderrTail ?? ""}`
  ).toBe("passed");
  expect(run.passMarkerFound).toBeTruthy();

  await shot(page, "ps-10-postsynth-passed");
  dump();
});
