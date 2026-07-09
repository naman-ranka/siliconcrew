"""Run a cocotb testbench for the agent's self-verification (engine-routed).

Execution is delegated to ``get_tool_engine()``:
  * **docker** (local default): the digest-pinned CVDP reference container
    ``ghcr.io/hdl/sim/osvb`` — the SAME image the benchmark is graded in, so a
    self-PASS predicts the hidden-harness verdict. Named container + hard-kill on
    timeout (a non-terminating sim cannot leak a runaway container).
  * **native** (hosted / Cloud Run): the same cocotb runner runs as a subprocess
    directly in the per-session workspace using the host's ``iverilog`` + cocotb
    (both present in the app image) — no Docker. (Fidelity note: native uses the
    app image's cocotb/iverilog, not the osvb grader image; grading still runs in
    the osvb container.)

The runner script + ``SC_*`` env are identical across engines, and the script
adds the **cwd** to ``sys.path`` (so the test module imports under both the
container ``-w`` dir and the native ``cwd``). Sources are workspace-relative, so
the command is engine-agnostic. Non-termination → status="TIMEOUT" (treat as
FAIL), never an opaque hang.
"""
from __future__ import annotations

import base64
import json
import os
import re
import uuid

from src.platform_engines.tool_engine import get_tool_engine

# Pinned to the SAME digest the grader uses (cvdp-pipeline/regrade_docker.py) so self-check == grade env.
DEFAULT_OSVB_IMAGE = (
    "ghcr.io/hdl/sim/osvb@sha256:"
    "6fc999d943f1b8f8c49e7221459ae01e57afd33f7e73c3734b9a65be25e7f434"
)
# Keep the default just under codex's ~120s MCP tool-call timeout so we always return a clean
# structured result rather than letting the client time out. Raise both together for heavy suites.
DEFAULT_TIMEOUT = 110

# This runs in the tool cwd (the per-session workspace under either engine). It adds cwd to sys.path
# (so the cocotb test module imports), builds with iverilog + runs the test via the modern runner API
# (falling back to the legacy import), then parses the JUnit results.xml for pass/fail.
_RUNNER = r"""
import os, sys, json, glob
import xml.etree.ElementTree as ET
sys.path.insert(0, os.getcwd())   # import the agent's cocotb test module from the workspace
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
failures = []
for path in results[:1]:
    try:
        for tc in ET.parse(path).iter("testcase"):
            fail_node = tc.find("failure")
            err_node = tc.find("error")
            if fail_node is not None or err_node is not None:
                nfail += 1
                node = fail_node if fail_node is not None else err_node
                failures.append("Testcase %s FAILED: %s\n%s" % (tc.get("name"), node.get("message") or "", node.text or ""))
            else:
                npass += 1
    except Exception as e:
        print("SC_COCOTB_PARSE_EXC:", repr(e))
if failures:
    print("\n--- COCOTB FAILURE DETAILS ---")
    for f in failures:
        print(f)
        print("------------------------------")
print("SC_COCOTB_RESULT pass=%d fail=%d xml=%s" % (npass, nfail, "yes" if results else "no"))
sys.exit(0 if (npass > 0 and nfail == 0) else 1)
"""


def _to_rel(path: str, cwd: str) -> str:
    """Express a (possibly absolute) source path relative to the workspace cwd."""
    if os.path.isabs(path):
        try:
            return os.path.relpath(path, cwd).replace("\\", "/")
        except ValueError:
            return path.replace("\\", "/")
    return path.replace("\\", "/")


def run_cocotb(verilog_files, toplevel, python_module, cwd=None,
               timeout=DEFAULT_TIMEOUT, sim="icarus", image=DEFAULT_OSVB_IMAGE):
    """Run a cocotb testbench via the selected ToolEngine.

    Args:
        verilog_files (list[str]): DUT + dependency sources (abs or workspace-relative).
        toplevel (str): top-level HDL module name.
        python_module (str): cocotb test module importable from the workspace.
        cwd (str): the agent session workspace.
        timeout (int): hard wall-clock limit; on expiry the run is killed and status=TIMEOUT.
        sim (str): cocotb simulator name (default "icarus").
        image (str): reference container for the docker engine (digest-pinned).

    Returns:
        dict: {success, status: PASS|FAIL|TIMEOUT|ERROR, passed, failed, timed_out,
               stdout, stderr, command}
    """
    cwd = cwd or os.getcwd()

    # Validate sources exist in the workspace before running.
    missing = [f for f in verilog_files if not os.path.exists(f if os.path.isabs(f) else os.path.join(cwd, f))]
    if missing:
        return _err(f"Source file(s) not found: {', '.join(missing)}")

    sources = [_to_rel(f, cwd) for f in verilog_files]
    uid = uuid.uuid4().hex[:8]
    runner_path = f"/tmp/sc_cocotb_runner_{uid}.py"
    b64 = base64.b64encode(_RUNNER.encode()).decode()
    # Same command under both engines: materialize the runner, then run it in cwd.
    command = f"echo {b64} | base64 -d > {runner_path} && python3 {runner_path}"
    env = {
        "SC_SOURCES": json.dumps(sources),
        "SC_TOPLEVEL": toplevel,
        "SC_TEST_MODULE": python_module,
        "SC_BUILD_DIR": f"/tmp/sc_build_{uid}",   # unique → no cross-run collision (native)
        "SC_SIM": sim,
    }

    res = get_tool_engine().run(
        image=image, command=command, cwd=cwd, env=env, timeout=timeout, name_prefix="sc_cocotb"
    )

    stdout = res.get("stdout", "") or ""
    stderr = res.get("stderr", "") or ""
    timed_out = bool(res.get("timed_out"))
    npass, nfail = _parse_counts(stdout)

    if timed_out:
        status = "TIMEOUT"                      # non-terminating: the agent must treat as FAIL
    elif "build=fail" in stdout:
        status = "ERROR"                        # compile/elaboration failure — no test ran
    elif npass > 0 and nfail == 0 and res.get("success"):
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
        "command": res.get("command", command),
    }


def _parse_counts(stdout: str) -> tuple[int, int]:
    m = re.search(r"SC_COCOTB_RESULT pass=(\d+) fail=(\d+)", stdout or "")
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _err(msg: str, command: str = "") -> dict:
    return {"success": False, "status": "ERROR", "passed": 0, "failed": 0, "timed_out": False,
            "stdout": "", "stderr": msg, "command": command}
