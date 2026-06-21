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

Field names follow ``data-model.md`` (camelCase) so JSON crosses to the
TypeScript types unchanged.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel

from src.utils.session_context import SessionContext, session_scope
from src.tools import manifest as manifest_mod
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


# --- Shared helpers ---------------------------------------------------------

def _ok(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, **payload}


def _err(code: str, message: str, details: Optional[Dict[str, Any]] = None, status: int = 400):
    raise HTTPException(
        status_code=status,
        detail={"ok": False, "error": {"code": code, "message": message, "details": details or {}}},
    )


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
        ppa = {
            "areaUm2": metrics.get("area_um2") or metrics.get("areaUm2"),
            "cells": metrics.get("cell_count") or metrics.get("cells"),
            "wnsNs": metrics.get("wns_ns") or metrics.get("wnsNs"),
            "tnsNs": metrics.get("tns_ns") or metrics.get("tnsNs"),
            "fmaxMhz": metrics.get("fmax_mhz") or metrics.get("fmaxMhz"),
            "powerMw": metrics.get("power_mw") or metrics.get("powerMw"),
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


def build_actions_router(resolve_workspace: WorkspaceResolver) -> APIRouter:
    """Build the action router.

    ``resolve_workspace(session_id) -> path`` maps a session to its workspace
    directory. Phase 1 passes ``session_manager.get_workspace_path``; Phase 2
    swaps in a cloud-backed resolver — no handler changes required.
    """
    router = APIRouter(prefix="/api/workspace/{session_id:path}", tags=["actions"])

    def require_workspace(session_id: str) -> str:
        workspace = resolve_workspace(session_id)
        if not workspace or not os.path.exists(workspace):
            raise HTTPException(status_code=404, detail="Session not found")
        return workspace

    async def run_scoped(session_id: str, workspace: str, fn, *args, **kwargs):
        """Run a sync tool call bound to this request's SessionContext, off-thread.

        ``asyncio.to_thread`` copies the contextvar into the worker thread, so
        any tool reading ``get_workspace_path()`` sees this session and the
        blocking EDA work never stalls the event loop.
        """
        ctx = SessionContext(session_id=session_id, workspace=workspace)

        def runner():
            with session_scope(ctx):
                return fn(*args, **kwargs)

        return await asyncio.to_thread(runner)

    # ---- Design manifest ----------------------------------------------------

    @router.get("/manifest")
    async def get_manifest(session_id: str):
        workspace = require_workspace(session_id)
        manifest = await run_scoped(session_id, workspace, manifest_mod.read_manifest, workspace, session_id)
        return _ok({"manifest": manifest.model_dump()})

    @router.put("/manifest")
    async def put_manifest(session_id: str, body: ManifestUpdate):
        workspace = require_workspace(session_id)
        updates = {k: v for k, v in body.model_dump().items() if v is not None}
        manifest = await run_scoped(session_id, workspace, manifest_mod.write_manifest, workspace, updates, session_id)
        return _ok({"manifest": manifest.model_dump()})

    @router.post("/files")
    async def upload_files(session_id: str, files: List[UploadFile] = File(...)):
        workspace = require_workspace(session_id)
        os.makedirs(workspace, exist_ok=True)
        real_ws = os.path.realpath(workspace)

        saved: List[str] = []
        for upload in files:
            name = os.path.basename(upload.filename or "")
            if not name:
                continue
            dest = os.path.join(workspace, name)
            if not os.path.realpath(dest).startswith(real_ws):
                _err("invalid_path", f"Refusing to write outside the workspace: {name}", status=400)
            content = await upload.read()
            with open(dest, "wb") as f:
                f.write(content)
            saved.append(name)

        manifest = await run_scoped(session_id, workspace, manifest_mod.read_manifest, workspace, session_id)
        return _ok({"uploaded": saved, "manifest": manifest.model_dump()})

    # ---- Lint ---------------------------------------------------------------

    @router.post("/lint")
    async def lint_action(session_id: str):
        workspace = require_workspace(session_id)

        def work():
            manifest = manifest_mod.read_manifest(workspace, session_id)
            rel_files = manifest_mod.files_for_stage(manifest, "lint")
            if not rel_files:
                return {"empty": True}
            abs_files = [os.path.join(workspace, f) for f in rel_files]
            return {"empty": False, "result": run_linter(abs_files, cwd=workspace), "files": rel_files}

        out = await run_scoped(session_id, workspace, work)
        if out.get("empty"):
            _err("no_rtl", "No RTL files in the manifest to lint.", status=400)

        result = out["result"]
        warnings, errors, by_file = _parse_lint_output(result.get("stderr", ""))
        return _ok({
            "status": "passed" if result.get("success") else "failed",
            "warnings": warnings,
            "errors": errors,
            "byFile": by_file,
            "command": result.get("command", ""),
            "files": out["files"],
        })

    # ---- Simulate (sync, isolated run) -------------------------------------

    @router.post("/simulate")
    async def simulate_action(session_id: str, body: SimulateRequest):
        workspace = require_workspace(session_id)

        def work():
            manifest = manifest_mod.read_manifest(workspace, session_id)
            top = body.simTop or manifest.simTop
            if not top:
                return {"error": "no_sim_top"}
            rel_files = manifest_mod.files_for_stage(manifest, "simulate")
            if not rel_files:
                return {"error": "no_files"}
            sim_run = run_sim_isolated(
                workspace=workspace,
                verilog_files=rel_files,
                top_module=top,
                mode=body.mode,
                run_id=body.runId,
                platform=manifest.platform,
            )
            return {"simRun": sim_run}

        out = await run_scoped(session_id, workspace, work)
        if out.get("error") == "no_sim_top":
            _err("no_sim_top", "No simTop in the manifest and none provided.", status=400)
        if out.get("error") == "no_files":
            _err("no_files", "Manifest has no rtl/tb files to simulate.", status=400)
        return _ok({"run": out["simRun"]})

    # ---- Synthesize (async job + poll) -------------------------------------

    @router.post("/synthesize")
    async def synthesize_action(session_id: str, body: SynthesizeRequest):
        workspace = require_workspace(session_id)

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
            result = start_synthesis_job(
                workspace=workspace,
                verilog_files=abs_files,
                top_module=top,
                platform=body.platform or manifest.platform,
                clock_period_ns=body.clockPeriodNs or manifest.clockPeriodNs,
                utilization=body.utilization,
                aspect_ratio=body.aspectRatio,
                core_margin=body.coreMargin,
                run_equiv=body.runEquiv,
                constraints_mode=body.constraintsMode,
            )
            return {"result": result}

        out = await run_scoped(session_id, workspace, work)
        if out.get("error") == "no_synth_top":
            _err("no_synth_top", "No synthTop in the manifest and none provided.", status=400)
        if out.get("error") == "no_files":
            _err("no_files", "Manifest has no rtl files to synthesize.", status=400)
        result = out["result"]
        return _ok({"jobId": result.get("job_id"), "runId": result.get("run_id"), "raw": result})

    # ---- Unified runs -------------------------------------------------------

    @router.get("/runs")
    async def list_runs(session_id: str, kind: str = Query(default="all")):
        workspace = require_workspace(session_id)

        def work():
            runs: List[Dict[str, Any]] = []
            if kind in ("all", "sim"):
                runs.extend(list_sim_runs(workspace))
            if kind in ("all", "synth"):
                runs.extend(_synth_to_run(workspace, item) for item in list_synthesis_runs(workspace))
            runs.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
            return runs

        runs = await run_scoped(session_id, workspace, work)
        return _ok({"runs": runs})

    @router.get("/runs/compare")
    async def compare_runs(session_id: str, a: str = Query(...), b: str = Query(...)):
        workspace = require_workspace(session_id)

        def work():
            return (
                get_synthesis_metrics(workspace=workspace, run_id=a),
                get_synthesis_metrics(workspace=workspace, run_id=b),
            )

        ma, mb = await run_scoped(session_id, workspace, work)
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
    async def get_run(session_id: str, run_id: str):
        workspace = require_workspace(session_id)

        def work():
            if run_id.startswith("sim_"):
                return {"kind": "sim", "run": get_sim_run(workspace, run_id)}
            return {
                "kind": "synth",
                "status": get_stage_status(workspace=workspace, run_id=run_id),
                "metrics": get_synthesis_metrics(workspace=workspace, run_id=run_id),
            }

        out = await run_scoped(session_id, workspace, work)
        if out["kind"] == "sim":
            if not out["run"]:
                _err("not_found", f"Sim run {run_id} not found.", status=404)
            return _ok({"run": out["run"]})

        status = out["status"] or {}
        metrics = out["metrics"] or {}
        if status.get("error") and not metrics:
            _err("not_found", f"Run {run_id} not found.", status=404)
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
            "status": _SYNTH_STATUS_MAP.get(status.get("status", ""), "running"),
            "top": status.get("top_module"),
            "stages": status.get("stages"),
            "currentStage": status.get("current_stage"),
            "ppa": ppa,
        }})

    @router.get("/jobs/{job_id}")
    async def get_job(session_id: str, job_id: str):
        workspace = require_workspace(session_id)
        status = await run_scoped(session_id, workspace, get_synthesis_job_status, job_id, workspace)
        return _ok({"job": status})

    @router.post("/runs/{run_id}/retry")
    async def retry_run(session_id: str, run_id: str, body: RetryRequest):
        workspace = require_workspace(session_id)
        overrides_json = json.dumps(body.overrides) if body.overrides else ""

        def work():
            return retry_pd_job(
                workspace=workspace,
                source_run_id=run_id,
                start_stage=body.fromStage,
                max_stage=body.maxStage,
                orfs_overrides_json=overrides_json,
            )

        result = await run_scoped(session_id, workspace, work)
        return _ok({"jobId": result.get("job_id"), "runId": result.get("run_id"), "raw": result})

    @router.post("/runs/{run_id}/pin")
    async def pin_run(session_id: str, run_id: str, body: PinRequest):
        workspace = require_workspace(session_id)

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

        result = await run_scoped(session_id, workspace, work)
        if not result:
            _err("not_found", f"Run {run_id} not found.", status=404)
        return _ok({"runId": run_id, "pinned": body.pinned})

    return router
