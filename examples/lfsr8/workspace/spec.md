# 8-bit Maximal-Length LFSR

A Fibonacci linear-feedback shift register generating a pseudo-random sequence
with **maximal period 255**. Feedback polynomial x^8 + x^6 + x^5 + x^4 + 1
(taps at bits 8,6,5,4). The all-zero state is unreachable from a non-zero seed;
async active-low reset `rst_n` seeds 0xFF. `en` gates the shift.

## Interface
| Signal | Dir | Width | Description                        |
|--------|-----|-------|------------------------------------|
| clk    | in  | 1     | Clock                              |
| rst_n  | in  | 1     | Async active-low reset (seed 0xFF) |
| en     | in  | 1     | Shift enable                       |
| state  | out | 8     | Current LFSR state                 |

## Verification
A self-checking testbench runs 255 enabled clocks and asserts (a) the state is
never the all-zero lockup value and (b) the sequence returns to the seed exactly
at step 255 — i.e. the period is maximal. Target: `TEST PASSED`, then synthesize
to GDS on sky130hd.
