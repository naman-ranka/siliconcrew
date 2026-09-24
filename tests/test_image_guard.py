"""Locally built images: say what to build, never pull, never blame the image
for a stopped daemon.

siliconcrew-sby and siliconcrew/cocotb-coverage are built on the machine, not
published. Without a check, a stranger's first sby_tool call answers "pull
access denied" (and a namespaced tag would run whatever a registry serves,
with the workspace mounted). A daemon that is merely stopped is a different
failure, and the engine already reports it.
"""
import subprocess

import pytest

import src.platform_engines.tool_engine as te
import src.tools.run_sby as rs


def _fake_inspect(returncode, stderr="", exc=None):
    def run(argv, **kw):
        if exc:
            raise exc
        return subprocess.CompletedProcess(argv, returncode, "", stderr)
    return run


@pytest.mark.parametrize("rc,stderr,expected", [
    (0, "", True),
    (1, "Error: No such image: siliconcrew-sby:latest", False),
    (1, "Cannot connect to the Docker daemon at unix:///var/run/docker.sock", None),
    (1, "failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine", None),
])
def test_local_image_exists_is_tri_state(monkeypatch, rc, stderr, expected):
    monkeypatch.setattr(te.subprocess, "run", _fake_inspect(rc, stderr))
    assert te.local_image_exists("siliconcrew-sby:latest") is expected


def test_no_docker_cli_is_unknown_not_missing(monkeypatch):
    monkeypatch.setattr(te.subprocess, "run", _fake_inspect(0, exc=FileNotFoundError("docker")))
    assert te.local_image_exists("x:1") is None


def _sby_workspace(tmp_path):
    (tmp_path / "dut.v").write_text("module dut(input clk); endmodule\n")
    (tmp_path / "p.sby").write_text(
        "[options]\nmode bmc\ndepth 4\n\n[engines]\nsmtbmc z3\n\n[script]\nread -formal dut.v\n"
        "prep -top dut\n\n[files]\ndut.v\n")
    return str(tmp_path / "p.sby"), str(tmp_path)


class _DockerEngine:
    mode = "docker"

    def __init__(self):
        self.ran = []

    def run(self, **kw):
        self.ran.append(kw)
        return {"success": True, "stdout": "DONE (PASS, rc=0)", "stderr": "", "command": kw["command"]}


def test_unbuilt_formal_image_says_how_to_build_it(monkeypatch, tmp_path):
    engine = _DockerEngine()
    monkeypatch.setattr(rs, "get_tool_engine", lambda: engine)
    monkeypatch.setattr(rs, "local_image_exists", lambda image: False)
    sby, ws = _sby_workspace(tmp_path)
    out = rs.run_sby(sby, cwd=ws)
    assert engine.ran == []
    assert out["status"] == "ERROR"
    assert "Dockerfile.sby" in out["stderr"] and "docker build -t siliconcrew-sby:latest" in out["stderr"]


def test_a_stopped_daemon_is_left_to_the_engine(monkeypatch, tmp_path):
    engine = _DockerEngine()
    monkeypatch.setattr(rs, "get_tool_engine", lambda: engine)
    monkeypatch.setattr(rs, "local_image_exists", lambda image: None)
    sby, ws = _sby_workspace(tmp_path)
    rs.run_sby(sby, cwd=ws)
    assert len(engine.ran) == 1, "unknown image state must not block the run"


def test_native_engine_needs_no_image(monkeypatch, tmp_path):
    class Native(_DockerEngine):
        mode = "native"

    engine = Native()
    monkeypatch.setattr(rs, "get_tool_engine", lambda: engine)
    monkeypatch.setattr(rs, "local_image_exists", lambda image: False)
    sby, ws = _sby_workspace(tmp_path)
    rs.run_sby(sby, cwd=ws)
    assert len(engine.ran) == 1
