"""Isolated, provenance-stamped simulation runs.

Today simulation runs in the workspace ``cwd`` and the VCD from ``$dumpfile``
overwrites the previous one — so sims are neither isolated nor comparable. This
mirrors the synthesis run model (``synth_runs/synth_NNNN/`` + ``index.json`` +
``run_meta.json``) for simulation: every sim gets ``sim_runs/sim_NNNN/`` with
its own VCD, a persisted :class:`SimRun` record, and a stamped provenance block.

The actual compile/run still goes through :func:`run_simulation` (the single
tool) — this module only adds the per-run directory, VCD capture, metadata, and
the run index. Both the REST handler (human click) and the agent tool call the
same entry point, :func:`run_sim_isolated`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.tools.run_simulation import run_simulation

RUNS_DIRNAME = "sim_runs"
INDEX_FILENAME = "index.json"
LATEST_FILENAME = "LATEST"
RUN_META_FILENAME = "run_meta.json"

_ALLOC_LOCK = threading.Lock()
_PROVENANCE_CACHE: Dict[str, Any] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _runs_root(workspace: str) -> str:
    return _ensure_dir(os.path.join(workspace, RUNS_DIRNAME))


def _index_path(workspace: str) -> str:
    return os.path.join(_runs_root(workspace), INDEX_FILENAME)


def _latest_path(workspace: str) -> str:
    return os.path.join(_runs_root(workspace), LATEST_FILENAME)


def _load_index(workspace: str) -> Dict[str, Any]:
    path = _index_path(workspace)
    if not os.path.exists(path):
        return {"runs": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("runs", [])
            return data
    except Exception:
        return {"runs": []}


def _save_index(workspace: str, data: Dict[str, Any]) -> None:
    with open(_index_path(workspace), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _next_run_id(workspace: str) -> str:
    root = _runs_root(workspace)
    existing = [d for d in os.listdir(root) if re.match(r"sim_\d{4}$", d)]
    if not existing:
        return "sim_0001"
    max_id = max(int(x.split("_")[1]) for x in existing)
    return f"sim_{max_id + 1:04d}"


def _allocate_run_dir(workspace: str) -> tuple[str, str]:
    with _ALLOC_LOCK:
        while True:
            run_id = _next_run_id(workspace)
            run_dir = os.path.join(_runs_root(workspace), run_id)
            try:
                os.makedirs(run_dir, exist_ok=False)
                return run_id, run_dir
            except FileExistsError:
                continue


def _set_latest(workspace: str, run_id: str) -> None:
    with open(_latest_path(workspace), "w", encoding="utf-8") as f:
        f.write(run_id)


def _git_commit() -> Optional[str]:
    if "repoCommit" in _PROVENANCE_CACHE:
        return _PROVENANCE_CACHE["repoCommit"]
    commit = None
    try:
        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0:
            commit = out.stdout.strip()
    except Exception:
        commit = None
    _PROVENANCE_CACHE["repoCommit"] = commit
    return commit


def _iverilog_version() -> Optional[str]:
    if "iverilogVersion" in _PROVENANCE_CACHE:
        return _PROVENANCE_CACHE["iverilogVersion"]
    version = None
    try:
        out = subprocess.run(["iverilog", "-V"], capture_output=True, text=True, timeout=5)
        first = (out.stdout or out.stderr or "").splitlines()
        if first:
            m = re.search(r"version\s+(\S+)", first[0])
            version = m.group(1) if m else first[0].strip()
    except Exception:
        version = None
    _PROVENANCE_CACHE["iverilogVersion"] = version
    return version


def _provenance(platform: Optional[str]) -> Dict[str, Any]:
    return {
        "repoCommit": _git_commit(),
        "iverilogVersion": _iverilog_version(),
        "orfsImageDigest": None,
        "pdk": platform,
        "numCores": None,
    }


def _find_vcd(run_dir: str) -> Optional[str]:
    """Return the workspace-relative path of the VCD produced in the run dir."""
    candidates = []
    for name in os.listdir(run_dir):
        if name.endswith(".vcd"):
            candidates.append(os.path.join(run_dir, name))
    if not candidates:
        return None
    # Largest VCD is the real dump if several exist.
    return max(candidates, key=lambda p: os.path.getsize(p))


_RUN_STATUS = {
    "test_passed": "passed",
    "test_failed": "failed",
    "sim_failed": "failed",
    "compile_failed": "failed",
}


def _to_run_status(sim_status: str) -> str:
    return _RUN_STATUS.get(sim_status, "failed")


def sim_status_to_outcome(sim_status: Optional[str]) -> Optional[str]:
    """Fallback semantic outcome for a runner that predates the ``outcome`` field
    (e.g. the test fakes). run_simulation itself now always sets ``outcome``."""
    return sim_status


def _persist_resolution_failure(
    workspace: str,
    sim_run_id: str,
    run_dir: str,
    top_module: str,
    mode: str,
    parent_run_id: Optional[str],
    platform: Optional[str],
    res_err: Any,
) -> Dict[str, Any]:
    """Persist a typed post-synth resolution failure as a SimRun card.

    When the run record can't yield a netlist/platform, the caller gets a
    structured, self-describing record (semantic ``outcome`` + optional
    ``recovery``) — not an exception or a leaked traceback — so the IDE renders
    a card and the agent can branch/recover.
    """
    sim_run: Dict[str, Any] = {
        "id": sim_run_id,
        "kind": "sim",
        "status": "failed",
        "createdAt": _now_iso(),
        "top": top_module,
        "pinned": False,
        "parentRunId": parent_run_id,
        "provenance": _provenance(platform),
        "mode": mode,
        "vcdPath": "",
        "passMarkerFound": False,
        "passMarker": "",
        "failure": {"type": res_err.code, "firstFailureLine": res_err.message, "timeNs": None},
        "resolvedRunId": None,
        "resolvedNetlist": None,
        "stdcellSource": None,
        "outcome": res_err.code,
        "recovery": res_err.recovery,
        "compileCommand": "",
        "simCommand": "",
        "simStatus": "compile_failed",
        "stdoutTail": "",
        "stderrTail": res_err.message,
        "logTruncated": False,
    }
    _persist_run_meta(run_dir, sim_run)
    _append_to_index(workspace, sim_run)
    _set_latest(workspace, sim_run_id)
    return sim_run


def run_sim_isolated(
    workspace: str,
    verilog_files: List[str],
    top_module: str,
    mode: str = "rtl",
    run_id: Optional[str] = None,
    netlist_file: Optional[str] = None,
    platform: Optional[str] = None,
    sim_profile: str = "auto",
    pass_marker: str = "TEST PASSED",
    timeout: int = 60,
    parent_run_id: Optional[str] = None,
    _runner=run_simulation,
) -> Dict[str, Any]:
    """Run a simulation in its own ``sim_runs/sim_NNNN/`` directory.

    ``verilog_files`` are workspace-relative (or absolute) source paths. The
    compile/run executes with ``cwd`` set to the new run directory, so the
    ``$dumpfile`` VCD and the compiled ``a.out`` land inside it and never
    collide with other runs. Returns a :class:`SimRun`-shaped dict (camelCase,
    per data-model.md) plus the raw simulation log fields.
    """
    _ensure_dir(workspace)
    sim_run_id, run_dir = _allocate_run_dir(workspace)

    abs_files: List[str] = []
    for f in verilog_files:
        abs_files.append(f if os.path.isabs(f) else os.path.join(workspace, f))

    abs_netlist = None
    if netlist_file:
        abs_netlist = netlist_file if os.path.isabs(netlist_file) else os.path.join(workspace, netlist_file)

    # Post-synth resolution reads the synthesis run's authoritative *sim
    # contract* from the WORKSPACE run record (issue #52) — never re-discovered
    # under the isolated exec cwd (run_dir). The one resolver serves both the
    # isolated path (here) and the non-isolated run_simulation path. We resolve
    # here and forward the ABSOLUTE netlist + platform so run_simulation does not
    # re-resolve under cwd; cwd=run_dir stays purely for iverilog/vvp execution.
    forward_run_id = run_id
    resolved_run_id: Optional[str] = None
    resolved_netlist: Optional[str] = None
    stdcell_source: Optional[str] = None
    if mode == "post_synth":
        from src.tools.sim_contract import resolve_post_synth

        resolution, res_err = resolve_post_synth(
            workspace=workspace,
            run_id=run_id,
            netlist_file=netlist_file,
            platform=platform,
        )
        if res_err is not None:
            # Typed, semantic failure — a SimRun card, never a leaked traceback.
            return _persist_resolution_failure(
                workspace, sim_run_id, run_dir, top_module, mode,
                parent_run_id, platform, res_err,
            )
        abs_netlist = resolution.netlist_abs
        platform = resolution.platform
        resolved_run_id = resolution.resolved_run_id
        resolved_netlist = resolution.resolved_netlist
        stdcell_source = resolution.stdcell_source
        forward_run_id = None  # already resolved; don't re-resolve under cwd

    created_at = _now_iso()
    sim_result = _runner(
        verilog_files=abs_files,
        top_module=top_module,
        cwd=run_dir,
        mode=mode,
        run_id=forward_run_id,
        netlist_file=abs_netlist,
        platform=platform,
        sim_profile=sim_profile,
        pass_marker=pass_marker,
        timeout=timeout,
    )

    vcd_abs = _find_vcd(run_dir)
    vcd_rel = os.path.relpath(vcd_abs, workspace) if vcd_abs else ""

    status = _to_run_status(sim_result.get("status", "compile_failed"))
    failure = None
    if status == "failed":
        failure = {
            "type": sim_result.get("failure_type") or sim_result.get("status"),
            "firstFailureLine": sim_result.get("first_failure_line"),
            "timeNs": _extract_time_ns(sim_result.get("first_failure_line")),
        }

    sim_run: Dict[str, Any] = {
        "id": sim_run_id,
        "kind": "sim",
        "status": status,
        "createdAt": created_at,
        "top": top_module,
        "pinned": False,
        "parentRunId": parent_run_id,
        "provenance": _provenance(platform),
        "mode": mode,
        "vcdPath": vcd_rel,
        "passMarkerFound": bool(sim_result.get("pass_marker_found")),
        "passMarker": sim_result.get("pass_marker") or pass_marker,
        "failure": failure,
        # Honest echo of what post-synth resolution actually ran (invariant #4):
        # which run, which gate netlist (workspace-relative), which stdcell set.
        # The IDE renders it; the agent (which can't see the tree) reasons on it.
        "resolvedRunId": resolved_run_id,
        "resolvedNetlist": resolved_netlist,
        "stdcellSource": stdcell_source,
        # Semantic outcome + native recovery propagated from the run (e.g.
        # stdcell_cache_missing -> a bootstrap action the IDE/agent can invoke).
        "outcome": sim_result.get("outcome") or sim_status_to_outcome(sim_result.get("status")),
        "recovery": sim_result.get("recovery"),
        "compileCommand": sim_result.get("compile_command") or "",
        "simCommand": sim_result.get("sim_command") or "",
        # raw log surfaces for the console (not part of the frozen RunBase, but
        # handy and harmless to carry on the record).
        "simStatus": sim_result.get("status"),
        "stdoutTail": sim_result.get("stdout_tail", ""),
        "stderrTail": sim_result.get("stderr_tail", ""),
        "logTruncated": bool(sim_result.get("log_truncated")),
    }

    _persist_run_meta(run_dir, sim_run)
    _append_to_index(workspace, sim_run)
    _set_latest(workspace, sim_run_id)
    return sim_run


_TIME_RE = re.compile(r"(?:t\s*=\s*|@\s*|time\s*)(\d+)\s*ns", re.IGNORECASE)


def _extract_time_ns(line: Optional[str]) -> Optional[int]:
    if not line:
        return None
    m = _TIME_RE.search(line)
    return int(m.group(1)) if m else None


def _persist_run_meta(run_dir: str, sim_run: Dict[str, Any]) -> None:
    with open(os.path.join(run_dir, RUN_META_FILENAME), "w", encoding="utf-8") as f:
        json.dump(sim_run, f, indent=2)


def _read_run_meta(run_dir: str) -> Dict[str, Any]:
    path = os.path.join(run_dir, RUN_META_FILENAME)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _index_entry(sim_run: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "run_id": sim_run["id"],
        "status": sim_run["status"],
        "created_at": sim_run["createdAt"],
        "updated_at": _now_iso(),
        "top": sim_run.get("top"),
        "mode": sim_run.get("mode"),
        "pinned": sim_run.get("pinned", False),
        "parentRunId": sim_run.get("parentRunId"),
    }


def _append_to_index(workspace: str, sim_run: Dict[str, Any]) -> None:
    index = _load_index(workspace)
    index["runs"] = [r for r in index.get("runs", []) if r.get("run_id") != sim_run["id"]]
    index["runs"].append(_index_entry(sim_run))
    _save_index(workspace, index)


def get_sim_run_dir(workspace: str, run_id: Optional[str]) -> Optional[str]:
    if run_id:
        path = os.path.join(_runs_root(workspace), run_id)
        return path if os.path.exists(path) else None
    latest = _latest_path(workspace)
    if not os.path.exists(latest):
        return None
    with open(latest, "r", encoding="utf-8") as f:
        rid = f.read().strip()
    path = os.path.join(_runs_root(workspace), rid)
    return path if os.path.exists(path) else None


def get_sim_run(workspace: str, run_id: str) -> Optional[Dict[str, Any]]:
    run_dir = get_sim_run_dir(workspace, run_id)
    if not run_dir:
        return None
    meta = _read_run_meta(run_dir)
    return meta or None


def list_sim_runs(workspace: str) -> List[Dict[str, Any]]:
    """Newest-first list of :class:`SimRun` records."""
    if not os.path.isdir(os.path.join(workspace, RUNS_DIRNAME)):
        return []
    index = _load_index(workspace)
    runs = sorted(index.get("runs", []), key=lambda x: x.get("created_at") or "", reverse=True)
    out: List[Dict[str, Any]] = []
    for item in runs:
        run_id = item.get("run_id")
        if not run_id:
            continue
        run_dir = os.path.join(_runs_root(workspace), run_id)
        if not os.path.exists(run_dir):
            continue
        meta = _read_run_meta(run_dir)
        if meta:
            # Reflect any pin toggles persisted to the index.
            meta["pinned"] = item.get("pinned", meta.get("pinned", False))
            out.append(meta)
    return out


def set_sim_run_pinned(workspace: str, run_id: str, pinned: bool) -> Optional[Dict[str, Any]]:
    run_dir = get_sim_run_dir(workspace, run_id)
    if not run_dir:
        return None
    meta = _read_run_meta(run_dir)
    if not meta:
        return None
    meta["pinned"] = pinned
    _persist_run_meta(run_dir, meta)

    index = _load_index(workspace)
    for r in index.get("runs", []):
        if r.get("run_id") == run_id:
            r["pinned"] = pinned
    _save_index(workspace, index)
    return meta
