from __future__ import annotations

from pathlib import Path
from typing import Any
import json


def load_jsonl(path: Path | None) -> list[dict[str, Any]]:
    if not path or not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def write_agent_trace(run_dir: Path, agent_events: Path | list[Path] | None, sc_attempt_events: Path | None, summary: dict[str, Any]) -> Path:
    out = run_dir / "agent_trace.md"
    lines: list[str] = []
    problem = summary.get("problem", {})
    lines.append("# Agent Trace")
    lines.append("")
    lines.append(f"- Problem: `{problem.get('id')}`")
    lines.append(f"- Flow: `{summary.get('flow')}`")
    lines.append(f"- Agent: `{summary.get('agent')}`")
    lines.append(f"- Status: `{summary.get('status')}`")
    lines.append("")

    lines.append("## Agent Events")
    event_paths = _as_paths(agent_events)
    any_agent_rows = False
    for idx, path in enumerate(event_paths):
        label = "Initial run" if idx == 0 else f"Continuation {idx:03d}"
        rows = load_jsonl(path)
        if rows:
            any_agent_rows = True
            lines.append(f"### {label}")
        for row in rows[:200]:
            item = row.get("item") or {}
            if item.get("type") == "mcp_tool_call":
                lines.append(f"- `{item.get('tool')}`: {item.get('status', '')}")
            elif row.get("type"):
                lines.append(f"- {row.get('type')}")
    if not any_agent_rows:
        lines.append("- No agent event JSONL found.")
    lines.append("")

    lines.append("## SiliconCrew Tool Calls")
    sc_rows = load_jsonl(sc_attempt_events)
    for row in sc_rows[:300]:
        event = row.get("event_type")
        tool = row.get("tool")
        status = row.get("status")
        if event == "tool_call":
            lines.append(f"- call `{tool}`")
        elif event == "tool_result":
            lines.append(f"- result `{tool}`: {status}")
    if not sc_rows:
        lines.append("- No SiliconCrew attempt_events.jsonl found.")
    lines.append("")

    metrics = summary.get("siliconcrew", {}).get("summary_metrics") or {}
    if metrics:
        lines.append("## PPA")
        for k in ("area_um2", "cell_count", "power_uw", "wns_ns", "tns_ns"):
            lines.append(f"- {k}: `{metrics.get(k)}`")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return out


def extract_thread_id(events_path: Path | None) -> str | None:
    for row in load_jsonl(events_path):
        if row.get("thread_id"):
            return str(row["thread_id"])
    return None


def has_failed_agent_event(events_path: Path | None) -> bool:
    for row in load_jsonl(events_path):
        item = row.get("item") or {}
        if item.get("status") == "failed" or row.get("type") == "agent.failed":
            return True
    return False


def _as_paths(value: Path | list[Path] | None) -> list[Path]:
    if value is None:
        return []
    if isinstance(value, list):
        return [p for p in value if p]
    return [value]
