"""Single source of truth for writing a file into a workspace.

Both callers funnel through here so there is exactly one write path (api-contract
rule #2): the human editor's Save (REST ``POST /file``) and the agent's
``write_file`` ``@tool``. Centralizing it also makes this the one chokepoint
where a future git auto-commit / history hook can be dropped in without touching
either caller.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from src.utils.paths import is_within


def _safe_join(workspace: str, path: str) -> str:
    """Join + guard against path traversal escaping the workspace."""
    # Normalize and forbid absolute paths / parent escapes.
    rel = path.replace("\\", "/").lstrip("/")
    abspath = os.path.normpath(os.path.join(workspace, rel))
    if not is_within(workspace, abspath):
        raise ValueError(f"Refusing to write outside the workspace: {path}")
    return abspath


_DESIGN_SUFFIXES = (".v", ".sv", ".vh", ".svh", ".sdc")


def reconcile_roles(workspace: str, rel_paths: Any) -> None:
    """Re-read (and persist) the manifest when a design source changed.

    A new/renamed/edited source file can change roles/tops, so the next stage
    selection (lint/sim/synth) is only correct if the manifest saw the change.
    Every writer calls this — whole-file writes below, and the editing tool for
    both an exact replacement and a patch — so no write path is the one that
    leaves the manifest stale. Best-effort: reconciliation never fails a write.
    """
    paths = [rel_paths] if isinstance(rel_paths, str) else list(rel_paths or [])
    if not any(str(p).lower().endswith(_DESIGN_SUFFIXES) for p in paths):
        return
    try:
        from src.tools import manifest as manifest_mod
        from src.utils.session_context import current_session_id

        # read = reconcile + persist
        manifest_mod.read_manifest(workspace, session_id=current_session_id())
    except Exception:
        pass


def write_file(workspace: str, path: str, content: str) -> Dict[str, Any]:
    """Write ``content`` to ``path`` (workspace-relative) and reconcile roles.

    Returns a small dict describing the write. Used by the REST save action and
    the agent ``write_file`` tool alike.
    """
    abspath = _safe_join(workspace, path)
    os.makedirs(os.path.dirname(abspath) or workspace, exist_ok=True)
    with open(abspath, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

    rel = os.path.relpath(abspath, workspace)
    reconcile_roles(workspace, rel)
    return {"path": rel, "bytes": len(content)}
