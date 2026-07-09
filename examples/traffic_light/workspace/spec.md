# Traffic-Light Controller — 3-state Moore FSM

A classic single-intersection traffic light. The controller cycles through three
phases in a fixed order — **GREEN → YELLOW → RED → GREEN** — holding each phase
for a parameterized number of clock ticks. Exactly one of the three light outputs
is asserted every cycle (one-hot), so the outputs drive three LEDs directly.
An asynchronous active-low reset `rst_n` returns the FSM to GREEN with a fresh
phase timer.

## Parameters
| Name         | Default | Meaning                          |
|--------------|---------|----------------------------------|
| GREEN_TICKS  | 8       | Clock ticks the GREEN phase holds |
| YELLOW_TICKS | 3       | Clock ticks the YELLOW phase holds|
| RED_TICKS    | 8       | Clock ticks the RED phase holds   |

## Interface
| Signal | Dir | Width | Description                         |
|--------|-----|-------|-------------------------------------|
| clk    | in  | 1     | Clock (rising-edge sampled)         |
| rst_n  | in  | 1     | Async active-low reset (to GREEN)   |
| green  | out | 1     | GREEN light (one-hot)               |
| yellow | out | 1     | YELLOW light (one-hot)              |
| red    | out | 1     | RED light (one-hot)                 |

## Verification
A self-checking testbench uses short phase timers so the full cycle simulates
quickly. Every clock it checks (a) the outputs are one-hot (exactly one light
lit), (b) each completed phase is held for exactly its parameterized number of
ticks, and (c) phases advance only in the legal order GREEN → YELLOW → RED →
GREEN. Emits `TEST PASSED` only if every check holds, then synthesize to GDS on
sky130hd.
