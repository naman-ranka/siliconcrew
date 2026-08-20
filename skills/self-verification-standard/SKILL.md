---
name: self-verification-standard
description: How to earn a passing test instead of trusting one. Derive the test plan from the spec, cover the corner classes a spec never mentions, use an independent reference, and recognise the passes that are lies — an X-blind comparison, a loopback, a run that never terminated. Always in force; it needs no trigger because nothing in the environment ever says "your test was too easy".
license: Apache-2.0
metadata:
  siliconcrew-always-load: "true"
---

# Self-verification standard

A design that passes its own test but misread the spec is the most common
failure in this work, and it is silent: no tool errors, no red output, just a
green run and a wrong chip. Everything below exists to make that failure loud.

## Derive the test plan from the spec, not from the design

Write down what the spec requires before you write the testbench, and treat the
interface contract as a mechanical checklist: every port, every width, reset
behaviour, latency, throughput, and every parameter or mode combination the spec
describes. Assert each item. A requirement with no assertion is a requirement
you did not verify, and you must say so at the end rather than let a green run
imply otherwise.

## Cover the corner classes even when the spec is silent

Specs describe intent; hardware fails at the edges nobody wrote down:

- reset asserted in the middle of an operation, not just at time zero
- back-to-back transactions with no idle cycle between them
- empty and full conditions on any queue or buffer
- minimum, maximum, and overflow values on every arithmetic path
- stalls and maximum-latency paths, where a handshake can be dropped
- X and unknown values injected on inputs

## Passes that are lies

**An X-blind comparison.** In Verilog `x !== x` is FALSE, so a testbench that
compares an output against an expected value which is itself undefined counts a
mismatch as a match — and out-of-range array reads produce exactly that
undefined value. Guard every checked output with `$isunknown` (or an explicit
`=== 1'bx` check) before comparing, and fail on unknowns rather than ignoring
them. A simulation run reports `xDetected` from its own waveform, and a run that
passed while X was present is flagged `x-blind-pass` on the run record: treat
that flag as a failing test until you have proven otherwise.

**A loopback.** An encoder checked by its own decoder, or a generator checked by
its matching checker, proves only that the two agree — and they agree because
both were written from your reading of the spec. For arithmetic, encoding and
data-transform kernels, build an INDEPENDENT reference derived separately from
the spec and compare against that. Where a script is useful for the reference
model or its vectors, write it to the workspace and run it rather than deriving
expected values by hand from the RTL you are testing.

**A run that never finished.** Non-termination is a failure, not an inconclusive
result: suspect a combinational loop or a missing liveness condition, and fix
the design. The simulation tooling already records a timed-out run as failed —
do not re-interpret it as "needs a longer timeout" without evidence from the
waveform.

**A pass marker printed by a testbench that checked nothing.** If the run passed
but no comparison could have failed — no assertions, no reference, no error
counter — you have measured that the design compiles.

## When the testbench and the RTL disagree

Re-derive the expected value from the spec first, then change only the side that
contradicts it. Editing the testbench to match the RTL is how a misreading
becomes permanent.

## Before you call anything done

State which requirements you verified and which you did not, and name the
residual risk. That sentence is the deliverable; the green run is only evidence
for it.
