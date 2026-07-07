# 4-bit ALU (registered)

A compact 4-bit arithmetic/logic unit. Each clock it applies one of nine
operations to two 4-bit operands `a`, `b` selected by `opcode`, and registers
an 8-bit `result` plus `carry_out` / `overflow` status flags. Active-low reset
`rst_n` clears the result and flags.

## Attribution
The RTL is adapted from a Tiny Tapeout TT08 project,
**`Richard28277/4bit_alu`** (https://github.com/Richard28277/4bit_alu, commit
`fa2297666160eec4a520bfe3d236cf8fba00f93a`), licensed **Apache-2.0** (full text
in `LICENSE` at the bundle root). The original wraps the ALU in the fixed Tiny
Tapeout pin interface (`ui_in`/`uo_out`/`uio_*`/`ena`) — operands packed into
`ui_in`, opcode carried on the bidirectional `uio` input bus, and carry/overflow
returned on `uio_out[6]`/`[7]` with `uio_oe` direction bits. This bundle exposes
the real datapath ports (`a`, `b`, `opcode` -> `result`, `carry_out`,
`overflow`) and drops the `uio` direction plumbing; the operation logic,
encodings, result packing, and the reset behavior are kept verbatim. The
self-checking testbench is original to this bundle.

## Interface
| Signal    | Dir | Width | Description                                     |
|-----------|-----|-------|-------------------------------------------------|
| clk       | in  | 1     | Clock                                           |
| rst_n     | in  | 1     | Active-low reset (result & flags -> 0)          |
| a         | in  | 4     | Operand A                                       |
| b         | in  | 4     | Operand B                                       |
| opcode    | in  | 4     | Operation select (see table)                    |
| result    | out | 8     | Registered result                               |
| carry_out | out | 1     | ADD carry / SUB borrow-bar (valid for ADD/SUB)  |
| overflow  | out | 1     | Signed overflow (valid for ADD/SUB)             |

## Operations
| opcode | Name | result                                              |
|--------|------|-----------------------------------------------------|
| 0000   | ADD  | `{4'b0, (a+b)[3:0]}`, `carry_out`=`(a+b)[4]`         |
| 0001   | SUB  | `{4'b0, (a-b)[3:0]}`, `carry_out`=`~borrow`          |
| 0010   | MUL  | `a * b` (full 8-bit product)                        |
| 0011   | DIV  | `{a % b, a / b}` (0 when `b==0`)                     |
| 0100   | AND  | `{4'b0, a & b}`                                      |
| 0101   | OR   | `{4'b0, a \| b}`                                     |
| 0110   | XOR  | `{4'b0, a ^ b}`                                      |
| 0111   | NOT  | `{4'b0, ~a}` (unary)                                 |
| 1000   | ENC  | `((a<<4) \| b) ^ 8'hAB` (toy XOR "encrypt")          |

`carry_out` and `overflow` are meaningful only for ADD and SUB; other ops leave
those flag registers unchanged.

## Verification
An original self-checking testbench sweeps **every opcode over all 256 `(a,b)`
operand pairs** (2304 vectors). Its oracle is an independent golden model
computed from the operand+opcode by plain integer arithmetic — it does not read
the DUT internals. Each cycle it drives the inputs, waits one clock for the
registered output, and checks `result`; for ADD and SUB it additionally checks
`carry_out` and `overflow`. Target: `TEST PASSED`, then synthesize to GDS on
sky130hd.
