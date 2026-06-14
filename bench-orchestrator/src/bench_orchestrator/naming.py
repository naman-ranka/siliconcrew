from __future__ import annotations

from pathlib import Path
import re


def slug(value: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip())
    s = s.strip("-_.").lower()
    return s or "run"


def model_slug(value: str) -> str:
    return slug(value).replace("-", "").replace(".", "")


def run_base_name(suite: str, problem_id: str, flow: str, agent: str, model: str, timestamp: str) -> str:
    suite_s = slug(suite)
    problem_s = slug(problem_id)
    for prefix in (f"{suite_s}-", f"{suite_s}_"):
        if problem_s.startswith(prefix):
            problem_s = problem_s[len(prefix):]
            break
    return f"{suite_s}-{problem_s}__{slug(flow)}__{slug(agent)}-{model_slug(model)}__{timestamp}"


def allocate_run_dir(runs_root: Path, suite: str, problem_id: str, flow: str, agent: str, model: str, timestamp: str) -> Path:
    base = run_base_name(suite, problem_id, flow, agent, model, timestamp)
    for i in range(1, 1000):
        candidate = runs_root / f"{base}__r{i:02d}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not allocate run directory for {base}.")


def session_name(problem_id: str, flow: str, agent: str, model: str, timestamp: str, repeat: int = 1) -> str:
    return f"{slug(problem_id)}__{slug(flow)}__{slug(agent)}_{model_slug(model)}__{timestamp}__r{repeat:02d}"
