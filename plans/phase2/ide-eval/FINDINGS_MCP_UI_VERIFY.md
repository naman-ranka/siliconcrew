# MCP → Web UI Re-Verification (after fixes deployed)

Re-ran the cross-surface test after deploying the fixes: an agent drove an 8-bit
adder spec→GDS via the deployed MCP while a local FE (latest code) pointed at the
same deployed backend (same identity via proxy) was observed simultaneously.

## Verdict — the fixes landed

| Item | Before | After |
|---|---|---|
| Sim registers a UI run | sim left no trace | `run_isolated_simulation` → `sim_0001` (passed) in Runs panel + 13-signal waveform ✅ |
| Live reactivity (no reload) | required manual reload | files / sim run / synth status update **live on focus-revalidate (~5–8s)**, no reload ✅ |
| Session list live | new MCP session only after reload | appears after focus-revalidate (verified `picker_live_test` live) ✅ |
| Synth un-sticks from "running" | frozen at running forever | reconciles to terminal automatically via the active-run poll, no reload ✅ |
| Onboarding flash | flashed on first load | clean hydrate, no flash ✅ |

Reactivity nuance (expected): revalidation fires on real `focus`/`visibilitychange`
events; a closed session-picker dropdown only renders its (now-fresh) list when
reopened. Both verified working.

## Two findings from this run

**1. Regression in my own reconciliation — FIXED (commit ea71ef2).**
The first reconciliation used `synth_stat.txt` (area/cell_count) as the
completion signal, but that file is written right after *logic synthesis* — a run
that fails later (before CTS) still has it. So an incomplete run was mis-marked
"completed"/"passed". Fixed to key on the **finish-stage report (6_finish.rpt)**,
the only artifact that proves the flow reached finish. Fail-safe: no finish
report → status left non-terminal (a genuinely-failed stuck run is never falsely
shown as passed). Regression test added.

**2. The remote ORFS synth actually FAILED (infra, not UI).**
This run's ORFS job failed before CTS (`wait_for_synthesis` → failed; stages
constraints/synth/floorplan/place done, cts/route/finish never ran;
`6_finish.rpt not found`; no GDS). An 8-bit adder failing ORFS before CTS is
surprising — worth investigating the **remote ORFS service** (`ORFS_ENGINE=remote`,
136.111.64.201:8090) separately. With fix #1, such a run no longer shows as
"passed"; the UI correctly shows no GDS/finish PPA.

## Known pre-existing (not in scope here)
- `get_current_session` → "Object of type datetime is not JSON serializable".
- Monaco editor CDN (`cdn.jsdelivr.net`) blocked by the proxy → read-only Prism
  fallback (self-host Monaco is the fix; already flagged as a follow-up).
- `/spec` and per-run `/report` 404 probes (handled gracefully; UI falls back).

*Screenshots: `plans/phase2/screenshots/mcp-ui-verify2/` (01 baseline … 10 after-reload).*
