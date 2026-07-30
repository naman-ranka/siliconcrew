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


# --- sc#74: hierarchical names + collision honesty -------------------------
#
# The header parse used to keep only the $var leaf ref and ignore $scope
# entirely, so hierarchical requests could never match and a leaf that existed
# in two scopes silently resolved to whichever came first — the tool could
# return the WRONG signal with no warning.

NESTED_HEADER = """$date
    Nov 27 2025
$end
$timescale
    1ns
$end
$scope module tb $end
$var wire 1 ! clk $end
$scope begin stim $end
$var wire 1 % clk $end
$upscope $end
$scope module dut $end
$var wire 8 # count [7:0] $end
$var wire 1 & clk $end
$upscope $end
$upscope $end
$enddefinitions
$end
"""

NESTED_BODY = """#0
0!
0%
1&
b00000000 #
#10
1!
0&
b00000001 #
#20
0!
1&
b00000010 #
"""


def _nested_vcd(tmp_path, name="nested.vcd"):
    return _write_vcd(os.path.join(str(tmp_path), name), NESTED_BODY, NESTED_HEADER)


def _rows(out):
    return [line for line in out.splitlines()[1:] if "\t" in line]


def test_hierarchical_path_resolves(tmp_path):
    """A full dotted path is how a designer names a signal in a real design."""
    out = _nested_vcd(tmp_path)
    result = read_waveform(out, ["tb.dut.count"])

    assert "not found" not in result
    assert len(_rows(result)) == 3
    assert all("tb.dut.count" in r for r in _rows(result))


def test_unique_leaf_still_resolves(tmp_path):
    """The convenient short form keeps working when it is unambiguous."""
    result = read_waveform(_nested_vcd(tmp_path), ["count"])

    assert len(_rows(result)) == 3
    assert all("count" in r for r in _rows(result))


def test_ambiguous_leaf_is_an_error_naming_candidates(tmp_path):
    """Pre-fix this silently returned tb.clk. Guessing is the bug."""
    result = read_waveform(_nested_vcd(tmp_path), ["clk"])

    assert "Ambiguous" in result
    assert "tb.clk" in result
    assert "tb.dut.clk" in result
    assert "tb.stim.clk" in result
    # It must not have quietly returned one of them instead.
    assert not _rows(result)


def test_full_path_disambiguates_a_colliding_leaf(tmp_path):
    result = read_waveform(_nested_vcd(tmp_path), ["tb.dut.clk"])

    rows = _rows(result)
    assert len(rows) == 3
    assert all(r.split("\t")[1] == "tb.dut.clk" for r in rows)
    # tb.dut.clk is deliberately the INVERSE of tb.clk (1,0,1 vs 0,1,0), so
    # this fails if the resolver picked the colliding leaf's other code.
    assert [r.split("\t")[2] for r in rows] == ["1", "0", "1"]


def test_not_found_lists_full_paths(tmp_path):
    result = read_waveform(_nested_vcd(tmp_path), ["nosuch"])

    assert "not found" in result
    assert "tb.dut.count" in result


def test_named_block_scope_does_not_corrupt_later_paths(tmp_path):
    """A $scope begin must push like any other scope; if only `module` pushed,
    the block's $upscope would pop the module and every later $var would get a
    wrong path — the exact silent-wrong-signal failure this fixes."""
    result = read_waveform(_nested_vcd(tmp_path), ["tb.stim.clk"])
    # The block's clk only changes at t=0 in this fixture; resolving at all is
    # the point (pre-fix it was reachable under no name whatsoever).
    assert _rows(result) == ["0\ttb.stim.clk\t0"]

    # And the module that follows the block still reports its true path.
    assert "tb.dut.count" in read_waveform(_nested_vcd(tmp_path), ["nope"])


def test_stray_upscope_does_not_crash(tmp_path):
    """Guard the pop: a malformed header must not take the tool down."""
    header = NESTED_HEADER.replace("$enddefinitions", "$upscope $end\n$upscope $end\n$enddefinitions")
    vcd = _write_vcd(os.path.join(str(tmp_path), "stray.vcd"), NESTED_BODY, header)

    result = read_waveform(vcd, ["tb.dut.count"])
    assert len(_rows(result)) == 3


def test_same_code_in_two_scopes_is_not_ambiguous(tmp_path):
    """VCD reuses one identifier code for a signal connected across hierarchy.
    Two paths, one code, one signal — reporting that as ambiguous would be a
    false alarm."""
    header = NESTED_HEADER.replace('$var wire 1 & clk $end', '$var wire 1 @ shared $end')
    header = header.replace('$var wire 1 ! clk $end', '$var wire 1 @ shared $end')
    header = header.replace('$var wire 1 % clk $end', '$var wire 1 $ other $end')
    vcd = _write_vcd(os.path.join(str(tmp_path), "alias.vcd"), "#0\n0@\n#10\n1@\n", header)

    result = read_waveform(vcd, ["shared"])
    assert "Ambiguous" not in result
    assert len(_rows(result)) == 2
