`timescale 1ns/1ps
// Self-checking testbench: verifies maximal length. Over 255 enabled clocks the
// state must (a) never be zero and (b) return to the 0xFF seed exactly at step
// 255 (full period). Emits "TEST PASSED" only when both hold.
module lfsr8_tb;
    reg        clk = 1'b0;
    reg        rst_n = 1'b0;
    reg        en = 1'b0;
    wire [7:0] state;

    integer i;
    integer errors = 0;
    integer period = 0;

    lfsr8 dut (.clk(clk), .rst_n(rst_n), .en(en), .state(state));
    always #5 clk = ~clk;

    initial begin
        $dumpfile("lfsr8_tb.vcd");
        $dumpvars(0, lfsr8_tb);

        rst_n = 1'b0; en = 1'b0;
        repeat (2) @(negedge clk);
        rst_n = 1'b1;
        en = 1'b1;

        for (i = 1; i <= 255; i = i + 1) begin
            @(posedge clk); #1;
            if (state == 8'h00) begin
                errors = errors + 1;
                $display("ERROR: LFSR hit the all-zero lockup state at step %0d", i);
            end
            if (state == 8'hFF && period == 0) period = i;
        end

        if (period != 255) begin
            errors = errors + 1;
            $display("ERROR: period = %0d, expected 255 (not maximal-length)", period);
        end

        if (errors == 0) $display("TEST PASSED");
        else             $display("TEST FAILED with %0d error(s)", errors);
        $finish;
    end
endmodule
