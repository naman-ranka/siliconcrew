"""Hosted read-path hydration (P0 regression guard).

The api.py workspace READ endpoints must resolve through the active
WorkspaceProvider (``api._resolve_workspace``), not the raw local
``session_manager.get_workspace_path``. On Cloud Run the local disk is ephemeral
and per-instance, so a read served by a cold/other instance would 404 ("Session
not found") even though the files are safe in object storage. This proves the
read path rehydrates from storage after a simulated instance recycle.
"""
import os

import pytest

pytest.importorskip("fastapi")

import api
from src.platform_engines.workspace_provider import (
    CloudWorkspaceProvider,
    InMemoryObjectStore,
    set_workspace_provider,
)


def test_resolve_workspace_hydrates_after_instance_recycle(tmp_path):
    store = InMemoryObjectStore()
    try:
        # Instance 1: write a file into the session workspace and sync to storage.
        p1 = CloudWorkspaceProvider(store, str(tmp_path / "scratch1"))
        set_workspace_provider(p1)
        ws1 = api._resolve_workspace("proj/sess_x")  # exercise :path slash id too
        with open(os.path.join(ws1, "counter.v"), "w", encoding="utf-8") as f:
            f.write("module counter; endmodule\n")
        p1.sync("proj/sess_x")

        # Instance 2: a brand-new provider + scratch dir (a different Cloud Run
        # instance). The read path must hydrate the file from object storage
        # instead of seeing an empty/absent local dir.
        p2 = CloudWorkspaceProvider(store, str(tmp_path / "scratch2"))
        set_workspace_provider(p2)
        ws2 = api._resolve_workspace("proj/sess_x")
        assert ws2 != ws1
        assert os.path.isfile(os.path.join(ws2, "counter.v")), (
            "read path did not rehydrate the workspace from object storage"
        )
    finally:
        set_workspace_provider(None)  # reset the module singleton for other tests
