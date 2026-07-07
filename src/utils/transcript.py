"""Render a LangGraph chat thread to a readable markdown transcript.

Two pieces, deliberately split so the renderer is a pure, unit-testable
function and the I/O is a thin async reader:

* ``read_thread_messages`` — a LIGHTWEIGHT checkpoint reader. It opens the
  self-host SQLite checkpointer directly (``open_sqlite_checkpointer`` over the
  local ``state.db``) and pulls the persisted ``messages`` channel with a single
  ``aget_tuple``. It builds NO agent and constructs NO LLM client, so it needs
  no API key and does not import ``api.py`` (which would drag in the whole
  FastAPI app + agent construction). Honest limitation (Wave 11 A7): on a
  Postgres/hosted deployment the checkpoints live in Cloud SQL, not the local
  sqlite file — so bundle EXPORT is a self-host authoring tool.

* ``render_transcript`` — a pure function: a list of LangChain-style messages →
  markdown. The tool-call lines mirror the Activity dock's language ("called
  ``tool`` → one-line result") so the rendered file reads like the trajectory.

The renderer is duck-typed against the message objects (``.type``/``.content``/
``.tool_calls``/``.tool_call_id``) so tests can drive it with tiny stand-ins and
it does not depend on the concrete LangChain message classes.
"""

from __future__ import annotations

import re
from typing import Any, List, Optional


async def read_thread_messages(db_path: str, thread_id: str) -> List[Any]:
    """Persisted messages for one thread, read straight from the checkpoint.

    Returns the deserialized message objects (LangChain BaseMessage instances)
    in order, or ``[]`` when the thread has no checkpoint yet. No LLM, no agent.
    """
    from src.platform_engines.checkpointer import open_sqlite_checkpointer

    async with open_sqlite_checkpointer(db_path) as saver:
        config = {"configurable": {"thread_id": thread_id}}
        tup = await saver.aget_tuple(config)
        if not tup or not getattr(tup, "checkpoint", None):
            return []
        channel_values = tup.checkpoint.get("channel_values", {}) or {}
        messages = channel_values.get("messages") or []
        return list(messages)


def _msg_type(msg: Any) -> str:
    """Normalize a message's role: 'human' | 'ai' | 'tool' | 'system' | ''."""
    t = getattr(msg, "type", None)
    if t:
        return str(t)
    # Fallbacks for dict-shaped or minimally-stubbed messages.
    if isinstance(msg, dict):
        return str(msg.get("type") or msg.get("role") or "")
    return ""


def _text_content(msg: Any) -> str:
    content = getattr(msg, "content", None)
    if content is None and isinstance(msg, dict):
        content = msg.get("content")
    if isinstance(content, str):
        return content.strip()
    # LangChain can carry a list of content blocks; join their text parts.
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "\n".join(p for p in parts if p).strip()
    return "" if content is None else str(content).strip()


def _tool_calls(msg: Any) -> List[dict]:
    calls = getattr(msg, "tool_calls", None)
    if not calls and isinstance(msg, dict):
        calls = msg.get("tool_calls")
    out: List[dict] = []
    for c in calls or []:
        if isinstance(c, dict):
            out.append({"name": c.get("name", "tool"), "args": c.get("args", {}) or {}})
        else:  # object-shaped tool call
            out.append({
                "name": getattr(c, "name", "tool"),
                "args": getattr(c, "args", {}) or {},
            })
    return out


def _one_line(text: str, limit: int = 200) -> str:
    flat = " ".join(str(text or "").split())
    return (flat[: limit - 1] + "…") if len(flat) > limit else flat


def _summarize_result(content: Any, limit: int = 200) -> str:
    """A one-line summary of a tool result, mirroring the Activity card."""
    if content is None:
        return ""
    if isinstance(content, (dict, list)):
        import json

        try:
            content = json.dumps(content, default=str)
        except Exception:
            content = str(content)
    return _one_line(content, limit)


def _fmt_args(args: dict, limit: int = 120) -> str:
    if not args:
        return ""
    parts = []
    for k, v in args.items():
        vs = _one_line(v, 60)
        parts.append(f"{k}={vs}")
    return _one_line(", ".join(parts), limit)


def render_transcript(
    messages: List[Any],
    *,
    title: str,
    template_name: Optional[str] = None,
    redact_paths: Optional[List[str]] = None,
) -> str:
    """Render messages → markdown. Pure (no I/O), so it is fully unit-testable.

    User and assistant turns become sections; each assistant tool call becomes a
    bullet with its arguments and a one-line result summary, so the file reads
    like the run trajectory a human (or the fork's own agent) can follow.

    ``redact_paths`` (used by bundle export) scrubs the author's absolute host
    paths from the rendered markdown — a tool result echoed into the transcript
    can carry ``C:\\Users\\<name>\\…`` and a PUBLIC bundle must not ship it.
    """
    # Index tool results by call id so each result attaches under its call.
    results_by_id: dict[str, Any] = {}
    for msg in messages:
        if _msg_type(msg) == "tool":
            cid = getattr(msg, "tool_call_id", None)
            if cid is None and isinstance(msg, dict):
                cid = msg.get("tool_call_id")
            if cid is not None:
                results_by_id[cid] = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")

    lines: List[str] = [f"# {title}", ""]
    if template_name:
        lines.append(f"> Conversation transcript from the **{template_name}** example.")
        lines.append("")

    rendered_any = False
    for msg in messages:
        mtype = _msg_type(msg)
        if mtype == "system" or mtype == "tool":
            continue  # system prompt is noise; tool results render under their call
        if mtype == "human":
            body = _text_content(msg)
            if not body:
                continue
            lines.append("## User")
            lines.append("")
            lines.append(body)
            lines.append("")
            rendered_any = True
        elif mtype == "ai":
            body = _text_content(msg)
            calls = _tool_calls(msg)
            if not body and not calls:
                continue
            lines.append("## Assistant")
            lines.append("")
            if body:
                lines.append(body)
                lines.append("")
            for call in calls:
                name = call["name"]
                argstr = _fmt_args(call["args"])
                header = f"- 🛠 `{name}`"
                if argstr:
                    header += f" ({argstr})"
                lines.append(header)
                # Attach the matching result summary (by any of this msg's ids).
                cid = None
                raw_calls = getattr(msg, "tool_calls", None) or (
                    msg.get("tool_calls") if isinstance(msg, dict) else None
                ) or []
                for rc in raw_calls:
                    rc_id = rc.get("id") if isinstance(rc, dict) else getattr(rc, "id", None)
                    if rc_id in results_by_id:
                        cid = rc_id
                        break
                if cid is not None:
                    summary = _summarize_result(results_by_id[cid])
                    if summary:
                        lines.append(f"  - → {summary}")
            lines.append("")
            rendered_any = True

    if not rendered_any:
        lines.append("_(no conversation recorded)_")
        lines.append("")

    result = "\n".join(lines).rstrip() + "\n"
    if redact_paths:
        from src.utils.bundles import redact_host_paths

        result = redact_host_paths(result, redact_paths)
    return result


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str, *, fallback: str = "chat", limit: int = 40) -> str:
    """Filesystem-safe kebab slug for a conversation filename."""
    slug = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    slug = slug[:limit].strip("-")
    return slug or fallback
