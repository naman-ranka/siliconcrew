"""ORFS make-target maps stay in lock-step with the pinned image (Fix A).

Root cause these guard: the openroad/orfs image renamed the synth do-target —
there is no ``do-synth``, only ``do-yosys-canonicalize`` + ``do-yosys``. The old
first-run chain led with ``do-synth`` and every hosted synth-only run died with
``make: *** No rule to make target 'do-synth'``. These tests assert every target
our maps emit is a real image target (KNOWN_IMAGE_TARGETS, derived from the
image — see the constant's docstring), so this class of drift fails in CI, not
in a hosted run.
"""
from src.tools import synthesis_manager as sm


def _targets_in(value: str):
    # A map value may pack multiple targets into one make invocation
    # (synth -> "do-yosys-canonicalize do-yosys").
    return value.split()


def test_pd_stage_targets_are_real_image_targets():
    for stage, value in sm.PD_STAGE_TARGETS.items():
        for target in _targets_in(value):
            assert target in sm.KNOWN_IMAGE_TARGETS, (stage, target)


def test_first_run_stage_targets_are_real_image_targets():
    for stage, value in sm.FIRST_RUN_STAGE_TARGETS.items():
        for target in _targets_in(value):
            assert target in sm.KNOWN_IMAGE_TARGETS, (stage, target)


def test_synth_do_target_is_the_renamed_yosys_pair():
    # Regression on the exact rename: the synth do-targets are the yosys steps,
    # and the phantom ``do-synth`` must never reappear in any map.
    assert sm.PD_STAGE_TARGETS["synth"] == "do-yosys-canonicalize do-yosys"
    assert "do-synth" not in sm.KNOWN_IMAGE_TARGETS
    all_values = list(sm.PD_STAGE_TARGETS.values()) + list(sm.FIRST_RUN_STAGE_TARGETS.values())
    assert not any("do-synth" in _targets_in(v) for v in all_values)


def test_first_run_target_is_never_absent_from_the_image():
    # The load-bearing regression: a synth-only first run must emit only targets
    # the image actually has. FAILS on pre-fix code, which returned ["do-synth"]
    # (absent from KNOWN_IMAGE_TARGETS).
    for stage in ["synth", "floorplan", "place", "cts", "grt", "route"]:
        for target in sm._first_run_targets(stage):
            for one in _targets_in(target):
                assert one in sm.KNOWN_IMAGE_TARGETS, (stage, one)


def test_known_image_targets_cover_every_stage_name():
    # Every ORFS stage (constraints is pre-ORFS) has a phony target of the same
    # name in the image — the invariant FIRST_RUN_STAGE_TARGETS relies on.
    for stage in sm.PD_STAGE_SEQUENCE:
        if stage == "constraints":
            continue
        assert stage in sm.KNOWN_IMAGE_TARGETS, stage
