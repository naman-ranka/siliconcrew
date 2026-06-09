#!/usr/bin/env python3
"""DEPRECATED — DO NOT USE FOR GRADING. Produces UNTRUSTWORTHY verdicts.

This is the Windows-native cocotb shim. It runs harnesses on Windows iverilog 12 + cocotb 2.0.1,
which is NOT the CVDP reference environment. It was verified to be ~half wrong (false negatives from
Windows VPI crashes, false positives from simulator-semantic differences, and patch side-effects).
Use **`regrade_docker.py`** instead — it grades in the official reference container
`ghcr.io/hdl/sim/osvb` with correct context staging. See `research/EVAL_BROKEN_HANDOFF.md`.
Kept only for reference / the historical overnight runs.

Replay the official CVDP cocotb/pytest harness against a bench-orchestrator run.

Decoupled, run-dir-driven evaluator. Given a bench-orchestrator run directory, this:
  1. reads `run_config.json` (dataset, datapoint_id, session info),
  2. locates the SiliconCrew session workspace the agent wrote RTL into
     (reusing `bench_orchestrator.summary.find_workspace`),
  3. copies the problem's harness into a FRESH, isolated dir inside the run
     (`<run-dir>/raw/cvdp_harness_run/`) — never mutating the pristine
     `raw/cvdp_problem/harness/` materialized by the orchestrator,
  4. applies cocotb-2.0 compatibility rewrites and runs pytest/cocotb there,
  5. writes `<run-dir>/raw/cvdp_replay_result.json` (the shape/location that
     `summary.py:parse_cvdp_replay` + the dashboard already consume).

Usage:
    python cvdp-pipeline/replay_cvdp_harness.py --run-dir bench-orchestrator/runs/<run> \
        [--no-cocotb-compat-patch]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

# Repo root = parent of cvdp-pipeline/. Make the bench-orchestrator package importable so
# we reuse its workspace-discovery logic instead of duplicating path reconstruction.
REPO_ROOT = Path(__file__).resolve().parent.parent
_BENCH_SRC = REPO_ROOT / "bench-orchestrator" / "src"
if str(_BENCH_SRC) not in sys.path:
    sys.path.insert(0, str(_BENCH_SRC))

from bench_orchestrator.summary import find_workspace, parse_cvdp_replay, read_json  # noqa: E402
from bench_orchestrator.config import write_json  # noqa: E402


# --- harness materialization -------------------------------------------------

def write_harness(harness: Dict[str, str], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    for rel, content in harness.items():
        p = out_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")


_TO_UNSIGNED_PAT = re.compile(r"([A-Za-z_][A-Za-z0-9_\.\[\]]*)\.value\.to_unsigned\(\)")
_TO_SIGNED_PAT = re.compile(r"([A-Za-z_][A-Za-z0-9_\.\[\]]*)\.value\.to_signed\(\)")
_COCOTB_RUNNER_IMPORT_PAT = re.compile(
    r"^\s*from\s+cocotb\.runner\s+import\s+get_runner\s*$", re.MULTILINE
)
# cocotb 2.0 rejects an odd Clock `period` (checked in *sim steps*) unless `period_high` is given.
# Older harnesses use e.g. Clock(clk, 5, units="ns"). For odd integer periods, add period_high=N//2
# (a valid high/low split) so the clock is accepted; physical period is unchanged. Even periods untouched.
_CLOCK_NS_PAT = re.compile(
    r"Clock\(\s*([^,]+?)\s*,\s*([0-9]+)\s*,\s*units\s*=\s*(['\"])ns\3\s*\)"
)


def _clock_ns_to_ps(m: "re.Match[str]") -> str:
    sig, n, q = m.group(1), int(m.group(2)), m.group(3)
    if n % 2 == 1:
        return f"Clock({sig}, {n}, units={q}ns{q}, period_high={n // 2})"
    return m.group(0)


def apply_cocotb_compat_patches(harness_dir: Path) -> int:
    """Rewrite copied cocotb tests so they run on newer cocotb (2.x) where BinaryValue
    helpers like `.to_unsigned()` were removed. Applied only to the isolated copy."""
    changed = 0
    for py in harness_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        updated = _TO_UNSIGNED_PAT.sub(r"int(\1.value)", text)
        updated = _TO_SIGNED_PAT.sub(r"int(\1.value.signed_integer)", updated)
        updated = _COCOTB_RUNNER_IMPORT_PAT.sub(
            (
                "try:\n"
                "    from cocotb.runner import get_runner\n"
                "except Exception:\n"
                "    from cocotb_tools.runner import get_runner"
            ),
            updated,
        )
        updated = _CLOCK_NS_PAT.sub(_clock_ns_to_ps, updated)
        if updated != text:
            py.write_text(updated, encoding="utf-8", newline="\n")
            changed += 1
    return changed


# --- environment / source mapping --------------------------------------------

def parse_env_text(env_text: str) -> Dict[str, str]:
    env: Dict[str, str] = {}
    for raw in env_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip()
    return env


def map_code_path(token: str, session_dir: Path) -> str:
    """Map a harness `/code/<rel>` token onto the agent's session workspace."""
    t = token.strip().strip('"').strip("'")
    if t.startswith("/code/"):
        rel = t[len("/code/"):]
        p = session_dir / rel
        if p.exists():
            return p.as_posix()
        # Fallbacks for sessions that store generated RTL at the workspace root.
        if rel.startswith("rtl/"):
            p2 = session_dir / rel[len("rtl/"):]
            if p2.exists():
                return p2.as_posix()
        if rel.startswith("verif/"):
            p3 = session_dir / rel[len("verif/"):]
            if p3.exists():
                return p3.as_posix()
        return p.as_posix()
    return t


def build_env(problem: dict, session_dir: Path) -> Dict[str, str]:
    base = dict(os.environ)
    harness = problem.get("harness", {}) or {}
    # The .env is usually src/.env, but some harnesses nest it (e.g. src/<test>/.env).
    # Find it wherever it lives so VERILOG_SOURCES isn't silently dropped.
    env_key = "src/.env" if "src/.env" in harness else next(
        (k for k in sorted(harness) if k.endswith("/.env") or k == ".env"), None)
    raw_env = harness.get(env_key, "") if env_key else ""
    kv = parse_env_text(raw_env)

    verilog_sources = kv.get("VERILOG_SOURCES", "")
    mapped = []
    if verilog_sources:
        for tok in shlex.split(verilog_sources, posix=True):
            mapped.append(map_code_path(tok, session_dir))
    if mapped:
        kv["VERILOG_SOURCES"] = " ".join(mapped)

    kv.setdefault("PYTHONPATH", ".")
    kv.setdefault("WAVE", "true")

    base.update(kv)
    # Force UTF-8 stdio so cocotb harnesses that print Unicode (→, °, etc.) don't crash with
    # UnicodeEncodeError under Windows' default cp1252 console codec (a false-negative source).
    base["PYTHONIOENCODING"] = "utf-8"
    base["PYTHONUTF8"] = "1"
    return base


def run_pytest(harness_dir: Path, env: Dict[str, str]) -> subprocess.CompletedProcess:
    # Find the runner recursively (some harnesses nest it under src/<test>/test_runner.py).
    runner_files = sorted((harness_dir / "src").rglob("test_runner*.py"))
    if runner_files:
        targets = [p.relative_to(harness_dir).as_posix() for p in runner_files]
        # Make each runner's own directory importable (harness_library / cocotb MODULE).
        env = dict(env)
        extra = os.pathsep.join(sorted({str(p.parent.resolve()) for p in runner_files}))
        env["PYTHONPATH"] = extra + os.pathsep + env.get("PYTHONPATH", ".")
    else:
        targets = ["src"]
    cmd = ["pytest", "-s", "-v", *targets]
    return subprocess.run(cmd, cwd=harness_dir, env=env, text=True, capture_output=True)


# --- run-dir plumbing --------------------------------------------------------

def load_problem_row(run_dir: Path, dataset: Optional[Path], datapoint_id: str) -> dict:
    """Prefer the already-materialized problem.json; fall back to scanning the dataset."""
    materialized = read_json(run_dir / "raw" / "cvdp_problem" / "problem.json")
    if isinstance(materialized, dict) and materialized.get("harness"):
        return materialized
    if dataset and dataset.exists():
        with dataset.open("r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s:
                    continue
                row = json.loads(s)
                if row.get("id") == datapoint_id:
                    return row
    raise ValueError(
        f"Could not load CVDP problem '{datapoint_id}': no harness in materialized "
        f"problem.json and not found in dataset {dataset}."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Replay a bench-orchestrator run against its CVDP harness.")
    ap.add_argument("--run-dir", required=True, help="Bench-orchestrator run directory (contains run_config.json).")
    ap.add_argument(
        "--no-cocotb-compat-patch",
        action="store_true",
        help="Disable cocotb compatibility rewrites in the isolated harness copy.",
    )
    args = ap.parse_args()

    run_dir = Path(args.run_dir).resolve()
    run_config = read_json(run_dir / "run_config.json")
    if not isinstance(run_config, dict):
        raise FileNotFoundError(f"run_config.json missing or invalid in {run_dir}")

    problem_cfg = run_config.get("problem", {}) or {}
    datapoint_id = problem_cfg.get("datapoint_id")
    if not datapoint_id:
        raise ValueError(f"{run_dir}: run_config.problem has no datapoint_id (not a CVDP run?).")
    dataset = Path(problem_cfg["dataset"]) if problem_cfg.get("dataset") else None

    # 1. Locate the agent's session workspace (reuse bench discovery).
    workspace = find_workspace(run_dir)
    if not workspace:
        raise FileNotFoundError(
            f"Could not locate SiliconCrew session workspace for {run_dir}. "
            "Ensure the agent run completed and produced a workspace."
        )
    session_dir = Path(workspace).resolve()
    print(f"Session workspace: {session_dir}")

    # 2. Load the problem + harness.
    problem = load_problem_row(run_dir, dataset, str(datapoint_id))
    harness = problem.get("harness")
    if not harness:
        raise ValueError(f"Problem '{datapoint_id}' has no harness field; cannot replay.")

    # 3. Fresh, isolated harness dir inside the run (never mutate the pristine copy).
    harness_dir = run_dir / "raw" / "cvdp_harness_run"
    if harness_dir.exists():
        shutil.rmtree(harness_dir)
    write_harness(harness, harness_dir)
    if not args.no_cocotb_compat_patch:
        n = apply_cocotb_compat_patches(harness_dir)
        if n:
            print(f"Applied cocotb compatibility rewrites in {n} file(s).")

    # 4. Build env (map /code/ -> session workspace) and run pytest/cocotb.
    env = build_env(problem, session_dir)
    proc = run_pytest(harness_dir, env)
    print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="")

    # 5. Write the result where the dashboard/summary look for it.
    result = {
        "problem_id": str(datapoint_id),
        "datapoint_id": str(datapoint_id),
        "session_dir": session_dir.as_posix(),
        "harness_dir": harness_dir.as_posix(),
        "returncode": proc.returncode,
        "passed": proc.returncode == 0,
    }
    result_path = run_dir / "raw" / "cvdp_replay_result.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8", newline="\n")
    print(f"\n{'PASS' if result['passed'] else 'FAIL'} — wrote result: {result_path}")

    # Fold the verdict back into run_summary.json so the dashboard reflects it without a
    # re-run. The CVDP replay verdict takes precedence over runner status (mirrors
    # summary._overall_status), and parse_cvdp_replay re-reads the file we just wrote.
    summary = read_json(run_dir / "run_summary.json")
    if isinstance(summary, dict):
        cvdp = parse_cvdp_replay(run_dir)
        summary["cvdp_replay"] = cvdp
        summary["status"] = "passed" if (cvdp or {}).get("passed") else "failed"
        write_json(run_dir / "run_summary.json", summary)
        print(f"Updated run_summary.json: status={summary['status']}")

    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
