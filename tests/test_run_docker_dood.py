"""Docker-outside-Docker workspace path resolution (src/tools/run_docker.py).

Sibling containers are started by the host daemon, so their -v source must be
a host path. docker-compose used to pass HOST_WORKSPACE=./workspace verbatim;
the daemon cannot mount a relative path, the ORFS container saw an empty dir,
and synthesis died with `PLATFORM variable not set`. These pin the fix: a
relative or missing value inside a container is resolved from the daemon.
"""
import json
import subprocess

import pytest

import src.tools.run_docker as rd

WIN_SRC = "C:\\Users\\dev\\siliconcrew\\workspace"


def _mounts_json(source=WIN_SRC):
    return json.dumps([
        {"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock"},
        {"Type": "bind", "Source": source, "Destination": "/workspace"},
    ])


@pytest.fixture
def dood(monkeypatch):
    """Configure HOST_WORKSPACE, the /.dockerenv marker and `docker inspect`."""
    calls = []

    def setup(host_workspace=None, in_container=True, inspect_stdout=None, inspect_rc=0):
        monkeypatch.setattr(rd, "_HOST_WORKSPACE", host_workspace)
        monkeypatch.setattr(rd, "_discovered_host_workspace", None)
        real_exists = rd.os.path.exists
        monkeypatch.setattr(
            rd.os.path, "exists",
            lambda p: in_container if p == "/.dockerenv" else real_exists(p),
        )

        def fake_run(argv, **kwargs):
            calls.append(argv)
            return subprocess.CompletedProcess(argv, inspect_rc, inspect_stdout or "", "")

        monkeypatch.setattr(rd.subprocess, "run", fake_run)
        return calls

    return setup


def test_absolute_host_workspace_is_used_as_given(dood):
    calls = dood(host_workspace="/srv/sc/workspace")
    assert rd._translate_dood_path("/workspace/s1/run") == "/srv/sc/workspace/s1/run"
    assert calls == []  # no daemon round-trip when the value is already usable


def test_windows_absolute_host_workspace_is_absolute(dood):
    calls = dood(host_workspace="C:/Users/dev/sc/workspace")
    assert rd._translate_dood_path("/workspace/s1") == "C:/Users/dev/sc/workspace\\s1"
    assert calls == []


def test_relative_host_workspace_is_resolved_from_docker_inspect(dood):
    calls = dood(host_workspace="./workspace", inspect_stdout=_mounts_json())
    assert rd._translate_dood_path("/workspace/s1/synth_runs") == WIN_SRC + "\\s1\\synth_runs"
    assert calls and calls[0][:2] == ["docker", "inspect"]


def test_unset_inside_container_is_resolved_from_docker_inspect(dood):
    dood(host_workspace=None, inspect_stdout=_mounts_json("/home/dev/sc/workspace"))
    assert rd._translate_dood_volume("/workspace/s1:/workspace:rw") == "/home/dev/sc/workspace/s1:/workspace:rw"


def test_native_self_host_is_untouched(dood):
    calls = dood(host_workspace=None, in_container=False)
    assert rd._translate_dood_path("/home/dev/sc/workspace/s1") == "/home/dev/sc/workspace/s1"
    assert calls == []  # never shells out to docker on a plain host


def test_discovery_is_cached(dood):
    calls = dood(host_workspace="./workspace", inspect_stdout=_mounts_json())
    rd._translate_dood_path("/workspace/a")
    rd._translate_dood_path("/workspace/b")
    assert len(calls) == 1


def test_relative_value_without_discovery_fails_loudly_before_docker_run(dood, monkeypatch):
    dood(host_workspace="./workspace", inspect_rc=1)
    popen_called = []
    monkeypatch.setattr(rd.subprocess, "Popen", lambda *a, **k: popen_called.append(a))
    # run_docker_command creates workspace_path first; keep that off the real disk.
    monkeypatch.setattr(rd.os, "makedirs", lambda *a, **k: None)

    result = rd.run_docker_command("true", workspace_path="/workspace/s1")

    assert result["success"] is False
    assert "HOST_WORKSPACE='./workspace' is relative" in result["stderr"]
    assert popen_called == []


def test_python_analysis_surfaces_the_same_error(dood):
    from src.tools.run_python import PythonAnalysisError, build_docker_argv

    dood(host_workspace="./workspace", inspect_rc=1)
    with pytest.raises(PythonAnalysisError, match="is relative"):
        build_docker_argv(image="img:1", workspace="/workspace", rel_script="g.py",
                          args=[], container_name="sc_py_x")


def test_unset_inside_container_without_discovery_fails_loudly(dood):
    # compose now passes HOST_WORKSPACE empty; a custom `hostname:` breaks
    # `docker inspect <hostname>`. Passing /workspace through would mount an
    # empty host dir, so this must be an error, not a silent fallback.
    dood(host_workspace=None, inspect_rc=1)
    with pytest.raises(rd.DoodWorkspaceError, match="HOST_WORKSPACE is not set"):
        rd._translate_dood_path("/workspace/s1")


def test_paths_outside_workspace_need_no_host_path(dood):
    calls = dood(host_workspace=None, inspect_rc=1)
    assert rd._translate_dood_path("/opt/pdk/sky130") == "/opt/pdk/sky130"
    assert calls == []


def test_failed_discovery_is_retried(dood, monkeypatch):
    # One transient failure (daemon still starting) must not stick for the
    # life of the process.
    dood(host_workspace=None, inspect_rc=1)
    with pytest.raises(rd.DoodWorkspaceError):
        rd._translate_dood_path("/workspace/s1")
    monkeypatch.setattr(
        rd.subprocess, "run",
        lambda argv, **k: subprocess.CompletedProcess(argv, 0, _mounts_json("/srv/ws"), ""),
    )
    assert rd._translate_dood_path("/workspace/s1") == "/srv/ws/s1"


def test_relative_value_on_a_native_host_is_ignored(dood):
    # .env.example suggests HOST_WORKSPACE=./workspace for compose, and
    # `python api.py` loads the same .env. Natively that must be a no-op,
    # not a docker inspect round-trip and a DooD error.
    calls = dood(host_workspace="./workspace", in_container=False)
    assert rd._translate_dood_path("/workspace/s1") == "/workspace/s1"
    assert calls == []
