from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import copy
import json

import yaml


SUPPORTED_AGENTS = {"codex", "fake", "claude", "antigravity"}
SUPPORTED_KINDS = {"yaml_spec", "prompt", "cvdp_agentic_jsonl"}
SUPPORTED_EVALUATORS = {"siliconcrew_pnr", "cvdp_replay_harness", "none"}


@dataclass(frozen=True)
class ProjectConfig:
    enabled: bool
    name: str | None


@dataclass(frozen=True)
class ProblemConfig:
    id: str
    suite: str
    kind: str
    flow: str
    agent: str
    model: str
    mcp_server: str
    timeout_sec: int
    evaluation: str
    path: Path | None = None
    dataset: Path | None = None
    datapoint_id: str | None = None
    text: str | None = None


@dataclass(frozen=True)
class BenchmarkConfig:
    name: str
    project: ProjectConfig
    defaults: dict[str, Any]
    problems: list[ProblemConfig]
    source_path: Path


def _resolve_path(repo_root: Path, value: str | None) -> Path | None:
    if not value:
        return None
    p = Path(value)
    if not p.is_absolute():
        p = repo_root / p
    return p.resolve()


def load_config(path: Path, repo_root: Path) -> BenchmarkConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("Benchmark config must be a YAML mapping.")
    name = str(raw.get("name") or "").strip()
    if not name:
        raise ValueError("Benchmark config requires 'name'.")

    defaults = dict(raw.get("defaults") or {})
    project_raw = dict(raw.get("project") or {})
    project = ProjectConfig(
        enabled=bool(project_raw.get("enabled", True)),
        name=str(project_raw.get("name") or f"bench_{name}").strip() or None,
    )

    rows = raw.get("problems") or []
    if not isinstance(rows, list) or not rows:
        raise ValueError("Benchmark config requires a non-empty 'problems' list.")

    problems: list[ProblemConfig] = []
    for idx, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise ValueError(f"Problem {idx} must be a mapping.")
        merged = copy.deepcopy(defaults)
        merged.update(row)

        pid = str(merged.get("id") or "").strip()
        suite = str(merged.get("suite") or "").strip()
        kind = str(merged.get("kind") or "").strip()
        agent = str(merged.get("agent") or "").strip()
        evaluation = str(merged.get("evaluation") or "none").strip()
        if not pid or not suite or not kind:
            raise ValueError(f"Problem {idx} requires id, suite, and kind.")
        if kind not in SUPPORTED_KINDS:
            raise ValueError(f"Unsupported problem kind '{kind}' for {pid}.")
        if agent not in SUPPORTED_AGENTS:
            raise ValueError(f"Unsupported agent '{agent}' for {pid}.")
        if evaluation not in SUPPORTED_EVALUATORS:
            raise ValueError(f"Unsupported evaluator '{evaluation}' for {pid}.")

        flow = str(merged.get("flow") or "verilog").strip()
        model = str(merged.get("model") or "default").strip()
        mcp_server = str(merged.get("mcp_server") or "rtl-codex").strip()
        timeout_sec = int(merged.get("timeout_sec") or 5400)

        p = ProblemConfig(
            id=pid,
            suite=suite,
            kind=kind,
            flow=flow,
            agent=agent,
            model=model,
            mcp_server=mcp_server,
            timeout_sec=timeout_sec,
            evaluation=evaluation,
            path=_resolve_path(repo_root, merged.get("path")),
            dataset=_resolve_path(repo_root, merged.get("dataset")),
            datapoint_id=merged.get("datapoint_id"),
            text=merged.get("text"),
        )
        _validate_problem(p)
        problems.append(p)

    return BenchmarkConfig(name=name, project=project, defaults=defaults, problems=problems, source_path=path.resolve())


def _validate_problem(problem: ProblemConfig) -> None:
    if problem.kind == "yaml_spec":
        if not problem.path:
            raise ValueError(f"{problem.id}: yaml_spec requires path.")
    elif problem.kind == "prompt":
        if not problem.path and not problem.text:
            raise ValueError(f"{problem.id}: prompt requires path or text.")
    elif problem.kind == "cvdp_agentic_jsonl":
        if not problem.dataset or not problem.datapoint_id:
            raise ValueError(f"{problem.id}: cvdp_agentic_jsonl requires dataset and datapoint_id.")


def problem_to_jsonable(problem: ProblemConfig) -> dict[str, Any]:
    data = problem.__dict__.copy()
    for key in ("path", "dataset"):
        if data.get(key) is not None:
            data[key] = str(data[key])
    return data


def problem_from_jsonable(data: dict[str, Any]) -> ProblemConfig:
    restored = dict(data)
    for key in ("path", "dataset"):
        if restored.get(key) is not None:
            restored[key] = Path(restored[key])
    return ProblemConfig(**restored)


def config_to_jsonable(config: BenchmarkConfig) -> dict[str, Any]:
    return {
        "name": config.name,
        "project": config.project.__dict__,
        "defaults": config.defaults,
        "source_path": str(config.source_path),
        "problems": [problem_to_jsonable(p) for p in config.problems],
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8", newline="\n")
