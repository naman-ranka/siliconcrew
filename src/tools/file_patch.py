import os
import re
import subprocess
from typing import Dict, List


_PATH_RE = re.compile(r"^(?:\+\+\+|---)\s+(?:a/|b/)?([^\t\n\r]+)")


def _extract_patch_paths(unified_diff: str) -> List[str]:
    paths = []
    for line in unified_diff.splitlines():
        m = _PATH_RE.match(line)
        if not m:
            continue
        p = m.group(1).strip()
        if p == "/dev/null":
            continue
        paths.append(p)
    # preserve order, de-dup
    seen = set()
    out = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _validate_workspace_paths(workspace: str, rel_paths: List[str]) -> Dict[str, str]:
    w = os.path.abspath(workspace)
    for rel in rel_paths:
        if os.path.isabs(rel):
            return {"ok": False, "error": f"Absolute patch path is not allowed: {rel}"}
        norm = os.path.normpath(rel)
        target = os.path.abspath(os.path.join(w, norm))
        if not target.startswith(w + os.sep) and target != w:
            return {"ok": False, "error": f"Patch path escapes workspace: {rel}"}
    return {"ok": True}


def apply_unified_patch(workspace: str, unified_diff: str) -> Dict:
    if not unified_diff.strip():
        return {"success": False, "message": "Empty patch."}

    paths = _extract_patch_paths(unified_diff)
    if not paths:
        return {"success": False, "message": "No patch file paths found in unified diff headers."}

    valid = _validate_workspace_paths(workspace, paths)
    if not valid.get("ok"):
        return {"success": False, "message": valid["error"]}

    # git apply works in non-repo directories for patch application.
    check_cmd = ["git", "apply", "--check", "--recount", "--whitespace=nowarn", "-"]
    apply_cmd = ["git", "apply", "--recount", "--whitespace=nowarn", "-"]

    try:
        chk = subprocess.run(check_cmd, cwd=workspace, input=unified_diff, text=True, capture_output=True)
    except Exception as exc:
        return {"success": False, "message": f"Failed to run git apply check: {exc}"}

    if chk.returncode != 0:
        detail = (chk.stderr or chk.stdout or "").strip()
        return {"success": False, "message": f"Patch check failed: {detail}"}

    try:
        res = subprocess.run(apply_cmd, cwd=workspace, input=unified_diff, text=True, capture_output=True)
    except Exception as exc:
        return {"success": False, "message": f"Failed to run git apply: {exc}"}

    if res.returncode != 0:
        detail = (res.stderr or res.stdout or "").strip()
        return {"success": False, "message": f"Patch apply failed: {detail}"}

    return {
        "success": True,
        "message": "Patch applied successfully.",
        "files_changed": paths,
    }
