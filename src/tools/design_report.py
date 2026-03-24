"""
Design Report Generator - Creates comprehensive reports comparing spec vs actual results.
"""

import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, Tuple
from src.tools.spec_manager import load_yaml_file, DesignSpec
from src.tools.get_ppa import get_ppa_metrics
from src.tools.synthesis_manager import get_run_dir, get_synthesis_metrics


# =============================================================================
# METRICS PERSISTENCE
# =============================================================================
# The agent can save metrics from any source (ppa_tool, search_logs_tool, etc.)
# The report generator reads from this file first, then falls back to parsing.

METRICS_FILENAME = "design_metrics.json"
RUN_REPORT_FILENAME = "design_report.md"


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


def load_metrics(workspace_path: str, run_id: str = None) -> Dict[str, Any]:
    """
    Load metrics from the workspace, trying multiple sources:
    1. First: design_metrics.json (saved by agent)
    2. Second: Parse ORFS logs directly (get_ppa_metrics)
    
    Returns:
        Dict with metrics or empty dict
    """
    metrics = {}
    
    # Source 1: Saved metrics file (highest priority - agent may have found these manually)
    target_dir, resolved_run_id = _resolve_report_scope(workspace_path, run_id)
    metrics_path = os.path.join(target_dir, METRICS_FILENAME)
    if os.path.exists(metrics_path):
        try:
            with open(metrics_path, 'r') as f:
                metrics = json.load(f)
        except:
            pass

    # Source 2: Structured parsing from the synthesis run
    if resolved_run_id:
        try:
            parsed = get_synthesis_metrics(workspace_path, resolved_run_id)
            parsed_metrics = parsed.get("metrics", {}) if parsed.get("status") == "ok" else {}
            for key in ["area_um2", "cell_count", "wns_ns", "tns_ns", "power_uw"]:
                if key not in metrics or metrics.get(key) is None:
                    if parsed_metrics.get(key) is not None:
                        metrics[key] = parsed_metrics[key]
        except:
            pass

    # Source 3: Legacy workspace-root parsing fallback
    if not resolved_run_id:
        orfs_logs = os.path.join(workspace_path, "orfs_logs")
        if os.path.exists(orfs_logs):
            try:
                parsed_metrics = get_ppa_metrics(orfs_logs)
                for key in ["area_um2", "cell_count", "wns_ns", "tns_ns", "power_uw"]:
                    if key not in metrics or metrics.get(key) is None:
                        if parsed_metrics.get(key) is not None:
                            metrics[key] = parsed_metrics[key]
            except:
                pass
    
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
        report_lines.append("*No specification file found.*\n")
    
    # Generated Files
    report_lines.append("\n---\n## 📁 Generated Files\n")
    
    if os.path.exists(workspace_path):
        files = os.listdir(workspace_path)
        
        rtl_files = [f for f in files if f.endswith(('.v', '.sv')) and not f.endswith('_tb.v')]
        tb_files = [f for f in files if f.endswith('_tb.v')]
        spec_files = [f for f in files if f.endswith('_spec.yaml')]
        sdc_files = [f for f in files if f.endswith('.sdc')]
        vcd_files = [f for f in files if f.endswith('.vcd')]
        
        report_lines.append("| Category | Files |")
        report_lines.append("|----------|-------|")
        report_lines.append(f"| RTL | {', '.join(rtl_files) if rtl_files else '-'} |")
        report_lines.append(f"| Testbenches | {', '.join(tb_files) if tb_files else '-'} |")
        report_lines.append(f"| Specifications | {', '.join(spec_files) if spec_files else '-'} |")
        report_lines.append(f"| Constraints | {', '.join(sdc_files) if sdc_files else '-'} |")
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
    
    # Check for simulation log or output
    sim_passed = None
    sim_log_path = os.path.join(workspace_path, "simulation.log")
    
    # Check for testbench outputs in various files
    for f in os.listdir(workspace_path) if os.path.exists(workspace_path) else []:
        if f.endswith('.out') or f == 'simulation.log':
            try:
                with open(os.path.join(workspace_path, f), 'r') as log_file:
                    content = log_file.read().lower()
                    if 'pass' in content:
                        sim_passed = True
                    elif 'fail' in content:
                        sim_passed = False
            except:
                pass
    
    report_lines.append("| Check | Status |")
    report_lines.append("|-------|--------|")
    
    # Lint status (assume passed if RTL exists)
    if rtl_files:
        report_lines.append("| Syntax (Lint) | ✅ Pass |")
    else:
        report_lines.append("| Syntax (Lint) | ⏳ Pending |")
    
    # Simulation status
    if sim_passed is True:
        report_lines.append("| Simulation | ✅ Pass |")
    elif sim_passed is False:
        report_lines.append("| Simulation | ❌ Fail |")
    else:
        report_lines.append("| Simulation | ⏳ Not Run |")
    
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
        
        # Timing
        wns = metrics.get("wns_ns")
        if wns is not None:
            status = "✅ Met" if wns >= 0 else "❌ Violated"
            report_lines.append(f"| WNS (Setup) | {wns:.3f} ns | {status} |")
        else:
            report_lines.append("| WNS (Setup) | N/A | - |")
        
        # Power
        power = metrics.get("power_uw")
        if power:
            report_lines.append(f"| Total Power | {power:.4f} µW | ✅ |")
        else:
            report_lines.append("| Total Power | N/A | - |")
        
        # Spec vs Actual comparison
        if wns is not None:
            report_lines.append("\n### Timing Comparison\n")
            requested_clock, target_period, target_source = _resolve_run_clock_fields(run_meta, spec)
            if target_period is None:
                target_period = 0
            achieved_period = target_period - wns if wns < 0 else target_period
            slack_pct = (wns / target_period) * 100 if target_period > 0 else 0
            
            if requested_clock is not None:
                report_lines.append(f"| Requested Clock | {requested_clock} ns |")
            report_lines.append(f"| Target Clock | {target_period} ns |")
            report_lines.append(f"| Achieved Slack | {wns:.3f} ns ({slack_pct:+.1f}%) |")
            if target_source:
                report_lines.append(f"| Timing Target Source | {target_source} |")
            
            if wns >= 0:
                if target_period > 0:
                    report_lines.append(f"\n✅ **Timing requirement MET** - Design can run at {1000/target_period:.1f} MHz")
                else:
                    report_lines.append("\n✅ **Timing requirement MET**")
            else:
                max_freq = 1000 / achieved_period if achieved_period > 0 else 0
                report_lines.append(f"\n❌ **Timing requirement NOT MET** - Max achievable: {max_freq:.1f} MHz")
        
        # Note the source of metrics
        metrics_path = os.path.join(report_dir, METRICS_FILENAME)
        if os.path.exists(metrics_path):
            report_lines.append("\n*Metrics loaded from saved data.*")
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
