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


def write_file(workspace: str, path: str, content: str) -> Dict[str, Any]:
    """Write ``content`` to ``path`` (workspace-relative) and reconcile roles.

    Returns a small dict describing the write. Used by the REST save action and
    the agent ``write_file`` tool alike.
    """
    abspath = _safe_join(workspace, path)
    os.makedirs(os.path.dirname(abspath) or workspace, exist_ok=True)
    with open(abspath, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)

    # A new/renamed/edited source file can change roles/tops — keep the manifest
    # in sync so the next stage selection (lint/sim/synth) is correct.
    rel = os.path.relpath(abspath, workspace)
    try:
        from src.tools import manifest as manifest_mod

        if rel.lower().endswith((".v", ".sv", ".vh", ".svh", ".sdc")):
            manifest_mod.read_manifest(workspace)  # read = reconcile + persist
    except Exception:
        # manifest reconciliation is best-effort; never fail a write on it
        pass

    return {"path": rel, "bytes": len(content)}
