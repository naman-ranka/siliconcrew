---
name: pareto-sweep
description: Characterise a verified design's power/performance/area frontier — how to choose sweep points, run them in parallel, decide what is on the frontier, and report marginal points honestly. Load when asked to explore Fmax, operating points, or power/area trade-offs for a design that already passes verification.
license: Apache-2.0
---

# Sweeping the PPA frontier

A sweep characterises a design that is ALREADY verified. If the RTL simulation
does not pass, there is nothing worth measuring — fix that first. Every number
in the result must come from a run's own reports; a sweep that reports an
estimate as a measurement is worse than no sweep.

## Choose the points, then start them all

Sweep the clock period in both directions from the spec's target: relaxed
(roughly 1.5x and 2x) to find the power floor and to see whether area falls,
and aggressive (roughly 0.85x, 0.75x, 0.65x) to find where timing breaks.
Dispatch every run before waiting on any of them — synthesis is asynchronous
and the runs queue server-side — then poll them with a bounded wait. Running
them one at a time turns a twenty-minute sweep into an afternoon.

Utilization is the second axis. Find the highest value the design can actually
place and route rather than settling for a safe low number; a too-low
utilization makes area meaningless. When the power grid rejects the floorplan,
`pd-diagnosis` has the back-calculation that gives you the real ceiling.

## Architecture variants earn their place, or they do not

Before writing a variant, read the critical path of the tightest run that
passed and let it tell you where the bottleneck is. A variant that does not
break the actual bottleneck cannot produce a new frontier point, whatever else
it changes. Keep a variant only if it is on the frontier — better area OR
better Fmax at the same or lower power. A variant that is worse on every axis
is a result too: record it and exclude it.

## What counts as a frontier point

A measured point is on the frontier when no other measured point beats it on
every dimension at once. The primary axes are Fmax and power; area is reported
but on small designs it is often flat across the whole sweep — say so
explicitly rather than presenting noise as a trend.

Honesty rules specific to sweeps:

- A point whose slack is positive but tiny is MARGINAL. Report it as marginal
  and do not treat it as a robust operating point.
- Cell area and post-place area diverge once clock-tree buffers and filler
  cells land. Record them as two numbers, each with the run it came from, and
  never present one as the other.
- A failed run is data. Include it in the table with its failure class.
- Stop when you hit a wall and name the wall: negative slack at the floorplan
  stage is a process floor, and a power-grid rejection at the recalculated
  utilization is a physical floor.

## Report

Write the results to a workspace file so the table survives the conversation.
Include: every run with its identifier, configuration and measured numbers,
including failures; the failure classes with the evidence they came from; the
frontier itself; and a short statement of what actually limits this design,
whether area is a real dimension for it, and the operating range you would be
willing to defend to someone taping it out.
