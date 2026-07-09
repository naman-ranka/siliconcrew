"""Provenance + determinism stamp (Phase 2, slice 7).

Every run is meant to be a pure function of (manifest subset + pinned toolchain)
in an isolated dir (see data-model.md). To make a run *reproducible* and
*auditable*, we stamp the toolchain identity onto it:

  * ``repo_commit``   — the SiliconCrew commit that produced the run
  * ``orfs_image_digest`` — the pinned ORFS image (``@sha256:...``), not a tag
  * ``pdk``           — the platform / PDK (e.g. sky130hd)
  * ``iverilog_version`` — the simulator build
  * ``num_cores``     — the pinned P&R parallelism (the only real nondeterminism
                        source; see config.mk pinning in synthesis_manager)

Collection is best-effort and never raises: a missing git binary or unpinned
image degrades to ``None``/``"unknown"`` rather than failing a synth run.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import asdict, dataclass
from functools import lru_cache
from typing import Optional


@dataclass(frozen=True)
class Provenance:
    repo_commit: str
    orfs_image_digest: Optional[str] = None
    pdk: Optional[str] = None
    iverilog_version: Optional[str] = None
    num_cores: Optional[int] = None

    def as_dict(self) -> dict:
        return asdict(self)


@lru_cache(maxsize=1)
def repo_commit() -> str:
    """The current repo commit — env override first, then git, then 'unknown'."""
    env = os.environ.get("SILICONCREW_COMMIT") or os.environ.get("GIT_COMMIT")
    if env:
        return env.strip()
    try:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


@lru_cache(maxsize=1)
def iverilog_version() -> Optional[str]:
    try:
        out = subprocess.run(["iverilog", "-V"], capture_output=True, text=True, timeout=5)
        first = (out.stdout or out.stderr or "").splitlines()
        if first:
            m = re.search(r"version\s+(\S+)", first[0])
            return m.group(1) if m else first[0].strip()
    except Exception:
        pass
    return None


def orfs_image_digest(image: Optional[str] = None) -> Optional[str]:
    """Return the pinned image digest if the configured image is digest-pinned."""
    image = image or os.environ.get("ORFS_IMAGE", "")
    explicit = os.environ.get("ORFS_IMAGE_DIGEST")
    if explicit:
        return explicit.strip()
    if image and "@sha256:" in image:
        return image.split("@", 1)[1]
    return None


def collect_provenance(
    pdk: Optional[str] = None,
    num_cores: Optional[int] = None,
    orfs_image: Optional[str] = None,
) -> Provenance:
    """Gather the full provenance stamp for a run (best-effort, never raises)."""
    return Provenance(
        repo_commit=repo_commit(),
        orfs_image_digest=orfs_image_digest(orfs_image),
        pdk=pdk,
        iverilog_version=iverilog_version(),
        num_cores=num_cores,
    )
