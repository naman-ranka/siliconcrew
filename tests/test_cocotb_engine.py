"""cocotb routes through the ToolEngine; native smoke gated like ORFS (slice 4)."""
import json
import os
import shutil

import pytest

import src.platform_engines.tool_engine as te
from src.tools.run_cocotb import run_cocotb


class FakeEngine:
    mode = "native"

    def __init__(self, stdout="SC_COCOTB_RESULT pass=1 fail=0 xml=yes", success=True, timed_out=False):
        self.stdout, self.success, self.timed_out = stdout, success, timed_out
        self.calls = []

    def run(self, *, image, command, cwd, env=None, timeout, workdir="/workspace", name_prefix="sc_tool", base_env=None):
        self.calls.append({"image": image, "command": command, "cwd": cwd, "env": env,
                           "timeout": timeout, "name_prefix": name_prefix, "base_env": base_env})
        return {"success": self.success, "stdout": self.stdout, "stderr": "", "command": command, "timed_out": self.timed_out}


@pytest.fixture(autouse=True)
def _clear():
    yield
    te.set_tool_engine(None)


def _ws(tmp_path):
    (tmp_path / "dut.v").write_text("module dut(input a, output b); assign b=a; endmodule")
    (tmp_path / "test_dut.py").write_text("# cocotb test placeholder\n")
    return str(tmp_path)


def test_routes_with_relative_sources_and_env(tmp_path):
    eng = FakeEngine()
    te.set_tool_engine(eng)
    res = run_cocotb(["dut.v"], "dut", "test_dut", cwd=_ws(tmp_path), timeout=55)
    call = eng.calls[-1]
    # Command materializes + runs the cocotb runner (engine-agnostic).
    assert "base64 -d" in call["command"] and "python3" in call["command"]
    assert "/workspace" not in call["command"]
    assert call["cwd"] == str(tmp_path) and call["name_prefix"] == "sc_cocotb" and call["timeout"] == 55
    # Sources are workspace-relative (no /workspace, no abs path) in the env.
    assert json.loads(call["env"]["SC_SOURCES"]) == ["dut.v"]
    assert call["env"]["SC_TOPLEVEL"] == "dut" and call["env"]["SC_TEST_MODULE"] == "test_dut"
    assert call["env"]["SC_BUILD_DIR"].startswith("/tmp/sc_build_")  # unique per run
    assert res["status"] == "PASS" and res["passed"] == 1


def test_absolute_sources_made_relative(tmp_path):
    eng = FakeEngine()
    te.set_tool_engine(eng)
    abs_src = os.path.join(str(tmp_path), "dut.v")
    run_cocotb([abs_src], "dut", "test_dut", cwd=_ws(tmp_path))
    assert json.loads(eng.calls[-1]["env"]["SC_SOURCES"]) == ["dut.v"]


def test_build_fail_is_error(tmp_path):
    te.set_tool_engine(FakeEngine(stdout="SC_COCOTB_RESULT pass=0 fail=0 build=fail", success=False))
    res = run_cocotb(["dut.v"], "dut", "test_dut", cwd=_ws(tmp_path))
    assert res["status"] == "ERROR"


def test_timeout(tmp_path):
    te.set_tool_engine(FakeEngine(stdout="", success=False, timed_out=True))
    res = run_cocotb(["dut.v"], "dut", "test_dut", cwd=_ws(tmp_path))
    assert res["status"] == "TIMEOUT" and res["timed_out"]


def test_missing_source(tmp_path):
    te.set_tool_engine(FakeEngine())
    res = run_cocotb(["nope.v"], "dut", "test_dut", cwd=str(tmp_path))
    assert res["status"] == "ERROR" and "not found" in res["stderr"]


# --- native end-to-end smoke (CI-friendly, gated like the ORFS real run) -----

def _cocotb_native_available() -> bool:
    if os.name == "nt":
        return False
    if not shutil.which("iverilog"):
        return False
    try:
        import cocotb  # noqa: F401
        try:
            from cocotb_tools.runner import get_runner  # noqa: F401
        except Exception:
            from cocotb.runner import get_runner  # noqa: F401
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _cocotb_native_available(),
                    reason="native cocotb smoke needs iverilog + cocotb (like the ORFS real-run gate)")
def test_native_cocotb_end_to_end(tmp_path):  # pragma: no cover - runs only where the toolchain exists
    from src.platform_engines.tool_engine import NativeToolEngine

    te.set_tool_engine(NativeToolEngine())
    (tmp_path / "dff.v").write_text(
        "module dff(input clk, input d, output reg q);\n"
        "  always @(posedge clk) q <= d;\nendmodule\n"
    )
    (tmp_path / "test_dff.py").write_text(
        "import cocotb\n"
        "from cocotb.triggers import Timer\n"
        "@cocotb.test()\n"
        "async def t(dut):\n"
        "    dut.d.value = 1\n"
        "    dut.clk.value = 0\n"
        "    await Timer(1, units='ns')\n"
        "    dut.clk.value = 1\n"
        "    await Timer(1, units='ns')\n"
        "    assert dut.q.value == 1\n"
    )
    res = run_cocotb(["dff.v"], "dff", "test_dff", cwd=str(tmp_path), timeout=120)
    assert res["status"] == "PASS", res
