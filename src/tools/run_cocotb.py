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

coverage   = os.environ.get("SC_COVERAGE") == "1"
# Taken out of the environment before the test runs, so the test (which
# shares stdout) cannot learn it and print a report that passes for ours.
run_tag    = os.environ.pop("SC_RUN_TAG", "")

runner = get_runner(sim)
_bk = dict(verilog_sources=sources, hdl_toplevel=toplevel, build_dir=build_dir, always=True)
if coverage:
    # Verilator line + toggle coverage; lint warnings stay warnings so a design
    # that simulates is not refused over style.
    # --timing: RTL with delays (q <= #1 d) builds as it simulates under Icarus,
    # instead of failing NEEDTIMINGOPT and turning a PASS into a build ERROR.
    _bk["build_args"] = ["--coverage-line", "--coverage-toggle", "--timing", "-Wno-fatal"]
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

if coverage:
    # coverage.dat: one point per line, C '<\x01key\x02value ...>' <count>, with
    # f=file, l=line, o=signal, page=v_line/.. | v_toggle/.. | v_branch/..
    # Only points in the design's own sources count.
    dats = sorted(glob.glob(os.path.join(build_dir, "**", "coverage.dat"), recursive=True))

    def _rel(p):
        # Workspace-relative, so rtl/alu.v and sub/alu.v stay two files.
        p = os.path.relpath(p, os.getcwd()) if os.path.isabs(p) else p
        return os.path.normpath(p).replace("\\", "/")

    wanted = set(_rel(s) for s in sources)
    kinds, lines_missed, branches_missed, toggles_missed = {}, set(), [], []
    for dat in dats[:1]:
        with open(dat, errors="replace") as fh:
            for raw in fh:
                if not raw.startswith("C '"):
                    continue
                body, _, count = raw.rstrip("\n").rpartition("' ")
                fields = dict(kv.split("\x02", 1) for kv in body[3:].split("\x01") if "\x02" in kv)
                fname = _rel(fields.get("f", ""))
                if fname not in wanted:
                    continue
                kind = fields.get("page", "").split("/")[0].replace("v_", "") or "other"
                hit = count.strip().isdigit() and int(count) > 0
                tally = kinds.setdefault(kind, [0, 0])
                tally[0] += 1 if hit else 0
                tally[1] += 1
                if hit:
                    continue
                where = "%s:%s" % (fname, fields.get("l", "?"))
                if kind == "line":
                    lines_missed.add((fname, int(fields.get("l", "0") or 0)))
                elif kind == "branch":
                    # A branch point sits on the `if` line, which may well have
                    # run; name the arm that did not, e.g. ram.v:4 (else).
                    branches_missed.append("%s (%s)" % (where, fields.get("o", "?")))
                elif kind == "toggle":
                    toggles_missed.append("%s (%s)" % (fields.get("o", "?"), where))
    summary = {k: {"covered": c, "total": t, "pct": round(100.0 * c / t, 1) if t else None}
               for k, (c, t) in sorted(kinds.items())}
    # Tagged per run: the test module shares this stdout and must not be able
    # to print a report that is taken for this one.
    print("SC_COCOTB_COVERAGE_%s %s" % (run_tag, json.dumps({
        "measured": bool(dats),
        "summary": summary,
        "uncoveredLines": ["%s:%d" % fl for fl in sorted(lines_missed)][:40],
        "uncoveredBranches": branches_missed[:40],
        # Ports and control signals before memory bits (mem[3][5]), which
        # would otherwise fill the list.
        "uncoveredToggles": sorted(toggles_missed, key=lambda t: t.split(" ")[0].count("["))[:40],
    })))
sys.exit(0 if (npass > 0 and nfail == 0) else 1)
"""


# Toolchain-essential env kept for the NATIVE cocotb subprocess. Everything else
# (API keys, DB URLs, WorkOS/GCP creds in the backend process env) is dropped so
# the agent's cocotb Python can't read a backend secret — parity with the docker
# path (which already starts from a clean image env) and with run_python_analysis.
_COCOTB_ENV_KEEP = (
    "PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "USER", "LOGNAME", "TMPDIR",
    "TERM", "SHELL",
    # Windows self-host: the interpreter/toolchain need these to start.
    "SYSTEMROOT", "SystemRoot", "WINDIR", "PATHEXT", "TEMP", "TMP", "COMSPEC",
)


def _scrubbed_base_env(cwd: str) -> dict:
    """A minimal explicit base env for the native cocotb subprocess (no backend
    secrets). The ``SC_*`` runner vars are layered on top by the engine's ``env``."""
    env = {k: os.environ[k] for k in _COCOTB_ENV_KEEP if k in os.environ}
    env.setdefault("HOME", cwd)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _to_rel(path: str, cwd: str) -> str:
    """Express a (possibly absolute) source path relative to the workspace cwd."""
    if os.path.isabs(path):
        try:
            return os.path.relpath(path, cwd).replace("\\", "/")
        except ValueError:
            return path.replace("\\", "/")
    return path.replace("\\", "/")


def run_cocotb(verilog_files, toplevel, python_module, cwd=None,
               timeout=DEFAULT_TIMEOUT, sim="icarus", image=DEFAULT_OSVB_IMAGE, coverage=False):
    """Run a cocotb testbench via the selected ToolEngine.

    Args:
        verilog_files (list[str]): DUT + dependency sources (abs or workspace-relative).
        toplevel (str): top-level HDL module name.
        python_module (str): cocotb test module importable from the workspace.
        cwd (str): the agent session workspace.
        timeout (int): hard wall-clock limit; on expiry the run is killed and status=TIMEOUT.
        sim (str): cocotb simulator name (default "icarus").
        image (str): reference container for the docker engine (digest-pinned).
        coverage (bool): measure line + toggle code coverage. Runs under Verilator
            in the coverage image (settings.cocotb_coverage_image) instead of the
            grader image; the result gains a ``coverage`` dict.

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
    if coverage:
        from src.platform_engines.settings import get_settings
        sim, image = "verilator", get_settings().cocotb_coverage_image
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
        "SC_COVERAGE": "1" if coverage else "0",
        "SC_RUN_TAG": uid,
    }

    engine = get_tool_engine()
    if coverage and not _is_docker_engine(engine):
        # The native engine runs whatever verilator/cocotb is on PATH, which is
        # not the pinned pair the coverage image exists to guarantee. Numbers
        # from an unknown toolchain, reported as measured, are worse than none.
        return _err("Coverage needs the docker engine and the pinned coverage image; this server "
                    "runs the native engine (SIM_ENGINE=native), where the toolchain on PATH is "
                    "not the measured one. Run without coverage=True, or use the docker engine.",
                    command)
    if coverage and not _local_image_exists(image):
        # A locally built tag must never be pulled: whatever a registry has
        # under that name would run with the workspace mounted.
        return _err(f"Coverage image '{image}' is not built on this server. Build it with: "
                    f"docker build -t {image} - < Dockerfile.cocotb-coverage", command)

    res = engine.run(
        image=image, command=command, cwd=cwd, env=env, timeout=timeout, name_prefix="sc_cocotb",
        # Native path only: scrub the backend process env so the agent's cocotb
        # Python can't read secrets (docker already isolates). See PA1 / Item 3.
        base_env=_scrubbed_base_env(cwd),
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

    if coverage and status == "ERROR" and _IMAGE_MISSING.search(stderr + stdout):
        return _err(f"Coverage image '{image}' is not built on this server. Build it with: "
                    f"docker build -t {image} - < Dockerfile.cocotb-coverage", res.get("command", command))

    out = {
        "success": status == "PASS",
        "status": status,
        "passed": npass,
        "failed": nfail,
        "timed_out": timed_out,
        "stdout": stdout,
        "stderr": stderr,
        "command": res.get("command", command),
    }
    if coverage:
        out["coverage"] = _parse_coverage(stdout, uid)
    return out


def _is_docker_engine(engine) -> bool:
    # The engines declare their own mode (tool_engine.py); a class-name check
    # would miss a subclass or a test double.
    return getattr(engine, "mode", "") == "docker"


def _local_image_exists(image: str) -> bool:
    import subprocess
    try:
        return subprocess.run(["docker", "image", "inspect", image], capture_output=True,
                              stdin=subprocess.DEVNULL, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


# docker's wording for a local tag that was never built.
_IMAGE_MISSING = re.compile(r"Unable to find image|pull access denied|repository does not exist", re.I)


def _parse_coverage(stdout: str, tag: str):
    """This run's coverage report (tagged, last one wins), or {"measured": False}."""
    found = re.findall(r"^SC_COCOTB_COVERAGE_%s (\{.*\})$" % re.escape(tag), stdout or "", re.M)
    if not found:
        return {"measured": False}
    try:
        return json.loads(found[-1])
    except ValueError:
        return {"measured": False}


def _parse_counts(stdout: str) -> tuple[int, int]:
    # The runner prints its result after the test's own output, so the last
    # marker is the real one; an earlier copy can only come from the test.
    found = re.findall(r"SC_COCOTB_RESULT pass=(\d+) fail=(\d+)", stdout or "")
    return (int(found[-1][0]), int(found[-1][1])) if found else (0, 0)


def _err(msg: str, command: str = "") -> dict:
    return {"success": False, "status": "ERROR", "passed": 0, "failed": 0, "timed_out": False,
            "stdout": "", "stderr": msg, "command": command}
