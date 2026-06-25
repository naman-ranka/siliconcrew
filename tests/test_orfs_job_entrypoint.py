"""Regression test for the ORFS Cloud Run Job entrypoint's stage-IN step.

Bug it locks down: the cloud job only staged OUT (copied ORFS outputs back) and
never staged IN, so a checkpoint-based ``retry_pd`` run started with an empty
``./results`` and OpenROAD aborted ("ORD-0007 … 3_place.odb does not exist").
Locally the Docker volume bind hides this; in the cloud job there is no bind, so
the entrypoint must copy the staged checkpoint tree into the ORFS container path
before the run — the mirror of the existing stage-out.

We extract the actual stage-in block from ``entrypoint.sh`` and run it, so the
test exercises the real shell rather than a copy that could drift.
"""
import os
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ENTRYPOINT = Path(__file__).resolve().parents[1] / "deploy" / "orfs_job" / "entrypoint.sh"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _extract_stage_in_block() -> str:
    """Pull the first ORFS_VOLUME_MAP loop (stage-in) out of entrypoint.sh.

    Stage-in is inserted before the run and before stage-out, so the first
    ``if [ -n "${ORFS_VOLUME_MAP...`` block is it. We grab to its matching ``fi``.
    """
    lines = ENTRYPOINT.read_text().splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.strip().startswith('if [ -n "${ORFS_VOLUME_MAP'))
    end = next(i for i in range(start + 1, len(lines)) if lines[i].rstrip() == "fi")
    block = "\n".join(lines[start : end + 1])
    # Sanity: this must be the stage-IN block (copies run-dir -> container).
    assert 'cp -r "$RUN_DIR/$rel/." "$container/"' in block, "extracted the wrong block"
    return block


def _run_block(tmp_path: Path, volume_map: str) -> None:
    run_dir = tmp_path / "run"
    block = _extract_stage_in_block()
    script = textwrap.dedent(
        f"""
        set -euo pipefail
        RUN_DIR="{run_dir}"
        ORFS_VOLUME_MAP="{volume_map}"
        {block}
        """
    )
    subprocess.run(["bash", "-c", script], check=True)


def test_stage_in_copies_checkpoint_into_container_path(tmp_path):
    """A staged checkpoint under RUN_DIR/<rel> lands at the container path."""
    container = tmp_path / "flow" / "results"
    rel_root = tmp_path / "run" / "orfs_results"
    ckpt = rel_root / "sky130hd" / "saturating_add" / "base" / "3_place.odb"
    ckpt.parent.mkdir(parents=True)
    ckpt.write_text("ODB")

    _run_block(tmp_path, f"orfs_results::{container}")

    landed = container / "sky130hd" / "saturating_add" / "base" / "3_place.odb"
    assert landed.is_file()
    assert landed.read_text() == "ODB"  # nested structure + content preserved


def test_stage_in_noop_when_nothing_staged(tmp_path):
    """Fresh full runs (no staged inputs) are untouched — the -d guard skips."""
    container = tmp_path / "flow" / "results"
    # RUN_DIR/orfs_results does not exist.
    _run_block(tmp_path, f"orfs_results::{container}")
    assert not container.exists()  # nothing created, no error


def test_entrypoint_stages_in_before_running_orfs():
    """Structural guard: stage-in must come before the ORFS run, not after."""
    text = ENTRYPOINT.read_text()
    stage_in = text.index('cp -r "$RUN_DIR/$rel/." "$container/"')
    run_at = text.index('cd "$FLOW_DIR"')
    assert stage_in < run_at, "stage-in must populate ./results BEFORE ORFS runs"
