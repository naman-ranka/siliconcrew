import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.tools.run_docker import run_docker_command
from src.tools.spec_manager import load_yaml_file
from src.platform_engines.orfs_runner import OrfsRequest, get_orfs_runner
from src.platform_engines.provenance import collect_provenance


def _pinned_num_cores() -> int:
    """Pinned ORFS P&R core count (determinism). From platform settings."""
    try:
        from src.platform_engines.settings import get_settings

        return max(1, int(get_settings().num_cores))
    except Exception:
        return 4


def _configured_orfs_backend() -> str:
    """The execution backend the ORFS runner is configured for, without running.

    Used to label a job as remote/local in its status payload while it is still
    in flight. Falls back to "local_docker" if the runner cannot be resolved.
    """
    try:
        return getattr(get_orfs_runner(), "backend", "local_docker") or "local_docker"
    except Exception:
        return "local_docker"


def _run_orfs_via_runner(
    run_dir: str,
    command: str,
    volumes: List[str],
    timeout: int,
) -> Dict[str, Any]:
    """Execute one ORFS invocation through the swappable OrfsRunner seam.

    Returns the same dict shape the synthesis manager has always consumed
    (``success``/``stdout``/``stderr``/``command``) so run management is
    unchanged regardless of whether the local Docker or cloud Job backend runs.
    """
    result = get_orfs_runner().run(
        OrfsRequest(run_dir=run_dir, command=command, volumes=list(volumes), timeout=timeout)
    )
    return {
        "success": result.success,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": result.command,
        "backend": result.backend,
    }

RUNS_DIRNAME = "synth_runs"
INDEX_FILENAME = "index.json"
LATEST_FILENAME = "LATEST"
RUN_META_FILENAME = "run_meta.json"

PD_STAGE_SEQUENCE = ["constraints", "synth", "floorplan", "place", "cts", "grt", "route", "finish"]
PD_RETRYABLE_STAGES = ["floorplan", "place", "cts", "grt", "route", "finish"]
PD_STAGE_TARGETS = {
    "floorplan": "do-floorplan",
    "place": "do-place",
    "cts": "do-cts",
    "grt": "do-grt",
    "route": "do-route",
    "finish": "do-finish",
}
PD_PREREQ_FILES = {
    "floorplan": [("1_synth.odb", "1_synth.odb"), ("1_synth.sdc", "1_synth.sdc")],
    "place": [("2_floorplan.odb", "2_floorplan.odb"), ("2_floorplan.sdc", "2_floorplan.sdc")],
    "cts": [("3_place.odb", "3_place.odb"), ("3_place.sdc", "3_place.sdc")],
    "grt": [("4_cts.odb", "4_cts.odb"), ("4_cts.sdc", "4_cts.sdc")],
    # ORFS do-route invokes 5_1_grt first, so it needs the CTS checkpoint.
    "route": [("4_cts.odb", "4_cts.odb"), ("4_cts.sdc", "4_cts.sdc")],
    "finish": [("5_route.odb", "5_route.odb"), ("5_route.sdc", "5_route.sdc")],
}

_JOB_LOCK = threading.Lock()
_INDEX_LOCK = threading.Lock()
# Default single-tenant executor (local / self-host). In hosted mode this is
# replaced via set_job_executor() with a per-user queue so one tenant's backlog
# cannot starve others and per-user synth concurrency is enforced. Any object
# with a ``.submit(fn, *args)`` returning a concurrent.futures.Future works.
_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_ACTIVE_EXECUTOR: Any = None


def set_job_executor(executor: Any) -> None:
    """Override the synth job executor (hosted per-user queue). None resets to default."""
    global _ACTIVE_EXECUTOR
    _ACTIVE_EXECUTOR = executor


def _job_executor() -> Any:
    return _ACTIVE_EXECUTOR if _ACTIVE_EXECUTOR is not None else _EXECUTOR


# Quota enforcement around synthesis. None (default) = self-host, no enforcement.
# In hosted mode settings.apply_platform_wiring installs a shared QuotaManager so
# per-user concurrency / daily-run / monthly-compute caps are enforced fleet-wide.
_QUOTA_MANAGER: Any = None


def set_quota_manager(manager: Any) -> None:
    """Install the quota manager enforced around synth submissions (None disables)."""
    global _QUOTA_MANAGER
    _QUOTA_MANAGER = manager


def _quota_identity() -> tuple:
    """(user_id, tier) for the current request, from the session context."""
    try:
        from src.utils.session_context import get_current_session

        ctx = get_current_session()
        if ctx:
            return (ctx.user_id or ctx.session_id, ctx.tier or "user")
    except Exception:
        pass
    return ("local", "user")


def _reserve_synth_quota():
    """Reserve a synth slot for the current user, or return an error envelope.

    Returns ``(reservation, None)`` on success, or ``(None, error_dict)`` when a
    cap is hit. ``reservation`` is None when no quota manager is installed
    (self-host) — synthesis proceeds unchanged.
    """
    if _QUOTA_MANAGER is None:
        return None, None
    from src.platform_engines.quotas import QuotaExceeded

    user_id, tier = _quota_identity()
    try:
        return _QUOTA_MANAGER.reserve_synth_run(user_id, tier), None
    except QuotaExceeded as exc:
        env = exc.to_envelope()
        return None, {
            "status": "rejected",
            "ok": False,
            "error": env["error"],
            "check_notes": exc.message,
            "next_action": "Wait for your in-flight run / quota window, or add capacity.",
        }


def _submit_with_quota_release(reservation, fn, *fn_args):
    """Submit ``fn`` to the active executor, releasing the reservation when done."""
    def runner():
        try:
            return fn(*fn_args)
        finally:
            if reservation is not None and _QUOTA_MANAGER is not None:
                try:
                    _QUOTA_MANAGER.release_synth_run(reservation)
                except Exception:
                    pass

    return _job_executor().submit(runner)


_JOBS: Dict[str, Dict[str, Any]] = {}
_POLL_CACHE: Dict[str, Dict[str, Any]] = {}
_POLL_BACKOFF_STATE: Dict[str, Dict[str, Any]] = {}
_ORFS_OVERRIDE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Prevent aggressive status polling loops from burning recursion/context.
POLL_MIN_INTERVAL_SEC = 1.0
POLL_BACKOFF_START_SEC = 30
POLL_BACKOFF_MAX_SEC = 600
SYNTH_HARD_TIMEOUT_SEC = 1200


@dataclass
class GuardrailSummary:
    constraints: str = "skip"
    signoff: str = "skip"
    equiv: str = "skip"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def _runs_root(workspace: str) -> str:
    return _ensure_dir(os.path.join(workspace, RUNS_DIRNAME))


def _index_path(workspace: str) -> str:
    return os.path.join(_runs_root(workspace), INDEX_FILENAME)


def _latest_path(workspace: str) -> str:
    return os.path.join(_runs_root(workspace), LATEST_FILENAME)


def _load_index(workspace: str) -> Dict[str, Any]:
    path = _index_path(workspace)
    if not os.path.exists(path):
        return {"runs": [], "jobs": []}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            data.setdefault("runs", [])
            data.setdefault("jobs", [])
            return data
    except Exception:
        return {"runs": [], "jobs": []}


def _save_index(workspace: str, data: Dict[str, Any]) -> None:
    with open(_index_path(workspace), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _next_run_id(workspace: str) -> str:
    root = _runs_root(workspace)
    existing = [d for d in os.listdir(root) if re.match(r"synth_\d{4}$", d)]
    if not existing:
        return "synth_0001"
    max_id = max(int(x.split("_")[1]) for x in existing)
    return f"synth_{max_id + 1:04d}"


def _allocate_run_dir(workspace: str) -> tuple[str, str]:
    with _JOB_LOCK:
        while True:
            run_id = _next_run_id(workspace)
            run_dir = os.path.join(_runs_root(workspace), run_id)
            try:
                os.makedirs(run_dir, exist_ok=False)
                return run_id, run_dir
            except FileExistsError:
                continue


def _write_json(path: str, data: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _read_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _copy_inputs(verilog_files: List[str], input_dir: str) -> List[str]:
    copied = []
    for src in verilog_files:
        name = os.path.basename(src)
        dst = os.path.join(input_dir, name)
        shutil.copy2(src, dst)
        copied.append(dst)
    return copied


def _find_latest_spec(workspace: str) -> Optional[str]:
    specs = [x for x in os.listdir(workspace) if x.endswith("_spec.yaml")]
    if not specs:
        return None
    specs.sort(key=lambda x: os.path.getmtime(os.path.join(workspace, x)), reverse=True)
    return os.path.join(workspace, specs[0])


def _copy_active_spec(workspace: str, run_dir: str) -> Optional[str]:
    spec_path = _find_latest_spec(workspace)
    if not spec_path or not os.path.exists(spec_path):
        return None
    dst = os.path.join(run_dir, os.path.basename(spec_path))
    shutil.copy2(spec_path, dst)
    return dst


def _write_default_sdc(sdc_path: str, clock_period_ns: float, clock_port: str = "clk") -> None:
    # Guarded SDC so missing ports do not hard-fail synthesis scripts.
    content = (
        f"set _sc_clk_ports [get_ports {{{clock_port}}}]\n"
        f"if {{[llength $_sc_clk_ports] > 0}} {{\n"
        f"  create_clock -period {clock_period_ns} $_sc_clk_ports\n"
        "}\n"
    )
    with open(sdc_path, "w", encoding="utf-8") as f:
        f.write(content)


def _constraints_guardrail(
    workspace: str,
    run_dir: str,
    top_module: str,
    fallback_clock_period_ns: Optional[float],
    constraints_mode: str = "auto",
) -> Dict[str, Any]:
    result = {
        "status": "fail",
        "note": "No specification file found.",
        "sdc_path": None,
        "requested_clock_period_ns": fallback_clock_period_ns,
        "effective_clock_period_ns": fallback_clock_period_ns,
        "clock_period_ns": fallback_clock_period_ns,
        "clock_source": "requested" if fallback_clock_period_ns and fallback_clock_period_ns > 0 else None,
    }
    constraints_mode = (constraints_mode or "auto").lower().strip()
    if constraints_mode not in {"auto", "strict", "bypass"}:
        constraints_mode = "auto"

    spec_path = _find_latest_spec(workspace)
    if not spec_path:
        if fallback_clock_period_ns is None or fallback_clock_period_ns <= 0:
            result["note"] = "No spec file and no valid clock period provided."
            return result
        sdc_path = os.path.join(run_dir, "constraints.sdc")
        _write_default_sdc(sdc_path=sdc_path, clock_period_ns=fallback_clock_period_ns, clock_port="clk")
        result.update({
            "status": "pass",
            "note": "No spec found; generated fallback constraints.sdc from explicit clock period.",
            "sdc_path": sdc_path,
            "effective_clock_period_ns": fallback_clock_period_ns,
        })
        return result

    try:
        spec = load_yaml_file(spec_path)
    except Exception as exc:
        result["note"] = f"Failed to parse spec: {exc}"
        return result

    if spec.module_name != top_module:
        result["note"] = f"Spec module '{spec.module_name}' does not match top module '{top_module}'."
        return result

    clock_ports = [p.name for p in spec.ports if p.direction == "input" and p.name.lower() in {"clk", "clock", "clk_i"}]
    input_ports = [p.name for p in spec.ports if p.direction == "input"]
    if not clock_ports:
        if constraints_mode == "strict":
            result["note"] = (
                "Spec is missing a recognized clock input (clk/clock/clk_i). "
                "Rerun start_synthesis with constraints_mode='auto' or 'bypass' to allow default-clock fallback."
            )
            return result
        fallback_port = input_ports[0] if input_ports else "clk"
        requested_clock = fallback_clock_period_ns if fallback_clock_period_ns and fallback_clock_period_ns > 0 else None
        period = requested_clock if requested_clock is not None else (
            spec.clock_period_ns if spec.clock_period_ns > 0 else 10.0
        )
        sdc_path = os.path.join(run_dir, "constraints.sdc")
        _write_default_sdc(sdc_path=sdc_path, clock_period_ns=period, clock_port=fallback_port)
        result.update({
            "status": "pass",
            "note": (
                f"No explicit clock in spec. Applied explicit requested clock on port '{fallback_port}'."
                if requested_clock is not None
                else f"No explicit clock in spec. Applied default clock fallback on port '{fallback_port}'."
            ),
            "sdc_path": sdc_path,
            "effective_clock_period_ns": period,
            "clock_period_ns": period,
            "clock_source": "requested" if requested_clock is not None else "spec_fallback_port",
        })
        return result

    if spec.clock_period_ns <= 0:
        result["note"] = "Spec clock period must be > 0."
        return result

    sdc_path = os.path.join(run_dir, "constraints.sdc")
    requested_clock = fallback_clock_period_ns if fallback_clock_period_ns and fallback_clock_period_ns > 0 else None
    if requested_clock is not None:
        clock_port = clock_ports[0]
        _write_default_sdc(sdc_path=sdc_path, clock_period_ns=requested_clock, clock_port=clock_port)
        result.update({
            "status": "pass",
            "note": f"Explicit requested clock override applied on spec clock port '{clock_port}'.",
            "sdc_path": sdc_path,
            "effective_clock_period_ns": requested_clock,
            "clock_period_ns": requested_clock,
            "clock_source": "requested",
        })
        return result

    sdc_content = spec.generate_sdc()
    if "create_clock" not in sdc_content:
        result["note"] = "Generated SDC missing create_clock."
        return result

    with open(sdc_path, "w", encoding="utf-8") as f:
        f.write(sdc_content)

    result.update({
        "status": "pass",
        "note": "Spec-driven constraints validated.",
        "sdc_path": sdc_path,
        "effective_clock_period_ns": spec.clock_period_ns,
        "clock_period_ns": spec.clock_period_ns,
        "clock_source": "spec",
    })
    return result


def _infer_stage(lines: List[str]) -> str:
    text = "\n".join(lines).lower()
    if any(k in text for k in ["global route", "detailed route", "route"]):
        return "route"
    if any(k in text for k in ["clock tree", "cts"]):
        return "cts"
    if "place" in text:
        return "place"
    if "floorplan" in text:
        return "floorplan"
    if "yosys" in text or "synth" in text:
        return "synth"
    if "finish" in text or "final" in text:
        return "final"
    return "unknown"


def _tail_lines(path: str, max_lines: int = 40) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read().splitlines()[-max_lines:]
    except Exception:
        return []


def _collect_log_tail(run_dir: str, max_lines: int = 40) -> List[str]:
    logs_root = os.path.join(run_dir, "orfs_logs")
    if not os.path.exists(logs_root):
        return []
    candidates = []
    for root, _, files in os.walk(logs_root):
        for name in files:
            if name.endswith((".log", ".rpt", ".txt")):
                path = os.path.join(root, name)
                candidates.append((os.path.getmtime(path), path))
    if not candidates:
        return []
    _, latest = sorted(candidates, key=lambda x: x[0], reverse=True)[0]
    return _tail_lines(latest, max_lines=max_lines)


def _extract_summary_metrics(run_dir: str) -> Dict[str, Any]:
    metrics = {"area_um2": None, "cell_count": None, "wns_ns": None, "tns_ns": None, "power_uw": None}
    reports_root = os.path.join(run_dir, "orfs_reports")
    logs_root = os.path.join(run_dir, "orfs_logs")
    search_roots = [reports_root, logs_root]

    area_re = re.compile(r"Chip area.*:\s*([0-9.]+)", re.IGNORECASE)
    cells_re = re.compile(r"Number of cells.*:\s*([0-9]+)", re.IGNORECASE)
    wns_re = re.compile(r"\bwns\b\s*[:=]?\s*([0-9.+-]+)", re.IGNORECASE)
    tns_re = re.compile(r"\btns\b\s*[:=]?\s*([0-9.+-]+)", re.IGNORECASE)
    power_re = re.compile(r"Total Power\s+([0-9.eE+-]+)", re.IGNORECASE)

    for base in search_roots:
        if not os.path.exists(base):
            continue
        for root, _, files in os.walk(base):
            for name in files:
                if not name.endswith((".log", ".rpt", ".txt")):
                    continue
                path = os.path.join(root, name)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        text = f.read()
                except Exception:
                    continue
                if metrics["area_um2"] is None:
                    m = area_re.search(text)
                    if m:
                        metrics["area_um2"] = float(m.group(1))
                if metrics["cell_count"] is None:
                    m = cells_re.search(text)
                    if m:
                        metrics["cell_count"] = int(m.group(1))
                if metrics["wns_ns"] is None:
                    m = wns_re.search(text)
                    if m:
                        metrics["wns_ns"] = float(m.group(1))
                if metrics["tns_ns"] is None:
                    m = tns_re.search(text)
                    if m:
                        metrics["tns_ns"] = float(m.group(1))
                if metrics["power_uw"] is None:
                    m = power_re.search(text)
                    if m:
                        metrics["power_uw"] = float(m.group(1))
    return metrics


def _collect_artifacts(run_dir: str) -> Dict[str, int]:
    counts = {"gds": 0, "def": 0, "odb": 0, "reports": 0, "netlists": 0}
    for root, _, files in os.walk(run_dir):
        for name in files:
            lower = name.lower()
            if lower.endswith(".gds"):
                counts["gds"] += 1
            elif lower.endswith(".def"):
                counts["def"] += 1
            elif lower.endswith(".odb"):
                counts["odb"] += 1
            elif lower.endswith(".rpt"):
                counts["reports"] += 1
            elif lower.endswith(".v"):
                counts["netlists"] += 1
    return counts


def _init_stage_metadata() -> Dict[str, Any]:
    return {
        stage: {
            "status": "pending",
            "artifacts": {},
        }
        for stage in PD_STAGE_SEQUENCE
    }


def _find_stage_artifacts(run_dir: str) -> Dict[str, Dict[str, str]]:
    found: Dict[str, Dict[str, str]] = {stage: {} for stage in PD_STAGE_SEQUENCE}

    checks = {
        "synth": [
            ("odb", "orfs_results", "1_synth.odb"),
            ("sdc", "orfs_results", "1_synth.sdc"),
            ("stat_report", "orfs_reports", "synth_stat.txt"),
        ],
        "floorplan": [
            ("report", "orfs_reports", "2_floorplan_final.rpt"),
            ("odb", "orfs_results", "2_floorplan.odb"),
            ("sdc", "orfs_results", "2_floorplan.sdc"),
        ],
        "place": [
            ("log", "orfs_logs", "3_3_place_gp.json"),
            ("odb", "orfs_results", "3_place.odb"),
            ("sdc", "orfs_results", "3_place.sdc"),
        ],
        "cts": [
            ("report", "orfs_reports", "4_cts_final.rpt"),
            ("odb", "orfs_results", "4_cts.odb"),
            ("sdc", "orfs_results", "4_cts.sdc"),
        ],
        "grt": [
            ("report", "orfs_reports", "congestion.rpt"),
            ("log", "orfs_logs", "5_1_grt.log"),
            ("odb", "orfs_results", "5_1_grt.odb"),
            ("sdc", "orfs_results", "5_1_grt.sdc"),
        ],
        "route": [
            ("report", "orfs_reports", "5_route_drc.rpt"),
            ("odb", "orfs_results", "5_route.odb"),
            ("sdc", "orfs_results", "5_route.sdc"),
        ],
        "finish": [
            ("report", "orfs_reports", "6_finish.rpt"),
            ("odb", "orfs_results", "6_final.odb"),
            ("sdc", "orfs_results", "6_final.sdc"),
            ("netlist", "orfs_results", "6_final.v"),
            ("gds", "orfs_results", "6_final.gds"),
        ],
    }

    for stage, candidates in checks.items():
        for artifact_key, scope, filename in candidates:
            path = _find_artifact_file(run_dir, scope, filename)
            if path:
                found[stage][artifact_key] = path
    return found


def _orfs_final_artifacts_are_clean(run_dir: str, top_module: str) -> Dict[str, str]:
    finish_report = _find_report_file(run_dir, "6_finish.rpt")
    if not finish_report:
        return {"status": "fail", "note": "6_finish.rpt not found"}

    netlist = _find_netlist(run_dir, top_module)
    if not netlist:
        return {"status": "fail", "note": "6_final.v netlist not found"}

    gds = _find_artifact_file(run_dir, "orfs_results", "6_final.gds")
    if not gds:
        return {"status": "fail", "note": "6_final.gds not found"}

    finish_data = _parse_finish_report(finish_report)
    wns = finish_data.get("wns_ns")
    tns = finish_data.get("tns_ns")
    if wns is None or tns is None:
        return {"status": "fail", "note": "final timing metrics could not be parsed"}
    if wns < 0 or tns != 0:
        return {"status": "fail", "note": f"final timing is not clean: WNS={wns}, TNS={tns}"}

    violations = finish_data.get("violations", {})
    for key in ("setup", "hold", "max_slew", "max_cap", "max_fanout"):
        value = violations.get(key)
        if value not in (None, 0):
            return {"status": "fail", "note": f"final {key} violation count is {value}"}

    route_drc = _find_artifact_file(run_dir, "orfs_reports", "5_route_drc.rpt")
    if route_drc:
        try:
            with open(route_drc, "r", encoding="utf-8", errors="ignore") as f:
                if f.read().strip():
                    return {"status": "fail", "note": "final route DRC report is not empty"}
        except Exception:
            return {"status": "fail", "note": "final route DRC report could not be read"}

    report_json = _find_artifact_file(run_dir, "orfs_logs", "6_report.json")
    if report_json:
        try:
            data = _read_json(report_json)
            errors = data.get("finish__flow__errors__count")
            if errors not in (None, 0):
                return {"status": "fail", "note": f"finish flow errors count is {errors}"}
        except Exception:
            return {"status": "fail", "note": "6_report.json could not be parsed"}

    return {"status": "pass", "note": "final artifacts, timing, and route DRC are clean"}


def _stage_artifacts_indicate_completion(stage: str, artifacts: Dict[str, str]) -> bool:
    if not artifacts:
        return False
    if stage == "route":
        return "odb" in artifacts or "sdc" in artifacts
    return True


def _refresh_stage_metadata(run_dir: str, run_meta: Dict[str, Any], terminal_status: Optional[str] = None) -> Dict[str, Any]:
    stages = run_meta.get("stages")
    if not isinstance(stages, dict):
        stages = _init_stage_metadata()

    discovered = _find_stage_artifacts(run_dir)
    for stage in PD_STAGE_SEQUENCE:
        stage_meta = stages.get(stage, {"status": "pending", "artifacts": {}})
        stage_meta.setdefault("artifacts", {})
        if stage == "constraints":
            constraints_ok = run_meta.get("auto_checks", {}).get("constraints")
            if constraints_ok == "pass":
                stage_meta["status"] = "completed"
            elif constraints_ok == "fail":
                stage_meta["status"] = "failed"
        else:
            artifacts = discovered.get(stage, {})
            if artifacts:
                stage_meta["artifacts"] = artifacts
            if _stage_artifacts_indicate_completion(stage, artifacts):
                stage_meta["status"] = "completed"
            elif terminal_status == "failed" and run_meta.get("current_stage") == stage:
                stage_meta["status"] = "failed"
        stages[stage] = stage_meta

    # If a later stage completed, earlier stages necessarily completed too, even
    # when intermediate artifacts were not preserved in the mounted run dir.
    for idx, stage in enumerate(PD_RETRYABLE_STAGES):
        if any(stages.get(later, {}).get("status") == "completed" for later in PD_RETRYABLE_STAGES[idx + 1 :]):
            stages[stage]["status"] = "completed"

    downstream_completed = any(stages.get(stage, {}).get("status") == "completed" for stage in PD_RETRYABLE_STAGES)
    if downstream_completed and stages["synth"].get("status") != "completed":
        stages["synth"]["status"] = "completed"

    if terminal_status == "completed":
        run_meta["current_stage"] = "finish"
    elif terminal_status == "failed":
        failed_stage = run_meta.get("current_stage") or _infer_stage(_collect_log_tail(run_dir))
        run_meta["current_stage"] = failed_stage
        if failed_stage in stages and stages[failed_stage].get("status") != "completed":
            stages[failed_stage]["status"] = "failed"

    run_meta["stages"] = stages
    return run_meta


def _load_run_meta_with_inferred_stages(run_dir: str) -> Dict[str, Any]:
    run_meta = _read_run_meta(run_dir)
    stages = run_meta.get("stages")
    if isinstance(stages, dict) and stages:
        return run_meta

    terminal_status = run_meta.get("status")
    if terminal_status not in {"completed", "failed"}:
        terminal_status = None
    return _refresh_stage_metadata(run_dir, run_meta, terminal_status=terminal_status)


def _read_config_mk_pd_parameters(run_dir: str) -> Dict[str, Any]:
    config_path = os.path.join(run_dir, "config.mk")
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return {}

    values: Dict[str, Any] = {}
    for key, out_key, cast in [
        ("CORE_UTILIZATION", "utilization", int),
        ("CORE_ASPECT_RATIO", "aspect_ratio", float),
        ("CORE_MARGIN", "core_margin", float),
    ]:
        match = re.search(rf"^\s*export\s+{key}\s*=\s*([^\s#]+)", text, re.MULTILINE)
        if not match:
            continue
        try:
            values[out_key] = cast(match.group(1))
        except Exception:
            pass
    return values


def _pd_parameters_from_run(run_dir: str, run_meta: Dict[str, Any]) -> Dict[str, Any]:
    config_values = _read_config_mk_pd_parameters(run_dir)
    nested = run_meta.get("pd_parameters") if isinstance(run_meta.get("pd_parameters"), dict) else {}

    def _pick(name: str, default: Any, cast: Any) -> Any:
        for source in (run_meta, nested, config_values):
            value = source.get(name)
            if value is None:
                continue
            try:
                return cast(value)
            except Exception:
                continue
        return default

    utilization = _pick("utilization", 5, int)
    return {
        "utilization": max(1, min(100, utilization)),
        "aspect_ratio": _pick("aspect_ratio", 1.0, float),
        "core_margin": _pick("core_margin", 2.0, float),
    }


def _find_netlist(run_dir: str, top_module: str) -> Optional[str]:
    roots = [os.path.join(run_dir, "orfs_results"), os.path.join(run_dir, "inputs")]
    ranked = []
    for base in roots:
        if not os.path.exists(base):
            continue
        for root, _, files in os.walk(base):
            for name in files:
                if not name.endswith(".v"):
                    continue
                path = os.path.join(root, name)
                score = 0
                lname = name.lower()
                if "final" in lname:
                    score += 4
                if "yosys" in lname:
                    score += 3
                if top_module.lower() in lname:
                    score += 2
                score += int(os.path.getmtime(path) / 1000)
                ranked.append((score, path))
    if not ranked:
        return None
    return sorted(ranked, key=lambda x: x[0], reverse=True)[0][1]


def _run_equiv_check(golden_files: List[str], gate_file: str, top_module: str, timeout_sec: int = 300) -> Dict[str, str]:
    if not shutil.which("yosys"):
        return {"status": "skip", "note": "yosys not available"}

    script = [
        "read_verilog " + " ".join(golden_files),
        f"prep -top {top_module}",
        "design -stash gold",
        f"read_verilog {gate_file}",
        f"prep -top {top_module}",
        "design -stash gate",
        "design -copy-from gold -as gold_top gold",
        "design -copy-from gate -as gate_top gate",
        "equiv_make gold_top gate_top equiv",
        "hierarchy -top equiv",
        "equiv_simple",
        "equiv_status -assert",
    ]
    cmd = ["yosys", "-q", "-p", "; ".join(script)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        return {"status": "fail", "note": "equivalence timed out"}
    except Exception as exc:
        return {"status": "fail", "note": f"equivalence execution error: {exc}"}

    if proc.returncode == 0:
        return {"status": "pass", "note": "yosys equivalence passed"}
    tail = (proc.stderr or proc.stdout or "")[-400:]
    return {"status": "fail", "note": f"yosys equivalence failed: {tail}"}


def _run_orfs(
    run_dir: str,
    top_module: str,
    platform: str,
    input_files: List[str],
    clock_period_ns: float,
    utilization: int,
    aspect_ratio: float,
    core_margin: float,
    timeout: int,
) -> Dict[str, Any]:
    results_dir = _ensure_dir(os.path.join(run_dir, "orfs_results"))
    logs_dir = _ensure_dir(os.path.join(run_dir, "orfs_logs"))
    reports_dir = _ensure_dir(os.path.join(run_dir, "orfs_reports"))

    rel_files = [f"/workspace/inputs/{os.path.basename(x)}" for x in input_files]
    config_mk = os.path.join(run_dir, "config.mk")
    config = (
        f"export DESIGN_NAME = {top_module}\n"
        f"export PLATFORM = {platform}\n"
        f"export VERILOG_FILES = {' '.join(rel_files)}\n"
        "export SDC_FILE = /workspace/constraints.sdc\n"
        f"export CORE_UTILIZATION = {utilization}\n"
        f"export CORE_ASPECT_RATIO = {aspect_ratio}\n"
        f"export CORE_MARGIN = {core_margin}\n"
        # Determinism: pin NUM_CORES so P&R parallelism (the only real source of
        # run-to-run nondeterminism) is fixed and runs are reproducible.
        f"export NUM_CORES = {_pinned_num_cores()}\n"
    )
    with open(config_mk, "w", encoding="utf-8") as f:
        f.write(config)

    volumes = [
        f"{results_dir}:/OpenROAD-flow-scripts/flow/results",
        f"{logs_dir}:/OpenROAD-flow-scripts/flow/logs",
        f"{reports_dir}:/OpenROAD-flow-scripts/flow/reports",
    ]

    return _run_orfs_via_runner(
        run_dir=run_dir,
        command="make -B DESIGN_CONFIG=/workspace/config.mk",
        volumes=volumes,
        timeout=timeout,
    )


def _write_orfs_config(
    run_dir: str,
    top_module: str,
    platform: str,
    input_files: List[str],
    utilization: int,
    aspect_ratio: float,
    core_margin: float,
    orfs_overrides: Optional[Dict[str, Any]] = None,
) -> str:
    rel_files = [f"/workspace/inputs/{os.path.basename(x)}" for x in input_files]
    config_mk = os.path.join(run_dir, "config.mk")
    lines = [
        f"export DESIGN_NAME = {top_module}",
        f"export PLATFORM = {platform}",
        f"export VERILOG_FILES = {' '.join(rel_files)}",
        "export SDC_FILE = /workspace/constraints.sdc",
        f"export CORE_UTILIZATION = {utilization}",
        f"export CORE_ASPECT_RATIO = {aspect_ratio}",
        f"export CORE_MARGIN = {core_margin}",
        # Determinism: pin NUM_CORES (see _run_orfs). Overrides below may still
        # set a different value explicitly if a retry intentionally varies it.
        f"export NUM_CORES = {_pinned_num_cores()}",
    ]
    for key, value in (orfs_overrides or {}).items():
        lines.append(f"export {key} = {value}")
    with open(config_mk, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return config_mk


def _run_orfs_targets(
    run_dir: str,
    top_module: str,
    platform: str,
    input_files: List[str],
    utilization: int,
    aspect_ratio: float,
    core_margin: float,
    targets: List[str],
    timeout: int,
    orfs_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    results_dir = _ensure_dir(os.path.join(run_dir, "orfs_results"))
    logs_dir = _ensure_dir(os.path.join(run_dir, "orfs_logs"))
    reports_dir = _ensure_dir(os.path.join(run_dir, "orfs_reports"))

    _write_orfs_config(
        run_dir=run_dir,
        top_module=top_module,
        platform=platform,
        input_files=input_files,
        utilization=utilization,
        aspect_ratio=aspect_ratio,
        core_margin=core_margin,
        orfs_overrides=orfs_overrides,
    )

    volumes = [
        f"{results_dir}:/OpenROAD-flow-scripts/flow/results",
        f"{logs_dir}:/OpenROAD-flow-scripts/flow/logs",
        f"{reports_dir}:/OpenROAD-flow-scripts/flow/reports",
    ]
    target_cmds = [f"make DESIGN_CONFIG=/workspace/config.mk {target}" for target in targets]
    return _run_orfs_via_runner(
        run_dir=run_dir,
        command="set -e; " + "; ".join(target_cmds),
        volumes=volumes,
        timeout=timeout,
    )


def _stage_range(start_stage: str, max_stage: str) -> List[str]:
    start_idx = PD_RETRYABLE_STAGES.index(start_stage)
    end_idx = PD_RETRYABLE_STAGES.index(max_stage)
    return PD_RETRYABLE_STAGES[start_idx : end_idx + 1]


def _parse_orfs_overrides(orfs_overrides_json: Optional[str]) -> Dict[str, Any]:
    raw = (orfs_overrides_json or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception as exc:
        raise ValueError(f"Invalid orfs_overrides_json: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("orfs_overrides_json must decode to a JSON object.")

    normalized: Dict[str, Any] = {}
    for raw_key, value in parsed.items():
        key = str(raw_key)
        if not _ORFS_OVERRIDE_KEY_RE.match(key):
            raise ValueError(
                f"Invalid ORFS override key '{key}'. Keys must match ^[A-Z][A-Z0-9_]*$."
            )
        if value is None or isinstance(value, (dict, list)):
            raise ValueError(f"Invalid ORFS override value for '{key}'. Use a scalar string/number/bool.")
        text = str(value)
        if any(ch in text for ch in ["\n", "\r", "\x00", "$", "`"]):
            raise ValueError(
                f"Invalid ORFS override value for '{key}'. Newlines, NUL, '$', and backticks are not allowed."
            )
        normalized[key] = value
    return normalized


def _copy_retry_inputs(parent_run_dir: str, child_run_dir: str, parent_meta: Optional[Dict[str, Any]] = None) -> tuple[List[str], Optional[str]]:
    parent_inputs = os.path.join(parent_run_dir, "inputs")
    child_inputs = _ensure_dir(os.path.join(child_run_dir, "inputs"))
    copied_inputs: List[str] = []
    if os.path.exists(parent_inputs):
        for name in os.listdir(parent_inputs):
            src = os.path.join(parent_inputs, name)
            if os.path.isfile(src):
                dst = os.path.join(child_inputs, name)
                shutil.copy2(src, dst)
                copied_inputs.append(dst)

    copied_spec = None
    parent_spec = os.path.join(parent_run_dir, "spec")
    child_spec = _ensure_dir(os.path.join(child_run_dir, "spec"))
    if os.path.exists(parent_spec):
        for name in os.listdir(parent_spec):
            src = os.path.join(parent_spec, name)
            if os.path.isfile(src):
                dst = os.path.join(child_spec, name)
                shutil.copy2(src, dst)
                if copied_spec is None:
                    copied_spec = dst

    # Older/full-flow runs may store the active spec at the run root instead of run_dir/spec/.
    if copied_spec is None:
        spec_name = None
        if parent_meta:
            spec_name = parent_meta.get("spec_file")
        candidate_specs = []
        if spec_name:
            candidate_specs.append(os.path.join(parent_run_dir, spec_name))
        candidate_specs.extend(
            os.path.join(parent_run_dir, name)
            for name in os.listdir(parent_run_dir)
            if name.endswith("_spec.yaml")
        )
        seen = set()
        for src in candidate_specs:
            if src in seen:
                continue
            seen.add(src)
            if os.path.isfile(src):
                dst = os.path.join(child_spec, os.path.basename(src))
                shutil.copy2(src, dst)
                copied_spec = dst
                break
    return copied_inputs, copied_spec


def _copy_retry_constraints(parent_run_dir: str, child_run_dir: str) -> None:
    parent_constraints = os.path.join(parent_run_dir, "constraints.sdc")
    if os.path.exists(parent_constraints):
        shutil.copy2(parent_constraints, os.path.join(child_run_dir, "constraints.sdc"))


def _validate_retry_prerequisites(parent_run_dir: str, start_stage: str) -> Dict[str, str]:
    found: Dict[str, str] = {}
    missing: List[str] = []

    for filename, artifact_key in PD_PREREQ_FILES[start_stage]:
        src = _find_artifact_file(parent_run_dir, "orfs_results", filename)
        if not src:
            missing.append(filename)
            continue
        found[artifact_key] = src

    if missing:
        raise FileNotFoundError(
            f"Missing prerequisite artifacts for retry stage '{start_stage}': {', '.join(missing)}"
        )
    return found


def _copy_retry_prerequisites(parent_run_dir: str, child_run_dir: str, start_stage: str) -> Dict[str, str]:
    parent_results = os.path.join(parent_run_dir, "orfs_results")
    child_results = _ensure_dir(os.path.join(child_run_dir, "orfs_results"))
    copied: Dict[str, str] = {}

    for artifact_key, src in _validate_retry_prerequisites(parent_run_dir, start_stage).items():
        rel = os.path.relpath(src, parent_results)
        dst = os.path.join(child_results, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        copied[artifact_key] = dst

    return copied


def _retry_pd_worker(job_id: str, workspace: str, run_dir: str, args: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    parent_run_id = args["source_run_id"]
    parent_run_dir = get_run_dir(workspace, parent_run_id)
    if not parent_run_dir:
        return {
            "run_id": args["run_id"],
            "job_id": job_id,
            "status": "failed",
            "current_stage": args["start_stage"],
            "check_notes": f"Source run '{parent_run_id}' not found.",
        }

    parent_meta = _read_run_meta(parent_run_dir)
    copied_inputs, copied_spec = _copy_retry_inputs(parent_run_dir, run_dir, parent_meta=parent_meta)
    _copy_retry_constraints(parent_run_dir, run_dir)
    copied_prereqs = _copy_retry_prerequisites(parent_run_dir, run_dir, args["start_stage"])

    auto_checks = GuardrailSummary(
        constraints=parent_meta.get("auto_checks", {}).get("constraints", "pass"),
        signoff="skip",
        equiv="skip",
    )
    stages = _init_stage_metadata()
    for stage in PD_STAGE_SEQUENCE:
        if stage == "constraints":
            stages[stage]["status"] = "completed"
        elif stage in PD_RETRYABLE_STAGES and PD_RETRYABLE_STAGES.index(stage) < PD_RETRYABLE_STAGES.index(args["start_stage"]):
            stages[stage]["status"] = "completed"

    run_meta: Dict[str, Any] = {
        "run_id": args["run_id"],
        "job_id": job_id,
        "created_at": _now_iso(),
        "status": "running",
        "mode": "pd_retry",
        "parent_run_id": parent_run_id,
        "source_run_id": parent_run_id,
        "retry_start_stage": args["start_stage"],
        "retry_max_stage": args["max_stage"],
        "orfs_overrides": args["orfs_overrides"],
        "current_stage": args["start_stage"],
        "platform": args["platform"],
        "top_module": args["top_module"],
        "input_files": [os.path.basename(x) for x in copied_inputs],
        "spec_file": os.path.basename(copied_spec) if copied_spec else None,
        "requested_clock_period_ns": parent_meta.get("requested_clock_period_ns"),
        "effective_clock_period_ns": parent_meta.get("effective_clock_period_ns"),
        "clock_period_ns": parent_meta.get("clock_period_ns"),
        "clock_source": parent_meta.get("clock_source"),
        "constraints_mode": parent_meta.get("constraints_mode", "auto"),
        "utilization": args["utilization"],
        "aspect_ratio": args["aspect_ratio"],
        "core_margin": args["core_margin"],
        "pd_parameters": {
            "utilization": args["utilization"],
            "aspect_ratio": args["aspect_ratio"],
            "core_margin": args["core_margin"],
        },
        "auto_checks": asdict(auto_checks),
        "check_notes": f"Retrying from stage '{args['start_stage']}' through '{args['max_stage']}'.",
        "stages": stages,
        "retry_prerequisites": copied_prereqs,
        "provenance": collect_provenance(
            pdk=args["platform"], num_cores=_pinned_num_cores()
        ).as_dict(),
    }
    run_meta["stages"][args["start_stage"]]["status"] = "running"
    _persist_run_meta(run_dir, run_meta)

    targets = [PD_STAGE_TARGETS[stage] for stage in _stage_range(args["start_stage"], args["max_stage"])]
    docker_result = _run_orfs_targets(
        run_dir=run_dir,
        top_module=args["top_module"],
        platform=args["platform"],
        input_files=copied_inputs,
        utilization=args["utilization"],
        aspect_ratio=args["aspect_ratio"],
        core_margin=args["core_margin"],
        targets=targets,
        timeout=args["timeout"],
        orfs_overrides=args["orfs_overrides"],
    )

    run_meta["docker_command"] = docker_result.get("command")
    run_meta["docker_success"] = docker_result.get("success", False)
    run_meta["docker_stdout_tail"] = (docker_result.get("stdout") or "")[-1200:]
    run_meta["docker_stderr_tail"] = (docker_result.get("stderr") or "")[-1200:]

    signoff = _signoff_guardrail(run_dir, args["top_module"], docker_result)
    auto_checks.signoff = signoff["status"]
    run_meta["auto_checks"] = asdict(auto_checks)
    run_meta["netlist_path"] = _find_netlist(run_dir, args["top_module"])
    # Same shared finalization parser as the full-flow worker (see _job_worker).
    run_meta["summary_metrics"] = _compute_summary_metrics(run_dir, run_meta)
    run_meta["status"] = "completed" if auto_checks.signoff == "pass" else "failed"
    retry_completed_note = (
        signoff["note"]
        if signoff["note"].startswith("ORFS command returned nonzero")
        else "PD retry completed"
    )
    run_meta["check_notes"] = signoff["note"] if auto_checks.signoff != "pass" else retry_completed_note
    run_meta["next_action"] = (
        "Inspect stage summaries and continue tuning." if run_meta["status"] == "completed"
        else "Inspect retry stage logs and adjust parameters."
    )
    run_meta["finished_at"] = _now_iso()
    run_meta["elapsed_sec"] = round(time.time() - start, 2)
    run_meta["current_stage"] = args["max_stage"] if run_meta["status"] == "completed" else args["start_stage"]
    run_meta = _refresh_stage_metadata(run_dir, run_meta, terminal_status=run_meta["status"])

    _persist_run_meta(run_dir, run_meta)
    _append_index(workspace, args["run_id"], job_id, run_meta["status"])
    return run_meta


def _signoff_guardrail(run_dir: str, top_module: str, docker_result: Dict[str, Any]) -> Dict[str, str]:
    artifacts = _collect_artifacts(run_dir)
    if artifacts["reports"] == 0:
        return {"status": "fail", "note": "No ORFS reports found"}

    recovered = False
    if not docker_result.get("success"):
        recovery = _orfs_final_artifacts_are_clean(run_dir, top_module)
        if recovery["status"] != "pass":
            return {"status": "fail", "note": f"ORFS command failed; {recovery['note']}"}
        recovered = True

    log_tail = "\n".join(_collect_log_tail(run_dir, max_lines=120)).lower()
    fatal_patterns = ["error:", "fatal", "failed"]
    if any(p in log_tail for p in fatal_patterns):
        return {"status": "fail", "note": "Fatal pattern detected in synthesis logs"}

    if artifacts["netlists"] == 0:
        return {"status": "fail", "note": "No netlist artifact found"}

    if recovered:
        return {"status": "pass", "note": "ORFS command returned nonzero, but final artifacts and reports are clean"}

    return {"status": "pass", "note": "Signoff artifact/log checks passed"}


def _persist_run_meta(run_dir: str, meta: Dict[str, Any]) -> None:
    _write_json(os.path.join(run_dir, RUN_META_FILENAME), meta)


def _append_index(workspace: str, run_id: str, job_id: str, status: str) -> None:
    with _INDEX_LOCK:
        index = _load_index(workspace)
        index["runs"] = [x for x in index["runs"] if x.get("run_id") != run_id]
        index["jobs"] = [x for x in index["jobs"] if x.get("job_id") != job_id]
        now = _now_iso()
        index["runs"].append({"run_id": run_id, "status": status, "updated_at": now})
        index["jobs"].append({"job_id": job_id, "run_id": run_id, "status": status, "updated_at": now})
        _save_index(workspace, index)
        with open(_latest_path(workspace), "w", encoding="utf-8") as f:
            f.write(run_id)


def _load_stdcell_manifest(workspace: str, platform: str) -> Dict[str, Any]:
    manifest = os.path.join(workspace, "_stdcells", platform, "sim", "manifest.json")
    if not os.path.exists(manifest):
        return {}
    try:
        return _read_json(manifest)
    except Exception:
        return {}


def _job_worker(job_id: str, workspace: str, run_dir: str, args: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    run_id = args["run_id"]
    top_module = args["top_module"]
    platform = args["platform"]

    inputs_dir = _ensure_dir(os.path.join(run_dir, "inputs"))
    copied_inputs = _copy_inputs(args["verilog_files"], inputs_dir)
    copied_spec = _copy_active_spec(workspace, run_dir)

    constraints = _constraints_guardrail(
        workspace,
        run_dir,
        top_module,
        args.get("clock_period_ns"),
        constraints_mode=args.get("constraints_mode", "auto"),
    )
    auto_checks = GuardrailSummary(constraints=constraints["status"], signoff="skip", equiv="skip")

    run_meta: Dict[str, Any] = {
        "run_id": run_id,
        "job_id": job_id,
        "created_at": _now_iso(),
        # Record the configured execution backend up-front so the job-status
        # payload can communicate where this run is executing (e.g. the "remote"
        # VM) while it is still running, not only after artifacts return.
        "backend": _configured_orfs_backend(),
        "status": "running",
        "current_stage": "constraints",
        "platform": platform,
        "top_module": top_module,
        "input_files": [os.path.basename(x) for x in copied_inputs],
        "spec_file": os.path.basename(copied_spec) if copied_spec else None,
        "requested_clock_period_ns": args.get("clock_period_ns"),
        "effective_clock_period_ns": constraints.get("effective_clock_period_ns"),
        "clock_period_ns": constraints.get("clock_period_ns"),
        "clock_source": constraints.get("clock_source"),
        "constraints_mode": args.get("constraints_mode", "auto"),
        "utilization": args["utilization"],
        "aspect_ratio": args["aspect_ratio"],
        "core_margin": args["core_margin"],
        "pd_parameters": {
            "utilization": args["utilization"],
            "aspect_ratio": args["aspect_ratio"],
            "core_margin": args["core_margin"],
        },
        "auto_checks": asdict(auto_checks),
        "check_notes": constraints["note"],
        "stages": _init_stage_metadata(),
        # Reproducibility stamp: repo commit, pinned ORFS image digest, PDK,
        # iverilog version, and the pinned NUM_CORES used for this run.
        "provenance": collect_provenance(
            pdk=platform, num_cores=_pinned_num_cores()
        ).as_dict(),
    }
    run_meta["stages"]["constraints"]["status"] = "running"
    _persist_run_meta(run_dir, run_meta)

    if constraints["status"] != "pass":
        run_meta["status"] = "failed"
        run_meta["current_stage"] = "constraints"
        run_meta["finished_at"] = _now_iso()
        run_meta["elapsed_sec"] = round(time.time() - start, 2)
        run_meta["next_action"] = "Fix spec/clock constraints and rerun synthesis."
        run_meta = _refresh_stage_metadata(run_dir, run_meta, terminal_status="failed")
        _persist_run_meta(run_dir, run_meta)
        _append_index(workspace, run_id, job_id, "failed")
        return run_meta

    run_meta["stages"]["constraints"]["status"] = "completed"
    run_meta["current_stage"] = "synth"
    run_meta["stages"]["synth"]["status"] = "running"
    _persist_run_meta(run_dir, run_meta)

    docker_result = _run_orfs(
        run_dir=run_dir,
        top_module=top_module,
        platform=platform,
        input_files=copied_inputs,
        clock_period_ns=constraints["clock_period_ns"],
        utilization=args["utilization"],
        aspect_ratio=args["aspect_ratio"],
        core_margin=args["core_margin"],
        timeout=args["timeout"],
    )

    run_meta["docker_command"] = docker_result.get("command")
    run_meta["docker_success"] = docker_result.get("success", False)
    run_meta["docker_stdout_tail"] = (docker_result.get("stdout") or "")[-1200:]
    run_meta["docker_stderr_tail"] = (docker_result.get("stderr") or "")[-1200:]

    signoff = _signoff_guardrail(run_dir, top_module, docker_result)
    auto_checks.signoff = signoff["status"]

    netlist_path = _find_netlist(run_dir, top_module)
    run_meta["netlist_path"] = netlist_path

    if args.get("run_equiv") and netlist_path:
        equiv = _run_equiv_check(copied_inputs, netlist_path, top_module)
        auto_checks.equiv = equiv["status"]
        run_meta["equiv_note"] = equiv["note"]
    elif args.get("run_equiv") and not netlist_path:
        auto_checks.equiv = "fail"
        run_meta["equiv_note"] = "No synthesized netlist found for equivalence check"

    run_meta["auto_checks"] = asdict(auto_checks)

    manifest = _load_stdcell_manifest(workspace, platform)
    run_meta["stdcell_manifest_version"] = manifest.get("updated_at") if manifest else None
    run_meta["stdcell_files_used"] = manifest.get("files", []) if manifest else []

    # Finalize PPA via the single shared parser so EVERY backend (local docker,
    # cloud job, remote VM) persists identical summary_metrics: area/cells from
    # synth_stat.txt, WNS/TNS/power from 6_finish.rpt (the targeted parsers handle
    # the "wns max <value>" finish-report format and the 4-column yosys cell row),
    # plus derived fmax_mhz and power_mw. _extract_summary_metrics' broad regex
    # scan missed both cell_count and the "wns max" format, leaving them null.
    run_meta["summary_metrics"] = _compute_summary_metrics(run_dir, run_meta)

    final_ok = auto_checks.signoff == "pass" and auto_checks.constraints == "pass" and auto_checks.equiv != "fail"
    run_meta["status"] = "completed" if final_ok else "failed"
    run_meta["current_stage"] = "finish" if final_ok else _infer_stage(_collect_log_tail(run_dir))
    completed_note = (
        signoff["note"]
        if signoff["note"].startswith("ORFS command returned nonzero")
        else "All guardrails passed"
    )
    run_meta["check_notes"] = signoff["note"] if auto_checks.signoff != "pass" else completed_note
    run_meta["next_action"] = (
        "Use search_logs_tool for detailed PPA/error verification." if run_meta["status"] == "completed"
        else "Use search_logs_tool with error/timing queries and fix RTL/constraints."
    )
    run_meta["finished_at"] = _now_iso()
    run_meta["elapsed_sec"] = round(time.time() - start, 2)
    run_meta = _refresh_stage_metadata(run_dir, run_meta, terminal_status=run_meta["status"])

    _persist_run_meta(run_dir, run_meta)
    _append_index(workspace, run_id, job_id, run_meta["status"])
    return run_meta


def start_synthesis_job(
    workspace: str,
    verilog_files: List[str],
    top_module: str,
    platform: str = "sky130hd",
    clock_period_ns: float = 10.0,
    utilization: int = 5,
    aspect_ratio: float = 1.0,
    core_margin: float = 2.0,
    timeout: int = SYNTH_HARD_TIMEOUT_SEC,
    run_equiv: bool = False,
    constraints_mode: str = "auto",
) -> Dict[str, Any]:
    # Quota gate (hosted): reject before doing any work if the user is over a cap
    # (concurrency / runs-per-day / monthly-compute). No-op in self-host.
    reservation, quota_error = _reserve_synth_quota()
    if quota_error is not None:
        return quota_error

    _ensure_dir(workspace)
    run_id, run_dir = _allocate_run_dir(workspace)
    job_id = f"job_{uuid.uuid4().hex[:10]}"

    # Enforce global safety cap so synthesis jobs do not run unbounded.
    timeout_sec = max(60, min(int(timeout), SYNTH_HARD_TIMEOUT_SEC))

    args = {
        "run_id": run_id,
        "verilog_files": verilog_files,
        "top_module": top_module,
        "platform": platform,
        "clock_period_ns": clock_period_ns,
        "utilization": utilization,
        "aspect_ratio": aspect_ratio,
        "core_margin": core_margin,
        "timeout": timeout_sec,
        "run_equiv": run_equiv,
        "constraints_mode": constraints_mode,
    }

    with _JOB_LOCK:
        future = _submit_with_quota_release(reservation, _job_worker, job_id, workspace, run_dir, args)
        _JOBS[job_id] = {
            "future": future,
            "workspace": workspace,
            "run_id": run_id,
            "run_dir": run_dir,
            "created_at": _now_iso(),
        }

    _append_index(workspace, run_id, job_id, "running")
    return {
        "job_id": job_id,
        "run_id": run_id,
        "status": "queued",
        "stage": "unknown",
        "timeout_sec": timeout_sec,
    }


def retry_pd_job(
    workspace: str,
    source_run_id: str,
    start_stage: str,
    max_stage: str = "finish",
    orfs_overrides_json: str = "",
    timeout: int = SYNTH_HARD_TIMEOUT_SEC,
) -> Dict[str, Any]:
    start_stage = (start_stage or "").strip().lower()
    max_stage = (max_stage or "").strip().lower()
    if start_stage not in PD_RETRYABLE_STAGES:
        return {
            "status": "error",
            "message": f"Unsupported start_stage '{start_stage}'.",
            "supported_stages": PD_RETRYABLE_STAGES,
        }
    if max_stage not in PD_RETRYABLE_STAGES:
        return {
            "status": "error",
            "message": f"Unsupported max_stage '{max_stage}'.",
            "supported_stages": PD_RETRYABLE_STAGES,
        }
    if PD_RETRYABLE_STAGES.index(max_stage) < PD_RETRYABLE_STAGES.index(start_stage):
        return {
            "status": "error",
            "message": "max_stage must be the same as or after start_stage.",
        }

    parent_run_dir = get_run_dir(workspace, source_run_id)
    if not parent_run_dir:
        return {
            "status": "error",
            "message": f"Source run '{source_run_id}' not found.",
        }
    parent_meta = _read_run_meta(parent_run_dir)
    top_module = parent_meta.get("top_module")
    platform = parent_meta.get("platform")
    if not top_module or not platform:
        return {
            "status": "error",
            "message": f"Source run '{source_run_id}' is missing top_module/platform metadata.",
        }
    try:
        orfs_overrides = _parse_orfs_overrides(orfs_overrides_json)
    except ValueError as exc:
        return {"status": "error", "message": str(exc)}

    try:
        _validate_retry_prerequisites(parent_run_dir, start_stage)
    except FileNotFoundError as exc:
        return {"status": "error", "message": str(exc)}

    # A PD retry is a synth run too — same quota gate.
    reservation, quota_error = _reserve_synth_quota()
    if quota_error is not None:
        return quota_error

    pd_parameters = _pd_parameters_from_run(parent_run_dir, parent_meta)
    run_id, run_dir = _allocate_run_dir(workspace)
    job_id = f"job_{uuid.uuid4().hex[:10]}"
    timeout_sec = max(60, min(int(timeout), SYNTH_HARD_TIMEOUT_SEC))
    args = {
        "run_id": run_id,
        "source_run_id": source_run_id,
        "start_stage": start_stage,
        "max_stage": max_stage,
        "top_module": top_module,
        "platform": platform,
        "utilization": pd_parameters["utilization"],
        "aspect_ratio": pd_parameters["aspect_ratio"],
        "core_margin": pd_parameters["core_margin"],
        "timeout": timeout_sec,
        "orfs_overrides": orfs_overrides,
    }

    with _JOB_LOCK:
        future = _submit_with_quota_release(reservation, _retry_pd_worker, job_id, workspace, run_dir, args)
        _JOBS[job_id] = {
            "future": future,
            "workspace": workspace,
            "run_id": run_id,
            "run_dir": run_dir,
            "created_at": _now_iso(),
        }

    _append_index(workspace, run_id, job_id, "running")
    return {
        "job_id": job_id,
        "run_id": run_id,
        "status": "queued",
        "stage": start_stage,
        "timeout_sec": timeout_sec,
        "source_run_id": source_run_id,
        "mode": "pd_retry",
    }


def _read_run_meta(run_dir: str) -> Dict[str, Any]:
    path = os.path.join(run_dir, RUN_META_FILENAME)
    if not os.path.exists(path):
        return {}
    try:
        return _read_json(path)
    except Exception:
        return {}


def _recommended_poll_after_sec(job_id: str, status: str, stage: str, last_log_lines: List[str]) -> int:
    if status not in {"queued", "running"}:
        _POLL_BACKOFF_STATE.pop(job_id, None)
        return 0

    state = _POLL_BACKOFF_STATE.get(job_id, {"count": 0})
    state["count"] = int(state.get("count", 0)) + 1
    _POLL_BACKOFF_STATE[job_id] = state

    poll_after = POLL_BACKOFF_START_SEC * (2 ** (state["count"] - 1))
    return min(POLL_BACKOFF_MAX_SEC, max(POLL_BACKOFF_START_SEC, poll_after))


def _elapsed_seconds(meta: Dict[str, Any], status: str) -> Optional[float]:
    """Wall-clock elapsed for a job.

    Once the run is finalized the persisted ``elapsed_sec`` is authoritative; while
    it is still running we compute live elapsed from ``created_at`` so the UI has a
    ticking timer instead of ``null``.
    """
    persisted = meta.get("elapsed_sec")
    if persisted is not None and status in {"completed", "failed"}:
        return persisted
    created = meta.get("created_at")
    if created:
        try:
            started = datetime.fromisoformat(created)
            if started.tzinfo is None:
                started = started.replace(tzinfo=timezone.utc)
            return round((datetime.now(timezone.utc) - started).total_seconds(), 2)
        except Exception:
            pass
    return persisted


def _build_status_response(job_id: str, run_id: str, run_dir: str, status: str, meta: Dict[str, Any], recovered: bool = False) -> Dict[str, Any]:
    last_log_lines = _collect_log_tail(run_dir)
    stage = _infer_stage(last_log_lines)
    poll_after = _recommended_poll_after_sec(job_id, status, stage, last_log_lines)

    next_action = (
        "Use search_logs_tool for detailed PPA/error verification."
        if status == "completed"
        else "Use search_logs_tool with error/timing queries."
        if status == "failed"
        else f"wait/poll (recommended backoff: {poll_after}s)"
    )

    resp = {
        "job_id": job_id,
        "run_id": run_id,
        "status": status,
        "stage": "final" if status in {"completed", "failed"} else stage,
        "current_stage": meta.get("current_stage", stage),
        "stages": meta.get("stages"),
        # Live elapsed while running (computed from created_at), final elapsed
        # once persisted at finalization. So the UI always has a running timer.
        "elapsed_sec": _elapsed_seconds(meta, status),
        "last_log_lines": last_log_lines,
        "artifacts_found": _collect_artifacts(run_dir),
        "summary_metrics": meta.get("summary_metrics"),
        "auto_checks": meta.get("auto_checks", {"constraints": "skip", "signoff": "skip", "equiv": "skip"}),
        "check_notes": meta.get("check_notes", ""),
        "next_action": next_action,
        "poll_after_sec": poll_after,
        "poll_hint": (
            f"Polling backoff for this job: start {POLL_BACKOFF_START_SEC}s, "
            f"double each subsequent poll, cap {POLL_BACKOFF_MAX_SEC}s."
        ),
    }
    # Communicate where this run is executing so the UI can say e.g. "running on
    # remote VM" instead of implying it is local. Additive — existing fields are
    # untouched.
    backend = meta.get("backend") or _configured_orfs_backend()
    resp["backend"] = backend
    resp["remote"] = backend not in ("local_docker", "", None)
    resp["execution_label"] = "remote VM" if resp["remote"] else "local Docker"
    if recovered:
        resp["recovered_from_index"] = True
        if status not in {"completed", "failed"}:
            resp["check_notes"] = (
                (resp["check_notes"] + " | ") if resp["check_notes"] else ""
            ) + "Recovered from disk index; live executor state is not attached in this process."
    return resp


def _with_rate_limit_fields(resp: Dict[str, Any], retry_after_sec: float) -> Dict[str, Any]:
    out = dict(resp)
    out["rate_limited"] = True
    out["retry_after_sec"] = max(0.0, round(retry_after_sec, 2))
    note = out.get("check_notes", "")
    suffix = f"Rate limited: poll again after ~{out['retry_after_sec']}s."
    out["check_notes"] = f"{note} | {suffix}" if note else suffix
    out["next_action"] = f"wait/poll (recommended backoff: {max(1, int(round(retry_after_sec)))}s)"
    out["poll_hint"] = "Honor poll_after_sec/retry_after_sec to avoid excessive polling."
    return out


def _maybe_cache_poll_response(job_id: str, response: Dict[str, Any]) -> None:
    status = response.get("status")
    if status in {"running", "queued"}:
        _POLL_CACHE[job_id] = {"ts": time.time(), "response": dict(response)}
    elif job_id in _POLL_CACHE:
        del _POLL_CACHE[job_id]
    if status not in {"running", "queued"} and job_id in _POLL_BACKOFF_STATE:
        del _POLL_BACKOFF_STATE[job_id]


def _recover_job_from_index(workspace: str, job_id: str) -> Optional[Dict[str, str]]:
    index = _load_index(workspace)
    for item in index.get("jobs", []):
        if item.get("job_id") == job_id:
            run_id = item.get("run_id")
            if not run_id:
                return None
            run_dir = os.path.join(_runs_root(workspace), run_id)
            if not os.path.exists(run_dir):
                return None
            return {"run_id": run_id, "run_dir": run_dir}
    return None


def get_synthesis_job_status(job_id: str, workspace: Optional[str] = None) -> Dict[str, Any]:
    with _JOB_LOCK:
        data = _JOBS.get(job_id)

    if not data:
        if workspace:
            recovered = _recover_job_from_index(workspace, job_id)
            if recovered:
                meta = _read_run_meta(recovered["run_dir"])
                status = meta.get("status", "running")
                return _build_status_response(
                    job_id=job_id,
                    run_id=recovered["run_id"],
                    run_dir=recovered["run_dir"],
                    status=status,
                    meta=meta,
                    recovered=True,
                )
        return {"job_id": job_id, "status": "failed", "check_notes": "Unknown job_id", "next_action": "Start a new synthesis run."}

    future = data["future"]
    run_id = data["run_id"]
    run_dir = data["run_dir"]

    # Throttle aggressive polling while job is non-terminal.
    # Terminal states are never rate-limited.
    if not future.done():
        cached = _POLL_CACHE.get(job_id)
        if cached:
            elapsed = time.time() - cached["ts"]
            if elapsed < POLL_MIN_INTERVAL_SEC:
                return _with_rate_limit_fields(cached["response"], POLL_MIN_INTERVAL_SEC - elapsed)

    meta = _read_run_meta(run_dir)

    if future.running():
        if not meta.get("check_notes"):
            meta["check_notes"] = "Synthesis in progress."
        resp = _build_status_response(job_id, run_id, run_dir, "running", meta)
        _maybe_cache_poll_response(job_id, resp)
        return resp

    if not future.done():
        if not meta.get("check_notes"):
            meta["check_notes"] = "Queued."
        resp = _build_status_response(job_id, run_id, run_dir, "queued", meta)
        _maybe_cache_poll_response(job_id, resp)
        return resp

    try:
        final = future.result()
    except Exception as exc:
        meta["check_notes"] = f"Job execution error: {exc}"
        meta["auto_checks"] = meta.get("auto_checks", {"constraints": "fail", "signoff": "fail", "equiv": "skip"})
        resp = _build_status_response(job_id, run_id, run_dir, "failed", meta)
        _maybe_cache_poll_response(job_id, resp)
        return resp

    final_status = final.get("status", "failed")
    resp = _build_status_response(job_id, run_id, run_dir, final_status, final)
    _maybe_cache_poll_response(job_id, resp)
    return resp


def get_run_dir(workspace: str, run_id: Optional[str]) -> Optional[str]:
    if run_id:
        path = os.path.join(_runs_root(workspace), run_id)
        return path if os.path.exists(path) else None
    latest = _latest_path(workspace)
    if not os.path.exists(latest):
        return None
    with open(latest, "r", encoding="utf-8") as f:
        rid = f.read().strip()
    path = os.path.join(_runs_root(workspace), rid)
    return path if os.path.exists(path) else None


def list_synthesis_runs(workspace: str) -> List[Dict[str, Any]]:
    index = _load_index(workspace)
    items: List[Dict[str, Any]] = []

    runs = sorted(
        index.get("runs", []),
        key=lambda x: x.get("updated_at") or "",
        reverse=True,
    )

    for item in runs:
        run_id = item.get("run_id")
        if not run_id:
            continue
        run_dir = os.path.join(_runs_root(workspace), run_id)
        if not os.path.exists(run_dir):
            continue

        meta = _read_run_meta(run_dir)
        # Self-heal: re-finalize PPA for completed runs whose stored
        # summary_metrics predate the shared finalizer (missing cell_count or the
        # derived fmax_mhz). This repairs historical runs on read without a
        # migration, so the runs list shows correct PPA for old + new runs alike.
        if meta.get("status") == "completed":
            sm = meta.get("summary_metrics") or {}
            if sm.get("cell_count") is None or sm.get("fmax_mhz") is None:
                recomputed = _compute_summary_metrics(run_dir, meta)
                if recomputed.get("cell_count") is not None or recomputed.get("fmax_mhz") is not None:
                    meta["summary_metrics"] = recomputed
                    try:
                        _persist_run_meta(run_dir, meta)
                    except Exception:
                        pass
        report_path = os.path.join(run_dir, "design_report.md")
        items.append(
            {
                "run_id": run_id,
                "status": meta.get("status", item.get("status", "unknown")),
                "updated_at": item.get("updated_at"),
                "created_at": meta.get("created_at"),
                "finished_at": meta.get("finished_at"),
                "top_module": meta.get("top_module"),
                "platform": meta.get("platform"),
                "elapsed_sec": meta.get("elapsed_sec"),
                "summary_metrics": meta.get("summary_metrics"),
                "auto_checks": meta.get("auto_checks"),
                "report_available": os.path.exists(report_path),
                "report_filename": os.path.basename(report_path) if os.path.exists(report_path) else None,
            }
        )

    return items


def _find_report_file(run_dir: str, name: str) -> Optional[str]:
    reports_root = os.path.join(run_dir, "orfs_reports")
    if not os.path.exists(reports_root):
        return None
    for root, _, files in os.walk(reports_root):
        if name in files:
            return os.path.join(root, name)
    return None


def _find_artifact_file(run_dir: str, subdir: str, name: str) -> Optional[str]:
    root_dir = os.path.join(run_dir, subdir)
    if not os.path.exists(root_dir):
        return None
    for root, _, files in os.walk(root_dir):
        if name in files:
            return os.path.join(root, name)
    return None


_STAGE_REPORT_CANDIDATES: Dict[str, List[tuple[str, str]]] = {
    "floorplan": [("orfs_reports", "2_floorplan_final.rpt")],
    "place": [("orfs_logs", "3_3_place_gp.json")],
    "placement": [("orfs_logs", "3_3_place_gp.json")],
    "cts": [("orfs_reports", "4_cts_final.rpt")],
    "grt": [("orfs_reports", "congestion.rpt")],
    "global_route": [("orfs_reports", "congestion.rpt")],
    "route": [("orfs_reports", "5_route_drc.rpt")],
    "finish": [("orfs_reports", "6_finish.rpt")],
    "final": [("orfs_reports", "6_finish.rpt")],
}


def read_stage_report(workspace: str, stage: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    run_dir = get_run_dir(workspace, run_id)
    requested_stage = (stage or "").strip().lower()
    if run_dir is None:
        return {
            "status": "error",
            "message": f"Run '{run_id}' not found." if run_id else "No synthesis run found.",
            "run_id": run_id,
            "stage": requested_stage or stage,
        }

    if requested_stage not in _STAGE_REPORT_CANDIDATES:
        return {
            "status": "error",
            "message": f"Unsupported stage '{stage}'.",
            "supported_stages": sorted(_STAGE_REPORT_CANDIDATES.keys()),
            "run_id": run_id,
            "stage": requested_stage or stage,
        }

    selected_path = None
    selected_scope = None
    selected_name = None
    checked = []
    for scope, filename in _STAGE_REPORT_CANDIDATES[requested_stage]:
        checked.append({"scope": scope, "filename": filename})
        selected_path = _find_artifact_file(run_dir, scope, filename)
        if selected_path:
            selected_scope = scope
            selected_name = filename
            break

    run_meta = _load_run_meta_with_inferred_stages(run_dir)
    resolved_run_id = run_meta.get("run_id") or os.path.basename(run_dir)
    if not selected_path:
        return {
            "status": "error",
            "message": f"No report artifact found for stage '{requested_stage}'.",
            "run_id": resolved_run_id,
            "top_module": run_meta.get("top_module"),
            "platform": run_meta.get("platform"),
            "stage": requested_stage,
            "checked_candidates": checked,
        }

    try:
        with open(selected_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to read stage artifact: {exc}",
            "run_id": resolved_run_id,
            "top_module": run_meta.get("top_module"),
            "platform": run_meta.get("platform"),
            "stage": requested_stage,
            "artifact_path": selected_path,
            "artifact_scope": selected_scope,
            "artifact_name": selected_name,
        }

    max_chars = 12000
    excerpt = content[:max_chars]
    return {
        "status": "ok",
        "run_id": resolved_run_id,
        "top_module": run_meta.get("top_module"),
        "platform": run_meta.get("platform"),
        "stage": requested_stage,
        "artifact_scope": selected_scope,
        "artifact_name": selected_name,
        "artifact_path": selected_path,
        "content_excerpt": excerpt,
        "content_truncated": len(content) > max_chars,
        "content_length": len(content),
        "checked_candidates": checked,
    }


def get_route_drc_summary(workspace: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    run_dir = get_run_dir(workspace, run_id)
    if run_dir is None:
        return {
            "status": "error",
            "message": f"Run '{run_id}' not found." if run_id else "No synthesis run found.",
            "run_id": run_id,
            "stage": "route",
        }

    report_path = _find_report_file(run_dir, "5_route_drc.rpt")
    run_meta = _load_run_meta_with_inferred_stages(run_dir)
    resolved_run_id = run_meta.get("run_id") or os.path.basename(run_dir)
    if not report_path:
        return {
            "status": "error",
            "message": "5_route_drc.rpt not found.",
            "run_id": resolved_run_id,
            "top_module": run_meta.get("top_module"),
            "platform": run_meta.get("platform"),
            "stage": "route",
        }

    try:
        with open(report_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = [line.rstrip("\n") for line in f.readlines()]
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to read route DRC report: {exc}",
            "run_id": resolved_run_id,
            "top_module": run_meta.get("top_module"),
            "platform": run_meta.get("platform"),
            "stage": "route",
            "report_path": report_path,
        }

    nonempty = [line.strip() for line in lines if line.strip()]
    unique_entries: List[str] = []
    seen = set()
    for entry in nonempty:
        if entry not in seen:
            unique_entries.append(entry)
            seen.add(entry)

    route_stage = run_meta.get("stages", {}).get("route", {})
    route_completed = route_stage.get("status") == "completed"
    clean = len(nonempty) == 0 and route_completed
    notes = []
    if len(nonempty) == 0 and route_completed:
        notes.append("Empty 5_route_drc.rpt with completed route stage indicates no final route DRC entries.")
    elif len(nonempty) == 0:
        notes.append("Empty 5_route_drc.rpt is not treated as clean because route stage is not completed.")
    return {
        "status": "ok",
        "run_id": resolved_run_id,
        "top_module": run_meta.get("top_module"),
        "platform": run_meta.get("platform"),
        "stage": "route",
        "route_stage_status": route_stage.get("status"),
        "report_path": report_path,
        "line_count": len(lines),
        "violation_count": len(nonempty),
        "unique_violation_count": len(unique_entries),
        "clean": clean,
        "sample_violations": unique_entries[:20],
        "notes": notes,
    }


def get_cts_summary(workspace: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    run_dir = get_run_dir(workspace, run_id)
    if run_dir is None:
        return {
            "status": "error",
            "message": f"Run '{run_id}' not found." if run_id else "No synthesis run found.",
            "run_id": run_id,
            "stage": "cts",
        }

    report_path = _find_report_file(run_dir, "4_cts_final.rpt")
    run_meta = _load_run_meta_with_inferred_stages(run_dir)
    resolved_run_id = run_meta.get("run_id") or os.path.basename(run_dir)
    if not report_path:
        return {
            "status": "error",
            "message": "4_cts_final.rpt not found.",
            "run_id": resolved_run_id,
            "top_module": run_meta.get("top_module"),
            "platform": run_meta.get("platform"),
            "stage": "cts",
        }

    try:
        with open(report_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to read CTS report: {exc}",
            "run_id": resolved_run_id,
            "top_module": run_meta.get("top_module"),
            "platform": run_meta.get("platform"),
            "stage": "cts",
            "report_path": report_path,
        }

    def _mfloat(pattern: str) -> Optional[float]:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if not match:
            return None
        try:
            return float(match.group(1))
        except Exception:
            return None

    def _mint(pattern: str) -> Optional[int]:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if not match:
            return None
        try:
            return int(match.group(1))
        except Exception:
            return None

    summary = {
        "wns_ns": _mfloat(r"^\s*wns\s+max\s+([0-9.eE+-]+)"),
        "tns_ns": _mfloat(r"^\s*tns\s+max\s+([0-9.eE+-]+)"),
        "worst_slack_ns": _mfloat(r"^\s*worst\s+slack\s+max\s+([0-9.eE+-]+)"),
        "clock_period_min_ns": _mfloat(r"period_min\s*=\s*([0-9.eE+-]+)"),
        "clock_fmax_mhz": _mfloat(r"fmax\s*=\s*([0-9.eE+-]+)"),
        "setup_skew_ns": _mfloat(r"^\s*([0-9.eE+-]+)\s+setup\s+skew\s*$"),
        "max_slew_violation_count": _mint(r"max_slew_violation_count\s*-+\s*([0-9]+)"),
        "max_fanout_violation_count": _mint(r"max_fanout_violation_count\s*-+\s*([0-9]+)"),
        "max_cap_violation_count": _mint(r"max_cap_violation_count\s*-+\s*([0-9]+)"),
        "setup_violation_count": _mint(r"setup_violation_count\s*-+\s*([0-9]+)"),
        "hold_violation_count": _mint(r"hold_violation_count\s*-+\s*([0-9]+)"),
        "critical_path_delay_ns": _mfloat(r"critical\s+path\s+delay\s*-+\s*([0-9.eE+-]+)"),
        "critical_path_slack_ns": _mfloat(r"critical\s+path\s+slack\s*-+\s*([0-9.eE+-]+)"),
        "slack_over_delay_ratio": _mfloat(r"slack\s+div\s+critical\s+path\s+delay\s*-+\s*([0-9.eE+-]+)"),
    }

    startpoints = re.findall(r"^Startpoint:\s+(.+)$", text, re.MULTILINE)
    endpoints = re.findall(r"^Endpoint:\s+(.+)$", text, re.MULTILINE)
    clock_names = re.findall(r"^Clock\s+(\S+)\s*$", text, re.MULTILINE)

    return {
        "status": "ok",
        "run_id": resolved_run_id,
        "top_module": run_meta.get("top_module"),
        "platform": run_meta.get("platform"),
        "stage": "cts",
        "report_path": report_path,
        "clock_names": clock_names,
        "startpoint_count": len(startpoints),
        "endpoint_count": len(endpoints),
        "sample_startpoints": startpoints[:5],
        "sample_endpoints": endpoints[:5],
        "summary": summary,
    }


def get_congestion_summary(workspace: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    run_dir = get_run_dir(workspace, run_id)
    if run_dir is None:
        return {
            "status": "error",
            "message": f"Run '{run_id}' not found." if run_id else "No synthesis run found.",
            "run_id": run_id,
            "stage": "grt",
        }

    run_meta = _load_run_meta_with_inferred_stages(run_dir)
    resolved_run_id = run_meta.get("run_id") or os.path.basename(run_dir)

    artifact_path = _find_artifact_file(run_dir, "orfs_reports", "congestion.rpt")
    artifact_scope = "orfs_reports"
    if not artifact_path:
        artifact_path = _find_artifact_file(run_dir, "orfs_logs", "5_1_grt.log")
        artifact_scope = "orfs_logs"

    if not artifact_path:
        return {
            "status": "error",
            "message": "Neither congestion.rpt nor 5_1_grt.log was found.",
            "run_id": resolved_run_id,
            "top_module": run_meta.get("top_module"),
            "platform": run_meta.get("platform"),
            "stage": "grt",
        }

    try:
        with open(artifact_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to read congestion artifact: {exc}",
            "run_id": resolved_run_id,
            "top_module": run_meta.get("top_module"),
            "platform": run_meta.get("platform"),
            "stage": "grt",
            "artifact_path": artifact_path,
        }

    layer_rows = []
    row_re = re.compile(
        r"^(?P<layer>\S+)\s+"
        r"(?P<resource>[0-9]+)\s+"
        r"(?P<demand>[0-9]+)\s+"
        r"(?P<usage>[0-9.]+)%\s+"
        r"(?P<max_h>[0-9]+)\s*/\s*(?P<max_v>[0-9]+)\s*/\s*(?P<overflow>[0-9]+)\s*$",
        re.MULTILINE,
    )
    for match in row_re.finditer(text):
        layer = match.group("layer")
        if layer.lower() == "total":
            continue
        layer_rows.append(
            {
                "layer": layer,
                "resource": int(match.group("resource")),
                "demand": int(match.group("demand")),
                "usage_pct": float(match.group("usage")),
                "max_h_overflow": int(match.group("max_h")),
                "max_v_overflow": int(match.group("max_v")),
                "total_overflow": int(match.group("overflow")),
            }
        )

    total_match = re.search(
        r"^Total\s+([0-9]+)\s+([0-9]+)\s+([0-9.]+)%\s+([0-9]+)\s*/\s*([0-9]+)\s*/\s*([0-9]+)\s*$",
        text,
        re.MULTILINE,
    )

    total = None
    if total_match:
        total = {
            "resource": int(total_match.group(1)),
            "demand": int(total_match.group(2)),
            "usage_pct": float(total_match.group(3)),
            "max_h_overflow": int(total_match.group(4)),
            "max_v_overflow": int(total_match.group(5)),
            "total_overflow": int(total_match.group(6)),
        }

    wirelength_um = None
    routed_nets = None
    wire_m = re.search(r"Total wirelength:\s*([0-9.eE+-]+)\s*um", text)
    if wire_m:
        try:
            wirelength_um = float(wire_m.group(1))
        except Exception:
            pass
    nets_m = re.search(r"Routed nets:\s*([0-9]+)", text)
    if nets_m:
        try:
            routed_nets = int(nets_m.group(1))
        except Exception:
            pass

    congested_layers = [row["layer"] for row in layer_rows if row["total_overflow"] > 0]
    return {
        "status": "ok",
        "run_id": resolved_run_id,
        "top_module": run_meta.get("top_module"),
        "platform": run_meta.get("platform"),
        "stage": "grt",
        "artifact_scope": artifact_scope,
        "artifact_path": artifact_path,
        "layer_count": len(layer_rows),
        "layers": layer_rows,
        "total": total,
        "wirelength_um": wirelength_um,
        "routed_nets": routed_nets,
        "has_overflow": bool(total and total["total_overflow"] > 0),
        "congested_layers": congested_layers,
    }


def _numeric_comparison(parent_value: Any, child_value: Any, better_when: str) -> Dict[str, Any]:
    out = {
        "parent": parent_value,
        "child": child_value,
        "delta": None,
        "percent_delta": None,
        "classification": "missing",
        "better_when": better_when,
    }
    if not isinstance(parent_value, (int, float)) or not isinstance(child_value, (int, float)):
        return out

    delta = child_value - parent_value
    out["delta"] = delta
    if parent_value != 0:
        out["percent_delta"] = (delta / abs(parent_value)) * 100.0

    if abs(delta) < 1e-12:
        out["classification"] = "unchanged"
    elif better_when == "higher":
        out["classification"] = "improved" if delta > 0 else "regressed"
    elif better_when == "lower":
        out["classification"] = "improved" if delta < 0 else "regressed"
    else:
        out["classification"] = "unknown"
    return out


def _violation_total(violations: Dict[str, Any]) -> Optional[int]:
    if not isinstance(violations, dict):
        return None
    values = [v for v in violations.values() if isinstance(v, int)]
    if not values:
        return None
    return sum(values)


def compare_pd_runs(
    workspace: str,
    child_run_id: str,
    parent_run_id: Optional[str] = None,
) -> Dict[str, Any]:
    child_dir = get_run_dir(workspace, child_run_id)
    if child_dir is None:
        return {
            "status": "error",
            "message": f"Child run '{child_run_id}' not found.",
            "child_run_id": child_run_id,
            "parent_run_id": parent_run_id,
        }

    child_meta = _read_run_meta(child_dir)
    resolved_child_id = child_meta.get("run_id") or os.path.basename(child_dir)
    resolved_parent_id = parent_run_id or child_meta.get("parent_run_id") or child_meta.get("source_run_id")
    if not resolved_parent_id:
        return {
            "status": "error",
            "message": "parent_run_id is required when the child run has no parent_run_id/source_run_id metadata.",
            "child_run_id": resolved_child_id,
            "parent_run_id": parent_run_id,
        }

    parent_dir = get_run_dir(workspace, resolved_parent_id)
    if parent_dir is None:
        return {
            "status": "error",
            "message": f"Parent run '{resolved_parent_id}' not found.",
            "child_run_id": resolved_child_id,
            "parent_run_id": resolved_parent_id,
        }

    parent_meta = _read_run_meta(parent_dir)
    parent_metrics = get_synthesis_metrics(workspace=workspace, run_id=resolved_parent_id)
    child_metrics = get_synthesis_metrics(workspace=workspace, run_id=resolved_child_id)
    if parent_metrics.get("status") != "ok" or child_metrics.get("status") != "ok":
        return {
            "status": "error",
            "message": "Unable to read metrics for one or both runs.",
            "parent_run_id": resolved_parent_id,
            "child_run_id": resolved_child_id,
            "parent_metrics_status": parent_metrics.get("status"),
            "child_metrics_status": child_metrics.get("status"),
        }

    parent_values = parent_metrics.get("metrics", {})
    child_values = child_metrics.get("metrics", {})
    metric_preferences = {
        "wns_ns": "higher",
        "tns_ns": "higher",
        "area_um2": "lower",
        "cell_count": "lower",
        "power_uw": "lower",
    }
    comparisons = {
        name: _numeric_comparison(parent_values.get(name), child_values.get(name), better_when)
        for name, better_when in metric_preferences.items()
    }

    parent_violation_total = _violation_total(parent_metrics.get("violations", {}))
    child_violation_total = _violation_total(child_metrics.get("violations", {}))
    comparisons["timing_violation_total"] = _numeric_comparison(
        parent_violation_total,
        child_violation_total,
        "lower",
    )

    parent_drc = get_route_drc_summary(workspace=workspace, run_id=resolved_parent_id)
    child_drc = get_route_drc_summary(workspace=workspace, run_id=resolved_child_id)
    route_drc_comparison = None
    if parent_drc.get("status") == "ok" and child_drc.get("status") == "ok":
        route_drc_comparison = {
            "violation_count": _numeric_comparison(
                parent_drc.get("violation_count"),
                child_drc.get("violation_count"),
                "lower",
            ),
            "parent_clean": parent_drc.get("clean"),
            "child_clean": child_drc.get("clean"),
        }

    parent_congestion = get_congestion_summary(workspace=workspace, run_id=resolved_parent_id)
    child_congestion = get_congestion_summary(workspace=workspace, run_id=resolved_child_id)
    congestion_comparison = None
    if parent_congestion.get("status") == "ok" and child_congestion.get("status") == "ok":
        parent_total = parent_congestion.get("total") or {}
        child_total = child_congestion.get("total") or {}
        congestion_comparison = {
            "total_overflow": _numeric_comparison(
                parent_total.get("total_overflow"),
                child_total.get("total_overflow"),
                "lower",
            ),
            "usage_pct": _numeric_comparison(
                parent_total.get("usage_pct"),
                child_total.get("usage_pct"),
                "lower",
            ),
            "wirelength_um": _numeric_comparison(
                parent_congestion.get("wirelength_um"),
                child_congestion.get("wirelength_um"),
                "lower",
            ),
            "parent_congested_layers": parent_congestion.get("congested_layers", []),
            "child_congested_layers": child_congestion.get("congested_layers", []),
        }

    improved = [name for name, item in comparisons.items() if item.get("classification") == "improved"]
    regressed = [name for name, item in comparisons.items() if item.get("classification") == "regressed"]
    if route_drc_comparison:
        cls = route_drc_comparison["violation_count"].get("classification")
        if cls == "improved":
            improved.append("route_drc_violation_count")
        elif cls == "regressed":
            regressed.append("route_drc_violation_count")
    if congestion_comparison:
        cls = congestion_comparison["total_overflow"].get("classification")
        if cls == "improved":
            improved.append("congestion_total_overflow")
        elif cls == "regressed":
            regressed.append("congestion_total_overflow")

    child_wns = child_values.get("wns_ns")
    child_tns = child_values.get("tns_ns")
    timing_closed = (
        isinstance(child_wns, (int, float))
        and child_wns >= 0
        and (child_tns is None or child_tns >= 0)
    )
    route_clean = child_drc.get("clean") if child_drc.get("status") == "ok" else None
    signoff_clean = bool(timing_closed and route_clean is True)

    if signoff_clean and not regressed:
        verdict = "closed"
    elif signoff_clean:
        verdict = "closed_with_tradeoffs"
    elif improved and not regressed:
        verdict = "improved"
    elif improved and regressed:
        verdict = "mixed"
    elif regressed:
        verdict = "regressed"
    else:
        verdict = "neutral"

    return {
        "status": "ok",
        "parent_run_id": resolved_parent_id,
        "child_run_id": resolved_child_id,
        "top_module": child_meta.get("top_module") or parent_meta.get("top_module"),
        "platform": child_meta.get("platform") or parent_meta.get("platform"),
        "lineage": {
            "child_mode": child_meta.get("mode"),
            "retry_start_stage": child_meta.get("retry_start_stage"),
            "retry_max_stage": child_meta.get("retry_max_stage"),
            "orfs_overrides": child_meta.get("orfs_overrides", {}),
        },
        "verdict": verdict,
        "signoff_clean": signoff_clean,
        "timing_closed": timing_closed,
        "route_clean": route_clean,
        "improved_metrics": improved,
        "regressed_metrics": regressed,
        "comparisons": comparisons,
        "route_drc_comparison": route_drc_comparison,
        "congestion_comparison": congestion_comparison,
        "parent_complete": parent_metrics.get("complete"),
        "child_complete": child_metrics.get("complete"),
        "notes": [
            "Positive WNS/TNS deltas are better; negative area/cell/power/DRC/congestion deltas are better.",
            "Use this as a retry triage summary; detailed diagnosis still comes from stage-specific reports.",
        ],
    }


def get_stage_status(workspace: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    run_dir = get_run_dir(workspace, run_id)
    if run_dir is None:
        return {
            "status": "error",
            "message": f"Run '{run_id}' not found." if run_id else "No synthesis run found.",
            "run_id": run_id,
        }

    run_meta = _load_run_meta_with_inferred_stages(run_dir)
    resolved_run_id = run_meta.get("run_id") or os.path.basename(run_dir)
    stages = run_meta.get("stages", {})
    completed = [name for name, item in stages.items() if item.get("status") == "completed"]
    failed = [name for name, item in stages.items() if item.get("status") == "failed"]
    running = [name for name, item in stages.items() if item.get("status") == "running"]
    pending = [name for name, item in stages.items() if item.get("status") == "pending"]

    return {
        "status": "ok",
        "run_id": resolved_run_id,
        "top_module": run_meta.get("top_module"),
        "platform": run_meta.get("platform"),
        "run_status": run_meta.get("status"),
        "current_stage": run_meta.get("current_stage"),
        "stages": stages,
        "completed_stages": completed,
        "failed_stages": failed,
        "running_stages": running,
        "pending_stages": pending,
        "stage_count": len(stages),
        "elapsed_sec": run_meta.get("elapsed_sec"),
    }


def _parse_finish_report(path: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "wns_ns": None,
        "tns_ns": None,
        "power_uw": None,
        "violations": {
            "setup": None,
            "hold": None,
            "max_slew": None,
            "max_cap": None,
            "max_fanout": None,
        },
    }
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return out

    def _mfloat(pattern: str) -> Optional[float]:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    def _mint(pattern: str) -> Optional[int]:
        m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if not m:
            return None
        try:
            return int(m.group(1))
        except Exception:
            return None

    out["wns_ns"] = _mfloat(r"^\s*wns\s+max\s+([0-9.eE+-]+)")
    out["tns_ns"] = _mfloat(r"^\s*tns\s+max\s+([0-9.eE+-]+)")
    out["violations"]["setup"] = _mint(r"setup\s+violation\s+count\s+([0-9]+)")
    out["violations"]["hold"] = _mint(r"hold\s+violation\s+count\s+([0-9]+)")
    out["violations"]["max_slew"] = _mint(r"max\s+slew\s+violation\s+count\s+([0-9]+)")
    out["violations"]["max_cap"] = _mint(r"max\s+cap\s+violation\s+count\s+([0-9]+)")
    out["violations"]["max_fanout"] = _mint(r"max\s+fanout\s+violation\s+count\s+([0-9]+)")

    # Power table line shape:
    # Total <internal> <switching> <leakage> <total> 100.0%
    total_w = _mfloat(r"^\s*Total\s+[0-9.eE+-]+\s+[0-9.eE+-]+\s+[0-9.eE+-]+\s+([0-9.eE+-]+)\s+100")
    if total_w is not None:
        out["power_uw"] = total_w * 1e6
    return out


def _parse_synth_stat(path: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"area_um2": None, "cell_count": None}
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return out

    area_m = re.search(r"Chip area for module .*:\s*([0-9.]+)", text, re.IGNORECASE)
    if area_m:
        try:
            out["area_um2"] = float(area_m.group(1))
        except Exception:
            pass

    # The yosys/ORFS stat summary row that reports the total cell count comes in
    # two shapes depending on the flow version:
    #   * old/abbreviated:  "814 7.33E+03 cells"   (count, area, "cells")
    #   * real ORFS output: "37  339.075  37  339.075 cells"
    #                       (count, area, local-count, local-area, "cells")
    # The total cell count is always the FIRST integer on the line that ends in
    # the bare word "cells" (the per-cell breakdown lines below it end in a cell
    # name, not "cells", so they are not matched).
    cells_m = re.search(r"^\s*([0-9]+)\b.*\bcells\s*$", text, re.IGNORECASE | re.MULTILINE)
    if cells_m:
        try:
            out["cell_count"] = int(cells_m.group(1))
        except Exception:
            pass
    return out


def _derive_fmax_mhz(clock_period_ns: Optional[float], wns_ns: Optional[float]) -> Optional[float]:
    """Achievable Fmax = 1000 / (clock_period_ns - wns_ns).

    WNS is the worst negative slack: positive slack means timing met with margin
    (the clock could be tightened by WNS), negative means the period must grow by
    |WNS|. Either way the achieved period is ``clock_period_ns - wns_ns``.
    """
    try:
        if clock_period_ns is None or wns_ns is None:
            return None
        achieved_period = float(clock_period_ns) - float(wns_ns)
        if achieved_period <= 0:
            return None
        return round(1000.0 / achieved_period, 2)
    except Exception:
        return None


def _compute_summary_metrics(run_dir: str, run_meta: Dict[str, Any]) -> Dict[str, Any]:
    """Parse PPA from on-disk ORFS reports into the canonical summary_metrics shape.

    This is the SINGLE finalization parser shared by every backend (local docker,
    cloud job, remote VM) and by the PD-retry path, so a successful run is
    finalized identically regardless of where ORFS actually executed. It reuses
    the targeted ``_parse_synth_stat`` / ``_parse_finish_report`` parsers (which
    handle the "wns max <value>" finish-report format and the 4-column yosys cell
    row), derives Fmax from the effective clock period and WNS, and exposes power
    in both micro- and milliwatts.
    """
    finish_path = _find_report_file(run_dir, "6_finish.rpt")
    stat_path = _find_report_file(run_dir, "synth_stat.txt")
    finish_data = _parse_finish_report(finish_path) if finish_path else {}
    stat_data = _parse_synth_stat(stat_path) if stat_path else {}

    wns_ns = finish_data.get("wns_ns")
    clock_period_ns = (
        run_meta.get("effective_clock_period_ns")
        or run_meta.get("clock_period_ns")
        or run_meta.get("requested_clock_period_ns")
    )
    power_uw = finish_data.get("power_uw")
    power_mw = round(power_uw / 1000.0, 6) if power_uw is not None else None

    return {
        "area_um2": stat_data.get("area_um2"),
        "cell_count": stat_data.get("cell_count"),
        "wns_ns": wns_ns,
        "tns_ns": finish_data.get("tns_ns"),
        "power_uw": power_uw,
        "power_mw": power_mw,
        "fmax_mhz": _derive_fmax_mhz(clock_period_ns, wns_ns),
    }


def get_synthesis_metrics(workspace: str, run_id: Optional[str] = None) -> Dict[str, Any]:
    run_dir = get_run_dir(workspace, run_id)
    if run_dir is None:
        return {
            "status": "error",
            "message": f"Run '{run_id}' not found." if run_id else "No synthesis run found.",
            "run_id": run_id,
            "complete": False,
        }

    finish = _find_report_file(run_dir, "6_finish.rpt")
    stat = _find_report_file(run_dir, "synth_stat.txt")
    finish_data = _parse_finish_report(finish) if finish else {}
    stat_data = _parse_synth_stat(stat) if stat else {}

    run_meta = _read_run_meta(run_dir)
    clock_period_ns = (
        run_meta.get("effective_clock_period_ns")
        or run_meta.get("clock_period_ns")
        or run_meta.get("requested_clock_period_ns")
    )
    power_uw = finish_data.get("power_uw")
    wns_ns = finish_data.get("wns_ns")
    metrics = {
        "area_um2": stat_data.get("area_um2"),
        "cell_count": stat_data.get("cell_count"),
        "wns_ns": wns_ns,
        "tns_ns": finish_data.get("tns_ns"),
        "power_uw": power_uw,
        "power_mw": round(power_uw / 1000.0, 6) if power_uw is not None else None,
        "fmax_mhz": _derive_fmax_mhz(clock_period_ns, wns_ns),
    }
    sources = {
        "area_um2": stat,
        "cell_count": stat,
        "wns_ns": finish,
        "tns_ns": finish,
        "power_uw": finish,
        "power_mw": finish,
        "fmax_mhz": finish,
    }
    # Completeness is judged on the core PPA fields; fmax/power_mw are derived
    # and may legitimately be absent without the run being "incomplete".
    core = ("area_um2", "cell_count", "wns_ns", "tns_ns", "power_uw")
    missing = [k for k in core if metrics.get(k) is None]
    notes = []
    if not finish:
        notes.append("6_finish.rpt not found")
    if not stat:
        notes.append("synth_stat.txt not found")

    return {
        "status": "ok",
        "run_id": run_meta.get("run_id") or os.path.basename(run_dir),
        "top_module": run_meta.get("top_module"),
        "platform": run_meta.get("platform"),
        "metrics": metrics,
        "violations": finish_data.get("violations", {}),
        "sources": sources,
        "complete": len(missing) == 0,
        "missing_fields": missing,
        "parse_notes": notes,
    }
