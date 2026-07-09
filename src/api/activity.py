"""Unified activity feed — read side of the per-session tool event log.

``attempt_logger`` appends every tool call/result (agent WS, MCP, and — as of
Workbench v2 — user-initiated REST actions) to ``<workspace>/attempt_events.jsonl``
as separate ``tool_call`` / ``tool_result`` records. This module pairs those
records into single UI-facing events (camelCase, per data-model.md) so the
frontend's Activity feed can render one row per tool invocation with an honest
status: ``running`` (call without result yet), ``ok``, or ``error``.

Pure functions over already-read records; no FastAPI here. The endpoint lives
in ``src/api/actions.py`` and the snapshot embeds the most recent page.
"""
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.utils.attempt_logger import EVENTS_FILE, _read_events

# Sources recorded by attempt_logger → UI actor buckets. The agent's WS loop
# logs "api_ws"; MCP logs "mcp"; the REST action layer logs "ui".
_SOURCE_MAP = {"api_ws": "agent", "agent": "agent", "ui": "user", "user": "user", "mcp": "mcp"}

_RUN_ID_PAT = re.compile(r"\b(?:sim|synth)_\d{1,6}\b")
_RESULT_SUMMARY_MAX = 500


def _map_source(raw: Any) -> str:
    return _SOURCE_MAP.get(str(raw or "").lower(), "agent")


def _iso_delta_ms(start: Optional[str], end: Optional[str]) -> Optional[int]:
    if not start or not end:
        return None
    try:
        t0 = datetime.fromisoformat(start)
        t1 = datetime.fromisoformat(end)
        return max(0, int((t1 - t0).total_seconds() * 1000))
    except (ValueError, TypeError):
        return None


def _extract_run_id(args: Any, result_text: Optional[str]) -> Optional[str]:
    """Best-effort run id: explicit arg fields first, then id patterns in the result."""
    if isinstance(args, dict):
        for key in ("run_id", "runId", "source_run_id", "sourceRunId"):
            val = args.get(key)
            if isinstance(val, str) and val:
                return val
    if result_text:
        m = _RUN_ID_PAT.search(result_text)
        if m:
            return m.group(0)
    return None


def build_activity_events(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Pair raw jsonl records into UI events, in file (chronological) order.

    Pairing: by ``tool_call_id`` when both sides carry one; otherwise a result
    closes the most recent unpaired call for the same tool name. A result with
    no matching call becomes a standalone completed event (the log may predate
    call-side logging); a call with no result stays ``running``.
    """
    events: List[Dict[str, Any]] = []
    by_call_id: Dict[str, Dict[str, Any]] = {}
    open_by_tool: Dict[str, List[Dict[str, Any]]] = {}
    # Deterministic-id orphan results (e.g. the synthesis completion event,
    # tool_call_id "completion:<run_id>") may be emitted by more than one
    # instance — duplicates collapse here at read time (plan round-2 #2).
    seen_orphan_ids: set = set()

    for i, rec in enumerate(records):
        etype = rec.get("event_type")
        tool = rec.get("tool")
        if not isinstance(tool, str) or not tool:
            continue
        ts = rec.get("ts")
        cid = rec.get("tool_call_id")
        args = rec.get("arguments") if isinstance(rec.get("arguments"), dict) else {}

        if etype == "tool_call":
            ev = {
                "id": str(cid) if cid else f"evt-{i}",
                "ts": ts,
                "source": _map_source(rec.get("source")),
                "tool": tool,
                "args": args,
                "status": "running",
                "resultSummary": "",
                "durationMs": None,
                "runId": _extract_run_id(args, None),
                "threadId": rec.get("thread_id"),
                "_callTs": ts,
            }
            events.append(ev)
            if cid:
                by_call_id[str(cid)] = ev
            else:
                open_by_tool.setdefault(tool, []).append(ev)
            continue

        if etype != "tool_result":
            continue

        ev = None
        if cid and str(cid) in by_call_id:
            ev = by_call_id.pop(str(cid))
        elif open_by_tool.get(tool):
            ev = open_by_tool[tool].pop()
        if ev is None:
            if cid:
                if str(cid) in seen_orphan_ids:
                    continue  # duplicate deterministic-id event (cross-instance)
                seen_orphan_ids.add(str(cid))
            ev = {
                "id": str(cid) if cid else f"evt-{i}",
                "ts": ts,
                "source": _map_source(rec.get("source")),
                "tool": tool,
                "args": args,
                "status": "running",
                "resultSummary": "",
                "durationMs": None,
                "runId": _extract_run_id(args, rec.get("result")),
                "threadId": rec.get("thread_id"),
                "_callTs": None,
            }
            events.append(ev)

        status = str(rec.get("status", "success")).lower()
        result_text = rec.get("result") or ""
        ev["status"] = "error" if status in ("error", "fail", "failed") else "ok"
        ev["resultSummary"] = result_text[:_RESULT_SUMMARY_MAX]
        if not ev["args"] and args:
            ev["args"] = args
        ev["runId"] = _extract_run_id(args, result_text) or ev["runId"]
        ev["durationMs"] = _iso_delta_ms(ev.get("_callTs"), ts)

    for ev in events:
        ev.pop("_callTs", None)
    return events


def read_activity(
    workspace: str,
    limit: int = 100,
    before: Optional[str] = None,
) -> Dict[str, Any]:
    """Newest-first page of activity events for a workspace.

    ``before`` is the id of the last event of the previous page (opaque cursor);
    ``nextBefore`` is null when the log is exhausted. Missing/corrupt log lines
    never raise — _read_events already skips unparsable lines.
    """
    limit = max(1, min(int(limit), 500))
    records = _read_events(os.path.join(workspace, EVENTS_FILE))
    events = build_activity_events(records)
    events.reverse()  # newest first

    start = 0
    if before:
        for idx, ev in enumerate(events):
            if ev["id"] == before:
                start = idx + 1
                break
    page = events[start:start + limit]
    has_more = (start + len(page)) < len(events)
    next_before = page[-1]["id"] if (page and has_more) else None
    return {"events": page, "nextBefore": next_before}
