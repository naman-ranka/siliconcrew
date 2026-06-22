"""ToolEngine seam — SIM_ENGINE selection + docker/native execution (slice 1)."""
import os

import pytest

import src.platform_engines.tool_engine as te
from src.platform_engines.settings import reset_settings_cache


@pytest.fixture(autouse=True)
def _reset():
    te.set_tool_engine(None)
    reset_settings_cache()
    yield
    te.set_tool_engine(None)
    reset_settings_cache()


# --- selection --------------------------------------------------------------


def test_default_is_docker(monkeypatch):
    monkeypatch.delenv("SILICONCREW_HOSTED", raising=False)
    monkeypatch.delenv("SIM_ENGINE", raising=False)
    reset_settings_cache()
    assert te.get_tool_engine().mode == "docker"


def test_native_when_sim_engine_set(monkeypatch):
    monkeypatch.setenv("SIM_ENGINE", "native")
    reset_settings_cache()
    te.set_tool_engine(None)
    assert te.get_tool_engine().mode == "native"


def test_native_default_when_hosted(monkeypatch):
    monkeypatch.setenv("SILICONCREW_HOSTED", "1")
    monkeypatch.delenv("SIM_ENGINE", raising=False)
    reset_settings_cache()
    te.set_tool_engine(None)
    assert te.get_tool_engine().mode == "native"


def test_docker_override_under_hosted(monkeypatch):
    monkeypatch.setenv("SILICONCREW_HOSTED", "1")
    monkeypatch.setenv("SIM_ENGINE", "docker")
    reset_settings_cache()
    te.set_tool_engine(None)
    assert te.get_tool_engine().mode == "docker"


# --- docker engine wraps run_docker_command ---------------------------------


def test_docker_engine_wraps_run_docker_command(monkeypatch):
    calls = {}

    def fake_run_docker_command(**kwargs):
        calls.update(kwargs)
        return {"success": True, "stdout": "ok", "stderr": "", "command": "docker run ..."}

    monkeypatch.setattr("shutil.which", lambda _x: "/usr/bin/docker")
    monkeypatch.setattr("src.tools.run_docker.run_docker_command", fake_run_docker_command)

    res = te.DockerToolEngine().run(
        image="siliconcrew-xls:latest", command="interpreter_main design.x",
        cwd="/ws/sess1", env={"SC_X": "1"}, timeout=120, workdir="/workspace",
    )
    assert res["success"] and res["stdout"] == "ok"
    # Real per-session cwd is mounted as workspace_path; container workdir is /workspace.
    assert calls["workspace_path"] == "/ws/sess1"
    assert calls["cwd"] == "/workspace"
    assert calls["image"] == "siliconcrew-xls:latest"
    assert calls["env"] == {"SC_X": "1"}
    assert calls["timeout"] == 120
    assert calls["name"]  # a named container (hard-killed on timeout)


def test_docker_engine_reports_missing_docker(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _x: None)
    res = te.DockerToolEngine().run(image="img", command="x", cwd="/ws", timeout=10)
    assert not res["success"] and "Docker not found" in res["stderr"]


# --- native engine runs in the real cwd (cwd-relative paths) ----------------


def test_native_engine_runs_in_cwd_with_relative_paths(tmp_path):
    res = te.NativeToolEngine().run(
        image="unused", command="echo hello > out.txt", cwd=str(tmp_path), timeout=30
    )
    assert res["success"] and res["timed_out"] is False
    # The command's relative path resolved inside the per-session cwd.
    assert (tmp_path / "out.txt").read_text().strip() == "hello"


def test_native_engine_passes_env(tmp_path):
    if os.name == "nt":
        pytest.skip("Skip native tool engine environment variables test on Windows since WSL shell doesn't automatically inherit them")
    res = te.NativeToolEngine().run(
        image="unused", command="echo $SC_FOO > env.txt", cwd=str(tmp_path),
        env={"SC_FOO": "bar123"}, timeout=30,
    )
    assert res["success"]
    assert (tmp_path / "env.txt").read_text().strip() == "bar123"


def test_native_engine_timeout_kills(tmp_path):
    res = te.NativeToolEngine().run(
        image="unused", command="sleep 10", cwd=str(tmp_path), timeout=1
    )
    assert not res["success"] and res["timed_out"] is True


def test_native_engine_nonzero_exit(tmp_path):
    res = te.NativeToolEngine().run(image="u", command="exit 3", cwd=str(tmp_path), timeout=10)
    assert not res["success"] and res["timed_out"] is False
