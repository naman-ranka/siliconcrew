import json
import shutil
import subprocess

import pytest

from src.tools.run_xls import XLS_IMAGE
from src.tools.wrappers import run_xls_flow, simulation_tool


def _docker_image_available(image: str) -> bool:
    if not shutil.which("docker"):
        return False
    proc = subprocess.run(
        ["docker", "image", "inspect", image],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    return proc.returncode == 0


@pytest.fixture
def isolated_workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setenv("RTL_WORKSPACE", str(workspace))
    return workspace


@pytest.fixture
def require_xls_and_iverilog():
    if not _docker_image_available(XLS_IMAGE):
        pytest.skip(f"Docker image {XLS_IMAGE!r} is not available. Build it with Dockerfile.xls.")
    if not shutil.which("iverilog"):
        pytest.skip("iverilog is not available; XLS generated-Verilog simulation skipped.")


def test_xls_generated_verilog_runs_in_siliconcrew_simulation(
    isolated_workspace,
    require_xls_and_iverilog,
):
    (isolated_workspace / "sat_add.x").write_text(
        """
fn sat_add(x: u8, y: u8) -> u8 {
    let sum: bits[9] = (x as bits[9]) + (y as bits[9]);
    if sum > bits[9]:255 { u8:255 } else { sum as u8 }
}

#[test]
fn test_sat_add() {
    assert_eq(sat_add(u8:1, u8:2), u8:3);
    assert_eq(sat_add(u8:255, u8:1), u8:255);
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    flow = json.loads(
        run_xls_flow.invoke(
            {
                "dslx_file": "sat_add.x",
                "top_module": "sat_add",
                "generator": "combinational",
                "module_name": "sat_add_core",
                "keep_intermediates": True,
                "run_lint": True,
            }
        )
    )
    assert flow["success"] is True, flow.get("stderr")
    assert flow["generated_module"] == "sat_add_core"

    (isolated_workspace / "sat_add_tb.v").write_text(
        """
module sat_add_tb;
    reg [7:0] x;
    reg [7:0] y;
    wire [7:0] out;
    integer errors;

    sat_add_core dut (
        .x(x),
        .y(y),
        .out(out)
    );

    task check;
        input [7:0] a;
        input [7:0] b;
        input [7:0] expected;
        begin
            x = a;
            y = b;
            #1;
            if (out !== expected) begin
                $display("FAIL x=%0d y=%0d got=%0d expected=%0d", a, b, out, expected);
                errors = errors + 1;
            end
        end
    endtask

    initial begin
        $dumpfile("sat_add.vcd");
        $dumpvars(0, sat_add_tb);
        errors = 0;

        check(8'd1, 8'd2, 8'd3);
        check(8'd100, 8'd50, 8'd150);
        check(8'd200, 8'd100, 8'd255);
        check(8'd255, 8'd1, 8'd255);

        if (errors == 0) begin
            $display("TEST PASSED");
        end else begin
            $display("TEST FAILED: %0d errors", errors);
        end
        $finish;
    end
endmodule
""".strip()
        + "\n",
        encoding="utf-8",
    )

    sim = json.loads(
        simulation_tool.invoke(
            {
                "verilog_files": ["sat_add.v", "sat_add_tb.v"],
                "top_module": "sat_add_tb",
                "mode": "rtl",
                "pass_marker": "TEST PASSED",
            }
        )
    )
    assert sim["success"] is True, sim
    assert sim["status"] == "test_passed", sim
    assert sim["pass_marker_found"] is True, sim
