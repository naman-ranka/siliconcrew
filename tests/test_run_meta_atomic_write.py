"""P2 follow-up: run-metadata writes must be atomic.

list_synthesis_runs() self-heals run_meta.json on READ (reconcile stale status,
re-finalize PPA). Those reads now run concurrently (F6 moved hydration + workspace
reads off the event loop), so two readers can persist the same run_meta.json at
once. A truncate-then-write would let a concurrent reader see a half-written /
empty file; _write_json uses a temp file + os.replace so a reader always sees a
complete document (old or new), never torn.
"""
import json
import os
import threading

from src.tools.synthesis_manager import _read_json, _write_json


def test_write_json_is_atomic_and_leaves_no_temp(tmp_path):
    path = str(tmp_path / "run_meta.json")
    _write_json(path, {"status": "completed", "summary_metrics": {"cell_count": 42}})
    assert _read_json(path)["summary_metrics"]["cell_count"] == 42
    # No leftover temp files from the atomic swap.
    assert [p for p in os.listdir(tmp_path) if ".tmp." in p] == []


def test_concurrent_write_read_never_tears(tmp_path):
    path = str(tmp_path / "run_meta.json")
    _write_json(path, {"status": "running", "n": 0})

    errors: list[str] = []
    stop = threading.Event()

    def writer():
        i = 0
        while not stop.is_set():
            i += 1
            _write_json(path, {"status": "completed", "n": i, "pad": "x" * 500})

    def reader():
        while not stop.is_set():
            try:
                doc = _read_json(path)
            except (json.JSONDecodeError, ValueError) as e:
                errors.append(str(e))  # a torn/half-written read
                continue
            # Whatever we read must be a complete, well-formed document.
            if "status" not in doc or "n" not in doc:
                errors.append(f"incomplete doc: {doc!r}")

    threads = [threading.Thread(target=writer) for _ in range(2)] + [
        threading.Thread(target=reader) for _ in range(3)
    ]
    for t in threads:
        t.start()
    threading.Event().wait(0.4)
    stop.set()
    for t in threads:
        t.join()

    assert not errors, f"atomic write violated: {errors[:3]}"
    assert [p for p in os.listdir(tmp_path) if ".tmp." in p] == []
