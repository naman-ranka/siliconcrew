# 4x4 Array Multiplier

A purely combinational **4-bit x 4-bit unsigned array multiplier** producing an
8-bit product. Each partial product is an AND of one bit of `a` with one bit of
`b`; the partial products are summed by a diagonal tree of full adders — the
classic array-multiplier structure, a compact datapath tile.

## Attribution
The multiplier RTL (the AND-array and full-adder tree) is adapted from the Tiny
Tapeout TT06 project **`Array-multiplier`** by UACJ Group A
(https://github.com/HHRB98/Array-multiplier, commit
`f5291c90038acf79065f3d48129c7e8ce8fe0348`), licensed **Apache-2.0** (repo
`LICENSE` and the `SPDX-License-Identifier: Apache-2.0` header on `src/project.v`;
full LICENSE copied to the bundle root, origin repo+commit recorded here, in
`template.json`, and in a header on the RTL file).

**Adaptation.** The upstream design wraps the multiplier in the fixed Tiny
Tapeout pin interface (`ui_in[3:0]=a`, `ui_in[7:4]=b`, `uo_out=product`) and
carries a dead reset flip-flop. This bundle drops the pin wrapper and the unused
flip-flop, exposing real named ports (`a`, `b` → `p`). The AND-array and
full-adder tree (the actual multiplier) and the `FA` full-adder cell are kept
verbatim. The self-checking testbench (`array_multiplier_tb.v`) is **original**
to this bundle.

## Interface (`array_multiplier`)
| Signal | Dir | Width | Description                  |
|--------|-----|-------|------------------------------|
| a      | in  | 4     | Unsigned multiplicand        |
| b      | in  | 4     | Unsigned multiplier          |
| p      | out | 8     | Product `p = a * b`          |

## Verification
The original self-checking testbench is **exhaustive**: it drives all
16 x 16 = 256 input combinations and asserts the 8-bit product equals `a*b`
computed independently. On success it prints `TEST PASSED (256/256 products
correct)`. The design is then synthesized to GDSII on sky130hd.
