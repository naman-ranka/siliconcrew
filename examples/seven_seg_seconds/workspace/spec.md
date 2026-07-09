# Seven-Segment Seconds Counter

A free-running clock divider ticks a single BCD digit **0 → 9 → 0** once per
"second", decoded onto a seven-segment display output. A parameter `MAX_COUNT`
sets the clock ticks per increment (10,000,000 for a 10 MHz clock → 1 Hz);
reduce it to make the digit tick fast in simulation. Synchronous active-low
reset `rst_n` returns the digit to 0.

## Attribution
The RTL is adapted from **Tiny Tapeout's `tt05-verilog-demo`**
(https://github.com/TinyTapeout/tt05-verilog-demo, commit
`a7e71a2f1b954fff59597838ef1453dba01f8861`), licensed **Apache-2.0** (full text
in `LICENSE` at the bundle root). The original wraps the logic in the fixed
Tiny Tapeout pin interface (`ui_in`/`uo_out`/`uio_*`/`ena`); this bundle exposes
real ports (`clk`, `rst_n`, `seg[6:0]`) and adds the sim-friendly `MAX_COUNT`
parameter. The seven-segment decoder (`seg7.v`) is kept verbatim. The
self-checking testbench is original to this bundle.

## Interface
| Signal | Dir | Width | Description                                   |
|--------|-----|-------|-----------------------------------------------|
| clk    | in  | 1     | Clock                                         |
| rst_n  | in  | 1     | Synchronous active-low reset (digit → 0)      |
| seg    | out | 7     | Seven-segment segments for the current digit  |

## Parameters
| Name      | Default    | Meaning                          |
|-----------|------------|----------------------------------|
| MAX_COUNT | 10_000_000 | Clock ticks per BCD increment    |

## Verification
A self-checking testbench uses a tiny `MAX_COUNT` so the digit ticks quickly.
Its oracle is independent of the DUT's internal counter: the expected digit at
sample k is `floor(k/(MAX_COUNT+1)) % 10`, and the expected segment pattern comes
from a golden 7-segment table. Every clock it checks the segments equal the
golden decode of the expected digit, and asserts the digit reached 9 and wrapped
to 0 across several full cycles. Target: `TEST PASSED`, then synthesize to GDS on
sky130hd (the default 24-bit `MAX_COUNT` divider is the synthesized design).
