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

import fnmatch
import json
import logging
import os
import re
from typing import Any, Dict, Iterator, List, Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.json"

FileRole = Literal["rtl", "tb", "sdc", "include", "other"]

# Directories that hold generated run artifacts or third-party payloads — never
# part of the design set. Dot-dirs (".git", ".cache", …) are pruned separately.
_IGNORED_DIRS = {
    "synth_runs", "sim_runs", "orfs_reports", "orfs_logs", "results",
    "__pycache__", "node_modules",
}

# Runaway guard for the recursive scan: directories nested deeper than this
# (relative to the workspace root) are never descended into.
_MAX_SCAN_DEPTH = 6

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
    name: str  # basename, for display only — never a key (may collide across dirs)
    role: FileRole
    path: str  # workspace-relative POSIX path — the canonical key for role/top logic


class DesignManifest(BaseModel):
    sessionId: str = ""
    files: List[DesignFile] = Field(default_factory=list)
    synthTop: str = ""
    simTop: str = ""
    clockPeriodNs: float = 10.0
    platform: str = "sky130hd"
    # User-editable fnmatch globs matched against workspace-relative POSIX paths
    # (files AND directories), e.g. "vendor/**" or "vendor". Matching files are
    # excluded from the scan; matching directories are pruned entirely.
    ignore: List[str] = Field(default_factory=list)
    # DERIVED, never user-maintained: one entry per role=="tb" file as
    # {"file": <workspace-relative path>, "module": <TB top module name>}.
    # Recomputed on every read/reconcile — any user edit is overwritten.
    # ``simTop`` keeps its meaning as the *default* TB (what one-click Simulate
    # runs); it is still inferred from the first tb file when unset.
    testbenches: List[Dict[str, str]] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# File scanning + role derivation
# --------------------------------------------------------------------------- #

def _matches_ignore(rel_posix: str, ignore: List[str]) -> bool:
    """fnmatch the workspace-relative POSIX path against user ignore globs."""
    return any(fnmatch.fnmatch(rel_posix, pat) for pat in ignore or [] if pat)


def iter_workspace_files(workspace: str, ignore: Optional[List[str]] = None) -> Iterator[str]:
    """Yield workspace-relative POSIX paths of ALL files under the scan policy.

    The single exclusion policy shared by the manifest scan and every workspace
    listing endpoint (GET /files, /code, /spec, workbench snapshots):
      * prune run-artifact dirs (``sim_runs``, ``synth_runs``, …), dot-dirs,
        ``__pycache__`` and ``node_modules``;
      * prune dirs / drop files whose relative POSIX path matches a user
        ``ignore`` glob (fnmatch, e.g. ``vendor/**`` or ``vendor``);
      * never descend deeper than ``_MAX_SCAN_DEPTH`` directory levels.

    No extension filtering here — callers filter for their own file kinds.
    """
    ignore = ignore or []
    if not os.path.isdir(workspace):
        return
    for dirpath, dirnames, filenames in os.walk(workspace):
        rel_dir = os.path.relpath(dirpath, workspace)
        rel_dir_posix = "" if rel_dir == "." else rel_dir.replace(os.sep, "/")
        depth = 0 if not rel_dir_posix else rel_dir_posix.count("/") + 1
        if depth >= _MAX_SCAN_DEPTH:
            dirnames[:] = []  # runaway guard: do not descend further
        else:
            kept = []
            for d in dirnames:
                if d in _IGNORED_DIRS or d.startswith("."):
                    continue
                child = f"{rel_dir_posix}/{d}" if rel_dir_posix else d
                if _matches_ignore(child, ignore):
                    continue
                kept.append(d)
            dirnames[:] = sorted(kept)
        for name in sorted(filenames):
            rel = f"{rel_dir_posix}/{name}" if rel_dir_posix else name
            if _matches_ignore(rel, ignore):
                continue
            yield rel


def _list_source_files(workspace: str, ignore: Optional[List[str]] = None) -> List[str]:
    """Workspace-relative POSIX paths of design source files (recursive).

    Recursive since the verification-loop work: RTL under ``rtl/``, TBs under
    ``tb/`` etc. are first-class. The historic fear behind root-only scanning
    (ingesting run artifacts / vendor models as user RTL) is addressed by
    :func:`iter_workspace_files`'s exclusion policy instead.
    """
    out: List[str] = []
    for rel in iter_workspace_files(workspace, ignore):
        if rel == MANIFEST_FILENAME:
            continue
        ext = os.path.splitext(rel)[1].lower()
        if ext in _RTL_EXTS or ext in _INCLUDE_EXTS or ext == ".sdc":
            out.append(rel)
    return sorted(out)


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
    # ``name`` may be a workspace-relative path — heuristics key on the basename.
    base = os.path.splitext(os.path.basename(name))[0].lower()
    if base.endswith("_tb") or base.startswith("tb_") or base.endswith("testbench") or "_test" in base:
        return True
    # A module with no ports that instantiates another module is a testbench.
    has_ports = bool(_HAS_PORTS_RE.search(text))
    instantiates = bool(_instances_in(text))
    if not has_ports and instantiates and _modules_in(text):
        return True
    return False


def derive_role(name: str, text: str = "") -> FileRole:
    """Deterministic role derivation (overridable). See data-model.md.

    ``name`` may be a bare filename or a workspace-relative path — extension and
    testbench naming heuristics operate on the basename.
    """
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


def _derive_testbenches(workspace: str, files: List[DesignFile]) -> List[Dict[str, str]]:
    """DERIVED testbench list: {file, module} per role=="tb" file.

    The TB top is the last module declared in the file — the same inference
    :func:`_infer_tops` uses for ``simTop``. Recomputed on every reconcile;
    never user-maintained.
    """
    out: List[Dict[str, str]] = []
    for f in files:
        if f.role != "tb":
            continue
        mods = _modules_in(_read_text(os.path.join(workspace, f.path)))
        if mods:
            out.append({"file": f.path, "module": mods[-1]})
    return out


def _spec_clock_period(workspace: str) -> Optional[float]:
    """Best-effort clock period from the latest spec file (non-fatal)."""
    try:
        import yaml  # local import keeps manifest importable without pyyaml
    except Exception:
        return None
    specs = sorted(
        [f for f in iter_workspace_files(workspace) if f.endswith("_spec.yaml")],
        key=lambda x: os.path.getmtime(os.path.join(workspace, x)),
        reverse=True,
    )
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
    for rel in _list_source_files(workspace):
        text = _read_text(os.path.join(workspace, rel)) if rel.lower().endswith((".v", ".sv")) else ""
        files.append(DesignFile(name=os.path.basename(rel), role=derive_role(rel, text), path=rel))

    synth_top, sim_top = _infer_tops(workspace, files)
    clock = _spec_clock_period(workspace) or 10.0
    return DesignManifest(
        sessionId=session_id,
        files=files,
        synthTop=synth_top,
        simTop=sim_top,
        clockPeriodNs=clock,
        platform="sky130hd",
        testbenches=_derive_testbenches(workspace, files),
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
    became empty or point at a now-missing module. Files are keyed by their
    workspace-relative ``path`` (at the root ``path == name``, so legacy
    root-only manifests reconcile unchanged). The derived ``testbenches`` list
    is always recomputed here — user edits to it do not survive.
    """
    on_disk = _list_source_files(workspace, stored.ignore)
    by_path = {f.path: f for f in stored.files}

    merged: List[DesignFile] = []
    for rel in on_disk:
        if rel in by_path:
            merged.append(by_path[rel])
        else:
            text = _read_text(os.path.join(workspace, rel)) if rel.lower().endswith((".v", ".sv")) else ""
            merged.append(DesignFile(name=os.path.basename(rel), role=derive_role(rel, text), path=rel))

    stored.files = merged

    if not stored.synthTop or not stored.simTop:
        synth_top, sim_top = _infer_tops(workspace, merged)
        stored.synthTop = stored.synthTop or synth_top
        stored.simTop = stored.simTop or sim_top
    stored.testbenches = _derive_testbenches(workspace, merged)
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
    """Upsert manifest fields (roles, tops, clock, platform, ignore).

    ``updates`` may carry any subset of the manifest fields. A ``files`` entry
    overrides roles keyed by ``path`` (canonical). For backward compatibility a
    ``name``-only entry is honored when the basename is unambiguous (unique
    across the manifest); an ambiguous name-only update is a logged no-op —
    callers that can see nested files must address them by path.

    ``testbenches`` is derived and cannot be set here (silently recomputed).
    """
    current = read_manifest(workspace, session_id=session_id)

    if "files" in updates and isinstance(updates["files"], list):
        by_path = {f.path: f for f in current.files}
        basename_counts: Dict[str, int] = {}
        for f in current.files:
            basename_counts[f.name] = basename_counts.get(f.name, 0) + 1
        by_unique_name = {f.name: f for f in current.files if basename_counts[f.name] == 1}

        for entry in updates["files"]:
            if not (isinstance(entry, dict) and entry.get("role")):
                continue
            target: Optional[DesignFile] = None
            if entry.get("path"):
                target = by_path.get(entry["path"])
            elif entry.get("name"):
                nm = entry["name"]
                target = by_path.get(nm) or by_unique_name.get(nm)
                if target is None and basename_counts.get(nm, 0) > 1:
                    logger.warning(
                        "write_manifest: role update for name=%r skipped — basename is "
                        "ambiguous (%d matches); address the file by its path", nm, basename_counts[nm],
                    )
            if target is not None:
                target.role = entry["role"]  # type: ignore[assignment]

    for key in ("synthTop", "simTop", "platform", "sessionId"):
        if key in updates and isinstance(updates[key], str) and updates[key]:
            setattr(current, key, updates[key])
    if "clockPeriodNs" in updates:
        try:
            current.clockPeriodNs = float(updates["clockPeriodNs"])
        except (TypeError, ValueError):
            pass
    if "ignore" in updates and isinstance(updates["ignore"], list):
        current.ignore = [str(p) for p in updates["ignore"] if isinstance(p, str) and p]
        # New exclusions take effect immediately (drops newly-ignored files).
        current = _reconcile(workspace, current)

    # testbenches is derived — recompute so role edits above are reflected.
    current.testbenches = _derive_testbenches(workspace, current.files)

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
