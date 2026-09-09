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
import hashlib
import json
import logging
import os
import posixpath
import re
from typing import Any, Collection, Dict, Iterator, List, Literal, NamedTuple, Optional, get_args

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

# The one definition of "a Verilog/SystemVerilog source" — every caller that
# filters or resolves RTL by extension (the REST twins, the tool wrappers, the
# file resolver) reads this tuple rather than retyping it.
RTL_EXTS: tuple[str, ...] = (".v", ".sv")
_RTL_EXTS = frozenset(RTL_EXTS)
_INCLUDE_EXTS = {".vh", ".svh"}

# One position-ordered alternation instead of two passes: precedence between
# strings, `//` and `/* */` falls out of scan order, exactly as a lexer sees
# them. Two passes cannot get this right in both directions — stripping block
# comments first let a `/*` INSIDE a `//` comment open a match that swallowed
# real code up to the next `*/` anywhere later in the file.
_COMMENT_OR_STRING_RE = re.compile(
    r'"(?:\\.|[^"\\\n])*"'  # string literal (kept as an empty "")
    r"|//[^\n]*"            # line comment
    r"|/\*.*?\*/",          # block comment
    re.DOTALL,
)

# IEEE 1800 module_declaration: `module_keyword [lifetime] module_identifier`.
# Without the lifetime branch, `module automatic core` declared a phantom
# module named 'automatic' — which could win synthTop (dev#77's exact failure
# through a different vector). `extern module x (...)` is a legal prototype
# BESIDE the definition (IEEE 1800 §23.2.4), so it must not count as a second
# declaration; it is blanked before matching (see _find_modules).
_MODULE_RE = re.compile(
    r"\bmodule\s+(?:static\s+|automatic\s+)?([A-Za-z_]\w*)", re.MULTILINE
)
_EXTERN_MODULE_RE = re.compile(r"\bextern\s+module\b")


def _find_modules(text: str) -> List[str]:
    """Declared module names in ``text`` (comment-stripped)."""
    return _MODULE_RE.findall(_EXTERN_MODULE_RE.sub("", text))
# Instantiation: `module_name #(...) inst (...)` or `module_name inst (...)`.
_INSTANCE_RE = re.compile(r"^\s*([A-Za-z_]\w*)\s+(?:#\s*\([^;]*?\)\s*)?[A-Za-z_]\w*\s*\(", re.MULTILINE)
# Same lifetime branch as _MODULE_RE: without it, `module automatic core (...)`
# read as port-less, flipping the file's role to tb — which silently drops the
# module from the synthesis compile set (files_for_stage synth = rtl + sdc).
_HAS_PORTS_RE = re.compile(
    r"\bmodule\s+(?:static\s+|automatic\s+)?[A-Za-z_]\w*\s*(#\s*\([^;]*?\)\s*)?\(\s*[^)\s]",
    re.DOTALL,
)

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
    # User/agent-editable, free-entry: the stdout substring that marks a passing
    # simulation for THIS design (e.g. "TEST_PASS"). A design's pass criterion
    # is a property of the design, not of the invocation (dev#44) — so it lives
    # here rather than being a per-call argument each caller must remember.
    # Empty means "no design-specific marker": simulation falls back to its
    # default ("TEST PASSED"). An explicit per-call pass_marker still wins.
    passMarker: str = ""
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
    # DERIVED, never user-maintained: digest of the design-file scan fingerprint
    # (see _scan_fingerprint) at the last time _infer_tops ran. This is what
    # tells "inferred: none found" apart from "not yet inferred" — without it,
    # a workspace whose simTop is legitimately empty (no testbench) re-ran the
    # full inference on EVERY read (sc#81). Not a source of truth: losing the
    # field (hand edit, older writer) costs exactly one re-inference.
    topsInferredFingerprint: str = ""


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
    """Blank out Verilog comments/strings so the regexes above only see code.

    Single pass, position-ordered: whichever of a string, ``//`` or ``/*``
    starts first claims the region, so ``/*`` inside a line comment or ``//``
    inside a block comment can never open a bogus region (a two-pass version
    deleted real module declarations when a ``//`` comment contained ``/*``).

    Block comments collapse to their own newlines rather than "": ``_INSTANCE_RE``
    is ``^\\s*``-anchored per line, so dropping the line breaks would splice a
    following instantiation onto the preceding line and lose it. String literals
    collapse to an empty ``""`` — their contents are display text, and a
    ``$display("module gcn booting")`` must not read as a declaration.
    """
    def _sub(mo: "re.Match[str]") -> str:
        tok = mo.group(0)
        if tok.startswith('"'):
            return '""'
        return "\n" * tok.count("\n")

    return _COMMENT_OR_STRING_RE.sub(_sub, text)


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
    return _find_modules(text)


def _instances_in(text: str) -> List[str]:
    return [m for m in _INSTANCE_RE.findall(text) if m not in _NOT_A_MODULE]


_GUARD_OPEN_RE = re.compile(r"^\s*`(ifdef|ifndef)\s+(\w+)")
_GUARD_ELSIF_RE = re.compile(r"^\s*`elsif\s+(\w+)")
_GUARD_ELSE_RE = re.compile(r"^\s*`else\b")
_GUARD_CLOSE_RE = re.compile(r"^\s*`endif\b")


def _guarded_modules(text: str) -> Dict[str, frozenset]:
    """Map module -> the set of guard CONDITIONS its declarations sit under.

    Guard-AWARE, not a preprocessor: no macro is ever evaluated. A condition is
    a frozenset of ("+" | "-", MACRO) terms — the `` `ifdef``/`` `ifndef``
    (and `` `else``/`` `elsif``) stack in force at the declaration; an
    unguarded declaration records the empty condition.

    Recording WHICH macros guard a declaration (not merely that one does) is
    what lets the collision detector distinguish alternates of one module —
    `` `ifdef X`` vs `` `ifndef X``, or the same include guard in two copies —
    from two copies that each carry their OWN unrelated guard, which the
    preprocessor happily compiles both of (iverilog: "'gcn' has already been
    declared"). Lines between directives are batched per condition, so a
    declaration split across lines (``module\\n  name``) still matches.
    """
    # Stack of FRAMES (one per open `ifdef/`ifndef); a frame is the term list
    # of the branch currently in force, INCLUDING the negations of earlier
    # branches in its chain — `ifdef A/`elsif B's second branch is (¬A ∧ B),
    # not just (B). Dropping the ¬A recorded `ifdef X vs `elsif Y alternates
    # as unrelated conditions and manufactured a collision warning for a pair
    # the preprocessor can never compile together.
    frames: List[List[tuple]] = []
    segments: List[tuple] = []
    current: List[str] = []

    def _flush() -> None:
        nonlocal current
        if current:
            cond = frozenset(term for frame in frames for term in frame)
            segments.append((cond, current))
            current = []

    for line in text.splitlines():
        mo = _GUARD_OPEN_RE.match(line)
        if mo:
            _flush()
            frames.append([("+" if mo.group(1) == "ifdef" else "-", mo.group(2))])
            continue
        mo = _GUARD_ELSIF_RE.match(line)
        if mo:
            _flush()
            if frames:
                sign, name = frames[-1][-1]
                frames[-1][-1] = ("-" if sign == "+" else "+", name)
                frames[-1].append(("+", mo.group(1)))
            continue
        if _GUARD_ELSE_RE.match(line):
            _flush()
            if frames:
                sign, name = frames[-1][-1]
                frames[-1][-1] = ("-" if sign == "+" else "+", name)
            continue
        if _GUARD_CLOSE_RE.match(line):
            _flush()
            if frames:
                frames.pop()
            continue
        current.append(line)
    _flush()

    out: Dict[str, set] = {}
    for cond, lines in segments:
        for mod in _find_modules("\n".join(lines)):
            out.setdefault(mod, set()).add(cond)
    return {mod: frozenset(conds) for mod, conds in out.items()}


def _mutually_exclusive(cond_a: frozenset, cond_b: frozenset) -> bool:
    """Some macro appears with opposite signs — both can't survive one run."""
    return any(
        (("-" if sign == "+" else "+"), name) in cond_b for sign, name in cond_a
    )


def _self_defining(cond: frozenset, defines: frozenset) -> bool:
    """An `` `ifndef X`` term whose file also `` `defines X`` — an include
    guard: whichever copy the preprocessor reads first defines the macro, so
    the other copy's region is skipped."""
    return any(sign == "-" and name in defines for sign, name in cond)


def _guards_make_exclusive(entries: List[tuple]) -> bool:
    """True when guard conditions guarantee at most one declaration survives.

    ``entries`` is one ``(condition_set, file_defines)`` pair per declaring
    file. Requires every declaration to be conditional at all, then pairwise
    across files: mutually exclusive conditions (`` `ifdef X`` vs
    `` `ifndef X`` / `` `else`` alternates), or identical SELF-DEFINING
    include guards (`` `ifndef X`` + `` `define X`` in both copies — the
    preprocessor keeps one; verified with iverilog). Identical conditions
    alone are NOT enough: two copies both wrapped in a plain `` `ifdef DEBUG``
    each compile under ``+define+DEBUG`` and still collide. And two copies
    each wrapped in their OWN distinct guard fail outright — both compile.
    """
    for cs, _ in entries:
        if any(not cond for cond in cs):
            return False
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            cs_a, defs_a = entries[i]
            cs_b, defs_b = entries[j]
            for cond_a in cs_a:
                for cond_b in cs_b:
                    if _mutually_exclusive(cond_a, cond_b):
                        continue
                    if (
                        cond_a == cond_b
                        and _self_defining(cond_a, defs_a)
                        and _self_defining(cond_b, defs_b)
                    ):
                        continue
                    return False
    return True


_DEFINE_RE = re.compile(r"^\s*`define\s+(\w+)", re.MULTILINE)


class _FileScan(NamedTuple):
    """What one design file declares — read once, used by every derived field."""
    modules: List[str]
    instances: List[str]
    guarded_modules: Dict[str, frozenset]  # module -> guard conditions (see _guarded_modules)
    defines: frozenset  # macros the file `defines — distinguishes include guards


def _scan_text(text: str) -> _FileScan:
    return _FileScan(
        modules=_modules_in(text),
        instances=_instances_in(text),
        guarded_modules=_guarded_modules(text),
        defines=frozenset(_DEFINE_RE.findall(text)),
    )


# Per-workspace memo of the module scan. Process memory is a cache of disk truth
# (invariant 5): the key is a fingerprint of the files that would be scanned, so
# any edit invalidates it and a stale entry is unreachable rather than merely
# unlikely. Without this the sweep re-read every rtl/tb file on EVERY
# read_manifest — and read_manifest sits under GET /files, GET /code, every
# write_file and every dispatch (measured: 0.011s -> 0.205s on 202 files).
_SCAN_CACHE: Dict[str, tuple] = {}
_SCAN_CACHE_MAX = 64  # bounded: a hosted instance serves many workspaces


def _scan_fingerprint(workspace: str, files: List[DesignFile]) -> tuple:
    """(path, mtime_ns, size, ctime_ns, ino) per file the sweep would read.

    Size alongside mtime because a filesystem's mtime granularity can hide a
    same-tick rewrite. ctime_ns and inode close the hole mtime+size leave open:
    ``shutil.copy2`` PRESERVES mtime (this repo's documented sharp edge —
    bundles.py restores workspaces with it deliberately), so a same-size
    mtime-preserved overwrite fingerprinted as unchanged and served a stale
    scan. The kernel bumps ctime on every write/replace and userspace cannot
    backdate it, so the fingerprint stays stat-only — no content I/O, which is
    the entire point of the cache (sc#81). An unstat-able file fingerprints as
    missing, which differs from any real state and so forces a rescan.
    """
    out = []
    for f in files:
        if f.role not in ("rtl", "tb"):
            continue
        try:
            st = os.stat(os.path.join(workspace, f.path))
            out.append((f.path, st.st_mtime_ns, st.st_size, st.st_ctime_ns, st.st_ino))
        except OSError:
            out.append((f.path, None, None, None, None))
    return tuple(sorted(out))


def _fingerprint_digest(fingerprint: tuple, files: List[DesignFile]) -> str:
    """Compact, persistable form of the tops-inference input.

    The raw fingerprint is one stat tuple per design file — persisting it
    verbatim would bloat manifest.json linearly with the file count. The digest
    is derived metadata only ever compared for equality, so a hash loses
    nothing. Reuses THE fingerprint (ctime/inode terms included), so it stays
    safe against ``shutil.copy2``'s preserved mtimes — no second fingerprint.

    Roles are digested ALONGSIDE the stat fingerprint: fixing a misclassified
    file via ``write_manifest`` (rtl -> tb) changes what inference would
    conclude without touching a single stat, so a stat-only marker left simTop
    stale forever (sc#81 follow-up). Including every file's (path, role) costs
    exactly one re-inference per role edit — the honest price.
    """
    payload = (fingerprint, tuple(sorted((f.path, f.role) for f in files)))
    return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()


def _scan_design_files(
    workspace: str,
    files: List[DesignFile],
    texts: Optional[Dict[str, str]] = None,
    fingerprint: Optional[tuple] = None,
) -> Dict[str, _FileScan]:
    """ONE pass over the rtl/tb text per reconcile, keyed by workspace-relative path.

    ``_infer_tops``, ``_derive_testbenches`` and the duplicate-module detector all
    want the same module/instance lists; each reading the tree itself made the
    reconcile cost a multiple of the file count for no new information.

    ``texts`` lets a caller that has ALREADY read a file (role derivation) hand
    the stripped text over instead of paying for a second read. ``fingerprint``
    does the same for a caller that already computed the scan fingerprint —
    the stat sweep is cheap but not free, and reconcile needs the fingerprint
    anyway for the inference marker.
    """
    if fingerprint is None:
        fingerprint = _scan_fingerprint(workspace, files)
    cached = _SCAN_CACHE.get(workspace)
    if cached is not None and cached[0] == fingerprint:
        return cached[1]

    scans: Dict[str, _FileScan] = {}
    for f in files:
        if f.role not in ("rtl", "tb") or f.path in scans:
            continue
        text = (texts or {}).get(f.path)
        if text is None:
            text = _read_text(os.path.join(workspace, f.path))
        scans[f.path] = _scan_text(text)

    if len(_SCAN_CACHE) >= _SCAN_CACHE_MAX:
        _SCAN_CACHE.clear()
    _SCAN_CACHE[workspace] = (fingerprint, scans)
    return scans


def _roles_by_path(files: List[DesignFile]) -> Dict[str, str]:
    return {f.path: f.role for f in files}


def _and_join(items: List[str]) -> str:
    quoted = [f"'{i}'" for i in items]
    if len(quoted) == 2:
        return f"both {quoted[0]} and {quoted[1]}"
    return ", ".join(quoted[:-1]) + f" and {quoted[-1]}"


def _affected_set(paths: List[str], roles: Optional[Dict[str, str]]) -> str:
    """Which compile set these declarations actually collide in.

    ``rtl`` reaches lint, simulation and synthesis; ``tb`` reaches only
    simulation. So a duplicate between an rtl file and a tb file is a simulation
    problem and nothing else — saying "every compile set" there would be a false
    alarm for synthesis.
    """
    if roles is None:
        return "this compile set"
    if any(roles.get(p) == "tb" for p in paths):
        return "the simulation compile set"
    return "every compile set (lint, simulation, synthesis)"


def _collision_warnings(
    scans: Dict[str, _FileScan], roles: Optional[Dict[str, str]] = None
) -> List[str]:
    """One line per module declared by 2+ files in the given set.

    We never guess which copy is the reference — both are named, and the remedy
    (the ``ignore`` glob) is spelled out, which is the part no compiler can tell
    the user. iverilog hard-errors on the redefinition; yosys names only the
    second file and is one flag away from silently picking one.

    ``roles`` (manifest scan only) narrows the message to the set that actually
    breaks; the dispatch path passes None because the set it was handed IS the
    affected set.
    """
    declared: Dict[str, List[str]] = {}
    for path, scan in scans.items():
        for module in dict.fromkeys(scan.modules):
            declared.setdefault(module, []).append(path)

    out: List[str] = []
    for module, paths in sorted(declared.items()):
        if len(paths) < 2:
            continue
        # Suppress only when the guard MACROS guarantee at most one declaration
        # survives a preprocessor run: mutually exclusive conditions (`ifdef X
        # vs `ifndef X / `else alternates) or the same SELF-DEFINING include
        # guard in both copies — legal, verified with iverilog. Merely "every
        # declaration is guarded" is not enough: two copies each wrapped in
        # their OWN `ifndef X_V-style guard both compile and still collide
        # (sc#66's handout-plus-solution scenario), a plain identical `ifdef
        # DEBUG in both copies collides under +define+DEBUG, and an
        # unconditional declaration always compiles.
        entries = [
            (
                scans[p].guarded_modules.get(module, frozenset({frozenset()})),
                scans[p].defines,
            )
            for p in paths
        ]
        if _guards_make_exclusive(entries):
            continue
        out.append(
            f"module '{module}' is declared by {_and_join(paths)} — they collide in "
            f"{_affected_set(paths, roles)}, which can hold only one definition "
            f"(iverilog errors out; yosys may just pick one). "
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
    texts: Dict[str, str] = {}
    for rel in _list_source_files(workspace):
        text = _read_text(os.path.join(workspace, rel)) if rel.lower().endswith((".v", ".sv")) else ""
        texts[rel] = text  # hand it to the sweep instead of reading twice
        files.append(DesignFile(name=os.path.basename(rel), role=derive_role(rel, text), path=rel))

    fingerprint = _scan_fingerprint(workspace, files)
    scans = _scan_design_files(workspace, files, texts=texts, fingerprint=fingerprint)
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
        warnings=_collision_warnings(scans, _roles_by_path(files)),
        topsInferredFingerprint=_fingerprint_digest(fingerprint, files),
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


def _coerce_files(raw_files: Any) -> tuple[List[DesignFile], bool]:
    """Stored file entries → DesignFile, one bad field at a time.

    An unrecognized role reads as ``rtl`` with a log line instead of failing the
    document. Hosted runs rolling deploys (invariant 9), so an old reader WILL
    meet a manifest written by a newer one; the alternative — discarding the
    document — wipes every user field on the way past.
    """
    out: List[DesignFile] = []
    coerced = False
    if not isinstance(raw_files, list):
        return out, coerced
    for entry in raw_files:
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
                "manifest: unrecognized role %r for %r — using %r for this read; "
                "the stored value is left on disk untouched",
                role, path, _ROLE_FALLBACK,
            )
            role = _ROLE_FALLBACK
            coerced = True
        out.append(DesignFile(name=name, role=role, path=path))
    return out, coerced


def _manifest_from_raw(raw: Dict[str, Any]) -> tuple[DesignManifest, bool]:
    """Per-FIELD tolerant load: a value this reader can't use costs that field,
    never the document. ``testbenches`` is derived — reconcile recomputes it.

    Returns ``(manifest, coerced)``; ``coerced`` is True when a role had to be
    downgraded, which is the caller's signal not to write the result back.
    """
    manifest = DesignManifest()
    manifest.files, coerced = _coerce_files(raw.get("files"))
    for key in ("sessionId", "synthTop", "simTop", "platform", "passMarker", "topsInferredFingerprint"):
        value = raw.get(key)
        if isinstance(value, str):
            setattr(manifest, key, value)
    clock = raw.get("clockPeriodNs")
    if isinstance(clock, bool):
        clock = None
    if isinstance(clock, (int, float)):
        manifest.clockPeriodNs = float(clock)
    elif isinstance(clock, str):
        # A numeric string ("10.0") is what a hand-edited manifest or a loosely
        # typed client writes. Silently resetting a real constraint to the 10.0
        # default is the kind of quiet wrong answer this whole item is about.
        try:
            manifest.clockPeriodNs = float(clock.strip())
        except ValueError:
            logger.warning("manifest: clockPeriodNs %r is not a number — keeping the default", clock)
    ignore = raw.get("ignore")
    if isinstance(ignore, list):
        manifest.ignore = [p for p in ignore if isinstance(p, str) and p]
    return manifest, coerced


def stored_ignore(workspace: str) -> List[str]:
    """The persisted ``ignore`` globs, WITHOUT a reconcile.

    For callers that need the user's exclusions and nothing else (staging data
    files into a run dir). ``read_manifest`` re-scans and re-infers tops on every
    read, which costs seconds on a large workspace — a price a file copy should
    not pay. Returns [] when no manifest exists yet.
    """
    raw = _load_raw(workspace)
    ignore = raw.get("ignore") if isinstance(raw, dict) else None
    if not isinstance(ignore, list):
        return []
    return [p for p in ignore if isinstance(p, str) and p]


def stored_pass_marker(workspace: str) -> str:
    """The persisted ``passMarker``, WITHOUT a reconcile.

    Same rationale as :func:`stored_ignore`: the simulation runner needs one
    string, not a rescan of the workspace. Returns "" when no manifest exists
    or no marker is set — the caller falls back to its default.
    """
    raw = _load_raw(workspace)
    marker = raw.get("passMarker") if isinstance(raw, dict) else None
    return marker if isinstance(marker, str) else ""


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
    texts: Dict[str, str] = {}
    for rel in on_disk:
        if rel in by_path:
            merged.append(by_path[rel])
        else:
            text = _read_text(os.path.join(workspace, rel)) if rel.lower().endswith((".v", ".sv")) else ""
            texts[rel] = text  # newly discovered: reuse the read the sweep needs
            merged.append(DesignFile(name=os.path.basename(rel), role=derive_role(rel, text), path=rel))

    stored.files = merged

    fingerprint = _scan_fingerprint(workspace, merged)
    scans = _scan_design_files(workspace, merged, texts=texts, fingerprint=fingerprint)
    if not stored.synthTop or not stored.simTop:
        # A top may be EMPTY because inference already ran and found nothing
        # (e.g. no testbench -> simTop stays ""). The persisted marker tells
        # that apart from "not yet inferred": re-infer only when the design
        # file set — content stats OR roles — actually changed since inference
        # last ran (sc#81). A user-set top is never overwritten either way
        # (`or` keeps it).
        digest = _fingerprint_digest(fingerprint, merged)
        if stored.topsInferredFingerprint != digest:
            synth_top, sim_top = _infer_tops(merged, scans)
            stored.synthTop = stored.synthTop or synth_top
            stored.simTop = stored.simTop or sim_top
            stored.topsInferredFingerprint = digest
    stored.testbenches = _derive_testbenches(merged, scans)
    stored.warnings = _collision_warnings(scans, _roles_by_path(merged))
    return stored


def read_manifest(workspace: str, session_id: str = "") -> DesignManifest:
    """Return the manifest, auto-deriving + persisting one if absent.

    Always reconciles against the files currently on disk so uploads/deletes
    made outside the manifest API are reflected.

    One exception to the write-back: when a role had to be coerced (a value this
    reader doesn't know, i.e. a NEWER writer during a rolling deploy), the result
    is NOT persisted. Reading must not be what destroys the other version's data
    — otherwise the first old-instance read makes the loss permanent, long after
    the traffic split is over. An explicit ``write_manifest`` still rewrites it;
    that is a user editing through an old client, which we cannot second-guess.
    """
    raw = _load_raw(workspace)
    if raw is None or not isinstance(raw, dict):
        manifest = build_manifest(workspace, session_id=session_id)
        _persist(workspace, manifest)
        return manifest
    stored, coerced = _manifest_from_raw(raw)
    if session_id and not stored.sessionId:
        stored.sessionId = session_id
    stored = _reconcile(workspace, stored)
    if not coerced:
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

    # Roles this reader doesn't know (a NEWER writer during a rolling deploy)
    # are coerced to rtl for THIS read — but this function persists, and an
    # unrelated edit (clock period from the IDE) must not make the coercion
    # permanent. Capture the stored originals so they round-trip verbatim;
    # only an EXPLICIT role update for that same path may replace one.
    raw_before = _load_raw(workspace)
    unknown_roles: Dict[str, str] = {}
    if isinstance(raw_before, dict) and isinstance(raw_before.get("files"), list):
        for entry in raw_before["files"]:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path") or entry.get("name")
            role = entry.get("role")
            if isinstance(path, str) and path and isinstance(role, str) and role not in ROLES:
                unknown_roles[path] = role

    current = read_manifest(workspace, session_id=session_id)
    explicitly_set: set = set()

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
                explicitly_set.add(target.path)

    for key in ("synthTop", "simTop", "platform", "sessionId"):
        if key in updates and isinstance(updates[key], str) and updates[key]:
            setattr(current, key, updates[key])
    # passMarker accepts the empty string on purpose: clearing it means "back
    # to the simulation default", which is a legitimate edit (unlike blanking
    # a top, which would just be re-inferred).
    if "passMarker" in updates and isinstance(updates["passMarker"], str):
        current.passMarker = updates["passMarker"]
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
    current.warnings = _collision_warnings(scans, _roles_by_path(current.files))

    # Round-trip a newer writer's roles: the coerced 'rtl' was a READ decision,
    # and persisting it here would be silent, permanent data loss (a formal
    # harness re-entering the synthesis compile set). The restore goes into a
    # COPY that only _persist sees: the returned object keeps the coerced view,
    # matching what the next read returns — handing an off-enum role back to
    # callers put an unknown value into a closed TS union and dropped the file
    # from any compile set computed on the return value. pydantic v2 does not
    # validate on assignment, so the stored string passes through untouched.
    persisted = current
    if unknown_roles:
        persisted = current.model_copy(deep=True)
        for f in persisted.files:
            stored_role = unknown_roles.get(f.path)
            if stored_role is not None and f.path not in explicitly_set:
                f.role = stored_role  # type: ignore[assignment]

    _persist(workspace, persisted)
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


def include_dirs(manifest: DesignManifest) -> List[str]:
    """Workspace-relative directories of the manifest's include-role files —
    the ``-I`` search path a lint/compile needs for an `` `include`` that does
    not live beside the file including it (``"."`` for the workspace root).

    The manifest is the ONE source of this (invariant 1): the REST twin and
    the agent/MCP wrapper both pass it to ``run_linter``, so an explicit agent
    file list still resolves the design's headers. It is deliberately NOT the
    source files' directories — on verilator ``-I`` doubles as a module
    library, and naming a source directory there silently widens the compile
    past the files given (see ``run_linter``).
    """
    return sorted({posixpath.dirname(f.path) or "." for f in manifest.files if f.role == "include"})


def dropped_manifest_files(manifest_files: List[str], override_files: List[str]) -> List[str]:
    """Manifest-supplied files a user override leaves out, in manifest order —
    the delta between :func:`files_for_stage`'s set and what actually ran."""
    override = set(override_files)
    return [rel for rel in manifest_files if rel not in override]


def override_drop_notes(
    stage: str,
    manifest_files: List[str],
    override_files: List[str],
    compiled: Optional[Collection[str]] = None,
    engine: str = "",
) -> List[str]:
    """One honest note per manifest-supplied file a user override leaves out.

    Same delivery pattern as :func:`compile_set_collisions` (best-effort notes
    in the reply, never a dispatch failure) — the override is legitimate; the
    note just says out loud what it changed. Empty when the override covers
    the whole manifest set.

    ``compiled``: the files the engine proved it read on THIS run
    (``run_linter.files_compiled``). A dropped file that is in it was not
    left out after all — a header the listed files `` `include``, or a module
    verilator found by library lookup in an include directory — and the note
    says exactly that instead of the false "not part of this run" (invariant
    4). The read list does not say WHICH of the two happened, so the note
    names both rather than guess. Callers that cannot measure (simulate,
    synthesize; a failed verilator elaboration writes no read list) pass
    nothing and get the plain wording.
    """
    compiled_set = set(compiled or ())
    who = engine or "the engine"
    notes: List[str] = []
    for rel in dropped_manifest_files(manifest_files, override_files):
        if rel in compiled_set:
            notes.append(
                f"Override omits manifest {stage} file '{rel}' — {who} read it anyway "
                "(`include, or a module lookup in an include directory); the verdict covers it."
            )
        else:
            notes.append(f"Override omits manifest {stage} file '{rel}' — it is not part of this run.")
    return notes


def synthesis_sources(files: List[str]) -> "tuple[List[str], List[str]]":
    """(the ``.v``/``.sv`` sources in ``files``, one note per file the filter dropped).

    Synthesis compiles only RTL sources; constraints flow via constraintsMode,
    not the file list. The manifest path applies this filter silently (its
    ``sdc`` role never was a source), but an EXPLICIT file must never vanish
    without a word — the REST twin and the agent/MCP wrapper both call this so
    every actor narrates the same drop the same way (invariant 2).
    """
    src = [f for f in files if f.lower().endswith(RTL_EXTS)]
    notes = [
        f"Override file '{f}' was dropped — synthesis compiles only .v/.sv "
        "sources (constraints flow via constraintsMode, not this list)."
        for f in files if f not in src
    ]
    return src, notes


def modules_defined_by(workspace: str, manifest: DesignManifest, paths: List[str]) -> set:
    """Module names the given manifest design files DECLARE, from the ONE
    cached module scan every reconcile already pays for (:func:`_scan_design_files`).

    This is what makes a file-scoped lint a statement of fact rather than a
    policy: an engine's "Unknown module type: X" is only a scoping artifact
    when X is defined by a file the caller deliberately left out. Only rtl/tb
    files are scanned (the manifest's own rule), so a dropped ``include`` file
    contributes nothing — an unresolved name it happened to define stays an
    error, which is the strict direction.
    """
    scans = _scan_design_files(workspace, manifest.files)
    return {m for p in paths for m in (scans[p].modules if p in scans else ())}
