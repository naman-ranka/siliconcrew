# Configurable PWM generator

A pulse-width-modulation generator with a 12-bit programmable period and a
percentage duty cycle (1..99%). Two on-chip registers — `period_reg` and
`duty_reg` — are loaded through a shared write port; the core then drives
`pwm_out` high for `t_on = period*duty/100` clocks out of every `period` clocks,
gated by `out_en`. Active-low reset clears both registers.

## Attribution
The RTL core is adapted from a Tiny Tapeout TT08 project,
**`MateaSamuel/tt08-pwm-generator`**
(https://github.com/MateaSamuel/tt08-pwm-generator, commit
`731fb9162500ee5c35bdf9be478586b346df94ef`), licensed **Apache-2.0** (full text
in `LICENSE` at the bundle root). Upstream ships this synthesizable core
(`pwm_generator`) alongside a thin Tiny Tapeout wrapper
(`tt_um_samuelm_pwm_generator`) that muxes the config write port onto the fixed
`ui_in`/`uio_in` pins. This bundle drops that pin wrapper and promotes the core
itself to the top module — its ports are already the real interface. The core
logic is kept **verbatim**. The self-checking testbench is original to this
bundle.

## Interface
| Signal  | Dir | Width | Description                                          |
|---------|-----|-------|------------------------------------------------------|
| clk     | in  | 1     | Clock (design intent 50 MHz)                         |
| rst_n   | in  | 1     | Active-low reset (period & duty registers -> 0)      |
| in      | in  | 12    | Write data: 12-bit period, or duty% in `in[6:0]`     |
| sel     | in  | 1     | Register select: 1 = period, 0 = duty                |
| wr_en   | in  | 1     | Load `in` into the selected register this clock      |
| out_en  | in  | 1     | Output enable (0 forces `pwm_out` low)               |
| pwm_out | out | 1     | PWM output                                           |

## Programming
Raise `wr_en` for one clock with `sel=1` to load the period, and with `sel=0` to
load the duty (a percentage in `in[6:0]`). Then raise `out_en`. The duty holds
until reprogrammed.

## Verification
An original self-checking testbench programs several `(period, duty)` pairs
through the real write protocol, lets the output reach its periodic steady
state, then counts `pwm_out` high-cycles over an exact whole number of periods
and asserts the count equals the expected on-time `t_on = floor(period*duty/100)`
per period. Because `pwm_out` is periodic with `period`, counting over `K*period`
cycles yields exactly `K*t_on` highs for any phase — so the oracle needs no
peeking into DUT internals. It also verifies `out_en=0` forces the output low.
Cases: 25%, 50%, 75%, 10% at period 100, and 50% at period 60. Target:
`TEST PASSED`, then synthesize to GDS on sky130hd.
