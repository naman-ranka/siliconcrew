# PD ORFS Stage Tooling Plan

## Intent

We want to expand the current synthesis tooling from a single full-flow ORFS job into a stage-aware PD toolset that can:

- inspect stage outputs and diagnostics
- rerun selected physical design stages with controlled parameter changes
- support a future PD-focused subagent that can make decisions between stages instead of waiting for final signoff

The target use case is a flow like:

- main agent handles RTL, simulation, architecture selection
- PD-focused logic takes a synthesized design or run artifact
- PD logic inspects floorplan, placement, CTS, routing, and signoff outputs
- PD logic retries selected stages with tuned parameters
- final result returns timing status, diagnosis, and parameter lineage

This is not just about exposing more ORFS knobs. The goal is to build a reliable stage-aware backend that supports systematic PD iteration.

## Why This Matters

The current `synthesis_manager` is whole-flow oriented. It is good at:

- starting a synthesis job
- waiting for completion
- collecting metrics
- doing full-run bookkeeping

But it is too coarse for PD iteration. Today it does not model:

- stage checkpoints
- stage-specific status
- rerun from an intermediate checkpoint
- stage-specific diagnostics as first-class outputs

If timing, congestion, skew, or DRC problems are already visible after placement, CTS, or global route, we want to catch them there and react earlier.

## What We Are Trying To Implement

The long-term direction discussed was a PD-aware toolset that could eventually support an orchestrator model like:

- inspect stage reports
- decide whether to proceed
- retry later stages with updated parameters
- report final closure status with diagnosis

Candidate tool directions discussed:

- `read_stage_report(run_id, stage)`
- `get_congestion_summary(run_id)`
- `get_route_drc_summary(run_id)`
- `get_cts_summary(run_id)`
- `get_critical_paths(run_id, top_n=5)`
- `retry_pd(run_id, start_stage, params, max_stage)`

Important design principle:

- start with read-only and controlled retry tools
- do not expose many raw ORFS stage entry points immediately
- keep policy decisions in the agent layer, not hardcoded inside the execution tools

## Recommended Rollout

### Phase 1

Implement and test:

- `read_stage_report(run_id, stage)`
- `get_congestion_summary(run_id)`
- `get_route_drc_summary(run_id)`
- `get_cts_summary(run_id)`

### Phase 2

Add stage-aware metadata:

- current stage
- per-stage status
- artifacts by stage
- lineage to parent/source run
- parameter deltas

### Phase 3

Add one controlled execution tool:

- `retry_pd(run_id, start_stage, params, max_stage)`

### Phase 4

Only after the backend is stable:

- custom Tcl hooks
- richer clock/timing diagnostics
- PD orchestration logic

## Probe Summary

Real ORFS probing was done using:

- `C:\Users\naman\Desktop\Projects\RTL_AGENT\workspace\p1-claude-code`
- copied into isolated test area:
  - `C:\Users\naman\Desktop\Projects\RTL_AGENT\workspace\orfs-probe-p1`

Key findings:

- ORFS stage targets like `floorplan`, `place`, `cts`, `grt`, `route`, `finish`, `drc`, `lvs` are real and usable
- `do-*` stage targets work for retries only when prerequisite checkpoints already exist
- stage chaining through intermediate ORFS artifacts is real
- floorplan, placement, and CTS knobs showed clear effects on the probe design
- at least some routing knobs need per-knob validation before exposure

## Working Rule

Expand the toolset incrementally, validate each step on a real design, and only widen the ORFS surface after each knob proves meaningful in practice.
