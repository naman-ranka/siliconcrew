"""read_waveform: hierarchical signal resolution (no EDA binaries needed)."""
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.read_waveform import read_waveform

# TB { clk (code "), DUT { clk (code !), sig (code #) } }
# Two signals named "clk" in different scopes -> bare "clk" is ambiguous.
NESTED_VCD = """$timescale 1ns $end
$scope module TB $end
$var wire 1 " clk $end
$scope module DUT $end
$var wire 1 ! clk $end
$var wire 8 # sig [7:0] $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
0"
0!
b00000000 #
#5
1"
1!
b00000001 #
#10
0"
0!
"""


def _vcd(tmp_path, content=NESTED_VCD):
    p = tmp_path / "dump.vcd"
    p.write_text(content)
    return str(p)


def test_hierarchical_path_resolves(tmp_path):
    out = read_waveform(_vcd(tmp_path), ["TB.DUT.sig"], 0, 20)
    assert not out.startswith("Error"), out
    assert "TB.DUT.sig" in out
    assert "00000001" in out


def test_hierarchical_path_picks_the_right_scope(tmp_path):
    """TB.clk and TB.DUT.clk are distinct signals; each must resolve on its own."""
    out = read_waveform(_vcd(tmp_path), ["TB.DUT.clk"], 0, 20)
    assert not out.startswith("Error"), out
    assert "TB.DUT.clk" in out
    assert "TB.clk\t" not in out


def test_unique_bare_name_still_resolves(tmp_path):
    """Backward compatibility: bare leaf names keep working when unambiguous."""
    out = read_waveform(_vcd(tmp_path), ["sig"], 0, 20)
    assert not out.startswith("Error"), out
    assert "TB.DUT.sig" in out


def test_ambiguous_bare_name_is_reported_not_guessed(tmp_path):
    out = read_waveform(_vcd(tmp_path), ["clk"], 0, 20)
    assert out.startswith("Error"), out
    assert "Ambiguous" in out
    assert "TB.clk" in out and "TB.DUT.clk" in out


def test_unknown_signal_lists_full_paths(tmp_path):
    out = read_waveform(_vcd(tmp_path), ["nope"], 0, 20)
    assert out.startswith("Error"), out
    assert "TB.DUT.sig" in out and "TB.clk" in out


def test_partial_miss_reports_the_missing_name(tmp_path):
    out = read_waveform(_vcd(tmp_path), ["TB.DUT.sig", "nope"], 0, 20)
    assert "nope" in out
    assert "TB.DUT.sig" in out


def test_time_window_is_respected(tmp_path):
    out = read_waveform(_vcd(tmp_path), ["TB.DUT.sig"], 5, 5)
    assert "00000001" in out
    assert "00000000" not in out


def test_missing_file_is_an_error(tmp_path):
    out = read_waveform(str(tmp_path / "absent.vcd"), ["clk"], 0, 10)
    assert out.startswith("Error") and "does not exist" in out
