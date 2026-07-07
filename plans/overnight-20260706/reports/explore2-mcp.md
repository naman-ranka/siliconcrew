# explore2-mcp — 8-tap FIR through the hosted MCP server (external-app view)

Agent posture: an EXTERNAL AI app driving SiliconCrew's hosted backend through
the `claude.ai Silicon crew` MCP connector (`mcp__claude_ai_Silicon_crew__*`).
Design: medium-hard 8-tap signed FIR (WIDTH=16, N=8) inspired by ASU p9. RTL +
self-checking TB authored clean-room (nothing shipped). ~90-min budget.

- **Session:** `x2_fir_mcp_20260707` (owner workos_user_01KWXD6VJZ0KHBGJT8EGSF2EZH — my own; not deleted)
- **Synthesis run:** `synth_0001` — **COMPLETED, real `6_final.gds` produced** (full RTL→GDS)
- **Verdict:** the engine is capable and honest end-to-end (clean-room FIR → sim →
  real GDS with honest failing-timing metrics). The weak points are all on the
  hosted **plumbing/legibility** side: after the heavy synth the server degraded
  into `-32602`/hangs, and the purpose-built PD-summary tool family was unusable.

## What I did (narrative)

1. **Setup.** `create_session_tool` → session live, real workos owner (connector
   NOT stale at start; F15 not reproduced on entry). `get_current_session` OK.
2. **Authoring.** `write_spec` (FIR, 8ns, sky130hd) auto-generated `constraints.sdc`.
   `write_file` fir_filter.v (direct-form, flattened `h_flat[k*WIDTH +: WIDTH]`
   coeff bus, 1-cycle registered MAC) + fir_filter_tb.v (self-checking, recomputes
   the convolution each cycle, independent of any constant table).
3. **Manifest.** `get_manifest` auto-populated roles/tops CORRECTLY (rtl/tb/sdc,
   synthTop=fir_filter, simTop=fir_filter_tb). Only clock was wrong (10.0 despite
   the 8ns spec) → `update_manifest` set clockPeriodNs=8.0. (`sessionId` field
   came back `""`.)
4. **Lint.** `linter_tool` verilator (RTL) + iverilog (RTL+TB) → both "Syntax OK".
5. **Sim.** `run_isolated_simulation` (sim_0001) → **passed**, outputs exactly
   `1,4,10,20,35,56,84,120` (matches p9 reference). `passMarkerFound:true` honest.
6. **Edits.** `edit_file_tool` (RTL comment) OK first try. `apply_patch_tool`
   REJECTED a context-only diff, then applied once I supplied line-numbered hunks.
   `simulation_tool` (non-isolated) re-verified → still passes, new `$display` line
   present (edits confirmed live, not just claimed).
7. **Viewers / search.** `waveform_tool` returned correct transitions but only after
   I switched to ps-scale windows (see X2M-6). `schematic_tool` FAILED (no docker,
   X2M-5). `search_logs_tool` pre-synth → "No log files found" (OpenROAD-only; does
   NOT cover sim logs).
8. **Alt families (hosted support probe).** `compile_dslx_to_ir` (XLS) → real IR
   (sign_ext/smul/add). `sby_tool` (formal, z3) → **PASSED** a zero-coeff→zero-output
   property. Both work on hosted despite no docker (different backends than schematic).
9. **Synthesis.** `start_synthesis` (finish, sky130hd, 8ns) → synth_0001. `synth`
   stage ran **~14 min** with `last_log_lines` empty throughout (X2M-8). Flow then
   completed all stages → **real GDS**. `auto_checks.equiv = skip` (F9 LEC_CHECK=0
   fix in action → no CTS SIGILL; F9 re-confirmed).
10. **Results captured before degradation:** `get_synthesis_status` returned full
    metrics (area 85157.9 µm², 8171 cells, **WNS -6.36 ns**, TNS -172.9, fmax 69.6
    MHz — honest failing timing for an unpipelined MAC at 8ns). `search_logs_tool`
    (post-synth) showed the honest slack progression (fp -5.63 → gp -7.55 → dp -7.47
    → cts -6.41). `save_metrics_tool` + `generate_report_tool` → honest report
    ("Timing requirement NOT MET", 69.6 MHz).
11. **Degradation.** The five dedicated PD tools (`get_synthesis_metrics`,
    `read_stage_report`, `get_cts_summary`, `get_congestion_summary`,
    `get_route_drc_summary`) returned `-32602` throughout. Then even basic
    `read_spec`/`list_files_tool`/`get_current_session` began flapping to `-32602`,
    and two `get_synthesis_status`/`wait_for_synthesis` calls hung >300s and were
    client-aborted. `retry_pd` (planned single F9b probe) was blocked by this
    degradation. I stopped hammering the shared instance.

## Findings

| ID | Severity | Status | Evidence (tool · args · response) |
|----|----------|--------|-----------------------------------|
| X2M-1 | HIGH (availability) | OPEN | After synth_0001 completed, hosted MCP degraded into sustained failures. Exact sequence: `get_synthesis_status`/`wait_for_synthesis(run_id=synth_0001)` each hung >300s → client abort ("sent no response or progress for 300s"), TWICE; then repeated `get_synthesis_metrics`/`read_spec`/`list_files_tool`/`get_current_session()` → `-32602`. `get_current_session` had succeeded 3× earlier, so this is a NEW degraded state, not a stale connector. Best-supported hypothesis: F2's unconditional whole-workspace `provider.sync()` in `session_request_scope` — the post-synth workspace ballooned (20 ODBs, 2 GDS, 8 report dirs) so every file-touching call now tars+PUTs a huge tree → stalls/times out → mapped to `-32602`. This upgrades F2 from "perf" to an **availability** failure: a completed synthesis makes the session's own tools unusable. |
| X2M-2 | HIGH (tooling) | OPEN | The dedicated PD-summary/metrics/stage-report family is unusable on hosted for a COMPLETED run whose data plainly exists. `get_synthesis_metrics(run_id=synth_0001)`, `read_stage_report(stage=finish)`, `get_cts_summary`, `get_congestion_summary`, `get_route_drc_summary` → all `-32602`, including `get_cts_summary()` with NO run_id (so run_id resolution is not the cause). Yet on the SAME run and SAME minute, `get_synthesis_status` returned all those metrics inline, and `search_logs_tool`/`save_metrics_tool`/`generate_report_tool` succeeded. An external app that calls the purpose-built summary tools (the obvious choice) gets nothing; the data is only reachable via status + search_logs + report. Compounds F12: the tools built FOR legibility are the ones that fail. |
| X2M-3 | MEDIUM (ops) | OPEN (confirms F9c) | Every degraded/backend condition surfaced as JSON-RPC `-32602 "Invalid request parameters"` despite valid args — a lie that sends external-app devs hunting a nonexistent bad-arg bug. Fresh, broad evidence across ~8 distinct tools. Map to `-32000` server-error + retry hint (F9c). |
| X2M-4 | MEDIUM (contract) | OPEN | `wait_for_synthesis` is documented as a BOUNDED wait (≤120s; I passed max_wait_sec=120) and `get_synthesis_status` as a fast reconciling read, but both exceeded 300s of silence and were client-aborted. Invariant-6 "bounded wait" and invariant-5 "every read reconciles, no run stuck" were not honored under load — a read/bounded-wait must return within its ceiling even when the sync/reconcile path is slow. |
| X2M-5 | MEDIUM (availability) | OPEN | `schematic_tool(verilog_file=fir_filter.v, top_module=fir_filter)` → "Failed to generate schematic: Yosys Failed: failed to connect to the docker API at unix:///var/run/docker.sock ... daemon is running". Yosys-schematic needs local docker, absent on the Cloud Run instance. Raw docker-socket error leaks to the external app; an honest "schematic not available on hosted" is warranted. (Contrast: synthesis, `sby_tool`, and XLS all work on hosted via their own backends — so this is a gap specific to the schematic path.) |
| X2M-6 | LOW-MED (legibility) | OPEN | `waveform_tool` (a) renders values in raw BINARY with no radix label (`y_out=1010100` for decimal 84, `x_in=1000` for 8) and (b) takes start/end in undocumented VCD-native units. With `timescale 1ns/1ps` the VCD is ps, so a natural ns window `start=20,end=100` → "No events found in this time window."; `start=0,end=90000` was needed. A hardware designer expects hex/dec and a unit hint. Values themselves were correct. |
| X2M-7 | LOW (friction) | OPEN | `apply_patch_tool` rejected a context-only unified diff (`@@ ... @@` header) with `{"success": false, "message": "Patch check failed: error: No valid patches in input"}`. Only a fully line-numbered hunk (`@@ -68,5 +68,6 @@`) applied. Many agents emit context-only hunks; either accept them or document the requirement. (`edit_file_tool` worked first try — prefer it.) |
| X2M-8 | LOW (perf/visibility) | OPEN | `synth` stage ran ~14 min (dispatch 06:51 → all stages ended 07:05:46) with `last_log_lines: []` the WHOLE time — zero progress signal — for an 8-tap FIR. Cause is the design: an unpipelined combinational 8×(16×16) MAC + 36-bit adder tree is a huge combinational cone that ABC maps slowly (8171 cells). Not a bug, but a first-timer sees a silent 14-min "running". Feeds F12 (make long/opaque stages legible; consider streaming synth log lines like PD stages). |
| X2M-9 | LOW (metric sanity) | OPEN | Reported total power = 256000 µW = **256 mW** for an 8171-cell sky130 FIR, shown ✅ (no sanity flag) in both `get_synthesis_status.summary_metrics` and `generate_report_tool`. Plausibly a units/parse artifact (256 mW is high for this size). Worth a sanity check / range flag; reported as an unconfirmed concern, not a proven bug. |
| X2M-10 | LOW (honesty, minor) | OPEN | All eight `stage_history` `ended_at` values are identical (`2026-07-07T07:05:46+00:00`) — reconcile batch-stamped them, so per-stage timing is not preserved (known deferred "hosted per-stage timings"). Separately, `get_manifest`/`update_manifest` return `sessionId: ""` (empty) rather than the session id. |

## Positives to NOT regress

- **F9 re-confirmed (3rd+ independent):** `auto_checks.equiv = skip`, full RTL→GDS to a
  real `6_final.gds`, **no CTS SIGILL**. Dependable by construction, not luck.
- **Honest failing-timing surfacing:** WNS -6.36 ns, fmax 69.6 MHz, report says
  "Timing requirement NOT MET"; `search_logs` shows the real slack progression. The
  engine tells the truth about a deliberately-too-slow design.
- **Sim pass contract honest:** exact reference vector matched; `passMarkerFound` truthful.
- **Manifest auto-population** correct for roles/tops (only clock needed a nudge).
- **XLS DSLX→IR and SBY formal both work on hosted** — real IR nodes, real z3 proof.
- **generate_report_tool** produced a complete, honest spec-vs-results report.

## Toolset coverage matrix

| Tool | Result | Note |
|------|--------|------|
| create_session_tool | worked | |
| get_current_session | worked, then flapped | OK early; `-32602` under late degradation (X2M-1) |
| set_active_session | not-tried | session auto-active on create; never needed standalone |
| write_spec / read_spec | write worked; read failed | `read_spec` only attempted during degradation → `-32602` |
| write_file / read_file | worked | |
| get_manifest / update_manifest | worked | `sessionId:""` (X2M-10) |
| list_files_tool | failed | `-32602` (degradation window) |
| edit_file_tool | worked | first try |
| apply_patch_tool | worked w/ caveat | needs line-numbered hunks (X2M-7) |
| linter_tool | worked | verilator + iverilog |
| simulation_tool | worked | |
| run_isolated_simulation | worked | sim_0001 passed |
| waveform_tool | worked w/ caveat | binary values + ps units, no hints (X2M-6) |
| schematic_tool | FAILED | no docker on hosted (X2M-5) |
| search_logs_tool | worked | OpenROAD-only; "no logs" pre-synth |
| save_metrics_tool | worked | |
| generate_report_tool | worked | honest report |
| start_synthesis | worked | synth_0001 |
| get_synthesis_status | worked, then hung | full metrics early; >300s hang later (X2M-1/4) |
| wait_for_synthesis | worked, then hung | bounded contract broken under load (X2M-4) |
| get_synthesis_metrics | FAILED | `-32602` on completed run (X2M-2) |
| read_stage_report | FAILED | `-32602` (X2M-2) |
| get_cts_summary | FAILED | `-32602`, incl. no-run_id (X2M-2) |
| get_congestion_summary | FAILED | `-32602` (X2M-2) |
| get_route_drc_summary | FAILED | `-32602` (X2M-2) |
| compile_dslx_to_ir (XLS) | worked | real IR |
| sby_tool (formal) | worked | z3 PASS |
| retry_pd | not-tried | planned single F9b probe blocked by X2M-1 degradation |
| cocotb_tool | not-tried | covered the alt-family goal with XLS + formal |
| list_sessions_tool / load_yaml_spec_file | not-tried | tenancy covered by F1; load not needed (authored clean-room) |

## Key artifacts (run synth_0001, on the worker/GCS tree)

- GDS: `synth_runs/synth_0001/orfs_results/sky130hd/fir_filter/base/6_final.gds`
- Netlist: `.../base/6_final.v` · Finish report: `orfs_reports/.../6_finish.rpt`
- Metrics: area 85157.92 µm² · 8171 cells · WNS -6.36 ns · TNS -172.9 · fmax 69.6 MHz · power 256 mW (X2M-9)
