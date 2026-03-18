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

RUNS_DIRNAME = "synth_runs"
INDEX_FILENAME = "index.json"
LATEST_FILENAME = "LATEST"
RUN_META_FILENAME = "run_meta.json"

_JOB_LOCK = threading.Lock()
_EXECUTOR = ThreadPoolExecutor(max_workers=2)
_JOBS: Dict[str, Dict[str, Any]] = {}
_POLL_CACHE: Dict[str, Dict[str, Any]] = {}
_POLL_BACKOFF_STATE: Dict[str, Dict[str, Any]] = {}

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
        "clock_period_ns": fallback_clock_period_ns,
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
        period = spec.clock_period_ns if spec.clock_period_ns > 0 else (fallback_clock_period_ns or 10.0)
        sdc_path = os.path.join(run_dir, "constraints.sdc")
        _write_default_sdc(sdc_path=sdc_path, clock_period_ns=period, clock_port=fallback_port)
        result.update({
            "status": "pass",
            "note": f"No explicit clock in spec. Applied default clock fallback on port '{fallback_port}'.",
            "sdc_path": sdc_path,
            "clock_period_ns": period,
        })
        return result

    if spec.clock_period_ns <= 0:
        result["note"] = "Spec clock period must be > 0."
        return result

    sdc_content = spec.generate_sdc()
    if "create_clock" not in sdc_content:
        result["note"] = "Generated SDC missing create_clock."
        return result

    sdc_path = os.path.join(run_dir, "constraints.sdc")
    with open(sdc_path, "w", encoding="utf-8") as f:
        f.write(sdc_content)

    result.update({
        "status": "pass",
        "note": "Spec-driven constraints validated.",
        "sdc_path": sdc_path,
        "clock_period_ns": spec.clock_period_ns,
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
    )
    with open(config_mk, "w", encoding="utf-8") as f:
        f.write(config)

    volumes = [
        f"{results_dir}:/OpenROAD-flow-scripts/flow/results",
        f"{logs_dir}:/OpenROAD-flow-scripts/flow/logs",
        f"{reports_dir}:/OpenROAD-flow-scripts/flow/reports",
    ]

    return run_docker_command(
        command="make -B DESIGN_CONFIG=/workspace/config.mk",
        workspace_path=run_dir,
        volumes=volumes,
        timeout=timeout,
    )


def _signoff_guardrail(run_dir: str, top_module: str, docker_result: Dict[str, Any]) -> Dict[str, str]:
    if not docker_result.get("success"):
        return {"status": "fail", "note": "ORFS command failed"}

    artifacts = _collect_artifacts(run_dir)
    if artifacts["reports"] == 0:
        return {"status": "fail", "note": "No ORFS reports found"}

    log_tail = "\n".join(_collect_log_tail(run_dir, max_lines=120)).lower()
    fatal_patterns = ["error:", "fatal", "failed"]
    if any(p in log_tail for p in fatal_patterns):
        return {"status": "fail", "note": "Fatal pattern detected in synthesis logs"}

    if artifacts["netlists"] == 0:
        return {"status": "fail", "note": "No netlist artifact found"}

    return {"status": "pass", "note": "Signoff artifact/log checks passed"}


def _persist_run_meta(run_dir: str, meta: Dict[str, Any]) -> None:
    _write_json(os.path.join(run_dir, RUN_META_FILENAME), meta)


def _append_index(workspace: str, run_id: str, job_id: str, status: str) -> None:
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
        "status": "running",
        "platform": platform,
        "top_module": top_module,
        "input_files": [os.path.basename(x) for x in copied_inputs],
        "clock_period_ns": constraints.get("clock_period_ns"),
        "constraints_mode": args.get("constraints_mode", "auto"),
        "auto_checks": asdict(auto_checks),
        "check_notes": constraints["note"],
    }
    _persist_run_meta(run_dir, run_meta)

    if constraints["status"] != "pass":
        run_meta["status"] = "failed"
        run_meta["finished_at"] = _now_iso()
        run_meta["elapsed_sec"] = round(time.time() - start, 2)
        run_meta["next_action"] = "Fix spec/clock constraints and rerun synthesis."
        _persist_run_meta(run_dir, run_meta)
        _append_index(workspace, run_id, job_id, "failed")
        return run_meta

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

    summary_metrics = _extract_summary_metrics(run_dir)
    run_meta["summary_metrics"] = summary_metrics

    final_ok = docker_result.get("success", False) and auto_checks.signoff == "pass" and auto_checks.constraints == "pass" and auto_checks.equiv != "fail"
    run_meta["status"] = "completed" if final_ok else "failed"
    run_meta["check_notes"] = signoff["note"] if auto_checks.signoff != "pass" else "All guardrails passed"
    run_meta["next_action"] = (
        "Use search_logs_tool for detailed PPA/error verification." if run_meta["status"] == "completed"
        else "Use search_logs_tool with error/timing queries and fix RTL/constraints."
    )
    run_meta["finished_at"] = _now_iso()
    run_meta["elapsed_sec"] = round(time.time() - start, 2)

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
    _ensure_dir(workspace)
    run_id = _next_run_id(workspace)
    run_dir = _ensure_dir(os.path.join(_runs_root(workspace), run_id))
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
        future = _EXECUTOR.submit(_job_worker, job_id, workspace, run_dir, args)
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
        "elapsed_sec": meta.get("elapsed_sec"),
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


def _find_report_file(run_dir: str, name: str) -> Optional[str]:
    reports_root = os.path.join(run_dir, "orfs_reports")
    if not os.path.exists(reports_root):
        return None
    for root, _, files in os.walk(reports_root):
        if name in files:
            return os.path.join(root, name)
    return None


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

    # Yosys stat summary row usually looks like: "814 7.33E+03 cells"
    cells_m = re.search(r"^\s*([0-9]+)\s+[0-9.eE+-]+\s+cells\b", text, re.IGNORECASE | re.MULTILINE)
    if cells_m:
        try:
            out["cell_count"] = int(cells_m.group(1))
        except Exception:
            pass
    return out


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

    metrics = {
        "area_um2": stat_data.get("area_um2"),
        "cell_count": stat_data.get("cell_count"),
        "wns_ns": finish_data.get("wns_ns"),
        "tns_ns": finish_data.get("tns_ns"),
        "power_uw": finish_data.get("power_uw"),
    }
    sources = {
        "area_um2": stat,
        "cell_count": stat,
        "wns_ns": finish,
        "tns_ns": finish,
        "power_uw": finish,
    }
    missing = [k for k, v in metrics.items() if v is None]
    notes = []
    if not finish:
        notes.append("6_finish.rpt not found")
    if not stat:
        notes.append("synth_stat.txt not found")

    run_meta = _read_run_meta(run_dir)
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
