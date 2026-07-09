"""F6: blocking I/O runs off the event loop, so one slow request can't stall others.

Before this fix the workspace GET handlers hydrated (GCS download+untar), listed,
read files, and parsed VCDs directly on the async loop — one slow hydration
blocked *every* in-flight request. These tests fire two concurrent requests whose
work blocks; if the blocking part is offloaded (asyncio.to_thread) they overlap
(~T), if it ran on the loop they'd serialize (~2T).
"""
import asyncio
import os
import time

import pytest

pytest.importorskip("fastapi")
import httpx
from httpx import ASGITransport
from fastapi import FastAPI

from src.api.actions import build_actions_router

SLOW = 0.4  # per-request blocking hydration


async def _two_concurrent(app, path):
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        t0 = time.perf_counter()
        rs = await asyncio.gather(c.get(path), c.get(path))
        return time.perf_counter() - t0, rs


def test_slow_workspace_resolve_does_not_stall_concurrent_actions_request(tmp_path):
    """The action router resolves the workspace (a blocking hydration) off-thread,
    so two concurrent reads overlap instead of serializing on the loop."""

    def resolve(session_id: str) -> str:
        time.sleep(SLOW)  # simulate the GCS download+untar hydration
        ws = os.path.join(str(tmp_path), session_id)
        os.makedirs(ws, exist_ok=True)
        return ws

    app = FastAPI()
    app.include_router(build_actions_router(resolve))

    dt, rs = asyncio.run(_two_concurrent(app, "/api/workspace/s/runs"))
    assert all(r.status_code == 200 for r in rs), [r.status_code for r in rs]
    # Overlapped off-thread (~SLOW), not serialized on the loop (~2*SLOW).
    assert dt < SLOW * 1.8, f"requests serialized on the event loop: {dt:.2f}s"


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("langchain_core") is None,
    reason="api.py pulls the agent stack (langchain_core) — runs in CI",
)
def test_slow_hydration_does_not_stall_concurrent_api_get(tmp_path):
    """The api.py workspace GET handlers offload hydration+listdir off-thread."""
    import api
    from src.platform_engines.workspace_provider import set_workspace_provider

    (tmp_path / "wave.vcd").write_text("")  # dir exists → 200, not 404

    class SlowProvider:
        def workspace_for(self, session_id: str) -> str:
            time.sleep(SLOW)
            return str(tmp_path)

        def sync(self, session_id: str) -> None:
            pass

    set_workspace_provider(SlowProvider())
    api.app.dependency_overrides[api.verify_session_access] = lambda: None
    try:
        dt, rs = asyncio.run(_two_concurrent(api.app, "/api/workspace/s/waveforms"))
    finally:
        api.app.dependency_overrides.clear()
        set_workspace_provider(None)

    assert all(r.status_code == 200 for r in rs), [r.status_code for r in rs]
    assert dt < SLOW * 1.8, f"a slow hydration serialized concurrent requests: {dt:.2f}s"
