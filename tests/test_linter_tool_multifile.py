import os
import tempfile

from src.tools.wrappers import linter_tool


def test_linter_tool_supports_multi_file_workspace_inputs():
    with tempfile.TemporaryDirectory() as workspace:
        old = os.environ.get("RTL_WORKSPACE")
        os.environ["RTL_WORKSPACE"] = workspace
        try:
            dut = os.path.join(workspace, "dut.v")
            tb = os.path.join(workspace, "tb.v")
            with open(dut, "w", encoding="utf-8") as f:
                f.write("module dut(input a, output y); assign y=a; endmodule")
            with open(tb, "w", encoding="utf-8") as f:
                f.write("module tb; reg a; wire y; dut u(.a(a), .y(y)); initial begin a=0; #1; $finish; end endmodule")

            # Using single-file mode for dut still passes
            assert "Syntax OK" in linter_tool.invoke({"verilog_files": "dut.v"})

            # Multi-file mode should also pass (tb references dut)
            result = linter_tool.invoke({"verilog_files": ["dut.v", "tb.v"]})
            assert "Syntax OK" in result
        finally:
            if old is None:
                os.environ.pop("RTL_WORKSPACE", None)
            else:
                os.environ["RTL_WORKSPACE"] = old
