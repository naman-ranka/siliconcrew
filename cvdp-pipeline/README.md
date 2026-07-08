# cvdp-pipeline

Python-centric glue for running the **CVDP** (Chip Verification & Design Problems) benchmark
through the generic [`bench-orchestrator`](../bench-orchestrator), with no CVDP datasets or cocotb
details leaking into the orchestrator itself.

> ⚠️ **GRADING: use `regrade_docker.py`, NOT `replay_cvdp_harness.py`.** The latter is a Windows-native
> cocotb shim that produces **untrustworthy verdicts** (verified ~half wrong). The trustworthy validator
> grades in the official CVDP reference container `ghcr.io/hdl/sim/osvb`. See
> [`research/CVDP_RESULTS.md`](research/CVDP_RESULTS.md) for results and
> [`research/EVAL_BROKEN_HANDOFF.md`](research/EVAL_BROKEN_HANDOFF.md) for why.

## Prerequisites

| For | Need |
| --- | --- |
| Generating configs (`generate_cvdp_config.py`) | Python 3.10+, `pyyaml`, and a raw CVDP dataset JSONL (e.g. `cvdp_benchmark/data/cvdp_v1.0.2_agentic_code_generation_no_commercial.jsonl`). |
| Running the agentic phase | The `bench-orchestrator` + the `rtl-codex` MCP server; `RTL_WORKSPACE` exported to match the MCP server's session root (see *Environment gotchas*). |
| **Grading (`regrade_docker.py`) — REQUIRED for any trustworthy verdict** | **Docker running**, plus a one-time pull of the official reference image. Without it, grading is not trustworthy — the Windows-native shim is deprecated for exactly this reason. |

```bash
docker pull ghcr.io/hdl/sim/osvb   # one-time; the official CVDP test environment (cocotb 2.0-dev, iverilog 13)
```

> The CVDP **harness comes from the dataset itself** (materialized verbatim by the orchestrator's
> `_cvdp()` and graded as-is in the container) — this pipeline never invents a harness, and does **not**
> use CVDP's own runner scripts (`docker-compose`/`run.py`), only its dataset JSONL + the OSVB image it pins.
> The image is **digest-pinned** in `regrade_docker.py` (`DEFAULT_IMAGE`) so results stay reproducible if
> the `:latest` tag moves; override with `--image`. Staging dir is a temp dir by default (`--stage-root`
> or `CVDP_STAGE_ROOT` to override) — no hardcoded paths.

## Dataset & attribution

The CVDP benchmark (datasets, problem definitions, and the cocotb harnesses graded here) is **NVIDIA's
Comprehensive Verilog Design Problems (CVDP)** benchmark. This pipeline contains **no CVDP data** — it
reads a dataset JSONL you supply and runs the dataset's own harnesses unchanged in the reference image.

Obtain the dataset from NVIDIA's CVDP benchmark distribution (the `cvdp_benchmark` repository and its
linked dataset release) and place/symlink it where the configs expect it, e.g.:

```
cvdp_benchmark/data/cvdp_v1.0.2_agentic_code_generation_no_commercial.jsonl
```

Use of the dataset and the `ghcr.io/hdl/sim/osvb` reference image is governed by **their respective
licenses** — review and comply with NVIDIA's CVDP benchmark license and the OSVB image license before
publishing results. The `no_commercial` dataset is used because the commercial split requires
proprietary (Cadence `xrun`) infrastructure the reference container does not provide.

Stages:

| Stage | Script | Role |
| --- | --- | --- |
| **All-in-one** ⭐ | **`run_all.py`** | generate → run → grade → emit a provenance-stamped `results.json`. The one-command showcase/replication entrypoint. |
| **Before** | `generate_cvdp_config.py` | Select problems from a raw CVDP JSONL → emit a bench-orchestrator YAML config |
| *(run)* | `bench-orchestrator/run_benchmark.py` | Materializes the problem, drives the agent (the orchestrator already supports `kind: cvdp_agentic_jsonl`) |
| **Grade** ✅ | **`regrade_docker.py`** | Grade a finished run in the **official reference container** (osvb image, correct context staging). **The trustworthy validator.** |

(`_cocotb_compat.py` is a small helper used by the grader to load cocotb-1.x harnesses under cocotb-2.x;
it is not run directly.)

The orchestrator's `_cvdp()` does the heavy lifting (reads the raw row by `datapoint_id`,
materializes `context/`, `harness/`, `problem.json` under `<run>/raw/cvdp_problem/`), so these
scripts only *select* and *validate*.

## Reproduce a result (one command)

`run_all.py` ties the stages together and writes a single `results.json` whose every verdict is
stamped with **the repo commit, the digest-pinned image, and the agent/model/flow** — so a third
party can see exactly what produced the number and re-grade it.

```bash
export RTL_WORKSPACE=C:/Users/naman/Desktop/Projects/RTL_AGENT/workspace_new   # for the agent run
docker pull ghcr.io/hdl/sim/osvb                                               # one-time

# full run: generate a 92-problem config, drive the agent, grade in the container, emit results.json
python cvdp-pipeline/run_all.py \
    --dataset cvdp_benchmark/data/cvdp_v1.0.2_agentic_code_generation_no_commercial.jsonl \
    --max-problems 92 --agent claude --model claude-sonnet-5 --flow auto --name cvdp_full92

# grade-only: re-grade existing runs into a fresh, provenance-stamped results.json (no agent needed)
python cvdp-pipeline/run_all.py --config bench-orchestrator/configs/cvdp_des_smoke.yaml --skip-run
```

`results.json` shape:
```jsonc
{
  "benchmark": "cvdp_full92", "dataset": "...jsonl", "generated_at": "2026-...",
  "provenance": { "repo_commit": "<sha>", "image": "ghcr.io/hdl/sim/osvb@sha256:...",
                  "grader": "cvdp-pipeline/regrade_docker.py", "agent": "claude",
                  "model": "claude-sonnet-5", "flow": "auto" },
  "summary": { "passed": 64, "total": 92, "pass_rate": 0.6957 },
  "results": [ { "problem": "DES_0001", "verdict": "PASS", "passed": 1, "failed": 0,
                 "run_dir": "...", "datapoint_id": "cvdp_agentic_DES_0001" } ]
}
```
A third party with the same dataset + Docker can re-run `--skip-run` against your published run dirs (or
a fresh full run) and confirm the number; the pinned image digest makes the simulator environment
bit-identical to what produced it.

## Workflow (manual, stage by stage)

```bash
# 1. Generate a config (RTL-simulation-only; verilog flow => agent skips synthesis/PD)
python cvdp-pipeline/generate_cvdp_config.py \
    --dataset cvdp_benchmark/data/cvdp_v1.0.2_agentic_code_generation_no_commercial.jsonl \
    --out bench-orchestrator/configs/cvdp_des_smoke.yaml \
    --ids cvdp_agentic_DES_0001 --agent claude --model claude-sonnet-5
#   (or: --category cid003 --max-problems 5)

# 2. Run the benchmark (fake agent first to smoke-test plumbing, then a real agent)
python bench-orchestrator/run_benchmark.py --config bench-orchestrator/configs/cvdp_des_smoke.yaml --dry-run
python bench-orchestrator/run_benchmark.py --config bench-orchestrator/configs/cvdp_des_smoke.yaml --agent fake
python bench-orchestrator/run_benchmark.py --config bench-orchestrator/configs/cvdp_des_smoke.yaml --agent claude --model claude-sonnet-5

# 3. GRADE in the official reference container (trustworthy). Needs Docker running.
export RTL_WORKSPACE=C:/Users/naman/Desktop/Projects/RTL_AGENT/workspace_new
docker pull ghcr.io/hdl/sim/osvb   # one-time
python cvdp-pipeline/regrade_docker.py --ids <datapoint_short_id>   # or --run-dir <run>
#   (regrade_docker grades in ghcr.io/hdl/sim/osvb with official-style /code staging:
#    provided context files + the agent's patch-target files; unpatched-first.)
```

## How validation hooks into the dashboard

`regrade_docker.py --run-dir <run> --write`:
1. reads `<run>/run_config.json` for `datapoint_id`, and the materialized `raw/cvdp_problem/`
   (`harness/src` + `problem.json` with the dataset's `context`/`patch` fields),
2. locates the agent's SiliconCrew session workspace via `bench_orchestrator.summary.find_workspace`,
3. stages `/code` like the official runner into a temp tree (provided **context** files, then the
   agent's **patch-target** files overlaid) and mounts `harness/src` at `/src` (the pristine
   `raw/cvdp_problem/harness/` is never mutated); runs `pytest /src/test_runner.py` in the osvb
   container (unpatched first; `_cocotb_compat` rewrites applied only if the harness fails to load),
4. with `--write`, writes `<run>/raw/cvdp_docker_result.json` **and** folds the verdict into
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
- **No local simulator needed for grading** — `iverilog`/`cocotb`/`pytest` all live inside the osvb
  container; the host only needs Docker. (The deprecated Windows-native replay shim that *did* need a
  local simulator has been removed; grade only in the container.)

## Relation to the legacy `cvdp-automate/`

`cvdp-pipeline/` supersedes the fragmented, PowerShell-reliant `cvdp-automate/` flow
(`extract_minimal_tasks.py` → `prepare_cvdp_workspaces.py` → `run_cvdp_cid003_two_step.ps1` →
`replay_cvdp_harness.py --session-dir`). Those scripts are **deprecated** and kept only for
reference; everything now goes through the bench-orchestrator via the two scripts here.
