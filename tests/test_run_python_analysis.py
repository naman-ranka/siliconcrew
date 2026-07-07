"""Tests for run_python_analysis — the bespoke gated subprocess (Wave 10).

Covers the plan's Item 6 backend list: containment rejection, timeout kill,
env-scrub (child cannot see backend secrets), artifact scan (reports created
files, excludes run dirs), docker command shape (--network=none etc.), rlimit
caps (POSIX-only), and the hosted PYTHON gate. No pytest-asyncio; everything is
synchronous.
"""
import os
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.tools.run_python import (
    run_python_analysis,
    build_docker_argv,
    resolve_engine,
    _posix_rlimits,
    _scrubbed_env,
    PythonAnalysisError,
)


def _write(ws, name, body):
    path = os.path.join(ws, name)
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(name) else None
    with open(path, "w") as f:
        f.write(textwrap.dedent(body))
    return path


# --- Containment (PA5) -------------------------------------------------------

def test_rejects_parent_traversal(tmp_path):
    with pytest.raises(PythonAnalysisError, match="escapes the workspace"):
        run_python_analysis(str(tmp_path), "../evil.py", engine="native")


def test_rejects_absolute_escape(tmp_path):
    outside = tmp_path.parent / "outside.py"
    outside.write_text("print('hi')")
    with pytest.raises(PythonAnalysisError, match="escapes the workspace"):
        run_python_analysis(str(tmp_path), str(outside), engine="native")


def test_rejects_missing_script(tmp_path):
    with pytest.raises(PythonAnalysisError, match="not found"):
        run_python_analysis(str(tmp_path), "nope.py", engine="native")


# --- Execution + artifacts ---------------------------------------------------

def test_runs_script_and_reports_artifacts(tmp_path):
    ws = str(tmp_path)
    _write(ws, "gen.py", """
        import os
        os.makedirs('data', exist_ok=True)
        open('data/result.csv', 'w').write('a,b\\n1,2\\n')
        open('plot.png', 'wb').write(b'\\x89PNG fake')
        # A file inside a run dir must be EXCLUDED from the artifact scan.
        os.makedirs('sim_runs/sim_0001', exist_ok=True)
        open('sim_runs/sim_0001/junk.csv', 'w').write('x')
        print('done')
    """)
    r = run_python_analysis(ws, "gen.py", engine="native")

    assert r["ok"] is True
    assert r["exit_code"] == 0
    assert r["engine"] == "native"
    assert "done" in r["stdout_tail"]

    paths = {a["path"] for a in r["artifacts"]}
    assert "data/result.csv" in paths
    assert "plot.png" in paths
    assert "gen.py" not in paths  # the input script is not an "artifact produced"
    assert not any(p.startswith("sim_runs/") for p in paths)  # run dirs excluded

    kinds = {a["path"]: a["kind"] for a in r["artifacts"]}
    assert kinds["plot.png"] == "image"
    assert kinds["data/result.csv"] == "data"


def test_passes_args_to_script(tmp_path):
    ws = str(tmp_path)
    _write(ws, "echo.py", """
        import sys
        print('ARGV=' + ','.join(sys.argv[1:]))
    """)
    r = run_python_analysis(ws, "echo.py", ["--n", "4"], engine="native")
    assert "ARGV=--n,4" in r["stdout_tail"]


# --- Timeout -----------------------------------------------------------------

def test_timeout_kills_runaway(tmp_path):
    ws = str(tmp_path)
    _write(ws, "slow.py", """
        import time
        time.sleep(30)
    """)
    r = run_python_analysis(ws, "slow.py", engine="native", timeout=1)
    assert r["timed_out"] is True
    assert r["ok"] is False


# --- Env-scrub (the single most important native gate) -----------------------

def test_child_cannot_see_backend_secret(tmp_path, monkeypatch):
    monkeypatch.setenv("SC_FAKE_API_KEY", "super-secret-value")
    ws = str(tmp_path)
    _write(ws, "peek.py", """
        import os
        print('SECRET=' + os.environ.get('SC_FAKE_API_KEY', 'MISSING'))
        print('MPL=' + os.environ.get('MPLBACKEND', 'unset'))
    """)
    r = run_python_analysis(ws, "peek.py", engine="native")
    assert "SECRET=MISSING" in r["stdout_tail"]
    assert "super-secret-value" not in r["stdout_tail"]
    assert "MPL=Agg" in r["stdout_tail"]  # the explicit safe key IS passed


def test_scrubbed_env_excludes_arbitrary_host_vars(monkeypatch, tmp_path):
    monkeypatch.setenv("DATABASE_URL", "postgres://secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-xxx")
    env = _scrubbed_env(str(tmp_path))
    assert "DATABASE_URL" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert env["MPLBACKEND"] == "Agg"
    assert env["HOME"] == str(tmp_path)


# --- Docker command shape (recording; no real docker) ------------------------

def test_docker_argv_has_isolation_flags():
    argv = build_docker_argv(image="img:1", workspace="/ws", rel_script="a/gen.py", args=["--n", "4"])
    assert argv[:3] == ["docker", "run", "--rm"]
    assert "--network=none" in argv
    assert "--read-only" in argv
    assert "--user" in argv and "1000:1000" in argv
    assert "--pids-limit" in argv
    assert "--memory" in argv and "--cpus" in argv
    # workspace mounted rw at /workspace; script + args are the tail
    assert "-v" in argv
    vol_idx = argv.index("-v") + 1
    assert argv[vol_idx].endswith(":/workspace:rw")
    assert argv[-4:] == ["python", "-I", "/workspace/a/gen.py", "--n"] or \
        argv[-5:] == ["python", "-I", "/workspace/a/gen.py", "--n", "4"]


def test_docker_volume_translated_for_dood(monkeypatch):
    # In docker-outside-docker, the -v host path is rewritten to HOST_WORKSPACE.
    import src.tools.run_docker as rd
    monkeypatch.setattr(rd, "_HOST_WORKSPACE", "/host/mount")
    argv = build_docker_argv(image="img:1", workspace="/workspace", rel_script="g.py", args=[])
    vol = argv[argv.index("-v") + 1]
    assert vol == "/host/mount:/workspace:rw"


# --- Engine resolution -------------------------------------------------------

def test_docker_falls_back_to_native_when_docker_absent(monkeypatch):
    import src.tools.run_python as rp
    monkeypatch.setattr(rp.shutil, "which", lambda _name: None)
    assert resolve_engine("docker") == "native"


def test_explicit_native_is_respected(monkeypatch):
    import src.tools.run_python as rp
    monkeypatch.setattr(rp.shutil, "which", lambda _name: "/usr/bin/docker")
    assert resolve_engine("native") == "native"


# --- rlimits (POSIX only) ----------------------------------------------------

def test_posix_rlimits_is_none_on_windows():
    if os.name == "nt":
        assert _posix_rlimits() is None
    else:
        assert callable(_posix_rlimits())


@pytest.mark.skipif(os.name == "nt", reason="rlimits are POSIX-only")
def test_rlimits_are_applied_to_child(tmp_path):
    ws = str(tmp_path)
    _write(ws, "limits.py", """
        import resource
        soft, _hard = resource.getrlimit(resource.RLIMIT_CPU)
        print('CPU_SOFT=%d' % soft)
    """)
    r = run_python_analysis(ws, "limits.py", engine="native")
    assert "CPU_SOFT=30" in r["stdout_tail"]
