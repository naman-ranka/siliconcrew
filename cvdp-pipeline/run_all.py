#!/usr/bin/env python3
"""One-command CVDP benchmark: generate -> run -> grade-in-container -> results.json.

This is the showcase / replication entrypoint. It ties the three pipeline stages together and emits a
single `results.json` whose every per-problem verdict is stamped with provenance — the repo commit, the
digest-pinned reference image, and the agent/model/flow — so a third party can see exactly what
produced the number and re-grade it themselves.

Typical use:
    # full run: generate a config, drive the agent, grade in the container, write results.json
    python cvdp-pipeline/run_all.py \
        --dataset cvdp_benchmark/data/cvdp_v1.0.2_agentic_code_generation_no_commercial.jsonl \
        --max-problems 92 --agent codex --model gpt-5.5 --flow auto --name cvdp_full92

    # grade-only (re-grade existing runs into a fresh, provenance-stamped results.json)
    python cvdp-pipeline/run_all.py --config bench-orchestrator/configs/cvdp_des_smoke.yaml --skip-run

Grading needs Docker + the osvb image (see README). The agent run additionally needs the rtl-codex MCP
server and RTL_WORKSPACE exported (see README "Environment gotchas").
"""
from __future__ import annotations

import argparse
import datetime
import json
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
from regrade_docker import regrade, newest_run, DEFAULT_IMAGE, DEFAULT_STAGE_ROOT  # noqa: E402
import generate_cvdp_config as gen  # noqa: E402


def git_commit() -> str | None:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                             capture_output=True, text=True)
        return out.stdout.strip() or None
    except Exception:
        return None


def run_orchestrator(config_path: Path, agent: str | None, model: str | None) -> None:
    cmd = [sys.executable, str(REPO_ROOT / "bench-orchestrator" / "run_benchmark.py"),
           "--config", str(config_path)]
    if agent:
        cmd += ["--agent", agent]
    if model:
        cmd += ["--model", model]
    print(f"[run_all] launching orchestrator: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate -> run -> grade a CVDP benchmark; emit results.json.")
    # Either generate a config from a dataset+selection, or reuse an existing one.
    ap.add_argument("--dataset", default="", help="Raw CVDP JSONL (required unless --config is given).")
    ap.add_argument("--config", default="", help="Use an existing bench-orchestrator config (skip generation).")
    ap.add_argument("--ids", default="", help="Comma-separated datapoint ids (selection).")
    ap.add_argument("--category", default="", help="Select by category (e.g. cid003).")
    ap.add_argument("--max-problems", type=int, default=0, help="Limit problem count (0 = all matched).")
    ap.add_argument("--agent", default="codex", help="Agent (codex|claude|antigravity|fake).")
    ap.add_argument("--model", default="gpt-5.5", help="Model.")
    ap.add_argument("--flow", default="auto", help="Flow (auto|verilog|xls_force).")
    ap.add_argument("--name", default="cvdp_run", help="Benchmark/config name.")
    ap.add_argument("--image", default=DEFAULT_IMAGE, help="Reference container (digest-pinned by default).")
    ap.add_argument("--stage-root", default=str(DEFAULT_STAGE_ROOT), help="Staging dir for the grader.")
    ap.add_argument("--out", default="", help="results.json output path (default runs/results_<name>.json).")
    ap.add_argument("--skip-run", action="store_true", help="Grade existing runs only; do not launch the agent.")
    ap.add_argument("--no-write", action="store_true",
                    help="Do not fold container verdicts back into each run_summary.json.")
    args = ap.parse_args()

    # 1. Config: reuse or generate.
    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            ap.error(f"--config not found: {config_path}")
    else:
        if not args.dataset:
            ap.error("--dataset is required unless --config is given")
        dataset = Path(args.dataset)
        if not dataset.exists():
            ap.error(f"--dataset not found: {dataset}")
        rows = gen.load_rows(dataset)
        ids = [s.strip() for s in args.ids.split(",") if s.strip()] or None
        selected = gen.select_rows(rows, ids, args.category or None, args.max_problems)
        if not selected:
            ap.error("No problems matched the selection criteria.")
        cfg_obj = gen.build_config(
            rows=selected, name=args.name, dataset_yaml=gen.dataset_path_for_yaml(dataset),
            agent=args.agent, model=args.model, flow=args.flow, mcp_server="rtl-codex",
            timeout=2400, project_name=f"bench_{args.name}", project_enabled=False,
        )
        config_path = REPO_ROOT / "bench-orchestrator" / "configs" / f"{args.name}.yaml"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(gen.dump_yaml(cfg_obj), encoding="utf-8", newline="\n")
        print(f"[run_all] wrote config {config_path} ({len(selected)} problems)")

    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    problems = cfg.get("problems", []) or []
    defaults = cfg.get("defaults", {}) or {}
    agent = args.agent or defaults.get("agent")
    model = args.model or defaults.get("model")
    flow = defaults.get("flow", args.flow)
    dataset_used = problems[0].get("dataset") if problems else args.dataset

    # 2. Run the agentic phase (unless grading existing runs).
    if args.skip_run:
        print("[run_all] --skip-run: grading existing runs only")
    else:
        run_orchestrator(config_path, args.agent, args.model)

    # 3. Grade every problem in the reference container.
    stage_root = Path(args.stage_root)
    results = []
    print(f"\n{'problem':<34}{'verdict':<11}{'pass':>5}{'fail':>5}")
    print("-" * 60)
    for p in problems:
        sid = p["id"]
        run = newest_run(sid)
        if not run:
            res = {"problem": sid, "verdict": "NO_RUN", "passed": 0, "failed": 0}
        else:
            try:
                res = regrade(run, args.image, write=not args.no_write, stage_root=stage_root)
            except Exception as e:  # keep going; record the error per-problem
                res = {"problem": sid, "verdict": f"ERR:{e}", "passed": 0, "failed": 0}
            res["run_dir"] = str(run)
        res["datapoint_id"] = p.get("datapoint_id")
        results.append(res)
        print(f"{sid:<34}{res.get('verdict',''):<11}{res.get('passed',0):>5}{res.get('failed',0):>5}")

    # 4. Provenance-stamped results.json — the replication artifact.
    npass = sum(1 for r in results if r.get("verdict") == "PASS")
    total = len(results)
    out = {
        "benchmark": cfg.get("name", args.name),
        "dataset": dataset_used,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "provenance": {
            "repo_commit": git_commit(),
            "image": args.image,
            "grader": "cvdp-pipeline/regrade_docker.py",
            "agent": agent,
            "model": model,
            "flow": flow,
        },
        "summary": {
            "passed": npass,
            "total": total,
            "pass_rate": round(npass / total, 4) if total else None,
        },
        "results": results,
    }
    out_path = Path(args.out) if args.out else (
        REPO_ROOT / "bench-orchestrator" / "runs" / f"results_{cfg.get('name', args.name)}.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("-" * 60)
    print(f"[run_all] PASS {npass}/{total}  (pass_rate={out['summary']['pass_rate']})")
    print(f"[run_all] results -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
