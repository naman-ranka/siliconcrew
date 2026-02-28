import json
import os
from datetime import datetime, timezone
from typing import Any


EVENTS_FILE = "attempt_events.jsonl"
SUMMARY_FILE = "attempt_log.json"

CHANGE_TOOLS = {
    "write_spec",
    "load_yaml_spec_file",
    "write_file",
    "edit_file_tool",
    "apply_patch_tool",
    "start_synthesis",
}

CHECKPOINT_TOOLS = {
    "linter_tool",
    "simulation_tool",
    "get_synthesis_metrics",
    "generate_report_tool",
}


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
        status = str(obj.get("status", "unknown")).lower()
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
    wns = obj.get("wns_ns")
    tns = obj.get("tns_ns")
    try:
        wns = float(wns) if wns is not None else None
    except Exception:
        wns = None
    try:
        tns = float(tns) if tns is not None else None
    except Exception:
        tns = None
    return wns, tns


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
        if current is None:
            current = new_attempt(ts)
            attempts.append(current)
        elif tool in CHANGE_TOOLS and (current["_has_checkpoint"] or current["_had_failure"]):
            current["ended_at"] = ts
            current = new_attempt(ts)
            attempts.append(current)

        if tool in CHANGE_TOOLS:
            if tool == "start_synthesis":
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

        if tool == "linter_tool":
            l_status = "pass" if "syntax ok" in (result_text or "").lower() else "fail"
            current["rtl_lint"] = l_status
            current["_has_checkpoint"] = True
            current["_had_failure"] = current["_had_failure"] or l_status == "fail"
        elif tool == "simulation_tool":
            mode = str(args.get("mode", "rtl")).lower()
            parsed_mode, sim_status = _extract_sim_status(result_text)
            if mode not in {"rtl", "post_synth"}:
                mode = parsed_mode
            if mode == "post_synth":
                current["post_synth_sim"] = sim_status
            else:
                current["rtl_sim"] = sim_status
            current["_has_checkpoint"] = True
            current["_had_failure"] = current["_had_failure"] or sim_status == "fail"
        elif tool == "start_synthesis":
            current["synth_status"] = "running" if status == "success" else "failed"
            current["_had_failure"] = current["_had_failure"] or status == "error"
        elif tool == "get_synthesis_metrics":
            wns, tns = _extract_synth_metrics(result_text)
            current["wns_ns"] = wns
            current["tns_ns"] = tns
            current["synth_status"] = "completed"
            current["_has_checkpoint"] = True
            if wns is not None and tns is not None and (wns < 0 or tns != 0):
                current["_had_failure"] = True
        elif tool == "generate_report_tool":
            current["_has_checkpoint"] = True

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
