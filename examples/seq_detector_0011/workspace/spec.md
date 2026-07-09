# Sequence Detector — pattern 0011

Detect the serial bit pattern **0-0-1-1** (in time order, MSB-first) on a
single-bit input `din`, sampled on the rising edge of `clk`. Assert `detected`
for the one cycle whose most-recent four bits equal `0011`. Detection is
**overlapping** — the window keeps shifting, so back-to-back and overlapping
occurrences are all reported. Active-low asynchronous reset `rst_n` clears the
window.

## Interface
| Signal    | Dir | Width | Description                          |
|-----------|-----|-------|--------------------------------------|
| clk       | in  | 1     | Clock (rising-edge sampled)          |
| rst_n     | in  | 1     | Async active-low reset               |
| din       | in  | 1     | Serial input bit                     |
| detected  | out | 1     | High for the cycle the window is 0011|

## Verification
A self-checking testbench drives a stream containing multiple (including
overlapping) occurrences of 0011 and checks `detected` against an independent
reference window every cycle. Target: `TEST PASSED`, then synthesize to GDS on
sky130hd.
