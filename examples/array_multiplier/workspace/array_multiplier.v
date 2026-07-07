// 4x4 -> 8 unsigned array multiplier (AND-array + full-adder tree).
//
// Adapted from the Tiny Tapeout TT06 project Array-multiplier by UACJ Group A.
//   repo:    https://github.com/HHRB98/Array-multiplier
//   commit:  f5291c90038acf79065f3d48129c7e8ce8fe0348
//   license: Apache-2.0 (repo LICENSE + src/project.v SPDX header,
//            (c) 2024; full LICENSE shipped at the bundle root).
// Adaptation: the upstream design wraps the multiplier in the fixed Tiny Tapeout
//   pin interface (ui_in[3:0]=a, ui_in[7:4]=b, uo_out=product) and carries a
//   dead reset flip-flop. This version drops the pin wrapper and the unused FF,
//   exposing real named ports (a, b -> p). The AND-array and full-adder tree
//   (the actual multiplier) are kept verbatim. The self-checking testbench
//   (array_multiplier_tb.v) is original to this bundle.
`default_nettype none

// Full adder (verbatim from upstream).
module FA(a, b, c, s, ca);
  input  a, b, c;
  output s, ca;
  assign s  = (a ^ b ^ c);
  assign ca = ((a & b) | (b & c) | (c & a));
endmodule

module array_multiplier (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [7:0] p   // p = a * b
);

  wire [39:0] w;

  // Partial products (AND array).
  and a1(w[0], a[0], b[0]);
  and a2(w[1], a[1], b[0]);
  and a3(w[2], a[2], b[0]);
  and a4(w[3], a[3], b[0]);

  and a5(w[4], a[0], b[1]);
  and a6(w[5], a[1], b[1]);
  and a7(w[6], a[2], b[1]);
  and a8(w[7], a[3], b[1]);

  and a9(w[8], a[0], b[2]);
  and a10(w[9], a[1], b[2]);
  and a11(w[10], a[2], b[2]);
  and a12(w[11], a[3], b[2]);

  and a13(w[12], a[0], b[3]);
  and a14(w[13], a[1], b[3]);
  and a15(w[14], a[2], b[3]);
  and a16(w[15], a[3], b[3]);

  assign p[0] = w[0];

  // Full-adder reduction tree.
  FA a17(1'b0, w[1], w[4], w[16], w[17]);
  FA a18(1'b0, w[2], w[5], w[18], w[19]);
  FA a19(1'b0, w[3], w[6], w[20], w[21]);

  FA a20(w[8], w[17], w[18], w[22], w[23]);
  FA a21(w[9], w[19], w[20], w[24], w[25]);
  FA a22(w[10], w[7], w[21], w[26], w[27]);

  FA a23(w[12], w[23], w[24], w[28], w[29]);
  FA a24(w[13], w[25], w[26], w[30], w[31]);
  FA a25(w[14], w[11], w[27], w[32], w[33]);

  FA a26(1'b0, w[29], w[30], w[34], w[35]);
  FA a27(w[31], w[32], w[35], w[36], w[37]);
  FA a28(w[15], w[33], w[37], w[38], w[39]);

  assign p[1] = w[16];
  assign p[2] = w[22];
  assign p[3] = w[28];
  assign p[4] = w[34];
  assign p[5] = w[36];
  assign p[6] = w[38];
  assign p[7] = w[39];

endmodule
