// Exhaustive self-checking testbench for the 4x4 array multiplier.
//
// Original to this SiliconCrew bundle. Drives all 256 (a, b) input combinations
// and asserts the 8-bit product equals a*b computed independently. Prints
// TEST PASSED only if every case matches.
`default_nettype none
`timescale 1ns / 1ps

module array_multiplier_tb;

  reg  [3:0] a, b;
  wire [7:0] p;
  integer    ai, bi, errors;

  array_multiplier dut (.a(a), .b(b), .p(p));

  initial begin
    $dumpfile("array_multiplier_tb.vcd");
    $dumpvars(0, array_multiplier_tb);

    errors = 0;
    for (ai = 0; ai < 16; ai = ai + 1) begin
      for (bi = 0; bi < 16; bi = bi + 1) begin
        a = ai[3:0];
        b = bi[3:0];
        #1;  // settle combinational logic
        if (p !== (a * b)) begin
          errors = errors + 1;
          $display("CHECK FAILED: %0d * %0d = %0d (expected %0d)", a, b, p, a * b);
        end
        #1;
      end
    end

    if (errors == 0)
      $display("TEST PASSED (256/256 products correct)");
    else
      $display("TEST FAILED: %0d mismatch(es)", errors);
    $finish;
  end

endmodule
