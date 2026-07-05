"""Agent-runtime registry — dispatch, removability, and the dependency rule.

Phase 1 of the Codex-as-extension work (plans/codex-runtime-extension.md). These
lock in the seam BEFORE any real Codex wiring: an extension can register and
receive turns; native is always the fallthrough; removing the extension returns
the app to native-only; and the shared registry never imports an extension.
"""
import ast
import asyncio
import os

import pytest

from src.agents import runtime_registry as rr
from src.agents.runtime_registry import (
    NATIVE_RUNTIME,
    RuntimeDescriptor,
    RuntimeEvent,
    RuntimeTurnContext,
)


# A stand-in extension (models Codex's shape) defined OUTSIDE the shared layer —
# proving a runtime can register from the outside and receive a turn.
class _StubRuntime:
    def __init__(self):
        self.turns = []

    async def run_turn(self, ctx: RuntimeTurnContext) -> None:
        self.turns.append(ctx)
        await ctx.emit(RuntimeEvent.start())
        await ctx.emit(RuntimeEvent.text(f"stub saw: {ctx.message}"))
        await ctx.emit(RuntimeEvent.done({"input": 0, "output": 0}))


STUB = RuntimeDescriptor(id="stub", display_name="Stub")


@pytest.fixture(autouse=True)
def clean_registry():
    """Every test starts and ends native-only (ships-empty is the default)."""
    rr.clear_extensions()
    yield
    rr.clear_extensions()


def _make_ctx(message="hi", thread_row=None):
    sent = []

    async def _send(frame):
        sent.append(frame)

    ctx = RuntimeTurnContext(
        message=message, turn_id="t1", thread_id="th1", session_id="s1",
        workspace="/ws", send=_send, user_id="alice", thread_row=thread_row,
    )
    return ctx, sent


# --- ships empty: native-only, dispatch is a no-op -------------------------

def test_ships_empty_native_only():
    assert rr.available_runtimes() == [rr.NATIVE_DESCRIPTOR]
    # Any thread — no marker, native marker, or an unknown one — is native, and
    # native has no extension handler, so the shell falls through.
    for row in (None, {}, {"runtime": NATIVE_RUNTIME}, {"runtime": "codex"}):
        assert rr.resolve_runtime(row) == NATIVE_RUNTIME
        assert rr.handler_for(rr.resolve_runtime(row)) is None


# --- registration + dispatch ------------------------------------------------

def test_register_then_resolve_and_dispatch():
    stub = _StubRuntime()
    rr.register_runtime(STUB, stub)

    assert rr.is_registered("stub")
    assert STUB in rr.available_runtimes()
    # A thread marked for the registered extension resolves + dispatches to it.
    assert rr.resolve_runtime({"runtime": "stub"}) == "stub"
    assert rr.handler_for("stub") is stub


def test_stub_turn_emits_presentation_frames():
    stub = _StubRuntime()
    rr.register_runtime(STUB, stub)

    ctx, sent = _make_ctx(message="hello", thread_row={"runtime": "stub"})
    handler = rr.handler_for(rr.resolve_runtime(ctx.thread_row))
    assert handler is stub
    asyncio.run(handler.run_turn(ctx))

    assert [f["type"] for f in sent] == ["start", "text", "done"]
    assert sent[1]["content"] == "stub saw: hello"
    assert stub.turns == [ctx]


# --- graceful degradation ---------------------------------------------------

def test_native_is_never_an_extension_handler():
    rr.register_runtime(STUB, _StubRuntime())
    # Even with an extension present, the native id has no handler → fallthrough.
    assert rr.handler_for(NATIVE_RUNTIME) is None


def test_unknown_or_disabled_marker_degrades_to_native():
    rr.register_runtime(STUB, _StubRuntime())
    # A marker for a runtime that is NOT registered (disabled/removed) degrades.
    assert rr.resolve_runtime({"runtime": "codex"}) == NATIVE_RUNTIME
    assert rr.handler_for(rr.resolve_runtime({"runtime": "codex"})) is None


# --- removability -----------------------------------------------------------

def test_unregister_returns_to_native():
    stub = _StubRuntime()
    rr.register_runtime(STUB, stub)
    assert rr.resolve_runtime({"runtime": "stub"}) == "stub"

    rr.unregister_runtime("stub")
    # The exact "remove Codex" state: the marked thread now degrades to native.
    assert rr.resolve_runtime({"runtime": "stub"}) == NATIVE_RUNTIME
    assert rr.handler_for("stub") is None
    assert rr.available_runtimes() == [rr.NATIVE_DESCRIPTOR]


def test_unregister_is_idempotent():
    rr.unregister_runtime("never-registered")  # no raise


# --- wiring guards ----------------------------------------------------------

def test_cannot_register_native_id():
    with pytest.raises(ValueError):
        rr.register_runtime(RuntimeDescriptor(id=NATIVE_RUNTIME, display_name="x"), _StubRuntime())


def test_double_registration_rejected():
    rr.register_runtime(STUB, _StubRuntime())
    with pytest.raises(ValueError):
        rr.register_runtime(STUB, _StubRuntime())


def test_handler_must_define_run_turn():
    class NotAHandler:
        pass

    with pytest.raises(TypeError):
        rr.register_runtime(RuntimeDescriptor(id="bad", display_name="bad"), NotAHandler())


# --- the one-way dependency rule (removability at the source level) ---------

# Substrings that must never appear as an import target in the shared registry.
# The registry is the shell-side seam; if it ever imports an extension, deleting
# that extension would break the shared path — exactly what removability forbids.
_FORBIDDEN_IMPORT_MARKERS = ("codex", "runtime_adapters", ".extensions", "openai_codex")


def test_registry_imports_no_extension():
    src_path = os.path.join(os.path.dirname(rr.__file__), "runtime_registry.py")
    with open(src_path, "r", encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")

    offenders = [
        name for name in imported
        if any(marker in name for marker in _FORBIDDEN_IMPORT_MARKERS)
    ]
    assert offenders == [], f"shared registry imports an extension: {offenders}"
