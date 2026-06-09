from __future__ import annotations

from pathlib import Path
import argparse
import json
import sys

from .paths import orchestrator_root, repo_root
from .trace import has_failed_agent_event


def load_summary(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_dashboard(runs_root: Path, output: Path) -> Path:
    rows = []
    for p in sorted(runs_root.glob("*/run_summary.json")):
        data = load_summary(p)
        if not data:
            continue
        problem = data.get("problem", {})
        sc = data.get("siliconcrew", {})
        metrics = sc.get("summary_metrics") or {}
        auto = sc.get("auto_checks") or {}
        rows.append({
            "run": p.parent.name,
            "problem": problem.get("id"),
            "flow": data.get("flow"),
            "agent": data.get("agent"),
            "model": data.get("model"),
            "status": "failed" if has_failed_agent_event(p.parent / "agent_events.jsonl") else data.get("status"),
            "synth": sc.get("run_status"),
            "post": auto.get("equiv"),
            "cvdp": (data.get("cvdp_replay") or {}).get("passed"),
            "area": metrics.get("area_um2"),
            "power": metrics.get("power_uw"),
            "wns": metrics.get("wns_ns"),
            "tns": metrics.get("tns_ns"),
        })

    lines = ["# Experiments Dashboard", ""]
    header = "| run | problem | flow | agent | model | status | synth | cvdp | area_um2 | power_uw | wns_ns | tns_ns |"
    lines.append(header)
    lines.append("|---|---|---|---|---|---|---|---|---:|---:|---:|---:|")
    for r in rows:
        lines.append(
            f"| {r['run']} | {r['problem']} | {r['flow']} | {r['agent']} | {r['model']} | "
            f"{r['status']} | {r['synth']} | {r['cvdp']} | {r['area']} | {r['power']} | {r['wns']} | {r['tns']} |"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return output


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Generate benchmark experiments dashboard.")
    root = repo_root()
    orch = orchestrator_root(root)
    ap.add_argument("--runs-root", default=str(orch / "runs"))
    ap.add_argument("--output", default=str(orch / "experiments_dashboard.md"))
    args = ap.parse_args(argv)
    out = build_dashboard(Path(args.runs_root), Path(args.output))
    print(f"Wrote dashboard: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
