import hashlib
import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Tuple

STDROOT = "_stdcells"

PINNED_GITHUB_SOURCES = {
    "asap7": {
        "orfs_repo": "The-OpenROAD-Project/OpenROAD-flow-scripts",
        "orfs_ref": "5f96c41ce70550f4b264c7a2680cf15301a454ff",
        "asap7_repo": "The-OpenROAD-Project/asap7sc7p5t_28",
        "asap7_ref": "f970bd3c3292b79ae4d022a3ec80533534614066",
    },
    "sky130hd": {
        "repo": "google/skywater-pdk-libs-sky130_fd_sc_hd",
        "ref": "ac7fb61f06e6470b94e8afdf7c25268f62fbd7b1",
    },
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _clear_cached_sim_models(cache_dir: str) -> None:
    """
    Remove previously cached top-level simulation model files.

    This keeps bootstrap deterministic across reruns by preventing stale model
    variants from surviving when source selection policy changes.
    """
    if not os.path.isdir(cache_dir):
        return
    for name in os.listdir(cache_dir):
        path = os.path.join(cache_dir, name)
        if os.path.isfile(path) and name.endswith(".v"):
            try:
                os.remove(path)
            except Exception:
                pass


def stdcell_cache_dir(workspace: str, platform: str) -> str:
    return os.path.join(workspace, STDROOT, platform, "sim")


def stdcell_manifest_path(workspace: str, platform: str) -> str:
    return os.path.join(stdcell_cache_dir(workspace, platform), "manifest.json")


def get_asap7_compat_model_files() -> List[str]:
    """Behavioral ASAP7 compatibility models for Icarus gate-level simulation."""
    base_dir = os.path.join(os.path.dirname(__file__), "asap7_compat_models")
    files = [
        os.path.join(base_dir, "DFFASRHQNx1_behavioral.v"),
    ]
    return [f for f in files if os.path.exists(f)]


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
        if name.endswith(".v") and _is_sim_model_file(platform, name):
            files.append(os.path.join(sim_dir, name))

    if not files:
        raise FileNotFoundError(
            f"No stdcell model files found in {sim_dir}. Run bootstrap script to populate cache."
        )

    return files, manifest


def _is_sim_model_file(platform: str, filename: str) -> bool:
    if not filename.endswith(".v"):
        return False
    if platform == "sky130hd":
        return filename.startswith("sky130_fd_sc_hd__")
    if platform == "asap7":
        # ORFS dff/empty collide with definitions already present in ASAP7 SEQ views for Icarus runs.
        if filename in {"dff.v", "empty.v"}:
            return False
    return True


def _download_file(url: str, dst: str, timeout_sec: int = 20) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout_sec) as r:
            data = r.read()
        if not data:
            return False
        with open(dst, "wb") as f:
            f.write(data)
        return True
    except Exception:
        return False


def _download_text(url: str, timeout_sec: int = 20) -> str:
    with urllib.request.urlopen(url, timeout=timeout_sec) as r:
        return r.read().decode("utf-8")


def _github_raw(repo: str, ref: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/{repo}/{ref}/{path}"


def _populate_asap7_pinned(cache_dir: str) -> Dict[str, List[str]]:
    cfg = PINNED_GITHUB_SOURCES["asap7"]
    added: List[str] = []
    failed: List[str] = []
    attempted: List[str] = []
    existing = set(os.listdir(cache_dir)) if os.path.exists(cache_dir) else set()

    required = [
        "asap7sc7p5t_AO_RVT_TT_201020.v",
        "asap7sc7p5t_INVBUF_RVT_TT_201020.v",
        "asap7sc7p5t_OA_RVT_TT_201020.v",
        "asap7sc7p5t_SEQ_RVT_TT_220101.v",
        "asap7sc7p5t_SIMPLE_RVT_TT_201020.v",
        "dff.v",
        "empty.v",
    ]

    for filename in required:
        if filename in existing:
            continue

        urls: List[str] = []
        urls.append(
            _github_raw(
                cfg["orfs_repo"],
                cfg["orfs_ref"],
                f"flow/platforms/asap7/verilog/stdcell/{filename}",
            )
        )
        if filename.startswith("asap7sc7p5t_"):
            urls.append(_github_raw(cfg["asap7_repo"], cfg["asap7_ref"], f"Verilog/{filename}"))
        dst = os.path.join(cache_dir, filename)
        ok = False
        for url in urls:
            attempted.append(url)
            if _download_file(url, dst):
                ok = True
                added.append(filename)
                existing.add(filename)
                break
        if not ok:
            failed.append(filename)

    return {"added": added, "failed": failed, "attempted_urls": attempted}


def _rewrite_sky130_includes(text: str) -> str:
    return re.sub(
        r'`include\s+"(?:\.\./)+models/[^/]+/([^"]+)"',
        r'`include "\1"',
        text,
    )


def _populate_sky130_pinned(cache_dir: str) -> Dict[str, List[str]]:
    cfg = PINNED_GITHUB_SOURCES["sky130hd"]
    repo = cfg["repo"]
    ref = cfg["ref"]

    added: List[str] = []
    failed: List[str] = []
    attempted: List[str] = []
    existing = set(os.listdir(cache_dir)) if os.path.exists(cache_dir) else set()

    tar_url = f"https://codeload.github.com/{repo}/tar.gz/{ref}"
    attempted.append(tar_url)
    with tempfile.TemporaryDirectory(prefix="sky130hd_src_") as tmp:
        tar_path = os.path.join(tmp, "sky130hd.tar.gz")
        if not _download_file(tar_url, tar_path, timeout_sec=60):
            return {"added": [], "failed": ["tarball_download_failed"], "attempted_urls": attempted}

        extract_root = os.path.join(tmp, "extract")
        os.makedirs(extract_root, exist_ok=True)
        try:
            with tarfile.open(tar_path, "r:gz") as tf:
                tf.extractall(extract_root)
        except Exception:
            return {"added": [], "failed": ["tarball_extract_failed"], "attempted_urls": attempted}

        repo_root = None
        for item in os.listdir(extract_root):
            full = os.path.join(extract_root, item)
            if os.path.isdir(full):
                repo_root = full
                break
        if not repo_root:
            return {"added": [], "failed": ["tarball_root_missing"], "attempted_urls": attempted}

        cells_root = os.path.join(repo_root, "cells")
        models_root = os.path.join(repo_root, "models")
        wrapper_re = re.compile(r"^sky130_fd_sc_hd__.*_[0-9]+\.v$")

        if os.path.isdir(cells_root):
            for cell_name in sorted(os.listdir(cells_root)):
                cell_dir = os.path.join(cells_root, cell_name)
                if not os.path.isdir(cell_dir):
                    continue
                cell_files = sorted(os.listdir(cell_dir))
                for name in cell_files:
                    src = os.path.join(cell_dir, name)
                    if not os.path.isfile(src):
                        continue

                    if wrapper_re.match(name):
                        if name in existing:
                            continue
                        shutil.copy2(src, os.path.join(cache_dir, name))
                        added.append(name)
                        existing.add(name)
                        continue

                # Base cell model preference for Icarus:
                # functional.v is generally more robust than behavioral.v.
                functional_src = None
                behavioral_src = None
                for name in cell_files:
                    if name.endswith(".functional.v") and ".pp." not in name:
                        functional_src = os.path.join(cell_dir, name)
                        break
                if functional_src is None:
                    for name in cell_files:
                        if name.endswith(".behavioral.v") and ".pp." not in name:
                            behavioral_src = os.path.join(cell_dir, name)
                            break

                chosen_src = functional_src or behavioral_src
                if chosen_src:
                    src_name = os.path.basename(chosen_src)
                    if src_name.endswith(".functional.v"):
                        dst_name = src_name.replace(".functional.v", ".v")
                    else:
                        dst_name = src_name.replace(".behavioral.v", ".v")
                    if dst_name not in existing:
                        try:
                            with open(chosen_src, "r", encoding="utf-8") as f:
                                text = f.read()
                            text = _rewrite_sky130_includes(text)
                            with open(os.path.join(cache_dir, dst_name), "w", encoding="utf-8") as out:
                                out.write(text)
                            added.append(dst_name)
                            existing.add(dst_name)
                        except Exception:
                            failed.append(dst_name)

        if os.path.isdir(models_root):
            for model_name in sorted(os.listdir(models_root)):
                model_dir = os.path.join(models_root, model_name)
                if not os.path.isdir(model_dir):
                    continue
                for name in sorted(os.listdir(model_dir)):
                    src = os.path.join(model_dir, name)
                    if not os.path.isfile(src):
                        continue
                    if not name.endswith(".v"):
                        continue
                    if name.endswith(".tb.v") or name.endswith(".symbol.v") or name.endswith(".blackbox.v"):
                        continue
                    if name in existing:
                        continue
                    shutil.copy2(src, os.path.join(cache_dir, name))
                    added.append(name)
                    existing.add(name)

    return {"added": added, "failed": failed, "attempted_urls": attempted}


def bootstrap_stdcells(workspace: str, platform: str, image: str = "openroad/orfs:latest") -> Dict:
    supported = sorted(PINNED_GITHUB_SOURCES)
    if platform not in PINNED_GITHUB_SOURCES:
        raise ValueError(f"Unsupported platform '{platform}'. Supported: {supported}")

    cache_dir = stdcell_cache_dir(workspace, platform)
    os.makedirs(cache_dir, exist_ok=True)
    _clear_cached_sim_models(cache_dir)

    source_details: Dict[str, Dict[str, List[str]]] = {}
    pinned_result = {"added": [], "failed": [], "attempted_urls": []}
    try:
        if platform == "asap7":
            pinned_result = _populate_asap7_pinned(cache_dir)
        elif platform == "sky130hd":
            pinned_result = _populate_sky130_pinned(cache_dir)
    except Exception as exc:
        pinned_result = {"added": [], "failed": [str(exc)], "attempted_urls": []}
    source_details["pinned_source"] = pinned_result

    all_cached = []
    for name in sorted(os.listdir(cache_dir)):
        if name.endswith(".v"):
            all_cached.append(os.path.join(cache_dir, name))

    if not all_cached:
        raise FileNotFoundError(f"Bootstrap completed but found no .v files for platform '{platform}'")

    manifest_files = []
    for fpath in all_cached:
        manifest_files.append(
            {
                "name": os.path.basename(fpath),
                "sha256": _sha256(fpath),
            }
        )

    manifest = {
        "platform": platform,
        "source_image": image,
        "source_policy": "pinned_only",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "mirror_urls_attempted": [],
        "mirror_files_added": [],
        "mirror_files_missing": [],
        "sources": source_details,
        "files": manifest_files,
    }

    with open(stdcell_manifest_path(workspace, platform), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    return {
        "platform": platform,
        "cache_dir": cache_dir,
        "file_count": len(all_cached),
        "manifest": stdcell_manifest_path(workspace, platform),
    }
