`timescale 1ns/1ps
`default_nettype none
// Self-checking testbench for the 4-bit carry-lookahead adder.
//
// Exhaustive sweep: every (a, b, ci) in 16 x 16 x 2 = 512 input vectors. The
// oracle is a plain integer add (independent of the DUT's lookahead network):
// for each vector the expected 5-bit result is a + b + ci, checked against the
// registered {co, s}. Emits "TEST PASSED" only when all 512 vectors match.
module cla4_tb;
    reg        clk = 1'b0;
    reg        rst_n = 1'b0;
    reg  [3:0] a = 4'd0;
    reg  [3:0] b = 4'd0;
    reg        ci = 1'b0;
    wire [3:0] s;
    wire       co;

    integer errors = 0;
    integer checks = 0;
    integer ia, ib, ic;
    reg [4:0] expected;

    cla4 dut (.clk(clk), .rst_n(rst_n), .a(a), .b(b), .ci(ci), .s(s), .co(co));

    always #5 clk = ~clk;

    initial begin
        $dumpfile("cla4_tb.vcd");
        $dumpvars(0, cla4_tb);

        // reset
        rst_n = 1'b0;
        repeat (2) @(negedge clk);
        rst_n = 1'b1;

        for (ia = 0; ia < 16; ia = ia + 1)
          for (ib = 0; ib < 16; ib = ib + 1)
            for (ic = 0; ic < 2; ic = ic + 1) begin
                a  = ia[3:0];
                b  = ib[3:0];
                ci = ic[0];
                @(posedge clk);   // register samples the applied inputs
                #1;               // let the registered outputs settle
                expected = ia[4:0] + ib[4:0] + ic[4:0];
                checks = checks + 1;
                if ({co, s} !== expected) begin
                    errors = errors + 1;
                    if (errors <= 10)
                        $display("ERROR a=%0d b=%0d ci=%0d: {co,s}=%b expected=%b",
                                 ia, ib, ic, {co, s}, expected);
                end
            end

        if (checks != 512) begin
            errors = errors + 1;
            $display("ERROR: expected 512 vectors, ran %0d", checks);
        end

        if (errors == 0) $display("TEST PASSED (%0d vectors)", checks);
        else             $display("TEST FAILED with %0d error(s)", errors);
        $finish;
    end
endmodule
