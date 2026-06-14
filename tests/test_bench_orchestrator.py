import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
ORCH = REPO / "bench-orchestrator"
SRC = ORCH / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from bench_orchestrator.config import SUPPORTED_AGENTS, load_config
from bench_orchestrator.dashboard import build_dashboard
from bench_orchestrator.naming import allocate_run_dir, run_base_name
from bench_orchestrator.problems import find_cvdp_datapoint
from bench_orchestrator.runners import _codex_auth_flag, ensure_antigravity_mcp_config
from bench_orchestrator.sc_project import project_id_for_name
from bench_orchestrator.summary import copy_generated_sources, extract_sc_summary, find_workspace
from bench_orchestrator.trace import has_failed_agent_event, write_agent_trace


def test_config_parses_defaults_and_problem_paths(tmp_path):
    spec = tmp_path / "p.yaml"
    spec.write_text("demo: {}\n", encoding="utf-8")
    cfg_path = tmp_path / "bench.yaml"
    cfg_path.write_text(
        f"""
name: t
defaults:
  agent: fake
  model: gpt-5.5
  flow: xls
  mcp_server: rtl-codex
problems:
  - id: p7
    suite: asu
    kind: yaml_spec
    path: {spec.as_posix()}
    evaluation: siliconcrew_pnr
""",
        encoding="utf-8",
    )
    cfg = load_config(cfg_path, REPO)
    assert cfg.problems[0].agent == "fake"
    assert cfg.problems[0].flow == "xls"
    assert cfg.problems[0].path == spec.resolve()


def test_config_accepts_claude_and_antigravity_agents(tmp_path):
    spec = tmp_path / "p.yaml"
    spec.write_text("demo: {}\n", encoding="utf-8")
    assert {"claude", "antigravity"}.issubset(SUPPORTED_AGENTS)
    for agent in ("claude", "antigravity"):
        cfg_path = tmp_path / f"{agent}.yaml"
        cfg_path.write_text(
            f"""
name: t
defaults:
  agent: {agent}
  model: gpt-5.5
  flow: verilog
  mcp_server: rtl-codex
problems:
  - id: p7
    suite: asu
    kind: yaml_spec
    path: {spec.as_posix()}
    evaluation: siliconcrew_pnr
""",
            encoding="utf-8",
        )
        cfg = load_config(cfg_path, REPO)
        assert cfg.problems[0].agent == agent


def test_antigravity_mcp_config_is_written(tmp_path):
    config = tmp_path / "mcp_config.json"
    data = ensure_antigravity_mcp_config(config, "rtl-codex", "python", ["mcp_server.py", "--codex-tools"])
    assert data["mcpServers"]["rtl-codex"]["command"] == "python"
    saved = json.loads(config.read_text(encoding="utf-8"))
    assert saved["mcpServers"]["rtl-codex"]["args"] == ["mcp_server.py", "--codex-tools"]


def test_codex_runner_uses_bypass_auth_flag():
    assert _codex_auth_flag() == "--dangerously-bypass-approvals-and-sandbox"


def test_project_id_for_name_is_side_effect_free():
    assert project_id_for_name("bench asu p7", True) == "benchasup7"
    assert project_id_for_name("bench asu p7", False) is None


def test_run_naming_allocates_repeat_dirs(tmp_path):
    base = run_base_name("asu", "p9", "xls", "codex", "gpt-5.5", "20260608-153012")
    assert base == "asu-p9__xls__codex-gpt55__20260608-153012"
    assert run_base_name("asu", "asu_p7", "xls", "fake", "gpt-5.5", "t") == "asu-p7__xls__fake-gpt55__t"
    first = allocate_run_dir(tmp_path, "asu", "p9", "xls", "codex", "gpt-5.5", "20260608-153012")
    first.mkdir()
    second = allocate_run_dir(tmp_path, "asu", "p9", "xls", "codex", "gpt-5.5", "20260608-153012")
    assert first.name.endswith("__r01")
    assert second.name.endswith("__r02")


def test_extract_sc_summary_and_copy_sources(tmp_path):
    ws = tmp_path / "ws"
    synth = ws / "synth_runs" / "synth_0001"
    synth.mkdir(parents=True)
    (ws / "synth_runs" / "LATEST").write_text("synth_0001", encoding="utf-8")
    (synth / "run_meta.json").write_text(json.dumps({"status": "completed", "summary_metrics": {"area_um2": 2}}), encoding="utf-8")
    (ws / "top.v").write_text("module top; endmodule\n", encoding="utf-8")
    (synth / "big.v").write_text("module big; endmodule\n", encoding="utf-8")

    summary = extract_sc_summary(ws)
    assert summary["latest_run_id"] == "synth_0001"
    assert summary["run_meta"]["summary_metrics"]["area_um2"] == 2
    copied = copy_generated_sources(ws, tmp_path / "out")
    assert copied == ["top.v"]


def test_find_workspace_infers_project_sc_layout(tmp_path):
    repo = tmp_path / "repo"
    run = repo / "bench-orchestrator" / "runs" / "asu-p7__xls__fake-gpt55__t__r01"
    ws = repo / "workspace_new" / "benchproj" / "asu_p7_xls_fake_gpt55"
    run.mkdir(parents=True)
    ws.mkdir(parents=True)
    (repo / "mcp_server.py").write_text("# fixture\n", encoding="utf-8")
    (run / "run_config.json").write_text(
        json.dumps({"session": {"name": "asu_p7_xls_fake_gpt55", "project_id": "benchproj"}}),
        encoding="utf-8",
    )

    assert find_workspace(run) == ws.resolve()


def test_trace_generation_from_fake_events(tmp_path):
    agent = tmp_path / "agent.jsonl"
    agent.write_text(json.dumps({"type": "item.completed", "item": {"type": "mcp_tool_call", "tool": "linter_tool", "status": "completed"}}) + "\n", encoding="utf-8")
    sc = tmp_path / "attempt_events.jsonl"
    sc.write_text(json.dumps({"event_type": "tool_call", "tool": "simulation_tool"}) + "\n", encoding="utf-8")
    summary = {"problem": {"id": "p"}, "flow": "xls", "agent": "fake", "status": "completed", "siliconcrew": {}}
    out = write_agent_trace(tmp_path, agent, sc, summary)
    text = out.read_text(encoding="utf-8")
    assert "`linter_tool`" in text
    assert "call `simulation_tool`" in text


def test_failed_agent_event_detection(tmp_path):
    agent = tmp_path / "agent.jsonl"
    agent.write_text(
        json.dumps({"type": "item.completed", "item": {"type": "mcp_tool_call", "tool": "create_session_tool", "status": "failed"}}) + "\n",
        encoding="utf-8",
    )
    assert has_failed_agent_event(agent) is True


def test_cvdp_datapoint_lookup(tmp_path):
    dataset = tmp_path / "d.jsonl"
    dataset.write_text(json.dumps({"id": "a", "prompt": "x"}) + "\n", encoding="utf-8")
    assert find_cvdp_datapoint(dataset, "a")["prompt"] == "x"
    with pytest.raises(ValueError):
        find_cvdp_datapoint(dataset, "missing")


def test_fake_agent_cli_creates_standard_run_folder(tmp_path):
    spec = tmp_path / "p.yaml"
    spec.write_text("demo: {}\n", encoding="utf-8")
    cfg = tmp_path / "bench.yaml"
    cfg.write_text(
        f"""
name: fake_cli
project:
  enabled: false
defaults:
  agent: fake
  model: gpt-5.5
  flow: verilog
  mcp_server: rtl-codex
problems:
  - id: p1
    suite: asu
    kind: yaml_spec
    path: {spec.as_posix()}
    evaluation: siliconcrew_pnr
""",
        encoding="utf-8",
    )
    cmd = [sys.executable, str(ORCH / "run_benchmark.py"), "--config", str(cfg), "--runs-root", str(tmp_path / "runs")]
    proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    runs = list((tmp_path / "runs").glob("*"))
    assert len(runs) == 1
    run = runs[0]
    assert (run / "run_config.json").exists()
    assert (run / "run_summary.json").exists()
    assert (run / "agent_trace.md").exists()
    assert (run / "agent_events.jsonl").exists()
    assert (run / "generated_sources" / "demo.v").exists()
    summary = json.loads((run / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["status"] == "passed"
    assert summary["siliconcrew"]["summary_metrics"]["wns_ns"] == 0.1


def test_resume_cli_appends_continuation_and_refreshes_summary(tmp_path):
    spec = tmp_path / "p.yaml"
    spec.write_text("demo: {}\n", encoding="utf-8")
    cfg = tmp_path / "bench.yaml"
    cfg.write_text(
        f"""
name: fake_resume
project:
  enabled: false
defaults:
  agent: fake
  model: gpt-5.5
  flow: verilog
  mcp_server: rtl-codex
problems:
  - id: p1
    suite: asu
    kind: yaml_spec
    path: {spec.as_posix()}
    evaluation: siliconcrew_pnr
""",
        encoding="utf-8",
    )
    runs_root = tmp_path / "runs"
    first = subprocess.run(
        [sys.executable, str(ORCH / "run_benchmark.py"), "--config", str(cfg), "--runs-root", str(runs_root)],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    assert first.returncode == 0, first.stderr + first.stdout
    run = next(runs_root.glob("*"))

    resumed = subprocess.run(
        [
            sys.executable,
            str(ORCH / "run_benchmark.py"),
            "--resume",
            str(run),
            "--prompt",
            "Lower power and refresh metrics.",
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    assert resumed.returncode == 0, resumed.stderr + resumed.stdout
    assert (run / "continuations" / "001" / "agent_events.jsonl").exists()
    assert (run / "continuations" / "001" / "prompt.txt").read_text(encoding="utf-8") == "Lower power and refresh metrics."

    cfg_data = json.loads((run / "run_config.json").read_text(encoding="utf-8"))
    assert len(cfg_data["continuations"]) == 1
    assert cfg_data["continuations"][0]["status"] == "completed"

    summary = json.loads((run / "run_summary.json").read_text(encoding="utf-8"))
    assert summary["siliconcrew"]["latest_run_id"] == "synth_0002"
    assert summary["siliconcrew"]["summary_metrics"]["power_uw"] == 1.5
    assert len(summary["continuations"]) == 1
    trace = (run / "agent_trace.md").read_text(encoding="utf-8")
    assert "Continuation 001" in trace
    assert "`set_active_session`" in trace


def test_dry_run_cli_does_not_create_runs(tmp_path):
    spec = tmp_path / "p.yaml"
    spec.write_text("demo: {}\n", encoding="utf-8")
    cfg = tmp_path / "bench.yaml"
    cfg.write_text(
        f"""
name: dry
project:
  enabled: false
defaults:
  agent: fake
  model: gpt-5.5
  flow: xls
  mcp_server: rtl-codex
problems:
  - id: p1
    suite: asu
    kind: yaml_spec
    path: {spec.as_posix()}
    evaluation: none
""",
        encoding="utf-8",
    )
    runs_root = tmp_path / "runs"
    cmd = [sys.executable, str(ORCH / "run_benchmark.py"), "--config", str(cfg), "--runs-root", str(runs_root), "--dry-run"]
    proc = subprocess.run(cmd, cwd=REPO, text=True, capture_output=True)
    assert proc.returncode == 0
    assert "session_name" in proc.stdout
    assert not runs_root.exists()


def test_dashboard_generation(tmp_path):
    run = tmp_path / "runs" / "one"
    run.mkdir(parents=True)
    (run / "run_summary.json").write_text(json.dumps({
        "problem": {"id": "p1"},
        "flow": "xls",
        "agent": "fake",
        "model": "gpt-5.5",
        "status": "passed",
        "siliconcrew": {"run_status": "completed", "summary_metrics": {"area_um2": 1, "power_uw": 2, "wns_ns": 0, "tns_ns": 0}},
    }), encoding="utf-8")
    out = build_dashboard(tmp_path / "runs", tmp_path / "dash.md")
    text = out.read_text(encoding="utf-8")
    assert "p1" in text
    assert "area_um2" in text
