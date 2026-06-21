"""Per-user job queue tests (Phase 2, slice 4).

Verifies the queue serializes a single user's jobs, runs different users in
parallel, and yields Future objects whose state matches what the synthesis
status endpoint inspects (done/running/result + a 'queued' pending state).
"""
import threading
import time

from src.platform_engines.job_queue import ContextUserExecutor, PerUserJobQueue
from src.utils.session_context import SessionContext, session_scope


def test_per_user_serialization_one_at_a_time():
    q = PerUserJobQueue(global_workers=8, per_user_limit=1)
    active = {"now": 0, "max": 0}
    lock = threading.Lock()
    release = threading.Event()

    def job():
        with lock:
            active["now"] += 1
            active["max"] = max(active["max"], active["now"])
        release.wait(timeout=2)
        with lock:
            active["now"] -= 1
        return "ok"

    f1 = q.submit("u1", job)
    f2 = q.submit("u1", job)
    # Give the pool a moment; only one of u1's jobs may be running.
    time.sleep(0.1)
    assert q.running_count("u1") == 1
    assert q.pending_count("u1") == 1
    assert f2.running() is False and f2.done() is False  # the "queued" state

    release.set()
    assert f1.result(timeout=2) == "ok"
    assert f2.result(timeout=2) == "ok"
    assert active["max"] == 1  # never two of u1's jobs at once
    q.shutdown()


def test_different_users_run_in_parallel():
    q = PerUserJobQueue(global_workers=8, per_user_limit=1)
    barrier = threading.Barrier(3, timeout=3)

    def job():
        barrier.wait()  # only succeeds if all three run concurrently
        return "ok"

    futs = [q.submit(f"u{i}", job) for i in range(3)]
    assert [f.result(timeout=3) for f in futs] == ["ok", "ok", "ok"]
    q.shutdown()


def test_future_propagates_exception():
    q = PerUserJobQueue()

    def boom():
        raise ValueError("nope")

    f = q.submit("u1", boom)
    try:
        f.result(timeout=2)
        assert False, "expected exception"
    except ValueError as e:
        assert "nope" in str(e)
    q.shutdown()


def test_context_user_executor_routes_by_session_user():
    q = PerUserJobQueue(per_user_limit=1)
    ex = ContextUserExecutor(q)
    seen = {}

    def job(tag):
        seen[tag] = threading.current_thread().name
        return tag

    with session_scope(SessionContext("sess_a", "/ws/a", user_id="alice")):
        fa = ex.submit(job, "a")
    with session_scope(SessionContext("sess_b", "/ws/b", user_id="bob")):
        fb = ex.submit(job, "b")

    assert fa.result(timeout=2) == "a"
    assert fb.result(timeout=2) == "b"
    # Both ran (different users → not serialized against each other).
    assert set(seen) == {"a", "b"}
    q.shutdown()


def test_executor_falls_back_to_local_without_context():
    q = PerUserJobQueue()
    ex = ContextUserExecutor(q)
    f = ex.submit(lambda: 42)
    assert f.result(timeout=2) == 42
    # No session context → bucketed under the "local" pseudo-user.
    assert q.running_count("local") == 0  # finished
    q.shutdown()
