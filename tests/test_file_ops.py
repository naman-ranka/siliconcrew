"""The single shared write path used by both the REST save action and the
agent's write_file tool."""
import os

import pytest

from src.tools import file_ops
from src.tools import manifest as mf


def test_writes_workspace_relative_file(tmp_path):
    ws = str(tmp_path)
    out = file_ops.write_file(ws, "alu.v", "module alu(input a); endmodule\n")
    assert out["path"] == "alu.v"
    assert out["bytes"] > 0
    assert os.path.exists(os.path.join(ws, "alu.v"))


def test_write_reconciles_manifest_roles(tmp_path):
    ws = str(tmp_path)
    file_ops.write_file(ws, "counter.v", "module counter(input clk, output reg q); endmodule\n")
    m = mf.read_manifest(ws)
    roles = {f.name: f.role for f in m.files}
    assert roles.get("counter.v") == "rtl"


def test_rejects_path_traversal(tmp_path):
    ws = str(tmp_path / "ws")
    os.makedirs(ws, exist_ok=True)
    with pytest.raises(ValueError):
        file_ops.write_file(ws, "../evil.v", "x")
    assert not os.path.exists(os.path.join(str(tmp_path), "evil.v"))
