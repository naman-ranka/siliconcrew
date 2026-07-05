"""Agent-runtime registry — the shell-side seam extensions plug into.

The app has ONE native agent runtime (LangChain/LangGraph). Additional runtimes
(e.g. Codex) are *extensions*: they register a handler here and own a per-thread
``runtime`` marker. The chat shell dispatches a turn through this registry —
falling through to the untouched native path whenever the thread resolves to the
native runtime.

Design invariants (see plans/codex-runtime-extension.md):

- **Native is the default, never an extension.** ``NATIVE_RUNTIME`` is never
  registered; ``handler_for(NATIVE_RUNTIME)`` is always ``None`` so the caller
  runs the existing LangChain block unchanged.
- **Ships empty → removability is the default state.** With zero extensions
  registered, every turn resolves to native and dispatch is a no-op. "Remove the
  Codex extension" literally means "an empty registry" — the shipped default.
- **Graceful degradation.** A thread carrying ``runtime="codex"`` when Codex is
  disabled/removed resolves to native rather than erroring — stale rows degrade,
  they don't break.
- **One-way dependency rule.** This shared module imports NOTHING from any
  extension (no ``import`` of codex/etc.). Enforced by an import-graph test. The
  presentation contract below is a *rendering format both emit*, not an execution
  abstraction the native path must conform to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, runtime_checkable

# The native, always-present runtime. Never registered as an extension; it is the
# fallthrough the chat shell runs when a turn does not resolve to an extension.
NATIVE_RUNTIME = "langchain"


# ---------------------------------------------------------------------------
# Presentation contract — the thin rendered-turn vocabulary both runtimes emit.
# A runtime translates its native stream INTO these; the shell maps each to a
# WebSocket frame. This is intentionally the SAME frame vocabulary the native
# chat path already sends, so the shared bubble/tool-call UI renders both.
# ---------------------------------------------------------------------------

# Frame ``type`` values the shell/UI understands. Kept as plain strings (not an
# enum) to match the existing WS frame shape exactly.
EVENT_START = "start"
EVENT_TEXT = "text"
EVENT_TEXT_DELTA = "text_delta"
EVENT_TOOL_CALL = "tool_call"
EVENT_TOOL_RESULT = "tool_result"
EVENT_DONE = "done"
EVENT_STOPPED = "stopped"
EVENT_ERROR = "error"


@dataclass
class RuntimeEvent:
    """One rendered-turn event. ``to_frame()`` is the wire form (a WS JSON frame).

    Builders cover the shared vocabulary; a runtime is free to attach extra
    fields via ``data`` — the shell forwards them verbatim.
    """

    type: str
    data: Dict[str, Any] = field(default_factory=dict)

    def to_frame(self) -> Dict[str, Any]:
        return {"type": self.type, **self.data}

    # -- builders (the shared vocabulary) --
    @classmethod
    def start(cls) -> "RuntimeEvent":
        return cls(EVENT_START)

    @classmethod
    def text(cls, content: str) -> "RuntimeEvent":
        return cls(EVENT_TEXT, {"content": content})

    @classmethod
    def text_delta(cls, content: str) -> "RuntimeEvent":
        return cls(EVENT_TEXT_DELTA, {"content": content})

    @classmethod
    def tool_call(cls, tool: Any) -> "RuntimeEvent":
        return cls(EVENT_TOOL_CALL, {"tool": tool})

    @classmethod
    def tool_result(cls, tool_call_id: str, **result: Any) -> "RuntimeEvent":
        return cls(EVENT_TOOL_RESULT, {"tool_call_id": tool_call_id, **result})

    @classmethod
    def done(cls, tokens: Optional[Dict[str, int]] = None) -> "RuntimeEvent":
        return cls(EVENT_DONE, {"tokens": tokens or {"input": 0, "output": 0}})

    @classmethod
    def stopped(cls, tokens: Optional[Dict[str, int]] = None) -> "RuntimeEvent":
        return cls(EVENT_STOPPED, {"tokens": tokens or {"input": 0, "output": 0}})

    @classmethod
    def error(cls, message: str, code: Optional[str] = None) -> "RuntimeEvent":
        data: Dict[str, Any] = {"error": message}
        if code:
            data["code"] = code
        return cls(EVENT_ERROR, data)


@dataclass
class RuntimeTurnContext:
    """Everything an extension needs to run one turn, decoupled from the socket.

    ``send`` writes one already-``turn_id``-stamped frame to the client (the
    shell owns the actual WebSocket and single-writer semantics). ``emit`` is the
    presentation-contract convenience over it.
    """

    message: str
    turn_id: str
    thread_id: str
    session_id: str
    workspace: str
    send: Callable[[Dict[str, Any]], Awaitable[None]]
    user_id: Optional[str] = None
    thread_row: Optional[Dict[str, Any]] = None

    async def emit(self, event: RuntimeEvent) -> None:
        await self.send(event.to_frame())


@runtime_checkable
class RuntimeHandler(Protocol):
    """An extension runtime. Owns its own turn lifecycle end-to-end."""

    async def run_turn(self, ctx: RuntimeTurnContext) -> None: ...


@dataclass(frozen=True)
class RuntimeDescriptor:
    """UI-facing identity of a runtime (for the switcher / capability list)."""

    id: str
    display_name: str


# The native runtime's UI identity. Present in ``available_runtimes()`` even with
# zero extensions, so the switcher always has the default occupant to show.
NATIVE_DESCRIPTOR = RuntimeDescriptor(id=NATIVE_RUNTIME, display_name="Workbench")


# ---------------------------------------------------------------------------
# Registry state + API
# ---------------------------------------------------------------------------

_HANDLERS: Dict[str, RuntimeHandler] = {}
_DESCRIPTORS: Dict[str, RuntimeDescriptor] = {}


def register_runtime(descriptor: RuntimeDescriptor, handler: RuntimeHandler) -> None:
    """Register an extension runtime. Called by an extension's own setup (gated by
    its feature flag), never by the shared layer itself.

    Rejects the native id (native is the fallthrough, not an extension) and
    double-registration (a duplicate id is a wiring bug, not a silent override).
    """
    if descriptor.id == NATIVE_RUNTIME:
        raise ValueError(
            f"'{NATIVE_RUNTIME}' is the native runtime and cannot be registered as an extension"
        )
    if descriptor.id in _HANDLERS:
        raise ValueError(f"runtime '{descriptor.id}' is already registered")
    if not hasattr(handler, "run_turn"):
        raise TypeError(f"handler for '{descriptor.id}' must define async run_turn(ctx)")
    _HANDLERS[descriptor.id] = handler
    _DESCRIPTORS[descriptor.id] = descriptor


def unregister_runtime(runtime_id: str) -> None:
    """Remove an extension (idempotent). The removability seam — and a test hook."""
    _HANDLERS.pop(runtime_id, None)
    _DESCRIPTORS.pop(runtime_id, None)


def clear_extensions() -> None:
    """Drop all registered extensions — back to native-only (test hook)."""
    _HANDLERS.clear()
    _DESCRIPTORS.clear()


def is_registered(runtime_id: str) -> bool:
    return runtime_id in _HANDLERS


def available_runtimes() -> List[RuntimeDescriptor]:
    """Native descriptor first, then registered extensions in registration order.

    Drives the frontend switcher / ``codexEnabled``-style capability list.
    """
    return [NATIVE_DESCRIPTOR, *_DESCRIPTORS.values()]


def resolve_runtime(thread_row: Optional[Dict[str, Any]]) -> str:
    """The runtime id a thread should run under.

    Returns the thread's ``runtime`` marker only when it names a *registered*
    extension; otherwise native. So an absent marker (today's threads), the
    native id, an unknown id, or a marker for a disabled/removed extension all
    resolve to native — the graceful-degradation invariant.
    """
    if not thread_row:
        return NATIVE_RUNTIME
    marker = thread_row.get("runtime")
    if marker and marker != NATIVE_RUNTIME and marker in _HANDLERS:
        return marker
    return NATIVE_RUNTIME


def handler_for(runtime_id: str) -> Optional[RuntimeHandler]:
    """The extension handler for ``runtime_id``, or ``None`` for native/unknown.

    ``None`` is the signal to the chat shell: run the existing LangChain block
    unchanged. With zero extensions registered this is always ``None``.
    """
    return _HANDLERS.get(runtime_id)
