#!/usr/bin/env python3
"""Detect benchmark leakage in a CVDP run by scanning the agent transcript.

The agent must solve from the sanitized problem.json + context only. A run is INVALID (regardless of
pass/fail) if the agent's transcript shows it read anything it shouldn't be able to use:

  * dataset-read   — it ran a read command on the raw CVDP dataset JSONL (which embeds every problem's
                     hidden harness). The agent never needs the raw dataset; reading it = it saw its harness.
  * harness-access — it touched the hidden grading harness directly (cvdp_problem/harness, /src/test_runner,
                     harness_library) — e.g. running pytest on it in place (the pre-leak-fix in-place leak).
  * research-read  — it read our own research notes (cvdp-pipeline/research/*.md), which contain per-problem
                     analysis, expected behaviors and harness details.

This is detection-based enforcement: we can't physically stop a shell from reading files on the box, so
any run that DID is marked INVALID and must be re-run in a sealed environment. Also a permanent gate so
every future grade self-polices.

Usage:
    python cvdp-pipeline/leak_detector.py --run-dir <run>
    python cvdp-pipeline/leak_detector.py --audit-all     # recalibrate the whole corpus
"""
from __future__ import annotations
import argparse, json, os, re, glob, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUN_ROOTS = [
    REPO / "bench-orchestrator" / "runs",
    Path("C:/Users/naman/Desktop/Projects/RTL_AGENT/bench-orchestrator/runs"),
]

DATASET_RE = re.compile(r"cvdp_v[\d.]+_agentic[^\s\"']*\.jsonl", re.I)
READ_VERB = re.compile(r"(get-content|\bgc\b|\bcat\b|\btype\b|select-string|\bsls\b|import-csv|open\s*\(|\.read_text|\.read\s*\(|readlines|findstr)", re.I)
# Only the UNAMBIGUOUS hidden-grader signatures. The in-place harness leak always shows the path
# `cvdp_problem/harness/...` (or imports `harness_library`), so those catch it. We deliberately do NOT
# match a bare `test_runner.py` / `/src/test_runner`: cocotb names its OWN generated runner `test_runner.py`,
# so those broad patterns false-positive on every legitimate cocotb run (the intended golden-first flow).
HARNESS_RE = re.compile(r"harness_library|cvdp_problem[\\/]+harness", re.I)
RESEARCH_DOCS = r"cvdp-pipeline[\\/]+research|ITERATION_LOG|AUDIT_XLS_TOOLING|CVDP_RESULTS|MORNING_REPORT|CVDP_XLS_RESEARCH|SELF_VERIFICATION_GAP|EVAL_BROKEN_HANDOFF|FULL_BENCHMARK_PLAN"
RESEARCH_RE = re.compile(RESEARCH_DOCS, re.I)


def _read_near(txt: str, pat: re.Pattern, window: int = 140) -> bool:
    """True if a read-verb appears within `window` chars of any match of `pat`."""
    for m in pat.finditer(txt):
        seg = txt[max(0, m.start() - window): m.end() + 30]
        if READ_VERB.search(seg):
            return True
    return False


def detect(run_dir: Path) -> dict:
    log = run_dir / "raw" / "agent_stdout.log"
    if not log.exists():
        return {"leak": None, "reasons": ["no-transcript"]}
    txt = log.read_text(encoding="utf-8", errors="ignore")
    reasons = []
    if _read_near(txt, DATASET_RE):
        reasons.append("dataset-read")
    if HARNESS_RE.search(txt):                       # harness-specific names/paths: strong alone
        reasons.append("harness-access")
    if _read_near(txt, RESEARCH_RE):
        reasons.append("research-read")
    return {"leak": bool(reasons), "reasons": reasons}


def _verdict(run_dir: Path):
    r = run_dir / "raw" / "cvdp_docker_result.json"
    if not r.exists():
        return None
    try:
        return bool(json.loads(r.read_text(encoding="utf-8")).get("passed"))
    except Exception:
        return None


def _short(name: str) -> str:
    return re.sub(r"__.*", "", name).replace("cvdp-", "").lower()


def audit_all() -> int:
    rows = {}  # problem -> {clean_pass, any_pass, leaked_pass}
    seen = set()
    for root in RUN_ROOTS:
        for d in glob.glob(str(root / "cvdp-*")):
            key = os.path.basename(d)
            if key in seen:
                continue
            seen.add(key)
            rd = Path(d)
            v = _verdict(rd)
            if v is None:
                continue
            leak = detect(rd)["leak"]
            p = _short(key)
            r = rows.setdefault(p, {"any_pass": False, "clean_pass": False, "leaked_pass": False})
            if v:
                r["any_pass"] = True
                if leak:
                    r["leaked_pass"] = True
                else:
                    r["clean_pass"] = True
    # totals across the 92
    ds = REPO / "cvdp_benchmark" / "data" / "cvdp_v1.0.2_agentic_code_generation_no_commercial.jsonl"
    all92 = {re.sub(r"^cvdp_agentic_", "", json.loads(l)["id"]).lower()
             for l in ds.open(encoding="utf-8") if l.strip()} if ds.exists() else set(rows)
    any_pass = [p for p in all92 if rows.get(p, {}).get("any_pass")]
    clean_pass = [p for p in all92 if rows.get(p, {}).get("clean_pass")]
    inflated = [p for p in all92 if rows.get(p, {}).get("any_pass") and not rows.get(p, {}).get("clean_pass")]
    print(f"Problems: {len(all92)} | graded: {len([p for p in all92 if p in rows])}")
    print(f"OLD best-known (leak-inclusive) PASS: {len(any_pass)}/{len(all92)}")
    print(f"HONEST clean PASS (leak-free):        {len(clean_pass)}/{len(all92)}")
    print(f"Inflation (passed only via leaked runs): {len(inflated)}")
    print(f"  -> {sorted(inflated)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir")
    ap.add_argument("--audit-all", action="store_true")
    a = ap.parse_args()
    if a.audit_all:
        return audit_all()
    if a.run_dir:
        res = detect(Path(a.run_dir))
        verdict = "INVALID (leak)" if res["leak"] else ("CLEAN" if res["leak"] is False else "UNKNOWN (no transcript)")
        print(f"{verdict}: {', '.join(res['reasons']) or '-'}")
        return 0
    ap.error("pass --run-dir or --audit-all")


if __name__ == "__main__":
    raise SystemExit(main())
