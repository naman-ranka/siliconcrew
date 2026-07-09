"""F9 regression — hosted ORFS config disables the LEC (logical-equivalence)
check that SIGILLs on the Cloud Run CPU pool.

On hosted, the OpenROAD LEC child step exec'd from cts.tcl dies with "illegal
instruction" (the deployed CPU lacks ISA extensions the shipped build uses),
blocking every hosted run from reaching routing/GDS
(plans/overnight-20260706/reports/explore-mcp.md F1). The synth flow must write
`export LEC_CHECK = 0` into config.mk on hosted so the flow finishes. Self-host
runs on the user's own CPU and must KEEP the real equivalence check (no line).
"""
import os

from src.platform_engines.settings import reset_settings_cache
from src.tools.synthesis_manager import _write_orfs_config


def _write(tmp_path, overrides=None):
    return _write_orfs_config(
        run_dir=str(tmp_path),
        top_module="seq_detector_0011",
        platform="sky130hd",
        input_files=["/x/rtl.v"],
        utilization=15,
        aspect_ratio=1.0,
        core_margin=2.0,
        orfs_overrides=overrides,
    )


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def test_hosted_config_disables_lec(tmp_path, monkeypatch):
    monkeypatch.setenv("SILICONCREW_HOSTED", "1")
    reset_settings_cache()
    try:
        cfg = _read(_write(tmp_path))
        assert "export LEC_CHECK = 0" in cfg
    finally:
        reset_settings_cache()


def test_self_host_config_keeps_lec(tmp_path, monkeypatch):
    monkeypatch.delenv("SILICONCREW_HOSTED", raising=False)
    reset_settings_cache()
    try:
        cfg = _read(_write(tmp_path))
        assert "LEC_CHECK" not in cfg
    finally:
        reset_settings_cache()


def test_hosted_lec_disable_wins_over_override(tmp_path, monkeypatch):
    """A retry override cannot re-enable the crashing LEC step on hosted: the
    disable is appended LAST, so ORFS reads the final (0) assignment."""
    monkeypatch.setenv("SILICONCREW_HOSTED", "1")
    reset_settings_cache()
    try:
        cfg = _read(_write(tmp_path, overrides={"LEC_CHECK": 1}))
        # Both lines may be present; the disable must come last (ORFS honors the
        # last `export` of a variable).
        assert cfg.rindex("export LEC_CHECK = 0") > cfg.rindex("export LEC_CHECK = 1")
    finally:
        reset_settings_cache()
