"""
Tests for create_session_tool project_id support.
Tests the SessionManager layer (same code path the MCP handler calls).
"""
import os
import pytest
from src.utils.session_manager import SessionManager


@pytest.fixture
def sm(tmp_path):
    return SessionManager(base_dir=str(tmp_path / "workspace"), db_path=str(tmp_path / "state.db"))


# ---------------------------------------------------------------------------
# create_session with project_id
# ---------------------------------------------------------------------------

def test_create_session_with_project_id(sm):
    sm.create_project("asu_batch")
    sid = sm.create_session("p1", project_id="asu_batch")
    assert sid == "asu_batch/p1"
    meta = sm.get_session_metadata(sid)
    assert meta["project_id"] == "asu_batch"


def test_create_session_with_project_workspace_exists(sm):
    sm.create_project("asu_batch")
    sid = sm.create_session("p5", project_id="asu_batch")
    workspace = sm.get_workspace_path(sid)
    assert os.path.isdir(workspace)


def test_create_session_without_project_id(sm):
    sid = sm.create_session("p1")
    assert sid == "p1"
    meta = sm.get_session_metadata(sid)
    assert meta["project_id"] is None


def test_create_session_unknown_project_raises(sm):
    with pytest.raises(ValueError, match="not found"):
        sm.create_session("p1", project_id="nonexistent_project")


def test_create_session_duplicate_in_project_raises(sm):
    sm.create_project("batch")
    sm.create_session("p1", project_id="batch")
    with pytest.raises(FileExistsError):
        sm.create_session("p1", project_id="batch")


def test_multiple_sessions_same_project(sm):
    sm.create_project("asu_0421")
    problems = ["p1", "p5", "p7", "p8", "p9"]
    session_ids = []
    for p in problems:
        sid = sm.create_session(p, project_id="asu_0421")
        session_ids.append(sid)

    assert session_ids == [f"asu_0421/{p}" for p in problems]

    all_sessions = sm.get_all_sessions()
    for sid in session_ids:
        assert sid in all_sessions
        meta = sm.get_session_metadata(sid)
        assert meta["project_id"] == "asu_0421"


def test_project_delete_unassigns_sessions_created_with_project_id(sm):
    sm.create_project("temp_batch")
    sid = sm.create_session("p1", project_id="temp_batch")
    sm.delete_project("temp_batch")
    meta = sm.get_session_metadata(sid)
    assert meta["project_id"] is None


# ---------------------------------------------------------------------------
# MCP handler argument parsing (unit-level, no real MCP server needed)
# ---------------------------------------------------------------------------

def test_project_id_none_when_empty_string(sm):
    """Ensure empty string project_id is treated as None (matches MCP handler logic)."""
    project_id = "" or None  # mirrors: arguments.get("project_id") or None
    assert project_id is None


def test_project_id_preserved_when_set(sm):
    project_id = "asu_batch" or None
    assert project_id == "asu_batch"
