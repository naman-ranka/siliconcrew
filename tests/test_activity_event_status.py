"""Activity-event status classification (dev#31).

The agent stream recorded `status == "success"` or else `"error"` into
`attempt_events.jsonl`, so tools returning a legitimate domain status
(`test_passed`, `queued`) were logged as errors — red X in the Activity dock,
counted in the Errors filter. The event answers "did the tool CALL complete",
not "did the design pass"; domain verdicts live in the payload.
"""
import pytest

from api import classify_result_status


@pytest.mark.parametrize("status", [
    "success",
    "test_passed",   # simulation
    "queued",        # start_synthesis
    "running",
    "completed",
])
def test_non_failure_statuses_are_success(status):
    assert classify_result_status({"status": status}) == "success"


@pytest.mark.parametrize("status", [
    "error",
    "failed",
    "fail",
    "compile_failed",   # run_simulation
    "sim_failed",
    "test_failed",
    "timeout",
    "cancelled",
    "rejected",         # quota
    "denied",
])
def test_failure_statuses_are_error(status):
    assert classify_result_status({"status": status}) == "error"


def test_classification_is_case_insensitive():
    assert classify_result_status({"status": "TIMEOUT"}) == "error"
    assert classify_result_status({"status": "Compile_Failed"}) == "error"


def test_missing_status_is_success():
    # `format_tool_result_for_api` always sets one, but never blow up on a
    # payload that doesn't.
    assert classify_result_status({}) == "success"
