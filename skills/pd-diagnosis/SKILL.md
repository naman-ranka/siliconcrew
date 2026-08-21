---
name: pd-diagnosis
description: Diagnose and fix physical-design failures — negative slack, congestion, routing DRCs, PDN errors. Classify the failure from stage evidence before changing anything, then choose between a physical retry and an RTL change. Load whenever timing is not met or a synthesis run fails in floorplan, placement, CTS, routing or power-grid generation.
license: Apache-2.0
---

# Diagnosing a physical-design failure

Timing and physical failures have a small number of causes and each leaves a
different fingerprint in the stage reports. Read the fingerprint first. Guessing
a knob and re-running is the expensive way to learn what one report would have
told you in a single call.

## Gather evidence in this order

1. `get_synthesis_status` — which stages actually produced artifacts. A failure
   at floorplan and a failure at route are different problems; the stage history
   tells you which one you have.
2. `read_stage_report` — the structured summary for the stage that matters
   (timing at CTS, congestion at global route, DRCs at route). Read these
   before grepping anything.
3. `get_synthesis_metrics` — the run's PPA and the signed slack. Take timing
   from the signed worst slack, never from a clamped report value.
4. `search_logs_tool` — last, and only for what the structured readers do not
   surface: PDN errors, path-level detail, ORFS-specific warnings.

Diagnose from what you read. Do not name a cause you did not look up.

## Classify the timing failure

**Negative slack already present at the floorplan stage.** Cell delay alone
exceeds the clock period: this is a process floor, and no physical knob will
close it. The remedies are RTL — shorten the logic depth, pipeline the critical
path, restructure the arithmetic — or accept the achieved frequency as this
design's limit on this process and say so.

**Slack positive at floorplan, negative only after routing.** This is wire
parasitics, not logic depth. Physical knobs are the right lever: core margin,
aspect ratio, utilization. Retry the physical stages rather than touching RTL.

**Congestion.** Per-layer overflow at global route means the placement cannot be
wired as-is. Lower utilization or change the aspect ratio; a design that is
congested at a sane utilization usually has a routing-hostile structure (a wide
crossbar, a large mux tree) and that is an RTL conversation.

**PDN-0185.** The floorplan is too small for the power grid, not a timing
problem at all. The error reports the die width the grid requires; the largest
utilization that can fit is the cell area divided by the square of that required
width. Retry at that value. Never respond by dropping utilization to a token
few percent — that hides the real limit and produces meaningless area numbers.

## Retry, and judge the result honestly

`retry_pd` branches a child run from an existing parent and reruns only the
stages from your chosen start stage onward; the parent is never modified, so
each knob is a separate, comparable experiment. The knob you change determines
the earliest stage that can consume it — see `references/pd_knob_catalog.md` for
the validated set and the stage each one applies to. Do not invent ORFS
variables; an unvalidated override is passed through unchecked and will fail
somewhere less obvious.

After a retry, wait for a terminal status and read `compare_pd_runs`. Accept the
child only if the target metric improved and the trade-offs elsewhere are ones
you can defend: a small slack gain bought with a large area increase is a real
result, not automatically a better one.

## When to stop tuning physics

Two or three physical retries that do not move the target metric mean the limit
is not physical. Go back to the RTL — pipeline depth, state encoding, arithmetic
structure, reset strategy, port widths — or report the achieved operating point
as the honest limit. Continuing to sweep knobs past that point produces runs,
not progress.
