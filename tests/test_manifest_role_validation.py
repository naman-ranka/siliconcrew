"""Role validation on write + per-field tolerance on read (D0).

Before this fix an unknown role could be persisted by ``update_manifest`` (pydantic
v2 does not validate on assignment) and the NEXT read discarded the whole document
— wiping synthTop, platform, clockPeriodNs, ``ignore`` and every role override.
"""
import json
import os

import pytest

from src.tools import manifest as m


DUT = """
module counter (input clk, output reg [7:0] count);
    always @(posedge clk) count <= count + 1;
endmodule
"""

TB = """
module counter_tb;
    reg clk; wire [7:0] count;
    counter dut(.clk(clk), .count(count));
    initial begin #10 $finish; end
endmodule
"""


def _write(ws, name, text):
    path = os.path.join(ws, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _seed(tmp_path):
    ws = str(tmp_path)
    _write(ws, "counter.v", DUT)
    _write(ws, "counter_tb.v", TB)
    _write(ws, "vendor/ip.v", "module ip(input a, output b); assign b = a; endmodule\n")
    return ws


def test_stored_unknown_role_coerces_without_wiping_the_document(tmp_path):
    """A manifest carrying an unrecognized role keeps every user field."""
    ws = _seed(tmp_path)
    m.read_manifest(ws, session_id="s1")
    m.write_manifest(ws, {
        "synthTop": "counter",
        "simTop": "counter_tb",
        "platform": "asap7",
        "clockPeriodNs": 3.5,
        "ignore": ["vendor/**"],
    })

    # Simulate an old/foreign writer (or a future role this reader doesn't know).
    path = os.path.join(ws, m.MANIFEST_FILENAME)
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    raw["files"][0]["role"] = "quux"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f)

    reread = m.read_manifest(ws, session_id="s1")

    assert reread.synthTop == "counter"
    assert reread.simTop == "counter_tb"
    assert reread.platform == "asap7"
    assert reread.clockPeriodNs == 3.5
    assert reread.ignore == ["vendor/**"]
    # The unknown role is the ONLY thing lost — coerced to the safe default.
    roles = {f.path: f.role for f in reread.files}
    assert roles["counter.v"] == "rtl"
    # The ignore glob still excludes the vendor file (proof reconcile ran on the
    # stored document, not on a rebuilt one).
    assert "vendor/ip.v" not in roles


def test_write_manifest_rejects_unknown_role_and_persists_nothing(tmp_path):
    ws = _seed(tmp_path)
    m.read_manifest(ws, session_id="s1")
    m.write_manifest(ws, {"platform": "asap7", "ignore": ["vendor/**"]})

    before = open(os.path.join(ws, m.MANIFEST_FILENAME), "r", encoding="utf-8").read()

    with pytest.raises(ValueError) as exc:
        m.write_manifest(ws, {
            "platform": "sky130hd",
            "files": [{"path": "counter.v", "role": "rtll"}],
        })
    assert "rtll" in str(exc.value)

    after = open(os.path.join(ws, m.MANIFEST_FILENAME), "r", encoding="utf-8").read()
    assert after == before  # nothing persisted, not even the valid platform edit


def test_update_manifest_tool_reports_the_bad_role(tmp_path, monkeypatch):
    """The wrapper (agent/MCP/REST all land here) returns an error reply."""
    ws = _seed(tmp_path)
    from src.tools import wrappers

    monkeypatch.setattr(wrappers, "get_workspace_path", lambda: ws)
    monkeypatch.setattr(wrappers, "current_session_id", lambda: "s1")

    out = wrappers.update_manifest.func(json.dumps({"files": [{"path": "counter.v", "role": "RTL"}]}))
    assert out.startswith("Error:")
    assert "RTL" in out
    roles = {f.path: f.role for f in m.read_manifest(ws, session_id="s1").files}
    assert roles["counter.v"] == "rtl"
