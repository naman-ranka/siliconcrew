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

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from src.api.activity import read_activity
from src.api import workspace_fs
from src.api import tool_catalog
from src.utils.attempt_logger import log_tool_call, log_tool_result
from src.utils.session_context import SessionContext, session_scope
from src.utils.paths import is_within
from src.platform_engines import auth as _auth_engine
from src.tools import manifest as manifest_mod
from src.tools import file_ops
from src.tools.run_linter import run_linter
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
    get_synthesis_job_status,
    get_synthesis_metrics,
    get_stage_status,
)

WorkspaceResolver = Callable[[str], str]


# --- Request bodies (camelCase, per data-model.md) --------------------------

class ManifestUpdate(BaseModel):
    synthTop: Optional[str] = None
    simTop: Optional[str] = None
    clockPeriodNs: Optional[float] = None
    platform: Optional[str] = None
    files: Optional[List[Dict[str, Any]]] = None


class SimulateRequest(BaseModel):
    simTop: Optional[str] = None
    mode: str = "rtl"
    runId: Optional[str] = None


class SynthesizeRequest(BaseModel):
    synthTop: Optional[str] = None
    platform: Optional[str] = None
    clockPeriodNs: Optional[float] = None
    utilization: int = 5
    aspectRatio: float = 1.0
    coreMargin: float = 2.0
    runEquiv: bool = False
    constraintsMode: str = "auto"


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
    }


def _parse_lint_output(stderr: str):
    """Parse iverilog diagnostics into structured warnings/errors + byFile."""
    pat = re.compile(
        r"^(?P<file>[^:\n]+):(?P<line>\d+):(?:\d+:)?\s*(?P<sev>error|warning|syntax error)?:?\s*(?P<msg>.*)$"
    )
    warnings: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []
    by_file: Dict[str, List[Dict[str, Any]]] = {}
    for line in (stderr or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = pat.match(stripped)
        if not m:
            if "error" in stripped.lower():
                errors.append({"line": None, "severity": "error", "message": stripped})
            continue
        sev_raw = (m.group("sev") or "error").lower()
        severity = "warning" if sev_raw == "warning" else "error"
        fname = os.path.basename(m.group("file"))
        entry = {
            "line": int(m.group("line")),
            "severity": severity,
            "message": m.group("msg").strip() or stripped,
        }
        by_file.setdefault(fname, []).append(entry)
        (warnings if severity == "warning" else errors).append({**entry, "file": fname})
    return warnings, errors, by_file


def _classify_file(name: str) -> str:
    """FileInfo.type classification — mirrors api.py's list_workspace_files."""
    ext = os.path.splitext(name)[1].lower()
    if ext in (".v", ".sv"):
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


def _snapshot_files(workspace: str, roles: Dict[str, Optional[str]]) -> List[Dict[str, Any]]:
    """FileInfo[] for the workbench snapshot (same shape as GET /files)."""
    import datetime as _dt

    out: List[Dict[str, Any]] = []
    for item in os.listdir(workspace):
        item_path = os.path.join(workspace, item)
        if not os.path.isfile(item_path):
            continue
        st = os.stat(item_path)
        out.append({
            "name": item,
            "path": item_path,
            "type": _classify_file(item),
            "size": st.st_size,
            "modified": _dt.datetime.fromtimestamp(st.st_mtime).isoformat(),
            "role": roles.get(item),
        })
    out.sort(key=lambda f: f["modified"], reverse=True)
    return out


def _snapshot_spec(workspace: str) -> Optional[Dict[str, Any]]:
    """Latest *_spec.yaml as {filename, content, parsed} — same as GET /spec."""
    import yaml as _yaml

    spec_files = sorted(
        [f for f in os.listdir(workspace) if f.endswith("_spec.yaml")],
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


def _snapshot_code(workspace: str) -> List[Dict[str, Any]]:
    """All .v/.sv files as CodeFile[] — same shape as GET /code."""
    files = sorted(
        f for f in os.listdir(workspace)
        if f.endswith((".v", ".sv")) and os.path.isfile(os.path.join(workspace, f))
    )
    out: List[Dict[str, Any]] = []
    for name in files:
        with open(os.path.join(workspace, name), "r", errors="ignore") as f:
            out.append({
                "filename": name,
                "content": f.read(),
                "language": "systemverilog" if name.endswith(".sv") else "verilog",
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
        manifest = await run_scoped(session_id, workspace, manifest_mod.write_manifest, workspace, updates, session_id, _uid=uid, _id=identity, mutates=True)
        return _ok({"manifest": manifest.model_dump()})

    @router.post("/files")
    async def upload_files(session_id: str, files: List[UploadFile] = File(...), identity=Depends(require_signed_in)):
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)
        os.makedirs(workspace, exist_ok=True)

        saved: List[str] = []
        for upload in files:
            name = os.path.basename(upload.filename or "")
            if not name:
                continue
            dest = os.path.join(workspace, name)
            if not is_within(workspace, dest):
                _err("invalid_path", f"Refusing to write outside the workspace: {name}", status=400)
            content = await upload.read()
            with open(dest, "wb") as f:
                f.write(content)
            saved.append(name)

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
    async def lint_action(session_id: str, identity=Depends(get_identity)):
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)

        def work():
            manifest = manifest_mod.read_manifest(workspace, session_id)
            rel_files = manifest_mod.files_for_stage(manifest, "lint")
            if not rel_files:
                return {"empty": True}
            call_id = _ui_log_call(workspace, session_id, "linter_tool", {"verilog_files": rel_files})
            abs_files = [os.path.join(workspace, f) for f in rel_files]
            result = run_linter(abs_files, cwd=workspace)
            warnings, errors, by_file = _parse_lint_output(result.get("stderr", ""))
            passed = bool(result.get("success"))
            _ui_log_result(
                workspace, session_id, "linter_tool", call_id,
                {"status": "passed" if passed else "failed",
                 "warnings": len(warnings), "errors": len(errors)},
                ok=passed,
            )
            return {
                "empty": False,
                "result": result,
                "files": rel_files,
                "warnings": warnings,
                "errors": errors,
                "byFile": by_file,
            }

        # mutates=True: lint itself is a read, but it now records itself in the
        # per-session event log (attempt_events.jsonl), which must persist.
        out = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity, mutates=True)
        if out.get("empty"):
            _err("no_rtl", "No RTL files in the manifest to lint.", status=400)

        result = out["result"]
        return _ok({
            "status": "passed" if result.get("success") else "failed",
            "warnings": out["warnings"],
            "errors": out["errors"],
            "byFile": out["byFile"],
            "command": result.get("command", ""),
            "files": out["files"],
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
            rel_files = manifest_mod.files_for_stage(manifest, "simulate")
            if not rel_files:
                return {"error": "no_files"}
            call_id = _ui_log_call(workspace, session_id, "run_isolated_simulation", {
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
                workspace, session_id, "run_isolated_simulation", call_id,
                {"run_id": sim_run.get("id"), "status": sim_run.get("status"),
                 "vcdPath": sim_run.get("vcdPath")},
                ok=passed,
            )
            return {"simRun": sim_run}

        out = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity, mutates=True)
        if out.get("error") == "no_sim_top":
            _err("no_sim_top", "No simTop in the manifest and none provided.", status=400)
        if out.get("error") == "no_files":
            _err("no_files", "Manifest has no rtl/tb files to simulate.", status=400)
        return _ok({"run": out["simRun"]})

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
            src_files = [f for f in rel_files if f.lower().endswith((".v", ".sv"))]
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
            )
            dispatched = isinstance(result, dict) and result.get("status") != "rejected"
            _ui_log_result(
                workspace, session_id, "start_synthesis", call_id,
                {"job_id": (result or {}).get("job_id"), "run_id": (result or {}).get("run_id"),
                 "status": (result or {}).get("status")},
                ok=dispatched,
            )
            return {"result": result}

        out = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity, mutates=True)
        if out.get("error") == "no_synth_top":
            _err("no_synth_top", "No synthTop in the manifest and none provided.", status=400)
        if out.get("error") == "no_files":
            _err("no_files", "Manifest has no rtl files to synthesize.", status=400)
        result = out["result"]
        # Quota is enforced inside start_synthesis_job; surface a cap hit as 429.
        if isinstance(result, dict) and result.get("status") == "rejected":
            _err((result.get("error") or {}).get("code", "quota_exceeded"),
                 (result.get("error") or {}).get("message", "Quota exceeded."),
                 details=result.get("error"), status=429)
        return _ok({"jobId": result.get("job_id"), "runId": result.get("run_id"), "raw": result})

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
            roles = {f.name: f.role for f in manifest.files}
            runs: List[Dict[str, Any]] = list(list_sim_runs(workspace))
            runs.extend(_synth_to_run(workspace, item) for item in list_synthesis_runs(workspace))
            runs.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
            return {
                "manifest": manifest.model_dump(),
                "runs": runs,
                "files": _snapshot_files(workspace, roles),
                "spec": _snapshot_spec(workspace),
                "code": _snapshot_code(workspace),
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
        rows = []
        for key, label in metric_keys:
            va = (ma or {}).get(key)
            vb = (mb or {}).get(key)
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
                "status": get_stage_status(workspace=workspace, run_id=run_id),
                "metrics": get_synthesis_metrics(workspace=workspace, run_id=run_id),
            }

        out = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity)
        if out["kind"] == "sim":
            if not out["run"]:
                _err("not_found", f"Sim run {run_id} not found.", status=404)
            return _ok({"run": out["run"]})

        status = out["status"] or {}
        metrics_resp = out["metrics"] or {}
        # get_stage_status returns {"status": "error", ...} when the run is missing
        # (its "status" key is the CALL status, not the run status — the run's
        # actual lifecycle state lives in "run_status").
        if status.get("status") == "error" and not metrics_resp:
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
        } if metrics else None
        return _ok({"run": {
            "id": run_id,
            "kind": "synth",
            # Map from run_status (the run's lifecycle), not "status" (the call
            # status, which is always "ok" on success → would mis-map to running).
            "status": _SYNTH_STATUS_MAP.get(status.get("run_status") or "", "running"),
            "top": status.get("top_module"),
            "stages": status.get("stages"),
            "currentStage": status.get("current_stage"),
            "ppa": ppa,
        }})

    @router.get("/jobs/{job_id}")
    async def get_job(session_id: str, job_id: str, identity=Depends(get_identity)):
        uid = require_owned(session_id, identity)
        workspace = await require_workspace(session_id)
        status = await run_scoped(session_id, workspace, get_synthesis_job_status, job_id, workspace, _uid=uid, _id=identity)
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
                {"job_id": (result or {}).get("job_id"), "run_id": (result or {}).get("run_id"),
                 "status": (result or {}).get("status")},
                ok=dispatched,
            )
            return result

        result = await run_scoped(session_id, workspace, work, _uid=uid, _id=identity, mutates=True)
        if isinstance(result, dict) and result.get("status") == "rejected":
            _err((result.get("error") or {}).get("code", "quota_exceeded"),
                 (result.get("error") or {}).get("message", "Quota exceeded."),
                 details=result.get("error"), status=429)
        return _ok({"jobId": result.get("job_id"), "runId": result.get("run_id"), "raw": result})

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
