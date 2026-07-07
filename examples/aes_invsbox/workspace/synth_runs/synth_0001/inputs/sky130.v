// Portable behavioral standard-cell library for the AES inverse S-box.
//
// From the Tiny Tapeout project "AES inverse S-box"
//   repo:    https://github.com/daosvik/tt08-aes-invsbox  (src/sky130.v)
//   commit:  e78636840df3af0a11027db7fe2a0d3a82821521
//   author:  Dag Arne Osvik
//   license: Apache-2.0 (see LICENSE in this bundle)
//
// Cell names mirror the Sky130 PDK but the bodies are plain behavioral Verilog,
// so the gate-level S-box is portable to any flow; synthesis maps these onto the
// target library. ONE adaptation for this bundle: the upstream `keep_hierarchy`
// attribute on each cell module was removed so the standard sky130hd flow
// flattens the design and reports true (flattened) PPA. No cell logic changed.
//
/*
   Verilog modules for standard cells.

   (Upstream note, retained for provenance: the modules originally carried a
   keep_hierarchy attribute to prevent synthesis from modifying the structure of
   the logic built from them. This bundle removes that attribute — see the
   adaptation note above.)

   Module names are consistent with the Sky130 PDK, but the modules are
   portable to other PDKs, though not necessarily matching their gates.

   Copyright 2024 Dag Arne Osvik

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
*/

module a2111o (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  c0,
    input wire  d0,
    output wire y);

    assign y = (a0 & a1) | b0 | c0 | d0;
endmodule

module a2111oi (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  c0,
    input wire  d0,
    output wire y);

    assign y = ~((a0 & a1) | b0 | c0 | d0);
endmodule

module a211o (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  c0,
    output wire y);

    assign y = (a0 & a1) | b0 | c0;
endmodule

module a211oi (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  c0,
    output wire y);

    assign y = ~((a0 & a1) | b0 | c0);
endmodule

module a21bo (
    input wire  a0,
    input wire  a1,
    input wire  b0n,
    output wire y);

    assign y = (a0 & a1) | ~b0n;
endmodule

module a21boi (
    input wire  a0,
    input wire  a1,
    input wire  b0n,
    output wire y);

    assign y = ~((a0 & a1) | ~b0n);
endmodule

module a21o (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    output wire y);

    assign y = (a0 & a1) | b0;
endmodule

module a21oi (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    output wire y);

    assign y = ~((a0 & a1) | b0);
endmodule

module a221o (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  b1,
    input wire  c0,
    output wire y);

    assign y = (a0 & a1) | (b0 & b1) | c0;
endmodule

module a221oi (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  b1,
    input wire  c0,
    output wire y);

    assign y = ~((a0 & a1) | (b0 & b1) | c0);
endmodule

module a222oi (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  b1,
    input wire  c0,
    input wire  c1,
    output wire y);

    assign y = ~((a0 & a1) | (b0 & b1) | (c0 & c1));
endmodule

module a22o (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  b1,
    output wire y);

    assign y = (a0 & a1) | (b0 & b1);
endmodule

module a22oi (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  b1,
    output wire y);

    assign y = ~((a0 & a1) | (b0 & b1));
endmodule

module a2bb2o (
    input wire  a0n,
    input wire  a1n,
    input wire  b0,
    input wire  b1,
    output wire y);

    assign y = (~a0n & ~a1n) | (b0 & b1);
endmodule

module a2bb2oi (
    input wire  a0n,
    input wire  a1n,
    input wire  b0,
    input wire  b1,
    output wire y);

    assign y = ~((~a0n & ~a1n) | (b0 & b1));
endmodule

module a311o (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  b0,
    input wire  c0,
    output wire y);

    assign y = (a0 & a1 & a2) | b0 | c0;
endmodule

module a311oi (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  b0,
    input wire  c0,
    output wire y);

    assign y = ~((a0 & a1 & a2) | b0 | c0);
endmodule

module a31o (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  b0,
    output wire y);

    assign y = (a0 & a1 & a2) | b0;
endmodule

module a31oi (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  b0,
    output wire y);

    assign y = ~((a0 & a1 & a2) | b0);
endmodule

module a32o (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  b0,
    input wire  b1,
    output wire y);

    assign y = (a0 & a1 & a2) | (b0 & b1);
endmodule

module a32oi (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  b0,
    input wire  b1,
    output wire y);

    assign y = ~((a0 & a1 & a2) | (b0 & b1));
endmodule

module a41o (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  a3,
    input wire  b0,
    output wire y);

    assign y = (a0 & a1 & a2 & a3) | b0;
endmodule

module a41oi (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  a3,
    input wire  b0,
    output wire y);

    assign y = ~((a0 & a1 & a2 & a3) | b0);
endmodule

module and2 (
    input wire  a,
    input wire  b,
    output wire y);

    assign y = a & b;
endmodule

module and2b (
    input wire  an,
    input wire  b,
    output wire y);

    assign y = ~an & b;
endmodule

module and3 (
    input wire  a,
    input wire  b,
    input wire  c,
    output wire y);

    assign y = a & b & c;
endmodule

module and3b (
    input wire  an,
    input wire  b,
    input wire  c,
    output wire y);

    assign y = ~an & b & c;
endmodule

module and4 (
    input wire  a,
    input wire  b,
    input wire  c,
    input wire  d,
    output wire y);

    assign y = a & b & c & d;
endmodule

module and4b (
    input wire  an,
    input wire  b,
    input wire  c,
    input wire  d,
    output wire y);

    assign y = ~an & b & c & d;
endmodule

module and4bb (
    input wire  an,
    input wire  bn,
    input wire  c,
    input wire  d,
    output wire y);

    assign y = ~an & ~bn & c & d;
endmodule

module inv (
    input wire  a,
    output wire y);

    assign y = ~a;
endmodule

module maj3 (
    input wire  a,
    input wire  b,
    input wire  c,
    output wire y);

    assign y = (a & b) | (a & c) | (b & c);
endmodule

module mux2 (
    input wire  s,
    input wire  a0,
    input wire  a1,
    output wire y);

    assign y = s ? a1 : a0;
endmodule

module mux2i (
    input wire  s,
    input wire  a0,
    input wire  a1,
    output wire y);

    assign y = ~(s ? a1 : a0);
endmodule

module nand2 (
    input wire  a,
    input wire  b,
    output wire y);

    assign y = ~(a & b);
endmodule

module nand2b (
    input wire  an,
    input wire  b,
    output wire y);

    assign y = ~(~an & b);
endmodule

module nand3 (
    input wire  a,
    input wire  b,
    input wire  c,
    output wire y);

    assign y = ~(a & b & c);
endmodule

module nand3b (
    input wire  an,
    input wire  b,
    input wire  c,
    output wire y);

    assign y = ~(~an & b & c);
endmodule

module nand4 (
    input wire  a,
    input wire  b,
    input wire  c,
    input wire  d,
    output wire y);

    assign y = ~(a & b & c & d);
endmodule

module nand4b (
    input wire  an,
    input wire  b,
    input wire  c,
    input wire  d,
    output wire y);

    assign y = ~(~an & b & c & d);
endmodule

module nand4bb (
    input wire  an,
    input wire  bn,
    input wire  c,
    input wire  d,
    output wire y);

    assign y = ~(~an & ~bn & c & d);
endmodule

module nor2 (
    input wire  a,
    input wire  b,
    output wire y);

    assign y = ~(a | b);
endmodule

module nor2b (
    input wire  an,
    input wire  b,
    output wire y);

    assign y = ~(~an | b);
endmodule

module nor3 (
    input wire  a,
    input wire  b,
    input wire  c,
    output wire y);

    assign y = ~(a | b | c);
endmodule

module nor3b (
    input wire  an,
    input wire  b,
    input wire  c,
    output wire y);

    assign y = ~(~an | b | c);
endmodule

module nor4 (
    input wire  a,
    input wire  b,
    input wire  c,
    input wire  d,
    output wire y);

    assign y = ~(a | b | c | d);
endmodule

module nor4b (
    input wire  an,
    input wire  b,
    input wire  c,
    input wire  d,
    output wire y);

    assign y = ~(~an | b | c | d);
endmodule

module nor4bb (
    input wire  an,
    input wire  bn,
    input wire  c,
    input wire  d,
    output wire y);

    assign y = ~(~an | ~bn | c | d);
endmodule

module o2111a (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  c0,
    input wire  d0,
    output wire y);

    assign y = (a0 | a1) & b0 & c0 & d0;
endmodule

module o2111ai (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  c0,
    input wire  d0,
    output wire y);

    assign y = ~((a0 | a1) & b0 & c0 & d0);
endmodule

module o211a (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  c0,
    output wire y);

    assign y = (a0 | a1) & b0 & c0;
endmodule

module o211ai (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  c0,
    output wire y);

    assign y = ~((a0 | a1) & b0 & c0);
endmodule

module o21a (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    output wire y);

    assign y = (a0 | a1) & b0;
endmodule

module o21ai (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    output wire y);

    assign y = ~((a0 | a1) & b0);
endmodule

module o21ba (
    input wire  a0,
    input wire  a1,
    input wire  b0n,
    output wire y);

    assign y = (a0 | a1) & ~b0n;
endmodule

module o21bai (
    input wire  a0,
    input wire  a1,
    input wire  b0n,
    output wire y);

    assign y = ~((a0 | a1) & ~b0n);
endmodule

module o221a (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  b1,
    input wire  c0,
    output wire y);

    assign y = (a0 | a1) & (b0 | b1) & c0;
endmodule

module o221ai (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  b1,
    input wire  c0,
    output wire y);

    assign y = ~((a0 | a1) & (b0 | b1) & c0);
endmodule

module o22a (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  b1,
    output wire y);

    assign y = (a0 | a1) & (b0 | b1);
endmodule

module o22ai (
    input wire  a0,
    input wire  a1,
    input wire  b0,
    input wire  b1,
    output wire y);

    assign y = ~((a0 | a1) & (b0 | b1));
endmodule

module o2bb2a (
    input wire  a0n,
    input wire  a1n,
    input wire  b0,
    input wire  b1,
    output wire y);

    assign y = (~a0n | ~a1n) & (b0 | b1);
endmodule

module o2bb2ai (
    input wire  a0n,
    input wire  a1n,
    input wire  b0,
    input wire  b1,
    output wire y);

    assign y = ~((~a0n | ~a1n) & (b0 | b1));
endmodule

module o311a (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  b0,
    input wire  c0,
    output wire y);

    assign y = (a0 | a1 | a2) & b0 & c0;
endmodule

module o311ai (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  b0,
    input wire  c0,
    output wire y);

    assign y = ~((a0 | a1 | a2) & b0 & c0);
endmodule

module o31a (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  b0,
    output wire y);

    assign y = (a0 | a1 | a2) & b0;
endmodule

module o31ai (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  b0,
    output wire y);

    assign y = ~((a0 | a1 | a2) & b0);
endmodule

module o32a (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  b0,
    input wire  b1,
    output wire y);

    assign y = (a0 | a1 | a2) & (b0 | b1);
endmodule

module o32ai (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  b0,
    input wire  b1,
    output wire y);

    assign y = ~((a0 | a1 | a2) & (b0 | b1));
endmodule

module o41a (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  a3,
    input wire  b0,
    output wire y);

    assign y = (a0 | a1 | a2 | a3) & b0;
endmodule

module o41ai (
    input wire  a0,
    input wire  a1,
    input wire  a2,
    input wire  a3,
    input wire  b0,
    output wire y);

    assign y = ~((a0 | a1 | a2 | a3) & b0);
endmodule

module or2 (
    input wire  a,
    input wire  b,
    output wire y);

    assign y = a | b;
endmodule

module or2b (
    input wire  an,
    input wire  b,
    output wire y);

    assign y = ~an | b;
endmodule

module or3 (
    input wire  a,
    input wire  b,
    input wire  c,
    output wire y);

    assign y = a | b | c;
endmodule

module or3b (
    input wire  an,
    input wire  b,
    input wire  c,
    output wire y);

    assign y = ~an | b | c;
endmodule

module or4 (
    input wire  a,
    input wire  b,
    input wire  c,
    input wire  d,
    output wire y);

    assign y = a | b | c | d;
endmodule

module or4b (
    input wire  an,
    input wire  b,
    input wire  c,
    input wire  d,
    output wire y);

    assign y = ~an | b | c | d;
endmodule

module or4bb (
    input wire  an,
    input wire  bn,
    input wire  c,
    input wire  d,
    output wire y);

    assign y = ~an | ~bn | c | d;
endmodule

module xnor2 (
    input wire  a,
    input wire  b,
    output wire y);

    assign y = ~(a ^ b);
endmodule

module xnor3 (
    input wire  a,
    input wire  b,
    input wire  c,
    output wire y);

    assign y = ~(a ^ b ^ c);
endmodule

module xor2 (
    input wire  a,
    input wire  b,
    output wire y);

    assign y = a ^ b;
endmodule

module xor3 (
    input wire  a,
    input wire  b,
    input wire  c,
    output wire y);

    assign y = a ^ b ^ c;
endmodule
