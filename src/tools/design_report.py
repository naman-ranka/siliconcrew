"""
Design Report Generator - Creates comprehensive reports comparing spec vs actual results.
"""

import os
import json
import math
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from src.tools.spec_manager import load_yaml_file, DesignSpec
from src.tools.synthesis_manager import get_run_dir, get_synthesis_metrics
from src.tools.sim_manager import list_sim_runs


# =============================================================================
# METRICS PERSISTENCE
# =============================================================================
# The agent can hand-save metrics it found by other means (e.g. search_logs_tool).
# Those saved values rank strictly BELOW the structured parse of the run's own
# reports: a hand-typed number never outranks a measured one (invariant #4).

METRICS_FILENAME = "design_metrics.json"
RUN_REPORT_FILENAME = "design_report.md"

# Spec files the platform (or a user) may write. The structured summary table
# needs a YAML ``*_spec.yaml`` (write_spec's output), but a session can carry a
# markdown/text spec (e.g. ``spec.md`` from the Spec tab). Detecting these keeps
# the report honest instead of claiming "no spec" when one plainly exists.
_SPEC_LIKE_EXACT_NAMES = {"spec.md", "spec.yaml", "spec.yml", "spec.txt"}


def _is_spec_like(name: str) -> bool:
    low = name.lower()
    return (
        low.endswith("_spec.yaml")
        or low.endswith("_spec.yml")
        or low.endswith("_spec.md")
        or low in _SPEC_LIKE_EXACT_NAMES
    )


def _spec_like_files(dir_path: str) -> list:
    """Spec-like filenames present in a directory (sorted, may be empty)."""
    if not dir_path or not os.path.isdir(dir_path):
        return []
    return sorted(f for f in os.listdir(dir_path) if _is_spec_like(f))


def _files_by_role(workspace_path: str) -> Dict[str, list]:
    """Workspace files grouped by their MANIFEST role (invariant 1).

    Replaces a root-only ``os.listdir`` + suffix guess that filed every nested
    file nowhere and every ``*_props.sv`` under "RTL". Paths are
    workspace-relative, so a nested file reads as ``rtl/alu.v``.
    """
    try:
        from src.tools import manifest as manifest_mod

        manifest = manifest_mod.read_manifest(workspace_path)
    except Exception:
        return {}
    grouped: Dict[str, list] = {}
    for f in manifest.files:
        grouped.setdefault(f.role, []).append(f.path)
    return grouped


def _latest_lint_event(workspace_path: str) -> Optional[Dict[str, Any]]:
    """The most recent lint result from the session event log.

    Every actor's lint lands in ``attempt_events.jsonl`` (invariant 3), so that
    log — not a guess — is the evidence for the report's lint cell. Appended in
    order, so the last match is the latest.
    """
    try:
        from src.api.tool_catalog import tools_with_attempt_parser
        from src.utils.attempt_logger import EVENTS_FILE, _read_events, attempt_lint

        # Which tool produces a lint verdict is the registry's answer, not a
        # name spelled here: a tool declares ``attempt_parser=attempt_lint`` in
        # its @policy, which is the same declaration the attempt log reads.
        lint_tools = tools_with_attempt_parser(attempt_lint)
        records = _read_events(os.path.join(workspace_path, EVENTS_FILE))
    except Exception:
        return None
    for rec in reversed(records):
        if rec.get("event_type") == "tool_result" and rec.get("tool") in lint_tools:
            return rec
    return None


def _lint_status_cell(workspace_path: str) -> str:
    """The Syntax (Lint) verification-table cell.

    This used to print "✅ Pass" whenever any RTL file existed — its own comment
    said "assume passed if RTL exists", so a design that had never been linted,
    or had failed lint, still read as passing. Now it reports the last real lint
    and WHEN it ran: the RTL may have changed since, and a timestamp lets the
    reader judge that instead of being told a stale result is current
    (invariant 4). No lint in the log → "Not run".
    """
    rec = _latest_lint_event(workspace_path)
    if not rec:
        return "| Syntax (Lint) | ⏳ Not run |"
    passed = str(rec.get("status", "")).lower() in ("success", "ok", "passed")
    icon = "✅ Pass" if passed else "❌ Fail"
    when = rec.get("ts")
    return f"| Syntax (Lint) | {icon}{f' (last run {when})' if when else ''} |"


def _simulation_status_cell(workspace_path: str) -> str:
    """The Simulation verification-table cell.

    Reads the authoritative isolated sim runs (``sim_runs/<id>/run_meta.json``)
    and reports the LATEST run's verdict, noting the count when there are
    several. Falls back to the legacy workspace-root ``.out`` / ``simulation.log``
    scan for sessions that predate isolated runs. "Not Run" only when nothing
    actually ran — so a session with passing sims never reads as un-run.
    """
    try:
        runs = list_sim_runs(workspace_path)  # newest-first
    except Exception:
        runs = []
    if runs:
        latest = runs[0]
        icon = "✅ Pass" if latest.get("status") == "passed" else "❌ Fail"
        detail = latest.get("id") or ""
        n = len(runs)
        if n > 1:
            detail = f"{detail}, latest of {n} runs" if detail else f"latest of {n} runs"
        suffix = f" ({detail})" if detail else ""
        return f"| Simulation | {icon}{suffix} |"

    # Legacy fallback: scan workspace-root sim outputs (pre-isolated-runs).
    # Fail-dominant: a log line like "0 passed, 3 failed" contains both words,
    # and a false Pass is the dishonest direction (X2A-2) — so any 'fail'
    # verdict sticks over 'pass', within and across files.
    sim_passed = None
    for f in (os.listdir(workspace_path) if os.path.exists(workspace_path) else []):
        if f.endswith('.out') or f == 'simulation.log':
            try:
                with open(os.path.join(workspace_path, f), 'r') as log_file:
                    content = log_file.read().lower()
                    if 'fail' in content:
                        sim_passed = False
                    elif 'pass' in content and sim_passed is None:
                        sim_passed = True
            except Exception:
                pass
    if sim_passed is True:
        return "| Simulation | ✅ Pass |"
    if sim_passed is False:
        return "| Simulation | ❌ Fail |"
    return "| Simulation | ⏳ Not Run |"


def _resolve_report_scope(workspace_path: str, run_id: str = None) -> Tuple[str, Optional[str]]:
    if run_id:
        resolved_run_dir = get_run_dir(workspace_path, run_id)
        if resolved_run_dir:
            return resolved_run_dir, os.path.basename(resolved_run_dir)
        return workspace_path, None

    latest_marker = os.path.join(workspace_path, "synth_runs", "LATEST")
    if os.path.exists(latest_marker):
        resolved_run_dir = get_run_dir(workspace_path, None)
        if resolved_run_dir:
            return resolved_run_dir, os.path.basename(resolved_run_dir)
    return workspace_path, None


def _resolve_spec_for_report(workspace_path: str, report_dir: str, spec_filename: str = None) -> Optional[DesignSpec]:
    candidate_paths = []
    if spec_filename:
        candidate_paths.append(os.path.join(report_dir, spec_filename))
        if report_dir != workspace_path:
            candidate_paths.append(os.path.join(workspace_path, spec_filename))
    else:
        if os.path.exists(report_dir):
            report_specs = [f for f in os.listdir(report_dir) if f.endswith("_spec.yaml")]
            report_specs.sort(key=lambda x: os.path.getmtime(os.path.join(report_dir, x)), reverse=True)
            candidate_paths.extend([os.path.join(report_dir, f) for f in report_specs])
        if report_dir != workspace_path and os.path.exists(workspace_path):
            workspace_specs = [f for f in os.listdir(workspace_path) if f.endswith("_spec.yaml")]
            workspace_specs.sort(key=lambda x: os.path.getmtime(os.path.join(workspace_path, x)), reverse=True)
            candidate_paths.extend([os.path.join(workspace_path, f) for f in workspace_specs])

    seen = set()
    for path in candidate_paths:
        if path in seen:
            continue
        seen.add(path)
        if os.path.exists(path):
            try:
                return load_yaml_file(path)
            except:
                pass
    return None


def _load_run_meta_for_report(workspace_path: str, run_id: str = None) -> Dict[str, Any]:
    report_dir, resolved_run_id = _resolve_report_scope(workspace_path, run_id)
    if not resolved_run_id:
        return {}
    meta_path = os.path.join(report_dir, "run_meta.json")
    if not os.path.exists(meta_path):
        return {}
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def _resolve_run_clock_fields(run_meta: Dict[str, Any], spec: Optional[DesignSpec]) -> Tuple[Optional[float], Optional[float], Optional[str]]:
    requested_clock = run_meta.get("requested_clock_period_ns")
    effective_clock = run_meta.get("effective_clock_period_ns")
    if effective_clock is None:
        effective_clock = run_meta.get("clock_period_ns")

    if effective_clock is not None:
        source = run_meta.get("clock_source") or "run metadata"
        return requested_clock, effective_clock, source

    if spec:
        return requested_clock, spec.clock_period_ns, "specification"

    return requested_clock, None, None


def save_metrics(workspace_path: str, metrics: Dict[str, Any], run_id: str = None) -> str:
    """
    Save PPA metrics to a JSON file in the workspace.
    Called by the agent when it finds metrics through any means.
    
    Args:
        workspace_path: Path to workspace
        metrics: Dict with keys like area_um2, wns_ns, power_uw, cell_count
        
    Returns:
        Path to saved file
    """
    target_dir, _ = _resolve_report_scope(workspace_path, run_id)
    metrics_path = os.path.join(target_dir, METRICS_FILENAME)
    
    # Merge with existing metrics (don't overwrite if new value is None)
    existing = {}
    if os.path.exists(metrics_path):
        try:
            with open(metrics_path, 'r') as f:
                existing = json.load(f)
        except:
            pass
    
    # Update with new metrics (only non-None values)
    for key, value in metrics.items():
        if value is not None:
            existing[key] = value
    
    existing["updated_at"] = datetime.now().isoformat()
    
    with open(metrics_path, 'w') as f:
        json.dump(existing, f, indent=2)
    
    return metrics_path


def _metric_values_agree(saved: Any, parsed: Any) -> bool:
    """True when a saved value and a parsed value are the same measurement.

    JSON round-trips and hand-typed decimals introduce representation noise, so
    numbers compare with a tolerance; everything else compares exactly. Booleans
    are compared as booleans (in Python ``True == 1.0``).
    """
    if isinstance(saved, bool) or isinstance(parsed, bool):
        return saved is parsed
    if isinstance(saved, (int, float)) and isinstance(parsed, (int, float)):
        return math.isclose(saved, parsed, rel_tol=1e-9, abs_tol=1e-12)
    return saved == parsed


def load_metrics(workspace_path: str, run_id: str = None) -> Dict[str, Any]:
    """
    Load metrics for a run. The MEASURED values win.

    Ranking (invariant #4, honest state):
    1. get_synthesis_metrics for the resolved run — the ONE structured parser
       every other surface uses. Authoritative.
    2. design_metrics.json (hand-saved by the agent via save_metrics_tool).
       Read for legacy runs and for gap-filling ONLY; it can never override a
       parsed value.

    When both sources carry a value for the same field and they disagree, the
    parsed value is used and the conflict is reported under the
    ``saved_metric_conflicts`` key (a list of
    ``{"field", "saved", "parsed"}`` dicts) so the report can say so out loud
    instead of silently dropping one of the two numbers.

    A third tier used to parse *sta.log / *timing.rpt from the workspace root
    with its own crude regexes (src/tools/get_ppa.py). It never read
    6_finish.rpt, so it reported different numbers than every other surface;
    it was deleted in Wave C rather than aligned.

    Returns:
        Dict with metrics or empty dict
    """
    # Tier 2 (lowest): saved metrics file. Loaded first only so the parse can be
    # laid OVER it — every non-None parsed value replaces what is here.
    metrics = {}
    target_dir, resolved_run_id = _resolve_report_scope(workspace_path, run_id)
    metrics_path = os.path.join(target_dir, METRICS_FILENAME)
    if os.path.exists(metrics_path):
        try:
            with open(metrics_path, 'r') as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                metrics = loaded
        except:
            pass

    # Tier 1 (authoritative): structured parsing from the synthesis run.
    conflicts = []
    if resolved_run_id:
        try:
            parsed = get_synthesis_metrics(workspace_path, resolved_run_id)
            parsed_metrics = parsed.get("metrics", {}) if parsed.get("status") == "ok" else {}
            for key in [
                "area_um2", "cell_count", "wns_ns", "tns_ns", "power_uw",
                # The honest timing set (Wave C): the real margin, the achieved
                # frequency ORFS itself reported, and the corner it ran at.
                "worst_slack_ns", "clock_period_min_ns", "fmax_mhz",
                "timing_met", "timing_corner",
                # The disclosure travels with the numbers: without it the report
                # cannot say WHY a run has no verdict.
                "timing_note",
            ]:
                parsed_value = parsed_metrics.get(key)
                if parsed_value is None:
                    # Nothing measured for this field — a saved value may fill
                    # the gap, and stays exactly where it is.
                    continue
                saved_value = metrics.get(key)
                if saved_value is not None and not _metric_values_agree(saved_value, parsed_value):
                    conflicts.append(
                        {"field": key, "saved": saved_value, "parsed": parsed_value}
                    )
                metrics[key] = parsed_value
        except:
            pass

    if conflicts:
        metrics["saved_metric_conflicts"] = conflicts

    return metrics


def generate_design_report(workspace_path: str, spec_filename: str = None, run_id: str = None) -> str:
    """
    Generate a comprehensive design report comparing spec vs actual results.
    
    Args:
        workspace_path: Path to the workspace directory
        spec_filename: Optional specific spec file to use
        
    Returns:
        Markdown formatted report string
    """
    report_lines = []
    report_dir, resolved_run_id = _resolve_report_scope(workspace_path, run_id)
    run_meta = _load_run_meta_for_report(workspace_path, resolved_run_id)
    
    # Header
    report_lines.append("# Design Report")
    report_lines.append(f"\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    report_lines.append(f"\n*Workspace: `{os.path.basename(workspace_path)}`*\n")
    if resolved_run_id:
        report_lines.append(f"*Synthesis Run: `{resolved_run_id}`*\n")
    
    # Find spec file
    spec = _resolve_spec_for_report(workspace_path, report_dir, spec_filename)
    
    # Specification Summary
    report_lines.append("---\n## 📋 Specification Summary\n")
    
    if spec:
        report_lines.append(f"| Property | Value |")
        report_lines.append(f"|----------|-------|")
        report_lines.append(f"| **Module Name** | `{spec.module_name}` |")
        report_lines.append(f"| **Description** | {spec.description[:80]}{'...' if len(spec.description) > 80 else ''} |")
        report_lines.append(f"| **Tech Node** | {spec.tech_node} |")
        report_lines.append(f"| **Target Clock** | {spec.clock_period_ns} ns |")
        report_lines.append(f"| **Ports** | {len(spec.ports)} |")
        
        if spec.parameters:
            params_str = ", ".join([f"{k}={v}" for k, v in spec.parameters.items()])
            report_lines.append(f"| **Parameters** | {params_str} |")
        
        report_lines.append("\n### Port List\n")
        report_lines.append("| Name | Direction | Width | Description |")
        report_lines.append("|------|-----------|-------|-------------|")
        for port in spec.ports:
            width = port.width if port.width else 1
            report_lines.append(f"| `{port.name}` | {port.direction} | {width} | {port.description or '-'} |")
    else:
        # No structured YAML spec parsed — but a markdown/text spec (e.g.
        # spec.md) may still be present. Report it honestly rather than
        # claiming none exists.
        present = _spec_like_files(report_dir)
        if report_dir != workspace_path:
            present += [f for f in _spec_like_files(workspace_path) if f not in present]
        if present:
            report_lines.append(
                f"*Specification file present: {', '.join(present)} — open the Spec tab to view. "
                "(A structured summary table requires a YAML `*_spec.yaml` spec.)*\n"
            )
        else:
            report_lines.append("*No specification file found.*\n")
    
    # Generated Files
    report_lines.append("\n---\n## 📁 Generated Files\n")
    
    if os.path.exists(workspace_path):
        files = os.listdir(workspace_path)

        # The manifest is the single source of truth for what a file IS
        # (invariant 1). The old root-only listdir + suffix guess put a nested
        # RTL file nowhere and a formal harness under "RTL".
        by_role = _files_by_role(workspace_path)
        rtl_files = by_role.get("rtl", [])
        tb_files = by_role.get("tb", [])
        formal_files = by_role.get("formal", [])
        sdc_files = by_role.get("sdc", [])
        include_files = by_role.get("include", [])
        spec_files = [f for f in files if _is_spec_like(f)]
        vcd_files = [f for f in files if f.endswith('.vcd')]

        report_lines.append("| Category | Files |")
        report_lines.append("|----------|-------|")
        report_lines.append(f"| Design — RTL | {', '.join(rtl_files) if rtl_files else '-'} |")
        report_lines.append(f"| Design — Includes | {', '.join(include_files) if include_files else '-'} |")
        report_lines.append(f"| Design — Constraints | {', '.join(sdc_files) if sdc_files else '-'} |")
        report_lines.append(f"| Verification — Testbenches | {', '.join(tb_files) if tb_files else '-'} |")
        report_lines.append(f"| Verification — Formal properties | {', '.join(formal_files) if formal_files else '-'} |")
        report_lines.append(f"| Specifications | {', '.join(spec_files) if spec_files else '-'} |")
        report_lines.append(f"| Waveforms | {', '.join(vcd_files) if vcd_files else '-'} |")

        # Check for ORFS outputs
        orfs_results = os.path.join(report_dir, "orfs_results")
        if os.path.exists(orfs_results):
            import glob
            gds_files = glob.glob(os.path.join(orfs_results, "**", "*.gds"), recursive=True)
            odb_files = glob.glob(os.path.join(orfs_results, "**", "6_final.odb"), recursive=True)
            report_lines.append(f"| GDS Layout | {len(gds_files)} file(s) |")
            report_lines.append(f"| ODB Database | {len(odb_files)} file(s) |")
        if resolved_run_id:
            inputs_dir = os.path.join(report_dir, "inputs")
            if os.path.exists(inputs_dir):
                input_files = sorted(os.listdir(inputs_dir))
                report_lines.append(f"| Synthesis Inputs | {', '.join(input_files) if input_files else '-'} |")
            run_spec_files = sorted([f for f in os.listdir(report_dir) if f.endswith("_spec.yaml")]) if os.path.exists(report_dir) else []
            if run_spec_files:
                report_lines.append(f"| Run Spec Snapshot | {', '.join(run_spec_files)} |")
    
    # Verification Results
    report_lines.append("\n---\n## ✅ Verification Results\n")

    report_lines.append("| Check | Status |")
    report_lines.append("|-------|--------|")

    report_lines.append(_lint_status_cell(workspace_path))

    # Simulation status — the authoritative isolated sim runs, not a stale
    # workspace-root scan (which never matched isolated runs → false "Not Run").
    report_lines.append(_simulation_status_cell(workspace_path))

    # Synthesis Results
    report_lines.append("\n---\n## 🔧 Synthesis Results (PPA)\n")
    
    # Load metrics from saved file OR parse from logs
    metrics = load_metrics(workspace_path, run_id=resolved_run_id)
    
    if metrics:
        
        report_lines.append("| Metric | Value | Status |")
        report_lines.append("|--------|-------|--------|")
        
        # Area
        area = metrics.get("area_um2")
        if area:
            report_lines.append(f"| Area | {area:.2f} µm² | ✅ |")
        else:
            report_lines.append("| Area | N/A | - |")
        
        # Cell Count
        cells = metrics.get("cell_count")
        if cells:
            report_lines.append(f"| Cell Count | {cells} | ✅ |")
        else:
            report_lines.append("| Cell Count | N/A | - |")
        
        # Timing. ORFS's report_wns CLAMPS positive slack to 0, so a 0.00 reads
        # the same for a design with real margin and for one whose margin was
        # never reported at all. A NEGATIVE wns is not clamped and therefore IS
        # the worst slack — the same rule get_synthesis_metrics applies, so the
        # report and the metrics can never disagree about a run. Only that real
        # slack earns a verdict; the clamped 0.00 earns a labelled row and
        # nothing more.
        clamped_wns = metrics.get("wns_ns")
        timing_note = metrics.get("timing_note")
        wns = metrics.get("worst_slack_ns")
        if wns is None and clamped_wns is not None and clamped_wns < 0:
            wns = clamped_wns
        if wns is not None:
            status = "✅ Met" if wns >= 0 else "❌ Violated"
            report_lines.append(f"| Worst Slack (Setup) | {wns:.3f} ns | {status} |")
        elif clamped_wns is not None:
            report_lines.append(
                f"| WNS (Setup, ORFS-clamped) | {clamped_wns:.3f} ns | ⚠️ no verdict |"
            )
        else:
            report_lines.append("| Worst Slack (Setup) | N/A | - |")
        
        # Power
        power = metrics.get("power_uw")
        if power:
            report_lines.append(f"| Total Power | {power:.4f} µW | ✅ |")
        else:
            report_lines.append("| Total Power | N/A | - |")
        
        # Spec vs Actual comparison. The clock rows describe the CONSTRAINT and
        # are always printable; only the achieved rows and the verdict need the
        # real slack, because every one of them is derived from it — and derived
        # from a clamped 0.00 they reproduce the target echo this wave removed
        # (1000/(target - 0) == 1000/target).
        if wns is not None or clamped_wns is not None or timing_note:
            report_lines.append("\n### Timing Comparison\n")
            requested_clock, target_period, target_source = _resolve_run_clock_fields(run_meta, spec)
            if target_period is None:
                target_period = 0
            corner = metrics.get("timing_corner")

            if requested_clock is not None:
                report_lines.append(f"| Requested Clock | {requested_clock} ns |")
            report_lines.append(f"| Target Clock | {target_period} ns |")

            if wns is not None:
                # The achieved period is target - slack in BOTH directions:
                # positive slack means the clock could be tightened by that much,
                # negative means it must be loosened.
                achieved_period = target_period - wns
                slack_pct = (wns / target_period) * 100 if target_period > 0 else 0
                report_lines.append(f"| Achieved Slack | {wns:.3f} ns ({slack_pct:+.1f}%) |")
                report_lines.append(f"| Achieved Period | {achieved_period:.3f} ns |")
            if target_source:
                report_lines.append(f"| Timing Target Source | {target_source} |")
            if corner:
                # asap7 runs best-case (FF) libraries by default: an unlabelled
                # frequency from that corner overstates the design.
                report_lines.append(f"| Timing Corner | {corner} |")

            if wns is None:
                report_lines.append(
                    "\n*Timing cannot be judged from this run: ORFS's `report_wns` clamps "
                    "positive slack to 0 and these reports carry no `worst slack` line, so "
                    "neither the achieved margin nor the achieved frequency is recoverable. "
                    "The clock target above is a CONSTRAINT, not an achieved frequency.*"
                )
            else:
                # The achieved frequency comes from get_synthesis_metrics and
                # ONLY from there: it already prefers ORFS's own fmax, already
                # falls back to a labelled derivation from the real slack, and
                # already returns None when neither exists (a combinational block
                # has no maximum frequency at all). Re-deriving it here would be
                # a second opinion that can disagree with every other surface —
                # and the version of that arithmetic this report used to run was
                # the target echo itself.
                achieved_fmax = metrics.get("fmax_mhz")
                corner_suffix = f" ({corner} corner)" if corner else ""
                verdict = (
                    "✅ **Timing requirement MET**" if wns >= 0
                    else "❌ **Timing requirement NOT MET**"
                )
                if achieved_fmax is not None:
                    qualifier = "Design runs at" if wns >= 0 else "Max achievable:"
                    report_lines.append(
                        f"\n{verdict} - {qualifier} {achieved_fmax:.1f} MHz{corner_suffix}"
                    )
                else:
                    report_lines.append(f"\n{verdict}")
            if timing_note:
                report_lines.append(f"\n*{timing_note}*")
        
        # Note the source of metrics. Values parsed from this run's reports
        # always win; a saved design_metrics.json only fills what the parse
        # could not measure. Where the two disagree the report says so — a
        # silently dropped number is exactly the dishonest state invariant #4
        # forbids.
        conflicts = metrics.get("saved_metric_conflicts") or []
        metrics_path = os.path.join(report_dir, METRICS_FILENAME)
        if os.path.exists(metrics_path):
            report_lines.append(
                "\n*Values above are parsed from this run's synthesis reports; "
                "saved metrics (`design_metrics.json`) fill only fields the parse "
                "did not measure.*"
            )
        if conflicts:
            report_lines.append(
                "\n> ⚠️ **Saved metrics disagree with this run's reports.** "
                "The parsed values are shown above; the saved values were NOT used."
            )
            report_lines.append("\n| Metric | Saved (`design_metrics.json`) | Parsed (used) |")
            report_lines.append("|--------|------------------------------|---------------|")
            for conflict in conflicts:
                report_lines.append(
                    f"| {conflict['field']} | {conflict['saved']} | {conflict['parsed']} |"
                )
    else:
        report_lines.append("*Synthesis not run or metrics not available.*\n")
    
    # Footer
    report_lines.append("\n---\n## 📝 Notes\n")
    report_lines.append("- This report was auto-generated by SiliconCrew")
    if resolved_run_id:
        report_lines.append(f"- For detailed synthesis logs, check `synth_runs/{resolved_run_id}/orfs_logs/`")
    else:
        report_lines.append("- For detailed synthesis logs, check `orfs_logs/` directory")
    report_lines.append("- For waveform debugging, open `.vcd` files in the Waveform tab")
    
    return "\n".join(report_lines)


def save_design_report(workspace_path: str, spec_filename: str = None, run_id: str = None) -> str:
    """
    Generate and save a design report to the workspace.
    
    Returns:
        Path to the saved report file
    """
    report_content = generate_design_report(workspace_path, spec_filename, run_id=run_id)
    target_dir, resolved_run_id = _resolve_report_scope(workspace_path, run_id)
    
    # Find module name for filename
    module_name = "design"
    if resolved_run_id:
        report_path = os.path.join(target_dir, RUN_REPORT_FILENAME)
    elif spec_filename:
        module_name = spec_filename.replace("_spec.yaml", "")
        report_path = os.path.join(target_dir, f"{module_name}_report.md")
    else:
        spec_files = [f for f in os.listdir(workspace_path) if f.endswith("_spec.yaml")]
        if spec_files:
            module_name = spec_files[0].replace("_spec.yaml", "")
        report_path = os.path.join(target_dir, f"{module_name}_report.md")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
    
    return report_path
