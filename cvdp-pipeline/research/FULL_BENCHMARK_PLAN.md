# Plan — run the full CVDP benchmark (all 92) for a showcase-grade result

Goal: produce a single, trustworthy, reproducible number — *"SiliconCrew passes N/92 of the CVDP
no-commercial agentic benchmark"* — that we can put in the repo README, generated end-to-end by the
`cvdp-pipeline` + `bench-orchestrator` path and graded only in the official reference container.

## 0. Selection-bias context (why we're doing the full run)
The 30-problem subset we have was **deliberately weighted toward historically-failing problems**:
27 of the 32 distinct problems we touched were March-2026 *failures* (84%), vs the benchmark's true
60% failure rate. So our container-verified **20/30 (67%)** is a *recovery rate on hard problems*,
not a representative benchmark score. The full 92 is needed for a number we can publish.

## 1. Pre-run: lock the agent we showcase (prompt freeze)
Decide **before** the run which agent we are scoring — the run is the showcase, so freeze the prompt:
- **Baseline-as-is** (current `architect_prompt_v2.md` with the XLS-for-datapath fix), OR
- **+ self-verification upgrade** from `SELF_VERIFICATION_GAP.md` lever 1 (cheap, non-disclosive):
  spec-derived adversarial test-plan + `prompt_contract` checklist + **"sim-hang / non-termination =
  FAIL"**. This is the single highest-leverage change and is the one we *should* ship before a
  showcase run, because the genuine failures were all false-confidence (self-PASS → harness-FAIL).
- The architect prompt edit lives in the **main repo** on `feature/xls-flow` (that copy is what the
  MCP server loads), not this worktree — apply/confirm it there first, then freeze.

Recommendation: **do one short calibration batch (~8 problems) with the upgraded prompt**, container-
grade it, confirm no regression vs the current numbers, then commit to the prompt for the full run.

## 2. Generate the 92-problem config
```bash
python cvdp-pipeline/generate_cvdp_config.py \
  --dataset cvdp_benchmark/data/cvdp_v1.0.2_agentic_code_generation_no_commercial.jsonl \
  --out bench-orchestrator/configs/cvdp_full92.yaml \
  --max-problems 999 --agent codex --model gpt-5.5 --flow auto
```
`--flow auto` = XLS is offered but the agent chooses (the honest "what does SC do when free" run).
One config, 92 problems, project disabled (avoids the cross-DB session bug).

## 3. Run the agentic phase (batched, resumable)
92 × ~5–12 min each ≈ many hours of wall-clock. Run in **batches of ~10** so a crash never loses more
than one batch, and so we can watch the stream:
```bash
export RTL_WORKSPACE=C:/Users/naman/Desktop/Projects/RTL_AGENT/workspace_new   # MCP + orch must agree
python bench-orchestrator/run_benchmark.py --config bench-orchestrator/configs/cvdp_full92.yaml \
  --agent codex --model gpt-5.5            # add batch/slice flags as available
```
Operational notes that bit us before, now codified:
- Keep `RTL_WORKSPACE` identical for the orchestrator and the `rtl-codex` MCP server.
- `project.enabled: false` (generator default) — bare `session_name`, no "Project not found".
- Heartbeat / never block silently; a problem that hangs the *agent* (not the sim) should be timed out
  by `timeout_sec` and moved on.

## 4. Grade — ALL in the reference container (the only trustworthy step)
Never use the Windows shim. One command per finished run (or loop over the run dirs):
```bash
docker pull ghcr.io/hdl/sim/osvb     # one-time
for run in bench-orchestrator/runs/cvdp-*__auto__*; do
  python cvdp-pipeline/regrade_docker.py --run-dir "$run" --write
done
python bench-orchestrator/summarize_runs.py     # dashboard now authoritative (docker verdicts)
```
`--write` folds the container verdict into `run_summary.json` so `experiments_dashboard.md` shows the
real number. **STAGE_ROOT in `regrade_docker.py` is hardcoded to `C:/Users/naman/cvdp_dock`** — fine on
this machine; parametrize before anyone else runs it.

## 5. Showcase artifact
- A `CVDP_FULL_RESULTS.md` with: N/92 headline, per-category breakdown, the XLS-on/off deltas, the
  failure taxonomy (codec-precision, hang, DSP-precision, protocol), and the exact reproduce commands.
- One results table in the repo README pointing at it. Every cell traceable to a container grade.

## 6. Risks / honesty guards
- **Cost/time:** 92 real agent runs is the expensive part — batch + resume, don't re-run passes.
- **Flakiness:** a few problems are borderline (dynamic_equalizer_0004 flipped run-to-run) — mark
  flaky explicitly, don't cherry-pick the lucky run.
- **No silent caps:** if we time-box and skip any problem, the results doc must say so (skipped ≠ pass).
- **Grade only in-container**; if Docker is down, the run is *ungraded*, not *passed*.

## 7. Predicted outcome (see chat answer for derivation)
Point estimate **~70% (≈ 64/92)**, plausible band **60–78%**, vs the March-2026 baseline of **40%
(37/92)** — i.e. roughly a doubling, driven by ~55% recovery of the previously-failing problems with
near-zero regression on the previously-passing ones. The upgraded self-verification prompt could push
the top of the band; the codec/precision class (hdbn/jpeg/prbs) will likely remain the hard floor.
