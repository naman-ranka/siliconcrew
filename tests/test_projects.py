"""Tests for project CRUD and session-move functionality."""
import os
import tempfile
import pytest
from src.utils.session_manager import SessionManager


@pytest.fixture
def sm(tmp_path):
    return SessionManager(base_dir=str(tmp_path / "workspace"), db_path=str(tmp_path / "state.db"))


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------

def test_create_project(sm):
    p = sm.create_project("My Project")
    assert p["id"] == "MyProject"
    assert p["name"] == "My Project"
    assert p["created_at"] is not None


def test_create_project_slug_normalisation(sm):
    p = sm.create_project("asu hackathon 2026!")
    assert p["id"] == "asuhackathon2026"


def test_create_duplicate_project_raises(sm):
    sm.create_project("Alpha")
    with pytest.raises(ValueError, match="already exists"):
        sm.create_project("Alpha")


def test_get_all_projects_empty(sm):
    assert sm.get_all_projects() == []


def test_get_all_projects(sm):
    sm.create_project("Beta")
    sm.create_project("Alpha")
    names = [p["name"] for p in sm.get_all_projects()]
    assert names == ["Alpha", "Beta"]  # sorted by name


def test_get_project(sm):
    sm.create_project("Gamma")
    p = sm.get_project("Gamma")
    assert p is not None
    assert p["name"] == "Gamma"


def test_get_project_missing(sm):
    assert sm.get_project("nonexistent") is None


def test_delete_project(sm):
    sm.create_project("ToDelete")
    sm.delete_project("ToDelete")
    assert sm.get_project("ToDelete") is None


def test_delete_project_unassigns_sessions(sm):
    sm.create_project("P1")
    sid = sm.create_session("sess1", project_id="P1")
    sm.delete_project("P1")
    meta = sm.get_session_metadata(sid)
    assert meta["project_id"] is None


# ---------------------------------------------------------------------------
# Session creation with project
# ---------------------------------------------------------------------------

def test_create_session_in_project(sm):
    sm.create_project("Exp")
    sid = sm.create_session("run1", project_id="Exp")
    assert sid == "Exp/run1"
    meta = sm.get_session_metadata(sid)
    assert meta["project_id"] == "Exp"


def test_create_session_unknown_project_raises(sm):
    with pytest.raises(ValueError, match="not found"):
        sm.create_session("run1", project_id="ghost")


def test_create_session_no_project(sm):
    sid = sm.create_session("flat_session")
    meta = sm.get_session_metadata(sid)
    assert meta["project_id"] is None


# ---------------------------------------------------------------------------
# Move session between projects
# ---------------------------------------------------------------------------

def test_move_session_to_project(sm):
    sm.create_project("A")
    sm.create_project("B")
    sid = sm.create_session("s1", project_id="A")
    sm.move_session_to_project(sid, "B")
    meta = sm.get_session_metadata(sid)
    assert meta["project_id"] == "B"


def test_move_session_remove_from_project(sm):
    sm.create_project("A")
    sid = sm.create_session("s1", project_id="A")
    sm.move_session_to_project(sid, None)
    meta = sm.get_session_metadata(sid)
    assert meta["project_id"] is None


def test_move_session_unknown_project_raises(sm):
    sid = sm.create_session("flat")
    with pytest.raises(ValueError, match="not found"):
        sm.move_session_to_project(sid, "ghost")


# ---------------------------------------------------------------------------
# Migration: existing grouped sessions get project_id auto-populated
# ---------------------------------------------------------------------------

def test_migration_populates_project_id(tmp_path):
    """Simulate a DB created before project support and verify migration."""
    import sqlite3, datetime

    db = str(tmp_path / "state.db")
    ws = str(tmp_path / "workspace")
    os.makedirs(os.path.join(ws, "myproj", "sess1"), exist_ok=True)
    os.makedirs(os.path.join(ws, "flat_sess"), exist_ok=True)

    # Write old-style DB (no project_id column, no projects table)
    with sqlite3.connect(db) as conn:
        conn.execute("""
            CREATE TABLE session_metadata (
                session_id TEXT PRIMARY KEY,
                session_name TEXT,
                model_name TEXT,
                created_at TIMESTAMP,
                updated_at TIMESTAMP,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                cached_tokens INTEGER DEFAULT 0,
                total_tokens INTEGER DEFAULT 0,
                total_cost REAL DEFAULT 0.0
            )
        """)
        now = datetime.datetime.now()
        conn.execute("INSERT INTO session_metadata VALUES (?,?,?,?,?,0,0,0,0,0.0)",
                     ("myproj/sess1", "sess1", "gemini-3-flash-preview", now, now))
        conn.execute("INSERT INTO session_metadata VALUES (?,?,?,?,?,0,0,0,0,0.0)",
                     ("flat_sess", "flat_sess", "gemini-3-flash-preview", now, now))
        conn.commit()

    # Instantiate SessionManager — triggers migration
    sm2 = SessionManager(base_dir=ws, db_path=db)

    # Grouped session should now have project_id
    meta_grouped = sm2.get_session_metadata("myproj/sess1")
    assert meta_grouped["project_id"] == "myproj"

    # Flat session should have no project_id
    meta_flat = sm2.get_session_metadata("flat_sess")
    assert meta_flat["project_id"] is None

    # Project row should have been created
    proj = sm2.get_project("myproj")
    assert proj is not None
    assert proj["name"] == "myproj"
