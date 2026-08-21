---
name: sim-failure-debug
description: Debug a failing, hanging or post-synthesis-only simulation from its waveform — X propagation, cycle misalignment, reset coverage, missing runtime data, and the gate-level causes that appear when the RTL simulation passed but the netlist one did not. Load when a simulation fails, times out, or fails only after synthesis.
license: Apache-2.0
---

# Debugging a failing simulation

## Start from the first divergence, not the last error

A failing run reports the first failing line and its simulation time. Open the
waveform at that time and work backwards to the first signal that is wrong; the
reported failure is usually several cycles downstream of the cause. Reading the
whole waveform from time zero wastes the budget the tool spends on it.

Four causes account for most RTL failures, and each looks distinct in the trace:

- **X or Z propagation.** A signal goes unknown and the unknown spreads. Trace
  it back to its source: an uninitialised register, a read outside an array's
  range, an unconnected port, or a bus with no driver.
- **Cycle misalignment.** The values are right and the timing is not — the
  testbench samples on the wrong edge, or the design has one more or one fewer
  pipeline stage than the checker assumes. Compare the expected and actual
  streams shifted by one cycle before assuming the data path is wrong.
- **Reset behaviour.** Check what the design does while reset is asserted and on
  the exact cycle it releases. A design that only works when reset is held for
  an unrealistically long time is a bug the testbench is hiding.
- **Missing runtime data.** A run whose `$readmem` data never loaded produces
  zeros or unknowns everywhere and can still print a pass marker. The run record
  lists the data files it actually staged — check that list before suspecting
  the logic.

## A hang is a failure

A simulation that never terminates is a failing design, not an inconclusive
run: suspect a combinational loop, a handshake that never completes, or a
counter that cannot reach its terminal value. Look for the last time any signal
changed — that is where the deadlock closed.

## The RTL simulation passed and the post-synthesis one did not

This has one dominant cause: gate-level flip-flops start unknown. RTL
simulation initialises registers to a defined value in many cases; a netlist
does not, so anything reset does not cover stays X forever and the X spreads
through the design.

Check, in order:

1. **Reset coverage.** Every state-holding element the design depends on must be
   reset. A register that is only ever "initialised" by an initial block or by
   an assumed power-up value does not exist in gates.
2. **Reset duration and polarity in the testbench.** The gate netlist may need
   reset held across more cycles than the RTL did.
3. **Unknowns at the boundary.** Inputs left floating by the testbench are
   tolerated by RTL semantics far more often than by gates.

Only after those come to nothing is the netlist itself a suspect. The
simulation tooling already substitutes the gate netlist and links the standard
cell models for you, so a mismatch is almost never a wiring mistake in the run
setup.

## Do not repair the symptom

Adding a delay, widening a window, relaxing a comparison or removing an
assertion makes the run green without changing what the hardware does. Fix the
side that contradicts the spec, then re-run.
