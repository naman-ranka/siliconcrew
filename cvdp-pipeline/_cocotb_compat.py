#!/usr/bin/env python3
"""cocotb-version compatibility rewrites for CVDP harnesses.

Some CVDP harnesses are written against cocotb 1.x and fail to *load* under the cocotb-2.x in the
reference container (removed `BinaryValue.to_unsigned()`/`to_signed()`, the `cocotb.runner` →
`cocotb_tools.runner` move, stricter `Clock` period checks). `regrade_docker.py` applies these
rewrites ONLY as a fallback, when an unpatched run fails to load (ModuleNotFoundError/AttributeError);
a harness that already loads is never touched, so this cannot change a harness's semantics.

(Extracted from the now-deleted Windows replay shim; this is the only piece of it worth keeping.)
"""
from __future__ import annotations

import re
from pathlib import Path

_TO_UNSIGNED_PAT = re.compile(r"([A-Za-z_][A-Za-z0-9_\.\[\]]*)\.value\.to_unsigned\(\)")
_TO_SIGNED_PAT = re.compile(r"([A-Za-z_][A-Za-z0-9_\.\[\]]*)\.value\.to_signed\(\)")
_COCOTB_RUNNER_IMPORT_PAT = re.compile(
    r"^\s*from\s+cocotb\.runner\s+import\s+get_runner\s*$", re.MULTILINE
)
# cocotb 2.0 rejects an odd Clock `period` (checked in *sim steps*) unless `period_high` is given.
# Older harnesses use e.g. Clock(clk, 5, units="ns"). For odd integer periods, add period_high=N//2
# (a valid high/low split) so the clock is accepted; physical period is unchanged. Even periods untouched.
_CLOCK_NS_PAT = re.compile(
    r"Clock\(\s*([^,]+?)\s*,\s*([0-9]+)\s*,\s*units\s*=\s*(['\"])ns\3\s*\)"
)


def _clock_ns_to_ps(m: "re.Match[str]") -> str:
    sig, n, q = m.group(1), int(m.group(2)), m.group(3)
    if n % 2 == 1:
        return f"Clock({sig}, {n}, units={q}ns{q}, period_high={n // 2})"
    return m.group(0)


def apply_cocotb_compat_patches(harness_dir: Path) -> int:
    """Rewrite copied cocotb tests so they run on newer cocotb (2.x) where BinaryValue
    helpers like `.to_unsigned()` were removed. Applied only to the isolated copy."""
    changed = 0
    for py in harness_dir.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        updated = _TO_UNSIGNED_PAT.sub(r"int(\1.value)", text)
        updated = _TO_SIGNED_PAT.sub(r"int(\1.value.signed_integer)", updated)
        updated = _COCOTB_RUNNER_IMPORT_PAT.sub(
            (
                "try:\n"
                "    from cocotb.runner import get_runner\n"
                "except Exception:\n"
                "    from cocotb_tools.runner import get_runner"
            ),
            updated,
        )
        updated = _CLOCK_NS_PAT.sub(_clock_ns_to_ps, updated)
        if updated != text:
            py.write_text(updated, encoding="utf-8", newline="\n")
            changed += 1
    return changed
