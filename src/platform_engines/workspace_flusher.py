"""Write-behind workspace flusher — continuous durability for agent turns.

The data-loss incident this exists for: an agent turn's workspace writes were
batched into ONE fire-and-forget turn-end sync, so an instance drain mid-turn
(deploy, scale-down, crash) lost the entire turn's files while the synthesis
Cloud Run Job survived (it writes to ``orfs-runs/…`` independently). Since 4A
made ``CloudWorkspaceProvider.sync`` incremental — cost proportional to what
changed, manifest-written-last as the atomic commit point — the latency reason
for batching is gone. This module changes only WHEN sync fires, never how.

Mechanism: agent code marks a session dirty at every tool boundary
(``mark_dirty`` / ``note_agent_frame``); one daemon worker thread runs
``provider.sync(session_id)`` with leading-edge-plus-cooldown scheduling —
the first mark after an idle period flushes ~immediately (minimal exposure
window), marks inside the cooldown coalesce into one trailing flush. The
cooldown adapts to the workspace: ``max(base, 2 × last sync duration)``, so a
run-heavy scratch whose scan/upload is slow backs off automatically.

Crash-only by design: durability does not depend on graceful shutdown. The
lifespan drain (``flush_all``) is belt-and-braces; a SIGKILL mid-flush leaves
the previous consistent manifest (provider guarantee) and loses at most
~one cooldown window of writes instead of a whole turn.

Self-host: ``LocalWorkspaceProvider`` has no ``sync`` — a flush resolves the
provider lazily, finds no ``sync``, and is a no-op. Call sites stay
unconditional one-liners; no cloud import ever happens here.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Dict, Optional

# WS frame types that mean "the agent crossed a tool boundary" — by then the
# tool's writes (and the attempt-log append every tool call makes) are on
# local scratch and should head to durable storage.
_AGENT_ACTIVITY_FRAME_TYPES = ("tool_call", "tool_result")


class WorkspaceFlusher:
    """Debounced per-session write-behind flushing over ``provider.sync``.

    Thread-based on purpose: ``sync`` is blocking network I/O and must never
    run on the event loop (same reason api.py used ``asyncio.to_thread``), and
    a plain daemon thread works identically under uvicorn and in tests.
    Concurrent flushes against other sync callers are safe — the provider
    holds a per-session lock and commits via content-addressed blobs with the
    manifest written last.
    """

    def __init__(
        self,
        provider_resolver: Optional[Callable[[], object]] = None,
        base_cooldown_sec: float = 2.0,
        retry_base_sec: float = 2.0,
        retry_max_sec: float = 30.0,
    ) -> None:
        # Resolved lazily PER FLUSH (never frozen at construction): the active
        # provider is swappable via set_workspace_provider, and tests inject
        # fakes — a singleton bound at build time would go permanently no-op
        # depending on import order.
        self._provider_resolver = provider_resolver
        self._base_cooldown = base_cooldown_sec
        self._retry_base = retry_base_sec
        self._retry_max = retry_max_sec
        # Idle entries (clean, no flush in a long while) are pruned so the
        # state map stays bounded on long-lived instances.
        self._idle_prune_sec = 600.0

        self._cond = threading.Condition()
        # session_id -> state dict; existence == "the flusher tracks this
        # session". Keys: dirty, due (monotonic), last_start, last_duration,
        # fail_streak, in_flight, discarded.
        self._state: Dict[str, dict] = {}
        self._worker: Optional[threading.Thread] = None
        self._closed = False

    # -- provider seam --------------------------------------------------------

    def _resolve_sync(self) -> Optional[Callable[[str], None]]:
        if self._provider_resolver is not None:
            provider = self._provider_resolver()
        else:
            from src.platform_engines.workspace_provider import get_workspace_provider

            provider = get_workspace_provider()
        fn = getattr(provider, "sync", None)
        return fn if callable(fn) else None

    # -- marking --------------------------------------------------------------

    def mark_dirty(self, session_id: str) -> None:
        """Record that ``session_id`` has unsynced local writes. O(1), never
        blocks on I/O — safe on the WS hot path."""
        self._schedule(session_id, immediate=False)

    def flush_soon(self, session_id: str) -> None:
        """Mark + wake now (skip the cooldown wait) — the turn-end flush."""
        self._schedule(session_id, immediate=True)

    def note_agent_frame(self, session_id: str, frame: object) -> None:
        """Mark dirty when a turn frame represents a tool boundary."""
        if isinstance(frame, dict) and frame.get("type") in _AGENT_ACTIVITY_FRAME_TYPES:
            self.mark_dirty(session_id)

    def _schedule(self, session_id: str, immediate: bool) -> None:
        now = time.monotonic()
        with self._cond:
            if self._closed:
                return
            st = self._state.setdefault(session_id, {
                "dirty": False, "due": now, "last_start": None,
                "last_duration": 0.0, "fail_streak": 0,
                "in_flight": False, "discarded": False,
            })
            st["discarded"] = False  # a fresh mark un-discards (session is live)
            was_dirty = st["dirty"]
            st["dirty"] = True
            if immediate or st["last_start"] is None:
                desired = now  # leading edge: first mark after idle flushes at once
            else:
                cooldown = max(self._base_cooldown, 2.0 * st["last_duration"])
                desired = max(now, st["last_start"] + cooldown)
            if was_dirty:
                if st["fail_streak"] and not immediate:
                    # A pending RETRY due embodies the backoff after a store
                    # failure — an ordinary mark must not pull it earlier, or
                    # an active turn hammers a failing store every cooldown
                    # and the 2s→30s escalation never engages. flush_soon /
                    # flush_now (immediate) stay deliberate overrides.
                    pass
                else:
                    # An already-pending earlier due wins.
                    st["due"] = min(st["due"], desired)
            else:
                # A stale due from a past clean cycle must not defeat the
                # cooldown — take the freshly computed one.
                st["due"] = desired
            self._ensure_worker()
            self._cond.notify_all()

    def discard(self, session_id: str) -> None:
        """Forget a session (it was deleted): drop its dirty state and stop
        retrying. An in-flight sync may still complete; the provider's
        missing-scratch guard prevents it from resurrecting the manifest."""
        with self._cond:
            st = self._state.get(session_id)
            if st is None:
                return
            if st["in_flight"]:
                st["dirty"] = False
                st["discarded"] = True
            else:
                del self._state[session_id]
            self._cond.notify_all()

    # -- draining -------------------------------------------------------------

    def flush_now(self, session_id: str, timeout: float = 30.0) -> bool:
        """Force a flush and wait for the session to be clean. True on clean."""
        deadline = time.monotonic() + timeout
        with self._cond:
            st = self._state.get(session_id)
            if st is None or (not st["dirty"] and not st["in_flight"]):
                return True
            st["due"] = time.monotonic()
            self._ensure_worker()
            self._cond.notify_all()
            while True:
                st = self._state.get(session_id)
                if st is None or (not st["dirty"] and not st["in_flight"]):
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._cond.wait(remaining)

    def flush_all(self, timeout: float = 5.0) -> Dict[str, bool]:
        """Drain every dirty session (shutdown belt-and-braces). Returns
        session_id -> flushed-clean; callers log the False ones honestly."""
        deadline = time.monotonic() + timeout
        with self._cond:
            targets = [
                sid for sid, st in self._state.items() if st["dirty"] or st["in_flight"]
            ]
            now = time.monotonic()
            for sid in targets:
                self._state[sid]["due"] = now
            if targets:
                self._ensure_worker()
                self._cond.notify_all()
        results: Dict[str, bool] = {}
        for sid in targets:
            remaining = max(0.0, deadline - time.monotonic())
            results[sid] = self.flush_now(sid, timeout=remaining)
        return results

    def close(self) -> None:
        """Stop accepting marks and let the worker exit (tests)."""
        with self._cond:
            self._closed = True
            self._cond.notify_all()
        worker = self._worker
        if worker is not None:
            worker.join(timeout=5.0)

    # -- worker ---------------------------------------------------------------

    def _ensure_worker(self) -> None:
        # Under self._cond. Restart if a previous worker died (defensive).
        if self._worker is None or not self._worker.is_alive():
            self._worker = threading.Thread(
                target=self._run, name="workspace-flusher", daemon=True
            )
            self._worker.start()

    def _next_due(self) -> Optional[str]:
        # Under self._cond: the dirty, not-in-flight session with min due.
        best_sid, best_due = None, None
        for sid, st in self._state.items():
            if st["dirty"] and not st["in_flight"]:
                if best_due is None or st["due"] < best_due:
                    best_sid, best_due = sid, st["due"]
        return best_sid

    def _run(self) -> None:
        while True:
            with self._cond:
                while True:
                    if self._closed:
                        return
                    sid = self._next_due()
                    if sid is None:
                        self._cond.wait()
                        continue
                    delay = self._state[sid]["due"] - time.monotonic()
                    if delay <= 0:
                        break
                    self._cond.wait(delay)
                st = self._state[sid]
                st["in_flight"] = True
                st["dirty"] = False  # a mark landing during the sync re-dirties
                st["last_start"] = time.monotonic()

            start = time.monotonic()
            error: Optional[BaseException] = None
            try:
                sync_fn = self._resolve_sync()
                if sync_fn is not None:
                    sync_fn(sid)
            except BaseException as exc:  # the worker must survive anything
                error = exc

            warn: Optional[str] = None
            with self._cond:
                st = self._state.get(sid)
                if st is None:
                    self._cond.notify_all()
                    continue
                st["in_flight"] = False
                st["last_duration"] = time.monotonic() - start
                if st["discarded"]:
                    del self._state[sid]
                elif error is not None:
                    # Never drop writes silently: stay dirty, retry with capped
                    # backoff so a transient GCS error self-heals.
                    st["fail_streak"] += 1
                    backoff = min(
                        self._retry_max,
                        self._retry_base * (2 ** min(st["fail_streak"] - 1, 6)),
                    )
                    st["dirty"] = True
                    st["due"] = time.monotonic() + backoff
                    warn = (
                        f"[WARN] workspace flush failed for '{sid}' "
                        f"(attempt {st['fail_streak']}, retry in {backoff:.0f}s): {error}"
                    )
                else:
                    st["fail_streak"] = 0
                # Bound _state: drop entries idle past the prune horizon
                # (clean, not in flight, last sync long ago). Covers the
                # deleted-then-late-marked session whose entry would
                # otherwise linger forever; for a live-but-quiet session the
                # loss is only cached cooldown stats, and its next mark is
                # leading-edge (immediate flush) anyway.
                horizon = time.monotonic() - self._idle_prune_sec
                for other, ost in list(self._state.items()):
                    if (
                        not ost["dirty"] and not ost["in_flight"]
                        and ost["last_start"] is not None
                        and ost["last_start"] < horizon
                    ):
                        del self._state[other]
                self._cond.notify_all()
            if warn:
                # Outside the lock: stdout can be a slow pipe and must never
                # stall mark_dirty on the WS hot path.
                print(warn)


# ---------------------------------------------------------------------------
# Process-wide singleton (mirrors get_workspace_provider's idiom).
# ---------------------------------------------------------------------------

_FLUSHER: Optional[WorkspaceFlusher] = None
_FLUSHER_GUARD = threading.Lock()


def get_workspace_flusher() -> WorkspaceFlusher:
    """The process-wide flusher. Provider is resolved lazily per flush, so
    building this early can never freeze a stale/no-op provider in."""
    global _FLUSHER
    if _FLUSHER is None:
        with _FLUSHER_GUARD:
            if _FLUSHER is None:
                _FLUSHER = WorkspaceFlusher()
    return _FLUSHER


def set_workspace_flusher(flusher: Optional[WorkspaceFlusher]) -> None:
    """Override/reset the process-wide flusher (tests)."""
    global _FLUSHER
    with _FLUSHER_GUARD:
        old, _FLUSHER = _FLUSHER, flusher
    if old is not None and old is not flusher:
        old.close()
