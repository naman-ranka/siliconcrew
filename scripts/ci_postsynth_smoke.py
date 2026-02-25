#!/usr/bin/env python
import json
import os
import tempfile

from src.tools.run_simulation import run_simulation
from src.tools.stdcells import bootstrap_stdcells


def _write(path: str, text: str) -> None:
    with open(path, "w", encoding="ascii") as f:
        f.write(text)


def _run_case(workspace: str, platform: str, netlist_text: str, tb_text: str) -> dict:
    netlist = os.path.join(workspace, f"{platform}_netlist.v")
    tb = os.path.join(workspace, f"{platform}_tb.v")
    _write(netlist, netlist_text)
    _write(tb, tb_text)

    return run_simulation(
        verilog_files=[tb],
        top_module=f"tb_{platform}",
        cwd=workspace,
        mode="post_synth",
        netlist_file=netlist,
        platform=platform,
        pass_marker="TEST PASSED",
    )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ci_postsynth_") as workspace:
        bootstrap_stdcells(workspace=workspace, platform="asap7")
        bootstrap_stdcells(workspace=workspace, platform="sky130hd")

        asap7 = _run_case(
            workspace=workspace,
            platform="asap7",
            netlist_text=(
                "module top(input a, output y);\n"
                "  INVx1_ASAP7_75t_R u0 (.A(a), .Y(y));\n"
                "endmodule\n"
            ),
            tb_text=(
                "`timescale 1ns/1ps\n"
                "module tb_asap7;\n"
                "  reg a;\n"
                "  wire y;\n"
                "  top dut(.a(a), .y(y));\n"
                "  initial begin\n"
                "    a = 0; #1;\n"
                "    a = 1; #1;\n"
                '    $display("TEST PASSED");\n'
                "    $finish;\n"
                "  end\n"
                "endmodule\n"
            ),
        )

        sky130 = _run_case(
            workspace=workspace,
            platform="sky130hd",
            netlist_text=(
                "module top(input a, output y);\n"
                "  sky130_fd_sc_hd__inv_1 u0 (.A(a), .Y(y));\n"
                "endmodule\n"
            ),
            tb_text=(
                "`timescale 1ns/1ps\n"
                "module tb_sky130hd;\n"
                "  reg a;\n"
                "  wire y;\n"
                "  top dut(.a(a), .y(y));\n"
                "  initial begin\n"
                "    a = 0; #1;\n"
                "    a = 1; #1;\n"
                '    $display("TEST PASSED");\n'
                "    $finish;\n"
                "  end\n"
                "endmodule\n"
            ),
        )

        print(json.dumps({"asap7": asap7["status"], "sky130hd": sky130["status"]}, indent=2))
        if asap7.get("status") != "test_passed":
            print(json.dumps(asap7, indent=2))
            return 1
        if sky130.get("status") != "test_passed":
            print(json.dumps(sky130, indent=2))
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
