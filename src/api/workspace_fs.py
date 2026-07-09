"""Workspace filesystem reads for the v2 IDE surfaces — pure, testable helpers.

The v2 file explorer is a *real* directory tree loaded lazily (VS Code-web
style): one ``list_dir`` call per expanded directory, plus a flat path index
(``walk_paths``) for quick-open (⌘P). File content goes through
``read_smart_file`` which refuses to serve binary/oversized files as lossy
text — the UI shows an honest "download instead" state and uses ``?raw=1``.

``artifact_cache_control`` encodes the immutability contract: artifacts under a
*terminal* run directory (``sim_runs/<id>/…`` / ``synth_runs/<id>/…``) never
change, so the browser may cache them forever; everything else is ``no-store``.

All functions are blocking — endpoints run them via ``asyncio.to_thread``.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List

# Never surfaced in the explorer or quick-open index.
_EXCLUDED_DIRS = {"__pycache__", "node_modules"}

# Run statuses after which a run directory's contents can no longer change.
_TERMINAL_RUN_STATUSES = {"passed", "failed", "completed"}

TEXT_CONTENT_CAP = 1_000_000  # 1 MB — beyond this the UI offers a download
_BINARY_SNIFF_BYTES = 8192

RECURSIVE_PATHS_CAP = 20_000

CACHE_IMMUTABLE = "private, max-age=31536000, immutable"
CACHE_NO_STORE = "no-store"


def _excluded(name: str) -> bool:
    return name.startswith(".") or name in _EXCLUDED_DIRS


def _safe_join(workspace: str, rel_path: str) -> str:
    """Resolve ``rel_path`` inside ``workspace`` or raise ValueError."""
    target = os.path.realpath(os.path.join(workspace, rel_path or ""))
    root = os.path.realpath(workspace)
    if target != root and not target.startswith(root + os.sep):
        raise ValueError(f"Path escapes the workspace: {rel_path}")
    return target


def list_dir(workspace: str, rel_path: str = "") -> List[Dict[str, Any]]:
    """Immediate children of one directory — dirs first, then case-insensitive name.

    Raises FileNotFoundError for a missing path, NotADirectoryError for a file,
    ValueError for traversal attempts.
    """
    target = _safe_join(workspace, rel_path)
    if not os.path.exists(target):
        raise FileNotFoundError(rel_path)
    if not os.path.isdir(target):
        raise NotADirectoryError(rel_path)

    entries: List[Dict[str, Any]] = []
    with os.scandir(target) as it:
        for entry in it:
            if _excluded(entry.name):
                continue
            rel = os.path.relpath(entry.path, workspace).replace(os.sep, "/")
            if entry.is_dir(follow_symlinks=False):
                entries.append({"name": entry.name, "path": rel, "kind": "dir"})
            elif entry.is_file(follow_symlinks=False):
                st = entry.stat()
                entries.append({
                    "name": entry.name,
                    "path": rel,
                    "kind": "file",
                    "size": st.st_size,
                    "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
                })

    entries.sort(key=lambda e: (e["kind"] != "dir", e["name"].lower()))
    return entries


def walk_paths(workspace: str) -> Dict[str, Any]:
    """Flat, sorted list of every file path for quick-open, capped for safety."""
    paths: List[str] = []
    truncated = False
    for root, dirs, files in os.walk(workspace):
        dirs[:] = sorted(d for d in dirs if not _excluded(d))
        for name in files:
            if _excluded(name):
                continue
            rel = os.path.relpath(os.path.join(root, name), workspace).replace(os.sep, "/")
            paths.append(rel)
            if len(paths) >= RECURSIVE_PATHS_CAP:
                truncated = True
                break
        if truncated:
            break
    paths.sort()
    return {"paths": paths, "truncated": truncated}


def read_smart_file(workspace: str, file_path: str, filename: str) -> Dict[str, Any]:
    """File content with honest binary/size handling.

    ``content`` is None (never lossy garbage) when the file is binary or over
    ``TEXT_CONTENT_CAP`` — the caller surfaces size + flags so the UI can offer
    the raw download instead.
    """
    size = os.path.getsize(file_path)
    with open(file_path, "rb") as f:
        head = f.read(_BINARY_SNIFF_BYTES)
    binary = b"\x00" in head
    too_large = size > TEXT_CONTENT_CAP

    content = None
    if not binary and not too_large:
        with open(file_path, "r", errors="ignore") as f:
            content = f.read()
    return {
        "filename": filename,
        "content": content,
        "size": size,
        "binary": binary,
        "tooLarge": too_large,
    }


def artifact_cache_control(workspace: str, file_path: str) -> str:
    """Immutable for files under a terminal run directory, no-store otherwise.

    A completed/failed run's artifacts (VCD, reports, GDS) never change, so the
    browser may cache them forever. Anything still running — or whose run
    status cannot be determined — must not be cached.
    """
    try:
        rel = os.path.relpath(file_path, workspace).replace(os.sep, "/")
    except ValueError:
        return CACHE_NO_STORE
    parts = rel.split("/")
    if len(parts) < 3 or parts[0] not in ("sim_runs", "synth_runs"):
        return CACHE_NO_STORE
    meta_path = os.path.join(workspace, parts[0], parts[1], "run_meta.json")
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            status = str(json.load(f).get("status", "")).lower()
    except (OSError, ValueError):
        return CACHE_NO_STORE
    return CACHE_IMMUTABLE if status in _TERMINAL_RUN_STATUSES else CACHE_NO_STORE
