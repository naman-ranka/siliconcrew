from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
import argparse
import json
import shutil

from .config import config_to_jsonable, load_config, problem_from_jsonable, problem_to_jsonable, write_json
from .naming import allocate_run_dir, session_name
from .paths import orchestrator_root, repo_root
from .problems import build_agent_prompt, prepare_problem
from .runners import get_runner, preflight
from .sc_project import ensure_project, project_id_for_name
from .summary import copy_generated_sources, find_workspace, make_run_summary
from .trace import extract_thread_id, has_failed_agent_event, write_agent_trace


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run repeatable SiliconCrew benchmark experiments.")
    sub = ap.add_subparsers(dest="command")
    p_pre = sub.add_parser("preflight", help="Check external agent/MCP prerequisites.")
    p_pre.add_argument("--agent", default="codex")
    p_pre.add_argument("--mcp-server", default="rtl-codex")

    ap.add_argument("--config", help="Benchmark YAML config.")
    ap.add_argument("--runs-root", help="Override run output root.")
    ap.add_argument("--dry-run", action="store_true", help="Validate and plan runs without launching agents.")
    ap.add_argument("--agent", help="Override config agent.")
    ap.add_argument("--model", help="Override config model.")
    ap.add_argument("--resume", help="Existing run directory to continue.")
    ap.add_argument("--prompt", help="Follow-up prompt for --resume.")
    ap.add_argument("--prompt-file", help="File containing follow-up prompt for --resume.")
    args = ap.parse_args(argv)

    if args.command == "preflight":
        return preflight(args.agent, args.mcp_server)
    if args.resume:
        return _resume_run(Path(args.resume), _read_resume_prompt(args.prompt, args.prompt_file))
    if not args.config:
        ap.error("--config is required unless using a subcommand")

    root = repo_root()
    orch = orchestrator_root(root)
    runs_root = Path(args.runs_root).resolve() if args.runs_root else orch / "runs"
    cfg = load_config(Path(args.config), root)
    project_id = (
        project_id_for_name(cfg.project.name, cfg.project.enabled)
        if args.dry_run
        else ensure_project(root, cfg.project.name, cfg.project.enabled)
    )

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    planned: list[dict[str, Any]] = []
    for problem in cfg.problems:
        if args.agent or args.model:
            problem = _override_problem(problem, agent=args.agent, model=args.model)
        run_dir = allocate_run_dir(runs_root, problem.suite, problem.id, problem.flow, problem.agent, problem.model, timestamp)
        sess = session_name(problem.id, problem.flow, problem.agent, problem.model, timestamp)
        planned.append({"problem": problem, "run_dir": run_dir, "session_name": sess})

    if args.dry_run:
        print(json.dumps({
            "config": config_to_jsonable(cfg),
            "project_id": project_id,
            "runs": [{"problem": p["problem"].id, "run_dir": str(p["run_dir"]), "session_name": p["session_name"]} for p in planned],
        }, indent=2))
        return 0

    for item in planned:
        _run_one(cfg, item["problem"], item["run_dir"], item["session_name"], project_id)
    return 0


def _override_problem(problem, agent: str | None = None, model: str | None = None):
    from dataclasses import replace
    kwargs = {}
    if agent:
        kwargs["agent"] = agent
    if model:
        kwargs["model"] = model
    return replace(problem, **kwargs)


def _clean_cwd_scratch() -> None:
    """Remove leftover rtl/ and verif/ scratch from the agent's cwd before a problem runs.

    The agent's GRADED deliverable lives in the isolated MCP session workspace (RTL_WORKSPACE), but its
    native tools (Claude Write/Bash, codex file_change) ALSO dump *.sv/*.py into the launch cwd. Across a
    multi-problem run those accumulate into a pile of prior near-solutions with module names matching other
    problems — and the agent does repo-wide name searches (Glob/rg), so it can read a previous problem's
    answer. leak_detector does not scan for that, so a contaminated run would score CLEAN. Wiping cwd scratch
    before each problem closes the vector. SAFE only because each shard runs in its OWN cwd (see the launcher);
    otherwise parallel shards would race on a shared cwd.
    """
    for name in ("rtl", "verif"):
        shutil.rmtree(Path.cwd() / name, ignore_errors=True)


def _run_one(cfg, problem, run_dir: Path, sess: str, project_id: str | None) -> None:
    run_dir.mkdir(parents=True, exist_ok=False)
    _clean_cwd_scratch()
    prepared = prepare_problem(problem, run_dir)
    run_config = {
        "benchmark": cfg.name,
        "config_path": str(cfg.source_path),
        "project_id": project_id,
        "problem": problem_to_jsonable(problem),
        "prepared_problem": prepared,
        "agent": problem.agent,
        "model": problem.model,
        "flow": problem.flow,
        "evaluation": problem.evaluation,
        "session": {"name": sess, "project_id": project_id},
    }
    # Redact the raw-dataset path from the agent-readable run_config.json: it embeds every problem's hidden
    # harness, and a stuck agent that reads run_config -> Get-Content the dataset is a confirmed leak vector
    # (leak_detector catches it, but don't hand over the breadcrumb). The orchestrator/grader still know the
    # path from the (agent-out-of-reach) YAML config; only this per-run copy is scrubbed.
    def _redact(o):
        if isinstance(o, dict):
            return {k: ("<redacted>" if k == "dataset" else _redact(v)) for k, v in o.items()}
        if isinstance(o, list):
            return [_redact(v) for v in o]
        return o
    write_json(run_dir / "run_config.json", _redact(run_config))

    prompt = build_agent_prompt(problem, prepared, sess, project_id)
    (run_dir / "raw").mkdir(parents=True, exist_ok=True)
    (run_dir / "raw" / "agent_prompt.txt").write_text(prompt, encoding="utf-8", newline="\n")

    result = get_runner(problem.agent).run(prompt, run_dir, problem.model, problem.timeout_sec)
    thread_id = extract_thread_id(result.events_path)
    if thread_id:
        run_config["agent_thread_id"] = thread_id
        write_json(run_dir / "run_config.json", run_config)
    workspace = find_workspace(run_dir)
    if workspace:
        write_json(run_dir / "sc_workspace_ref.json", {"workspace": str(workspace)})
    generated = copy_generated_sources(workspace, run_dir / "generated_sources")
    runner_status = _effective_runner_status(result)
    summary = make_run_summary(run_dir, run_config, runner_status, result.exit_code, workspace, generated)
    if thread_id:
        summary["agent_thread_id"] = thread_id
    write_json(run_dir / "run_summary.json", summary)
    sc_events = Path(summary["siliconcrew"]["workspace"]) / "attempt_events.jsonl" if summary["siliconcrew"].get("workspace") else None
    write_agent_trace(run_dir, result.events_path, sc_events, summary)
    print(f"Wrote run: {run_dir}")


def _read_resume_prompt(prompt: str | None, prompt_file: str | None) -> str:
    if prompt and prompt_file:
        raise ValueError("Use only one of --prompt or --prompt-file.")
    if prompt_file:
        return Path(prompt_file).read_text(encoding="utf-8")
    if prompt:
        return prompt
    raise ValueError("--resume requires --prompt or --prompt-file.")


def _resume_run(run_dir: Path, user_prompt: str) -> int:
    run_dir = run_dir.resolve()
    run_config_path = run_dir / "run_config.json"
    if not run_config_path.exists():
        raise FileNotFoundError(f"run_config.json not found in {run_dir}")
    run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
    problem = problem_from_jsonable(run_config["problem"])
    continuation_dir = _next_continuation_dir(run_dir)
    continuation_dir.mkdir(parents=True, exist_ok=False)
    (continuation_dir / "prompt.txt").write_text(user_prompt, encoding="utf-8", newline="\n")

    resume_prompt = _build_resume_prompt(run_config, user_prompt)
    (continuation_dir / "agent_prompt.txt").write_text(resume_prompt, encoding="utf-8", newline="\n")
    result = get_runner(problem.agent).resume(resume_prompt, run_dir, continuation_dir, problem.model, problem.timeout_sec)

    thread_id = extract_thread_id(result.events_path)
    cont = {
        "idx": int(continuation_dir.name),
        "prompt": str(continuation_dir / "prompt.txt"),
        "events": str(result.events_path),
        "last_message": str(result.last_message_path) if result.last_message_path else None,
        "status": _effective_runner_status(result),
        "exit_code": result.exit_code,
        "agent_thread_id": thread_id,
    }
    run_config.setdefault("continuations", []).append(cont)
    if thread_id:
        run_config["latest_agent_thread_id"] = thread_id
    write_json(run_config_path, run_config)

    workspace = find_workspace(run_dir)
    generated = copy_generated_sources(workspace, run_dir / "generated_sources")
    summary = make_run_summary(run_dir, run_config, _effective_runner_status(result), result.exit_code, workspace, generated)
    summary["continuations"] = run_config.get("continuations", [])
    if thread_id:
        summary["latest_agent_thread_id"] = thread_id
    write_json(run_dir / "run_summary.json", summary)

    sc_events = Path(summary["siliconcrew"]["workspace"]) / "attempt_events.jsonl" if summary["siliconcrew"].get("workspace") else None
    write_agent_trace(run_dir, _agent_event_paths(run_dir), sc_events, summary)
    print(f"Resumed run: {run_dir}")
    print(f"Continuation: {continuation_dir}")
    return 0


def _next_continuation_dir(run_dir: Path) -> Path:
    root = run_dir / "continuations"
    for i in range(1, 1000):
        p = root / f"{i:03d}"
        if not p.exists():
            return p
    raise RuntimeError(f"Could not allocate continuation directory under {root}")


def _build_resume_prompt(run_config: dict[str, Any], user_prompt: str) -> str:
    problem = run_config.get("problem", {})
    session = run_config.get("session", {})
    project_id = session.get("project_id")
    session_name = session.get("name")
    session_id = f"{project_id}/{session_name}" if project_id else session_name
    mcp_server = problem.get("mcp_server") or "rtl-codex"
    return (
        f'Use MCP server "{mcp_server}".\n\n'
        "Continue an existing SiliconCrew benchmark run. Do not create a new session.\n"
        f'1. Call set_active_session with session_id "{session_id}".\n'
        "2. If the active session needs prompt context, call inject_architect_prompt with that same session_id.\n"
        "3. Inspect the existing workspace files and latest synthesis/simulation state before changing anything.\n"
        "4. Apply this follow-up request, then rerun only the verification/synthesis steps needed to validate it.\n\n"
        f"Original problem id: {problem.get('id')}\n"
        f"Original flow: {run_config.get('flow')}\n\n"
        "Follow-up request:\n"
        f"{user_prompt}\n"
    )


def _agent_event_paths(run_dir: Path) -> list[Path]:
    paths: list[Path] = []
    initial = run_dir / "agent_events.jsonl"
    if initial.exists():
        paths.append(initial)
    for p in sorted((run_dir / "continuations").glob("*/agent_events.jsonl")) if (run_dir / "continuations").exists() else []:
        paths.append(p)
    return paths


def _effective_runner_status(result) -> str:
    if result.status == "completed" and has_failed_agent_event(result.events_path):
        return "failed"
    return result.status
