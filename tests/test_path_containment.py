"""Tenant boundary: workspace path containment.

Red-team the shared ``is_within`` guard and the write path that uses it. The bug
this locks down: a bare ``realpath(target).startswith(realpath(base))`` accepted
a *sibling* directory sharing a name prefix (base ``/ws/abc`` accepting
``/ws/abc-evil/...``) — a cross-tenant escape. No heavy deps.
"""
import importlib.util
import os

import pytest

from src.utils.paths import is_within
from src.tools.file_ops import _safe_join, write_file

_HAS_APP_STACK = importlib.util.find_spec("langchain_core") is not None


def test_is_within_accepts_contained_paths(tmp_path):
    ws = str(tmp_path / "abc")
    os.makedirs(ws)
    assert is_within(ws, ws) is True                       # the base itself
    assert is_within(ws, os.path.join(ws, "rtl.v")) is True
    assert is_within(ws, os.path.join(ws, "sub", "x.v")) is True


def test_is_within_rejects_parent_escape(tmp_path):
    ws = str(tmp_path / "abc")
    os.makedirs(ws)
    assert is_within(ws, os.path.join(ws, "..", "secret.v")) is False
    assert is_within(ws, str(tmp_path / "secret.v")) is False


def test_is_within_rejects_sibling_prefix(tmp_path):
    """The exact regression: a sibling whose name starts with the base name.

    ``startswith(base)`` (no separator) wrongly returns True here; ``is_within``
    must return False.
    """
    base = tmp_path / "abc"
    base.mkdir()
    sibling = tmp_path / "abc-evil"
    sibling.mkdir()
    (sibling / "secret.v").write_text("stolen")

    assert is_within(str(base), str(sibling / "secret.v")) is False


def test_safe_join_rejects_sibling_prefix(tmp_path):
    base = tmp_path / "abc"
    base.mkdir()
    (tmp_path / "abc-evil").mkdir()
    # A crafted relative path that resolves into the sibling must be refused.
    with pytest.raises(ValueError):
        _safe_join(str(base), "../abc-evil/secret.v")


def test_write_file_stays_inside_workspace(tmp_path):
    ws = str(tmp_path / "abc")
    os.makedirs(ws)
    (tmp_path / "abc-evil").mkdir()
    with pytest.raises(ValueError):
        write_file(ws, "../abc-evil/pwn.v", "x")
    assert not os.path.exists(str(tmp_path / "abc-evil" / "pwn.v"))


# --- Endpoint-level: the layout viewer must enforce tenant ownership ----------
# Needs the full app (LangChain etc.), so it runs in CI and skips in minimal envs.
@pytest.mark.skipif(not _HAS_APP_STACK, reason="needs full app stack (langchain)")
def test_layout_endpoint_requires_session_ownership(monkeypatch, tmp_path):
    """get_layout_svg had no verify_session_access — a tenant could read another
    tenant's rendered GDS by guessing session_id + filename. It must now 404 for
    a session the caller does not own, before any workspace resolution."""
    from fastapi.testclient import TestClient
    import api

    client = TestClient(api.app)
    # A session that does not exist (and thus the caller cannot own) must 404 via
    # the ownership dependency, not fall through to layout rendering.
    r = client.get("/api/workspace/does-not-exist/layout/top.gds")
    assert r.status_code == 404
    assert r.json()["detail"] == "Session not found"
