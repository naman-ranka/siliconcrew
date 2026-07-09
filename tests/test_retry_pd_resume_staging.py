"""F9b regression: a retry_pd resume must stage the prior-stage checkpoint
into the exact ORFS results path the resumed stage consumes.

Background (F9b, explore-mcp): a cloud `retry_pd` resume-from-CTS died with
``[ERROR ORD-0007] .../base/3_place.odb does not exist`` — the place checkpoint
was never materialized where ``do-cts`` reads it. Two contracts must hold, and
this test locks both without Docker/ORFS by driving ``_retry_pd_worker`` with a
recording fake OrfsRunner:

1. The checkpoint is physically present in the run dir at
   ``orfs_results/<platform>/<top>/base/3_place.odb`` BEFORE ORFS runs. This is
   exactly what the self-host bind mount exposes and what the cloud job's
   entrypoint stage-in copies into ``flow/results`` (deploy/orfs_job/
   entrypoint.sh). If the worker stops staging it, CTS aborts.
2. The ORFS volume map still resolves ``orfs_results`` → the container results
   path, so the cloud entrypoint stage-in has the mapping it needs to copy the
   staged tree to where ``do-cts`` reads it.

It also guards the honest-state half: a failed resume must not report a
netlist artifact that isn't physically on disk.
"""
import os

from src.orfs_client import OrfsResult
from src.platform_engines.orfs_runner import CloudJobOrfsRunner, set_orfs_runner
from src.tools import synthesis_manager as sm

PLATFORM = "sky130hd"
TOP = "seq_detector"
CKPT_REL = os.path.join("orfs_results", PLATFORM, TOP, "base")


class _RecordingRunner:
    """Captures the OrfsRequest and whether the place checkpoint is staged at
    the moment ORFS is invoked, then returns a benign non-success (the staging
    contract holds independent of the ORFS outcome, and we avoid fabricating a
    full clean signoff)."""

    backend = "cloud_job"

    def __init__(self):
        self.request = None
        self.checkpoint_present_at_run = None

    def run(self, request):
        self.request = request
        ckpt = os.path.join(request.run_dir, CKPT_REL, "3_place.odb")
        self.checkpoint_present_at_run = os.path.isfile(ckpt)
        return OrfsResult(
            success=False,
            stdout="",
            stderr="fake runner: ORFS not executed",
            command=request.command,
            exit_code=1,
            backend=self.backend,
        )


def _seed_parent_run(workspace: str) -> str:
    parent_dir = os.path.join(workspace, "synth_runs", "synth_0001")
    ckpt_dir = os.path.join(parent_dir, CKPT_REL)
    os.makedirs(ckpt_dir, exist_ok=True)
    # Place checkpoint + its SDC are the cts prerequisites (PD_PREREQ_FILES).
    with open(os.path.join(ckpt_dir, "3_place.odb"), "w", encoding="utf-8") as f:
        f.write("ODB")
    with open(os.path.join(ckpt_dir, "3_place.sdc"), "w", encoding="utf-8") as f:
        f.write("# sdc")
    inputs = os.path.join(parent_dir, "inputs")
    os.makedirs(inputs, exist_ok=True)
    with open(os.path.join(inputs, f"{TOP}.v"), "w", encoding="utf-8") as f:
        f.write(f"module {TOP}; endmodule\n")
    import json
    with open(os.path.join(parent_dir, "run_meta.json"), "w", encoding="utf-8") as f:
        json.dump({
            "run_id": "synth_0001", "status": "completed",
            "platform": PLATFORM, "top_module": TOP,
            "auto_checks": {"constraints": "pass"},
        }, f)
    return parent_dir


def _retry_args() -> dict:
    return {
        "run_id": "synth_0002",
        "source_run_id": "synth_0001",
        "start_stage": "cts",
        "max_stage": "cts",
        "orfs_overrides": {},
        "platform": PLATFORM,
        "top_module": TOP,
        "utilization": 5,
        "aspect_ratio": 1.0,
        "core_margin": 2.0,
        "timeout": 60,
    }


def test_retry_resume_stages_place_checkpoint_before_orfs(tmp_path):
    workspace = str(tmp_path)
    _seed_parent_run(workspace)
    child_dir = os.path.join(workspace, "synth_runs", "synth_0002")
    os.makedirs(child_dir, exist_ok=True)

    fake = _RecordingRunner()
    set_orfs_runner(fake)
    try:
        run_meta = sm._retry_pd_worker(workspace, child_dir, _retry_args())
    finally:
        set_orfs_runner(None)

    # (1) The place checkpoint was physically present at the exact nested path
    # ORFS reads BEFORE the run — the anti-regression for ORD-0007.
    assert fake.checkpoint_present_at_run is True
    landed = os.path.join(child_dir, CKPT_REL, "3_place.odb")
    assert os.path.isfile(landed)

    # (2) The volume map the cloud job would receive resolves orfs_results to
    # the container results path, so the entrypoint stage-in has its target.
    vol_map = CloudJobOrfsRunner._volume_map(fake.request)
    assert "orfs_results::/OpenROAD-flow-scripts/flow/results" in vol_map

    # run_meta advertises the staged prerequisite, and it physically exists.
    prereqs = run_meta.get("retry_prerequisites") or {}
    assert "3_place.odb" in prereqs
    assert os.path.isfile(prereqs["3_place.odb"])


def test_failed_retry_does_not_report_phantom_netlist(tmp_path):
    """Honest state: a resume that did not run ORFS must not claim a netlist
    artifact that isn't on disk."""
    workspace = str(tmp_path)
    _seed_parent_run(workspace)
    child_dir = os.path.join(workspace, "synth_runs", "synth_0002")
    os.makedirs(child_dir, exist_ok=True)

    set_orfs_runner(_RecordingRunner())
    try:
        run_meta = sm._retry_pd_worker(workspace, child_dir, _retry_args())
    finally:
        set_orfs_runner(None)

    assert run_meta["status"] == "failed"
    netlist = run_meta.get("netlist_path")
    assert netlist is None or os.path.isfile(netlist)
