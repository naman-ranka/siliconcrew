"""The Phase 1 action layer — manifest, IDE-first buttons, unified runs.

This is a self-contained FastAPI ``APIRouter`` with **no dependency on the agent
stack** (LangGraph/LangChain), so it can be mounted by ``api.py`` and tested in
isolation against a local workspace. Every handler is a thin wrapper over a
SiliconCrew tool function — never raw EDA — and the *same* tool functions back
the agent's ``@tool`` wrappers, so there is exactly one action layer
(``api-contract.md`` rule #2).

Per ``api-contract.md``:
  * Every request carries a session and resolves the workspace via
    ``session_scope`` — never the global ``RTL_WORKSPACE`` env var (rule #3).
  * Sim is sync (returns a run record); synth is async (job + poll) (rule #4).
  * Every endpoint uses the uniform error envelope (rule #5).

Auth/tenancy (Phase 2 integration): the auth dependencies and the tenant
ownership check are *injected* by ``api.py`` so this module stays free of the
agent/web wiring. When omitted (self-host / tests) they default to a trusted
local identity with no scoping — behaviour identical to before.

Field names follow ``data-model.md`` (camelCase) so JSON crosses to the
TypeScript types unchanged.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from src.api.activity import read_activity
from src.api import workspace_fs
from src.api import tool_catalog
from src.utils.attempt_logger import log_tool_call, log_tool_result
from src.utils.session_context import SessionContext, current_session_id, session_scope
from src.utils.paths import is_within
from src.platform_engines import auth as _auth_engine
from src.tools import manifest as manifest_mod
from src.tools import file_ops
# The SAME multi-file resolver the agent/MCP wrappers use: calling one shared
# helper from both the REST twins and the wrappers — not mere parameter
# presence — is what keeps invariant 2 (zero drift) true. Drop notes come from
# manifest_mod.override_drop_notes, likewise shared.
from src.tools.file_resolver import FileResolutionError, resolve_workspace_files
from src.tools.run_linter import files_compiled, run_linter
from src.tools.sim_manager import (
    run_sim_isolated,
    list_sim_runs,
    get_sim_run,
    set_sim_run_pinned,
)
from src.tools.synthesis_manager import (
    get_run_dir,
    list_synthesis_runs,
    start_synthesis_job,
    retry_pd_job,
    get_synthesis_status,
    get_synthesis_metrics,
)

WorkspaceResolver = Callable[[str], str]


# --- Request bodies (camelCase, per data-model.md) --------------------------

class ManifestUpdate(BaseModel):
    synthTop: Optional[str] = None
    simTop: Optional[str] = None
    clockPeriodNs: Optional[float] = None
    platform: Optional[str] = None
    files: Optional[List[Dict[str, Any]]] = None
    # fnmatch globs (workspace-relative POSIX paths) excluded from the scan.
    ignore: Optional[List[str]] = None


class SimulateRequest(BaseModel):
    simTop: Optional[str] = None
    mode: str = "rtl"
    runId: Optional[str] = None
    # Optional compile-set override: workspace-relative paths or basenames,
    # resolved through the shared file resolver. Empty/absent = the manifest's
    # files_for_stage set, exactly as before.
    files: Optional[List[str]] = None


class SynthesizeRequest(BaseModel):
    synthTop: Optional[str] = None
    platform: Optional[str] = None
    clockPeriodNs: Optional[float] = None
    # 40 matches start_synthesis and the frontend. A UI-dispatched run must
    # not silently differ from an agent-dispatched one; that divergence is
    # what made this value have five sources of truth.
    utilization: int = 40
    aspectRatio: float = 1.0
    coreMargin: float = 2.0
    runEquiv: bool = False
    constraintsMode: str = "auto"
    # Last flow stage to execute; "finish" (default) = full RTL->GDS flow,
    # "synth" = fast synthesis-only PPA estimate. Later stages are "skipped".
    maxStage: str = "finish"
    # Optional compile-set override; same .v/.sv filter as the manifest path
    # (constraints still flow via constraintsMode, never this list).
    verilogFiles: Optional[List[str]] = None


class RetryRequest(BaseModel):
    fromStage: str
    maxStage: str = "finish"
    overrides: Optional[Dict[str, Any]] = None


class PinRequest(BaseModel):
    pinned: bool = True


class CodeSave(BaseModel):
    content: str


class InvokeRequest(BaseModel):
    tool: str
    arguments: Optional[Dict[str, Any]] = None


class LintRequest(BaseModel):
    engine: str = "auto"  # auto | iverilog | verilator
    # Optional compile-set override; empty/absent = manifest lint set.
    files: Optional[List[str]] = None


# --- Shared helpers ---------------------------------------------------------

def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, **payload}


def _err(code: str, message: str, details: Optional[Dict[str, Any]] = None, status: int = 400):
    raise HTTPException(
        status_code=status,
        detail={"ok": False, "error": {"code": code, "message": message, "details": details or {}}},
    )


def _ui_log_call(workspace: str, session_id: str, tool: str, arguments: Dict[str, Any]) -> str:
    """Record a user-initiated (REST) tool call in the per-session event log.

    Same log the agent (WS) and MCP paths write, so the Activity feed shows
    every invocation regardless of who drove it. source="ui" → actor "user".
    Logging must never break the action itself.
    """
    call_id = f"ui-{uuid.uuid4().hex[:12]}"
    try:
        log_tool_call(workspace, session_id, "ui", tool, arguments, tool_call_id=call_id)
    except Exception:
        pass
    return call_id


def _ui_log_result(
    workspace: str,
    session_id: str,
    tool: str,
    call_id: str,
    result: Any,
    ok: bool = True,
) -> None:
    try:
        text = result if isinstance(result, str) else json.dumps(result)
        log_tool_result(
            workspace, session_id, "ui", tool, text,
            status="success" if ok else "error",
            tool_call_id=call_id,
        )
    except Exception:
        pass


_SYNTH_STATUS_MAP = {
    "completed": "passed",
    "failed": "failed",
    "running": "running",
    "queued": "running",
}


def _synth_to_run(workspace: str, item: Dict[str, Any]) -> Dict[str, Any]:
    """Map a synthesis-runs index item to the unified RunBase/SynthRun shape."""
    run_id = item.get("run_id")
    raw_status = item.get("status") or "unknown"
    status = _SYNTH_STATUS_MAP.get(raw_status, "failed")

    pinned = False
    parent = None
    if run_id:
        meta_path = os.path.join(workspace, "synth_runs", run_id, "run_meta.json")
        if os.path.exists(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                pinned = bool(meta.get("pinned", False))
                parent = meta.get("parent_run_id") or meta.get("parentRunId")
            except Exception:
                pass

    metrics = item.get("summary_metrics") or {}
    ppa = None
    if metrics:
        # Use an explicit None check, not ``or`` — WNS/TNS are legitimately 0.0
        # (timing met exactly), and ``0.0 or alt`` would drop a real value.
        def _pick(*keys):
            for k in keys:
                v = metrics.get(k)
                if v is not None:
                    return v
            return None

        ppa = {
            "areaUm2": _pick("area_um2", "areaUm2"),
            "cells": _pick("cell_count", "cells"),
            "wnsNs": _pick("wns_ns", "wnsNs"),
            "tnsNs": _pick("tns_ns", "tnsNs"),
            "fmaxMhz": _pick("fmax_mhz", "fmaxMhz"),
            "powerMw": _pick("power_mw", "powerMw"),
            # The honest timing set. Kept identical to the run-detail payload
            # below: this card reads the PERSISTED snapshot and the detail panel
            # recomputes, so any field present in one must be present in both or
            # the same run shows two different answers in one UI.
            "worstSlackNs": _pick("worst_slack_ns", "worstSlackNs"),
            "timingMet": _pick("timing_met", "timingMet"),
            "timingCorner": _pick("timing_corner", "timingCorner"),
            "timingNote": _pick("timing_note", "timingNote"),
        }

    return {
        "id": run_id,
        "kind": "synth",
        "status": status,
        "createdAt": item.get("created_at") or item.get("updated_at"),
        "top": item.get("top_module"),
        "pinned": pinned,
        "parentRunId": parent,
        "provenance": {"pdk": item.get("platform")},
        "platform": item.get("platform"),
        "elapsedSec": item.get("elapsed_sec"),
        "ppa": ppa,
        "reportAvailable": item.get("report_available", False),
        "autoChecks": item.get("auto_checks"),
        # Failing stage + reason (F12) so a failed run card can name the stage
        # and one-line cause without opening logs. Absent → null.
        "currentStage": item.get("current_stage"),
        "checkNotes": item.get("check_notes"),
    }


def _split_lint_diagnostics(diagnostics: List[Dict[str, Any]]):
    """Regroup run_linter's structured diagnostics (the ONE parsing contract —
    engines are parsed inside src/tools/run_linter.py) into the REST response's
    warnings/errors/byFile shape."""
    warnings: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for d in diagnostics or []:
        entry = {
            "line": d.get("line"),
            "severity": d.get("severity"),
            "message": d.get("message"),
            "code": d.get("code"),
        }
        fname = d.get("file")
        if fname:
            by_file.setdefault(fname, []).append(entry)
        (warnings if d.get("severity") == "warning" else errors).append({**entry, "file": fname})
    return warnings, errors, by_file


def _classify_file(name: str) -> str:
    """FileInfo.type classification — mirrors api.py's list_workspace_files."""
    ext = os.path.splitext(name)[1].lower()
    if ext in manifest_mod.RTL_EXTS:
        return "verilog"
    if ext == ".yaml":
        return "spec" if "_spec" in name else "yaml"
    if ext == ".vcd":
        return "waveform"
    if ext == ".gds":
        return "layout"
    if ext == ".svg":
        return "schematic"
    if ext == ".md":
        return "report"
    return "unknown"


def _snapshot_files(
    workspace: str,
    roles: Dict[str, Optional[str]],
    ignore: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """FileInfo[] for the workbench snapshot (same shape as GET /files).

    Recursive, under the manifest's exclusion policy. ``path`` is the
    workspace-relative POSIX path (was absolute pre-recursion; no frontend
    consumer reads FileInfo.path) and ``roles`` is keyed by that same path.
    """
    import datetime as _dt

    out: List[Dict[str, Any]] = []
    for rel in manifest_mod.iter_workspace_files(workspace, ignore):
        full = os.path.join(workspace, rel)
        try:
            st = os.stat(full)
        except OSError:
            continue
        name = os.path.basename(rel)
        out.append({
            "name": name,
            "path": rel,
            "type": _classify_file(name),
            "size": st.st_size,
            "modified": _dt.datetime.fromtimestamp(st.st_mtime).isoformat(),
            "role": roles.get(rel),
        })
    out.sort(key=lambda f: f["modified"], reverse=True)
    return out


def _snapshot_spec(workspace: str, ignore: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
    """Latest *_spec.yaml as {filename, content, parsed} — same as GET /spec."""
    import yaml as _yaml

    spec_files = sorted(
        [f for f in manifest_mod.iter_workspace_files(workspace, ignore) if f.endswith("_spec.yaml")],
        key=lambda x: os.path.getmtime(os.path.join(workspace, x)),
        reverse=True,
    )
    if not spec_files:
        return None
    path = os.path.join(workspace, spec_files[0])
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    try:
        parsed = _yaml.safe_load(content)
    except Exception:
        parsed = None
    return {"filename": spec_files[0], "content": content, "parsed": parsed}


def _compile_set_warnings(workspace: str, rel_files: List[str]) -> List[str]:
    """Duplicate-module warnings for a compile set the IDE is about to run.

    The Simulate/Synthesize buttons call the run functions directly rather than
    the agent wrappers, so without this the IDE user — sc#66's actual protagonist
    — would be the only actor who never sees the collision. Best-effort: a
    warning is never worth failing a dispatch over.
    """
    try:
        return manifest_mod.compile_set_collisions(workspace, rel_files)
    except Exception:
        return []


def _code_file_rel_paths(workspace: str, manifest: manifest_mod.DesignManifest) -> List[str]:
    """Relative paths served by GET /code: manifest files with code roles
    (rtl/tb/include) plus any .v/.sv the exclusion-aware scan found."""
    rels = {f.path for f in manifest.files if f.role in ("rtl", "tb", "include")}
    rels.update(
        rel for rel in manifest_mod.iter_workspace_files(workspace, manifest.ignore)
        if rel.lower().endswith(manifest_mod.RTL_EXTS)
    )
    return sorted(r for r in rels if os.path.isfile(os.path.join(workspace, r)))


def _snapshot_code(workspace: str, manifest: Optional[manifest_mod.DesignManifest] = None) -> List[Dict[str, Any]]:
    """Code files as CodeFile[] — same shape as GET /code.

    ``filename`` is the workspace-relative POSIX path (equals the basename for
    root files); the frontend keys code tabs by exactly this value.
    """
    if manifest is None:
        manifest = manifest_mod.read_manifest(workspace, session_id=current_session_id())
    out: List[Dict[str, Any]] = []
    for rel in _code_file_rel_paths(workspace, manifest):
        with open(os.path.join(workspace, rel), "r", errors="ignore") as f:
            out.append({
                "filename": rel,
                "content": f.read(),
                "language": "systemverilog" if rel.endswith((".sv", ".svh")) else "verilog",
            })
    return out


def _snapshot_report(workspace: str) -> Optional[Dict[str, Any]]:
    """Latest available report as {filename, content, run_id} — same as GET /report."""
    run_dir = get_run_dir(workspace, None)
    report_path = None
    run_id = None
    if run_dir:
        candidate = os.path.join(run_dir, "design_report.md")
        if os.path.exists(candidate):
            report_path, run_id = candidate, os.path.basename(run_dir)
    if not report_path:
        loose = sorted(
            [f for f in os.listdir(workspace) if f.endswith("_report.md")],
            key=lambda x: os.path.getmtime(os.path.join(workspace, x)),
            reverse=True,
        )
        if loose:
            report_path = os.path.join(workspace, loose[0])
    if not report_path:
        return None
    with open(report_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    # Field name must match the frontend ReportData shape (run_id), same as the
    # /report endpoint's ReportResponse — NOT runId.
    return {"filename": os.path.basename(report_path), "content": content, "run_id": run_id}


def build_actions_router(
    resolve_workspace: WorkspaceResolver,
    *,
    get_identity: Optional[Callable[..., Any]] = None,
    require_signed_in: Optional[Callable[..., Any]] = None,
    require_owned: Optional[Callable[[str, Any], Optional[str]]] = None,
    sync_workspace: Optional[Callable[[str], None]] = None,
) -> APIRouter:
    """Build the action router.

    ``resolve_workspace(session_id) -> path`` maps a session to its workspace
    directory. Phase 1 passes ``session_manager.get_workspace_path``; Phase 2
    swaps in a cloud-backed resolver — no handler changes required.

    Auth/tenancy is injected so this module stays free of the web wiring:
      * ``get_identity`` / ``require_signed_in`` — FastAPI deps returning the
        caller's ``Identity`` (anonymous trial allowed for lint/sim; sign-in
        required for save/synth).
      * ``require_owned(session_id, identity) -> user_id`` — 404s if the caller
        does not own the session; returns the tenant id (``None`` in self-host).
      * ``sync_workspace(session_id)`` — optional cloud write-back after a run.
    When omitted (self-host / tests) everything defaults to a trusted local
    identity with no scoping, i.e. behaviour identical to before.
    """
    if get_identity is None:
        def get_identity():
            return _auth_engine.LOCAL_IDENTITY
    if require_signed_in is None:
        require_signed_in = get_identity
    if require_owned is None:
        def require_owned(session_id: str, identity: Any) -> Optional[str]:
            return _auth_engine.scoped_user_id(identity)

    router = APIRouter(prefix="/api/workspace/{session_id:path}", tags=["actions"])

    async def require_workspace(session_id: str) -> str:
        # F6: workspace_for() is a blocking hydration (GCS download+untar in
        # hosted) — resolve it off the event loop so one slow session's read
        # can't stall every other in-flight request. (No-op cost in self-host.)
        workspace = await asyncio.to_thread(resolve_workspace, session_id)
        if not workspace or not os.path.exists(workspace):
            raise HTTPException(status_code=404, detail="Session not found")
        return workspace

    async def run_scoped(session_id: str, workspace: str, fn, *args, _uid=None, _id=None, mutates: bool = False, **kwargs):
        """Run a sync tool call bound to this request's SessionContext, off-thread.

        Binds the tenant (``_uid``) and tier into the task-local SessionContext so
        tenancy + synth quota enforcement see them, copies the contextvar into the
        worker thread (so tools reading ``get_workspace_path()`` resolve this
        session), and — **only after a mutating action** (``mutates=True``) —
        persists the workspace back to object storage (cloud) on exit.

        Reads pass ``mutates=False`` (the default) and therefore never upload.
        This is the F1 fix: a read-only GET re-tarring+uploading the whole
        workspace made post-synth "list my runs" take tens of seconds, and a
        stale read's sync could clobber a concurrent write's object. Self-host
        passes ``sync_workspace=None``, so the ``finally`` is a no-op regardless.
        """
        ctx = SessionContext(
            session_id=session_id,
            workspace=workspace,
            user_id=_uid,
            tier=getattr(_id, "tier", "user"),
        )

        def runner():
            with session_scope(ctx):
                return fn(*args, **kwargs)

        try:
            return await asyncio.to_thread(runner)
        finally:
            # F6: the sync (tar + GCS upload) is blocking — run it off the event
            # loop so it can't stall other in-flight requests.
            if mutates and sync_workspace is not None:
                try:
                    await asyncio.to_thread(sync_workspace, session_id)
                except Exception:
                    pass

    # ---- Design manifest ----------------------------------------------------

    @router.get("/manifest")
    async def get_manifest(session_id: str, identity=Depends(get_identity)):
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)
        manifest = await run_scoped(session_id, workspace, manifest_mod.read_manifest, workspace, session_id, _uid=uid, _id=identity)
        return _ok({"manifest": manifest.model_dump()})

    @router.put("/manifest")
    async def put_manifest(session_id: str, body: ManifestUpdate, identity=Depends(require_signed_in)):
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        try:
            manifest = await run_scoped(session_id, workspace, manifest_mod.write_manifest, workspace, updates, session_id, _uid=uid, _id=identity, mutates=True)
        except ValueError as exc:
            # Role validation lives in write_manifest (so every caller is covered);
            # here it just becomes a 400 instead of a 500.
            _err("invalid_role", str(exc), status=400)
        return _ok({"manifest": manifest.model_dump()})

    @router.post("/files")
    async def upload_files(
        session_id: str,
        files: List[UploadFile] = File(...),
        target_dir: str = Form("", alias="dir"),
        identity=Depends(require_signed_in),
    ):
        """Upload into the workspace root, or into ``dir`` (workspace-relative).

        The uploaded FILENAME is still basenamed — allowing a target directory
        must not also start honouring paths inside a client-supplied filename,
        which is the classic zip-slip shape. So traversal can only be attempted
        through ``dir``, which is containment-checked ONCE here, before any
        directory is created (checking after mkdir would already have made a
        directory outside the workspace).
        """
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)
        os.makedirs(workspace, exist_ok=True)

        rel_dir = (target_dir or "").strip().rstrip("/")
        if rel_dir:
            # Same contract as the inline "New file" input
            # (frontend/lib/fileTree.ts validateNewFilePath): workspace-relative,
            # no leading slash, no "."/".." segments. REJECT rather than
            # sanitize — quietly rewriting "/etc" to "etc" would write somewhere
            # the caller never asked for, which is the kind of silent
            # reinterpretation that makes a path bug invisible.
            if rel_dir.startswith("/") or any(seg in ("", ".", "..") for seg in rel_dir.split("/")):
                _err(
                    "invalid_path",
                    f"Target directory must be workspace-relative, with no '.' or '..' segments: {target_dir}",
                    status=400,
                )
        dest_dir = os.path.join(workspace, rel_dir) if rel_dir else workspace
        # Defence in depth behind the syntactic check above: catches a symlinked
        # subdirectory pointing out of the workspace, which no amount of string
        # validation would see.
        if not is_within(workspace, dest_dir):
            _err("invalid_path", f"Refusing to write outside the workspace: {target_dir}", status=400)
        os.makedirs(dest_dir, exist_ok=True)

        saved: List[str] = []
        for upload in files:
            name = os.path.basename(upload.filename or "")
            if not name:
                continue
            dest = os.path.join(dest_dir, name)
            if not is_within(workspace, dest):
                _err("invalid_path", f"Refusing to write outside the workspace: {name}", status=400)
            content = await upload.read()
            with open(dest, "wb") as f:
                f.write(content)
            # Workspace-relative POSIX path, matching how the manifest names
            # files (it walks recursively) — so the caller's "stored but not
            # shown" comparison stays meaningful for subdirectory uploads.
            saved.append(os.path.relpath(dest, workspace).replace(os.sep, "/"))

        # Files were written to the workspace above (outside run_scoped), so this
        # call must persist them → mutates=True even though read_manifest reads.
        manifest = await run_scoped(session_id, workspace, manifest_mod.read_manifest, workspace, session_id, _uid=uid, _id=identity, mutates=True)
        return _ok({"uploaded": saved, "manifest": manifest.model_dump()})

    @router.put("/code/{filename:path}")
    async def save_code(session_id: str, filename: str, body: CodeSave, identity=Depends(require_signed_in)):
        """Write an edited/new source file (the in-app fix loop), then return the
        refreshed manifest. Routes through ``file_ops.write_file`` — the SAME
        function the agent's write_file tool uses (one write path)."""
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)

        def work():
            try:
                file_ops.write_file(workspace, filename, body.content)
            except ValueError as exc:
                return {"error": str(exc)}
            return {"manifest": manifest_mod.read_manifest(workspace, session_id)}

        out = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity, mutates=True)
        if out.get("error"):
            _err("invalid_path", out["error"], status=400)
        return _ok({"saved": os.path.basename(filename), "manifest": out["manifest"].model_dump()})

    # ---- Lint ---------------------------------------------------------------

    @router.post("/lint")
    async def lint_action(session_id: str, body: Optional[LintRequest] = None, identity=Depends(get_identity)):
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)
        engine = (body.engine if body else "auto") or "auto"
        override = list(body.files) if body and body.files else []

        def work():
            manifest = manifest_mod.read_manifest(workspace, session_id)
            manifest_files = manifest_mod.files_for_stage(manifest, "lint")
            dropped: List[str] = []
            filter_notes: List[str] = []
            scope_modules: set = set()
            if override:
                try:
                    rel_files = resolve_workspace_files(workspace, override, exts=manifest_mod.RTL_EXTS)
                except FileResolutionError as exc:
                    return {"badFiles": str(exc)}
                # Same source filter the manifest path applies (files_for_stage
                # never hands lint a non-source) — an explicit file the engine
                # would only choke on is named as dropped, by the one helper
                # the wrappers and the other twins call too.
                rel_files, filter_notes = manifest_mod.compile_sources("lint", rel_files)
                if not rel_files:
                    return {"error": "no_override_sources"}
                dropped = manifest_mod.dropped_manifest_files(manifest_files, rel_files)
                # An override that leaves manifest lint files out (exactly the
                # files the drop notes name below) is a FILE-SCOPED lint. The
                # manifest already knows which modules each design file
                # declares, so the linter is told precisely which unresolved
                # names are the user's own choice: "Unknown module type:
                # counter" is a scope note only when a DROPPED file defines
                # `counter`; a typo'd `countr` or a module no file defines
                # stays a FAILED verdict (invariant 4 — a note states a fact,
                # never a policy of trust). Derived, not declared: a client
                # cannot claim file-scoped for a whole-design lint, and an
                # override that keeps the whole manifest set — or runs against
                # an empty manifest set — is strict by construction.
                scope_modules = manifest_mod.modules_defined_by(workspace, manifest, dropped)
            else:
                rel_files = manifest_files
            if not rel_files:
                return {"empty": True}
            # Invariant 3 — one event log, rendered everywhere: a file-scoped
            # lint's verdict means something different from a whole-design
            # lint's, so the durable event says so (scope in the call, notes
            # in the result), not just the transient toast.
            call_id = _ui_log_call(workspace, session_id, "linter_tool", {
                "verilog_files": rel_files, "engine": engine,
                "fileScoped": bool(dropped), "scopeModules": sorted(scope_modules),
            })
            abs_files = [os.path.join(workspace, f) for f in rel_files]
            # -I is the manifest's include directories (invariant 1), never the
            # source directories — on verilator -I is also a module library.
            result = run_linter(
                abs_files, cwd=workspace, engine=engine, scope_modules=scope_modules,
                include_dirs=manifest_mod.include_dirs(manifest),
            )
            if result.get("unavailable") or result.get("invalid_engine"):
                # No engine ran: an error, never a failed-lint verdict.
                _ui_log_result(workspace, session_id, "linter_tool", call_id,
                               {"status": "error", "error": result["stderr"]}, ok=False)
                key = "engineInvalid" if result.get("invalid_engine") else "engineUnavailable"
                return {key: result["stderr"]}
            # The drop notes are written AFTER the run, from what the engine
            # proved it read. The residual widening case: an include-role file
            # lives in a source directory, so that directory is on -I and
            # verilator's library search finds a dropped file there anyway.
            # Then the dropped file WAS compiled, its note says so (one helper,
            # one wording, same as the agent wrapper), and its modules are
            # struck from the recorded scope: they were elaborated, so they
            # cannot be excused — and by construction never were, since an
            # elaborated module raises no unresolved-module diagnostic for the
            # excuse to act on. The record is what is corrected here.
            compiled = files_compiled(result)
            notes = filter_notes + manifest_mod.override_drop_notes(
                "lint", manifest_files, rel_files, compiled=compiled, engine=result.get("engine")
            ) + list(result.get("notes") or [])
            widened = [f for f in dropped if f in compiled]
            if widened:
                scope_modules = scope_modules - manifest_mod.modules_defined_by(workspace, manifest, widened)
            warnings, errors, by_file = _split_lint_diagnostics(result.get("diagnostics") or [])
            passed = bool(result.get("success"))
            _ui_log_result(
                workspace, session_id, "linter_tool", call_id,
                {"status": "passed" if passed else "failed", "engine": result.get("engine"),
                 "warnings": len(warnings), "errors": len(errors), "notes": notes,
                 "scopeModules": sorted(scope_modules), "filesRead": result.get("filesRead")},
                ok=passed,
            )
            return {
                "empty": False,
                "result": result,
                "files": rel_files,
                "warnings": warnings,
                "errors": errors,
                "byFile": by_file,
                "notes": notes,
            }

        # mutates=True: lint itself is a read, but it now records itself in the
        # per-session event log (attempt_events.jsonl), which must persist.
        out = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity, mutates=True)
        if out.get("badFiles"):
            _err("invalid_files", out["badFiles"], status=400)
        if out.get("error") == "no_override_sources":
            _err("no_files", "The files override contains no .v/.sv/.vh/.svh sources to lint.", status=400)
        if out.get("empty"):
            _err("no_rtl", "No RTL files in the manifest to lint.", status=400)
        if out.get("engineUnavailable"):
            _err("engine_unavailable", out["engineUnavailable"], {"engine": engine}, status=409)
        if out.get("engineInvalid"):
            _err("invalid_engine", out["engineInvalid"], {"engine": engine}, status=400)

        result = out["result"]
        return _ok({
            "status": "passed" if result.get("success") else "failed",
            "engine": result.get("engine"),
            "warnings": out["warnings"],
            "errors": out["errors"],
            "byFile": out["byFile"],
            "command": result.get("command", ""),
            "files": out["files"],
            # What the engine proved it read (run_linter: verilator, after a
            # clean elaboration); null = not measured, never "read nothing".
            "filesRead": result.get("filesRead"),
            # Same channel simulate/synthesize use: honest notes about what a
            # file override changed (which manifest files it left out).
            "manifestWarnings": out["notes"],
        })

    # ---- Simulate (sync, isolated run) -------------------------------------

    @router.post("/simulate")
    async def simulate_action(session_id: str, body: SimulateRequest, identity=Depends(get_identity)):
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)

        def work():
            manifest = manifest_mod.read_manifest(workspace, session_id)
            top = body.simTop or manifest.simTop
            if not top:
                return {"error": "no_sim_top"}
            manifest_files = manifest_mod.files_for_stage(manifest, "simulate")
            notes: List[str] = []
            if body.files:
                try:
                    rel_files = resolve_workspace_files(workspace, body.files, exts=manifest_mod.RTL_EXTS)
                except FileResolutionError as exc:
                    return {"error": "bad_files", "message": str(exc)}
                # Same source filter the manifest path applies; an explicit
                # non-source is named as dropped, never handed to iverilog.
                rel_files, notes = manifest_mod.compile_sources("simulate", rel_files)
                if not rel_files:
                    return {"error": "no_override_sources"}
                notes.extend(manifest_mod.override_drop_notes("simulate", manifest_files, rel_files))
            else:
                rel_files = manifest_files
            if not rel_files:
                return {"error": "no_files"}
            call_id = _ui_log_call(workspace, session_id, "run_simulation", {
                "verilog_files": rel_files, "top_module": top, "mode": body.mode,
            })
            sim_run = run_sim_isolated(
                workspace=workspace,
                verilog_files=rel_files,
                top_module=top,
                mode=body.mode,
                run_id=body.runId,
                platform=manifest.platform,
            )
            passed = sim_run.get("status") == "passed"
            _ui_log_result(
                workspace, session_id, "run_simulation", call_id,
                {"run_id": sim_run.get("id"), "status": sim_run.get("status"),
                 "vcdPath": sim_run.get("vcdPath")},
                ok=passed,
            )
            return {"simRun": sim_run, "warnings": [*notes, *_compile_set_warnings(workspace, rel_files)]}

        out = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity, mutates=True)
        if out.get("error") == "no_sim_top":
            _err("no_sim_top", "No simTop in the manifest and none provided.", status=400)
        if out.get("error") == "bad_files":
            _err("invalid_files", out.get("message", "Invalid files override."), status=400)
        if out.get("error") == "no_override_sources":
            _err("no_files", "The files override contains no .v/.sv/.vh/.svh sources to simulate.", status=400)
        if out.get("error") == "no_files":
            _err("no_files", "Manifest has no rtl/tb files to simulate.", status=400)
        return _ok({"run": out["simRun"], "manifestWarnings": out["warnings"]})

    # ---- Synthesize (async job + poll) -------------------------------------

    @router.post("/synthesize")
    async def synthesize_action(session_id: str, body: SynthesizeRequest, identity=Depends(require_signed_in)):
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)

        def work():
            manifest = manifest_mod.read_manifest(workspace, session_id)
            top = body.synthTop or manifest.synthTop
            if not top:
                return {"error": "no_synth_top"}
            rel_files = manifest_mod.files_for_stage(manifest, "synthesize")
            manifest_src = [f for f in rel_files if f.lower().endswith(manifest_mod.RTL_EXTS)]
            notes: List[str] = []
            if body.verilogFiles:
                try:
                    resolved_files = resolve_workspace_files(
                        workspace, body.verilogFiles, exts=manifest_mod.RTL_EXTS
                    )
                except FileResolutionError as exc:
                    return {"error": "bad_files", "message": str(exc)}
                # Same .v/.sv filter the manifest path applies — but an
                # explicitly overridden file must never vanish silently: the
                # shared helper names each one it drops (the wrapper calls it too).
                src_files, notes = manifest_mod.compile_sources("synthesize", resolved_files)
                notes.extend(manifest_mod.override_drop_notes("synthesize", manifest_src, src_files))
                if not src_files:
                    return {"error": "no_override_sources"}
            else:
                src_files = manifest_src
            if not src_files:
                return {"error": "no_files"}
            abs_files = [os.path.join(workspace, f) for f in src_files]
            resolved = {
                "verilog_files": src_files,
                "top_module": top,
                "platform": body.platform or manifest.platform,
                "clock_period_ns": body.clockPeriodNs or manifest.clockPeriodNs,
                "utilization": body.utilization,
                "aspect_ratio": body.aspectRatio,
                "core_margin": body.coreMargin,
                "run_equiv": body.runEquiv,
                "constraints_mode": body.constraintsMode,
                "max_stage": body.maxStage,
            }
            call_id = _ui_log_call(workspace, session_id, "start_synthesis", resolved)
            result = start_synthesis_job(
                workspace=workspace,
                verilog_files=abs_files,
                top_module=top,
                platform=resolved["platform"],
                clock_period_ns=resolved["clock_period_ns"],
                utilization=body.utilization,
                aspect_ratio=body.aspectRatio,
                core_margin=body.coreMargin,
                run_equiv=body.runEquiv,
                constraints_mode=body.constraintsMode,
                max_stage=body.maxStage,
            )
            dispatched = isinstance(result, dict) and result.get("status") != "rejected"
            _ui_log_result(
                workspace, session_id, "start_synthesis", call_id,
                {"run_id": (result or {}).get("run_id"),
                 "status": (result or {}).get("status")},
                ok=dispatched,
            )
            return {"result": result, "warnings": [*notes, *_compile_set_warnings(workspace, src_files)]}

        out = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity, mutates=True)
        if out.get("error") == "no_synth_top":
            _err("no_synth_top", "No synthTop in the manifest and none provided.", status=400)
        if out.get("error") == "bad_files":
            _err("invalid_files", out.get("message", "Invalid verilogFiles override."), status=400)
        if out.get("error") == "no_override_sources":
            _err("no_files", "The verilogFiles override contains no .v/.sv sources to synthesize.", status=400)
        if out.get("error") == "no_files":
            _err("no_files", "Manifest has no rtl files to synthesize.", status=400)
        result = out["result"]
        # Quota is enforced inside start_synthesis_job; surface a cap hit as 429.
        if isinstance(result, dict) and result.get("status") == "rejected":
            _err((result.get("error") or {}).get("code", "quota_exceeded"),
                 (result.get("error") or {}).get("message", "Quota exceeded."),
                 details=result.get("error"), status=429)
        # Validation errors (e.g. an unsupported maxStage) surface as 400.
        if isinstance(result, dict) and result.get("status") == "error":
            _err("invalid_request", result.get("message", "Invalid synthesis request."),
                 details={"supported_stages": result.get("supported_stages")}, status=400)
        return _ok({"runId": result.get("run_id"), "pollAfterSec": result.get("poll_after_sec"),
                    "raw": result, "manifestWarnings": out["warnings"]})

    # ---- Activity feed (unified per-session tool event log) -----------------

    @router.get("/activity")
    async def get_activity(
        session_id: str,
        limit: int = Query(default=100, ge=1, le=500),
        before: Optional[str] = Query(default=None),
        identity=Depends(get_identity),
    ):
        """Newest-first page of every tool invocation in this session — agent
        (WS), user (these REST actions), and MCP — paired call+result events
        from attempt_events.jsonl. ``before`` pages older; ``nextBefore`` is
        null at the end."""
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)
        page = await run_scoped(session_id, workspace, read_activity, workspace, limit, before, _uid=uid, _id=identity)
        return _ok(page)

    # ---- Directory tree (lazy, VS Code-web style) ----------------------------

    @router.get("/dir")
    async def get_dir(
        session_id: str,
        path: str = Query(default=""),
        recursive: Optional[str] = Query(default=None),
        identity=Depends(get_identity),
    ):
        """Immediate children of one directory (default), or — with
        ``?recursive=paths`` — the flat file-path index for quick-open."""
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)

        if recursive == "paths":
            out = await run_scoped(session_id, workspace, workspace_fs.walk_paths, workspace, _uid=uid, _id=identity)
            return _ok(out)

        def work():
            return workspace_fs.list_dir(workspace, path)

        try:
            entries = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity)
        except (FileNotFoundError, NotADirectoryError):
            _err("not_found", f"Directory not found: {path or '.'}", status=404)
        except ValueError:
            _err("invalid_path", f"Path escapes the workspace: {path}", status=404)
        return _ok({"path": path, "entries": entries})

    # ---- Tool platform (the Command Surface) ---------------------------------
    # The catalog and execution both come from the SAME registry the agent and
    # MCP clients use (src/api/tool_catalog.py introspects the @tool wrappers),
    # so schemas can never drift between the UI and the backend.

    @router.get("/tools")
    async def list_tools(session_id: str, identity=Depends(get_identity)):
        """Every UI-invocable tool with its real JSON Schema + policy flags."""
        require_owned(session_id, identity)
        await require_workspace(session_id)
        try:
            catalog = await asyncio.to_thread(tool_catalog.build_catalog)
        except ImportError:
            _err("tools_unavailable", "The agent tool stack is not installed on this server.", status=503)
        return _ok({"tools": catalog})

    @router.post("/invoke")
    async def invoke_tool(session_id: str, body: InvokeRequest, identity=Depends(get_identity)):
        """Run one catalogued tool: schema-validated against the tool's own
        pydantic model, executed via the SAME wrapper function the agent runs,
        inside this session's scope. Logged to the per-session event log like
        every other invocation path (source ui)."""
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)

        try:
            known = await asyncio.to_thread(tool_catalog.is_invocable, body.tool)
        except ImportError:
            known = False
        if not known:
            _err("unknown_tool", f"'{body.tool}' is not an invocable tool.", status=404)
        flags = tool_catalog.tool_flags(body.tool)
        if flags["requiresSignIn"] and getattr(identity, "anonymous", False):
            _err("signin_required", f"'{body.tool}' requires signing in.", status=401)

        def work():
            call_id = _ui_log_call(workspace, session_id, body.tool, body.arguments or {})
            try:
                result = tool_catalog.validate_and_execute(body.tool, workspace, body.arguments)
            except tool_catalog.ToolArgumentError as exc:
                _ui_log_result(workspace, session_id, body.tool, call_id, str(exc), ok=False)
                return {"argError": exc}
            except Exception as exc:  # the tool itself failed — an honest error result
                _ui_log_result(workspace, session_id, body.tool, call_id, str(exc), ok=False)
                return {"error": str(exc)}
            # Wrapper tools return strings (often JSON) — parse structured
            # payloads back out so the UI gets typed results, not double-encoded
            # text. Failures are signalled via a status field when structured.
            parsed = result
            if isinstance(result, str):
                text = result.strip()
                if text.startswith("{") or text.startswith("["):
                    try:
                        parsed = json.loads(text)
                    except ValueError:
                        parsed = result
            summary = result if isinstance(result, str) else json.dumps(result)
            ok = not (isinstance(parsed, dict) and str(parsed.get("status", "")).lower() in ("error", "fail", "failed"))
            _ui_log_result(workspace, session_id, body.tool, call_id, summary[:2000], ok=ok)
            return {"result": parsed}

        out = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity, mutates=flags["mutates"])
        if "argError" in out:
            exc = out["argError"]
            _err("invalid_arguments", str(exc), details={"fields": exc.details}, status=400)
        if "error" in out:
            _err("tool_failed", out["error"], status=502)
        return _ok({"tool": body.tool, "result": out["result"]})

    # ---- Workbench snapshot (F4: one hydration, one response) ---------------

    @router.get("/workbench")
    async def workbench_snapshot(session_id: str, identity=Depends(get_identity)):
        """Hydrate the workspace ONCE and return everything the workbench needs on
        open — manifest + runs + files + spec + code + report — in a single
        response, replacing the ~18-call fan-out (each of which, in hosted, was a
        separate GCS download). A read: mutates=False, so it never uploads."""
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)

        def work():
            manifest = manifest_mod.read_manifest(workspace, session_id)
            roles = {f.path: f.role for f in manifest.files}
            runs: List[Dict[str, Any]] = list(list_sim_runs(workspace))
            runs.extend(_synth_to_run(workspace, item) for item in list_synthesis_runs(workspace))
            runs.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
            return {
                "manifest": manifest.model_dump(),
                "runs": runs,
                "files": _snapshot_files(workspace, roles, manifest.ignore),
                "spec": _snapshot_spec(workspace, manifest.ignore),
                "code": _snapshot_code(workspace, manifest),
                "report": _snapshot_report(workspace),
                "synthesisRuns": list(list_synthesis_runs(workspace)),
                # v2 additions — same shapes as GET /activity and GET /dir, so
                # the first paint of the Activity dock and file tree costs no
                # extra round trips.
                "activity": read_activity(workspace, limit=50)["events"],
                "rootDir": workspace_fs.list_dir(workspace, ""),
            }

        snap = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity)
        return _ok(snap)

    # ---- Unified runs -------------------------------------------------------

    @router.get("/runs")
    async def list_runs(session_id: str, kind: str = Query(default="all"), identity=Depends(get_identity)):
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)

        def work():
            runs: List[Dict[str, Any]] = []
            if kind in ("all", "sim"):
                runs.extend(list_sim_runs(workspace))
            if kind in ("all", "synth"):
                runs.extend(_synth_to_run(workspace, item) for item in list_synthesis_runs(workspace))
            runs.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
            return runs

        runs = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity)
        return _ok({"runs": runs})

    @router.get("/runs/compare")
    async def compare_runs(session_id: str, a: str = Query(...), b: str = Query(...), identity=Depends(get_identity)):
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)

        def work():
            return (
                get_synthesis_metrics(workspace=workspace, run_id=a),
                get_synthesis_metrics(workspace=workspace, run_id=b),
            )

        ma, mb = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity)
        metric_keys = [
            ("area_um2", "Area (µm²)"),
            ("cell_count", "Cells"),
            ("wns_ns", "WNS (ns)"),
            ("tns_ns", "TNS (ns)"),
            ("power_mw", "Power (mW)"),
        ]
        # get_synthesis_metrics returns the PPA fields NESTED under "metrics";
        # the wrapper's top level carries status/run_id/sources. Reading the
        # wrapper made every value and deltaPct in this diff None.
        pa = (ma or {}).get("metrics") or {}
        pb = (mb or {}).get("metrics") or {}
        rows = []
        for key, label in metric_keys:
            va = pa.get(key)
            vb = pb.get(key)
            delta_pct = None
            try:
                if va not in (None, 0) and vb is not None:
                    delta_pct = round((float(vb) - float(va)) / abs(float(va)) * 100, 2)
            except (TypeError, ValueError):
                delta_pct = None
            rows.append({"metric": label, "a": va, "b": vb, "deltaPct": delta_pct})
        return _ok({"diff": {"a": a, "b": b, "rows": rows}})

    @router.get("/runs/{run_id}")
    async def get_run(session_id: str, run_id: str, identity=Depends(get_identity)):
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)

        def work():
            if run_id.startswith("sim_"):
                return {"kind": "sim", "run": get_sim_run(workspace, run_id)}
            return {
                "kind": "synth",
                # Unified self-healing status payload (Wave 9) — the same
                # answer every other surface gets.
                "status": get_synthesis_status(run_id, workspace=workspace),
                "metrics": get_synthesis_metrics(workspace=workspace, run_id=run_id),
            }

        out = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity)
        if out["kind"] == "sim":
            if not out["run"]:
                _err("not_found", f"Sim run {run_id} not found.", status=404)
            return _ok({"run": out["run"]})

        status = out["status"] or {}
        metrics_resp = out["metrics"] or {}
        if status.get("error") == "unknown_run":
            _err("not_found", f"Run {run_id} not found.", status=404)
        # get_synthesis_metrics returns the PPA fields NESTED under "metrics"
        # (the top-level dict is the wrapper: status/run_id/metrics/...). Read the
        # inner dict so areaUm2/cells/etc are actually populated.
        metrics = metrics_resp.get("metrics") or {}
        ppa = {
            "areaUm2": metrics.get("area_um2"),
            "cells": metrics.get("cell_count"),
            "wnsNs": metrics.get("wns_ns"),
            "tnsNs": metrics.get("tns_ns"),
            "fmaxMhz": metrics.get("fmax_mhz"),
            "powerMw": metrics.get("power_mw"),
            # Must mirror _synth_to_run's card payload exactly — see the note there.
            "worstSlackNs": metrics.get("worst_slack_ns"),
            "timingMet": metrics.get("timing_met"),
            "timingCorner": metrics.get("timing_corner"),
            "timingNote": metrics.get("timing_note"),
        } if metrics else None
        return _ok({"run": {
            "id": run_id,
            "kind": "synth",
            "status": _SYNTH_STATUS_MAP.get(status.get("status") or "", "running"),
            "top": status.get("top_module"),
            "stages": status.get("stages"),
            "stageHistory": status.get("stage_history"),
            "currentStage": status.get("current_stage"),
            "ppa": ppa,
        }})

    @router.get("/runs/{run_id}/status")
    async def get_run_status(session_id: str, run_id: str, identity=Depends(get_identity)):
        """Full self-healing status by run_id — the ONE key (Wave 9). A plain
        read for callers; reconciliation persists durably on its own."""
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)
        status = await run_scoped(session_id, workspace, get_synthesis_status, run_id, workspace, _uid=uid, _id=identity)
        return _ok({"job": status})

    @router.post("/runs/{run_id}/retry")
    async def retry_run(session_id: str, run_id: str, body: RetryRequest, identity=Depends(require_signed_in)):
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)
        overrides_json = json.dumps(body.overrides) if body.overrides else ""

        def work():
            call_id = _ui_log_call(workspace, session_id, "retry_pd", {
                "run_id": run_id, "start_stage": body.fromStage, "max_stage": body.maxStage,
            })
            result = retry_pd_job(
                workspace=workspace,
                source_run_id=run_id,
                start_stage=body.fromStage,
                max_stage=body.maxStage,
                orfs_overrides_json=overrides_json,
            )
            dispatched = isinstance(result, dict) and result.get("status") != "rejected"
            _ui_log_result(
                workspace, session_id, "retry_pd", call_id,
                {"run_id": (result or {}).get("run_id"),
                 "status": (result or {}).get("status")},
                ok=dispatched,
            )
            return result

        result = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity, mutates=True)
        if isinstance(result, dict) and result.get("status") == "rejected":
            _err((result.get("error") or {}).get("code", "quota_exceeded"),
                 (result.get("error") or {}).get("message", "Quota exceeded."),
                 details=result.get("error"), status=429)
        # Validation errors (unsupported stage, missing source run/prereqs)
        # surface as 400, exactly like /synthesize does.
        if isinstance(result, dict) and result.get("status") == "error":
            _err("invalid_request", result.get("message", "Invalid retry request."),
                 details={"supported_stages": result.get("supported_stages")}, status=400)
        return _ok({"runId": result.get("run_id"), "pollAfterSec": result.get("poll_after_sec"), "raw": result})

    @router.post("/runs/{run_id}/pin")
    async def pin_run(session_id: str, run_id: str, body: PinRequest, identity=Depends(require_signed_in)):
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)

        def work():
            if run_id.startswith("sim_"):
                return set_sim_run_pinned(workspace, run_id, body.pinned)
            run_dir = get_run_dir(workspace, run_id)
            if not run_dir:
                return None
            meta_path = os.path.join(run_dir, "run_meta.json")
            meta: Dict[str, Any] = {}
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                except Exception:
                    meta = {}
            meta["pinned"] = body.pinned
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
            return {"run_id": run_id, "pinned": body.pinned}

        result = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity, mutates=True)
        if not result:
            _err("not_found", f"Run {run_id} not found.", status=404)
        return _ok({"runId": run_id, "pinned": body.pinned})

    return router
