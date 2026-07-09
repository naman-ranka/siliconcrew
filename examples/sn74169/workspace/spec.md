# sn74169 — 4-bit synchronous up/down counter

A functional replica of the classic TTL **74169** 4-bit synchronous binary
up/down counter. On each clock it either parallel-loads `A`, counts up or down,
or holds, depending on the active-low control lines. The active-low ripple-carry
output `RCOB` pulses low at terminal count so counters can be cascaded.

## Attribution
The RTL core is adapted from a Tiny Tapeout TT08 project,
**`andychip1/sn74169`** (https://github.com/andychip1/sn74169, commit
`cdab2c267cc94306c23f4e0c6a62559c30e6bed3`), licensed **Apache-2.0** (full text
in `LICENSE` at the bundle root). Upstream ships this synthesizable core
(`sn74169`) with a thin Tiny Tapeout wrapper (`tt_um_andychip1_sn74169`) that
maps the pins onto `ui_in`/`uo_out`. This bundle drops that pin wrapper and uses
the core directly as the top module — its ports are already the real '169
interface. The counter logic is kept **verbatim**. The self-checking testbench
is original to this bundle.

## Interface
| Signal | Dir | Width | Description                                          |
|--------|-----|-------|------------------------------------------------------|
| CLK    | in  | 1     | Clock                                                |
| A      | in  | 4     | Parallel-load data                                   |
| LOADB  | in  | 1     | Active-low synchronous load (`LOADB=0` -> `Q<=A`)    |
| ENPB   | in  | 1     | Active-low count enable P                            |
| ENTB   | in  | 1     | Active-low count enable T                            |
| U_DB   | in  | 1     | Direction: 1 = count up, 0 = count down              |
| Q      | out | 4     | Counter value                                        |
| RCOB   | out | 1     | Active-low ripple-carry out (low at terminal count)  |

## Behaviour
Priority each clock: `LOADB=0` loads `A`; else if `ENPB=ENTB=0` it counts
(up when `U_DB=1`, down when `U_DB=0`); otherwise it holds. `RCOB` is low when
`Q=15` while counting up, or `Q=0` while counting down — the cascade signal.

## Verification
An original self-checking testbench carries an independent golden model of the
transition rule and of `RCOB`. Every clock it drives a control vector, advances
the golden model, and asserts both `Q` and `RCOB`. It exercises a parallel load,
a full up-count through the `15 -> 0` wrap (with the `RCOB` terminal pulse), a
full down-count through the `0 -> 15` wrap, the hold/disable modes (`ENPB` and
`ENTB`), and load overriding an active count. Target: `TEST PASSED`, then
synthesize to GDS on sky130hd.
