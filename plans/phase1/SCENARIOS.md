# Phase 1 — Scenario-driven hardening log

Each scenario was reasoned as a hardware engineer, **run for real** (real
iverilog 12.0 / real VCDs, the actual app over HTTP), broken where it broke,
fixed in BOTH the tool/contract layer and the UI, then locked with a regression
test. Mocks were used only for the Tier-2 flow E2E; the truth checks are real.

Environment boundary (documented, not a regression): **Docker is unavailable
and yosys is not installed**, so the OpenROAD (ORFS) synthesis flow cannot
execute here. Real lint / simulation / waveform are fully exercised. The synth
path is verified to **fail fast and gracefully** (no hang) and surface
diagnostics; real PPA/timing/GDS rendering is a Phase-2 (ORFS-as-job) item.

How to reproduce locally: `iverilog` on PATH, run `uvicorn api:app` (port 8000)
+ `npm run dev` (port 3000), open `/workbench`. Real-flow tests:
`pytest tests/test_real_flows.py`.

---

## 1. Real single-module counter — lint → sim → real VCD
- **Expected:** upload counter.v + tb → roles auto rtl/tb, synthTop=counter,
  simTop=counter_tb → Lint passes → Sim passes (pass marker) → an isolated VCD
  appears, waveform renders.
- **Ran:** real iverilog via the action API and the agent tool layer.
- **Result:** worked end-to-end; provenance stamped real `iverilogVersion 12.0`
  and `repoCommit`. No fix needed at the contract level.
- **Tests:** `test_real_flows::test_real_counter_passes_with_real_vcd`;
  `test_actions_api::test_lint_and_simulate_end_to_end` (now runs for real —
  it also exposed that the fixture TB lacked `$dumpvars`, fixed so a real VCD is
  produced).

## 2. Real multi-module CPU (alu + regfile + decoder + cpu_top + tb)
- **Expected:** 4 rtl + 1 tb + sdc; two tops (synth=cpu_top, sim=cpu_tb); Lint
  elaborates the DUT set (no tb); Sim uses rtl+tb; Synthesis set excludes the tb
  and includes the sdc; hierarchical VCD.
- **Result:** role derivation + top inference + `files_for_stage` all correct on
  a real design; real hierarchical sim passes.
- **Test:** `test_real_flows::test_real_multimodule_roles_tops_lint_sim_synthset`.

## 3. Lint failure (syntax error) — errors by file:line
- **Expected:** missing semicolon → lint fails with file + line; pipeline Lint
  stage red; Sim stays available but the failure is legible.
- **Result:** the `/lint` handler parses iverilog diagnostics into
  `byFile`/errors with line numbers; the console shows the exact command.
- **Test:** `test_real_flows::test_real_lint_failure_reports_file_and_line`.

## 4. Sim failure (assertion / mismatch) — failure cursor + reason
- **Expected:** a buggy DUT (counts by 2) → `test_failed`, the run shows the
  failure time, the waveform marks *when* and *what* went wrong, the human reason
  is visible without digging.
- **What broke (UI, caught by the fresh-eyes Playwright review):**
  1. **The waveform failure cursor was pinned at x≈0.** Root cause: the failure
     time is in **ns** but the VCD axis is in the dump's **ticks** (ps when the
     TB declares `` `timescale 1ns/1ps``, endtime ~112000). The cursor used the
     ns value directly against a ps axis.
  2. **Nothing said which signal was wrong** — you had to already know the bug.
  3. The human failure reason lived only behind the console chevron.
- **Fix (arch + UI):**
  - `/waveform` now returns `unitSeconds` (seconds per VCD tick) from the VCD
    timescale. The viewer converts ns→ticks (`cursorTime*1e-9/unitSeconds`,
    fallback ticks==ns when unknown) and clamps to endtime, so the cursor lands
    at the real failure point.
  - Added a **value-at-cursor readout** per signal: at the failure time `count`
    reads `=0x14` (20) — the +2 bug — right in the signal column.
  - The failure first-line is surfaced in the **console peek** and the
    **"viewing X" banner** (`ERROR: count=20 expected 10 at t=112ns …`).
- **Tests:** `test_real_flows::test_real_sim_mismatch_is_test_failed_with_time`
  (status + parsed timeNs); `frontend/test/waveform.test.tsx` (cursor chip +
  `=0x14` value-at-cursor via the ns→ps mapping).
- **Before/after:** `screenshots/review/10-waveform-detail.png` (cursor pinned
  far-left) → `screenshots/after-waveform-failure-cursor.png` (cursor correct +
  `count` reads `0x14` at the failure; bus steps 0,2,4,6,8,A,C,E).

## 5. Compile failure (missing module)
- **Expected:** a TB instantiating an absent module → `compile_failed` (distinct
  from `test_failed`), failure type = compile.
- **Result:** the strict status contract holds via the real tool.
- **Test:** `test_real_flows::test_real_compile_failure_missing_module`.

## 6. No pass-marker → `test_failed`, not `test_passed`
- **Expected:** rc==0 but no pass marker printed must NOT be a pass.
- **Result:** holds.
- **Test:** `test_real_flows::test_real_no_pass_marker_is_test_failed_not_passed`.

## 7. Synthesis with ORFS/Docker unavailable — graceful, no hang
- **Expected:** clicking Synthesize must not hang; the user must learn why; the
  Signoff stage stays gated.
- **Ran:** real `/synthesize` → job; polled `/jobs/{id}`.
- **Result:** the job goes terminal (`failed`) within seconds, surfaces as
  `synth_0001 failed` in the unified runs, and carries `check_notes`/log tail.
- **Fix (UI):** the synth poll loop now surfaces `check_notes` + last log lines +
  `next_action` in the console on failure (instead of a bare "failed"), and the
  Report empty state explains synthesis needs Docker/ORFS.
- **Boundary:** real PPA/timing/GDS not produced here (no ORFS) — Phase 2.

## 8. Waveform hierarchy (was a flat, duplicated 2-signal view)
- **Expected:** see the scope hierarchy (tb vs dut), bus values, x/z, a time
  ruler — a real multi-signal scope view.
- **What broke:** the old endpoint collapsed every signal to its leaf name,
  losing `counter_tb.clk` vs `counter_tb.dut.clk` (looked like duplicates) and
  dropped width/x-z.
- **Fix (arch + UI):** endpoint preserves `scope`, `full_name`, `width`,
  `isBus`, `valuesStr`, `xFlags`, `timescale`; viewer rebuilt with a collapsible
  **scope tree**, bus hex, x/z in red, a time ruler, and signal/scope counts.
- **Before/after:** `screenshots/wb-3-sim-fail.png` (old flat mock view) →
  `screenshots/after-waveform-hierarchy.png` (scope tree, real VCD).

## 9. Code tab broke on restricted networks (Monaco CDN)
- **What broke:** `@monaco-editor/react` fetches its loader from a CDN; when
  blocked the Code tab hung on "Loading…" forever. (Found via the live console.)
- **Fix (UI):** graceful read-only `react-syntax-highlighter` fallback with a
  load timeout — the (secondary) code tab always renders.
- **After:** `screenshots/after-code-fallback.png`.

## 10. Report — timing-hero + PPA + compare; honest empty state
- **Expected (from the design):** Report leads with timing (WNS met/violated),
  then area/cells/fmax/power, with a compare-vs-previous-run delta.
- **Fix (UI):** new `PpaHero` renders WNS as the hero (green met / red violated),
  PPA metric cards, and Δ% vs the previous synth run; rendered above the markdown
  and even before a markdown report exists when a synth run has PPA. Empty state
  now explains the ORFS/Docker requirement.
- **Tests:** `frontend/test/ppa-hero.test.tsx` (met/violated, compare selection,
  no-ppa → renders nothing).
- **Boundary:** verified with unit tests; a live PPA-hero screenshot needs a real
  synth run (ORFS) — Phase 2. Empty state: `screenshots/after-report-empty.png`.

## 11. Reload UX — waveform didn't auto-load for the selected run
- **What broke:** opening the Wave tab after a reload showed "No waveforms yet"
  because the selected run's VCD was only wired when sim ran live.
- **Fix (UI):** `WaveformViewer` syncs to the selected sim run's `vcdPath` when
  nothing is selected yet (respects a manual VCD choice).

## 12. AI-assistant key banner was alarming during a non-AI flow
- **What broke:** a persistent red "Missing ANTHROPIC_API_KEY" banner made the
  app look broken while lint/sim/synth worked fine.
- **Fix (UI):** config/missing-key errors render as a calm blue info note
  ("AI assistant needs ANTHROPIC_API_KEY — lint/sim/synth work without it").

## 13. In-app code editing — the "user updates code → re-run" loop
- **Expected (the prompt's scenario):** a user fixes RTL in the workbench and
  re-runs sim, all in-app.
- **What broke:** the Code tab was **read-only** (Monaco `readOnly:true`) and
  there was **no save endpoint** — the only human fix paths were re-upload or the
  agent (needs an API key). Genuine in-app editing did not exist. (Phase 1
  treated the editor as "secondary"; this scenario showed that's too thin.)
- **Fix (arch + UI), one write path:**
  - `src/tools/file_ops.py::write_file(workspace, path, content)` is the single
    source of truth (path-traversal guard + manifest reconcile). BOTH the REST
    save action (`PUT /api/workspace/{id}/code/{filename}`) and the agent
    `write_file` tool route through it — a human Save and an agent edit are now
    one tracked mutation (the future git-commit chokepoint).
  - `CodeViewer` is editable: **Edit / Save / Cancel** (editable Monaco, or a
    plain textarea when the Monaco CDN is blocked) plus **New file** to write RTL
    from scratch (filename validation, dirty/error states).
  - The AI rail is **collapsible** so the editor/waveform get full width
    (re-review feedback).
- **Verified:** real re-upload fix loop (`sim_0001 failed` → corrected counter.v
  → `sim_0002 passed`) at the API level; in-app edit→Save→re-run in the browser.
- **Tests:** `tests/test_file_ops.py` (write + manifest reconcile + traversal
  reject); `tests/test_actions_api.py::test_save_code_*`.

## 14. First-time-user genuine pipeline (subagent, in-app authoring)
- **Method:** a subagent opened the running app as a newcomer and built designs
  **from scratch in the in-app editor** (no uploads): an 8-bit adder + tb
  (lint→sim→introduce a bug via the editor→fail→fix→pass) and a multi-module
  mux2+top+tb. Both pipelines completed end-to-end in-app. Screenshots in
  `screenshots/firstuser/`.
- **Confirmed working:** in-app create/edit/save, the edit→re-run debug loop,
  fail-state UX (red banner with the `$display` ERROR + open-waveform link),
  the waveform scope tree incl. `top_tb.dut.m0/m1` hierarchy, auto role/top
  detection, and the run-history audit trail.
- **Issues found → fixed this pass:**
  1. **(correctness) synthTop picked a leaf submodule** (`mux2`) instead of the
     hierarchy root (`top`). Fixed `manifest._infer_tops` to choose the RTL
     **root** (a module no other rtl module instantiates), preferring the tb's
     DUT. Test: `test_manifest::test_synthtop_is_hierarchy_root_not_submodule`.
  2. **No unsaved indicator / silent data-loss** when switching files mid-edit.
     Added a **dirty indicator** ("unsaved" + dot), a **navigate-away confirm**
     (tree switch restores the edited file), and a **beforeunload** guard.
  3. **No keyboard save.** Added **Ctrl/Cmd+S**.
  4. **Sim success was invisible** (only failure showed text). The pass console
     line now shows `· TEST PASSED` when the marker is found.
- **Deferred (Phase-2):** file **rename/delete** in the tree; an "unsaved" cue
  in the file tree itself; syntax highlighting in the edit textarea (Monaco is
  CDN-blocked in this env).

---

## Fresh-eyes review method (subagents)
A subagent acted as a real hardware engineer and drove the **running** app with
its own isolated headless Playwright (chrome channel), exercising a failing-sim
debug flow and reporting concrete, user-voice criticism with 10 screenshots
(`screenshots/review/`). Its top findings (cursor units, signal localization,
failure-reason surfacing, API-key noise) drove scenarios #4, #11, #12 above and
were fixed and re-verified.

## Still open / Phase-2
- Real synthesis (ORFS in Docker) → real PPA/timing/GDS, post-synth gate-level
  sim, synth DRC/timing-violated Report, staged-retry lineage with real data.
- Waveform: expected-vs-actual overlay needs a golden reference (beyond value-
  at-cursor); waveform zoom-to-cursor.
- Concurrent real-run tenant isolation is covered at the action layer
  (`test_actions_api::test_concurrent_sessions_are_workspace_isolated`); a
  two-real-agents load test awaits a model API key.
