import { test, expect } from "@playwright/test";
import fs from "node:fs";
import {
  ARTIFACTS,
  EMAIL,
  PASSWORD,
  attachBearerCapture,
  bearerAgeSec,
  createFileViaUi,
  looksUnauthorized,
  newSession,
  openRunsDock,
  parseToolResult,
  readBody,
  shot,
  signIn,
  simulateViaPalette,
  warmAuth,
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
  // Subscribe to the app's tokens BEFORE it makes its first authenticated
  // request, then never hold a token of our own (see the auth-freshness note
  // at the poll loop).
  const bearers = attachBearerCapture(page);
  await signIn(page, "ps-");
  log(`bearer captured: rotations=${bearers.rotations} origin=${bearers.origin}`);

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

  // The origin the APP itself talks to (it may be the backend directly or the
  // frontend's same-origin /api proxy, app/api/[...path]/route.ts) — taken from
  // the app's own simulate request, with the passive capture as a backstop.
  const apiOrigin = sim1.apiOrigin || bearers.origin;
  const wsPath = `/api/workspace/${encodeURIComponent(sid)}`;

  /** Headers built at CALL time from the live holder — never from a constant
   *  captured minutes ago. */
  const authHeaders = (): Record<string, string> =>
    bearers.value ? { authorization: bearers.value } : {};

  /** Every raw-body log goes through here: HTTP status + the first 300 chars.
   *  This is what run 31341766743 was missing. */
  const logRaw = (tag: string, res: { status: number; raw: string }) =>
    log(`[RAW ${tag}] http=${res.status} bearerAge=${bearerAgeSec(bearers)}s body=${JSON.stringify(res.raw.slice(0, 300))}`);

  /** One request, then — if it looks unauthorized — ONE warm-and-retry with the
   *  freshest token the app has minted since. The warm gesture is a real click
   *  on the dock's Refresh, so the retry uses a token the page just used
   *  successfully itself. */
  const apiCall = async (
    method: "get" | "post",
    path: string,
    opts: { data?: unknown; timeout?: number; tag: string }
  ) => {
    const timeout = opts.timeout ?? 120_000;
    const send = async () =>
      readBody(
        method === "get"
          ? await page.request.get(`${apiOrigin}${path}`, { headers: authHeaders(), timeout })
          : await page.request.post(`${apiOrigin}${path}`, { headers: authHeaders(), data: opts.data, timeout })
      );

    let res = await send();
    if (looksUnauthorized(res)) {
      logRaw(`${opts.tag}:401`, res);
      log(`[AUTH] ${opts.tag} looked unauthorized — warming the app's token and retrying once`);
      await warmAuth(page);
      await page.waitForTimeout(1_000);
      res = await send();
      log(`[AUTH] retry of ${opts.tag}: http=${res.status} bearerAge=${bearerAgeSec(bearers)}s rotations=${bearers.rotations}`);
    }
    return res;
  };

  const apiGet = (path: string, tag: string, timeout = 60_000) =>
    apiCall("get", path, { tag, timeout });
  const apiPost = (path: string, data: unknown, tag: string, timeout = 120_000) =>
    apiCall("post", path, { data, tag, timeout });

  // The manifest is the single source of truth for the tops — assert what the
  // synthesis dispatch below will actually resolve, rather than assuming it.
  const manifestRes = await apiGet(`${wsPath}/manifest`, "manifest");
  const manifest = manifestRes.json?.manifest;
  if (!manifest) logRaw("manifest", manifestRes);
  evidence.manifest = manifest;
  log("manifest:", JSON.stringify({ synthTop: manifest?.synthTop, simTop: manifest?.simTop, platform: manifest?.platform }));
  expect(manifest?.synthTop).toBe("counter");
  expect(manifest?.simTop).toBe("counter_tb");

  // --- 4. dispatch synthesis, the same route the Synthesize command uses ----
  // frontend/lib/commands.ts:350 -> workbenchApi.synthesize (frontend/lib/api.ts:489)
  // -> POST /api/workspace/{sid}/synthesize (src/api/actions.py:647), which
  // calls start_synthesis_job with the manifest's synth set.
  const dispatchRes = await apiPost(
    `${wsPath}/synthesize`,
    {
      platform: "sky130hd",
      maxStage: "synth", // bounded: writes 1_synth.v + the sim contract, skips PnR
      clockPeriodNs: 10,
    },
    "synthesize"
  );
  evidence.synthDispatch = dispatchRes.json ?? dispatchRes.raw;
  log("synthesize dispatch: http=", dispatchRes.status, JSON.stringify(dispatchRes.json ?? "").slice(0, 800));
  if (!dispatchRes.json?.runId) logRaw("synthesize", dispatchRes);
  expect(dispatchRes.ok, `synthesize dispatch failed (${dispatchRes.status}): ${dispatchRes.raw.slice(0, 600)}`).toBeTruthy();
  const runId: string = dispatchRes.json?.runId;
  expect(runId, `no runId returned by /synthesize: ${dispatchRes.raw.slice(0, 300)}`).toBeTruthy();
  log("synthesis run_id:", runId);
  await shot(page, "ps-07-synth-dispatched");

  // --- 5. poll get_synthesis_status until terminal --------------------------
  //
  // AUTH-FRESHNESS DESIGN (learned from staging run 31341766743, where a single
  // captured bearer expired at ~5 min and every later poll silently degraded to
  // `status=undefined`):
  //
  //   PRIMARY  — the app's OWN Refresh gesture. The Runs dock renders a
  //   per-run refresh button (data-testid `run-refresh-<id>`,
  //   components/workbench/RunsPane.tsx:184-194) which calls
  //   refreshRunStatus -> invokeTool("get_synthesis_status") — the documented
  //   user gesture (runStatus.ts:56-65). We click it and read the app's own
  //   /invoke RESPONSE as the poll result. No bearer is involved at all: the
  //   page always sends its live, SDK-refreshed token (lib/auth.tsx onRefresh).
  //
  //   FALLBACK — a direct /invoke with the freshest token the passive capture
  //   has seen, plus one warm-and-retry on an unauthorized shape. Needed
  //   because the refresh button unmounts as soon as the run is terminal
  //   (RunsPane.tsx:175 `!isTerminal(...)`), and because a dock/tab layout
  //   change must degrade to a slower poll, not to a hung test.
  //
  // Either way the page keeps making requests every iteration, so the captured
  // bearer can never go stale again — freshness is a side effect of the poll,
  // not a thing the test has to remember.
  const POLL_CAP_MS = 25 * 60_000;
  const startedAt = Date.now();
  let status: Record<string, any> = {};
  let lastReported = "";
  const transitions: { atSec: number; status: string; stage: string; via: string }[] = [];

  await openRunsDock(page);
  await warmAuth(page); // hydrate the runs table so the API-dispatched run has a row

  /** Poll via the app's own Refresh button; null when that path isn't available. */
  const pollViaGesture = async (): Promise<Record<string, any> | null> => {
    const btn = page.getByTestId(`run-refresh-${runId}`);
    if (!(await btn.count())) return null;
    try {
      const [resp] = await Promise.all([
        page.waitForResponse(
          (r) => r.url().includes("/invoke") && r.request().method() === "POST",
          { timeout: 60_000 }
        ),
        btn.first().click({ timeout: 10_000 }),
      ]);
      const res = await readBody(resp);
      const parsed = parseToolResult(res.json?.result);
      if (!parsed?.status) {
        logRaw("gesture-invoke", res);
        return null;
      }
      return parsed;
    } catch {
      return null;
    }
  };

  /** Poll via a direct /invoke with the freshest captured bearer. */
  const pollViaApi = async (): Promise<Record<string, any>> => {
    const res = await apiPost(
      `${wsPath}/invoke`,
      { tool: "get_synthesis_status", arguments: { run_id: runId } },
      "status-invoke",
      180_000
    );
    const parsed = parseToolResult(res.json?.result);
    if (!parsed?.status) {
      // The exact hole that hid the expiry: expected field absent -> RAW.
      logRaw("status-invoke", res);
      return {};
    }
    return parsed;
  };

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

    let via = "gesture";
    let next = await pollViaGesture();
    if (!next) {
      via = "api";
      next = await pollViaApi();
    }
    // An empty read is an ERROR, not a status — never overwrite a known status
    // with nothing (invariant #4: honest state, no ambiguous verdicts).
    if (next.status) status = next;
    else log(`t+${Math.round((Date.now() - startedAt) / 1000)}s poll produced NO status (via ${via}) — see [RAW] above`);

    const line = `${status.status}/${status.stage}`;
    if (line !== lastReported) {
      const atSec = Math.round((Date.now() - startedAt) / 1000);
      transitions.push({ atSec, status: String(status.status), stage: String(status.stage), via });
      log(
        `t+${atSec}s status=${status.status} stage=${status.stage} via=${via} backend=${status.backend} ` +
          `elapsed=${status.elapsed_sec} bearerAge=${bearerAgeSec(bearers)}s rotations=${bearers.rotations}`
      );
      // The ORFS job's own tail — the only view of a cold-starting Cloud Run job.
      const tail: string[] = status.last_log_lines || [];
      if (tail.length) log(`  last_log_lines (${status.last_log_source}):\n    ${tail.slice(-8).join("\n    ")}`);
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
  // Freshness matters most here: this call lands ~25 min after sign-in. It goes
  // through the same warm-and-retry wrapper, and we warm the token immediately
  // before, so the request carries a bearer the page minted seconds ago.
  await warmAuth(page);
  const simRes = await apiPost(
    `${wsPath}/invoke`,
    { tool: "run_isolated_simulation", arguments: { sim_top: "counter_tb", mode: "post_synth", run_id: runId } },
    "postsynth-invoke",
    10 * 60_000
  );
  evidence.postSynthEnvelope = simRes.json ?? simRes.raw;
  dump();

  log(`post-synth /invoke http=${simRes.status} bearerAge=${bearerAgeSec(bearers)}s rotations=${bearers.rotations}`);
  log("post-synth result:", JSON.stringify(simRes.json ?? "").slice(0, 3000));
  await shot(page, "ps-09-postsynth-invoked");

  if (!simRes.json?.result) logRaw("postsynth-invoke", simRes);
  expect(
    simRes.ok,
    `post-synth /invoke failed (${simRes.status}): ${simRes.raw.slice(0, 900)}`
  ).toBeTruthy();

  const run: SimRunRecord = (parseToolResult(simRes.json?.result) ?? {}) as SimRunRecord;
  expect(
    Object.keys(run).length,
    `post-synth /invoke returned no parsable run record (http=${simRes.status}): ${simRes.raw.slice(0, 600)}`
  ).toBeGreaterThan(0);

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
    const logRes = await apiGet(`${wsPath}/file/${encodeURIComponent(run.logFile)}`, "sim-log", 60_000);
    const content = typeof logRes.json?.content === "string" ? logRes.json.content : null;
    if (content === null) logRaw("sim-log", logRes);
    else {
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
