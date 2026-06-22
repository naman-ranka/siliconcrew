"""Design manifest — the single source of truth for a session's files & roles.

Phase 1 formalizes what was previously implicit (a per-call file list + "latest
``*_spec.yaml`` by mtime"). The manifest binds every workspace file to a *role*,
names the two top modules (``synthTop`` for synthesis, ``simTop`` for the
testbench), and carries the clock/platform constraints. Both the human (UI) and
the agent (a manifest tool) read and edit the same object.

Field names mirror ``plans/phase0/data-model.md`` (the frozen vocabulary) and
are camelCase so the JSON crosses to the TypeScript types unchanged.

Persistence: ``<workspace>/manifest.json``. Reading auto-derives + persists a
manifest when none exists, so the rest of the system can always assume one.
Role derivation is deterministic (naming + content heuristics) and any field is
user/agent overridable via :func:`write_manifest`.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

MANIFEST_FILENAME = "manifest.json"

FileRole = Literal["rtl", "tb", "sdc", "include", "other"]

# Directories that hold generated run artifacts — never part of the design set.
_IGNORED_DIRS = {"synth_runs", "sim_runs", "orfs_reports", "orfs_logs", "results", "__pycache__"}

_RTL_EXTS = {".v", ".sv"}
_INCLUDE_EXTS = {".vh", ".svh"}

_MODULE_RE = re.compile(r"\bmodule\s+([A-Za-z_]\w*)", re.MULTILINE)
# Instantiation: `module_name #(...) inst (...)` or `module_name inst (...)`.
_INSTANCE_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s+(?:#\s*\([^;]*?\)\s*)?[A-Za-z_]\w*\s*\(", re.MULTILINE)
_HAS_PORTS_RE = re.compile(r"\bmodule\s+[A-Za-z_]\w*\s*(#\s*\([^;]*?\)\s*)?\(\s*[^)\s]", re.DOTALL)

# Verilog keywords that the instance regex can mistake for a module type.
_NOT_A_MODULE = {
    "if", "for", "while", "case", "begin", "end", "assign", "always", "initial",
    "wire", "reg", "logic", "input", "output", "inout", "parameter", "localparam",
    "module", "endmodule", "generate", "endgenerate", "function", "task", "integer",
    "genvar", "real", "time", "posedge", "negedge", "repeat", "forever",
}


class DesignFile(BaseModel):
    name: str
    role: FileRole
    path: str  # workspace-relative


class DesignManifest(BaseModel):
    sessionId: str = ""
    files: List[DesignFile] = Field(default_factory=list)
    synthTop: str = ""
    simTop: str = ""
    clockPeriodNs: float = 10.0
    platform: str = "sky130hd"


# --------------------------------------------------------------------------- #
# File scanning + role derivation
# --------------------------------------------------------------------------- #

def _list_source_files(workspace: str) -> List[str]:
    """Workspace-relative source files relevant to the design (top level only).

    We deliberately stay at the workspace root: nested directories are run
    artifacts or third-party stdcell models, not the user's design.
    """
    out: List[str] = []
    if not os.path.isdir(workspace):
        return out
    for name in sorted(os.listdir(workspace)):
        full = os.path.join(workspace, name)
        if not os.path.isfile(full):
            continue
        if name == MANIFEST_FILENAME:
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext in _RTL_EXTS or ext in _INCLUDE_EXTS or ext == ".sdc":
            out.append(name)
    return out


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def _modules_in(text: str) -> List[str]:
    return _MODULE_RE.findall(text)


def _instances_in(text: str) -> List[str]:
    return [m for m in _INSTANCE_RE.findall(text) if m not in _NOT_A_MODULE]


def _looks_like_tb(name: str, text: str) -> bool:
    base = os.path.splitext(name)[0].lower()
    if base.endswith("_tb") or base.startswith("tb_") or base.endswith("testbench") or "_test" in base:
        return True
    # A module with no ports that instantiates another module is a testbench.
    has_ports = bool(_HAS_PORTS_RE.search(text))
    instantiates = bool(_instances_in(text))
    if not has_ports and instantiates and _modules_in(text):
        return True
    return False


def derive_role(name: str, text: str = "") -> FileRole:
    """Deterministic role derivation (overridable). See data-model.md."""
    ext = os.path.splitext(name)[1].lower()
    if ext == ".sdc":
        return "sdc"
    if ext in _INCLUDE_EXTS:
        return "include"
    if ext in _RTL_EXTS:
        return "tb" if _looks_like_tb(name, text) else "rtl"
    return "other"


def _infer_tops(workspace: str, files: List[DesignFile]) -> tuple[str, str]:
    """Infer (synthTop, simTop) from file roles + instantiation graph."""
    sim_top = ""
    synth_top = ""
    tb_text = ""

    # simTop = top module of the first testbench.
    for f in files:
        if f.role == "tb":
            text = _read_text(os.path.join(workspace, f.path))
            mods = _modules_in(text)
            if mods:
                # The tb top is usually the last/only module defining no ports.
                sim_top = mods[-1]
                tb_text = text
                break

    # synthTop = the ROOT of the RTL hierarchy (the module no other rtl module
    # instantiates), preferring the DUT the testbench instantiates. This fixes
    # multi-module designs where the old "first rtl module" guess picked a leaf
    # submodule (e.g. `mux2`) instead of the real top (`top`).
    rtl_modules: List[str] = []
    rtl_module_set: set[str] = set()
    instantiated_by_rtl: set[str] = set()
    for f in files:
        if f.role == "rtl":
            text = _read_text(os.path.join(workspace, f.path))
            for m in _modules_in(text):
                rtl_modules.append(m)
                rtl_module_set.add(m)
            for inst in _instances_in(text):
                instantiated_by_rtl.add(inst)

    # Roots = rtl modules that are never instantiated by another rtl module.
    roots = [m for m in rtl_modules if m not in instantiated_by_rtl]
    tb_insts = [i for i in _instances_in(tb_text) if i in rtl_module_set] if tb_text else []

    # 1) a root the testbench instantiates (the DUT); 2) the sole/first root;
    # 3) any module the tb instantiates; 4) first rtl module.
    synth_top = (
        next((i for i in tb_insts if i in roots), "")
        or (roots[0] if roots else "")
        or (tb_insts[0] if tb_insts else "")
        or (rtl_modules[0] if rtl_modules else "")
    )

    return synth_top, sim_top


def _spec_clock_period(workspace: str) -> Optional[float]:
    """Best-effort clock period from the latest spec file (non-fatal)."""
    try:
        import yaml  # local import keeps manifest importable without pyyaml
    except Exception:
        return None
    specs = sorted(
        [f for f in os.listdir(workspace) if f.endswith("_spec.yaml")],
        key=lambda x: os.path.getmtime(os.path.join(workspace, x)),
        reverse=True,
    ) if os.path.isdir(workspace) else []
    for s in specs:
        try:
            with open(os.path.join(workspace, s), "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh) or {}
            cp = data.get("clock_period_ns")
            if isinstance(cp, (int, float)) and cp > 0:
                return float(cp)
        except Exception:
            continue
    return None


def build_manifest(workspace: str, session_id: str = "") -> DesignManifest:
    """Construct a fresh manifest from the files on disk (no persistence)."""
    files: List[DesignFile] = []
    for name in _list_source_files(workspace):
        text = _read_text(os.path.join(workspace, name)) if name.lower().endswith((".v", ".sv")) else ""
        files.append(DesignFile(name=name, role=derive_role(name, text), path=name))

    synth_top, sim_top = _infer_tops(workspace, files)
    clock = _spec_clock_period(workspace) or 10.0
    return DesignManifest(
        sessionId=session_id,
        files=files,
        synthTop=synth_top,
        simTop=sim_top,
        clockPeriodNs=clock,
        platform="sky130hd",
    )


# --------------------------------------------------------------------------- #
# Persistence + reconciliation
# --------------------------------------------------------------------------- #

def _manifest_path(workspace: str) -> str:
    return os.path.join(workspace, MANIFEST_FILENAME)


def _load_raw(workspace: str) -> Optional[Dict[str, Any]]:
    path = _manifest_path(workspace)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _persist(workspace: str, manifest: DesignManifest) -> None:
    os.makedirs(workspace, exist_ok=True)
    with open(_manifest_path(workspace), "w", encoding="utf-8") as f:
        json.dump(manifest.model_dump(), f, indent=2)


def _reconcile(workspace: str, stored: DesignManifest) -> DesignManifest:
    """Merge a stored manifest with the current files on disk.

    New files are added (role auto-derived); deleted files are dropped; existing
    files keep their (possibly user-overridden) role. Tops are filled in if they
    became empty or point at a now-missing module.
    """
    on_disk = _list_source_files(workspace)
    by_name = {f.name: f for f in stored.files}

    merged: List[DesignFile] = []
    for name in on_disk:
        if name in by_name:
            merged.append(by_name[name])
        else:
            text = _read_text(os.path.join(workspace, name)) if name.lower().endswith((".v", ".sv")) else ""
            merged.append(DesignFile(name=name, role=derive_role(name, text), path=name))

    stored.files = merged

    if not stored.synthTop or not stored.simTop:
        synth_top, sim_top = _infer_tops(workspace, merged)
        stored.synthTop = stored.synthTop or synth_top
        stored.simTop = stored.simTop or sim_top
    return stored


def read_manifest(workspace: str, session_id: str = "") -> DesignManifest:
    """Return the manifest, auto-deriving + persisting one if absent.

    Always reconciles against the files currently on disk so uploads/deletes
    made outside the manifest API are reflected.
    """
    raw = _load_raw(workspace)
    if raw is None:
        manifest = build_manifest(workspace, session_id=session_id)
        _persist(workspace, manifest)
        return manifest
    try:
        stored = DesignManifest(**raw)
    except Exception:
        stored = build_manifest(workspace, session_id=session_id)
    if session_id and not stored.sessionId:
        stored.sessionId = session_id
    stored = _reconcile(workspace, stored)
    _persist(workspace, stored)
    return stored


def write_manifest(workspace: str, updates: Dict[str, Any], session_id: str = "") -> DesignManifest:
    """Upsert manifest fields (roles, tops, clock, platform).

    ``updates`` may carry any subset of the manifest fields. A ``files`` entry
    overrides roles by name (the path/file set is still reconciled with disk).
    """
    current = read_manifest(workspace, session_id=session_id)

    if "files" in updates and isinstance(updates["files"], list):
        role_by_name: Dict[str, str] = {}
        for entry in updates["files"]:
            if isinstance(entry, dict) and entry.get("name") and entry.get("role"):
                role_by_name[entry["name"]] = entry["role"]
        for f in current.files:
            if f.name in role_by_name:
                f.role = role_by_name[f.name]  # type: ignore[assignment]

    for key in ("synthTop", "simTop", "platform", "sessionId"):
        if key in updates and isinstance(updates[key], str) and updates[key]:
            setattr(current, key, updates[key])
    if "clockPeriodNs" in updates:
        try:
            current.clockPeriodNs = float(updates["clockPeriodNs"])
        except (TypeError, ValueError):
            pass

    _persist(workspace, current)
    return current


def files_for_stage(manifest: DesignManifest, stage: str) -> List[str]:
    """Workspace-relative file set that reaches a given stage (data-model.md).

    | Lint      | rtl + include              |
    | Simulate  | rtl + tb + include         |
    | Synthesize| rtl + sdc (no tb)          |
    """
    stage = stage.lower()
    if stage == "lint":
        roles = {"rtl", "include"}
    elif stage in ("sim", "simulate", "simulation"):
        roles = {"rtl", "tb", "include"}
    elif stage in ("synth", "synthesize", "synthesis"):
        roles = {"rtl", "sdc"}
    else:
        roles = {"rtl", "tb", "include", "sdc"}
    return [f.path for f in manifest.files if f.role in roles]
