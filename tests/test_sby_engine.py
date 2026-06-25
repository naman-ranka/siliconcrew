"""SBY routes through the ToolEngine with a cwd-relative command (slice 3)."""
import pytest

import src.platform_engines.tool_engine as te
from src.tools.run_sby import run_sby


class FakeEngine:
    mode = "native"

    def __init__(self, stdout="", success=True, timed_out=False):
        self.stdout, self.success, self.timed_out = stdout, success, timed_out
        self.calls = []

    def run(self, *, image, command, cwd, env=None, timeout, workdir="/workspace", name_prefix="sc_tool"):
        self.calls.append({"image": image, "command": command, "cwd": cwd, "timeout": timeout, "name_prefix": name_prefix})
        return {"success": self.success, "stdout": self.stdout, "stderr": "", "command": command, "timed_out": self.timed_out}


@pytest.fixture(autouse=True)
def _clear():
    yield
    te.set_tool_engine(None)


def _sby(tmp_path):
    f = tmp_path / "proof.sby"
    f.write_text("[options]\nmode prove\n")
    return str(f)


def test_routes_with_relative_command(tmp_path):
    eng = FakeEngine(stdout="DONE (PASS, ...)")
    te.set_tool_engine(eng)
    res = run_sby(_sby(tmp_path), cwd=str(tmp_path), timeout=42)
    call = eng.calls[-1]
    assert call["command"] == "sby -f proof.sby"      # cwd-relative basename, no /workspace
    assert "/workspace" not in call["command"]
    assert call["cwd"] == str(tmp_path)               # runs in the .sby's own dir
    assert call["timeout"] == 42 and call["name_prefix"] == "sc_sby"
    assert res["status"] == "PASS" and res["success"]


def test_parses_fail(tmp_path):
    te.set_tool_engine(FakeEngine(stdout="DONE (FAIL, ...)", success=False))
    res = run_sby(_sby(tmp_path))
    assert res["status"] == "FAIL" and not res["success"]


def test_timeout_maps_to_timeout_status(tmp_path):
    te.set_tool_engine(FakeEngine(stdout="", success=False, timed_out=True))
    res = run_sby(_sby(tmp_path))
    assert res["status"] == "TIMEOUT" and res["timed_out"] is True


def test_missing_file(tmp_path):
    te.set_tool_engine(FakeEngine())
    res = run_sby(str(tmp_path / "nope.sby"))
    assert res["status"] == "ERROR" and "not found" in res["stderr"]


def test_docker_path_unchanged_via_run_docker_command(tmp_path, monkeypatch):
    """With the docker engine, sby goes through run_docker_command (mockable)."""
    monkeypatch.setenv("SIM_ENGINE", "docker")
    from src.platform_engines.settings import reset_settings_cache

    reset_settings_cache()
    te.set_tool_engine(None)
    monkeypatch.setattr("shutil.which", lambda _x: "/usr/bin/docker")
    seen = {}

    def fake_rdc(**kw):
        seen.update(kw)
        return {"success": True, "stdout": "DONE (PASS, x)", "stderr": "", "command": "docker ...", "timed_out": False}

    monkeypatch.setattr("src.tools.run_docker.run_docker_command", fake_rdc)
    res = run_sby(_sby(tmp_path), timeout=99)
    assert res["status"] == "PASS"
    assert seen["workspace_path"] == str(tmp_path) and seen["cwd"] == "/workspace"
    assert seen["name"] and seen["timeout"] == 99      # named container, hard-kill on timeout
    reset_settings_cache()
