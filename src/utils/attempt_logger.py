import json
import os
from datetime import datetime, timezone
from typing import Any


EVENTS_FILE = "attempt_events.jsonl"
SUMMARY_FILE = "attempt_log.json"


def _tool_policy(tool: str):
    """The :class:`ToolPolicy` for a tool NAME read out of an event row.

    Lazy import on purpose: this module is dependency-light and is imported BY
    the tool registry (the wrappers declare the readers below on their tools),
    so it cannot import the registry at module load.

    ``None`` for a name the registry does not know. Event rows are a data
    stream from every actor, and they legitimately carry names that are not
    registry tools: the ``synthesis_run`` system pseudo-tool
    (synthesis_manager.py), the MCP server's session tools, and rows recorded
    before a rename. Those have no attempt semantics by construction — this is
    not a policy default for a REGISTERED tool, which cannot be missing
    (tests/test_tool_policy.py).
    """
    from src.api.tool_catalog import UnknownToolError, policy_for

    try:
        return policy_for(tool)
    except UnknownToolError:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_workspace(workspace: str) -> bool:
    if not workspace:
        return False
    if not os.path.exists(workspace):
        return False
    return True


def _append_jsonl(path: str, obj: dict[str, Any]) -> None:
    with open(path, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, ensure_ascii=True) + "\n")


def _read_events(path: str) -> list[dict[str, Any]]:
    if not os.path.exists(path):
        return []
    out: list[dict[str, Any]] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out.append(obj)
            except Exception:
                continue
    return out


def _parse_json_maybe(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    raw = text.strip()
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except Exception:
        return None
    return None


def _event_ts(ev: dict[str, Any]) -> str:
    ts = ev.get("ts")
    if isinstance(ts, str) and ts.strip():
        return ts
    return _utc_now()


def _compact_string(value: str, max_len: int = 240) -> dict[str, Any]:
    raw = value or ""
    preview = raw if len(raw) <= max_len else raw[:max_len] + "...(truncated)"
    return {"preview": preview, "length": len(raw)}


def _compact_value(value: Any, depth: int = 0) -> Any:
    if depth > 2:
        return "<truncated-depth>"
    if isinstance(value, str):
        if len(value) > 300:
            return _compact_string(value)
        return value
    if isinstance(value, list):
        if len(value) > 20:
            return {"type": "list", "length": len(value), "head": [_compact_value(v, depth + 1) for v in value[:5]]}
        return [_compact_value(v, depth + 1) for v in value]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            key = str(k)
            if key in {"content", "target_text", "replacement_text", "unified_diff"} and isinstance(v, str):
                out[key] = _compact_string(v)
            else:
                out[key] = _compact_value(v, depth + 1)
        return out
    return value


def _compact_result(result: str | None) -> str:
    text = result or ""
    if len(text) <= 4000:
        return text
    return text[:4000] + "\n...(truncated)"


def _status_from_text(text: str | None) -> str:
    raw = (text or "").lower()
    if not raw:
        return "unknown"
    if "test_passed" in raw or "syntax ok" in raw or "success" in raw:
        return "pass"
    if "error" in raw or "failed" in raw or "fail" in raw:
        return "fail"
    return "unknown"


def _extract_sim_status(result_text: str | None) -> tuple[str, str]:
    obj = _parse_json_maybe(result_text)
    if obj:
        mode = str(obj.get("mode", "rtl"))
        # An isolated run's top-level ``status`` is the run verdict
        # (passed/failed); the SIMULATION verdict is ``simStatus``. Reading only
        # the top level logged every passing run as "unknown" — the run happened
        # and the attempt summary said nothing about it.
        status = str(obj.get("simStatus") or obj.get("status", "unknown")).lower()
        if status == "test_passed":
            return mode, "pass"
        if "fail" in status:
            return mode, "fail"
        return mode, "unknown"
    return "rtl", _status_from_text(result_text)


def _extract_synth_metrics(result_text: str | None) -> tuple[float | None, float | None]:
    obj = _parse_json_maybe(result_text)
    if not obj:
        return None, None
    # get_synthesis_metrics nests the PPA fields under "metrics" (the top level
    # is the wrapper: status/run_id/metrics/...), so reading the top level
    # logged None for every attempt. Flat payloads (older logs, save_metrics
    # output) still resolve.
    ppa = obj.get("metrics") if isinstance(obj.get("metrics"), dict) else obj
    wns = ppa.get("wns_ns")
    tns = ppa.get("tns_ns")
    try:
        wns = float(wns) if wns is not None else None
    except Exception:
        wns = None
    try:
        tns = float(tns) if tns is not None else None
    except Exception:
        tns = None
    return wns, tns


# --- Per-tool result readers -------------------------------------------------
# Each reader fills the attempt summary from ONE tool's result. A tool names its
# reader on its own policy (``attempt_parser=`` in src/tools/wrappers.py); this
# module never selects one by tool name. That is the whole point: the dispatch
# used to be a chain of ``if tool == "..."`` here, five tool names away from the
# tools themselves, with no way to notice a tool that nobody handled.
#
# Contract: mutate ``attempt`` in place. ``_had_failure`` marks a failed
# checkpoint (the next change opens a new attempt). ``_has_checkpoint`` is NOT
# set here — it comes from the policy's ``attempt_role``.

def attempt_lint(attempt: dict[str, Any], arguments: dict[str, Any],
                 result_text: str | None, status: str) -> None:
    text = (result_text or "").lower()
    l_status = "pass" if ("syntax ok" in text or "lint passed" in text) else "fail"
    attempt["rtl_lint"] = l_status
    attempt["_had_failure"] = attempt["_had_failure"] or l_status == "fail"


def attempt_simulation(attempt: dict[str, Any], arguments: dict[str, Any],
                       result_text: str | None, status: str) -> None:
    mode = str(arguments.get("mode", "rtl")).lower()
    parsed_mode, sim_status = _extract_sim_status(result_text)
    if mode not in {"rtl", "post_synth"}:
        mode = parsed_mode
    if mode == "post_synth":
        attempt["post_synth_sim"] = sim_status
    else:
        attempt["rtl_sim"] = sim_status
    attempt["_had_failure"] = attempt["_had_failure"] or sim_status == "fail"


def attempt_synthesis_dispatch(attempt: dict[str, Any], arguments: dict[str, Any],
                               result_text: str | None, status: str) -> None:
    attempt["synth_status"] = "running" if status == "success" else "failed"
    attempt["_had_failure"] = attempt["_had_failure"] or status == "error"


def attempt_synthesis_metrics(attempt: dict[str, Any], arguments: dict[str, Any],
                              result_text: str | None, status: str) -> None:
    wns, tns = _extract_synth_metrics(result_text)
    attempt["wns_ns"] = wns
    attempt["tns_ns"] = tns
    attempt["synth_status"] = "completed"
    if wns is not None and tns is not None and (wns < 0 or tns != 0):
        attempt["_had_failure"] = True


def _write_summary(workspace: str, session_id: str | None) -> None:
    events_path = os.path.join(workspace, EVENTS_FILE)
    events = _read_events(events_path)
    attempts: list[dict[str, Any]] = []
    pending_calls: dict[str, dict[str, Any]] = {}
    current: dict[str, Any] | None = None

    def new_attempt(start_ts: str) -> dict[str, Any]:
        return {
            "attempt": len(attempts) + 1,
            "change_type": "unknown",
            "changes": [],
            "rtl_lint": "not_run",
            "rtl_sim": "not_run",
            "synth_status": "not_run",
            "wns_ns": None,
            "tns_ns": None,
            "post_synth_sim": "not_run",
            "spec_match": "unknown",
            "started_at": start_ts,
            "ended_at": None,
            "_has_checkpoint": False,
            "_had_failure": False,
        }

    def touch_attempt_for_call(tool: str, args: dict[str, Any], ts: str) -> None:
        nonlocal current
        policy = _tool_policy(tool)
        role = policy.attempt_role if policy is not None else None
        is_change = role in ("rtl_change", "synth_change")
        if current is None:
            current = new_attempt(ts)
            attempts.append(current)
        elif is_change and (current["_has_checkpoint"] or current["_had_failure"]):
            current["ended_at"] = ts
            current = new_attempt(ts)
            attempts.append(current)

        if is_change:
            if role == "synth_change":
                current["change_type"] = "synth" if current["change_type"] == "unknown" else "both"
            else:
                if current["change_type"] == "unknown":
                    current["change_type"] = "rtl"
                elif current["change_type"] == "synth":
                    current["change_type"] = "both"
            if len(current["changes"]) < 10:
                current["changes"].append(tool)

    for ev in events:
        etype = ev.get("event_type")
        tool = ev.get("tool")
        if not tool:
            continue
        args = ev.get("arguments") if isinstance(ev.get("arguments"), dict) else {}
        tool_call_id = ev.get("tool_call_id")
        ts = _event_ts(ev)
        if etype == "tool_call":
            touch_attempt_for_call(tool, args, ts)
            if tool_call_id:
                pending_calls[tool_call_id] = {"tool": tool, "arguments": args}
            continue

        if etype != "tool_result":
            continue
        if current is None:
            current = new_attempt(ts)
            attempts.append(current)

        if tool_call_id and tool_call_id in pending_calls:
            call = pending_calls.pop(tool_call_id)
            tool = call.get("tool", tool)
            args = call.get("arguments", args)

        result_text = ev.get("result")
        status = str(ev.get("status", "unknown")).lower()

        policy = _tool_policy(tool)
        if policy is not None:
            if policy.attempt_role == "checkpoint":
                current["_has_checkpoint"] = True
            if policy.attempt_parser is not None:
                policy.attempt_parser(current, args, result_text, status)

    if current is not None and current["ended_at"] is None:
        current["ended_at"] = _event_ts(events[-1]) if events else _utc_now()

    for a in attempts:
        a.pop("_has_checkpoint", None)
        a.pop("_had_failure", None)

    # Compute session-level success cumulatively (passes may occur across different attempts).
    seen_rtl_pass = False
    seen_post_pass = False
    best_attempt = None
    for a in attempts:
        if a.get("rtl_sim") == "pass":
            seen_rtl_pass = True
        if a.get("post_synth_sim") == "pass":
            seen_post_pass = True
        if best_attempt is None and seen_rtl_pass and seen_post_pass:
            best_attempt = a["attempt"]
    success = bool(seen_rtl_pass and seen_post_pass)

    summary = {
        "session_id": session_id,
        "attempt_count": len(attempts),
        "attempts": attempts,
        "final": {
            "success": success,
            "best_attempt": best_attempt,
        },
        "updated_at": _utc_now(),
    }
    with open(os.path.join(workspace, SUMMARY_FILE), "w", encoding="utf-8", newline="\n") as f:
        json.dump(summary, f, indent=2)


def log_tool_call(
    workspace: str,
    session_id: str | None,
    source: str,
    tool: str,
    arguments: dict[str, Any] | None = None,
    tool_call_id: str | None = None,
) -> None:
    if not _ensure_workspace(workspace):
        return
    event = {
        "ts": _utc_now(),
        "event_type": "tool_call",
        "source": source,
        "session_id": session_id,
        "tool": tool,
        "tool_call_id": tool_call_id,
        "arguments": _compact_value(arguments or {}),
    }
    _append_jsonl(os.path.join(workspace, EVENTS_FILE), event)
    _write_summary(workspace, session_id)


def log_tool_result(
    workspace: str,
    session_id: str | None,
    source: str,
    tool: str,
    result: str | None,
    status: str = "success",
    error: str | None = None,
    tool_call_id: str | None = None,
    arguments: dict[str, Any] | None = None,
) -> None:
    if not _ensure_workspace(workspace):
        return
    event = {
        "ts": _utc_now(),
        "event_type": "tool_result",
        "source": source,
        "session_id": session_id,
        "tool": tool,
        "tool_call_id": tool_call_id,
        "status": status,
        "arguments": _compact_value(arguments or {}),
        "result": _compact_result(result),
        "error": (error or "")[:2000] if error else None,
    }
    _append_jsonl(os.path.join(workspace, EVENTS_FILE), event)
    _write_summary(workspace, session_id)
