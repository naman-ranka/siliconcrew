import json
import os
import shutil
import subprocess

import pytest

from src.tools.run_xls import (
    XLS_IMAGE,
    validate_delay_model,
    validate_generator,
    validate_identifier,
    validate_nonnegative_int,
    validate_safe_relative_path,
)
from src.tools.wrappers import (
    experimental_compile_cpp_to_ir,
    get_workspace_path,
    run_xls_flow,
)


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
def require_xls_image():
    if not _docker_image_available(XLS_IMAGE):
        pytest.skip(f"Docker image {XLS_IMAGE!r} is not available. Build it with Dockerfile.xls.")


@pytest.fixture
def require_iverilog():
    if not shutil.which("iverilog"):
        pytest.skip("iverilog is not available; generated-Verilog lint test skipped.")


def test_validate_safe_relative_path():
    assert validate_safe_relative_path("saturating_add.x") == "saturating_add.x"
    assert validate_safe_relative_path("kernels/saturating_add.x") == "kernels/saturating_add.x"
    assert validate_safe_relative_path("kernels/sub-dir/design_1.x") == "kernels/sub-dir/design_1.x"

    for bad in [
        "../secret.x",
        "kernels/../secret.x",
        "/secret.x",
        "C:/secret.x",
        "C:\\secret.x",
        "foo.x;rm",
        "foo.x&&bar",
        "foo.x|bar",
        "foo.x`bar`",
        "foo.x$bar",
        "foo.x(bar)",
        "foo.x<bar",
        "foo x.x",
        "./foo.x",
        "kernels//foo.x",
    ]:
        with pytest.raises(ValueError):
            validate_safe_relative_path(bad)


def test_validate_xls_options():
    assert validate_identifier("my_add", "top_module") == "my_add"
    assert validate_identifier("_core0", "module_name") == "_core0"
    assert validate_generator("combinational") == "combinational"
    assert validate_generator("pipeline") == "pipeline"
    assert validate_nonnegative_int("3", "pipeline_stages") == 3
    assert validate_delay_model("sky130") == "sky130"
    assert validate_delay_model("") == ""

    for bad in ["foo/bar", "1bad", "bad-name", "bad name", "bad;name"]:
        with pytest.raises(ValueError):
            validate_identifier(bad, "top_module")

    with pytest.raises(ValueError):
        validate_generator("combinational;echo")
    with pytest.raises(ValueError):
        validate_nonnegative_int("-1", "pipeline_stages")
    with pytest.raises(ValueError):
        validate_delay_model("sky130;echo")


def test_path_safety_rejection_in_tool(isolated_workspace):
    flow_res_str = run_xls_flow.invoke({"dslx_file": "../secret.x", "top_module": "my_add"})
    flow_res = json.loads(flow_res_str)
    assert flow_res["success"] is False
    assert flow_res["stage"] == "interpreter"
    assert "Path traversal" in flow_res["stderr"]


def test_experimental_compile_cpp_to_ir_rejects_unsafe_path(isolated_workspace):
    res_str = experimental_compile_cpp_to_ir.invoke({"filename": "../secret.cc", "top_name": "my_func"})
    res = json.loads(res_str)
    assert res["success"] is False
    assert "Path traversal" in res["stderr"]


def test_get_workspace_path_respects_isolated_workspace(isolated_workspace):
    assert get_workspace_path() == os.path.abspath(str(isolated_workspace))


@pytest.mark.requires_eda
def test_run_xls_flow_combinational_lints_generated_verilog(
    isolated_workspace,
    require_xls_image,
    require_iverilog,
):
    dslx_file = isolated_workspace / "sat_add.x"
    dslx_file.write_text(
        """
fn sat_add(x: u8, y: u8) -> u8 {
    let sum: bits[9] = (x as bits[9]) + (y as bits[9]);
    if sum > bits[9]:255 { u8:255 } else { sum as u8 }
}

#[test]
fn test_sat_add() {
    assert_eq(sat_add(u8:100, u8:50), u8:150);
    assert_eq(sat_add(u8:200, u8:100), u8:255);
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    flow_res_str = run_xls_flow.invoke(
        {
            "dslx_file": "sat_add.x",
            "top_module": "sat_add",
            "generator": "combinational",
            "module_name": "sat_add_core",
            "keep_intermediates": True,
            "run_lint": True,
        }
    )
    flow_res = json.loads(flow_res_str)

    assert flow_res["success"] is True, flow_res.get("stderr")
    assert flow_res["stage"] == "completed"
    assert flow_res["verilog_filename"] == "sat_add.v"
    assert flow_res["generated_module"] == "sat_add_core"
    assert flow_res["artifacts"]["ir_file"] == "sat_add.ir"
    assert flow_res["artifacts"]["opt_ir_file"] == "sat_add.opt.ir"
    assert flow_res["stage_results"]["verilog_lint"]["success"] is True

    generated = isolated_workspace / "sat_add.v"
    assert generated.exists()
    content = generated.read_text(encoding="utf-8")
    assert "module sat_add_core" in content
    assert "input wire [7:0] x" in content
    assert "output wire [7:0] out" in content


@pytest.mark.requires_eda
def test_run_xls_flow_can_drop_intermediates(
    isolated_workspace,
    require_xls_image,
):
    dslx_file = isolated_workspace / "add16.x"
    dslx_file.write_text(
        """
fn add16(x: u16, y: u16) -> u16 {
    x + y
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    flow_res = json.loads(
        run_xls_flow.invoke(
            {
                "dslx_file": "add16.x",
                "top_module": "add16",
                "module_name": "add16_core",
                "keep_intermediates": False,
                "run_lint": False,
            }
        )
    )

    assert flow_res["success"] is True, flow_res.get("stderr")
    assert flow_res["artifacts"]["ir_file"] is None
    assert flow_res["artifacts"]["opt_ir_file"] is None
    assert not (isolated_workspace / "add16.ir").exists()
    assert not (isolated_workspace / "add16.opt.ir").exists()
    assert (isolated_workspace / "add16.v").exists()
