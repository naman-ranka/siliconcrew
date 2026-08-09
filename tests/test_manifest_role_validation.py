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


def test_reading_never_rewrites_the_unknown_role_to_disk(tmp_path):
    """Reading must not be what destroys a newer writer's data.

    A rolling deploy runs both versions at once. If the old reader persists its
    coerced view, the FIRST read makes the loss permanent — long after the
    traffic split ends and the new version owns every instance.
    """
    ws = _seed(tmp_path)
    m.read_manifest(ws, session_id="s1")
    path = os.path.join(ws, m.MANIFEST_FILENAME)
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    raw["files"][0]["role"] = "quux"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f)

    for _ in range(2):
        reread = m.read_manifest(ws, session_id="s1")
        assert {f.path: f.role for f in reread.files}["counter.v"] == "rtl"  # in memory
        with open(path, "r", encoding="utf-8") as f:
            assert json.load(f)["files"][0]["role"] == "quux"  # untouched on disk


def test_non_list_files_field_does_not_explode(tmp_path):
    ws = _seed(tmp_path)
    m.read_manifest(ws, session_id="s1")
    path = os.path.join(ws, m.MANIFEST_FILENAME)
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    raw["files"] = 7
    raw["platform"] = "asap7"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f)

    reread = m.read_manifest(ws, session_id="s1")
    assert reread.platform == "asap7"          # the rest of the document survives
    assert {f.path for f in reread.files} == {"counter.v", "counter_tb.v", "vendor/ip.v"}


def test_numeric_string_clock_period_is_not_silently_reset(tmp_path):
    ws = _seed(tmp_path)
    m.read_manifest(ws, session_id="s1")
    path = os.path.join(ws, m.MANIFEST_FILENAME)
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    raw["clockPeriodNs"] = "3.5"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f)

    assert m.read_manifest(ws, session_id="s1").clockPeriodNs == 3.5

    raw["clockPeriodNs"] = "fast please"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f)
    assert m.read_manifest(ws, session_id="s1").clockPeriodNs == 10.0  # documented default


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


def test_unrelated_write_does_not_persist_a_coerced_role(tmp_path):
    """An edit to an unrelated field must not downgrade a newer writer's role.

    read_manifest correctly refuses to persist the coercion; write_manifest
    used to read (coercing), then persist unconditionally — so a clock-period
    edit from an old client permanently rewrote 'formal_v2' to 'rtl', putting
    (say) a formal harness back into the synthesis compile set.
    """
    ws = _seed(tmp_path)
    m.read_manifest(ws, session_id="s1")
    mpath = os.path.join(ws, m.MANIFEST_FILENAME)
    with open(mpath, "r", encoding="utf-8") as f:
        raw = json.load(f)
    target = next(e for e in raw["files"] if e["path"] == "vendor/ip.v")
    target["role"] = "formal_v2"  # a role only a newer version knows
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(raw, f)

    result = m.write_manifest(ws, {"clockPeriodNs": 4.0}, session_id="s1")
    assert result.clockPeriodNs == 4.0

    with open(mpath, "r", encoding="utf-8") as f:
        after = json.load(f)
    stored = next(e for e in after["files"] if e["path"] == "vendor/ip.v")
    assert stored["role"] == "formal_v2"
    assert after["clockPeriodNs"] == 4.0


def test_explicit_role_update_replaces_an_unknown_role(tmp_path):
    """A user editing THE FILE'S role through an old client is an explicit
    decision — that one write may replace the unknown value."""
    ws = _seed(tmp_path)
    m.read_manifest(ws, session_id="s1")
    mpath = os.path.join(ws, m.MANIFEST_FILENAME)
    with open(mpath, "r", encoding="utf-8") as f:
        raw = json.load(f)
    next(e for e in raw["files"] if e["path"] == "vendor/ip.v")["role"] = "formal_v2"
    with open(mpath, "w", encoding="utf-8") as f:
        json.dump(raw, f)

    m.write_manifest(ws, {"files": [{"path": "vendor/ip.v", "role": "other"}]}, session_id="s1")
    with open(mpath, "r", encoding="utf-8") as f:
        after = json.load(f)
    assert next(e for e in after["files"] if e["path"] == "vendor/ip.v")["role"] == "other"
