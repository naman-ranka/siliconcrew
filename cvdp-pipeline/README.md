# cvdp-pipeline

Python-centric glue for running the **CVDP** (Chip Verification & Design Problems) benchmark
through the generic [`bench-orchestrator`](../bench-orchestrator), with no CVDP datasets or cocotb
details leaking into the orchestrator itself.

> ⚠️ **GRADING: use `regrade_docker.py`, NOT `replay_cvdp_harness.py`.** The latter is a Windows-native
> cocotb shim that produces **untrustworthy verdicts** (verified ~half wrong). The trustworthy validator
> grades in the official CVDP reference container `ghcr.io/hdl/sim/osvb`. See
> [`research/CVDP_RESULTS.md`](research/CVDP_RESULTS.md) for results and
> [`research/EVAL_BROKEN_HANDOFF.md`](research/EVAL_BROKEN_HANDOFF.md) for why.

Stages:

| Stage | Script | Role |
| --- | --- | --- |
| **Before** | `generate_cvdp_config.py` | Select problems from a raw CVDP JSONL → emit a bench-orchestrator YAML config |
| *(run)* | `bench-orchestrator/run_benchmark.py` | Materializes the problem, drives the agent (the orchestrator already supports `kind: cvdp_agentic_jsonl`) |
| **Grade** ✅ | **`regrade_docker.py`** | Grade a finished run in the **official reference container** (osvb image, correct context staging). **The trustworthy validator.** |
| ~~After~~ ⛔ | ~~`replay_cvdp_harness.py`~~ | **DEPRECATED** Windows-native shim — untrustworthy, kept only for the historical overnight runs |

The orchestrator's `_cvdp()` does the heavy lifting (reads the raw row by `datapoint_id`,
materializes `context/`, `harness/`, `problem.json` under `<run>/raw/cvdp_problem/`), so these
scripts only *select* and *validate*.

## Workflow

```bash
# 1. Generate a config (RTL-simulation-only; verilog flow => agent skips synthesis/PD)
python cvdp-pipeline/generate_cvdp_config.py \
    --dataset cvdp_benchmark/data/cvdp_v1.0.2_agentic_code_generation_no_commercial.jsonl \
    --out bench-orchestrator/configs/cvdp_des_smoke.yaml \
    --ids cvdp_agentic_DES_0001 --agent codex --model gpt-5.5
#   (or: --category cid003 --max-problems 5)

# 2. Run the benchmark (fake agent first to smoke-test plumbing, then a real agent)
python bench-orchestrator/run_benchmark.py --config bench-orchestrator/configs/cvdp_des_smoke.yaml --dry-run
python bench-orchestrator/run_benchmark.py --config bench-orchestrator/configs/cvdp_des_smoke.yaml --agent fake
python bench-orchestrator/run_benchmark.py --config bench-orchestrator/configs/cvdp_des_smoke.yaml --agent codex --model gpt-5.5

# 3. GRADE in the official reference container (trustworthy). Needs Docker running.
export RTL_WORKSPACE=C:/Users/naman/Desktop/Projects/RTL_AGENT/workspace_new
docker pull ghcr.io/hdl/sim/osvb   # one-time
python cvdp-pipeline/regrade_docker.py --ids <datapoint_short_id>   # or --run-dir <run>
#   (regrade_docker grades in ghcr.io/hdl/sim/osvb with official-style /code staging:
#    provided context files + the agent's patch-target files; unpatched-first.)
```

## How validation hooks into the dashboard

`replay_cvdp_harness.py`:
1. reads `<run>/run_config.json` for `dataset` / `datapoint_id` / session info,
2. locates the agent's SiliconCrew session workspace via `bench_orchestrator.summary.find_workspace`,
3. copies the harness into a **fresh, isolated** `<run>/raw/cvdp_harness_run/` (the pristine
   `raw/cvdp_problem/harness/` is never mutated), applies cocotb-2.x compat rewrites, runs pytest,
4. writes `<run>/raw/cvdp_replay_result.json` **and** folds the verdict back into
   `run_summary.json` (`cvdp_replay` + `status`), so `summarize_runs.py` shows the `cvdp` pass/fail
   column with no agent re-run.

## Environment gotchas (real agents)

The fake agent needs none of this; real agents (codex/claude) do:

- **`RTL_WORKSPACE`** — the `rtl-codex` MCP server pins its workspace root from its own `.env`
  (e.g. `…/RTL_AGENT/workspace_new`). When you run the orchestrator from a different checkout/worktree,
  export the **same** `RTL_WORKSPACE` so `find_workspace` looks where the agent actually wrote:
  ```bash
  export RTL_WORKSPACE=C:/Users/naman/Desktop/Projects/RTL_AGENT/workspace_new
  ```
- **Project disabled by default** — the orchestrator and the MCP server can use *different* session
  DBs, so a `project_id` makes the agent's `create_session_tool` fail "Project not found". The
  generated config sets `project.enabled: false`; sessions are created by bare `session_name`. Pass
  `--enable-project` only when both sides share one DB.
- **Simulator deps** — `iverilog`, `cocotb` (2.x), `pytest`, `cocotb_tools` must be importable in the
  environment that runs the replay.

## Relation to the legacy `cvdp-automate/`

`cvdp-pipeline/` supersedes the fragmented, PowerShell-reliant `cvdp-automate/` flow
(`extract_minimal_tasks.py` → `prepare_cvdp_workspaces.py` → `run_cvdp_cid003_two_step.ps1` →
`replay_cvdp_harness.py --session-dir`). Those scripts are **deprecated** and kept only for
reference; everything now goes through the bench-orchestrator via the two scripts here.
