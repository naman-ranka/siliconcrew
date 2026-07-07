# Exploration report: spec → GDS by hand through the SiliconCrew web UI

**Agent role:** Drive the DEPLOYED web app *as a human RTL designer would* — Playwright by
hand, IDE posture, NO in-app agent, NO MCP. Question answered: *can a competent RTL
designer, with no AI, take a small design from spec to as-far-as-it-goes using only this
UI, and where does the UI fail them?*

**App:** https://siliconcrew-frontend-psp2dkllmq-uc.a.run.app/ · backend rev 00059 ·
account `rockstarme.the5@gmail.com` (Claude test) · window 1680×1050 · 2026-07-06 (UTC
2026-07-07 ~05:33–05:56).

**Design used:** a small overlapping **"0011" sequence detector** (Mealy FSM, 4 states) +
a self-checking testbench. Chosen deliberately small so synthesis could actually run.

---

## TL;DR verdict

A competent RTL designer **can** drive this UI unaided through **file creation → manifest
→ lint → simulation → synthesis dispatch**, and the workbench is genuinely good: manifest
auto-population, honest per-run status, a real waveform viewer, and a truthful activity
log. **But two things would stop or badly confuse a real user:**

1. **A passing simulation is reported as "failed"** because the tool's pass-marker
   (`"TEST PASSED"`) is undocumented in the UI and the failure card shows **no reason** —
   the truth ("your testbench actually passed") is buried in a run_meta.json 3 levels deep.
2. **Full synthesis → GDS failed at CTS** with `child killed: illegal instruction`
   (SIGILL) — the **known per-worker infra flake** (team F9), now independently reproduced
   a **third time** via the UI path. The UI's failure surface is opaque: "failed" + partial
   metrics + a "Retry" button, with the real error buried **7 folder levels deep** in
   `orfs_logs/…/4_1_cts.log`.

**GDS *was* reached** — a fresh 2nd synthesis (`synth_0002`) landed on a compatible worker
and completed the full RTL→GDS flow: **WNS 0 ns (timing met), TNS 0 ns, 143.89 µm², 9 cells,
fmax 100 MHz, 39 µW, 2 GDS files**, and the UI's **Layout viewer rendered the routed
`6_1_merged.gds`** (real std cells: clkbuf_4, and2_1, dfstp_2, tap/fill). So the UI can do
the whole flow; it took **2 attempts** (the ~1/3 CTS coin-flip). *(img/11, img/12)*

**Would a hardware designer succeed unaided?** *To a green lint + passing waveform: yes,
comfortably — once past the pass-marker trap (U1). To GDS: **yes, but only by retrying
through the CTS coin-flip**, and when a run fails they get no legible reason in the UI —
they'd have to dig into raw ORFS logs 7 folders deep (U3) or just blindly hit "Synthesize"
again. A patient designer succeeds; a first-timer likely gives up at the opaque sim
"failure" (U1) or the opaque synth "failure" (U2/U3) without an AI or a teammate to explain
what happened.*

---

## Step-by-step UX walkthrough

### 0. Sign-in & Launcher
Already signed in ("Claude test" chip present). Launcher is clean: search, Recent/Grouped
toggle, New session, account, theme, settings. Two pre-existing sessions left untouched.

### 1. Create session (IDE posture) — smooth
New session → typed `ui_human_probe_20260706` → live `workspace/<slug>/` preview confirmed
the slug == sessionId → picked **IDE** (default) → Create. Routed straight to
`/w/ui_human_probe_20260706?view=ide`. Fresh IDE shows `synth_runs/` + `manifest.json`,
Top module and Testbench top both `—`. *(img/01-fresh-ide.png)*

### 2. Create + edit files (Monaco) — works, with one real friction
New file → `seq_detect.v` → auto-opened in Monaco, **auto-detected RTL badge**, "File
created" toast. Typed the module.
- **Monaco auto-close stranded a `)`**: because line 1 `module seq_detect (` ends in a bare
  `(`, Monaco auto-inserted a matching `)` that the newline separated and never got typed
  over → a **stray `)` after `endmodule`** that would break compilation.
  *(img/02-monaco-stray-paren.png)*. Deleting it by hand was easy. For the testbench I
  avoided ending any line on a bare `(` and got zero corruption — so the bug is specifically
  *"a line ending in an unmatched opening bracket."*
- **Save** gives no toast; the only success signal is the Save button re-disabling
  (matches the documented gap).

### 3. Manifest — a genuine strength, fully automatic
I never hand-edited JSON. On file creation the backend maintained `manifest.json`:
`seq_detect.v`→role `rtl` + **"synth top"** badge, `seq_detect_tb.v`→role `tb` + **"sim
top"** badge, and it filled `synthTop: seq_detect`, `simTop: seq_detect_tb`,
`clockPeriodNs: 10.0`, `platform: sky130hd`, `testbenches:[…]`. Explorer footer chips then
read the real tops. *(img/03-manifest-autoset.png)*. **Discoverability caveat:** the footer
Top/Testbench chips are display-only (not obviously editable); it works because inference
was correct, but there is no obvious in-UI "set top module" affordance if inference is wrong.

### 4. Lint (⌘K → Lint) — fast, legible, honest
Palette → Lint. Within seconds an Activity card: `linter_tool {"status":"passed",
"engine":"verilator","warnings":0,"errors":0}` **580 ms**, actor **"You"**, plus a top-bar
"Lint · done" pill. My UI gesture landed as a real event tagged "You" — **invariant 3
honored**. *(img/04-lint-passed.png)*

### 5. Simulation (⌘K → Simulate) — PASSING RUN REPORTED AS FAILED (top finding)
First sim: `run_isolated_simulation sim_0001 {"status":"failed", vcdPath:…}` 90 ms, surfaced
under the **Errors** filter with a red "Sim · error" pill. *(img/05-sim-failed.png)*
The card — even **expanded** — shows only the args, the same output JSON, and
"Open waveform" / "Re-run". **No log, no reason.** To learn why, I had to open
`sim_runs/sim_0001/run_meta.json` by hand, which revealed:
`stdoutTail: "…ALL TESTS PASSED …$finish called"`, yet `passMarkerFound:false`,
`failure.type:"test_failed"`. **The simulation genuinely passed** — my testbench printed
`ALL TESTS PASSED`, but the tool's required marker is the exact substring **`TEST PASSED`**
(`src/tools/run_simulation.py:11,437`), and `"ALL TESTS PASSED"` contains `"TESTS PASSED"`,
not `"TEST PASSED"`. Off by one `S`.
- Fixed as a human would: edited the TB to print exactly `TEST PASSED`, re-ran → `sim_0002
  {"status":"passed"}` 21 ms. *(img/06-sim-passed.png)*. The old failure honestly remains in
  history under Errors (correct — invariant 4).

### 5b. Waveform viewer — a strength
"Open waveform" on the passing run opened a **Waveform · sim_0002** artifact tab: header
(sim_0002 / passed / seq_detect_tb), **hex/dec radix toggle**, fit + zoom, a 0→100000 (1ps)
time axis, all **16 signals across 3 scopes** (`seq_detect_tb`, `.dut`, `.send`) with the
`state[1:0]` bus stepping 0→1→2→3→0 exactly matching the FSM, "click to place a measurement
cursor," footer "16 signals · 3 scopes." *(img/07-waveform.png)*

### 6. Synthesis (⌘K → Synthesize) — dispatch honest; flow FAILED at CTS (SIGILL)
Dispatch returned immediately; top-bar pill "Synth · done" (the *dispatch* event), while the
Runs table honestly showed `synth_0001 | seq_detect | running · started 38s ago`. The
`dispatch → poll(Refresh) → read` async contract behaved exactly as documented — the UI
never auto-updated; I clicked **Refresh** to advance. *(img/08-synth-running.png)*
After ~2.5 min `synth_0001` → **failed**. *(img/09-synth-failed-runs.png)*
- **Report tab** (Open report): AREA **143.89 µm²**, CELLS **9** computed, but
  WNS/FMAX/POWER "Not computed" and **"No report found · Retry"**. So yosys **synthesis
  succeeded** (netlist produced) and the flow died downstream.
- `synth_runs/synth_0001/run_meta.json`: `current_stage:"synth"`, `max_stage:"finish"`,
  `auto_checks.signoff:"fail"`, `check_notes:"ORFS command failed; 6_finish.rpt not found"`.
- Digging **7 levels deep** to `orfs_logs/sky130hd/seq_detect/base/4_1_cts.log` gave the
  real cause: CTS itself completed (H-tree built, `No setup violations`, `No hold
  violations`) then **`Error: cts.tcl, 85 child killed: illegal instruction` / non-zero
  status 1**. *(img/10-cts-sigill-error.png)*. This is the **known F9 per-worker SIGILL**
  (OpenROAD LEC child at cts.tcl:85 using ISA extensions only part of the Cloud Run pool
  supports); the MCP exploration hit the identical error on 2 of 3 fresh runs. **The design
  is correct and meets timing; the failure is infrastructure, not RTL or UI.**
- **Fresh re-dispatch `synth_0002` SUCCEEDED** (landed on a compatible worker; ran ~4 min,
  longer than the CTS-crash at ~2.5 min). Full flow completed: Report tab (`design_report.md`)
  showed **WNS 0.000 ns · TIMING MET · TNS 0 · AREA 143.89 µm² · CELLS 9 · FMAX 100 MHz ·
  POWER 39.2 µW · GDS Layout 2 files**, with a `synth_0001` vs `synth_0002` comparison.
  *(img/11-synth-report-passed.png)*. **Open layout** rendered the routed **`6_1_merged.gds`**
  in a real GDS viewer (std cells clkbuf_4/and2_1/dfstp_2/o31a_1, tap+fill, pin labels
  VPWR/VGND/CLK/D/Q). *(img/12-gds-layout.png)*. **The UI reached and displayed final GDS.**
  Minor legibility note: the report's Verification block lists **Simulation "⏳ Not Run"**
  even though sim_0002 passed — synth reports don't cross-link the separate sim run.

---

## Findings ledger

| # | Severity | Finding | What a real user experiences | Evidence | Suggested fix |
|---|----------|---------|------------------------------|----------|---------------|
| U1 | **HIGH** | Passing sim reported "failed"; failure card gives no reason | User's TB prints "PASSED", UI says failed, no explanation anywhere on the card; must open run_meta.json 3 levels deep to discover it actually passed and that the marker was wrong | img/05, sim_0001 run_meta `stdoutTail:"ALL TESTS PASSED"` + `passMarkerFound:false`; marker `TEST PASSED` at `src/tools/run_simulation.py:11,437` | On a `test_failed`-with-no-marker result, show in the card: "Expected pass marker **`TEST PASSED`** not found in output" + a stdout tail. Surface/settable `pass_marker` at point of use. Consider accepting common variants or a checkbox for "no self-check." |
| U2 | **HIGH** (infra; = team F9) | Full synth→GDS dies at CTS with `illegal instruction` (SIGILL) on some workers | Synthesis "just fails" ~2/3 of the time with zero legible reason near the run; GDS is a per-worker coin-flip | img/10, `4_1_cts.log`: `Error: cts.tcl, 85 child killed: illegal instruction`; corroborated by explore-mcp.md (2/3 fresh runs SIGILL) | Deploy the F9 `LEC_CHECK=0` fix (already root-caused). Independently: this is the UI confirming it, so **U3** below matters regardless. |
| U3 | **HIGH** | Synth failure is opaque in the UI: "failed" + partial metrics + "Retry", real error buried 7 folder levels deep | User cannot tell *which stage* failed or *why* without spelunking `orfs_logs/<pdk>/<top>/base/N_*.log` by hand | Report tab showed only "No report found / Retry"; run_meta `check_notes` names no stage; error only in `4_1_cts.log` | Surface `current_stage`/failing-stage + the tail of the failing stage log on the run card and Report tab (e.g., "Failed at **CTS** (4_1): child killed: illegal instruction"). A one-click "Open failing log." |
| U4 | MEDIUM | Monaco auto-close strands a `)` when a typed line ends in a bare `(` | New users typing RTL get a stray bracket after `endmodule` that breaks compile; silent until lint | img/02; reproduced on `module seq_detect (`; avoided when no line ends on bare `(` | Configure Monaco `autoClosingBrackets:"languageDefined"`/typeover, or a Verilog formatter on save; at minimum a lint hint. |
| U5 | LOW | No "Saved" confirmation | Uncertainty whether a save took; only signal is Save button re-disabling | §2 | Add a subtle "Saved" toast or a dirty-dot on the tab. |
| U6 | LOW | Top/Testbench manifest chips are display-only | If auto-inference of the top is wrong, there's no obvious in-UI way to override it | §3 explorer footer chips are `generic`, not buttons | Make the footer chips a picker (manifest is source of truth; offer suggestions from it). |
| U7 | LOW (cosmetic) | Radix a11y console error on every ⌘K | Console noise: "DialogContent requires a DialogTitle" (Radix) each palette open | console log; matches skill's known issue | Add a visually-hidden DialogTitle. |

**Honest positives (do not regress):** manifest auto-population (roles/tops/clock/platform);
activity log tags UI gestures as "You" via `/invoke` (invariant 3); per-run status with no
session-level dots and stale failures retained (invariant 4); async `dispatch→poll→read`
contract behaves exactly as documented; the waveform viewer (hierarchy, radix, cursor) is
genuinely good; lint 580 ms and sim 21 ms are snappy.

---

## How far the flow got

`spec-in-head → RTL (by hand) ✓ → manifest (auto) ✓ → lint PASS ✓ → sim PASS ✓ (after
fixing the pass-marker) → waveform ✓ → synthesis DISPATCH ✓ → yosys synth ✓ →
synth_0001 ORFS FAILED @ CTS (SIGILL) ✗ → **fresh retry synth_0002 → full RTL→GDS ✓ (WNS 0,
9 cells, 143.89 µm², 2 GDS files, layout rendered)**`.

**Full spec→GDS WAS reached through the UI by hand** — on the 2nd attempt, because the CTS
SIGILL (team F9) is a per-worker coin-flip (~1/3), independently reproduced here. The design,
manifest, lint, sim, synthesis, and GDS viewers all worked. The two things that would defeat
an unaided first-timer are the *legibility* gaps around failure: a passing sim shown as
"failed" with no reason (U1), and a synth failure shown as "failed" + "Retry" with the real
error buried 7 folders deep (U2/U3).
