"""Warm Codex worker pool — TTFT remediation (plans/codex-ttft-remediation.md).

A "worker" is one entered Codex SDK context (the app-server subprocess + its
bound SiliconCrew MCP child) plus the SDK thread object brought up for one chat
thread. Rebuilding all of that on every user turn was the measured ~8.5s bulk
of Codex time-to-first-token; this pool keeps a thread's worker alive across
turns (warm-keep, 3A) and lets the shell start one before the first message
(pre-warm, 3B).

Safety model — read before touching:

* **Tenant isolation by construction (invariant 8).** A worker is keyed by the
  full ``(session_id, thread_id, user_id)`` triple, and the SDK config it was
  spawned with was built from that same triple (``--bound-session``, per-user
  CODEX_HOME, the caller's MCP token). Lookups happen ONLY by the full key —
  there is no partial-key path, no cross-tenant pool, no late binding.
* **A worker is a cache, never truth (invariant 9).** Losing one (instance
  recycle, crash, eviction) costs exactly one honest re-cold-start. Nothing
  durable lives in it; transcripts/external ids persist via codex_store as
  before.
* **Loop-bound.** SDK transports belong to the event loop that created them; a
  worker is only ever reused on that loop. A different running loop (tests,
  embedding) drops the stale entries and rebinds.
* **One turn at a time.** ``turn_lock`` serializes turns per worker; a second
  concurrent turn queues behind the first — consistent with the shell's
  process-local supersede assumptions (X2A-7).
* **Retire on doubt.** Any abnormal turn end (SDK error, cancellation) closes
  the worker; the next turn cold-starts honestly rather than reusing a worker
  in an unknown stream state.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple

WorkerKey = Tuple[str, str, str]  # (session_id, thread_id, user_id or "")

# Worker states surfaced to the UI (3C). "unavailable" is reported by callers
# when there is no pool at all (warm-keep disabled / runtime has no key).
STATE_READY = "ready"
STATE_STARTING = "starting"
STATE_COLD = "cold"
STATE_UNAVAILABLE = "unavailable"


def worker_fingerprint(*, api_key: Optional[str], account_home: Optional[str],
                       sandbox: Optional[str], system_prompt: Optional[str]) -> str:
    """What must match for a warm worker to be reusable, beyond its key.

    Auth material (BYOK key / connected-account home) and spawn-time thread
    config (sandbox, base instructions) are baked into the worker at spawn; a
    change in any of them retires the worker instead of reusing it. The raw
    bearer token is deliberately EXCLUDED: it rotates per connection while the
    verified identity it proves is already part of the worker key.
    """
    digest = hashlib.sha256()
    for part in (api_key or "", account_home or "", sandbox or "", system_prompt or ""):
        digest.update(part.encode("utf-8", "replace"))
        digest.update(b"\x00")
    return digest.hexdigest()


@dataclass
class WarmWorker:
    key: WorkerKey
    fingerprint: str
    cm: Any                    # the SDK async context manager (owns the subprocess)
    client: Any                # the entered SDK client
    thread: Any                # the SDK thread (resumed/started once, at spawn)
    external_thread_id: str
    loop: asyncio.AbstractEventLoop
    turn_lock: asyncio.Lock
    last_used: float = field(default_factory=time.monotonic)
    closed: bool = False

    async def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        try:
            await self.cm.__aexit__(None, None, None)
        except Exception:
            pass  # teardown is best-effort; the subprocess dies with the context


class _Entry:
    """One pool slot: a spawn task (possibly still running) + its fingerprint."""

    def __init__(self, fingerprint: str, task: "asyncio.Task[WarmWorker]"):
        self.fingerprint = fingerprint
        self.task = task

    def worker(self) -> Optional[WarmWorker]:
        if self.task.done() and not self.task.cancelled() and self.task.exception() is None:
            return self.task.result()
        return None


class CodexWorkerPool:
    """Per-process pool of warm Codex workers, keyed by (session, thread, user).

    Soft-capped: when at capacity the least-recently-used idle worker is
    evicted before a new spawn; busy (mid-turn) workers are never evicted, so
    the true bound is cap + concurrently-active turns — both small on one
    instance. Idle workers are reaped by a lazy janitor task.
    """

    def __init__(self, *, max_workers: Optional[int] = None, idle_sec: Optional[float] = None):
        self.max_workers = max_workers if max_workers is not None else int(
            os.environ.get("CODEX_WARM_MAX", "3"))
        self.idle_sec = idle_sec if idle_sec is not None else float(
            os.environ.get("CODEX_WARM_IDLE_SEC", "900"))
        self._entries: Dict[WorkerKey, _Entry] = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._guard: Optional[asyncio.Lock] = None
        self._janitor: Optional[asyncio.Task] = None

    # -- loop binding ---------------------------------------------------------

    def _bind_loop(self) -> None:
        loop = asyncio.get_running_loop()
        if self._loop is not loop:
            # A different loop (tests / embedding): the old loop's workers are
            # unusable transports. Drop the references — if the old loop is
            # gone their subprocesses died with it; if it's alive the janitor
            # there can no longer run, so this is the correctness-safe choice.
            self._entries.clear()
            self._guard = asyncio.Lock()
            self._loop = loop
            self._janitor = None

    def _ensure_janitor(self) -> None:
        if self.idle_sec <= 0:
            return
        if self._janitor is None or self._janitor.done():
            self._janitor = asyncio.get_running_loop().create_task(self._janitor_loop())

    async def _janitor_loop(self) -> None:
        interval = max(0.05, min(60.0, self.idle_sec / 4))
        while True:
            await asyncio.sleep(interval)
            now = time.monotonic()
            stale: list[WarmWorker] = []
            assert self._guard is not None
            async with self._guard:
                for key, entry in list(self._entries.items()):
                    w = entry.worker()
                    if w is not None and not w.turn_lock.locked() and now - w.last_used > self.idle_sec:
                        self._entries.pop(key, None)
                        stale.append(w)
            for w in stale:
                await w.close()

    # -- capacity --------------------------------------------------------------

    async def _evict_for_capacity(self, new_key: WorkerKey) -> None:
        assert self._guard is not None
        victims: list[WarmWorker] = []
        async with self._guard:
            while len(self._entries) > max(0, self.max_workers - 1):
                idle = [
                    (entry.worker().last_used, key, entry.worker())  # type: ignore[union-attr]
                    for key, entry in self._entries.items()
                    if key != new_key and entry.worker() is not None
                    and not entry.worker().turn_lock.locked()  # type: ignore[union-attr]
                ]
                if not idle:
                    break  # only busy/pending workers left — soft cap, spawn anyway
                idle.sort()
                _, key, w = idle[0]
                self._entries.pop(key, None)
                victims.append(w)
        for w in victims:
            await w.close()

    # -- the public surface ----------------------------------------------------

    async def acquire(
        self,
        key: WorkerKey,
        fingerprint: str,
        spawn: Callable[[], Awaitable[Dict[str, Any]]],
        expected_external: Optional[str] = None,
    ) -> WarmWorker:
        """A live worker for ``key`` — reused when warm, spawned when not.

        Concurrent acquires (and a pre-warm racing a first send) coalesce onto
        one spawn. ``expected_external`` guards against a stale worker whose
        SDK thread no longer matches the persisted external thread id.
        """
        self._bind_loop()
        self._ensure_janitor()
        assert self._guard is not None
        for _ in range(4):  # bounded revalidation (fingerprint churn is rare)
            stale: Optional[WarmWorker] = None
            async with self._guard:
                entry = self._entries.get(key)
                if entry is not None and entry.task.done():
                    w = entry.worker()
                    reusable = (
                        w is not None
                        and not w.closed
                        and entry.fingerprint == fingerprint
                        and not (expected_external and w.external_thread_id
                                 and w.external_thread_id != expected_external)
                    )
                    if reusable:
                        w.last_used = time.monotonic()
                        return w  # type: ignore[return-value]
                    self._entries.pop(key, None)
                    stale = w
                    entry = None
                if entry is None:
                    entry = _Entry(fingerprint, asyncio.get_running_loop().create_task(
                        self._spawn(key, fingerprint, spawn)))
                    self._entries[key] = entry
            if stale is not None:
                await stale.close()
            try:
                worker = await asyncio.shield(entry.task)
            except Exception:
                async with self._guard:
                    if self._entries.get(key) is entry:
                        self._entries.pop(key, None)
                raise
            # Re-validate under the guard (a coalesced awaiter's fingerprint may
            # differ from the spawner's) — usually returns on the next pass.
            async with self._guard:
                if (self._entries.get(key) is entry and entry.fingerprint == fingerprint
                        and not worker.closed
                        and not (expected_external and worker.external_thread_id
                                 and worker.external_thread_id != expected_external)):
                    worker.last_used = time.monotonic()
                    return worker
        raise RuntimeError("codex warm pool: worker validation kept churning; giving up")

    async def _spawn(self, key: WorkerKey, fingerprint: str,
                     spawn: Callable[[], Awaitable[Dict[str, Any]]]) -> WarmWorker:
        await self._evict_for_capacity(key)
        t0 = time.monotonic()
        parts = await spawn()  # {"cm","client","thread","external_thread_id"}
        worker = WarmWorker(
            key=key, fingerprint=fingerprint, loop=asyncio.get_running_loop(),
            turn_lock=asyncio.Lock(), **parts,
        )
        print(
            f"[CODEX-TIMING] thread={key[1]} event=warm_worker_spawned "
            f"elapsed={time.monotonic() - t0:.2f}s pool_size={len(self._entries)}",
            file=sys.stderr,
        )
        return worker

    def ensure(self, key: WorkerKey, fingerprint: str,
               spawn: Callable[[], Awaitable[Dict[str, Any]]]) -> str:
        """Pre-warm (3B): make sure a worker exists or is being spawned for
        ``key`` WITHOUT waiting for it. Returns the resulting state. Must be
        called on the pool's event loop (the app loop)."""
        self._bind_loop()
        self._ensure_janitor()
        state = self.state_for(key)
        if state in (STATE_READY, STATE_STARTING):
            return state
        entry = _Entry(fingerprint, asyncio.get_running_loop().create_task(
            self._spawn_logged(key, fingerprint, spawn)))
        self._entries[key] = entry
        return STATE_STARTING

    async def _spawn_logged(self, key: WorkerKey, fingerprint: str,
                            spawn: Callable[[], Awaitable[Dict[str, Any]]]) -> WarmWorker:
        try:
            return await self._spawn(key, fingerprint, spawn)
        except BaseException as exc:
            # A failed pre-warm must clean up its slot so state reads "cold"
            # (honest) and the first real turn retries from scratch.
            self._entries.pop(key, None)
            print(f"[CODEX-TIMING] thread={key[1]} event=prewarm_failed error={exc}",
                  file=sys.stderr)
            raise

    def state_for(self, key: WorkerKey) -> str:
        """Honest worker state for the UI: ready | starting | cold."""
        entry = self._entries.get(key)
        if entry is None:
            return STATE_COLD
        if not entry.task.done():
            return STATE_STARTING
        w = entry.worker()
        if w is None or w.closed:
            return STATE_COLD
        return STATE_READY

    async def discard(self, key: WorkerKey, worker: Optional[WarmWorker]) -> None:
        """Retire a worker after an abnormal turn end (crash/cancel)."""
        assert self._guard is not None
        async with self._guard:
            entry = self._entries.get(key)
            if entry is not None and entry.task.done() and entry.worker() is worker:
                self._entries.pop(key, None)
        if worker is not None:
            await worker.close()

    async def close_thread(self, thread_id: str) -> None:
        """Tear down every worker for ``thread_id`` (thread/session delete)."""
        assert self._guard is not None or not self._entries
        if self._guard is None:
            return
        victims: list[WarmWorker] = []
        async with self._guard:
            for key in [k for k in self._entries if k[1] == thread_id]:
                entry = self._entries.pop(key)
                w = entry.worker()
                if w is not None:
                    victims.append(w)
                else:
                    entry.task.cancel()
        for w in victims:
            await w.close()

    def close_thread_sync(self, thread_id: str) -> None:
        """Loop-safe bridge for the (sync) runtime-registry cleanup hook."""
        loop = self._loop
        if loop is None or loop.is_closed():
            self._entries = {k: v for k, v in self._entries.items() if k[1] != thread_id}
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            loop.create_task(self.close_thread(thread_id))
        else:
            asyncio.run_coroutine_threadsafe(self.close_thread(thread_id), loop)
