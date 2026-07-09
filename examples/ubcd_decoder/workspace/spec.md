# Universal BCD / Seven-Segment Decoder

A combinational decoder that maps a 4-bit `value` to the seven segments of a
display. A 3-bit `version` input selects the glyph family: `000` is the standard
decimal font, `111` is hexadecimal (0-9, A-F), and the codes in between
reproduce a range of vintage calculator/instrument fonts (TI, NatSemi, Toshiba,
Electronika, Code B, and more). Lamp-test (`LT`), blanking (`BI`), active-level
(`AL`) and ripple-blanking (`RBI`) controls plus glyph-variant selects
(`X6`/`X7`/`X9`) shape the output the way classic BCD-to-seven-segment driver
ICs did.

## Attribution
The RTL is adapted from the **Tiny Tapeout project "ubcd"** by Rebecca G.
Bettencourt (https://github.com/RebeccaRGB/ubcd, commit
`b16f134182bcca003b459584bde786ec9539d82a`), licensed **Apache-2.0** (full text
in `LICENSE` at the bundle root). The upstream project muxes four decoders (BCD,
ASCII, Cistercian, Kaktovik) behind the fixed Tiny Tapeout pin interface; this
bundle uses the `universal_bcd_decoder` submodule directly as the top with its
own clean ports, kept verbatim except for a single portability edit
(SystemVerilog `always_comb` -> Verilog-2001 `always @(*)`; no logic changed).
The self-checking testbench is original to this bundle.

## Interface
| Signal        | Dir | Width | Description                                    |
|---------------|-----|-------|------------------------------------------------|
| A, B, C, D    | in  | 1 ea  | 4-bit code to decode (`value = {D,C,B,A}`)     |
| V0, V1, V2    | in  | 1 ea  | 3-bit glyph-family select (`version`)          |
| X6, X7, X9    | in  | 1 ea  | Glyph-variant selects for 6/7/9               |
| RBI           | in  | 1     | Ripple-blanking in (leading-zero blank)        |
| LT            | in  | 1     | Lamp test (all segments) when low              |
| BI            | in  | 1     | Blanking (all segments off) when low           |
| AL            | in  | 1     | Active level of the segment outputs            |
| Qa..Qg        | out | 1 ea  | Seven segment outputs                          |
| RBO           | out | 1     | Ripple-blanking out                            |

## Verification
An original self-checking testbench holds the control lines transparent
(LT=BI=AL=RBI=1, X6=1, X7=0, X9=0) so each segment output equals the decoded
value, and checks two glyph families against the well-known seven-segment hex
font (an oracle independent of the DUT's decode table): the **full BCD range
0-9** in decimal mode (version 000) and a **sample of extended codes A-F** in
hexadecimal mode (version 111). Target: `TEST PASSED`, then synthesize to GDS on
sky130hd.
