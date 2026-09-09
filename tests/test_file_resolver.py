"""The one file-value resolver (command-surface simplification v2, R1-R12).

Every tool that takes a user-supplied file name resolves it through
``resolve_workspace_file``: ws-relative path, basename, or basename without
extension, searched against the manifest file list first and then the
workspace tree, with the resolver's OWN is_within containment (several
file-valued keys bypass /invoke's containment heuristic, and the agent/MCP
paths never run it at all).
"""
import os

import pytest

from src.tools.manifest import override_drop_notes
from src.tools.file_resolver import (
    FileResolutionError,
    resolve_workspace_file,
    resolve_workspace_files,
)


def _mk(ws, rel, content="module m; endmodule\n"):
    path = os.path.join(ws, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def test_exact_relative_path(tmp_path):
    ws = str(tmp_path)
    _mk(ws, "alu.v")
    assert resolve_workspace_file(ws, "alu.v") == "alu.v"


def test_nested_exact_path(tmp_path):
    ws = str(tmp_path)
    _mk(ws, "rtl/alu.v")
    assert resolve_workspace_file(ws, "rtl/alu.v") == "rtl/alu.v"


def test_basename_resolves_nested_file(tmp_path):
    """THE bug this wave fixes: the UI suggests 'alu.v' for a file that lives
    at rtl/alu.v; a bare join made every such call fail."""
    ws = str(tmp_path)
    _mk(ws, "rtl/alu.v")
    assert resolve_workspace_file(ws, "alu.v") == "rtl/alu.v"


def test_basename_without_extension_with_exts(tmp_path):
    ws = str(tmp_path)
    _mk(ws, "rtl/alu.v")
    assert resolve_workspace_file(ws, "alu", exts=(".v", ".sv")) == "rtl/alu.v"


def test_pathed_value_completes_extension(tmp_path):
    ws = str(tmp_path)
    _mk(ws, "rtl/alu.v")
    assert resolve_workspace_file(ws, "rtl/alu", exts=(".v", ".sv")) == "rtl/alu.v"


def test_root_extensionless_value(tmp_path):
    ws = str(tmp_path)
    _mk(ws, "counter_spec.yaml")
    assert (
        resolve_workspace_file(ws, "counter_spec", exts=(".yaml", ".yml"))
        == "counter_spec.yaml"
    )


def test_ambiguous_basename_lists_candidates(tmp_path):
    ws = str(tmp_path)
    _mk(ws, "rtl/alu.v")
    _mk(ws, "given/alu.v")
    with pytest.raises(FileResolutionError) as ei:
        resolve_workspace_file(ws, "alu.v")
    msg = str(ei.value)
    assert "Ambiguous" in msg
    assert "rtl/alu.v" in msg and "given/alu.v" in msg


def test_missing_names_what_was_searched(tmp_path):
    ws = str(tmp_path)
    with pytest.raises(FileResolutionError) as ei:
        resolve_workspace_file(ws, "nope.v", exts=(".v",))
    msg = str(ei.value)
    # "does not exist" is the pinned substring (test_schematic_hosted_gate etc.)
    assert "does not exist" in msg
    assert "manifest" in msg and "workspace tree" in msg


def test_pathed_value_never_reroutes_to_another_directory(tmp_path):
    """'given/alu.v' must NOT resolve to rtl/alu.v — that would silently
    compile different code than the caller named."""
    ws = str(tmp_path)
    _mk(ws, "rtl/alu.v")
    with pytest.raises(FileResolutionError) as ei:
        resolve_workspace_file(ws, "given/alu.v")
    assert "does not exist" in str(ei.value)


def test_traversal_escape_rejected(tmp_path):
    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    _mk(str(tmp_path), "evil.v")
    with pytest.raises(FileResolutionError, match="escapes the workspace"):
        resolve_workspace_file(ws, "../evil.v")


def test_absolute_path_outside_workspace_rejected(tmp_path):
    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    outside = _mk(str(tmp_path), "evil.v")
    with pytest.raises(FileResolutionError, match="escapes the workspace"):
        resolve_workspace_file(ws, outside)


def test_absolute_path_inside_workspace_ok(tmp_path):
    ws = str(tmp_path)
    abs_path = _mk(ws, "rtl/alu.v")
    assert resolve_workspace_file(ws, abs_path) == "rtl/alu.v"


def test_symlink_escape_rejected(tmp_path):
    ws = str(tmp_path / "ws")
    os.makedirs(ws)
    secret = _mk(str(tmp_path), "secret.v")
    os.symlink(secret, os.path.join(ws, "link.v"))
    with pytest.raises(FileResolutionError, match="escapes the workspace"):
        resolve_workspace_file(ws, "link.v")


def test_must_exist_false_is_containment_checked_passthrough(tmp_path):
    ws = str(tmp_path)
    # A creation path must NOT "resolve" to an existing file elsewhere.
    _mk(ws, "rtl/alu.v")
    assert resolve_workspace_file(ws, "alu.v", must_exist=False) == "alu.v"
    with pytest.raises(FileResolutionError, match="escapes the workspace"):
        resolve_workspace_file(ws, "../x.v", must_exist=False)


def test_empty_value_rejected(tmp_path):
    with pytest.raises(FileResolutionError, match="empty"):
        resolve_workspace_file(str(tmp_path), "  ")


def test_run_artifact_dirs_reachable_by_exact_path_only(tmp_path):
    """sim_runs/ is excluded from the tree scan, so a basename search cannot
    find its files — but the exact relative path is still an honest address."""
    ws = str(tmp_path)
    _mk(ws, "sim_runs/sim_0001/dump.vcd", content="$enddefinitions $end\n")
    assert (
        resolve_workspace_file(ws, "sim_runs/sim_0001/dump.vcd")
        == "sim_runs/sim_0001/dump.vcd"
    )
    with pytest.raises(FileResolutionError, match="does not exist"):
        resolve_workspace_file(ws, "dump.vcd")


def test_multi_resolver_dedupes_and_preserves_order(tmp_path):
    ws = str(tmp_path)
    _mk(ws, "rtl/alu.v")
    _mk(ws, "tb/alu_tb.v")
    out = resolve_workspace_files(ws, ["alu_tb.v", "alu.v", "rtl/alu.v"])
    assert out == ["tb/alu_tb.v", "rtl/alu.v"]


def test_override_drop_notes_name_each_dropped_file():
    notes = override_drop_notes("lint", ["rtl/alu.v", "rtl/top.v"], ["rtl/top.v"])
    assert len(notes) == 1
    assert "rtl/alu.v" in notes[0]
    assert "lint" in notes[0]


def test_override_drop_notes_empty_when_superset():
    assert override_drop_notes("simulate", ["a.v"], ["a.v", "b.v"]) == []


# --- manifest-first resolution (adversarial-review F6) -------------------------

def _write_manifest(ws, paths, ignore=None):
    import json

    from src.tools.manifest import MANIFEST_FILENAME

    with open(os.path.join(ws, MANIFEST_FILENAME), "w", encoding="utf-8") as f:
        json.dump(
            {
                "files": [{"name": os.path.basename(p), "path": p, "role": "rtl"} for p in paths],
                "ignore": ignore or [],
            },
            f,
        )


def test_stray_untracked_copy_never_shadows_a_manifest_file(tmp_path):
    """The documented contract is manifest-FIRST: a leftover old/alu.v must not
    make the manifest's rtl/alu.v ambiguous (before the fix both indexes were
    merged, so every stray copy broke a tracked basename)."""
    ws = str(tmp_path)
    _mk(ws, "rtl/alu.v")
    _mk(ws, "old/alu.v")
    _write_manifest(ws, ["rtl/alu.v"])
    assert resolve_workspace_file(ws, "alu.v") == "rtl/alu.v"
    assert resolve_workspace_files(ws, ["alu"], exts=(".v", ".sv")) == ["rtl/alu.v"]


def test_manifest_itself_ambiguous_still_errors(tmp_path):
    ws = str(tmp_path)
    _mk(ws, "rtl/alu.v")
    _mk(ws, "given/alu.v")
    _write_manifest(ws, ["rtl/alu.v", "given/alu.v"])
    with pytest.raises(FileResolutionError) as ei:
        resolve_workspace_file(ws, "alu.v")
    msg = str(ei.value)
    assert "Ambiguous" in msg and "rtl/alu.v" in msg and "given/alu.v" in msg


def test_tree_fallback_ambiguity_still_errors_when_manifest_has_none(tmp_path):
    """Manifest yields zero → the tree decides, and an ambiguous tree is still
    an honest error (the fallback is not a licence to guess)."""
    ws = str(tmp_path)
    _mk(ws, "rtl/alu.v")
    _mk(ws, "old/alu.v")
    _write_manifest(ws, ["rtl/counter.v"])
    _mk(ws, "rtl/counter.v")
    with pytest.raises(FileResolutionError) as ei:
        resolve_workspace_file(ws, "alu.v")
    assert "Ambiguous" in str(ei.value)


def test_manifest_entry_deleted_on_disk_falls_through_to_the_tree(tmp_path):
    """The stored manifest can lag a delete — a manifest hit that is gone must
    not win over a real file."""
    ws = str(tmp_path)
    _mk(ws, "old/alu.v")
    _write_manifest(ws, ["rtl/alu.v"])  # rtl/alu.v never created
    assert resolve_workspace_file(ws, "alu.v") == "old/alu.v"
