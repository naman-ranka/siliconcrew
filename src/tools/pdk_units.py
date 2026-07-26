"""Per-platform unit metadata for ORFS artifacts (issue #63).

The API contract is canonical nanoseconds/milliwatts everywhere users and
agents touch: ``clock_period_ns`` (tool args, manifest ``clockPeriodNs``,
run_meta) is ALWAYS ns, and summary-metric fields named ``*_ns`` / ``*_mw``
mean exactly that on every platform.

ORFS, however, expresses SDC clock periods and STA report times in the PDK
liberty time unit, which differs per platform: asap7 liberty is 1 ps (its
ORFS design SDCs carry periods like ``310``, and its configs use
``ABC_CLOCK_PERIOD_IN_PS``), while sky130hd / nangate45 / ihp-sg13g2 / gf180
are 1 ns. Power (``report_power`` prints Watts) and area (yosys reports um^2)
were verified unit-consistent across sky130hd and asap7 real reports, so TIME
is the only per-platform axis this table carries.

Conversion happens in exactly two mirrored places, both driven by this table:

* write side — ``synthesis_manager._write_default_sdc`` converts canonical ns
  to the platform unit when the per-run ``constraints.sdc`` is generated (the
  single SDC generation point for every backend: local docker, cloud job,
  remote VM all ship the run dir as-is);
* read side — report time values are normalized back to ns at parse time,
  gated on the persisted ``sdc_time_unit`` run_meta marker so runs finalized
  under the old behavior are never silently reinterpreted.

Platforms not in the table default to ns (SiliconCrew does not maintain a
closed platform list; unknown strings pass through to ORFS unchanged).
"""
from typing import Optional

PLATFORM_TIME_UNITS = {
    "asap7": "ps",
    "sky130hd": "ns",
    "sky130hs": "ns",
    "nangate45": "ns",
    "ihp-sg13g2": "ns",
    "gf180": "ns",
}

DEFAULT_TIME_UNIT = "ns"

_NS_PER_UNIT = {"ns": 1.0, "ps": 1e-3}


def platform_time_unit(platform: Optional[str]) -> str:
    """The SDC/liberty time unit for an ORFS platform ("ns" or "ps")."""
    return PLATFORM_TIME_UNITS.get((platform or "").strip().lower(), DEFAULT_TIME_UNIT)


def ns_to_platform_time(period_ns: float, platform: Optional[str]) -> float:
    """Canonical ns -> the platform's SDC time unit (write side)."""
    return float(period_ns) / _NS_PER_UNIT[platform_time_unit(platform)]


def time_unit_to_ns(value: Optional[float], time_unit: Optional[str]) -> Optional[float]:
    """A report-time value expressed in ``time_unit`` -> ns (read side).

    None passes through; an unknown unit is left unscaled rather than guessed.
    """
    if value is None:
        return None
    return float(value) * _NS_PER_UNIT.get((time_unit or DEFAULT_TIME_UNIT).lower(), 1.0)
