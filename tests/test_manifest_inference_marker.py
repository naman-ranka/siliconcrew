"""sc#81 (remaining half): the persisted inference marker.

"Inferred: none found" must be distinguishable from "not yet inferred".
Before the fix, any workspace whose simTop was LEGITIMATELY empty (no file
looks like a testbench) re-ran ``_infer_tops`` on every ``read_manifest`` —
i.e. on every GET /files, /code, every write_file and every dispatch. The fix
persists the scan-fingerprint digest at inference time
(``topsInferredFingerprint``) and re-infers only when the design file set has
actually changed since inference last ran.
"""
import os

import src.tools.manifest as mf


RTL = """
module alu(input [3:0] a, input [3:0] b, output [3:0] y);
  assign y = a + b;
endmodule
"""

RTL2 = """
module alu(input [3:0] a, input [3:0] b, output [3:0] y);
  assign y = a - b;  // changed body
endmodule
"""

TB = """
module alu_tb;
  reg [3:0] a, b; wire [3:0] y;
  alu dut(.a(a), .b(b), .y(y));
endmodule
"""


def _w(ws, name, content):
    with open(os.path.join(ws, name), "w", encoding="utf-8") as f:
        f.write(content)


def _spy_infer(monkeypatch):
    calls = {"n": 0}
    real = mf._infer_tops

    def spy(files, scans):
        calls["n"] += 1
        return real(files, scans)

    monkeypatch.setattr(mf, "_infer_tops", spy)
    return calls


def test_no_reinference_when_sim_top_legitimately_empty(tmp_path, monkeypatch):
    ws = str(tmp_path)
    _w(ws, "alu.v", RTL)  # rtl only — no testbench, so simTop stays ""
    calls = _spy_infer(monkeypatch)

    m1 = mf.read_manifest(ws, "s")
    assert m1.synthTop == "alu"
    assert m1.simTop == ""          # legitimately empty: nothing looks like a tb
    assert calls["n"] == 1
    assert m1.topsInferredFingerprint  # marker persisted with the manifest

    # Second read, nothing changed: inference must NOT re-run.
    m2 = mf.read_manifest(ws, "s")
    assert m2.simTop == ""
    assert calls["n"] == 1

    # Third read, still nothing changed.
    mf.read_manifest(ws, "s")
    assert calls["n"] == 1


def test_reinference_when_a_file_is_added(tmp_path, monkeypatch):
    ws = str(tmp_path)
    _w(ws, "alu.v", RTL)
    calls = _spy_infer(monkeypatch)

    m1 = mf.read_manifest(ws, "s")
    assert calls["n"] == 1
    assert m1.simTop == ""

    # A new testbench changes the design file set -> inference re-runs and
    # the empty simTop is finally fillable.
    _w(ws, "alu_tb.v", TB)
    m2 = mf.read_manifest(ws, "s")
    assert calls["n"] == 2
    assert m2.simTop == "alu_tb"

    # Both tops set now: no further inference regardless of the marker.
    mf.read_manifest(ws, "s")
    assert calls["n"] == 2


def test_reinference_when_a_file_changes(tmp_path, monkeypatch):
    ws = str(tmp_path)
    _w(ws, "alu.v", RTL)
    calls = _spy_infer(monkeypatch)

    mf.read_manifest(ws, "s")
    mf.read_manifest(ws, "s")
    assert calls["n"] == 1

    _w(ws, "alu.v", RTL2)  # content change (size differs, ctime bumps)
    mf.read_manifest(ws, "s")
    assert calls["n"] == 2


def test_marker_survives_reload_from_disk(tmp_path, monkeypatch):
    """The marker must round-trip through manifest.json — a marker that only
    lives in process memory would re-infer once per read again after any
    restart (the scan cache is per-process; the manifest is the record)."""
    ws = str(tmp_path)
    _w(ws, "alu.v", RTL)
    mf.read_manifest(ws, "s")

    # Simulate a fresh process: drop the in-memory scan cache entirely.
    mf._SCAN_CACHE.clear()
    calls = _spy_infer(monkeypatch)
    m = mf.read_manifest(ws, "s")
    assert calls["n"] == 0
    assert m.topsInferredFingerprint


def test_missing_marker_costs_exactly_one_reinference(tmp_path, monkeypatch):
    """An older writer (or a hand edit) dropping the field is not an error:
    the next read re-infers once and restores it."""
    ws = str(tmp_path)
    _w(ws, "alu.v", RTL)
    mf.read_manifest(ws, "s")

    import json
    path = os.path.join(ws, mf.MANIFEST_FILENAME)
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    raw.pop("topsInferredFingerprint", None)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f)

    calls = _spy_infer(monkeypatch)
    mf.read_manifest(ws, "s")
    assert calls["n"] == 1
    mf.read_manifest(ws, "s")
    assert calls["n"] == 1
