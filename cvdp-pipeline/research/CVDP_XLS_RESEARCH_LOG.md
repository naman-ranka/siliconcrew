# CVDP × XLS Research Log

**Researcher:** Claude (autonomous overnight run)
**Started:** 2026-06-08 ~22:50
**Question:** When a SiliconCrew agent is free to choose, does it use the XLS/DSLX HLS frontend on
CVDP problems — and does choosing XLS make it *better* (more passes) or *easier* (fewer iterations)
than writing Verilog directly? Where does each path break, and what can our agent NOT do?

---

## ‼️ THIS LOG IS THE INVESTIGATION TRAJECTORY (contains BROKEN-eval numbers). For results, read `CVDP_RESULTS.md`. ‼️

The overnight runs were graded with a **hand-rolled Windows-native cocotb shim**, not CVDP's official
Docker harness. That grader was **~half wrong** (verified by re-grading in the reference container
`ghcr.io/hdl/sim/osvb`). **Every pass/fail number in the Executive Summary, Run Ledger, and findings
BELOW this banner is unreliable.**

➡️ **Authoritative results: [`CVDP_RESULTS.md`](CVDP_RESULTS.md).** Why the eval broke + how to grade:
[`EVAL_BROKEN_HANDOFF.md`](EVAL_BROKEN_HANDOFF.md). Quick correct headline: **20/30 ≈ 67%** in the
reference container (1 flaky), XLS **helped 2 / hurt 1 / no-diff 4**.

**Corrected, container-verified results (30-problem subset, codex/gpt-5.5):**

- **SiliconCrew natural-mode pass rate: 20/30 ≈ 67%** (vs the broken Windows eval's ~30–40%, and the
  March-2026 baseline 40%). **SiliconCrew is materially BETTER than the overnight story claimed.** The
  overnight "fails most control/protocol problems" narrative was largely a Windows-eval artifact:
  ~11 passing designs were mis-marked FAIL (false negatives), plus a few false positives.
- **Genuine failures (10)** — the real targets to improve: csr_apb, dynamic_equalizer_0004, hdbn_codec
  (0/415), jpeg_runlength (0/55), monte_carlo, phase_rotation_0010, phase_rotation_0015 (partial),
  poly_decimator (**hangs the sim**), prbs (0/73), queue.
- **XLS controlled pairs (both sides container-verified): helped 2, hurt 1, no-diff 4 (n=7).**
  Helped: phase_rotation_0010, monte_carlo (Verilog FAIL → XLS PASS). Hurt: spi_complex_mult (Verilog
  PASS → XLS FAIL). → **XLS is INCONCLUSIVE on CVDP at this sample size** — not the "wash-to-negative"
  claimed overnight. Needs the full-92 run to call.

**What from the overnight work still STANDS (independent of the grader):**
- The CVDP↔bench-orchestrator pipeline (`generate_cvdp_config.py`, prompt fix, `xls_force` flow).
- **The architect-prompt finding (F1/F3): the agent never *chose* XLS because the architect system
  prompt told it to avoid XLS for fixed/legacy interfaces (= all of CVDP).** Prompt fixed. This is a
  behavioral observation from traces, not a graded result, so it holds.
- The Docker re-grader (`regrade_docker.py`) and the EVAL_BROKEN_HANDOFF note.

**Next:** grade the full 92 via CVDP's official `run_benchmark.py` (authoritative) — in progress.

---

## ★ EXECUTIVE SUMMARY (OVERNIGHT — SUPERSEDED by the Correction above; numbers are from the broken eval) ★

*~26 runs, codex/gpt-5.5, overnight 2026-06-08→09. Full per-run detail in the Run Ledger below.*

**The core question — does the agent do better/easier with XLS on CVDP? Answer: No, not on CVDP.**

1. **The agent never *chooses* XLS on CVDP, even on arithmetic/DSP problems** — 0 XLS calls across all
   `auto`-mode runs (codex). Root cause (found via Haiku trace analysis): the **architect system prompt
   itself** said "don't force XLS for existing-Verilog/exact-legacy-interface tasks," which describes
   *every* CVDP problem (all have fixed interfaces). I **fixed the prompt** (general improvement: a fixed
   interface is not a reason to avoid XLS — wrap it; reserve Verilog for FSM/control/protocol). Even
   after the fix, codex *still* chose Verilog — defensible judgment, since CVDP gives a fixed contract.

2. **When FORCED to use XLS (new `xls_force` flow overriding the architect prompt), codex CAN drive the
   DSLX→run_xls_flow→wrapper toolchain end-to-end — but it's a wash-to-negative on CVDP.** Forced-XLS
   pass rate ~22% (2/9). The cleanest evidence is **7 controlled Verilog-vs-XLS pairs** (same problem,
   same SC): **XLS helped 1** (`phase_rotation_0010`: Verilog FAIL → XLS PASS), **XLS HURT 1**
   (`spi_complex_mult_0002`: Verilog PASS → XLS FAIL — the XLS wrapper added a bug to a problem Verilog
   solves), **no difference on 5** (both fail). So forcing XLS rescued exactly one problem and broke
   exactly one — a wash-to-negative.

3. **WHY XLS doesn't help on CVDP:** the arithmetic *core* is the easy part; **CVDP failures live in the
   sequential/interface/protocol wrapper** (handshakes, exact latency, port contracts) that the agent
   must hand-write *anyway* — XLS doesn't help there and adds surface area to get wrong (e.g.
   `spi_complex_mult`: correct DSLX multiply, but the SPI wrapper drove `spi_miso`=X). XLS would likely
   help more on *greenfield* arithmetic-datapath design without a fixed contract (ASU-style), not CVDP.

**Secondary finding — current SC partially beats the March-2026 baseline (40%), but unevenly.** Of ~18
historically-FAILED problems re-run in current-SC Verilog, **~4 now PASS (~22% recovery)** —
rgb_color_space_conversion_0004, dynamic_equalizer_0001, queue_0001, dma_xfer_engine_0001. The
recoveries are **datapath/structural**; the **hard control/protocol problems still fail** (csr_apb,
elevator_control, ttc_lite, event_storing, cache_controller, lfsr, async_filo, traffic_light, jpeg,
sigma_delta). So the agent improved most on datapath, least on stateful control/protocol — the same
class XLS also can't help with.

**Changes made tonight (all in service of valid measurement):** (a) architect-prompt XLS guidance fix
(main repo + worktree); (b) new `xls_force` flow-rule; (c) **4 replay false-negative fixes** — UTF-8
stdio, nested-harness `.env` discovery, recursive test-runner + PYTHONPATH, cocotb-2.0 odd-Clock
`period_high` (unblocks 7 DSP harnesses) — plus the replay→run_summary→dashboard verdict wiring from the
pipeline build. These flipped real false-negatives (e.g. rgb_0004) to PASS.

**Validity check (strong): 0 regressions vs March.** *(Computed by cross-referencing all run_summary.json
verdicts against the March `harness_summary.json`.)* Across 31 overlapping problems, **every problem
that passed in the March baseline still passes here (0 regressions)**, with **5 recoveries** (dma_xfer_
engine, dynamic_equalizer_0001, queue_0001, rgb_color_space_conversion_0004 in Verilog; phase_rotation_
0010 in XLS). The zero-regression result rules out the `load_entry`/no-result pattern being a random
eval artifact — if it were, some historically-passing problems would spuriously fail; none do. So the
eval pipeline is sound and `load_entry` failures reflect **genuine difficulty**.

**Caveats:** codex had intermittent "at capacity" blips (a few runs invalidated/re-run); claude(=max)
hung and was shelved; antigravity untried. `load_entry` is the agent's design not satisfying the cocotb
test (RTL-dependent, validated by phase_rotation_0010 + the 0-regression check).

### Quantitative snapshot (distinct problems, real-agent codex runs)

| Mode | PASS | FAIL | pass-rate | notes |
|---|---|---|---|---|
| **xls_force** (XLS mandated) | 2 | 7 | **~22%** | only `phase_rotation_0010` is a clean Verilog-fail→XLS-pass unlock; `min_hamming` also passes in Verilog |
| **auto / verilog** (agent picks → always Verilog) | 10 | 19 | ~34% | **NB: problem set was deliberately weighted toward historically-FAILED problems** (to test recovery), so this is a *recovery rate on hard problems*, NOT a representative CVDP pass rate. Recoveries are datapath/structural; control/protocol still fail |
| controlled pairs (same problem, both modes) | — | — | — | **XLS helped 1, HURT 1, no-diff 2** (see below) |

**Controlled Verilog-vs-XLS pairs (same problem, same SC) — the cleanest signal:**
| problem | Verilog | XLS (forced) | verdict |
|---|---|---|---|
| phase_rotation_0010 | ❌ FAIL | ✅ PASS | **XLS helped** |
| spi_complex_mult_0002 | ✅ PASS | ❌ FAIL | **XLS hurt** |
| phase_rotation_0013 | ❌ FAIL | ❌ FAIL | no difference |
| sigma_delta_audio_0001 | ❌ FAIL | ❌ FAIL | no difference |
| poly_decimator_0001 | ❌ FAIL | ❌ FAIL | no difference |
| monte_carlo_0006 | ❌ FAIL | ❌ FAIL | no difference |
| dynamic_equalizer_0004 | ❌ FAIL | ❌ FAIL | no difference |
→ **Across 7 clean pairs (helped 1, hurt 1, no-diff 5), forcing XLS is a wash-to-slightly-negative:**
it rescued exactly one problem and broke exactly one the agent could otherwise solve (the XLS wrapper
added a bug); on the other 5 it made no difference. **Decisively not a win for CVDP.**

*Caveats: counts are over distinct problems (the raw dashboard has ~36 run dirs incl. re-runs,
capacity-invalids, and duplicates like min_hamming run in both soft-`xls` and `xls_force`). A few
control problems' fails are the `load_entry`/no-result-xml pattern (agent design doesn't satisfy the
cocotb test — proven RTL-dependent). The numbers are directional, not a precise benchmark score.*

---

## Methodology (the loop)

For each small batch (2–4 problems):
1. **Select** a subset deliberately (by CVDP category / design type), noting *why*.
2. **Run** through `bench-orchestrator` under a chosen flow:
   - `verilog` — XLS forbidden (baseline)
   - `auto` — XLS available, **agent freely chooses** (the key condition)
   - `xls` — XLS mandated (only when probing "can XLS do this at all")
3. **Haiku subagent reads the full trace** after each run and reports: did it pick XLS or Verilog,
   how many lint/sim iterations, what it struggled with, final self-reported status.
4. **Run the official harness** (`replay_cvdp_harness.py --run-dir`) for the independent verdict.
5. **Adapt**: verilog fail → retry under `auto`/`xls`; xls fail → diagnose *why* (interface wrap?
   latency contract? DSLX expressiveness?) and log the capability gap.
6. **Log** everything here and refresh the dashboard.

**Agents:** rotate codex (gpt-5.5) → claude → antigravity(agy/gemini) on usage limits.

---

## Setup / environment (verified)

- Agents present: `codex` (cli 0.135.0, gpt-5.5), `claude` (2.1.169), `agy` (1.0.1).
- `rtl-codex` MCP registered & **connected** for both codex (config.toml) and claude (user `.claude.json`),
  both → `RTL_AGENT\.venv\python mcp_server.py --codex-tools`.
- **`RTL_WORKSPACE` must be exported** = `C:/Users/naman/Desktop/Projects/RTL_AGENT/workspace_new`
  (the MCP server pins its workspace root there via `.env`; this is where agents write and where the
  replay's `find_workspace` looks). Set it for every `run_benchmark.py` and `replay_cvdp_harness.py`.
- Project disabled in CVDP configs (orchestrator vs MCP use different session DBs).
- Sim deps OK: iverilog 12.0, cocotb 2.0.1 (+compat patches), pytest 7.4.3.
- antigravity (agy): MCP wiring **untested** — agy runner doesn't auto-add MCP; may not see SiliconCrew
  tools. Deprioritized; will probe after codex/claude batches.
- **`claude` = the high-limit `claude-max` account for me**: this session runs with
  `CLAUDE_CONFIG_DIR=C:\Users\naman\.claude-max`, which the Bash tool inherits, so every `--agent claude`
  run uses the max account automatically (and `claude mcp add` registered rtl-codex there). So my two
  workhorses are **codex (own limits)** + **claude=max (high limits)**. To drop to the *normal* claude
  account, unset `CLAUDE_CONFIG_DIR`. (`claude-max` = a PS profile function doing exactly this.)
- **Tracing claude runs**: `claude -p` does NOT stream JSON (agent_events.jsonl / agent_stdout.log stay
  empty until the end). Trace claude via the MCP server's per-session **`attempt_events.jsonl`** in the
  workspace (`RTL_AGENT/workspace_new/<session>/attempt_events.jsonl`) — it logs every SiliconCrew tool
  call regardless of agent — plus the final `agent_stdout.log` message. (codex DOES stream, so
  `agent_stdout.log` JSONL works for codex.)

### Flow-rule wording added (`problems.py:_flow_rules`)
- `auto`: "XLS/DSLX frontend AVAILABLE but OPTIONAL … your call … if you use XLS, wrap to the exact
  required interface + latency contract."

---

## CVDP dataset notes

- File: `cvdp_v1.0.2_agentic_code_generation_no_commercial.jsonl` — **92 problems**.
- Category distribution (cid = problem-type code, + difficulty):
  - cid003: 34 (25 medium, 5 easy, 4 hard)  ← code *generation* from scratch
  - cid004: 25 (15 medium, 6 hard, 4 easy)
  - cid005: 21 (12 medium, 9 hard)
  - cid016: 10 (7 easy, 3 medium)
  - (others sparse)
- Each row: `id, categories, system_message, prompt, context{}, patch{}, harness{}`.
  `patch` keys = files the agent must write; `harness` = cocotb test + `.env` (VERILOG_SOURCES).

*(What each cidNNN means in design terms — to be characterized as I read problems.)*

---

## Historical baseline (March 2026, old SC + codex two-step)

Source: `RTL_AGENT/codex-automate/runs/two_step_batch/20260301_225501/harness_summary.json`.
**37/92 passed = 40.2%** (different SC shape & models, Verilog-only — no XLS path existed).

**Failure pattern = the crux of this study:** the failures cluster hard in **arithmetic/DSP**:
- ALL 7 `phase_rotation_*` failed; `cic_decimator`, `poly_decimator`, `sigma_delta_audio` failed;
  3× `dynamic_equalizer` failed; both `rgb_color_space_conversion_*` failed; `monte_carlo`,
  `spi_complex_mult`, `jpeg_runlength`, `sorter_0009/0016/0026` failed.
- Also many control/protocol failed: `door_lock`, `elevator_control`, `digital_stopwatch`, `queue`,
  `async_filo`, `cache_controller`, `dma_xfer_engine`, `traffic_light`, `csr_apb`, `nmea_gps`,
  `sync_serial_communication`, `programmable_fsm`, several `*_cache`/`fifo`.
- Passed (easy/structural): adders, muxes, barrel_shifters, swizzlers, DES/AES (some), memories,
  `systolic_array`, `signed_comparator`, `gcd_0007`, `binary_to_gray`.

**→ Reframed central question:** the Verilog-only agent failed most of the **arithmetic/DSP** set.
That's precisely XLS/DSLX's sweet spot. So the highest-value experiment is: take historically-FAILED
arithmetic/DSP problems and compare **verilog vs auto vs xls** — does XLS unlock passes the Verilog
agent can't get? (And separately: does current SC alone already beat 40.2%?)

**Agent fallback:** `claude-max` (higher limits) not on PATH in non-interactive shell — only
`claude`. Locate via user's PS `$PROFILE` if codex/claude hit usage limits.

## Run Ledger

| # | datapoint | cat | agent | flow | chose | harness | iters | notes |
|---|-----------|-----|-------|------|-------|---------|-------|-------|
| 0 | DES_0001 | cid003/hard | codex | verilog | verilog(forced) | ✅ PASS | 4 sim | baseline; hand-written SV, 16-stage pipe; passed cocotb |
| 1 | binary_to_gray_0003 | cid003/easy | codex | **auto** | **verilog** | ✅ PASS | 1 lint, 2 sim | combinational `b^(b>>1)`; never mentioned XLS; only hiccup was a pass_marker detection quirk |
| 2 | gcd_0007 | cid005/hard | codex | **auto** | **verilog** | ✅ PASS | 4 lint, 4 sim (2 fail→pass) | NOT a GCD — RSA-style crypto accel (modexp+GCD FSM); fixed GCD `done`-pulse latching bug + square-and-multiply operand order; never mentioned XLS |
| 3 | barrel_shifter_0001 | cid016/easy | codex | **xls (forced)** | **verilog** | ✅ PASS | 2 lint, 2 sim | **Forced-xls IGNORED** — agent explicitly declined XLS ("existing Verilog bug repair with exact legacy interface, keeping direct SV"); 0 .x files |
| 4 | min_hamming_distance_finder_0001 | cid005/med | codex | **xls (forced)** | **verilog** | ✅ PASS | 2 lint, 2 sim | Forced-xls IGNORED again; direct SV; 0 XLS calls |
| 5 | min_hamming_distance_finder_0001 | cid005/med | codex | **xls_force** | **XLS** ✓ | ✅ PASS | 8 xls calls, 1 .x | **XLS works end-to-end!** DSLX core → run_xls_flow → gen Verilog + hand wrapper → **8 cocotb PASS**. Same problem as run 4: soft `xls`→Verilog, hard `xls_force`→XLS. Proves agent CAN drive XLS+wrap on CVDP |
| 6 | spi_complex_mult_0002 | cid004 | codex | **xls_force** | **XLS** ✓ | ❌ FAIL | 4 xls calls, 1 .x | **agent logic** — DSLX core fine but its SPI wrapper drives `spi_miso`=X @780ns during readout. Real fail (not our pipeline). Historically failed in Verilog too |
| 7 | rgb_color_space_conversion_0004 | cid004/med | codex | **auto** (new prompt) | **verilog** | ✅ PASS | — | chose Verilog (rgb→HSV is conditional, not pure datapath). **Initially a FALSE-NEGATIVE** (Windows cp1252 UnicodeEncodeError on the test's `→`/`°` prints); fixed replay to force UTF-8 → **1 passed**. Historically FAILED in March → current SC **beats baseline** here |
| 8 | sigma_delta_audio_0001 | cid?/  | codex | **auto** (new prompt) | **verilog** | ❌ FAIL | — | chose Verilog; **genuine** logic fail (10/10 cocotb cases fail, no encoding error). Historically failed too. Clean DSP kernel yet codex still didn't pick XLS |
| 9 | poly_decimator_0001 | cid005/med | codex | **xls_force** | **XLS** ✓ | ❌ FAIL | real logic | XLS core ok but polyphase decimation output wrong (`expected [50] got []/[0]`, 2/4 cocotb fail). Needed 2 pipeline fixes to even evaluate (nested .env + Clock period_high). Historically failed too |
| 10 | phase_rotation_0010 | cid005/hard | codex | **xls_force** | **XLS** ✓ | ✅ **PASS** | **18 cocotb** | **★ XLS UNLOCK ★** CORDIC/Viterbi phase-rotation, **FAILED in March Verilog baseline**, now **PASSES** via DSLX core + wrapper. First direct evidence XLS can solve a problem the Verilog agent couldn't |
| 11 | dynamic_equalizer_0001 | cid003/hard | codex | **auto** | verilog | ✅ PASS | 1 cocotb | historically FAILED → **current SC beats baseline** (Verilog) |
| 12 | jpeg_runlength_enc_0001 | cid005/hard | codex | **auto** | verilog | ⚠️ soft-FAIL | infra | compiles (sim.vvp built) but cocotb runtime `load_entry()` TypeError → no result xml. Env/runner edge, not RTL. Ambiguous |
| 13 | queue_0001 | cid003/med | codex | **auto** | verilog | ✅ PASS | 1 cocotb | historically FAILED → **current SC beats baseline** (Verilog) |
| 14 | traffic_light_controller_0001 | cid?/  | codex | **auto** | verilog | ⚠️ soft-FAIL | infra | same `load_entry` cocotb runtime error (compiles OK). Ambiguous |
| 15 | monte_carlo_0006 | cid016/hard | codex | **xls_force** | **XLS** ✓ | ⚠️ soft-FAIL | infra | XLS used (.x=2); cocotb `load_entry` startup crash (no result xml). Ambiguous |
| 16 | phase_rotation_0013 | cid005/med | codex | **xls_force** (re-run B10) | **XLS** ✓ | ❌ FAIL | load_entry/no result | XLS used but design fails — **fails in BOTH Verilog (run 19) and XLS**. XLS did NOT unlock this one (contrast run 10) |
| 17 | phase_rotation_0028 | cid005/hard | codex | xls_force | — | 🚫 INVALID×2 | — | codex "at capacity" on BOTH attempts (B8+B10). Abandoned — capacity casualty, not a real verdict |
| 18 | phase_rotation_0010 | cid005/hard | codex | **verilog** (control) | verilog | ❌ FAIL | sim runs, no result xml | **★ CONTROLLED XLS-ISOLATION ★** SAME problem+harness+SC as run 10 (XLS→PASS 18). Verilog attempt's sim runs but cocotb produces no results (load_entry/abnormal). → with SC held constant, **XLS produced a working design, Verilog did not**. Dashboard shows the pair: verilog=failed/cvdp=False vs xls_force=passed/cvdp=True |
| 19 | phase_rotation_0013 | cid005/med | codex | **verilog** (control) | verilog | ❌ FAIL | load_entry/no result | Verilog attempt fails (same pattern). XLS verdict pending B10 re-run (run 16 was capacity-invalid) |
| 20 | sigma_delta_audio_0001 | cid?/  | codex | **xls_force** | **XLS** ✓ | ❌ FAIL | load_entry | XLS used (2 calls) but fails. Also failed in auto/Verilog (run 8) → XLS did NOT unlock |
| 21 | phase_rotation_0015 | cid005/med | codex | **xls_force** | **XLS** ✓ | ❌ FAIL | load_entry | XLS used; fails. XLS did NOT unlock |
| 22 | dynamic_equalizer_0004 | cid004/hard | codex | **xls_force** | **XLS** ✓ | ❌ FAIL | 1 cocotb fail | XLS used heavily (8 calls, many run_xls_flow iters); still fails harness. XLS did NOT unlock |
| 23 | cache_controller_0001 | cid?/  | codex | **auto** | verilog | ❌ FAIL | load_entry | real design fail (control) |
| 24 | dma_xfer_engine_0001 | cid003/med | codex | **auto** | verilog | ✅ PASS | 1 cocotb | historically FAILED → **current SC beats baseline** |
| 25 | lfsr_0005 | cid?/  | codex | **auto** | verilog | ❌ FAIL | load_entry | real design fail |
| 26 | async_filo_0001 | cid003/med | codex | **auto** | verilog | ❌ FAIL | load_entry | real design fail |
| 27 | csr_using_apb_interface_0001 | cid003/med | codex | **auto** | verilog | ❌ FAIL | load_entry | control/protocol — still fails |
| 28 | elevator_control_0004 | cid004/med | codex | **auto** | verilog | ❌ FAIL | 4 cocotb fail | FSM control — real logic fail |
| 29 | event_storing_0001 | cid005/hard | codex | **auto** | verilog | ❌ FAIL | load_entry | control — still fails |
| 30 | ttc_lite_0001 | cid003/med | codex | **auto** | verilog | ❌ FAIL | load_entry | timer/control — still fails |
| 31 | rc5_0001 | cid003/hard | codex | **auto** | verilog | ❌ FAIL | load_entry | RC5 cipher (stateful rounds) — still fails |
| 32 | hdbn_codec_0001 | cid005/med | codex | **auto** | verilog | ❌ FAIL | load_entry | HDB3 line codec (stateful) — still fails |
| 33 | prbs_0001 | cid005/med | codex | **auto** | verilog | ❌ FAIL | load_entry | PRBS generator — still fails |
| 34 | custom_fifo_0004 | cid?/  | codex | **auto** | verilog | ❌ FAIL | load_entry | FIFO control — still fails |
| 35 | spi_complex_mult_0002 | cid004/med | codex | **verilog** (control) | verilog | ✅ **PASS** | 1 cocotb | **★ XLS HURT ★** pairs with run 6 (xls_force FAIL). Verilog PASSES (after 33min, 20 rewrites of the SPI wrapper); XLS version failed (spi_miso=X). Forcing XLS broke a problem Verilog solves. Also a current-SC recovery (March: FAIL) |
| 36 | poly_decimator_0001 | cid005/med | codex | **verilog** (control) | verilog | ❌ FAIL | load_entry | pairs with run 9 (xls_force FAIL) → both fail, no difference |
| 37 | monte_carlo_0006 | cid016/hard | codex | **verilog** (control) | verilog | ❌ FAIL | load_entry | pairs with run 15 (xls_force FAIL) → both fail, no difference |
| 38 | dynamic_equalizer_0004 | cid004/hard | codex | **verilog** (control) | verilog | ❌ FAIL | 1 cocotb | pairs with run 22 (xls_force FAIL) → both fail, no difference |

*(filled as runs complete)*

---

## Per-run detail

### Run 0 — DES_0001 / codex / verilog (baseline, pre-research)
- Agent wrote 9 SV files (des_enc + S1–S8) directly, lint OK, 4 sim iterations, self-reported pass.
- Official harness: **PASS** (`TESTS=1 PASS=1`). XLS not used (forbidden by verilog flow).
- Takeaway: codex can solve a "hard" cid003 datapath problem in direct SV in one session.

---

## Findings (running)

- **F1 — codex has near-zero XLS propensity in `auto` mode (3/3 runs chose direct Verilog).**
  DES (hard datapath), binary_to_gray (combinational arithmetic), and gcd_0007 (RSA crypto/modexp
  arithmetic) were all written in direct SystemVerilog with **zero** `run_xls_flow`/DSLX calls — and
  the agent never even *mentioned* XLS as an option in its reasoning. Strong early signal that, when
  free, codex defaults to Verilog even on arithmetic-heavy problems. Needs: (a) does Claude differ?
  (b) does forced-`xls` even work / where does it break? Both queued.
- **F2 — codex solves these reliably in direct Verilog, including non-trivial bugs.** gcd_0007's real
  difficulty was an FSM handshake (1-cycle `done` pulse latching) — codex diagnosed it from a sim
  mismatch and fixed it in 2 sim iterations. So the Verilog baseline is strong; XLS has to *beat* a
  capable Verilog agent to be worth choosing.
- **Note — CVDP ids mislead on design type.** "gcd_0007" is a crypto accelerator; problem id ≠ design
  scope. Must read the actual prompt to classify XLS-fitness, not the name.
- **F3 — codex won't use XLS even when the flow MANDATES it (0/2 forced-`xls` runs used XLS), and the
  ROOT CAUSE is our own architect prompt.** Haiku trace analysis of `barrel_shifter_0001` (forced xls):
  the agent read the injected `architect_prompt_v2.md`, which says *"Do not force XLS for existing
  Verilog bug repair, exact legacy interfaces, multi-clock logic… Use direct Verilog for those,"* and
  explicitly reasoned *"existing Verilog bug repair with an exact legacy interface, so I'm keeping the
  implementation direct SystemVerilog rather than introducing a generated XLS wrapper."*
  → **The architect prompt's XLS-exemption covers essentially ALL of CVDP** (every problem is a
  fixed/legacy interface). So the soft `xls` flow-rule is overridden by the injected architect prompt.
  This is arguably *correct* engineering judgment (XLS+wrapper overhead vs a fixed contract), but it
  means: to study XLS-on-CVDP at all, the mandate must explicitly override the architect guidance.
  → Added **`xls_force`** flow-rule that says "ignore the architect prompt's XLS exemption; XLS is
  required; only a thin wrapper may be hand Verilog." Next batch tests whether codex *can* drive the
  XLS toolchain end-to-end under that hard mandate (capability ceiling), separate from whether it
  *should*.

- **F4 — codex CAN drive XLS end-to-end on CVDP; the architect prompt was the ONLY gate.** Under
  `xls_force` (which explicitly overrides the architect exemption), codex used XLS on both problems:
  `min_hamming` → DSLX core → `run_xls_flow` → gen Verilog → hand wrapper → **8 cocotb PASS**;
  `spi_complex_mult` → DSLX `complex_mult_core` + wrapper → ran but FAILED (X output). So the
  capability is real and the soft refusal (F3) was purely the prompt. Confirms the prompt fix is the
  right lever. **Open: does the *revised* prompt make codex choose XLS in plain `auto`? (B5 running.)**
- **F5 — wrapping friction is real and asymmetric: combinational-core wrapping works, sequential
  wrapping breaks.** `min_hamming` (combinational reduction core) wrapped cleanly and passed.
  `spi_complex_mult` (XLS combinational complex-multiply core wrapped in an SPI/sequential shell)
  produced **`Logic('X')`** at the harness sample time — the wrapper didn't correctly drive
  valid/latency or left a signal unconnected. → The agent's XLS weakness on CVDP is the
  **sequential/handshake wrapper**, not the arithmetic kernel.

- **F6 — prompt fix VERIFIED injected, but codex still leans Verilog in `auto` (1 data point so far).**
  B5 `rgb_color_space_conversion_0004` (codex, auto, post-fix): the new architect text ("…NOT by itself
  a reason to avoid XLS…") is confirmed present in the injected prompt, yet codex chose **direct Verilog
  (0 XLS)**. BUT rgb→HSV is *conditional/piecewise* (min/max, branching, division) — not a clean
  datapath kernel — so declining XLS here is defensible judgment, not the old blanket refusal. Verdict
  on the prompt fix's behavioral effect is PENDING a clean DSP kernel (`sigma_delta_audio`, B5 #2) and
  more pure-arithmetic problems. (Methodology: don't over-read one non-ideal problem.)

## Agent reliability

- **codex (gpt-5.5): reliable.** Streams JSON, completes, drives MCP tools well. Primary workhorse.
- **claude (=max account): HUNG on first try.** B3 (`rgb_color_space_conversion_0001`, auto) created
  the session (6 MCP events) then produced **0 bytes stdout/stderr for 40 min** and never returned —
  `claude -p` buffers all output to the end and appears to stall waiting on an MCP tool call.
  Deprioritized; kept only as emergency backup if codex hits usage limits. (If revisited: try a shorter
  timeout + `--output-format stream-json` so progress is observable, and a simpler problem first.)
- **antigravity (agy): not yet tried** (no MCP auto-wiring; lower priority).

## Methodology guard — harness vs agent failures

Per user: only fix failures caused by **our** harness/replay pipeline (false negatives); leave genuine
**agent-logic** failures as real FAILs (they are the research signal). Triage each FAIL:
- `spi_complex_mult_0002` FAIL = **agent logic** (its SPI wrapper drives `spi_miso`=X during readout;
  our pipeline compiled+ran the official harness correctly). → left as real FAIL, not touched.
- Watch for false negatives: wrong VERILOG_SOURCES mapping, missing helper modules at compile, cocotb
  compat. None observed yet (binary_to_gray's pass_marker quirk was in the *agent's* SC sim, not our
  official-harness replay).

- **F9 — controlled XLS-vs-Verilog (same SC, same problem) shows XLS is a WASH-TO-NEGATIVE, not a win:**
  - `phase_rotation_0010`: Verilog FAIL → **XLS PASS (18/18)**. XLS helped. ✅
  - `spi_complex_mult_0002`: Verilog **PASS** → **XLS FAIL**. **XLS HURT** (wrapper bug on a solvable problem). ⛔
  - `phase_rotation_0013`: Verilog FAIL → XLS FAIL. no difference. ➖
  - `sigma_delta_audio_0001`: Verilog FAIL → XLS FAIL. no difference. ➖
  → 4 clean pairs: helped 1, hurt 1, no-diff 2. XLS is not a blanket win; when the agent's
  surrounding sequential/wrapper logic or the cocotb-interface is wrong, XLS fails just like Verilog.
  **Full XLS-forced scorecard: 2 PASS / 9 attempts (~22%).** PASS = min_hamming (also passes in Verilog),
  phase_rotation_0010 (the ONE clean XLS-unlock). FAIL (7) = spi_complex_mult (wrapper X), poly_decimator
  (decimation logic), phase_rotation_0013, monte_carlo, sigma_delta_audio, phase_rotation_0015,
  dynamic_equalizer_0004. → **Forcing XLS rarely rescues a CVDP problem**: the arithmetic core is the
  easy part; CVDP failures live in the sequential/interface/protocol wrapper, which XLS doesn't help
  (and arguably adds surface area to get wrong).
- **F7 — XLS CAN unlock a problem the Verilog agent fails: `phase_rotation_0010` (xls_force) PASSES
  18/18**, and it FAILED in the March Verilog baseline. Even within tonight's XLS runs the result is
  mixed by problem: min_hamming PASS, phase_rotation PASS, spi_complex_mult FAIL (wrapper), poly_decimator
  FAIL (decimation logic). So XLS *helps on some hard arithmetic/DSP problems* but isn't a blanket win —
  the agent must still get the surrounding sequential logic right. Caveat: vs the *March* baseline two
  things differ (XLS + newer SC); a current-SC Verilog run on phase_rotation_0010 would isolate XLS's
  contribution (TODO).

- **F8 — current SC (auto/Verilog) recovers problems the March baseline failed.** Of historically-FAILED
  problems re-run in plain Verilog: `rgb_color_space_conversion_0004` PASS, `dynamic_equalizer_0001`
  PASS, `queue_0001` PASS (vs all FAIL in March). So a chunk of the 60% March failures are now solved by
  the current SC in Verilog alone — the agent/flow improved independent of XLS. (`sigma_delta_audio` still
  fails; jpeg/traffic_light infra-ambiguous.)

## `load_entry`/"no result xml" — REVISED: likely a REAL agent failure, not infra

Updated understanding (run 18 evidence): the same `phase_rotation_0010` harness **PASSES** when the
agent's design is correct (the XLS version, run 10) and shows the `load_entry`/"abnormal, no result
xml" pattern when the design is the Verilog version (run 18). Since a correct DUT passes the identical
harness, the failure pattern is the **agent's design not running under the cocotb test** (interface
mismatch or a sim-time crash at startup), i.e. a genuine fail — NOT a pipeline false-negative. The
trailing `load_entry()` TypeError is atexit shutdown noise. → I'm treating these as real FAILs (with a
note), not "soft/infra." (Earlier runs 12/14/15 were over-charitably tagged "infra"; they're most
likely real design fails too.)

## Pipeline fixes made tonight (false-negative sources — user-sanctioned "fix our harness" only)

1. **UTF-8 stdio** (`build_env`): Windows cp1252 crashed on harnesses printing `→`/`°`
   (`UnicodeEncodeError`). Forced `PYTHONIOENCODING=utf-8`/`PYTHONUTF8=1`. → flipped
   `rgb_color_space_conversion_0004` from false-FAIL to PASS.
2. **Nested-harness `.env` discovery** (`build_env`): some harnesses nest `src/<test>/.env` instead of
   `src/.env`; we were dropping `VERILOG_SOURCES` → `NoneType.split()`. Now find `.env` anywhere.
3. **Recursive runner + PYTHONPATH** (`run_pytest`): find `test_runner*.py` recursively and add its dir
   to PYTHONPATH (nested harness imports).
4. **cocotb-2.0 odd-Clock compat** (`apply_cocotb_compat_patches`): cocotb 2.0 rejects odd period-in-steps
   unless `period_high` given; ~7/92 DSP harnesses use `Clock(clk, 5, units="ns")`. Add `period_high=N//2`
   for odd N (physical period unchanged). Unblocks the DSP problems most relevant to the XLS question.
   (min_hamming regression-checked: still 8/8 PASS after all four fixes.)

## Capability gaps / failure modes (running)

- **GAP-1 (XLS sequential wrapper): `spi_complex_mult_0002` (xls_force) → `Cannot convert Logic('X')
  to int` @780ns.** Codex generated a valid DSLX complex-multiply core but the surrounding SPI/
  sequential wrapper produced undefined output at the harness sample point (handshake/latency or
  unconnected port). Combinational XLS cores wrap fine; sequential adaptation is the failure mode.
  Historically this problem also failed in Verilog — hard problem regardless of frontend.

## Decisions & rationale (running)

- Rely on Haiku trace summaries for `frontend_used` + iteration counts rather than instrumenting
  `run_summary.json` — matches the requested method and avoids risky overnight code changes.
- Start with `auto` on a few diverse problems to see the agent's *natural* XLS propensity before
  forcing anything.
- **INTERVENTION (pivotal) — revised the architect system prompt's XLS guidance** (user-approved,
  general change). Root cause F3 was the prompt's blanket *"do not force XLS for … existing Verilog
  bug repair, exact legacy interfaces."* Replaced with the correct principle: *a fixed/pre-specified
  interface is NOT a reason to avoid XLS for an arithmetic/datapath core — generate with XLS and wrap
  it; reserve direct Verilog for fundamentally FSM/control/protocol/multi-clock/debug designs.*
  Edited in BOTH the worktree and — crucially — the **main repo** `RTL_AGENT/prompts/architect/
  architect_prompt_v2.md` + `src/agents/architect.py`, because the rtl-codex MCP server loads the
  prompt from the main repo. This is the clean before/after lever: auto-mode pre-edit (runs 1,2 →
  Verilog) vs auto-mode post-edit (B5+).
