"""Determinism pins + provenance stamping (Phase 2, slice 7)."""
import os

from src.platform_engines.provenance import (
    Provenance,
    collect_provenance,
    orfs_image_digest,
)


def test_provenance_collects_commit_and_pins(monkeypatch):
    monkeypatch.setenv("SILICONCREW_COMMIT", "deadbeefcafe")
    monkeypatch.setenv("ORFS_IMAGE_DIGEST", "sha256:1234")
    import src.platform_engines.provenance as prov

    prov.repo_commit.cache_clear()
    p = collect_provenance(pdk="sky130hd", num_cores=4)
    assert isinstance(p, Provenance)
    assert p.repo_commit == "deadbeefcafe"
    assert p.orfs_image_digest == "sha256:1234"
    assert p.pdk == "sky130hd"
    assert p.num_cores == 4
    # Round-trips to a JSON-friendly dict (stamped into run_meta).
    d = p.as_dict()
    assert d["repo_commit"] == "deadbeefcafe" and d["num_cores"] == 4


def test_orfs_digest_extracted_from_pinned_image(monkeypatch):
    monkeypatch.delenv("ORFS_IMAGE_DIGEST", raising=False)
    assert orfs_image_digest("repo/orfs@sha256:abc123") == "sha256:abc123"
    # A tag-only image is NOT a digest pin.
    assert orfs_image_digest("repo/orfs:latest") is None


def test_provenance_never_raises_without_git(monkeypatch):
    monkeypatch.delenv("SILICONCREW_COMMIT", raising=False)
    monkeypatch.delenv("GIT_COMMIT", raising=False)
    import src.platform_engines.provenance as prov

    prov.repo_commit.cache_clear()
    # Force the git lookup to fail.
    monkeypatch.setattr(prov.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    p = collect_provenance()
    assert p.repo_commit == "unknown"


def test_config_mk_pins_num_cores(tmp_path, monkeypatch):
    """The generated config.mk must pin NUM_CORES for P&R determinism."""
    monkeypatch.setenv("ORFS_NUM_CORES", "1")
    from src.platform_engines.settings import reset_settings_cache

    reset_settings_cache()
    import src.tools.synthesis_manager as sm

    run_dir = tmp_path / "synth_0001"
    (run_dir / "inputs").mkdir(parents=True)
    inp = run_dir / "inputs" / "dut.v"
    inp.write_text("module dut; endmodule\n")

    cfg = sm._write_orfs_config(
        run_dir=str(run_dir), top_module="dut", platform="sky130hd",
        input_files=[str(inp)], utilization=5, aspect_ratio=1.0, core_margin=2.0,
    )
    text = open(cfg).read()
    assert "export NUM_CORES = 1" in text
    reset_settings_cache()


def test_num_cores_pin_defaults(monkeypatch):
    monkeypatch.delenv("ORFS_NUM_CORES", raising=False)
    from src.platform_engines.settings import reset_settings_cache
    import src.tools.synthesis_manager as sm

    reset_settings_cache()
    assert sm._pinned_num_cores() == 4  # sensible reproducible default
    reset_settings_cache()
