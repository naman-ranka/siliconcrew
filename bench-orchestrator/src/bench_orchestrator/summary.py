from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import shutil

SOURCE_SUFFIXES = {".x", ".v", ".sv", ".svh", ".yaml", ".yml", ".md"}
SKIP_DIRS = {"synth_runs", "sim_build", "__pycache__", ".git"}


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def find_workspace(run_dir: Path, explicit: str | None = None) -> Path | None:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p.resolve()
    fake = run_dir / "raw" / "fake_sc_workspace"
    if fake.exists():
        return fake.resolve()
    ref = read_json(run_dir / "sc_workspace_ref.json")
    if isinstance(ref, dict) and ref.get("workspace"):
        p = Path(ref["workspace"])
        if p.exists():
            return p.resolve()
    config = read_json(run_dir / "run_config.json")
    if isinstance(config, dict):
        session = config.get("session") if isinstance(config.get("session"), dict) else {}
        session_name = session.get("name")
        project_id = session.get("project_id")
        for root in _repo_roots_from_run_dir(run_dir):
            candidates = []
            if project_id and session_name:
                candidates.extend([
                    root / "workspace_new" / str(project_id) / str(session_name),
                    root / "workspace" / str(project_id) / str(session_name),
                ])
            if session_name:
                candidates.extend([
                    root / "workspace_new" / str(session_name),
                    root / "workspace" / str(session_name),
                ])
            for candidate in candidates:
                if candidate.exists():
                    return candidate.resolve()
    return None


def _repo_roots_from_run_dir(run_dir: Path) -> list[Path]:
    roots: list[Path] = []
    resolved = run_dir.resolve()
    for parent in [resolved, *resolved.parents]:
        if parent.name == "bench-orchestrator" and parent.parent not in roots:
            roots.append(parent.parent)
        if (parent / "mcp_server.py").exists() and parent not in roots:
            roots.append(parent)
    return roots


def extract_sc_summary(workspace: Path | None) -> dict[str, Any]:
    if not workspace or not workspace.exists():
        return {"workspace": str(workspace) if workspace else None, "found": False}
    latest = None
    latest_path = workspace / "synth_runs" / "LATEST"
    if latest_path.exists():
        latest = latest_path.read_text(encoding="utf-8").strip()
    run_meta = None
    if latest:
        run_meta = read_json(workspace / "synth_runs" / latest / "run_meta.json")
    attempt_log = read_json(workspace / "attempt_log.json")
    return {
        "workspace": str(workspace),
        "found": True,
        "latest_run_id": latest,
        "run_meta": run_meta,
        "attempt_log": attempt_log,
        "attempt_events": str(workspace / "attempt_events.jsonl") if (workspace / "attempt_events.jsonl").exists() else None,
    }


def copy_generated_sources(workspace: Path | None, out_dir: Path) -> list[str]:
    copied: list[str] = []
    if not workspace or not workspace.exists():
        return copied
    out_dir.mkdir(parents=True, exist_ok=True)
    for src in workspace.rglob("*"):
        if not src.is_file():
            continue
        rel = src.relative_to(workspace)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if src.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        dst = out_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        copied.append(rel.as_posix())
    return sorted(copied)


def parse_cvdp_replay(run_dir: Path) -> dict[str, Any] | None:
    candidates = list((run_dir / "raw").glob("*replay*_result.json")) if (run_dir / "raw").exists() else []
    candidates += list((run_dir / "raw").glob("cvdp_replay_result.json")) if (run_dir / "raw").exists() else []
    for p in candidates:
        data = read_json(p)
        if isinstance(data, dict):
            data["result_path"] = str(p)
            return data
    return None


def make_run_summary(
    run_dir: Path,
    run_config: dict[str, Any],
    runner_status: str,
    runner_exit_code: int,
    workspace: Path | None,
    generated_sources: list[str],
) -> dict[str, Any]:
    sc = extract_sc_summary(workspace)
    meta = sc.get("run_meta") if isinstance(sc, dict) else None
    attempts = sc.get("attempt_log") if isinstance(sc, dict) else None
    metrics = meta.get("summary_metrics") if isinstance(meta, dict) else None
    auto_checks = meta.get("auto_checks") if isinstance(meta, dict) else None
    cvdp = parse_cvdp_replay(run_dir)
    return {
        "status": _overall_status(runner_status, meta, cvdp),
        "runner_status": runner_status,
        "runner_exit_code": runner_exit_code,
        "problem": run_config.get("problem", {}),
        "agent": run_config.get("agent"),
        "model": run_config.get("model"),
        "flow": run_config.get("flow"),
        "session": run_config.get("session", {}),
        "siliconcrew": {
            "workspace": sc.get("workspace"),
            "workspace_found": sc.get("found"),
            "latest_run_id": sc.get("latest_run_id"),
            "run_status": meta.get("status") if isinstance(meta, dict) else None,
            "auto_checks": auto_checks,
            "summary_metrics": metrics,
            "attempt_count": attempts.get("attempt_count") if isinstance(attempts, dict) else None,
        },
        "cvdp_replay": cvdp,
        "generated_sources": generated_sources,
    }


def _overall_status(runner_status: str, run_meta: dict[str, Any] | None, cvdp: dict[str, Any] | None) -> str:
    if cvdp is not None:
        return "passed" if cvdp.get("passed") else "failed"
    if isinstance(run_meta, dict) and run_meta.get("status") == "completed":
        return "passed"
    if runner_status == "completed":
        return "completed"
    return "failed"
