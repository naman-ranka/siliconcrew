"""XLS routes through the ToolEngine with cwd-relative paths (slice 2)."""
import pytest

import src.platform_engines.tool_engine as te
from src.tools.run_xls import compile_dslx_to_ir, run_dslx_interpreter


class RecordingEngine:
    mode = "native"

    def __init__(self):
        self.calls = []

    def run(self, *, image, command, cwd, env=None, timeout, workdir="/workspace", name_prefix="sc_tool"):
        self.calls.append({"image": image, "command": command, "cwd": cwd, "timeout": timeout})
        return {"success": True, "stdout": "", "stderr": "", "command": command, "timed_out": False}


@pytest.fixture
def engine():
    rec = RecordingEngine()
    te.set_tool_engine(rec)
    yield rec
    te.set_tool_engine(None)


def test_interpreter_routes_with_relative_path(engine, tmp_path):
    (tmp_path / "design.x").write_text("fn main() -> u8 { u8:0 }")
    run_dslx_interpreter("design.x", cwd=str(tmp_path))
    call = engine.calls[-1]
    # Native engine resolves the DSLX stdlib at /opt/xls (docker uses /xls).
    assert call["command"] == "interpreter_main --dslx_path=/opt/xls design.x"
    assert "/workspace" not in call["command"]          # cwd-relative, not container path
    assert call["cwd"] == str(tmp_path)                  # native runs in the real workspace
    assert call["image"] == "siliconcrew-xls:latest"


def test_compile_routes_with_relative_redirect(engine, tmp_path):
    (tmp_path / "design.x").write_text("fn foo() -> u8 { u8:0 }")
    compile_dslx_to_ir("design.x", "foo", cwd=str(tmp_path))
    call = engine.calls[-1]
    assert call["command"] == "ir_converter_main --dslx_path=/opt/xls --top=foo design.x > foo.ir"
    assert "/workspace" not in call["command"]


def test_validation_still_rejects_unsafe_paths(engine, tmp_path):
    # The tool keeps its own validation; the engine is never reached for bad input.
    res = run_dslx_interpreter("../escape.x", cwd=str(tmp_path))
    assert not res["success"] and "traversal" in res["stderr"].lower()
    assert engine.calls == []
