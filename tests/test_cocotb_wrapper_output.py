"""cocotb_tool must carry evidence on the PASS path too (dev#80 defect 1).

A run with 1896 passing assertions used to return a single summary line with
zero output — the tail was computed for every branch and dropped only on PASS.
"""
import os

from src.tools import wrappers


def _fake_result(status, stdout, stderr="", passed=3, failed=0):
    return {
        "status": status,
        "passed": passed,
        "failed": failed,
        "stdout": stdout,
        "stderr": stderr,
    }


def _invoke(tmp_path, monkeypatch, result):
    ws = str(tmp_path)
    with open(os.path.join(ws, "dut.v"), "w", encoding="utf-8") as f:
        f.write("module dut(); endmodule\n")
    monkeypatch.setattr(wrappers, "get_workspace_path", lambda: ws)
    monkeypatch.setattr(wrappers, "run_cocotb", lambda *a, **k: result)
    return wrappers.cocotb_tool.func(
        verilog_files=["dut.v"], top_module="dut", python_module="verif.test_dut"
    )


def test_pass_output_includes_tail(tmp_path, monkeypatch):
    """PASS must include the run output, not just the ✅ headline."""
    sentinel = "SENTINEL_ASSERTION_DETAIL"
    stdout = "\n".join([f"line {i}" for i in range(200)] + [sentinel, "done"])
    out = _invoke(tmp_path, monkeypatch, _fake_result("PASS", stdout))

    assert "PASSED" in out
    assert "3 testcase(s)" in out
    assert sentinel in out


def test_pass_tail_is_bounded(tmp_path, monkeypatch):
    """The happy path stays readable — the tail is the last ~4000 chars."""
    stdout = "x" * 50000 + "\nTAIL_END"
    out = _invoke(tmp_path, monkeypatch, _fake_result("PASS", stdout))

    assert "TAIL_END" in out
    assert len(out) < 6000


def test_failure_paths_still_carry_tail(tmp_path, monkeypatch):
    """Regression fence: the non-PASS branches keep their existing tails."""
    for status, needle in (("FAIL", "FAILED"), ("TIMEOUT", "DID NOT TERMINATE"),
                           ("ERROR", "ERROR")):
        out = _invoke(
            tmp_path, monkeypatch,
            _fake_result(status, "boring\nMARKER_" + status, passed=0, failed=1),
        )
        assert needle in out
        assert "MARKER_" + status in out


def test_pass_with_error_text_in_tail_still_classifies_green(tmp_path, monkeypatch):
    """A passing run whose own output mentions an exception must not go red.

    run_cocotb prints `SC_COCOTB_TEST_EXC: RuntimeError(...)` and can still
    report PASS from results.xml; with a prose return the API's substring
    heuristic saw "Error" in the tail and wrote an error activity event. The
    JSON status keeps the verdict out of the tail's hands.
    """
    import json as _json
    from api import format_tool_result_for_api, classify_result_status

    stdout = "SC_COCOTB_TEST_EXC: RuntimeError('transient')\nall 3 tests FAILED-free"
    out = _invoke(tmp_path, monkeypatch, _fake_result("PASS", stdout))

    payload = _json.loads(out)
    assert payload["status"] == "test_passed"
    assert "RuntimeError" in payload["output_tail"]

    formatted = format_tool_result_for_api(out)
    assert formatted["status"] == "test_passed"
    assert classify_result_status(formatted) == "success"


def test_fail_and_timeout_statuses_classify_as_errors(tmp_path, monkeypatch):
    import json as _json
    from api import format_tool_result_for_api, classify_result_status

    for status, expected in (("FAIL", "test_failed"), ("TIMEOUT", "timeout"),
                             ("ERROR", "error")):
        out = _invoke(tmp_path, monkeypatch,
                      _fake_result(status, "output", passed=0, failed=2))
        assert _json.loads(out)["status"] == expected
        assert classify_result_status(format_tool_result_for_api(out)) == "error"
