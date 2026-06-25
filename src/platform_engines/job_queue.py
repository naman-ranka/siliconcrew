"""Per-user job queue — replaces the process-global ThreadPoolExecutor.

The synthesis manager today submits jobs to one shared
``ThreadPoolExecutor(max_workers=2)``. Under multi-tenancy that lets one user's
backlog starve everyone else and ignores per-user concurrency. This queue:

  * serializes a user's jobs (``per_user_limit``, default 1 — matches the synth
    concurrency cap), while
  * running *different* users' jobs in parallel up to a global worker cap.

It returns standard ``concurrent.futures.Future`` objects, so it is a drop-in
for the synthesis manager (which calls ``.done()`` / ``.running()`` / ``.result()``
on them). Pending (queued) jobs report ``done()==False`` and ``running()==False``
— exactly the "queued" state the status endpoint already understands.
"""
from __future__ import annotations

import threading
from collections import defaultdict, deque
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Deque, Dict, Optional, Tuple


class PerUserJobQueue:
    def __init__(self, global_workers: int = 4, per_user_limit: int = 1):
        self._pool = ThreadPoolExecutor(max_workers=global_workers, thread_name_prefix="synthjob")
        self._per_user_limit = per_user_limit
        self._lock = threading.Lock()
        self._running: Dict[str, int] = defaultdict(int)
        self._pending: Dict[str, Deque[Tuple[Future, Callable, tuple, dict]]] = defaultdict(deque)

    def submit(self, user_id: str, fn: Callable[..., Any], *args, **kwargs) -> Future:
        fut: Future = Future()
        with self._lock:
            if self._running[user_id] < self._per_user_limit:
                self._start_locked(user_id, fut, fn, args, kwargs)
            else:
                self._pending[user_id].append((fut, fn, args, kwargs))
        return fut

    def pending_count(self, user_id: str) -> int:
        with self._lock:
            return len(self._pending[user_id])

    def running_count(self, user_id: str) -> int:
        with self._lock:
            return self._running[user_id]

    def shutdown(self, wait: bool = True) -> None:
        self._pool.shutdown(wait=wait)

    # -- internals -----------------------------------------------------------

    def _start_locked(self, user_id, fut, fn, args, kwargs) -> None:
        self._running[user_id] += 1
        self._pool.submit(self._run, user_id, fut, fn, args, kwargs)

    def _run(self, user_id, fut: Future, fn, args, kwargs) -> None:
        # Honor a cancel that landed before we started; mirror Future semantics.
        if not fut.set_running_or_notify_cancel():
            self._finish(user_id)
            return
        try:
            result = fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 - propagate to the Future
            fut.set_exception(exc)
        else:
            fut.set_result(result)
        finally:
            self._finish(user_id)

    def _finish(self, user_id) -> None:
        with self._lock:
            self._running[user_id] = max(0, self._running[user_id] - 1)
            if self._pending[user_id] and self._running[user_id] < self._per_user_limit:
                fut, fn, args, kwargs = self._pending[user_id].popleft()
                self._start_locked(user_id, fut, fn, args, kwargs)


class ContextUserExecutor:
    """Adapter giving the per-user queue a global-executor ``.submit(fn, *args)``.

    The synthesis manager submits without a user id; we read it from the active
    ``SessionContext`` *at submit time* (in the request task, before the job
    thread starts), so each job is queued under the right tenant.
    """

    def __init__(self, queue: PerUserJobQueue):
        self._queue = queue

    def submit(self, fn: Callable[..., Any], *args, **kwargs) -> Future:
        return self._queue.submit(self._current_user(), fn, *args, **kwargs)

    @staticmethod
    def _current_user() -> str:
        try:
            from src.utils.session_context import get_current_session

            ctx = get_current_session()
            if ctx:
                return ctx.user_id or ctx.session_id
        except Exception:
            pass
        return "local"
