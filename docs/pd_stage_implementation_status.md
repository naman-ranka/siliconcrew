# PD Stage Tooling Implementation Status

## Purpose

This worktree implements the first usable version of staged physical-design iteration on top of the existing RTL Agent synthesis manager.

The goal is to preserve the current simple full-flow synthesis path while adding a second layer for PD-style iteration:

- run one baseline full ORFS flow
- inspect stage-specific reports
- retry from a selected checkpoint
- tune ORFS variables during the retry
- keep every attempt isolated and traceable

## Worktree

```text
Branch:
  feature/pd-stage-tooling

Path:
  C:\Users\naman\Desktop\Projects\RTL_AGENT\workspace\.claude\worktrees\pd-stage-tooling
```

## Architecture Implemented

### Baseline full flow

```text
start_synthesis(...)
  -> creates synth_runs/synth_NNNN
  -> runs full ORFS flow
  -> preserves existing async job/polling behavior
  -> records stage-aware metadata after completion
```

`start_synthesis` remains the coarse first-pass entrypoint.

### Staged retry flow

```text
retry_pd(...)
  -> takes an existing parent run
  -> validates checkpoint prerequisites
  -> creates a separate child run
  -> copies only needed inputs/spec/constraints/checkpoints
  -> runs selected downstream ORFS do-* targets
  -> records lineage and stage metadata
```

Retries do not mutate parent runs.

Example:

```text
retry_pd(
  run_id="synth_0011",
  start_stage="cts",
  max_stage="finish",
  orfs_overrides_json="{\"CTS_BUF_DISTANCE\": 100}"
)

Copies:
  3_place.odb
  3_place.sdc

Runs:
  do-cts
  do-grt
  do-route
  do-finish
```

## Public Tools Added

### `read_stage_report`

Reads the main ORFS artifact for a stage.

Supported stages:

```text
floorplan -> 2_floorplan_final.rpt
place     -> 3_3_place_gp.json
cts       -> 4_cts_final.rpt
grt       -> congestion.rpt or related GRT artifact
route     -> 5_route_drc.rpt
finish    -> 6_finish.rpt
```

### `get_route_drc_summary`

Summarizes final route DRC status from `5_route_drc.rpt`.

Returns:

```text
clean
violation_count
unique_violation_count
sample_violations
```

An empty `5_route_drc.rpt` is treated as a clean final route DRC result.

### `get_cts_summary`

Summarizes `4_cts_final.rpt`.

Returns:

```text
wns_ns
tns_ns
worst_slack_ns
clock_period_min_ns
clock_fmax_mhz
setup_skew_ns
max_slew_violation_count
max_fanout_violation_count
max_cap_violation_count
setup_violation_count
hold_violation_count
critical_path_delay_ns
critical_path_slack_ns
slack_over_delay_ratio
sample_startpoints
sample_endpoints
clock_names
```

### `get_congestion_summary`

Summarizes global-route congestion from `congestion.rpt` when available, otherwise from `5_1_grt.log`.

Returns:

```text
per-layer resource
per-layer demand
per-layer usage_pct
per-layer overflow
total usage
total overflow
wirelength_um
routed_nets
has_overflow
congested_layers
```

### `get_stage_status`

Reads stage-aware metadata from `run_meta.json`.

Returns:

```text
run_status
current_stage
stages
completed_stages
failed_stages
running_stages
pending_stages
stage_count
elapsed_sec
```

### `compare_pd_runs`

Compares a PD retry child run against its parent.

If `parent_run_id` is omitted, the tool infers it from child retry metadata:

```text
parent_run_id
source_run_id
```

Returns:

```text
parent_run_id
child_run_id
lineage
verdict
signoff_clean
timing_closed
route_clean
improved_metrics
regressed_metrics
comparisons
route_drc_comparison
congestion_comparison
```

Current verdict values:

```text
closed
closed_with_tradeoffs
improved
mixed
regressed
neutral
```

### `retry_pd`

Creates a checkpoint-based child retry run.

Inputs:

```text
run_id
start_stage
max_stage
orfs_overrides_json
timeout_sec
```

Supported start stages:

```text
floorplan
place
cts
grt
route
finish
```

## Stage Metadata

`run_meta.json` now includes:

```text
current_stage
stages
```

Tracked stages:

```text
constraints
synth
floorplan
place
cts
grt
route
finish
```

Each stage records:

```text
status
artifacts
```

For child retry runs, metadata also records:

```text
mode: pd_retry
parent_run_id
source_run_id
retry_start_stage
retry_max_stage
orfs_overrides
retry_prerequisites
```

## Checkpoint Validation

`retry_pd` validates stage prerequisites before launching a child run.

Current mapping:

```text
floorplan:
  1_synth.odb
  1_synth.sdc

place:
  2_floorplan.odb
  2_floorplan.sdc

cts:
  3_place.odb
  3_place.sdc

grt:
  4_cts.odb
  4_cts.sdc

route:
  5_1_grt.odb
  5_1_grt.sdc

finish:
  5_route.odb
  5_route.sdc
```

## Files Copied Into Child Retry Runs

Copied from parent into child:

```text
inputs/*
constraints.sdc
spec file
required checkpoint artifacts for start_stage
```

Spec propagation handles both layouts:

```text
parent/spec/*.yaml
parent/<run_meta.spec_file>
```

This was fixed after a real ORFS retry exposed that older full-flow runs stored the spec at the parent run root.

## ORFS Overrides

Lower-level ORFS variables are currently passed through:

```text
orfs_overrides_json
```

Example:

```json
{
  "CTS_BUF_DISTANCE": 100
}
```

The separate knob catalog is in:

```text
docs/pd_knob_catalog.md
```

Current validated knobs:

```text
CORE_UTILIZATION
PLACE_DENSITY
CTS_BUF_DISTANCE
```

## Real ORFS Validation

A real retry was run against:

```text
workspace/p1-claude-code
parent: synth_0011
```

First live child:

```text
child: synth_0013
start_stage: cts
max_stage: finish
override: CTS_BUF_DISTANCE=100
result: completed
```

Verification:

```text
4_1_cts.log showed:
  clock_tree_synthesis ... -distance_between_buffers 100
  Distance between buffers: 3 units (100 um)
```

Second live child after spec propagation fix:

```text
child: synth_0014
start_stage: cts
max_stage: finish
override: CTS_BUF_DISTANCE=100
result: completed
```

Verification:

```text
run_meta.json:
  spec_file: seq_detector_0011_spec.yaml

child spec directory:
  spec/seq_detector_0011_spec.yaml
```

## Tests Added

Fixture and runtime tests:

```text
tests/test_stage_report_tool.py
tests/test_route_drc_summary_tool.py
tests/test_cts_summary_tool.py
tests/test_congestion_summary_tool.py
tests/test_stage_metadata_runtime.py
tests/test_stage_status_tool.py
tests/test_retry_pd_tool.py
tests/test_compare_pd_runs_tool.py
tests/test_synthesis_manager_hardening.py
```

MCP visibility updated in:

```text
tests/test_poll_wait_and_mcp_visibility.py
```

Fixtures added under:

```text
tests/fixtures/
```

## Validated Test Commands

Focused tests that were run and passed during implementation:

```text
pytest tests/test_stage_report_tool.py -q
pytest tests/test_route_drc_summary_tool.py -q
pytest tests/test_cts_summary_tool.py -q
pytest tests/test_congestion_summary_tool.py -q
pytest tests/test_stage_metadata_runtime.py -q
pytest tests/test_stage_status_tool.py -q
pytest tests/test_retry_pd_tool.py -q
pytest tests/test_synthesis_manager_hardening.py -q
pytest tests/test_poll_wait_and_mcp_visibility.py::test_mcp_does_not_expose_sleep_tool -q
```

Additional wrapper smoke checks were run for:

```text
read_stage_report
get_route_drc_summary
get_cts_summary
get_congestion_summary
get_stage_status
retry_pd error path
retry_pd success path with stubbed ORFS target runner
```

## Hardening Added After Review

The following correctness fixes were added after reviewing the first implementation:

```text
PD parameter preservation:
  start_synthesis now persists utilization/aspect_ratio/core_margin into run_meta
  retry_pd recovers those parent values instead of falling back through summary_metrics

Run allocation safety:
  run-id allocation and run directory creation are serialized
  index.json updates are serialized

Route DRC safety:
  an empty 5_route_drc.rpt is clean only when route stage completion is established
  empty incomplete reports are not reported as clean

ORFS override safety:
  override keys must match ^[A-Z][A-Z0-9_]*$
  values must be scalar and cannot contain newlines, NUL, '$', or backticks

Retry prerequisites:
  retry_pd validates prerequisite artifacts without copying into the child run
  worker performs the actual copy once

Legacy metadata:
  get_stage_status infers stage metadata from existing ORFS artifacts for old runs
```

## Current Limitations

### Parent-child QoR comparison is a read tool, not persisted metadata

`compare_pd_runs` now provides a structured comparison object on demand.

It is not yet automatically persisted into child `run_meta.json`.

### ORFS overrides are generic but validated

`orfs_overrides_json` is flexible, but it relies on the agent or user knowing valid ORFS variable names.

This is why `docs/pd_knob_catalog.md` was added.

### Knob validation is still small

Validated knobs are currently limited to:

```text
CORE_UTILIZATION
PLACE_DENSITY
CTS_BUF_DISTANCE
```

Many ORFS knobs are pass-through capable in principle, but not yet proven in this repo.

### No PD policy loop yet

There is no automatic decision logic like:

```text
if CTS WNS improves, continue
if congestion worsens, retry place density
if DRC appears, adjust route settings
```

The backend now supports that kind of loop, but the policy layer is not implemented.

### No custom Tcl hooks yet

Richer reports such as detailed skew histograms or top critical path endpoints may need generated Tcl hooks later.

## Recommended Future Plan

### 1. Persist parent-child QoR comparison in retry metadata

`compare_pd_runs(child_run_id, parent_run_id=None)` exists as an on-demand tool.

Next step is optional persistence into retry child metadata after completion.

Useful persisted fields:

```text
CTS:
  wns_ns
  tns_ns
  setup_violation_count
  hold_violation_count
  setup_skew_ns

GRT:
  total usage_pct
  total_overflow
  congested_layers
  wirelength_um

Route:
  clean
  violation_count

Finish:
  area_um2
  wns_ns
  tns_ns
  power_uw
```

### 2. Validate more knobs

Next candidates:

```text
CTS_CLUSTER_SIZE
CTS_CLUSTER_DIAMETER
CTS_BUF_LIST
GLOBAL_ROUTE_ARGS
MIN_ROUTING_LAYER
MAX_ROUTING_LAYER
CORE_ASPECT_RATIO
CORE_MARGIN
```

Each knob should be validated with:

```text
one real retry
one log check proving ORFS honored it
one summary comparison showing whether it changed anything meaningful
```

### 3. Add knob discovery helper if needed

Keep `retry_pd` small.

Possible future tool:

```text
get_pd_knob_catalog(stage=None)
```

This would return the same knowledge as `docs/pd_knob_catalog.md` in agent-friendly JSON.

### 4. Add guided retry policy

After comparison and more knob validation:

```text
suggest_pd_retry(run_id)
```

Could inspect:

```text
get_cts_summary
get_congestion_summary
get_route_drc_summary
get_stage_status
```

And return:

```text
recommended start_stage
recommended max_stage
recommended orfs_overrides_json
diagnosis
confidence
```

### 5. Consider richer OpenROAD report hooks

Only after basic comparison and retry flow stabilize.

Potential hooks:

```text
post-CTS report_cts/report_clock_skew
post-GRT detailed congestion dump
post-route DRC categorization
finish-stage top critical paths
```

## Practical Summary

Implemented now:

```text
full baseline synthesis remains intact
stage-aware read tools exist
stage-aware metadata exists
checkpoint-aware retry exists
real ORFS retry was validated
spec propagation bug was fixed
knob catalog doc exists
```

Most valuable next implementation:

```text
parent-vs-child QoR comparison
```

That will turn retries from "run and inspect manually" into a measurable PD iteration loop.
