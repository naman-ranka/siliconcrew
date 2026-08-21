"""The editing tool, in both of its forms.

``apply_patch_tool`` and ``edit_file_tool`` were one capability split across two
tools: change text in files that already exist. They are one tool now, and this
file is the proof that neither original lost anything — the exact-replacement
form and the unified-diff form are tested side by side, including the errors
each one is careful to raise before writing anything.
"""
import json

import pytest

from src.tools import wrappers


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setenv("RTL_WORKSPACE", str(ws))
    return ws


def _edit(**kwargs) -> dict:
    return json.loads(wrappers.edit_file.invoke(kwargs))


# --- the diff form (was apply_patch_tool) ------------------------------------

def test_unified_diff_updates_the_file(workspace):
    (workspace / "design.v").write_text("module a;\nendmodule\n", encoding="utf-8")
    patch = (
        "--- a/design.v\n"
        "+++ b/design.v\n"
        "@@ -1,2 +1,2 @@\n"
        "-module a;\n"
        "+module b;\n"
        " endmodule\n"
    )
    res = _edit(unified_diff=patch)
    assert res["success"] is True
    assert "design.v" in res["files_changed"]
    assert "module b;" in (workspace / "design.v").read_text(encoding="utf-8")


def test_unified_diff_touches_several_files_in_one_call(workspace):
    (workspace / "a.v").write_text("module a;\nendmodule\n", encoding="utf-8")
    (workspace / "b.v").write_text("module b;\nendmodule\n", encoding="utf-8")
    # `diff --git` headers matter for a multi-file patch: with --recount and no
    # header, git reads the next file's `--- a/b.v` line as a deletion line of
    # the previous hunk and the whole patch is refused. The tool says so.
    patch = (
        "diff --git a/a.v b/a.v\n"
        "--- a/a.v\n+++ b/a.v\n@@ -1,2 +1,2 @@\n-module a;\n+module a2;\n endmodule\n"
        "diff --git a/b.v b/b.v\n"
        "--- a/b.v\n+++ b/b.v\n@@ -1,2 +1,2 @@\n-module b;\n+module b2;\n endmodule\n"
    )
    res = _edit(unified_diff=patch)
    assert res["success"] is True
    assert set(res["files_changed"]) == {"a.v", "b.v"}
    assert "module a2;" in (workspace / "a.v").read_text(encoding="utf-8")
    assert "module b2;" in (workspace / "b.v").read_text(encoding="utf-8")


def test_a_diff_that_does_not_apply_writes_nothing(workspace):
    (workspace / "design.v").write_text("module a;\nendmodule\n", encoding="utf-8")
    patch = (
        "--- a/design.v\n+++ b/design.v\n@@ -1,2 +1,2 @@\n"
        "-module WRONG_CONTEXT;\n+module b;\n endmodule\n"
    )
    res = _edit(unified_diff=patch)
    assert res["success"] is False
    assert (workspace / "design.v").read_text(encoding="utf-8") == "module a;\nendmodule\n"


def test_a_diff_escaping_the_workspace_is_refused(workspace):
    patch = "--- a/../secret.v\n+++ b/../secret.v\n@@ -1 +1 @@\n-x\n+y\n"
    res = _edit(unified_diff=patch)
    assert res["success"] is False
    assert "escapes workspace" in res["message"]


# --- the replacement form (was edit_file_tool) --------------------------------

def test_exact_replacement_rewrites_one_block(workspace):
    (workspace / "counter.v").write_text(
        "module counter;\n  assign a = 1;\nendmodule\n", encoding="utf-8"
    )
    res = _edit(filename="counter.v", target_text="assign a = 1;",
                replacement_text="assign a = 2;")
    assert res["success"] is True
    assert res["files_changed"] == ["counter.v"]
    assert "assign a = 2;" in (workspace / "counter.v").read_text(encoding="utf-8")


def test_replacement_with_empty_text_deletes_the_block(workspace):
    (workspace / "counter.v").write_text("keep\nDROP ME\nkeep\n", encoding="utf-8")
    res = _edit(filename="counter.v", target_text="DROP ME\n", replacement_text="")
    assert res["success"] is True
    assert (workspace / "counter.v").read_text(encoding="utf-8") == "keep\nkeep\n"


def test_target_not_found_writes_nothing(workspace):
    (workspace / "counter.v").write_text("assign a = 1;\n", encoding="utf-8")
    res = _edit(filename="counter.v", target_text="nope", replacement_text="x")
    assert res["success"] is False
    assert "not found" in res["message"]
    assert (workspace / "counter.v").read_text(encoding="utf-8") == "assign a = 1;\n"


def test_an_ambiguous_target_writes_nothing(workspace):
    (workspace / "counter.v").write_text("assign a = 1;\nassign a = 1;\n", encoding="utf-8")
    res = _edit(filename="counter.v", target_text="assign a = 1;", replacement_text="x")
    assert res["success"] is False
    assert "found 2 times" in res["message"]
    assert (workspace / "counter.v").read_text(encoding="utf-8").count("assign a = 1;") == 2


def test_a_filename_escaping_the_workspace_is_refused(workspace):
    res = _edit(filename="../secret.v", target_text="a", replacement_text="b")
    assert res["success"] is False


# --- one call, one form -------------------------------------------------------

def test_both_forms_at_once_is_refused(workspace):
    (workspace / "design.v").write_text("module a;\nendmodule\n", encoding="utf-8")
    res = _edit(
        filename="design.v",
        target_text="module a;",
        replacement_text="module b;",
        unified_diff="--- a/design.v\n+++ b/design.v\n@@ -1 +1 @@\n-module a;\n+module c;\n",
    )
    assert res["success"] is False
    assert "not both" in res["message"]
    assert (workspace / "design.v").read_text(encoding="utf-8") == "module a;\nendmodule\n"


def test_no_form_at_all_says_what_to_pass(workspace):
    res = _edit()
    assert res["success"] is False
    assert "unified_diff" in res["message"] and "target_text" in res["message"]


# --- the manifest sees both forms --------------------------------------------

def test_both_forms_reconcile_the_manifest(workspace, monkeypatch):
    """Editing a design source can change roles/tops, so the manifest has to be
    re-read — the whole-file write path always did this and the two editing
    tools never did."""
    seen: list[str] = []
    real = wrappers.file_ops.reconcile_roles
    monkeypatch.setattr(
        wrappers.file_ops, "reconcile_roles",
        lambda ws, paths: (seen.extend(paths if isinstance(paths, list) else [paths]),
                           real(ws, paths))[1],
    )
    (workspace / "design.v").write_text("module a;\nendmodule\n", encoding="utf-8")

    _edit(filename="design.v", target_text="module a;", replacement_text="module b;")
    assert seen == ["design.v"]

    seen.clear()
    _edit(unified_diff="--- a/design.v\n+++ b/design.v\n@@ -1,2 +1,2 @@\n"
                       "-module b;\n+module c;\n endmodule\n")
    assert seen == ["design.v"]


def test_a_failed_edit_does_not_reconcile(workspace, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(wrappers.file_ops, "reconcile_roles",
                        lambda ws, paths: seen.append(paths))
    (workspace / "design.v").write_text("module a;\nendmodule\n", encoding="utf-8")
    _edit(filename="design.v", target_text="nope", replacement_text="x")
    assert seen == []


def test_reconcile_ignores_files_that_are_not_design_sources(workspace):
    """A README edit must not drag the manifest through a reconcile; a Verilog
    edit must."""
    from src.tools import file_ops

    file_ops.reconcile_roles(str(workspace), ["notes.md"])
    assert not (workspace / "manifest.json").exists()

    (workspace / "design.v").write_text("module a;\nendmodule\n", encoding="utf-8")
    file_ops.reconcile_roles(str(workspace), ["design.v"])
    assert (workspace / "manifest.json").exists()
