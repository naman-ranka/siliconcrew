"""Two children simulating at once must not lose a run (Codex P1).

Simulations became concurrent when subagents arrived: a ``verify-tb`` fan-out
runs one testbench per child. ``_append_to_index`` did an unlocked
load-modify-save of ``sim_runs/index.json``, so two children finishing together
each wrote a list missing the other's run — a simulation that completed, whose
directory is on disk, and which the runs API and the UI never show.
"""
import json
import os
import threading

from src.tools import sim_manager as sm


def _run(workspace: str, run_id: str, barrier: threading.Barrier) -> None:
    real_load = sm._load_index

    def loading(ws):
        index = real_load(ws)
        # Hold every writer here until each has read, which is the interleaving
        # that loses a run. Once the append is serialised only one thread can
        # be inside at a time, so the barrier is never completed and times out
        # — that timeout IS the fix working.
        try:
            barrier.wait(timeout=0.5)
        except threading.BrokenBarrierError:
            pass
        return index

    sm._load_index = loading
    try:
        sm._append_to_index(
            workspace,
            {"id": run_id, "status": "passed", "createdAt": "2026-08-21T00:00:00+00:00",
             "top": "tb_top", "mode": "rtl"},
        )
    finally:
        sm._load_index = real_load


def test_two_children_finishing_together_both_appear_in_the_index(tmp_path):
    workspace = str(tmp_path)
    os.makedirs(sm._runs_root(workspace), exist_ok=True)
    barrier = threading.Barrier(2)

    threads = [
        threading.Thread(target=_run, args=(workspace, rid, barrier))
        for rid in ("sim_0001", "sim_0002")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with open(sm._index_path(workspace), encoding="utf-8") as f:
        index = json.load(f)
    recorded = sorted(r["run_id"] for r in index["runs"])
    assert recorded == ["sim_0001", "sim_0002"], (
        f"a completed simulation is missing from the index: {recorded}"
    )


# NOTE — the sibling fix in ``src/utils/attempt_logger.py`` (serialise the
# rebuild of ``attempt_log.json``, replace the truncating write with an atomic
# one) has NO test here, deliberately. Two attempts to force the losing
# interleave passed on the pre-fix code as well: the second writer goes through
# the same patched read as the first, so the harness serialised them itself and
# proved nothing. A test that cannot fail is worse than no test, because it
# reads as coverage. The fix stands on the same reasoning as the one above and
# on the pattern already in ``synthesis_manager``; the reproduction is missing
# and this comment is where that is recorded rather than implied.

