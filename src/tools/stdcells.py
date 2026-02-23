import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

STDROOT = "_stdcells"

SOURCE_PATHS = {
    "asap7": [
        "/OpenROAD-flow-scripts/flow/platforms/asap7/verilog/stdcell",
    ],
    "sky130hd": [
        "/OpenROAD-flow-scripts/flow/platforms/sky130hd",
    ],
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stdcell_cache_dir(workspace: str, platform: str) -> str:
    return os.path.join(workspace, STDROOT, platform, "sim")


def stdcell_manifest_path(workspace: str, platform: str) -> str:
    return os.path.join(stdcell_cache_dir(workspace, platform), "manifest.json")


def read_stdcell_manifest(workspace: str, platform: str) -> Dict:
    path = stdcell_manifest_path(workspace, platform)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def resolve_stdcell_models(workspace: str, platform: str) -> Tuple[List[str], Dict]:
    sim_dir = stdcell_cache_dir(workspace, platform)
    manifest = read_stdcell_manifest(workspace, platform)
    if not os.path.exists(sim_dir):
        raise FileNotFoundError(
            f"Standard-cell cache missing for platform '{platform}'. Run: python scripts/bootstrap_stdcells.py --platform {platform} --workspace {workspace}"
        )

    files = []
    for name in sorted(os.listdir(sim_dir)):
        if name.endswith(".v"):
            files.append(os.path.join(sim_dir, name))

    if not files:
        raise FileNotFoundError(
            f"No stdcell model files found in {sim_dir}. Run bootstrap script to populate cache."
        )

    return files, manifest


def _docker_container_create(image: str) -> str:
    proc = subprocess.run(["docker", "create", image], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "docker create failed")
    return proc.stdout.strip()


def _docker_cp(container_id: str, src: str, dst: str) -> bool:
    proc = subprocess.run(["docker", "cp", f"{container_id}:{src}", dst], capture_output=True, text=True)
    if proc.returncode == 0:
        return True

    # Windows commonly fails copying container symlinks (privilege issue),
    # while still copying regular files successfully.
    if "A required privilege is not held by the client" in (proc.stderr or ""):
        for _, _, files in os.walk(dst):
            if files:
                return True
    return False


def bootstrap_stdcells(workspace: str, platform: str, image: str = "openroad/orfs:latest") -> Dict:
    if platform not in SOURCE_PATHS:
        raise ValueError(f"Unsupported platform '{platform}'. Supported: {sorted(SOURCE_PATHS)}")

    cache_dir = stdcell_cache_dir(workspace, platform)
    os.makedirs(cache_dir, exist_ok=True)

    tmp_root = os.path.join(cache_dir, ".tmp_extract")
    if os.path.exists(tmp_root):
        shutil.rmtree(tmp_root)
    os.makedirs(tmp_root, exist_ok=True)

    container_id = _docker_container_create(image)
    copied_any = False
    try:
        for idx, src in enumerate(SOURCE_PATHS[platform]):
            dst = os.path.join(tmp_root, f"src_{idx}")
            os.makedirs(dst, exist_ok=True)
            if _docker_cp(container_id, src, dst):
                copied_any = True
    finally:
        subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, text=True)

    if not copied_any:
        raise FileNotFoundError(f"Could not copy stdcell source paths from docker image for platform '{platform}'")

    found = []
    for root, _, files in os.walk(tmp_root):
        for name in files:
            if name.endswith(".v"):
                src = os.path.join(root, name)
                dst = os.path.join(cache_dir, name)
                shutil.copy2(src, dst)
                found.append(dst)

    shutil.rmtree(tmp_root, ignore_errors=True)

    if not found:
        raise FileNotFoundError(f"Bootstrap completed but found no .v files for platform '{platform}'")

    manifest_files = []
    for fpath in sorted(found):
        manifest_files.append(
            {
                "name": os.path.basename(fpath),
                "sha256": _sha256(fpath),
            }
        )

    manifest = {
        "platform": platform,
        "source_image": image,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "files": manifest_files,
    }

    with open(stdcell_manifest_path(workspace, platform), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return {
        "platform": platform,
        "cache_dir": cache_dir,
        "file_count": len(found),
        "manifest": stdcell_manifest_path(workspace, platform),
    }
