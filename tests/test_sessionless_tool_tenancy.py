"""Sessionless tools must not leak the process-global session across tenants.

`get_current_session` and `inject_architect_prompt` need no session, so they
dispatch BEFORE the per-call ownership re-verify — that is what makes them
usable for bootstrap. But `current_session` is a process-global pointer, and the
hosted streamable-HTTP transport multiplexes many tenants through one process.
Reading it directly therefore hands whoever asks next the previous tenant's
session id, workspace path and metadata.

These tests pin the fix: a sessionless tool sees the active session only when
the caller owns it, and fails closed otherwise.
"""
import json

import pytest

from src.tools.wrappers import (
    get_current_session,
    inject_architect_prompt,
    session_host,
    visible_session,
)


class _Manager:
    """Owner map: session id -> owning user id."""

    def __init__(self, owners):
        self.owners = owners

    def owns_session(self, session_id, user_id):
        # Mirrors the real SessionManager: user_id None (self-host) matches any
        # existing session.
        if session_id not in self.owners:
            return False
        return user_id is None or self.owners[session_id] == user_id

    def get_session_metadata(self, session_id):
        return {"tag": f"meta-for-{session_id}"}


class _Host:
    """The session-host contract, with a switchable caller identity."""

    def __init__(self, owners, current, caller):
        self.session_manager = _Manager(owners)
        self.current_session = current
        self._caller = caller

    def scoped_user_id(self):
        return self._caller

    def workspace_path(self, session_id):
        return f"/workspaces/{session_id}"

    def architect_prompt(self):
        return ("PROMPT BODY", "test", "vtest")


OWNERS = {"sess-alice": "alice"}


def test_a_tenant_cannot_read_another_tenants_active_session():
    host = _Host(OWNERS, current="sess-alice", caller="bob")
    with session_host(host):
        out = get_current_session.invoke({})
    assert "sess-alice" not in out, "bob was shown alice's session id"
    assert "/workspaces/sess-alice" not in out, "bob was shown alice's workspace path"
    assert "No active session" in out


def test_the_owner_still_sees_their_own_session():
    host = _Host(OWNERS, current="sess-alice", caller="alice")
    with session_host(host):
        info = json.loads(get_current_session.invoke({}))
    assert info["session_id"] == "sess-alice"
    assert info["workspace"] == "/workspaces/sess-alice"


def test_self_host_is_unaffected():
    """user_id None is the single trusted local user; any session is theirs."""
    host = _Host(OWNERS, current="sess-alice", caller=None)
    with session_host(host):
        info = json.loads(get_current_session.invoke({}))
    assert info["session_id"] == "sess-alice"


def test_inject_prompt_does_not_leak_the_active_session_either():
    host = _Host(OWNERS, current="sess-alice", caller="bob")
    with session_host(host):
        payload = inject_architect_prompt.invoke({})
    assert "PROMPT BODY" in payload, "the prompt itself must still be returned"
    assert "sess-alice" not in payload, "bob was shown alice's session id"
    assert "CURRENT_SESSION" not in payload


def test_visible_session_fails_closed_when_ownership_cannot_be_established():
    class _Exploding(_Host):
        def scoped_user_id(self):
            raise RuntimeError("identity backend down")

    host = _Exploding(OWNERS, current="sess-alice", caller="bob")
    assert visible_session(host) is None, "an ownership error must not grant access"


@pytest.mark.parametrize("value", [None, ""])
def test_optional_string_args_accept_a_json_null(value):
    """A client sending null for an optional field means 'unspecified'.

    Rejecting it broke the very first call the server's instructions tell a
    stranger to make.
    """
    from src.tools.wrappers import create_session_tool

    model = create_session_tool.args_schema(
        session_name="counter", model_name=value, project_id=value
    )
    assert model.session_name == "counter"
