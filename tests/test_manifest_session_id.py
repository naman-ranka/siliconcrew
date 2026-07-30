"""Manifest callers pass the session id they already have (dev#71 / A5c).

``read_manifest``/``write_manifest`` seed ``sessionId`` when given one, but the
tool-layer callers passed nothing, so every manifest written through a tool call
carried ``sessionId: ""`` even though the task-local SessionContext knew it.
"""
import json
import os

from src.tools import file_ops
from src.tools import wrappers
from src.utils.session_context import SessionContext, current_session_id, session_scope


def _manifest_on_disk(ws):
    with open(os.path.join(ws, "manifest.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def _workspace(tmp_path):
    ws = str(tmp_path)
    with open(os.path.join(ws, "top.v"), "w", encoding="utf-8") as f:
        f.write("module top(input clk, output q); endmodule\n")
    return ws


def test_current_session_id_returns_empty_without_context():
    assert current_session_id() == ""


def test_current_session_id_reads_the_context(tmp_path):
    with session_scope(SessionContext("s1", str(tmp_path))):
        assert current_session_id() == "s1"


def test_get_manifest_seeds_session_id(tmp_path):
    ws = _workspace(tmp_path)
    with session_scope(SessionContext("s1", ws)):
        out = json.loads(wrappers.get_manifest.func())

    assert out["sessionId"] == "s1"
    assert _manifest_on_disk(ws)["sessionId"] == "s1"


def test_update_manifest_seeds_session_id(tmp_path):
    ws = _workspace(tmp_path)
    with session_scope(SessionContext("s2", ws)):
        out = json.loads(wrappers.update_manifest.func(json.dumps({"synthTop": "top"})))

    assert out["sessionId"] == "s2"
    assert _manifest_on_disk(ws)["sessionId"] == "s2"


def test_write_file_reconciliation_seeds_session_id(tmp_path):
    ws = _workspace(tmp_path)
    with session_scope(SessionContext("s3", ws)):
        file_ops.write_file(ws, "adder.v", "module adder(input a, output b); endmodule\n")

    assert _manifest_on_disk(ws)["sessionId"] == "s3"


def test_existing_session_id_is_never_overwritten(tmp_path):
    """Seeding fills a blank; it does not re-stamp a manifest that has an id
    (a forked workspace deliberately carries the source id or a blank)."""
    ws = _workspace(tmp_path)
    with session_scope(SessionContext("first", ws)):
        wrappers.get_manifest.func()
    with session_scope(SessionContext("second", ws)):
        out = json.loads(wrappers.get_manifest.func())

    assert out["sessionId"] == "first"
