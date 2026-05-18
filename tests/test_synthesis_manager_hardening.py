import os
from concurrent.futures import ThreadPoolExecutor

from src.tools import synthesis_manager as sm


def test_allocate_run_dir_holds_job_lock_while_reading_next_id(tmp_path, monkeypatch):
    observed = {"locked": False}
    original_next_run_id = sm._next_run_id

    def checked_next_run_id(workspace: str) -> str:
        observed["locked"] = sm._JOB_LOCK.locked()
        return original_next_run_id(workspace)

    monkeypatch.setattr(sm, "_next_run_id", checked_next_run_id)

    run_id, run_dir = sm._allocate_run_dir(str(tmp_path))

    assert observed["locked"] is True
    assert run_id == "synth_0001"
    assert run_dir.endswith("synth_0001")


def test_allocate_run_dir_returns_unique_dirs_under_concurrency(tmp_path):
    workspace = str(tmp_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: sm._allocate_run_dir(workspace)[0], range(2)))

    assert sorted(results) == ["synth_0001", "synth_0002"]


def test_route_retry_prerequisites_match_orfs_do_route_dependency(tmp_path):
    parent = tmp_path / "parent"
    base = parent / "orfs_results" / "sky130hd" / "demo_top" / "base"
    base.mkdir(parents=True)
    (base / "4_cts.odb").write_text("cts odb", encoding="utf-8")
    (base / "4_cts.sdc").write_text("cts sdc", encoding="utf-8")

    found = sm._validate_retry_prerequisites(str(parent), "route")

    assert set(found) == {"4_cts.odb", "4_cts.sdc"}
    assert os.path.basename(found["4_cts.odb"]) == "4_cts.odb"
