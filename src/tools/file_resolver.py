"""One file-value resolver for every tool that takes a user-supplied file name.

The ".v here but not there" fix (plans/command-surface-simplification.md, W1):
before this module each wrapper did its own ``os.path.join(workspace, arg)``,
so a basename the UI legitimately suggested (``alu.v``) failed for a file that
lives at ``rtl/alu.v``, and every tool had its own idea of what a valid value
looks like. Now there is exactly one resolution contract:

  * a workspace-relative path is honored as an exact address (never fuzzily
    re-routed to a different directory — that would silently run other code);
  * a bare basename is searched across the manifest file list first, then the
    workspace tree (same exclusion policy as every listing endpoint);
  * a basename without extension is completed from ``exts`` when given;
  * ambiguous -> an error naming every candidate; missing -> an error naming
    what was searched (the message always contains "does not exist" — pinned
    by existing tests);
  * containment is checked HERE with :func:`is_within`. Load-bearing: several
    file-valued keys (``spec_filename``/``ir_filename``/``opt_ir_filename``/
    ``yaml_path``) never match ``/invoke``'s ``enforce_file_containment``
    heuristic, and the agent/MCP paths run no containment at all — so the
    resolver cannot delegate the check to the caller.

Layering: for tools with their own validation (XLS family's
``validate_safe_relative_path``, ``run_python_analysis``'s containment,
``build_interactive_sim``'s name checks) this is a PRE-resolution step that
runs BEFORE that validation and never replaces it (amendment A1).

``load_yaml_spec_file`` is deliberately NOT wired here: its project-root
fallback reads files OUTSIDE the workspace by design (amendment A4).
"""
from __future__ import annotations

import os
from typing import List, Optional, Sequence

from src.tools import manifest as manifest_mod
from src.utils.paths import is_within


class FileResolutionError(ValueError):
    """A file argument that cannot be honestly resolved: it escapes the
    workspace, does not exist, or matches more than one file."""


def _posix(rel: str) -> str:
    return rel.replace(os.sep, "/")


def _stored_manifest_paths(workspace: str) -> List[str]:
    """Workspace-relative paths from the persisted manifest, WITHOUT a
    reconcile (same rationale as :func:`manifest.stored_ignore`: resolving one
    argument must not pay for a full workspace rescan)."""
    raw = manifest_mod._load_raw(workspace)
    out: List[str] = []
    if isinstance(raw, dict) and isinstance(raw.get("files"), list):
        for entry in raw["files"]:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path") or entry.get("name")
            if isinstance(path, str) and path:
                out.append(path)
    return out


def _search_index(workspace: str) -> List[str]:
    """Manifest file list first, then the workspace tree, deduped in order."""
    seen: dict = {}
    for rel in _stored_manifest_paths(workspace):
        seen.setdefault(rel, None)
    ignore = manifest_mod.stored_ignore(workspace)
    for rel in manifest_mod.iter_workspace_files(workspace, ignore):
        seen.setdefault(rel, None)
    return list(seen)


def resolve_workspace_file(
    workspace: str,
    value: str,
    *,
    exts: Optional[Sequence[str]] = None,
    must_exist: bool = True,
) -> str:
    """Resolve one user-supplied file value to a workspace-relative POSIX path.

    ``exts`` (e.g. ``(".v", ".sv")``) enables extension-less values: ``alu``
    resolves to ``alu.v`` / ``rtl/alu.v`` when exactly one such file exists.
    ``must_exist=False`` is a containment-checked passthrough for creation
    paths (a new file must never "resolve" to an existing one).

    Raises :class:`FileResolutionError` on escape / missing / ambiguous.
    """
    if not isinstance(value, str) or not value.strip():
        raise FileResolutionError("File name cannot be empty.")
    value = value.strip()
    exts = tuple(exts or ())

    candidate = value if os.path.isabs(value) else os.path.join(workspace, value)
    if not is_within(workspace, candidate):
        raise FileResolutionError(f"Path escapes the workspace: {value}")

    if os.path.isabs(value):
        # A contained absolute path is an exact address — no searching.
        rel = _posix(os.path.relpath(os.path.realpath(candidate), os.path.realpath(workspace)))
        if not must_exist or os.path.isfile(candidate):
            return rel
        raise FileResolutionError(
            f"File '{value}' does not exist (absolute path inside the workspace)."
        )

    if not must_exist:
        return _posix(os.path.normpath(value))

    if os.path.isfile(candidate):
        return _posix(os.path.normpath(value))

    # Extension completion on the exact address ('rtl/alu' or 'alu' + '.v').
    for ext in exts:
        with_ext = candidate + ext
        if os.path.isfile(with_ext) and is_within(workspace, with_ext):
            return _posix(os.path.normpath(value + ext))

    ext_note = f" (also tried extensions: {', '.join(exts)})" if exts else ""
    if "/" in _posix(value):
        # A pathed value is an exact address: resolving 'given/alu.v' to some
        # OTHER directory's alu.v would silently compile different code.
        raise FileResolutionError(
            f"File '{value}' does not exist in the workspace{ext_note}."
        )

    index = _search_index(workspace)
    matches = [rel for rel in index if os.path.basename(rel) == value]
    if not matches and exts:
        wanted = {value + ext for ext in exts}
        matches = [rel for rel in index if os.path.basename(rel) in wanted]
    # Only files really on disk (the stored manifest can lag a delete).
    matches = sorted({rel for rel in matches if os.path.isfile(os.path.join(workspace, rel))})

    if len(matches) == 1:
        return _posix(matches[0])
    if len(matches) > 1:
        raise FileResolutionError(
            f"Ambiguous file '{value}' — matches {', '.join(matches)}. "
            "Use the workspace-relative path to pick one."
        )
    raise FileResolutionError(
        f"File '{value}' does not exist in the workspace "
        f"(searched the manifest file list and the workspace tree{ext_note})."
    )


def resolve_workspace_files(
    workspace: str,
    values: Sequence[str],
    *,
    exts: Optional[Sequence[str]] = None,
    must_exist: bool = True,
) -> List[str]:
    """Resolve a list of file values (deduped, order-preserving).

    This is the ONE shared multi-file helper called by both the agent/MCP
    wrappers and the REST twin handlers (amendment A13) — parity by
    construction, not by parallel implementations.
    """
    out: List[str] = []
    for v in values or []:
        rel = resolve_workspace_file(workspace, v, exts=exts, must_exist=must_exist)
        if rel not in out:
            out.append(rel)
    return out


def override_drop_notes(
    stage: str,
    manifest_files: Sequence[str],
    override_files: Sequence[str],
) -> List[str]:
    """One honest note per manifest-supplied file a user override leaves out.

    Same delivery pattern as ``_compile_set_warnings`` (best-effort notes in
    the reply, never a dispatch failure) — the override is legitimate; the
    note just says out loud what it changed.
    """
    override = set(override_files)
    return [
        f"Override omits manifest {stage} file '{rel}' — it is not part of this run."
        for rel in manifest_files
        if rel not in override
    ]
