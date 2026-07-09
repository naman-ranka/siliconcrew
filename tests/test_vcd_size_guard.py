"""#3 — honest size cap before VCD parsing (plans/followups-backlog.md).

``_parse_vcd_file`` loads the whole dump via VCDVCD and serializes every
transition to JSON, so an oversized VCD (the "open any workspace VCD" feature
makes hundreds-of-MB dumps reachable) would stall the request thread and blow
up the response. A file over the cap must return a structured too-large signal
(mirroring workspace_fs.read_smart_file's text cap), never a parse.
"""
import pytest

pytest.importorskip("fastapi")

import api


def test_parse_vcd_over_cap_returns_too_large_signal(tmp_path, monkeypatch):
    vcd = tmp_path / "big.vcd"
    vcd.write_text("$timescale 1ns $end\n" + "x" * 500)
    monkeypatch.setattr(api, "VCD_PARSE_CAP", 100)

    out = api._parse_vcd_file(str(vcd), "big.vcd")
    assert out["tooLarge"] is True
    assert out["signals"] == [] and out["signalCount"] == 0
    assert out["size"] == vcd.stat().st_size


def test_parse_vcd_under_cap_parses(tmp_path):
    pytest.importorskip("vcdvcd")
    vcd = tmp_path / "dump.vcd"
    vcd.write_text(
        "$timescale 1ns $end\n"
        "$scope module tb $end\n"
        "$var wire 1 ! clk $end\n"
        "$upscope $end\n$enddefinitions $end\n"
        "#0\n0!\n#5\n1!\n#10\n0!\n"
    )
    out = api._parse_vcd_file(str(vcd), "dump.vcd")
    assert out["tooLarge"] is False
    assert any(s["name"] == "clk" for s in out["signals"])
