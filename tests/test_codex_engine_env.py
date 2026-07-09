"""Regression test for the bound-session MCP subprocess env allowlist.

_config_overrides() must forward the settings keys mcp_server.py needs to
resolve the SAME engine as the parent (hosted flag, persistence/workspace
backends, etc.) — but that env transits through the Codex CLI's own
config/argv, so it must NEVER carry LLM provider keys or other secrets no MCP
tool touches. This guards against silently regressing to `dict(os.environ)`
(which leaked OPENAI_API_KEY/ANTHROPIC_API_KEY/DATABASE_URL password/etc. into
the Codex CLI's process env and command line).
"""
from src.agents.codex.codex_engine import CodexEngine, CodexTurn


def _turn(**overrides):
    base = dict(
        session_id="p1", thread_id="t1", message="hi", workspace="/tmp/ws",
        user_id="user_123", model_name="gpt-5",
    )
    base.update(overrides)
    return CodexTurn(**base)


def _env_overrides(overrides: tuple[str, ...]) -> dict[str, str]:
    """Parse the `mcp_servers.siliconcrew.env.<KEY>=<json-value>` overrides
    back into a plain dict, mirroring how codex_engine builds them."""
    import json
    prefix = "mcp_servers.siliconcrew.env."
    out = {}
    for line in overrides:
        if line.startswith(prefix):
            key, _, raw_value = line[len(prefix):].partition("=")
            out[key] = json.loads(raw_value)
    return out


def test_mcp_subprocess_env_never_carries_llm_or_secret_keys(monkeypatch, tmp_path):
    # Simulate a fully-populated hosted production environment, including every
    # secret the parent process legitimately holds.
    monkeypatch.setenv("SILICONCREW_HOSTED", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:hunter2@cloudsql/db")
    monkeypatch.setenv("PERSISTENCE_ENGINE", "postgres")
    monkeypatch.setenv("WORKSPACE_ENGINE", "cloud")
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_abc")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-should-not-leak")
    monkeypatch.setenv("GOOGLE_API_KEY", "goog-should-not-leak")
    monkeypatch.setenv("HOSTED_GEMINI_KEY", "gemini-should-not-leak")
    monkeypatch.setenv("KMS_KEY_URI", "projects/x/locations/y/keyRings/z/cryptoKeys/k")
    monkeypatch.setenv("WORKOS_API_KEY", "workos-secret-should-not-leak")
    monkeypatch.setenv("SILICONCREW_TEST_BEARER_TOKEN", "test-bearer-should-not-leak")
    monkeypatch.setenv("ORFS_SERVICE_TOKEN", "orfs-bearer-should-not-leak")

    engine = CodexEngine(enabled=True, state_dir=str(tmp_path / "state"),
                          local_sqlite_dir=str(tmp_path / "sqlite"),
                          mcp_data_dir=str(tmp_path / "data"),
                          repo_root=str(tmp_path))
    engine._workspace_base = str(tmp_path / "ws")
    turn = _turn()

    env = _env_overrides(engine._config_overrides(turn))

    # Needed settings DO transit.
    assert env["SILICONCREW_HOSTED"] == "1"
    assert env["DATABASE_URL"] == "postgresql://user:hunter2@cloudsql/db"
    assert env["PERSISTENCE_ENGINE"] == "postgres"
    assert env["WORKSPACE_ENGINE"] == "cloud"
    assert env["WORKOS_CLIENT_ID"] == "client_abc"
    assert env["RTL_WORKSPACE"] == engine._workspace_base
    # 4B: the parent owns the once-per-turn workspace sync, so the bound
    # subprocess must be told to skip its per-tool blocking upload.
    assert env["SILICONCREW_MCP_DEFER_WORKSPACE_SYNC"] == "1"

    # Secrets no MCP tool needs must NEVER transit through the Codex CLI.
    leaked = {k: v for k, v in env.items() if "should-not-leak" in v}
    assert leaked == {}, f"secret(s) leaked into the Codex CLI's env/argv: {leaked}"
    for forbidden in (
        "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "HOSTED_GEMINI_KEY",
        "KMS_KEY_URI", "WORKOS_API_KEY", "SILICONCREW_TEST_BEARER_TOKEN", "ORFS_SERVICE_TOKEN",
    ):
        assert forbidden not in env, f"{forbidden} must not be forwarded to the MCP subprocess"


def test_mcp_subprocess_env_omits_unset_passthrough_keys(monkeypatch, tmp_path):
    # None of the passthrough keys are set — the override list should just
    # skip them, not emit empty/placeholder values.
    for key in (
        "SILICONCREW_HOSTED", "DATABASE_URL", "PERSISTENCE_ENGINE", "WORKSPACE_ENGINE",
        "WORKOS_CLIENT_ID", "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)

    engine = CodexEngine(enabled=True, state_dir=str(tmp_path / "state"),
                          local_sqlite_dir=str(tmp_path / "sqlite"),
                          mcp_data_dir=str(tmp_path / "data"),
                          repo_root=str(tmp_path))
    engine._workspace_base = str(tmp_path / "ws")
    env = _env_overrides(engine._config_overrides(_turn()))

    assert "SILICONCREW_HOSTED" not in env
    assert "DATABASE_URL" not in env
    # The explicit overrides (workspace/data dir/buffering) always transit.
    assert env["RTL_DATA_DIR"] == engine.mcp_data_dir
    assert env["PYTHONUNBUFFERED"] == "1"
