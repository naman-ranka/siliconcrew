# Hosted GDS verification (post-LEC-fix) — IN PROGRESS / BLOCKED on MCP connector

**Task:** Verify hosted spec→GDS now reaches routing→GDS after the LEC_CHECK=0
fix (backend rev siliconcrew-backend-00060), on flagship session
`asu_p1_mcp_20260706`. Also confirm the tenancy fix via `list_sessions_tool`.

**Status as of first attempt window (~2026-07-06 late):** BLOCKED — the hosted
`Silicon_crew` MCP connector (claude.ai side) is returning a persistent
`-32602 Invalid request parameters` on EVERY tool call and is not
re-handshaking. Backend itself is healthy. Verification not yet started.

## What was tried (chronological)

- ~15 calls to hosted `Silicon_crew` MCP tools over ~7+ minutes:
  `list_sessions_tool`, `get_current_session`, `set_active_session` (with a
  required param) — ALL returned `MCP error -32602: Invalid request parameters`.
- Waited 10s, 30s, 60s, and a full 120s idle window between batches to let the
  connector re-initialize. No change.
- The lead's runbook says `-32602` = stale session after redeploy, retry
  re-handshakes. It did NOT re-handshake after many retries + idle.

## Diagnosis (backend is healthy; the claude.ai connector is stale)

Direct probes of the hosted backend `https://siliconcrew-backend-psp2dkllmq-uc.a.run.app`:

- `GET /api/health` → **HTTP 200** `{"status":"healthy","version":"1.0.0",
  "workspace":"/workspace","sessions":35}`. Backend is up and serving.
- `POST /mcp` (initialize, no bearer) → **HTTP 401**
  `{"error":"missing_token","error_description":"Authentication required: no
  bearer token."}`. The MCP endpoint is alive and correctly enforcing OAuth.

**Conclusion:** The deploy did NOT break the backend or the `/mcp` mount. The
`-32602` is coming from the claude.ai-side `Silicon_crew` connector holding a
stale MCP session after the redeploy. Re-establishing it requires refreshing /
reconnecting the connector on the claude.ai side (fresh OAuth handshake) —
something the agent cannot do from the tool-call side, and there is no bearer
token available locally to drive `/mcp` directly.

Note: the health endpoint's `"sessions":35` is a backend-global count (all
session dirs on the instance), NOT an owner-scoped list, so it is NOT the
tenancy confirmation the mission asks for — that still needs a successful
`list_sessions_tool` call.

## Cross-check: rtl-codex MCP is a DIFFERENT backend (not a substitute)

The `rtl-codex` MCP server DID respond (proving general MCP plumbing works),
but it returned 100+ `claude-sonnet-5` auto-benchmark sessions, is not
owner-scoped, and does NOT contain `asu_p1_mcp_20260706`. That is the
local/self-host instance, not the hosted Cloud Run platform under test. It
cannot be used to verify the hosted LEC fix or the hosted tenancy fix.

## Next action

Escalated to team lead: refresh/reconnect the hosted `Silicon_crew` MCP
connector on the claude.ai side, then this verification resumes immediately
(list_sessions count + full spec→GDS on `asu_p1_mcp_20260706`). Continuing to
retry the connector periodically in the meantime.

## Refined verdict criteria (per team lead, folded in)

The hosted CTS SIGILL is a HETEROGENEOUS-CPU-POOL FLAKE — on the OLD rev, CTS
passed ~1 in 3 runs purely by landing on a compatible worker. So a single CTS
pass on rev 00060 does NOT prove the fix. The definitive proof:

1. **config.mk contains `export LEC_CHECK = 0`** (read via `read_file`/
   `list_files_tool` on the synth run dir) — proves the fix is engaged by
   construction (no LEC child exec'd → no SIGILL possible on any CPU).
2. **CTS passed with NO "illegal instruction" in logs** (search_logs_tool).
3. **Reached GDS** (artifacts_found.gds, 6_finish.rpt, metrics).
4. Must use a **FRESH start_synthesis on rev 00060** (the existing
   asu_p1_mcp_20260706 GDS was produced on the OLD rev by luck — don't rely on
   it). If cheap, run synthesis 2x to rule out luck.

## UI-path verification (after switching off the dead MCP connector)

Team lead confirmed the claude.ai MCP connector needs a manual OAuth reconnect
(owner offline) → switched to the frontend/Playwright path
(`https://siliconcrew-frontend-psp2dkllmq-uc.a.run.app/`), signed in as
rockstarme.the5@gmail.com ("Claude test"). Backend rev 00060.

### (a) Tenancy — owner-scoped Launcher
The Launcher shows exactly **2 sessions**, both owned by this account:
`asu_p1_mcp_20260706` and `first_session`. No foreign-tenant sessions. (This is
the UI-side confirmation of the tenancy fix; the MCP `list_sessions_tool` count
was unobtainable due to the connector, but the owner-scoped Launcher is
equivalent evidence — the pre-fix 33-session cross-owner leak is gone.)

### Session readiness
`asu_p1_mcp_20260706` opened in IDE. Files present: `seq_detector_0011.v` (RTL),
`seq_detector_0011_tb.v` (TB), `manifest.json`, `constraints.sdc`, plus spec
yaml. Manifest: `synthTop=seq_detector_0011`, `simTop=seq_detector_0011_tb`,
`clockPeriodNs=1.1`, `platform=sky130hd`, roles rtl/tb/sdc set. Run history
(proves F9's coin-flip): synth_0001 FAIL, synth_0002 FAIL, synth_0003 FAIL,
synth_0004 completed (old-rev lucky GDS, WNS 0.0ns / 14 cells).

### FRESH run on rev 00060 — synth_0005
Dispatched via Command palette → Synthesize options → **Max stage = finish**
(full RTL→GDS), platform sky130hd, clock 1.1ns, top seq_detector_0011.
Activity event: `start_synthesis {"run_id":"synth_0005","status":"queued"}`.

### (b) config.mk has LEC_CHECK=0 — CONFIRMED ✅ (DEFINITIVE PROOF)
Read `synth_runs/synth_0005/config.mk` in the file explorer. Full contents:
```
export DESIGN_NAME = seq_detector_0011
export PLATFORM = sky130hd
export VERILOG_FILES = /workspace/inputs/seq_detector_0011.v
export SDC_FILE = /workspace/constraints.sdc
export CORE_UTILIZATION = 5
export CORE_ASPECT_RATIO = 1.0
export CORE_MARGIN = 2.0
export NUM_CORES = 4
export LEC_CHECK = 0
```
**`export LEC_CHECK = 0` is present** on the fresh rev-00060 run → the LEC child
is disabled by construction → no SIGILL possible regardless of which CPU the
worker lands on. This is the dependable proof the lead asked for (a lone CTS
pass would not have been). Screenshot: gds-verify-config-mk-lec0.png.

## Verdict (so far)

- (a) tenancy — **CONFIRMED**: Launcher shows 2 sessions, both owned (MCP count
  unobtainable due to stale connector; owner-scoped UI is equivalent evidence).
- (b) config.mk has LEC_CHECK=0? — **CONFIRMED ✅** on fresh synth_0005 (rev 00060).
- (c) CTS pass w/ no SIGILL? — **IN PROGRESS** (run live, polling).
- (d) GDS produced? — **IN PROGRESS** (run live, polling).
- (e) session left behind — `asu_p1_mcp_20260706`, untouched except the new run.
