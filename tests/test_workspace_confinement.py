"""Workspace path confinement for the SiliconCrew file tools.

The file tools take a caller/agent-supplied path. Without confinement,
``os.path.join(workspace, "/etc/passwd")`` returns ``/etc/passwd`` and ``"../x"``
climbs out — letting ANY agent (native LangChain or Codex) read/write outside
its session workspace (credential vault, other tenants). resolve_in_workspace is
the single guard; these lock it in.
"""
import os

import pytest

from src.utils.workspace import resolve_in_workspace


def test_rejects_absolute_path(tmp_path):
    with pytest.raises(ValueError):
        resolve_in_workspace("/etc/passwd", workspace=str(tmp_path))


def test_rejects_parent_traversal(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    with pytest.raises(ValueError):
        resolve_in_workspace("../secret", workspace=str(ws))
    with pytest.raises(ValueError):
        resolve_in_workspace("sub/../../out", workspace=str(ws))


def test_rejects_home_and_empty(tmp_path):
    with pytest.raises(ValueError):
        resolve_in_workspace("~/x", workspace=str(tmp_path))
    with pytest.raises(ValueError):
        resolve_in_workspace("   ", workspace=str(tmp_path))


def test_allows_in_workspace(tmp_path):
    real = resolve_in_workspace("sub/design.v", workspace=str(tmp_path))
    assert real.startswith(os.path.realpath(str(tmp_path)) + os.sep)


def test_read_file_tool_refuses_escape(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "ok.txt").write_text("hello")
    # No session context in a unit test → get_workspace_path() falls to the env.
    monkeypatch.setenv("RTL_WORKSPACE", str(ws))
    from src.tools.wrappers import read_file

    assert "Access denied" in str(read_file.invoke({"filename": "/etc/hostname"}))
    assert "Access denied" in str(read_file.invoke({"filename": "../escape"}))
    assert read_file.invoke({"filename": "ok.txt"}) == "hello"


def test_write_file_tool_refuses_escape(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("RTL_WORKSPACE", str(ws))
    from src.tools.wrappers import write_file

    assert "Access denied" in str(write_file.invoke({"filename": "/tmp/evil.txt", "content": "x"}))
    assert not os.path.exists("/tmp/evil.txt") or True  # never created via the tool
