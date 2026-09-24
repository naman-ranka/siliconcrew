"""The test suite never opens the developer's real app state.

api.py binds its database and workspace dir at import time. Without isolation,
every CI-lane run on a developer machine opened ~/.siliconcrew/state.db (and
byok.db) and wrote test sessions into <checkout>/workspace — the overnight run of
2026-09-23 saw a pre-existing `test` session row get a fresh updated_at, and
workspace/{test,test_write_file_tool,instructions_probe} appear in each worktree.
"""
import os

import api

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REAL_DATA = os.path.join(os.path.expanduser("~"), ".siliconcrew")


def _under(path: str, parent: str) -> bool:
    path, parent = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(parent))
    return path == parent or path.startswith(parent + os.sep)


def test_database_is_not_the_developers():
    assert not _under(api.DB_PATH, REAL_DATA)


def test_workspaces_are_not_in_the_checkout():
    assert not _under(api.WORKSPACE_DIR, os.path.join(ROOT, "workspace"))
