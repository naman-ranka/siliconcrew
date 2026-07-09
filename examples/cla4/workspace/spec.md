# 4-Bit Carry-Lookahead Adder

A 4-bit binary adder that computes all carries in parallel from operand
generate (`g = a & b`) and propagate (`p = a | b`) terms rather than rippling
them stage to stage. Sum and carry-out are registered on the clock; an
active-low reset clears them.

## Attribution
The RTL is adapted from the **Tiny Tapeout project "4-bit CLA"
(`tt08_CSA_4bits`)** by Wei Zhang
(https://github.com/Electom/tt08_CSA_4bits, commit
`213ea903e947a2fbc5415d67e893da5d43385ffe`), licensed **Apache-2.0** (full text
in `LICENSE` at the bundle root). The original wraps the adder in the fixed
Tiny Tapeout pin interface (`ui_in`/`uo_out`/`uio_*`/`ena`); this bundle exposes
real ports (`a`, `b`, `ci` -> `s`, `co`) while keeping the carry-lookahead
network and registered outputs verbatim. The self-checking testbench is original
to this bundle.

## Interface
| Signal | Dir | Width | Description                          |
|--------|-----|-------|--------------------------------------|
| clk    | in  | 1     | Clock                                |
| rst_n  | in  | 1     | Active-low reset (clears s, co)      |
| a      | in  | 4     | Operand A                            |
| b      | in  | 4     | Operand B                            |
| ci     | in  | 1     | Carry-in                             |
| s      | out | 4     | Sum (registered)                     |
| co     | out | 1     | Carry-out (registered)              |

## Verification
An original self-checking testbench sweeps **all 512 input vectors**
(a, b in 0..15 x ci in 0..1). Its oracle is an ordinary integer add
`a + b + ci`, independent of the lookahead carry network, compared against the
registered `{co, s}`. Target: `TEST PASSED`, then synthesize to GDS on sky130hd.
