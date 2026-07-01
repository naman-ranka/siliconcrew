"""F2 + F3: concurrent hydration is safe and deduped (the P1/P2 fix).

F6 moved the blocking workspace hydration off the event loop, so the WS-connect
(agent) path and the F4 snapshot read now untar the SAME session in parallel on
every open. Without a lock + temp-swap that races two ``tar.extractall()`` into
the live scratch dir → torn/half-extracted reads. F3 (generation-skip) makes the
second open a cache hit so only one untar happens, and makes the F7 prewarm's
scratch actually reused.

Uses a delaying/counting store so the untar window is real (the in-memory store
extracts instantly, which is exactly why the race never showed up in tests).
"""
import os
import threading
import time

import pytest

from src.platform_engines.workspace_provider import (
    CloudWorkspaceProvider,
    InMemoryObjectStore,
)


class SlowCountingStore:
    """Wraps a real store, counts get_tree, and can delay the untar."""

    def __init__(self, inner, delay=0.0):
        self.inner = inner
        self.get_calls = 0
        self.delay = delay

    def exists(self, key):
        return self.inner.exists(key)

    def put_tree(self, key, local_dir):
        return self.inner.put_tree(key, local_dir)

    def generation(self, key):
        return self.inner.generation(key)

    def get_tree(self, key, local_dir, subdirs=None):
        self.get_calls += 1
        if self.delay:
            time.sleep(self.delay)
        return self.inner.get_tree(key, local_dir, subdirs)


def _seed(tmp_path, name, files):
    d = tmp_path / name
    d.mkdir()
    for f in files:
        (d / f).write_text("// x\n")
    return str(d)


# --- F3: skip re-download when the generation is unchanged ------------------


def test_f3_skips_redownload_when_generation_unchanged(tmp_path):
    inner = InMemoryObjectStore()
    inner.put_tree("workspaces/s", _seed(tmp_path, "seed", ["top.v"]))
    store = SlowCountingStore(inner)
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))

    p.workspace_for("s")
    assert store.get_calls == 1
    p.workspace_for("s")  # unchanged → cache hit
    assert store.get_calls == 1

    # A new object generation forces exactly one re-hydration.
    inner.put_tree("workspaces/s", _seed(tmp_path, "seed2", ["top.v", "new.v"]))
    ws = p.workspace_for("s")
    assert store.get_calls == 2
    assert os.path.isfile(os.path.join(ws, "new.v"))


def test_sync_marks_generation_so_own_write_is_not_redownloaded(tmp_path):
    inner = InMemoryObjectStore()
    store = SlowCountingStore(inner)
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))

    ws = p.workspace_for("s")  # new session, nothing to download
    assert store.get_calls == 0
    with open(os.path.join(ws, "a.v"), "w") as f:
        f.write("// a\n")
    p.sync("s")  # upload + refresh marker to the just-written generation
    p.workspace_for("s")  # must NOT re-download our own write
    assert store.get_calls == 0


# --- F2: concurrent open hydrates once, no torn read ------------------------


def test_concurrent_open_hydrates_once_and_returns_complete_tree(tmp_path):
    inner = InMemoryObjectStore()
    files = [f"f{i}.v" for i in range(24)]
    inner.put_tree("workspaces/s", _seed(tmp_path, "seed", files))
    store = SlowCountingStore(inner, delay=0.2)  # a real multi-file untar window
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))

    results = {}

    def open_ws(tag):
        ws = p.workspace_for("s")
        results[tag] = sorted(f for f in os.listdir(ws) if f.endswith(".v"))

    # The two hydrations that race on every open: WS-connect + the snapshot read.
    t1 = threading.Thread(target=open_ws, args=("ws_connect",))
    t2 = threading.Thread(target=open_ws, args=("snapshot",))
    t1.start(); t2.start(); t1.join(); t2.join()

    # Only ONE untar (the lock serializes; the second is a cache hit) — P1/P2.
    assert store.get_calls == 1
    # Both callers saw the COMPLETE tree, never a half-extracted subset.
    assert results["ws_connect"] == sorted(files)
    assert results["snapshot"] == sorted(files)


def test_rehydration_never_exposes_a_partial_tree_to_a_reader(tmp_path):
    """A reader holding the workspace path while a NEW generation is hydrated must
    only ever see a complete tree (old or new), never a mix/partial — the
    temp-dir-then-swap guarantee."""
    inner = InMemoryObjectStore()
    a_files = {f"a{i}.v" for i in range(12)}
    b_files = {f"b{i}.v" for i in range(12)}
    inner.put_tree("workspaces/s", _seed(tmp_path, "genA", sorted(a_files)))
    store = SlowCountingStore(inner)
    p = CloudWorkspaceProvider(store, str(tmp_path / "scratch"))

    ws = p.workspace_for("s")  # gen A materialized
    inner.put_tree("workspaces/s", _seed(tmp_path, "genB", sorted(b_files)))  # gen B
    store.delay = 0.3

    torn = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                names = {f for f in os.listdir(ws) if f.endswith(".v")}
            except FileNotFoundError:
                continue  # the ~2-syscall swap gap — not a torn tree
            # Complete-tree invariant: exactly gen A, exactly gen B, or empty.
            if names and names != a_files and names != b_files:
                torn.append(sorted(names)[:5])

    rt = threading.Thread(target=reader)
    rt.start()
    p.workspace_for("s")  # re-hydrate gen B (0.3s untar into temp, then swap)
    time.sleep(0.02)
    stop.set()
    rt.join()

    assert not torn, f"reader saw a partial/torn tree: {torn[:3]}"
    assert {f for f in os.listdir(ws) if f.endswith(".v")} == b_files
