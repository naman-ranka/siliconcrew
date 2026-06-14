"""Run a cocotb testbench for the agent's self-verification.

Design (see SiliconCrew tool conventions):
  * Runs in the **digest-pinned CVDP reference container** `ghcr.io/hdl/sim/osvb` — the SAME image the
    benchmark is graded in — so the agent's self-check actually predicts the hidden-harness verdict.
    (Running cocotb on the host used a different cocotb/iverilog than the grader, which produced
    self-PASS/grader-FAIL divergence. Fidelity to the grader is the whole point.)
  * Mirrors the Docker pattern of `run_sby`/`run_synthesis` (workspace mounted, command in-container),
    but adds a **named container + guaranteed kill on timeout** so a non-terminating simulation cannot
    leak a runaway container.
  * **Synchronous** by design: the MCP server already offloads every tool to a thread executor
    (`run_in_executor`), so blocking here does NOT stall the event loop. What matters is a *hard
    internal timeout* that returns a structured result BEFORE the MCP client (codex, ~120s) gives up.
  * **Non-termination is reported as a result, not a hang**: a timeout returns status="TIMEOUT" so the
    agent can treat it as a FAILURE (comb loop / missing clock / unbounded test) instead of an opaque
    MCP error.

Build artifacts go to a container-local /tmp dir, so the mounted agent workspace is not polluted.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import uuid

try:
    from src.tools.run_docker import _translate_dood_path
except Exception:
    from tools.run_docker import _translate_dood_path

# Pinned to the SAME digest the grader uses (cvdp-pipeline/regrade_docker.py) so self-check == grade env.
DEFAULT_OSVB_IMAGE = (
    "ghcr.io/hdl/sim/osvb@sha256:"
    "6fc999d943f1b8f8c49e7221459ae01e57afd33f7e73c3734b9a65be25e7f434"
)
# Keep the default just under codex's ~120s MCP tool-call timeout so we always return a clean
# structured result rather than letting the client time out. Raise both together for heavy suites.
DEFAULT_TIMEOUT = 110

# In DooD mode (MCP server itself in a container) the bind-mount source must be a host path.
_HOST_WORKSPACE = os.environ.get("HOST_WORKSPACE")

# This runs INSIDE the osvb container. It builds with iverilog + runs the cocotb test via the modern
# runner API (falling back to the legacy import), then parses the JUnit results.xml for pass/fail.
_IN_CONTAINER_RUNNER = r"""
import os, sys, json, glob
import xml.etree.ElementTree as ET
try:
    from cocotb_tools.runner import get_runner
except Exception:
    from cocotb.runner import get_runner

sources    = json.loads(os.environ["SC_SOURCES"])
toplevel   = os.environ["SC_TOPLEVEL"]
test_mod   = os.environ["SC_TEST_MODULE"]
build_dir  = os.environ.get("SC_BUILD_DIR", "/tmp/sc_build")
sim        = os.environ.get("SC_SIM", "icarus")

runner = get_runner(sim)
_bk = dict(verilog_sources=sources, hdl_toplevel=toplevel, build_dir=build_dir, always=True)
try:
    # Default a 1ns/1ps timescale so Clock(...ns) self-tests work even when the agent's TB
    # doesn't set one (real CVDP harnesses set it via .env). Older runners lack the kwarg.
    try:
        runner.build(timescale=("1ns", "1ps"), **_bk)
    except TypeError:
        runner.build(**_bk)
except BaseException as e:
    print("SC_COCOTB_BUILD_EXC:", repr(e))
    print("SC_COCOTB_RESULT pass=0 fail=0 build=fail")
    sys.exit(2)

try:
    runner.test(hdl_toplevel=toplevel, test_module=test_mod, build_dir=build_dir)
except SystemExit:
    pass
except BaseException as e:
    print("SC_COCOTB_TEST_EXC:", repr(e))

results = sorted(glob.glob(os.path.join(build_dir, "**", "results.xml"), recursive=True))
npass = nfail = 0
for path in results[:1]:
    try:
        for tc in ET.parse(path).iter("testcase"):
            if tc.find("failure") is not None or tc.find("error") is not None:
                nfail += 1
            else:
                npass += 1
    except Exception as e:
        print("SC_COCOTB_PARSE_EXC:", repr(e))
print("SC_COCOTB_RESULT pass=%d fail=%d xml=%s" % (npass, nfail, "yes" if results else "no"))
sys.exit(0 if (npass > 0 and nfail == 0) else 1)
"""


def _to_rel(path: str, cwd: str) -> str:
    """Express a (possibly absolute) source path relative to the workspace mount."""
    if os.path.isabs(path):
        try:
            return os.path.relpath(path, cwd).replace("\\", "/")
        except ValueError:
            return path.replace("\\", "/")
    return path.replace("\\", "/")


def run_cocotb(verilog_files, toplevel, python_module, cwd=None,
               timeout=DEFAULT_TIMEOUT, sim="icarus", image=DEFAULT_OSVB_IMAGE):
    """Run a cocotb testbench in the reference container.

    Args:
        verilog_files (list[str]): DUT + dependency sources (abs or workspace-relative).
        toplevel (str): top-level HDL module name.
        python_module (str): cocotb test module, importable from the workspace
            (e.g. "test_dut" or "verif.test_dut").
        cwd (str): the agent session workspace (mounted at /work).
        timeout (int): hard wall-clock limit; on expiry the container is killed and status=TIMEOUT.
        sim (str): cocotb simulator name (default "icarus").
        image (str): reference container (digest-pinned by default).

    Returns:
        dict: {success, status: PASS|FAIL|TIMEOUT|ERROR, passed, failed, timed_out,
               stdout, stderr, command}
    """
    cwd = cwd or os.getcwd()

    if not shutil_which("docker"):
        return _err("Docker not found in PATH. The cocotb self-check runs in the "
                    f"{image} reference container and needs Docker available.", cwd)

    # Validate sources exist on the host before mounting.
    missing = [f for f in verilog_files if not os.path.exists(f if os.path.isabs(f) else os.path.join(cwd, f))]
    if missing:
        return _err(f"Source file(s) not found: {', '.join(missing)}", cwd)

    sources = [_to_rel(f, cwd) for f in verilog_files]
    mount_src = cwd
    if _HOST_WORKSPACE:  # DooD: translate container path -> host path for the sibling daemon
        mount_src = _translate_dood_path(cwd)

    name = f"sc_cocotb_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    b64 = base64.b64encode(_IN_CONTAINER_RUNNER.encode()).decode()
    inner = f"echo {b64} | base64 -d > /tmp/sc_runner.py && python3 /tmp/sc_runner.py"

    docker_cmd = [
        "docker", "run", "--rm", "--name", name,
        "-v", f"{mount_src}:/work", "-w", "/work",
        "-e", f"SC_SOURCES={json.dumps(sources)}",
        "-e", f"SC_TOPLEVEL={toplevel}",
        "-e", f"SC_TEST_MODULE={python_module}",
        "-e", "SC_BUILD_DIR=/tmp/sc_build",
        "-e", f"SC_SIM={sim}",
        "-e", "PYTHONPATH=/work",
        image,
        "bash", "-c", inner,
    ]

    proc = None
    timed_out = False
    try:
        proc = subprocess.Popen(docker_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = proc.communicate(timeout=timeout)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        timed_out = True
        # Hard-kill the container by name (killing the docker CLI alone may orphan it).
        subprocess.run(["docker", "kill", name], capture_output=True, text=True)
        try:
            proc.kill()
            stdout, stderr = proc.communicate(timeout=10)
        except Exception:
            stdout, stderr = "", ""
        rc = -1
    except Exception as e:
        return _err(f"Docker execution error: {e}", cwd, command=" ".join(docker_cmd))
    finally:
        if proc and proc.poll() is None:
            proc.kill()

    npass, nfail = _parse_counts(stdout)
    if timed_out:
        status = "TIMEOUT"                      # non-terminating: the agent must treat as FAIL
    elif "build=fail" in stdout:
        status = "ERROR"                        # compile/elaboration failure — no test ran
    elif npass > 0 and nfail == 0 and rc == 0:
        status = "PASS"
    elif (npass + nfail) > 0:
        status = "FAIL"                         # test ran and at least one case failed
    else:
        status = "ERROR"                        # no results produced (collection error, etc.)

    return {
        "success": status == "PASS",
        "status": status,
        "passed": npass,
        "failed": nfail,
        "timed_out": timed_out,
        "stdout": stdout,
        "stderr": stderr,
        "command": " ".join(docker_cmd),
    }


def _parse_counts(stdout: str) -> tuple[int, int]:
    m = re.search(r"SC_COCOTB_RESULT pass=(\d+) fail=(\d+)", stdout or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _err(msg: str, cwd: str, command: str = "") -> dict:
    return {"success": False, "status": "ERROR", "passed": 0, "failed": 0, "timed_out": False,
            "stdout": "", "stderr": msg, "command": command}


def shutil_which(name: str):
    import shutil
    return shutil.which(name)
