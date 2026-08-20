"""Tool sets are DATA, read-only mode is a filter, and the fence holds.

Three claims are asserted here, each of which was asserted informally before
and turned out to be false when someone measured it:

1. **Changing which tools an agent sees touches zero code files.** Not "one
   Python dict in one file" — zero. The proof is two-sided: the resolver reads
   a file and honours a different one, AND no production Python module names a
   set's membership.
2. **Read-only mode is nothing but "drop the tools that declare `mutates`".**
   If it ever becomes a list, this test says so.
3. **Focus cannot reach authority.** The data file's whole vocabulary is
   selection over policy the tools declare; nothing in it can grant, revoke or
   soften a check.
"""
from __future__ import annotations

import os

import pytest

from src.api import tool_catalog as tc

PRODUCTION_PY = ("src", "api.py", "mcp_server.py")


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _production_python_files():
    root = _repo_root()
    for entry in PRODUCTION_PY:
        path = os.path.join(root, entry)
        if os.path.isfile(path):
            yield path
            continue
        for dirpath, dirnames, filenames in os.walk(path):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in filenames:
                if name.endswith(".py"):
                    yield os.path.join(dirpath, name)


# --- 1. the sets are data ----------------------------------------------------

def test_a_tool_set_is_changed_by_editing_one_data_file_and_no_code(tmp_path):
    """The whole of criterion 3, demonstrated rather than claimed.

    A different file, with a different selection, produces a different tool
    list from the same unmodified code. No import is re-executed, no constant
    is patched, no module is reloaded.
    """
    alternative = tmp_path / "tool_sets.yaml"
    alternative.write_text(
        "tool_sets:\n"
        "  architect:\n"
        "    surface: agent\n"
        "    read_only_categories: [manifest]\n"
        "subagents: {}\n",
        encoding="utf-8",
    )
    shipped = tc.tool_names_in_set("architect")
    edited = tc.tool_names_in_set("architect", path=str(alternative))
    assert edited == ("get_manifest",), edited
    assert shipped != edited
    # And the shipped answer is unchanged by having asked about another file.
    assert tc.tool_names_in_set("architect") == shipped


def test_no_production_python_file_names_a_set_membership():
    """The other half of "zero code files": a set's CONTENTS appear nowhere in
    Python. Set NAMES may — something has to say which set to build with, and
    ``ARCHITECT_TOOL_SET`` is that one line — but a category list in Python
    would be the relocated hardcoding this wave exists to delete.
    """
    live_categories = {tc.policy_for(n).category for n in tc.tool_names_in_set("architect")}
    offenders = []
    for path in _production_python_files():
        if path.endswith(os.path.join("api", "tool_catalog.py")):
            continue  # the resolver itself reads the words out of the file
        text = open(path, encoding="utf-8-sig", errors="replace").read()
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            quoted = {c for c in live_categories if f'"{c}"' in line or f"'{c}' " in line}
            if quoted and ("tool_set" in line.lower() or "TOOL_SET" in line):
                offenders.append((path, line))
    assert not offenders, f"a tool set's membership is written in Python: {offenders}"


def test_the_data_file_names_no_tool():
    """No tool NAME appears in the data file. A name there would be a second
    list — the exact drift the category vocabulary exists to prevent."""
    text = open(tc.tool_sets_path(), encoding="utf-8").read()
    live = set(tc.tool_names_in_set("architect")) | {"cocotb_tool", "sby_tool", "run_xls_flow"}
    named = sorted(n for n in live if n in text)
    assert not named, f"the tool-set file names tools: {named}"


def test_the_architect_set_is_exactly_the_agent_surface():
    """The set is the same list ``architect_tools`` has always been, so moving
    the architect onto a data-defined set changed no behaviour on the day it
    shipped. If someone edits the file, this test is the thing that tells them
    the change was deliberate."""
    from src.tools.wrappers import architect_tools

    assert tc.tool_names_in_set("architect") == tuple(t.name for t in architect_tools)


# --- 2. read-only is one filter ---------------------------------------------

def test_read_only_is_exactly_the_non_mutating_tools():
    mutating = tc.MUTATING_TOOLS
    for name in tc.tool_set_names():
        full = set(tc.tool_names_in_set(name))
        read_only = set(tc.tool_names_in_set(name, read_only=True))
        assert read_only == full - mutating, name
        assert not (read_only & mutating)


def test_read_only_drops_something_real():
    """A filter that removes nothing is a mode that does nothing."""
    assert set(tc.tool_names_in_set("architect", read_only=True)) < set(
        tc.tool_names_in_set("architect")
    )


def test_there_is_no_second_mode():
    """L9: read-only ships, "auto"/"ask" does not. A mode system for one mode is
    machinery; a second flag here means someone built the switch anyway."""
    from src.platform_engines.settings import get_settings

    words = {"mode", "modes", "ask", "confirm", "confirmation", "approval"}
    fields = {f for f in vars(get_settings()) if set(f.split("_")) & words}
    assert not fields, f"a mode/confirmation setting appeared: {fields}"


# --- 3. the fence ------------------------------------------------------------

def test_the_data_file_has_no_authority_vocabulary():
    """FOCUS is what an agent SEES; AUTHORITY is what may RUN. The set schema
    can express only selection — surface, categories, and the read-only filter.
    A key that could turn a check off would be the two merging."""
    authority = {"protected", "allow", "deny", "authorize", "capability", "owner", "user"}
    for key in tc._SET_KEYS:
        assert not (set(key.split("_")) & authority), key


def test_focus_never_changes_a_policy_flag():
    for name in tc.tool_set_names():
        for read_only in (False, True):
            for tool_name in tc.tool_names_in_set(name, read_only=read_only):
                policy = tc.policy_for(tool_name)
                assert policy is tc.policy_for(tool_name)
                assert (tool_name in tc.PROTECTED_TOOLS) == policy.protected


# --- loud failures -----------------------------------------------------------

@pytest.mark.parametrize("body,fragment", [
    ("tool_sets:\n  x:\n    surface: nowhere\n", "surface"),
    ("tool_sets:\n  x:\n    surface: agent\n    categories: [nonesuch]\n", "categor"),
    ("tool_sets:\n  x:\n    surface: agent\n    categories: []\n", "no tools at all"),
    ("tool_sets:\n  x:\n    surface: agent\n    colour: red\n", "unknown key"),
    ("tool_sets: {}\n", "non-empty"),
    ("tool_sets:\n  x:\n    surface: agent\nsubagents:\n  r:\n    tool_set: nope\n    skills: [a]\n",
     "not defined here"),
    ("tool_sets:\n  x:\n    surface: agent\nsubagents:\n  r:\n    tool_set: x\n    skills: []\n",
     "at least one skill"),
])
def test_a_broken_file_fails_loudly(tmp_path, body, fragment):
    """A malformed set must never resolve to "no tools": an agent with no tools
    still answers, so the failure looks like a bad model, not a bad file."""
    path = tmp_path / "tool_sets.yaml"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(tc.ToolSetError) as exc:
        tc.tool_names_in_set("x", path=str(path))
    assert fragment in str(exc.value)


def test_a_missing_file_fails_loudly(tmp_path):
    with pytest.raises(tc.ToolSetError):
        tc.tool_names_in_set("architect", path=str(tmp_path / "absent.yaml"))


def test_the_path_is_overridable_without_a_code_change(tmp_path, monkeypatch):
    path = tmp_path / "elsewhere.yaml"
    path.write_text("tool_sets:\n  architect:\n    surface: agent\n", encoding="utf-8")
    monkeypatch.setenv("SILICONCREW_TOOL_SETS_FILE", str(path))
    assert tc.tool_sets_path() == str(path)
