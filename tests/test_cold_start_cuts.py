"""4C (hosted-latency plan): Codex cold-start quick cuts.

The Codex MCP subprocess is spawned fresh per turn (until warm-keep lands), so
its startup cost is paid before every first token. Two of the measured costs:
unconditional schema DDL on a fresh Cloud SQL connection, and an eager import
of the LangGraph agent module that only backs a rarely-used prompt fallback.
"""
import os
import subprocess
import sys


class _RecordingStore:
    def __init__(self):
        self.init_calls = 0

    def init_schema(self):
        self.init_calls += 1


def test_session_manager_skips_ddl_when_schema_ready(tmp_path, monkeypatch):
    """SILICONCREW_SCHEMA_READY=1 (set by codex_engine for its bound subprocess;
    the parent app provisioned the schema at boot) skips init_schema()."""
    from src.utils.session_manager import SessionManager

    store = _RecordingStore()
    monkeypatch.setenv("SILICONCREW_SCHEMA_READY", "1")
    SessionManager(base_dir=str(tmp_path / "ws"), db_path=str(tmp_path / "state.db"),
                   metadata_store=store)
    assert store.init_calls == 0


def test_session_manager_provisions_schema_by_default(tmp_path, monkeypatch):
    from src.utils.session_manager import SessionManager

    store = _RecordingStore()
    monkeypatch.delenv("SILICONCREW_SCHEMA_READY", raising=False)
    SessionManager(base_dir=str(tmp_path / "ws"), db_path=str(tmp_path / "state.db"),
                   metadata_store=store)
    assert store.init_calls == 1


def test_codex_engine_marks_subprocess_schema_ready(tmp_path):
    from src.agents.codex.codex_engine import CodexEngine, CodexTurn

    engine = CodexEngine(enabled=True, state_dir=str(tmp_path / "s"),
                         local_sqlite_dir=str(tmp_path / "q"),
                         mcp_data_dir=str(tmp_path / "d"), repo_root=str(tmp_path))
    engine._workspace_base = str(tmp_path / "ws")
    turn = CodexTurn(session_id="p1", thread_id="t1", message="hi",
                     workspace=str(tmp_path / "ws"), user_id="u", model_name="m")
    overrides = engine._config_overrides(turn)
    assert any(
        line == 'mcp_servers.siliconcrew.env.SILICONCREW_SCHEMA_READY="1"'
        for line in overrides
    ), overrides


def test_mcp_server_import_does_not_pull_langgraph_agent():
    """src.agents.architect (langgraph prebuilt + langsmith client) exists in
    mcp_server only as the prompt-file fallback — importing it eagerly taxed
    every subprocess spawn. Run in a subprocess so the interpreter is cold."""
    code = (
        "import mcp_server, sys; "
        "assert 'src.agents.architect' not in sys.modules, 'architect imported eagerly'"
    )
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run([sys.executable, "-c", code], cwd=repo,
                          capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr
