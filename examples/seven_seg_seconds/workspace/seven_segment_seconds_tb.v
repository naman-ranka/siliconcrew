`timescale 1ns/1ps
`default_nettype none
// Self-checking testbench for the seven-segment seconds counter. Uses a tiny
// MAX_COUNT so the BCD digit ticks quickly. The oracle is INDEPENDENT of the
// DUT's internal counter: the expected digit at in-loop sample k is the closed
// form floor(k / (MAX_COUNT+1)) % 10, and the expected segment pattern comes
// from a golden 7-seg table (the spec's encoding). Every clock it checks the
// segments equal the golden decode of the expected digit; it also asserts the
// digit actually reached 9 and wrapped back to 0. Emits "TEST PASSED" only when
// every check holds.
module seven_segment_seconds_tb;
    localparam [23:0] MAX_COUNT = 24'd3;   // digit holds MAX_COUNT+1 = 4 clocks
    localparam integer HOLD = 4;           // MAX_COUNT + 1

    reg        clk = 1'b0;
    reg        rst_n = 1'b0;
    wire [6:0] seg;

    integer errors = 0;
    integer k;
    integer exp_digit;
    reg [6:0] golden [0:9];
    integer saw9 = 0;
    integer wrapped = 0;
    integer prev_digit;

    seven_segment_seconds #(.MAX_COUNT(MAX_COUNT)) dut (
        .clk(clk), .rst_n(rst_n), .seg(seg)
    );

    always #5 clk = ~clk;

    initial begin
        // Golden 7-seg encodings for digits 0-9 (independent oracle).
        golden[0] = 7'b0111111;
        golden[1] = 7'b0000110;
        golden[2] = 7'b1011011;
        golden[3] = 7'b1001111;
        golden[4] = 7'b1100110;
        golden[5] = 7'b1101101;
        golden[6] = 7'b1111101;
        golden[7] = 7'b0000111;
        golden[8] = 7'b1111111;
        golden[9] = 7'b1101111;

        $dumpfile("seven_segment_seconds_tb.vcd");
        $dumpvars(0, seven_segment_seconds_tb);

        rst_n = 1'b0;
        repeat (2) @(negedge clk);
        rst_n = 1'b1;

        prev_digit = 0;
        // Run through more than two full 0-9 cycles.
        for (k = 1; k <= 3*10*HOLD; k = k + 1) begin
            @(posedge clk); #1;
            exp_digit = (k / HOLD) % 10;

            if (seg !== golden[exp_digit]) begin
                errors = errors + 1;
                $display("ERROR@%0t k=%0d: seg=%b expected digit %0d -> %b",
                         $time, k, seg, exp_digit, golden[exp_digit]);
            end
            if (exp_digit == 9) saw9 = 1;
            if (prev_digit == 9 && exp_digit == 0) wrapped = 1;
            prev_digit = exp_digit;
        end

        if (!saw9)    begin errors = errors + 1; $display("ERROR: digit never reached 9"); end
        if (!wrapped) begin errors = errors + 1; $display("ERROR: digit never wrapped 9 -> 0"); end

        if (errors == 0) $display("TEST PASSED");
        else             $display("TEST FAILED with %0d error(s)", errors);
        $finish;
    end
endmodule
