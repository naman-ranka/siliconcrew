#!/usr/bin/env python3
"""Re-grade bench-orchestrator CVDP runs in the OFFICIAL CVDP reference container.

Our Windows-native cocotb-2.0 replay produces false negatives (some harnesses die at
vvp/VPI init regardless of the design). The CVDP harnesses are designed to run in the
pinned `ghcr.io/hdl/sim/osvb` image. This grades a run there for a trustworthy verdict.

For each run it: stages the harness `src/` + the agent's solution RTL into a clean tree,
mounts them at /src and /code, and runs `pytest /src/test_runner.py` in the container
(the same command the shipped docker-compose.yml uses).

Usage:
    python cvdp-pipeline/regrade_docker.py --ids async_filo_0001,lfsr_0005 [--image ghcr.io/hdl/sim/osvb]
    python cvdp-pipeline/regrade_docker.py --run-dir bench-orchestrator/runs/<run>
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_BENCH_SRC = REPO_ROOT / "bench-orchestrator" / "src"
if str(_BENCH_SRC) not in sys.path:
    sys.path.insert(0, str(_BENCH_SRC))
from bench_orchestrator.summary import find_workspace, read_json  # noqa: E402
from bench_orchestrator.problems import find_cvdp_datapoint  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cocotb_compat import apply_cocotb_compat_patches  # noqa: E402

# Where /code and /src are staged before mounting into the container. Override with --stage-root
# (or the CVDP_STAGE_ROOT env); defaults to a temp dir so this is portable across machines.
DEFAULT_STAGE_ROOT = Path(os.environ.get("CVDP_STAGE_ROOT") or (Path(tempfile.gettempdir()) / "cvdp_dock"))
# Pin the official reference image to a digest so results stay reproducible even if the tag moves.
# (Repin via: docker inspect ghcr.io/hdl/sim/osvb --format '{{join .RepoDigests "\n"}}')
DEFAULT_IMAGE = "ghcr.io/hdl/sim/osvb@sha256:6fc999d943f1b8f8c49e7221459ae01e57afd33f7e73c3734b9a65be25e7f434"


def parse_env(env_text: str) -> dict[str, str]:
    env = {}
    for raw in env_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def newest_run(pid: str) -> Path | None:
    # Prefer the agent's NATURAL mode (auto/verilog) over forced-xls, for true efficacy.
    for flow in ("auto", "verilog", "xls_force", "xls"):
        cands = [Path(c) for c in glob.glob(f"bench-orchestrator/runs/cvdp-{pid}__{flow}*")]
        if cands:
            return max(cands, key=lambda p: p.stat().st_mtime)
    return None


def regrade(run_dir: Path, image: str, write: bool = False, stage_root: Path = DEFAULT_STAGE_ROOT) -> dict:
    rc = read_json(run_dir / "run_config.json") or {}
    prob = rc.get("problem", {}) if isinstance(rc, dict) else {}
    pid = prob.get("datapoint_id", "")
    short = re.sub(r"^cvdp_(agentic|nonagentic)_", "", pid)

    # Re-read the FULL datapoint (harness/context/patch) from the DATASET — the source of truth.
    # The agent-visible problem.json has `harness` stripped + `patch` blanked (leak fix), so grading
    # must never read the harness from the run dir. Legacy runs (pre-fix) still have a materialized
    # harness/src as a fallback.
    dataset = prob.get("dataset")
    # The per-run run_config.json has its dataset path REDACTED (leak fix — a stuck agent used to read it
    # to reach the raw dataset). Grading still needs the real dataset, so fall back to $RTL_DATASET or the
    # canonical path when the run_config copy is redacted/missing.
    if not dataset or dataset == "<redacted>" or not Path(dataset).exists():
        dataset = os.environ.get("RTL_DATASET") or (
            "C:/Users/naman/Desktop/Projects/RTL_AGENT/cvdp_benchmark/data/"
            "cvdp_v1.0.2_agentic_code_generation_no_commercial.jsonl"
        )
    row = None
    if dataset and Path(dataset).exists():
        try:
            row = find_cvdp_datapoint(Path(dataset), pid)
        except Exception:
            row = None
    harness = (row or {}).get("harness") or {}
    context = (row or {}).get("context") or {}
    patch_targets = list(((row or {}).get("patch") or {}).keys())

    ws = find_workspace(run_dir)
    if not ws:
        return {"problem": short, "verdict": "NO_WORKSPACE"}
    ws = Path(ws)

    dest = stage_root / short
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    (dest / "code" / "rundir").mkdir(parents=True, exist_ok=True)

    # Stage /src: harness from the dataset row (keys like "src/test_runner.py" -> dest/src/...);
    # fall back to a legacy materialized harness/src for runs created before the leak fix.
    src_root = dest / "src"
    legacy_src = run_dir / "raw" / "cvdp_problem" / "harness" / "src"
    if harness:
        for rel, content in harness.items():
            p = dest / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(str(content), encoding="utf-8", newline="\n")
    elif legacy_src.exists():
        shutil.copytree(legacy_src, src_root)
    if not src_root.exists():
        return {"problem": short, "verdict": "NO_HARNESS"}

    # The runner + .env may be nested (src/<test>/test_runner.py). Find them within the staged /src.
    runners = sorted(src_root.rglob("test_runner*.py"))
    runner = runners[0] if runners else (src_root / "test_runner.py")
    runner_dir = runner.parent
    env_file = (runner_dir / ".env") if (runner_dir / ".env").exists() else (src_root / ".env")
    env = parse_env(env_file.read_text(encoding="utf-8") if env_file.exists() else "")
    runner_rel = runner.relative_to(src_root).as_posix()              # e.g. test_poly_decimator/test_runner.py
    runner_cdir = "/src/" + runner_dir.relative_to(src_root).as_posix() if runner_dir != src_root else "/src"

    # Stage /code like the official runner: provided CONTEXT files first (verbatim from the dataset),
    # THEN overlay ONLY the agent's PATCH-TARGET files (its solution).
    for rel, content in context.items():                    # 1) provided context (verbatim from dataset)
        p = dest / "code" / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(str(content), encoding="utf-8")
    for rel in patch_targets:                               # 2) overlay the agent's solution files
        src = ws / rel
        if not src.exists():                                # agent may have written at a flattened path
            src = next((c for c in [ws / Path(rel).name, ws / "rtl" / Path(rel).name] if c.exists()), None)
        if src and src.exists():
            p = dest / "code" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, p)
    # fallback: if the harness expects sources not in context/patch, also mirror the agent's rtl/verif
    for sub in ("rtl", "verif"):
        if (ws / sub).exists():
            for f in (ws / sub).rglob("*"):
                if f.is_file():
                    tgt = dest / "code" / sub / f.relative_to(ws / sub)
                    if not tgt.exists():
                        tgt.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(f, tgt)

    cmd = ["docker", "run", "--rm",
           "-v", f"{dest / 'src'}:/src:ro",
           "-v", f"{dest / 'code'}:/code",
           "-w", "/code/rundir"]
    for k in ("SIM", "TOPLEVEL_LANG", "TOPLEVEL", "MODULE", "VERILOG_SOURCES"):
        if k in env:
            cmd += ["-e", f"{k}={env[k]}"]
    cmd += ["-e", f"PYTHONPATH={runner_cdir}", "-e", "WAVE=0", image,
            "pytest", "-o", "cache_dir=/code/rundir/.cache", f"/src/{runner_rel}", "-v"]
    # Unpatched first (cocotb-2.0-native harnesses must run as-is; patches can corrupt them).
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    out = proc.stdout + proc.stderr
    load_fail = ("No module named 'cocotb.runner'" in out or "ModuleNotFoundError" in out
                 or "errors during collection" in out or "AttributeError" in out)
    patched = False
    if load_fail:  # old cocotb-1.x harness — apply compat shims so it can load, then retry
        apply_cocotb_compat_patches(dest / "src")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        out = proc.stdout + proc.stderr
        patched = True
    # parse the final pytest summary line
    summ = ""
    for line in reversed(out.splitlines()):
        if "passed" in line or "failed" in line or "error" in line:
            summ = line.strip().strip("= ").strip()
            break
    npass = sum(int(x) for x in re.findall(r"(\d+) passed", out))
    nfail = sum(int(x) for x in re.findall(r"(\d+) (?:failed|error)", out))
    verdict = "PASS" if (npass > 0 and nfail == 0) else ("FAIL" if (npass + nfail) > 0 else "NO_RESULT")
    res = {"problem": short, "verdict": verdict, "passed": npass, "failed": nfail,
           "patched": patched, "summary": summ[:80]}
    if write:  # make the dashboard authoritative: record the trustworthy container verdict in the run
        passed = (verdict == "PASS")
        rec = {"grader": "docker:" + image, "passed": passed, "verdict": verdict,
               "passed_count": npass, "failed_count": nfail, "patched": patched}
        (run_dir / "raw" / "cvdp_docker_result.json").write_text(
            json.dumps(rec, indent=2), encoding="utf-8")
        summ_path = run_dir / "run_summary.json"
        rs = read_json(summ_path)
        if isinstance(rs, dict):
            rs["cvdp_replay"] = {"passed": passed, "result_path": str(run_dir / "raw" / "cvdp_docker_result.json"),
                                 "grader": rec["grader"], "passed_count": npass, "failed_count": nfail}
            rs["status"] = "passed" if passed else ("failed" if verdict == "FAIL" else "no_result")
            summ_path.write_text(json.dumps(rs, indent=2, sort_keys=True), encoding="utf-8")
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--run-dir", default="")
    ap.add_argument("--image", default=DEFAULT_IMAGE,
                    help="Reference container (digest-pinned by default for reproducibility).")
    ap.add_argument("--stage-root", default=str(DEFAULT_STAGE_ROOT),
                    help="Dir to stage /code and /src before mounting (default: a temp dir; "
                         "or set CVDP_STAGE_ROOT).")
    ap.add_argument("--write", action="store_true",
                    help="Write the trustworthy container verdict back into the run "
                         "(raw/cvdp_docker_result.json + run_summary.json) so the dashboard is authoritative.")
    args = ap.parse_args()
    stage_root = Path(args.stage_root)
    runs = []
    if args.run_dir:
        runs = [Path(args.run_dir)]
    else:
        for pid in [s.strip() for s in args.ids.split(",") if s.strip()]:
            r = newest_run(pid)
            if r:
                runs.append(r)
            else:
                print(f"  (no run found for {pid})")
    print(f"{'problem':<34}{'verdict':<11}{'pass':>5}{'fail':>5}")
    print("-" * 60)
    results = []
    for r in runs:
        try:
            res = regrade(r, args.image, write=args.write, stage_root=stage_root)
        except subprocess.TimeoutExpired:
            res = {"problem": r.name, "verdict": "TIMEOUT", "passed": 0, "failed": 0}
        except Exception as e:
            res = {"problem": r.name, "verdict": f"ERR:{e}", "passed": 0, "failed": 0}
        results.append(res)
        print(f"{res['problem']:<34}{res['verdict']:<11}{res.get('passed',0):>5}{res.get('failed',0):>5}")
    p = sum(1 for r in results if r["verdict"] == "PASS")
    print("-" * 60)
    print(f"PASS {p} / {len(results)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
