"""Regression: agent tool results must not be logged as errors (issue #31).

The chat WS logged ``status="success" if result["status"] == "success" else
"error"`` — an ALLOWLIST of one literal. No SiliconCrew tool ever returns the
literal "success": simulation_tool returns ``test_passed``, start_synthesis
``queued``, run_isolated_simulation ``passed``, get_synthesis_metrics ``ok``.
So every JSON-returning tool landed in ``attempt_events.jsonl`` as an error →
red X in the Activity dock, inflated "Errors N" filter counts, and
``attempt_log.json`` recording ``synth_status="failed"`` for every dispatched
synthesis (src/utils/attempt_logger.py keys off ``status == "success"``).

The fix flips it to a denylist (``api.tool_call_status``). These tests pin
both the pure predicate and the real WS → attempt-log → activity path.
"""
import json
import os
from contextlib import asynccontextmanager

import pytest
from starlette.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

import api
from src.api.activity import build_activity_events
from src.platform_engines.llm_keys import LlmKey
from src.utils.attempt_logger import EVENTS_FILE, SUMMARY_FILE


# --- The predicate itself ----------------------------------------------------

@pytest.mark.parametrize("status", [
    "test_passed",   # simulation_tool
    "passed",        # run_isolated_simulation
    "queued",        # start_synthesis
    "running",       # get_synthesis_status
    "ok",            # get_synthesis_metrics
    "completed",
    "",              # non-JSON / statusless tool output
])
def test_non_failure_statuses_are_successful_calls(status):
    assert api.tool_call_status({"status": status}) == "success"


@pytest.mark.parametrize("status", [
    "test_failed", "sim_failed", "compile_failed", "lint_failed",
    "error", "fail", "failed", "timeout", "timed_out", "cancelled",
    "FAILED", "  Error  ",  # case / whitespace insensitive
])
def test_failure_statuses_are_error_calls(status):
    assert api.tool_call_status({"status": status}) == "error"


def test_missing_status_key_is_a_successful_call():
    assert api.tool_call_status({}) == "success"


# --- The real logging path (chat WS → attempt_events.jsonl → activity) -------

class _ToolResultAgent:
    """Emits one tool call and its JSON result, exactly as the tools node does."""

    def __init__(self, tool_name, payload):
        self._call = AIMessage(
            content="", tool_calls=[{"name": tool_name, "args": {}, "id": "tc1"}]
        )
        self._result = ToolMessage(content=json.dumps(payload), tool_call_id="tc1")

    async def aget_state(self, config):
        class _State:
            values: dict = {}
        return _State()

    async def astream(self, inputs, config, stream_mode=None):
        yield ("updates", {"agent": {"messages": [self._call]}})
        yield ("updates", {"tools": {"messages": [self._result]}})


def _run_turn(monkeypatch, workspace, tool_name, payload):
    """Drive one real chat-WS turn that produces ``payload`` from ``tool_name``."""
    api._ACTIVE_TURNS.clear()
    monkeypatch.setattr(
        api, "create_architect_agent", lambda **k: _ToolResultAgent(tool_name, payload)
    )

    @asynccontextmanager
    async def fake_ckpt(_p):
        yield object()

    monkeypatch.setattr(api, "open_checkpointer", fake_ckpt)

    class _WS:
        def workspace_for(self, sid):
            return workspace

        def sync(self, sid):
            pass

    monkeypatch.setattr(api, "get_workspace_provider", lambda: _WS())
    monkeypatch.setattr(api, "_uid", lambda identity: "u1")

    class _Prov:
        def resolve(self, uid, model_name):
            return LlmKey(provider="anthropic", api_key="k", source="env")

    monkeypatch.setattr(api, "_LLM_KEY_PROVIDER", _Prov())

    sm = api.session_manager
    monkeypatch.setattr(sm, "owns_session", lambda sid, uid=None: True)
    monkeypatch.setattr(sm, "resolve_ws_thread", lambda tid, sid, user_id=None: sid)
    monkeypatch.setattr(sm, "touch_thread", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_thread", lambda *a, **k: {})
    monkeypatch.setattr(sm, "update_session_stats", lambda *a, **k: None)
    monkeypatch.setattr(sm, "get_session_metadata", lambda *a, **k: {"model_name": "claude-sonnet-5"})

    frames = []
    with TestClient(api.app).websocket_connect("/api/chat/sess1") as ws:
        ws.send_json({"message": "go"})
        while True:
            f = ws.receive_json()
            frames.append(f)
            if f.get("type") in ("done", "error", "stopped"):
                break
    assert frames[-1]["type"] == "done", frames
    return frames


def _events(workspace):
    path = os.path.join(workspace, EVENTS_FILE)
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


# A real simulation_tool payload (src/tools/run_simulation.py) — a PASS.
SIM_PASSED = {
    "status": "test_passed",
    "success": True,
    "outcome": "test_passed",
    "pass_marker_found": True,
    "pass_marker": "TEST PASSED",
    "compile_returncode": 0,
    "sim_returncode": 0,
    "mode": "rtl",
}


def test_passing_simulation_is_logged_as_a_successful_call(tmp_path, monkeypatch):
    ws_dir = str(tmp_path / "ws")
    os.makedirs(ws_dir, exist_ok=True)

    _run_turn(monkeypatch, ws_dir, "simulation_tool", SIM_PASSED)

    results = [e for e in _events(ws_dir) if e.get("event_type") == "tool_result"]
    assert len(results) == 1, results
    # THE bug: a passing simulation was durably recorded as an errored call.
    assert results[0]["status"] == "success", results[0]

    # ...and therefore rendered as a red X by the Activity dock.
    activity = build_activity_events(_events(ws_dir))
    assert [e["status"] for e in activity] == ["ok"], activity


def test_failing_simulation_is_still_logged_as_an_error(tmp_path, monkeypatch):
    """The denylist must not turn every call green — a real failure stays red."""
    ws_dir = str(tmp_path / "ws")
    os.makedirs(ws_dir, exist_ok=True)

    failed = {**SIM_PASSED, "status": "test_failed", "success": False,
              "outcome": "test_failed", "pass_marker_found": False}
    _run_turn(monkeypatch, ws_dir, "simulation_tool", failed)

    results = [e for e in _events(ws_dir) if e.get("event_type") == "tool_result"]
    assert results[0]["status"] == "error", results[0]
    assert [e["status"] for e in build_activity_events(_events(ws_dir))] == ["error"]


def test_dispatched_synthesis_is_recorded_as_running_not_failed(tmp_path, monkeypatch):
    """Collateral damage of the same bug: attempt_logger keys the synthesis
    verdict off the logged call status, so every dispatch was summarised as a
    FAILED synthesis in attempt_log.json."""
    ws_dir = str(tmp_path / "ws")
    os.makedirs(ws_dir, exist_ok=True)

    queued = {
        "run_id": "synth_0001",
        "status": "queued",
        "stage": "queued",
        "timeout_sec": 3600,
        "poll_after_sec": 15,
    }
    _run_turn(monkeypatch, ws_dir, "start_synthesis", queued)

    with open(os.path.join(ws_dir, SUMMARY_FILE), "r", encoding="utf-8") as f:
        summary = json.load(f)
    attempts = summary["attempts"]
    assert attempts, summary
    assert attempts[-1]["synth_status"] == "running", summary
