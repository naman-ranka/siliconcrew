`timescale 1ns/1ps
// Self-checking testbench: drives a serial bit stream (with back-to-back and
// overlapping occurrences of 0011) and checks `detected` against an independent
// reference window every cycle. Emits "TEST PASSED" only on a fully clean run.
module seq_detector_0011_tb;
    reg  clk = 1'b0;
    reg  rst_n = 1'b0;
    reg  din = 1'b0;
    wire detected;

    integer i;
    integer errors = 0;
    reg [3:0] ref_win;
    // 40-bit stimulus, MSB-first, exercising 0011, overlap (001011), and gaps.
    reg [39:0] vec = 40'b0011001100010110011000110011001100110011;

    seq_detector_0011 dut (.clk(clk), .rst_n(rst_n), .din(din), .detected(detected));

    always #5 clk = ~clk;

    initial begin
        $dumpfile("seq_detector_0011_tb.vcd");
        $dumpvars(0, seq_detector_0011_tb);

        rst_n = 1'b0;
        ref_win = 4'b0000;
        repeat (2) @(negedge clk);
        rst_n = 1'b1;

        for (i = 0; i < 40; i = i + 1) begin
            @(negedge clk);
            din = vec[39 - i];        // feed MSB first
            @(posedge clk);
            #1;
            ref_win = {ref_win[2:0], din};   // independent reference model
            if (detected !== (ref_win == 4'b0011)) begin
                errors = errors + 1;
                $display("ERROR i=%0d din=%b detected=%b expected=%b win=%b",
                         i, din, detected, (ref_win == 4'b0011), ref_win);
            end
        end

        if (errors == 0) $display("TEST PASSED");
        else             $display("TEST FAILED with %0d error(s)", errors);
        $finish;
    end
endmodule
