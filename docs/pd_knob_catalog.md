# PD Knob Catalog

## Purpose

This document is the current reference for physical-design tuning through the staged PD worktree.

The execution model today is:

- `start_synthesis(...)` for the initial full ORFS run
- `retry_pd(...)` for checkpoint-based staged reruns

Lower-level ORFS control currently enters through:

- `retry_pd(..., orfs_overrides_json="...")`

This document exists so we do not need to bloat `retry_pd` with a large typed parameter surface before the knob set is mature and validated.

## Current Retry Interface

Example:

```json
{
  "run_id": "synth_0011",
  "start_stage": "cts",
  "max_stage": "finish",
  "orfs_overrides_json": "{\"CTS_BUF_DISTANCE\": 100}"
}
```

Important rule:

- use only ORFS variables that are relevant to the chosen retry stage window
- prefer knobs that have been validated in this repo

## Status Labels

- `validated`: tested in this repo or probe flow and observed to affect ORFS behavior meaningfully
- `supported-not-validated`: known ORFS variable, but not yet validated in this repo flow
- `tried-no-clear-effect`: tested here, but did not show a reliable observable effect

## Validated Knobs

### Floorplan

```text
ORFS variable: CORE_UTILIZATION
Status: validated
Use with: start_synthesis, retry_pd(start_stage="floorplan", ...)
Observed effect:
  changing this materially changed die size and tapcell count on the seq_detector probe
Example:
  {"CORE_UTILIZATION": 10}
Notes:
  this is currently one of the safest floorplan tuning knobs we have verified
```

### Placement

```text
ORFS variable: PLACE_DENSITY
Status: validated
Use with: retry_pd(start_stage="place", ...)
Observed effect:
  ORFS explicitly used the passed density and placement behavior changed
Example:
  {"PLACE_DENSITY": 0.15}
Notes:
  useful for timing/congestion tradeoff experiments after floorplan is fixed
```

### CTS

```text
ORFS variable: CTS_BUF_DISTANCE
Status: validated
Use with: retry_pd(start_stage="cts", ...)
Observed effect:
  ORFS explicitly reflected the new distance_between_buffers value
  validated both in probe runs and in real retry_pd child runs
Example:
  {"CTS_BUF_DISTANCE": 100}
Notes:
  currently the most clearly proven CTS knob in this repo
```

## Supported But Not Yet Validated Here

These are plausible ORFS variables that may be useful, but we have not yet validated them end-to-end in this repo/tooling path.

### Floorplan candidates

```text
CORE_ASPECT_RATIO
CORE_MARGIN
DIE_AREA
CORE_AREA
```

Notes:
- `CORE_ASPECT_RATIO` and `CORE_MARGIN` are already exposed in `start_synthesis`
- they are not yet part of a staged retry-specific tuning workflow

### CTS candidates

```text
CTS_ARGS
CTS_CLUSTER_SIZE
CTS_CLUSTER_DIAMETER
CTS_BUF_LIST
CTS_LIB_NAME
```

Notes:
- likely useful once we broaden CTS experimentation
- should be validated with real retry runs before being recommended

### Global routing candidates

```text
GLOBAL_ROUTE_ARGS
MIN_ROUTING_LAYER
MAX_ROUTING_LAYER
```

Notes:
- these are strong candidates for future validation
- especially relevant when congestion or routing layer usage is the main issue

### Route / finish candidates

```text
additional stage-specific knobs TBD
```

Notes:
- route/finish tuning needs more repo-specific validation before we recommend variables

## Tried With No Clear Effect Yet

### Global routing

```text
ORFS variable: ROUTING_LAYER_ADJUSTMENT
Status: tried-no-clear-effect
Observed result:
  the probe run completed, but the logs still showed "Global adjustment: 0%"
Interpretation:
  may require different formatting, a different invocation context, or may not be effective in this flow/platform setup
Recommendation:
  do not recommend yet
```

## Recommended Usage Pattern

### Baseline flow

```text
1. run start_synthesis(...)
2. inspect:
   - get_synthesis_status (stages / stage_history)
   - get_cts_summary
   - get_congestion_summary
   - get_route_drc_summary
3. choose retry stage window
4. apply one or a few targeted ORFS overrides through retry_pd
5. compare parent and child
```

### Examples

CTS retry:

```json
{
  "run_id": "synth_0011",
  "start_stage": "cts",
  "max_stage": "finish",
  "orfs_overrides_json": "{\"CTS_BUF_DISTANCE\": 100}"
}
```

Placement retry:

```json
{
  "run_id": "synth_0011",
  "start_stage": "place",
  "max_stage": "finish",
  "orfs_overrides_json": "{\"PLACE_DENSITY\": 0.55}"
}
```

Floorplan retry:

```json
{
  "run_id": "synth_0011",
  "start_stage": "floorplan",
  "max_stage": "finish",
  "orfs_overrides_json": "{\"CORE_UTILIZATION\": 10}"
}
```

## What This Document Is Not

This is not a complete ORFS variable reference.

It is a repo-specific working catalog for:

- knobs the staged PD backend can realistically use
- knobs we have actually tested or are considering next
- avoiding unsafe or noisy recommendation of variables we have not validated

For the broader ORFS universe, use the official ORFS flow variable documentation separately.

## Next Catalog Improvements

- add parent-vs-child retry comparison examples
- add stage-specific recommended ranges where we have enough data
- add a `validated on real retry_pd` marker separate from `validated in probe`
- eventually consider a helper tool such as `get_pd_knob_catalog(stage=None)`
