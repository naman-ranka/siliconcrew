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
from typing import Any, Dict, Iterator, List, Literal, NamedTuple, Optional, get_args

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "manifest.json"

FileRole = Literal["rtl", "tb", "sdc", "include", "formal", "other"]
# The one list. Anything that names roles (validation, docstrings, API comments)
# derives from it so a new role can never leave a stale copy behind.
ROLES: tuple[str, ...] = get_args(FileRole)
# What an unrecognized stored role reads as. "rtl" is the safe direction: a file
# wrongly kept in the compile set is a loud toolchain error; a file wrongly
# dropped from it is a silent miscompile.
_ROLE_FALLBACK = "rtl"

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

_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

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
    # DERIVED, never user-maintained: one line per problem the file set has that
    # the manifest can see (today: duplicate module declarations). Recomputed on
    # every read/reconcile — any user edit is overwritten.
    warnings: List[str] = Field(default_factory=list)


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


def _strip_comments(text: str) -> str:
    """Blank out Verilog comments so the regexes above only ever see code.

    Block comments collapse to their own newlines rather than "": ``_INSTANCE_RE``
    is ``^\\s*``-anchored per line, so dropping the line breaks would splice a
    following instantiation onto the preceding line and lose it. Block comments
    are removed before line comments because ``//`` inside a ``/* … */`` (URLs,
    commented-out code) is far more common than ``/*`` inside a ``//``.

    No string-literal awareness: a ``"// module fake"`` inside a Verilog string
    is an accepted false negative — comment density in generated RTL is the
    actual threat, and a real lexer here would be machinery.
    """
    text = _BLOCK_COMMENT_RE.sub(lambda mo: "\n" * mo.group(0).count("\n"), text)
    return _LINE_COMMENT_RE.sub("", text)


def _read_text(path: str) -> str:
    """Read a design source file, comment-stripped.

    The single choke point feeding every module/instance/port regex here, so
    stripping once at the read covers all of them.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return _strip_comments(f.read())
    except Exception:
        return ""


def _modules_in(text: str) -> List[str]:
    return _MODULE_RE.findall(text)


def _instances_in(text: str) -> List[str]:
    return [m for m in _INSTANCE_RE.findall(text) if m not in _NOT_A_MODULE]


_GUARD_OPEN_RE = re.compile(r"^\s*`(?:ifdef|ifndef)\b")
_GUARD_CLOSE_RE = re.compile(r"^\s*`endif\b")


def _guarded_modules(text: str) -> frozenset:
    """Modules whose declaration sits inside an `` `ifdef``/`` `ifndef`` region.

    Guard-AWARE, not a preprocessor: no macro is ever evaluated, we only record
    that a declaration is conditional. That is enough for the one decision it
    feeds — two guarded alternates of the same module are a legal, common
    pattern (SBY's `` `ifdef FORMAL ``, vendor/simulation model swaps), so a
    duplicate involving one is not a collision worth shouting about.
    """
    depth = 0
    out: set = set()
    for line in text.splitlines():
        if _GUARD_CLOSE_RE.match(line):
            depth = max(0, depth - 1)
            continue
        if _GUARD_OPEN_RE.match(line):
            depth += 1
            continue
        if depth > 0:
            out.update(_MODULE_RE.findall(line))
    return frozenset(out)


class _FileScan(NamedTuple):
    """What one design file declares — read once, used by every derived field."""
    modules: List[str]
    instances: List[str]
    guarded_modules: frozenset


def _scan_text(text: str) -> _FileScan:
    return _FileScan(
        modules=_modules_in(text),
        instances=_instances_in(text),
        guarded_modules=_guarded_modules(text),
    )


def _scan_design_files(workspace: str, files: List[DesignFile]) -> Dict[str, _FileScan]:
    """ONE pass over the rtl/tb text per reconcile, keyed by workspace-relative path.

    ``_infer_tops``, ``_derive_testbenches`` and the duplicate-module detector all
    want the same module/instance lists; each reading the tree itself made the
    reconcile cost a multiple of the file count for no new information.
    """
    scans: Dict[str, _FileScan] = {}
    for f in files:
        if f.role not in ("rtl", "tb") or f.path in scans:
            continue
        scans[f.path] = _scan_text(_read_text(os.path.join(workspace, f.path)))
    return scans


def _and_join(items: List[str]) -> str:
    quoted = [f"'{i}'" for i in items]
    if len(quoted) == 2:
        return f"both {quoted[0]} and {quoted[1]}"
    return ", ".join(quoted[:-1]) + f" and {quoted[-1]}"


def _collision_warnings(scans: Dict[str, _FileScan]) -> List[str]:
    """One line per module declared by 2+ files in the given set.

    We never guess which copy is the reference — both are named, and the remedy
    (the ``ignore`` glob) is spelled out, which is the part no compiler can tell
    the user. iverilog hard-errors on the redefinition; yosys names only the
    second file and is one flag away from silently picking one.
    """
    declared: Dict[str, List[str]] = {}
    for path, scan in scans.items():
        for module in dict.fromkeys(scan.modules):
            declared.setdefault(module, []).append(path)

    out: List[str] = []
    for module, paths in sorted(declared.items()):
        if len(paths) < 2:
            continue
        if any(module in scans[p].guarded_modules for p in paths):
            continue  # `ifdef-gated alternates are legal together
        out.append(
            f"module '{module}' is declared by {_and_join(paths)} — a compile set can "
            f"hold only one definition (iverilog errors out; yosys may just pick one). "
            f"Keep one: add the other to the manifest 'ignore' list (fnmatch glob, e.g. "
            f"\"given/**\") or set its role to 'other'. The practice this rule comes "
            f"from: one module per file, and each file compiled once."
        )
    return out


def compile_set_collisions(workspace: str, paths: List[str]) -> List[str]:
    """Duplicate-module warnings for an ASSEMBLED compile set — the point of damage.

    ``paths`` is the exact list about to be handed to the toolchain (absolute or
    workspace-relative). A collision recorded on the manifest only costs a run
    when both declarations are really in the set, so this re-checks the set
    itself rather than replaying the manifest's warnings.
    """
    scans: Dict[str, _FileScan] = {}
    for p in paths:
        abs_p = p if os.path.isabs(p) else os.path.join(workspace, p)
        if os.path.splitext(abs_p)[1].lower() not in _RTL_EXTS or not os.path.isfile(abs_p):
            continue
        try:
            rel = os.path.relpath(abs_p, workspace).replace(os.sep, "/")
        except ValueError:  # different drive on Windows
            rel = os.path.basename(abs_p)
        if rel.startswith(".."):
            rel = os.path.basename(abs_p)
        if rel in scans:
            continue
        scans[rel] = _scan_text(_read_text(abs_p))
    return _collision_warnings(scans)


# Formal-harness naming, the attested conventions (SymbiYosys/OpenTitan/
# riscv-formal). ``_sva`` is deliberately absent — unattested as a file suffix.
_FORMAL_NAME_RE = re.compile(r"_(props|properties|formal|fpv|bind|bind_fpv|assert_fpv)$")
_PROPERTY_RE = re.compile(r"\b(?:assert|assume|cover)\s+property\b")


def _looks_like_formal(name: str, text: str) -> bool:
    """A formal harness: the NAME says so and the content doesn't contradict it.

    Filename-primary on purpose. Inline ``assert property`` in production RTL is
    normal practice (OpenTitan's policy puts basic assertions in the RTL), and
    SBY's own documented pattern keeps properties INSIDE the synthesizable
    module behind `` `ifdef FORMAL `` — so property constructs alone say nothing
    about what the FILE is. Content is only a negative gate: a file named
    ``*_props.sv`` with no properties in it stays rtl.

    The cost asymmetry settles every tie: calling a formal harness ``rtl`` costs
    a warning the compile already handles; calling rtl ``formal`` silently DROPS
    A MODULE from synthesis. When unsure, rtl.
    """
    base = os.path.splitext(os.path.basename(name))[0].lower()
    if not _FORMAL_NAME_RE.search(base):
        return False
    return bool(_PROPERTY_RE.search(text))


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
    testbench naming heuristics operate on the basename. ``text`` is stripped of
    comments here too (idempotent) since callers pass their own text.
    """
    text = _strip_comments(text)
    ext = os.path.splitext(name)[1].lower()
    if ext == ".sdc":
        return "sdc"
    if ext in _INCLUDE_EXTS:
        return "include"
    if ext in _RTL_EXTS:
        if _looks_like_formal(name, text):
            return "formal"
        return "tb" if _looks_like_tb(name, text) else "rtl"
    return "other"


def _infer_tops(files: List[DesignFile], scans: Dict[str, _FileScan]) -> tuple[str, str]:
    """Infer (synthTop, simTop) from file roles + instantiation graph."""
    sim_top = ""
    synth_top = ""
    tb_instances: List[str] = []

    # simTop = top module of the first testbench.
    for f in files:
        if f.role == "tb":
            scan = scans.get(f.path)
            if scan and scan.modules:
                # The tb top is usually the last/only module defining no ports.
                sim_top = scan.modules[-1]
                tb_instances = scan.instances
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
            scan = scans.get(f.path)
            if scan is None:
                continue
            for m in scan.modules:
                rtl_modules.append(m)
                rtl_module_set.add(m)
            instantiated_by_rtl.update(scan.instances)

    # Roots = rtl modules that are never instantiated by another rtl module.
    roots = [m for m in rtl_modules if m not in instantiated_by_rtl]
    tb_insts = [i for i in tb_instances if i in rtl_module_set]

    # 1) a root the testbench instantiates (the DUT); 2) the sole/first root;
    # 3) any module the tb instantiates; 4) first rtl module.
    synth_top = (
        next((i for i in tb_insts if i in roots), "")
        or (roots[0] if roots else "")
        or (tb_insts[0] if tb_insts else "")
        or (rtl_modules[0] if rtl_modules else "")
    )

    return synth_top, sim_top


def _derive_testbenches(files: List[DesignFile], scans: Dict[str, _FileScan]) -> List[Dict[str, str]]:
    """DERIVED testbench list: {file, module} per role=="tb" file.

    The TB top is the last module declared in the file — the same inference
    :func:`_infer_tops` uses for ``simTop``. Recomputed on every reconcile;
    never user-maintained.
    """
    out: List[Dict[str, str]] = []
    for f in files:
        if f.role != "tb":
            continue
        scan = scans.get(f.path)
        if scan and scan.modules:
            out.append({"file": f.path, "module": scan.modules[-1]})
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

    scans = _scan_design_files(workspace, files)
    synth_top, sim_top = _infer_tops(files, scans)
    clock = _spec_clock_period(workspace) or 10.0
    return DesignManifest(
        sessionId=session_id,
        files=files,
        synthTop=synth_top,
        simTop=sim_top,
        clockPeriodNs=clock,
        platform="sky130hd",
        testbenches=_derive_testbenches(files, scans),
        warnings=_collision_warnings(scans),
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


def _coerce_files(raw_files: Any) -> List[DesignFile]:
    """Stored file entries → DesignFile, one bad field at a time.

    An unrecognized role reads as ``rtl`` with a log line instead of failing the
    document. Hosted runs rolling deploys (invariant 9), so an old reader WILL
    meet a manifest written by a newer one; the alternative — discarding the
    document — wipes every user field on the way past.
    """
    out: List[DesignFile] = []
    for entry in raw_files or []:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path") or entry.get("name")
        if not isinstance(path, str) or not path:
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            name = os.path.basename(path)
        role = entry.get("role")
        if role not in ROLES:
            logger.warning(
                "manifest: unrecognized role %r for %r — reading it as %r "
                "(the stored value is not rewritten unless the manifest is edited)",
                role, path, _ROLE_FALLBACK,
            )
            role = _ROLE_FALLBACK
        out.append(DesignFile(name=name, role=role, path=path))
    return out


def _manifest_from_raw(raw: Dict[str, Any]) -> DesignManifest:
    """Per-FIELD tolerant load: a value this reader can't use costs that field,
    never the document. ``testbenches`` is derived — reconcile recomputes it."""
    manifest = DesignManifest()
    manifest.files = _coerce_files(raw.get("files"))
    for key in ("sessionId", "synthTop", "simTop", "platform"):
        value = raw.get(key)
        if isinstance(value, str):
            setattr(manifest, key, value)
    clock = raw.get("clockPeriodNs")
    if isinstance(clock, (int, float)) and not isinstance(clock, bool):
        manifest.clockPeriodNs = float(clock)
    ignore = raw.get("ignore")
    if isinstance(ignore, list):
        manifest.ignore = [p for p in ignore if isinstance(p, str) and p]
    return manifest


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

    scans = _scan_design_files(workspace, merged)
    if not stored.synthTop or not stored.simTop:
        synth_top, sim_top = _infer_tops(merged, scans)
        stored.synthTop = stored.synthTop or synth_top
        stored.simTop = stored.simTop or sim_top
    stored.testbenches = _derive_testbenches(merged, scans)
    stored.warnings = _collision_warnings(scans)
    return stored


def read_manifest(workspace: str, session_id: str = "") -> DesignManifest:
    """Return the manifest, auto-deriving + persisting one if absent.

    Always reconciles against the files currently on disk so uploads/deletes
    made outside the manifest API are reflected.
    """
    raw = _load_raw(workspace)
    if raw is None or not isinstance(raw, dict):
        manifest = build_manifest(workspace, session_id=session_id)
        _persist(workspace, manifest)
        return manifest
    stored = _manifest_from_raw(raw)
    if session_id and not stored.sessionId:
        stored.sessionId = session_id
    stored = _reconcile(workspace, stored)
    _persist(workspace, stored)
    return stored


def _validate_role_updates(updates: Dict[str, Any]) -> None:
    """Reject unknown roles before anything is read, mutated or persisted."""
    entries = updates.get("files")
    if not isinstance(entries, list):
        return
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("role"):
            continue
        role = entry["role"]
        if role not in ROLES:
            target = entry.get("path") or entry.get("name") or "?"
            raise ValueError(
                f"unknown role {role!r} for {target!r}. Valid roles: {', '.join(ROLES)}."
            )


def write_manifest(workspace: str, updates: Dict[str, Any], session_id: str = "") -> DesignManifest:
    """Upsert manifest fields (roles, tops, clock, platform, ignore).

    ``updates`` may carry any subset of the manifest fields. A ``files`` entry
    overrides roles keyed by ``path`` (canonical). For backward compatibility a
    ``name``-only entry is honored when the basename is unambiguous (unique
    across the manifest); an ambiguous name-only update is a logged no-op —
    callers that can see nested files must address them by path.

    ``testbenches`` is derived and cannot be set here (silently recomputed).

    Raises ``ValueError`` on an unknown role and persists NOTHING. The check
    lives here, not in a request model, so agent / MCP / REST ``/invoke`` are
    covered by construction — pydantic v2 does not validate on assignment, so an
    unvalidated role would otherwise reach disk and the next read would have to
    decide what to do with a document it can't parse.
    """
    _validate_role_updates(updates)
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

    # Derived fields — recompute so role edits above are reflected (a file moved
    # to 'other' leaves the compile set, so it can also leave a collision).
    scans = _scan_design_files(workspace, current.files)
    current.testbenches = _derive_testbenches(current.files, scans)
    current.warnings = _collision_warnings(scans)

    _persist(workspace, current)
    return current


def files_for_stage(manifest: DesignManifest, stage: str) -> List[str]:
    """Workspace-relative file set that reaches a given stage (data-model.md).

    | Lint      | rtl + include              |
    | Simulate  | rtl + tb + include         |
    | Synthesize| rtl + sdc (no tb)          |

    Role ``formal`` reaches NO stage here: an SVA harness is not synthesizable
    and iverilog can't elaborate concurrent assertions at all. Executing it is
    sby's job (Wave F); this function only stops it from breaking the stages
    that exist.
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
