"""Run SymbiYosys (SBY) formal verification through the ToolEngine seam.

Execution is delegated to ``get_tool_engine()``:
  * **docker** (local default): the ``siliconcrew-sby`` container (sby + yosys + z3),
    named + hard-killed on timeout so a non-terminating proof cannot orphan a container.
  * **native** (hosted / Cloud Run): ``sby`` runs as a subprocess in the per-session
    workspace — needs ``sby`` + ``z3`` on PATH (installed in the hosted image).

Robustness (added after a forensics pass over real runs, where the dominant failures were NOT the
solver but agent-written .sby mistakes — see cvdp-pipeline/research/AUDIT_XLS_TOOLING_LEAK.md):
  1. Runs from the **workspace root** deterministically (not the .sby's own dir), so a .sby placed in
     a subdir (e.g. formal/) no longer breaks relative [files] paths.
  2. **Normalizes the .sby before running**: resolves every [files] path against the workspace and
     rewrites it workspace-root-relative (validating it exists, with a clear error naming the cwd);
     and rewrites an unavailable solver engine (boolector/yices/bare smtbmc) to the installed ``z3``.
  3. The original .sby is never mutated — a normalized copy is run and cleaned up.
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile

from src.platform_engines.tool_engine import get_tool_engine

DEFAULT_SBY_IMAGE = "siliconcrew-sby:latest"   # openroad/orfs + z3 (build: docker build -t siliconcrew-sby:latest - < Dockerfile.sby)
DEFAULT_TIMEOUT = 110                           # under codex's ~120s MCP tool-call limit
INSTALLED_SOLVER = "z3"                         # the solver guaranteed present in both images
_UNAVAILABLE_SOLVERS = ("boolector", "btor", "yices")  # not installed; rewrite to z3


_HDL_EXT = (".sv", ".v", ".svh", ".vh")


def _index_basenames(workdir: str) -> dict:
    """basename -> [workspace-relative paths] for every HDL file under workdir (skips hidden/sby dirs)."""
    idx: dict[str, list[str]] = {}
    for root, dirs, files in os.walk(workdir):
        dirs[:] = [d for d in dirs if not d.startswith(".") and not d.startswith("_sc_sby_") and d != "sim_build"]
        for f in files:
            if f.lower().endswith(_HDL_EXT):
                idx.setdefault(f, []).append(os.path.relpath(os.path.join(root, f), workdir).replace("\\", "/"))
    return idx


def _resolve_file(path: str, workdir: str, sby_dir: str, bn_index: dict):
    """Resolve an HDL source path to a workdir-relative path. Tries the path as written (vs workdir and
    the .sby's dir), then falls back to a unique basename match anywhere in the workspace — which
    auto-fixes the common 'wrong relative prefix' mistake. Returns (relpath|None, how)."""
    cands = [path] if os.path.isabs(path) else [
        os.path.normpath(os.path.join(workdir, path)),
        os.path.normpath(os.path.join(sby_dir, path)),
    ]
    for c in cands:
        if os.path.exists(c):
            return os.path.relpath(c, workdir).replace("\\", "/"), None
    hits = bn_index.get(os.path.basename(path), [])
    # Prefer real source locations over sby sandbox copies (`<task>/src/...`) and build dirs.
    real = [h for h in hits if "/src/" not in h and "/sim_build/" not in h]
    pick = real or hits
    if len(pick) == 1:
        return pick[0], "basename"
    if len(pick) > 1:
        return None, f"ambiguous: {pick}"
    return None, "missing"


def _normalize_sby(text: str, workdir: str, sby_dir: str):
    """Return (normalized_text, missing_files, notes). Makes an agent-written .sby robust:
      * [engines]: rewrite an unavailable solver (boolector/yices/bare smtbmc) to 'smtbmc z3'.
      * [files]: resolve each source path workspace-relative (with basename fallback), validate.
      * [script] reads: rewrite HDL path args to basenames (sby copies [files] flat into the sandbox),
        and make sure every file a [script] read references is present in [files].
    """
    bn = _index_basenames(workdir)
    notes, missing, out = [], [], []
    section = None
    files_hdr_idx = None
    files_have: set[str] = set()
    script_refs: dict[str, str] = {}   # basename -> workdir-relative source

    for raw in text.splitlines():
        s = raw.strip()
        head = re.match(r"^\[(\w+)\]", s)
        if head:
            section = head.group(1).lower()
            out.append(raw)
            if section == "files":
                files_hdr_idx = len(out) - 1
            continue
        if s and not s.startswith("#") and section == "engines":
            low = s.lower()
            if any(b in low for b in _UNAVAILABLE_SOLVERS) or low == "smtbmc":
                out.append(f"smtbmc {INSTALLED_SOLVER}")
                notes.append(f"engine '{s}' -> 'smtbmc {INSTALLED_SOLVER}'")
                continue
        if s and not s.startswith("#") and section == "files":
            toks = s.split()
            res, how = _resolve_file(toks[-1], workdir, sby_dir, bn)
            if res is None:
                missing.append(f"{toks[-1]} ({how})")
                out.append(raw)
                continue
            if res != toks[-1]:
                notes.append(f"[files] '{toks[-1]}' -> '{res}'" + (f" (by {how})" if how else ""))
            toks[-1] = res
            files_have.add(os.path.basename(res))
            out.append(" ".join(toks))
            continue
        if s and not s.startswith("#") and section == "script" and s.lower().startswith("read"):
            toks = s.split()
            new = []
            for t in toks:
                if t.lower().endswith(_HDL_EXT):
                    res, how = _resolve_file(t, workdir, sby_dir, bn)
                    bnm = os.path.basename(res or t)
                    if res:
                        script_refs[bnm] = res
                    if bnm != t:
                        notes.append(f"[script] read '{t}' -> '{bnm}'")
                    new.append(bnm)
                else:
                    new.append(t)
            out.append(" ".join(new))
            continue
        out.append(raw)

    # ensure every [script]-read file is copied via [files]
    additions = [r for b, r in script_refs.items() if b not in files_have]
    if additions:
        if files_hdr_idx is None:
            out.append("[files]")
            files_hdr_idx = len(out) - 1
        for r in additions:
            out.insert(files_hdr_idx + 1, r)
            notes.append(f"[files] += '{r}' (referenced by [script])")

    return "\n".join(out) + "\n", missing, notes


def run_sby(sby_file, cwd=None, timeout=DEFAULT_TIMEOUT, image=DEFAULT_SBY_IMAGE) -> dict:
    """Run `sby` on a (normalized) copy of the agent's .sby via the selected ToolEngine.

    Returns: {success, status: PASS|FAIL|TIMEOUT|ERROR|UNKNOWN, timed_out, stdout, stderr,
              counter_example, command}
    """
    abs_sby = os.path.abspath(sby_file)
    if not os.path.exists(abs_sby):
        return _err(f"SBY file not found: {sby_file}")

    sby_dir = os.path.dirname(abs_sby)
    workdir = os.path.abspath(cwd) if cwd else sby_dir   # deterministic: workspace root

    try:
        text = open(abs_sby, encoding="utf-8", errors="ignore").read()
    except OSError as e:
        return _err(f"could not read {sby_file}: {e}")

    norm, missing, notes = _normalize_sby(text, workdir, sby_dir)
    if missing:
        return _err(
            f"SBY [files] not found from the workspace root ({workdir}): {', '.join(missing)}. "
            "List source files in [files] using workspace-root-relative paths "
            "(e.g. 'rtl/dut.sv', 'verif/dut_formal.sv')."
        )

    # Run a normalized copy inside workdir so its (workdir-relative) [files] resolve; never touch
    # the agent's original. sby creates a task dir named after the .sby stem — clean both up.
    fd, norm_path = tempfile.mkstemp(prefix="_sc_sby_", suffix=".sby", dir=workdir)
    os.close(fd)
    open(norm_path, "w", encoding="utf-8", newline="\n").write(norm)
    sby_name = os.path.basename(norm_path)
    task_dir = os.path.join(workdir, sby_name[:-4])      # strip ".sby"
    command = f"sby -f {sby_name}"

    try:
        res = get_tool_engine().run(
            image=image, command=command, cwd=workdir, timeout=timeout, name_prefix="sc_sby"
        )
    finally:
        for p in (norm_path,):
            try:
                os.remove(p)
            except OSError:
                pass
        shutil.rmtree(task_dir, ignore_errors=True)

    stdout = res.get("stdout", "") or ""
    stderr = res.get("stderr", "") or ""
    if notes:
        stdout = "[sby_tool normalized: " + "; ".join(notes) + "]\n" + stdout
    timed_out = bool(res.get("timed_out"))
    status = _classify(stdout + stderr, 0 if res.get("success") else 1, timed_out)
    return {
        "success": status == "PASS",
        "status": status,
        "timed_out": timed_out,
        "stdout": stdout,
        "stderr": stderr,
        "counter_example": None,
        "command": res.get("command", command),
    }


def _classify(out: str, rc: int, timed_out: bool) -> str:
    if timed_out:
        return "TIMEOUT"
    if "DONE (PASS" in out:
        return "PASS"
    if "DONE (FAIL" in out:
        return "FAIL"
    if "DONE (UNKNOWN" in out or "DONE (TIMEOUT" in out or "DONE (ERROR" in out:
        return "ERROR"
    if "ERROR:" in out or "Traceback (most recent call last)" in out or rc != 0:
        return "ERROR"
    return "UNKNOWN"


def _err(msg: str, command: str = "") -> dict:
    return {"success": False, "status": "ERROR", "timed_out": False,
            "stdout": "", "stderr": msg, "counter_example": None, "command": command}
