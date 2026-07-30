"""VCD reading: honest time windows and honest signal resolution.

dev#71 (A5b): the default ``end_time=1000`` silently dropped everything a
longer sim produced. Removing that bound needs a row cap with a footer that
says what was left out, plus a loop guard that understands "no end".
"""
import os

from src.tools.read_waveform import read_waveform


HEADER = """$date
    Nov 27 2025
$end
$timescale
    1ns
$end
$scope module tb $end
$var wire 1 ! clk $end
$var wire 1 " rst $end
$var wire 8 # count [7:0] $end
$upscope $end
$enddefinitions
$end
"""


def _write_vcd(path, body, header=HEADER):
    with open(path, "w", encoding="utf-8") as f:
        f.write(header + body)
    return path


def _long_vcd(tmp_path, name="dump.vcd", last_time=5000, step=500):
    """A sim that runs well past the old t=1000 default."""
    body = "".join(
        f"#{t}\n{t // step % 2}!\nb{t:08b} #\n" for t in range(0, last_time + 1, step)
    )
    return _write_vcd(os.path.join(str(tmp_path), name), body)


def test_default_reads_to_end_of_vcd(tmp_path):
    """Regression: with no end_time the tool must not stop at t=1000."""
    vcd = _long_vcd(tmp_path)
    out = read_waveform(vcd, ["clk", "count"])

    times = {int(line.split("\t")[0]) for line in out.splitlines()[1:] if "\t" in line}
    assert max(times) == 5000
    assert 4500 in times


def test_explicit_end_time_still_bounds(tmp_path):
    vcd = _long_vcd(tmp_path)
    out = read_waveform(vcd, ["clk", "count"], end_time=1500)

    times = {int(line.split("\t")[0]) for line in out.splitlines()[1:] if "\t" in line}
    assert max(times) == 1500


def test_start_time_still_bounds(tmp_path):
    vcd = _long_vcd(tmp_path)
    out = read_waveform(vcd, ["clk", "count"], start_time=3000)

    times = {int(line.split("\t")[0]) for line in out.splitlines()[1:] if "\t" in line}
    assert min(times) >= 3000


def test_row_cap_reports_what_it_dropped(tmp_path):
    """Unbounded output would dump the whole VCD into the model's context; the
    cap is only honest if it says how much it withheld."""
    vcd = _long_vcd(tmp_path, last_time=1_000_000, step=100)
    out = read_waveform(vcd, ["clk", "count"])

    rows = [line for line in out.splitlines() if "\t" in line][1:]
    assert len(rows) == 2000
    assert "showing first 2000 of " in out
    assert "start_time" in out and "end_time" in out


def test_small_result_has_no_footer(tmp_path):
    vcd = _long_vcd(tmp_path)
    out = read_waveform(vcd, ["clk"])

    assert "showing first" not in out


def test_no_events_in_window_is_stated(tmp_path):
    vcd = _long_vcd(tmp_path)
    out = read_waveform(vcd, ["clk"], start_time=9000)

    assert "No events found" in out


def test_missing_file_reports_error(tmp_path):
    out = read_waveform(os.path.join(str(tmp_path), "nope.vcd"), ["clk"])
    assert "does not exist" in out
