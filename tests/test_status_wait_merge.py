"""One synthesis status reader, and one place that refuses to block on it.

``wait_for_synthesis`` was a bounded poll loop over ``get_synthesis_status``, so
it is now an argument on the reader rather than a tool of its own. That merge
would quietly hand the web UI a call that occupies a worker for two minutes —
the reason the wait tool was kept off the UI surface in the first place — so the
``/invoke`` path clamps it. Invariant 6: the UI is a viewer, not an actor.

The clamp lives on the surface, not on the tool: the agent and MCP call the same
wrapper and DO get to wait, because for them one blocking call replaces ten
polls.
"""
import json

import pytest

from src.api import tool_catalog
from src.tools import wrappers


@pytest.fixture
def status_calls(tmp_path, monkeypatch):
    """A fake status source that never sleeps and counts how often it is read."""
    seen = {"n": 0}

    def fake_status(run_id, workspace=None):
        seen["n"] += 1
        return {"run_id": run_id, "status": "running", "poll_after_sec": 1}

    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(wrappers, "collect_synthesis_status", fake_status)
    monkeypatch.setattr(wrappers.time, "sleep", lambda *_: None)
    return seen


def _status(**kwargs) -> dict:
    return json.loads(wrappers.get_synthesis_status.invoke(kwargs))


def test_without_a_wait_it_answers_from_one_read(status_calls):
    """The non-blocking reader is unchanged: one sample, no loop, no wait
    bookkeeping in the reply."""
    data = _status(run_id="synth_0001")
    assert data["status"] == "running"
    assert status_calls["n"] == 1
    assert "waited_sec" not in data


def test_with_a_wait_it_polls_and_reports_the_timeout_honestly(status_calls, monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(wrappers.time, "time", lambda: clock["t"])
    monkeypatch.setattr(wrappers.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))

    data = _status(run_id="synth_0001", wait_sec=10, poll_interval_sec=1)
    assert status_calls["n"] > 1
    assert data["timed_out"] is True
    assert data["waited_sec"] <= wrappers.WAIT_MAX_WAIT_SEC
    # It says how to keep waiting, and names a tool that exists.
    assert "get_synthesis_status" in data["next_action"]


def test_the_wait_returns_as_soon_as_the_run_is_terminal(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_status(run_id, workspace=None):
        calls["n"] += 1
        if calls["n"] < 3:
            return {"run_id": run_id, "status": "running", "poll_after_sec": 1}
        return {"run_id": run_id, "status": "completed", "poll_after_sec": 0}

    monkeypatch.setenv("RTL_WORKSPACE", str(tmp_path))
    monkeypatch.setattr(wrappers, "collect_synthesis_status", fake_status)
    monkeypatch.setattr(wrappers.time, "sleep", lambda *_: None)

    data = _status(run_id="synth_0001", wait_sec=60)
    assert data["status"] == "completed"
    assert data["timed_out"] is False
    assert calls["n"] == 3


def test_the_wait_is_clamped_to_the_ceiling(status_calls, monkeypatch):
    clock = {"t": 0.0}
    monkeypatch.setattr(wrappers.time, "time", lambda: clock["t"])
    monkeypatch.setattr(wrappers.time, "sleep", lambda s: clock.__setitem__("t", clock["t"] + s))

    data = _status(run_id="synth_0001", wait_sec=99999)
    assert data["waited_sec"] <= wrappers.WAIT_MAX_WAIT_SEC


# --- the surface rule ---------------------------------------------------------

def test_the_invoke_path_never_blocks(status_calls, tmp_path):
    """The web UI's own path forces the wait to zero: same tool, same answer it
    already had, no worker held for two minutes."""
    result = tool_catalog.validate_and_execute(
        "get_synthesis_status", str(tmp_path), {"run_id": "synth_0001", "wait_sec": 120}
    )
    data = json.loads(result)
    assert status_calls["n"] == 1          # one read, not a poll loop
    assert "waited_sec" not in data        # it never entered the wait


def test_the_clamp_is_a_rule_about_arguments_not_a_list_of_tools():
    """No tool name is written down anywhere for this. Any tool that later
    offers a blocking wait under the same argument name is covered on the day it
    is written."""
    args = {"run_id": "x", "wait_sec": 60, "poll_interval_sec": 5}
    tool_catalog.clamp_blocking_waits(args)
    assert args == {"run_id": "x", "wait_sec": 0, "poll_interval_sec": 5}


def test_the_status_reader_is_offered_on_every_surface():
    """It is the UI's Refresh, the agent's poll and an MCP client's poll — the
    merge must not have dropped it off a surface to keep the wait off the UI."""
    policy = wrappers.get_synthesis_status.func.__tool_policy__
    assert policy.surfaces >= {"agent", "mcp", "ui"}
