"""One file-value resolver for every tool that takes a user-supplied file name.

Before this module each wrapper did its own ``os.path.join(workspace, arg)``,
so a basename the UI legitimately suggested (``alu.v``) failed for a file that
lives at ``rtl/alu.v``, and every tool had its own idea of what a valid value
looks like. Now there is exactly one resolution contract:

  * a workspace-relative path is honored as an exact address (never fuzzily
    re-routed to a different directory — that would silently run other code);
  * a bare basename is resolved MANIFEST-FIRST (invariant 1: the manifest is
    the single source of truth for design files): the stored manifest file
    list decides on its own, and the workspace tree (the manifest scan's
    exclusion policy, :func:`manifest.iter_workspace_files`) is searched ONLY
    when the manifest matches nothing. A stray untracked copy — ``old/alu.v``
    next to the manifest's ``rtl/alu.v`` — therefore cannot make a tracked
    design file ambiguous; ambiguity is reported only when the index that WON
    is itself ambiguous;
  * a basename without extension is completed from ``exts`` when given;
  * ambiguous -> an error naming every candidate; missing -> an error naming
    what was searched (the message always contains "does not exist" — pinned
    by existing wrapper-level tests);
  * containment is checked HERE with :func:`is_within`, on the typed value AND
    on every index hit (a manifest entry or tree file that resolves outside
    the workspace is treated as absent). Load-bearing: the
    agent and MCP paths run no containment at all, and ``/invoke``'s
    ``enforce_file_containment`` is an argument-NAME convention that checks
    only what the caller typed — so the resolver cannot delegate the check to
    the caller. A contained absolute path is accepted (what the compile-set
    tools always took) and returned as a workspace-relative path.

Layering: for tools with their own validation (``run_python_analysis``'s
containment, ``build_interactive_sim``'s name checks) this is a PRE-resolution
step that runs BEFORE that validation and never replaces it.

Run-artifact directories (``sim_runs/``, ``synth_runs/``, …) are pruned from
the tree scan, so their files are reachable by exact path only — a bare
``dump.vcd`` search will not find one.
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
            # ``path`` is the canonical key; ``name`` is display-only, kept as
            # a fallback for legacy manifests written before ``path`` existed.
            path = entry.get("path") or entry.get("name")
            if isinstance(path, str) and path:
                out.append(path)
    return out


def _tree_paths(workspace: str) -> List[str]:
    """Workspace-relative paths from the tree walk (manifest scan policy)."""
    ignore = manifest_mod.stored_ignore(workspace)
    return list(manifest_mod.iter_workspace_files(workspace, ignore))


def _basename_matches(
    workspace: str,
    index: Sequence[str],
    value: str,
    exts: Sequence[str],
) -> List[str]:
    """Files in ``index`` whose basename is ``value`` (or ``value`` + one of
    ``exts`` when nothing matched exactly), deduped, sorted, and filtered to
    what is really on disk (the stored manifest can lag a delete) AND inside
    the workspace.

    Containment applies to the ANSWER, not only to the typed value: the stored
    manifest is tenant-writable (``write_file("manifest.json", ...)`` persists
    ``path`` verbatim) and the tree walk lists symlinks whose targets can point
    anywhere, so an index hit is exactly as untrusted as user input. A hit that
    resolves outside the workspace is dropped here as if it did not exist —
    the caller then reports "does not exist" without ever naming it.
    """
    matches = [rel for rel in index if os.path.basename(rel) == value]
    if not matches and exts:
        wanted = {value + ext for ext in exts}
        matches = [rel for rel in index if os.path.basename(rel) in wanted]
    return sorted({
        rel for rel in matches
        if os.path.isfile(p := os.path.join(workspace, rel)) and is_within(workspace, p)
    })


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

    # Manifest-first (invariant 1): a tracked design file is never made
    # ambiguous by an untracked copy sitting elsewhere in the tree. The tree is
    # a FALLBACK for files the manifest does not carry, not a co-equal index.
    matches = _basename_matches(workspace, _stored_manifest_paths(workspace), value, exts)
    if not matches:
        matches = _basename_matches(workspace, _tree_paths(workspace), value, exts)

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
    wrappers and the REST twin handlers — parity by construction, not by
    parallel implementations.
    """
    out: List[str] = []
    for v in values or []:
        rel = resolve_workspace_file(workspace, v, exts=exts, must_exist=must_exist)
        if rel not in out:
            out.append(rel)
    return out
