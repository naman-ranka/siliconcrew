# AES Inverse S-Box

The byte-substitution step used in AES decryption: it maps each input byte
`x` to `AES^-1_Sbox[x]`. This is a hardware realization built from a gate-level
network (multiplicative inverse in GF(2^8) composed with the inverse affine
transform), expressed with standard-cell primitives rather than a lookup ROM.
The substituted byte appears combinationally on `y`; a registered copy is
latched on `clk` into `cy`.

## Attribution
The RTL is adapted from the **Tiny Tapeout project "AES inverse S-box"** by
Dag Arne Osvik (https://github.com/daosvik/tt08-aes-invsbox, commit
`e78636840df3af0a11027db7fe2a0d3a82821521`), licensed **Apache-2.0** (full text
in `LICENSE` at the bundle root). The upstream Tiny Tapeout wrapper
(`tt_um_daosvik_aesinvsbox`) maps the core onto the fixed `ui_in`/`uo_out`/`uio`
pins; this bundle drops that wrapper and uses the `sbox_aesinv` core module
directly as the top, verbatim. Its standard-cell primitives come from the
project's own portable behavioral library `sky130.v` -- the cell names mirror
the Sky130 PDK but the bodies are plain behavioral Verilog, so the gate-level
design is PDK-neutral for lint, simulation, and synthesis. The only edit is in
`sky130.v`: the upstream `keep_hierarchy` attribute on each cell module is
removed so the standard sky130hd flow flattens the design and reports true
(flattened) PPA rather than leaving the substitution network in unelaborated
sub-modules; no cell logic changed. The self-checking testbench is original to
this bundle.

## Interface
| Signal | Dir | Width | Description                                    |
|--------|-----|-------|------------------------------------------------|
| clk    | in  | 1     | Clock (latches the registered output)          |
| x      | in  | 8     | Input byte                                     |
| y      | out | 8     | `AES^-1_Sbox[x]` (combinational)               |
| cy     | out | 8     | Registered copy of `y`                        |

## Verification
An original self-checking testbench drives **all 256 input bytes** and checks
the combinational output `y` against the **FIPS-197 inverse S-box** (a golden
table embedded in the testbench, independent of the DUT's gate network). It also
checks the registered output `cy` one clock after each input. Target:
`TEST PASSED`, then synthesize to GDS on sky130hd (the gate-level netlist carries
`keep_hierarchy`, so the substitution structure is preserved through synthesis).
