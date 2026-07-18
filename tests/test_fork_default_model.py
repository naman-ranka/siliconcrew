"""Blind-test finding S1: template forks (and any caller omitting the model)
must land on the CURRENT catalog default, never a stale needs-key literal —
a keyless user's first suggested action after forking has to work."""
import os
import tempfile

from src.model_catalog import DEFAULT_MODEL
from src.utils.session_manager import SessionManager


def test_create_session_without_model_uses_catalog_default():
    with tempfile.TemporaryDirectory() as ws:
        mgr = SessionManager(base_dir=ws, db_path=os.path.join(ws, "meta.db"))
        sid = mgr.create_session(tag="forked-example")
        meta = mgr.get_session_metadata(sid)
        assert meta["model_name"] == DEFAULT_MODEL


def test_explicit_model_still_wins():
    with tempfile.TemporaryDirectory() as ws:
        mgr = SessionManager(base_dir=ws, db_path=os.path.join(ws, "meta.db"))
        sid = mgr.create_session(tag="picked", model_name="claude-sonnet-5")
        assert mgr.get_session_metadata(sid)["model_name"] == "claude-sonnet-5"
