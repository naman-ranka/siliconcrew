`timescale 1ns/1ps
// Self-checking testbench for the configurable PWM generator.
//
// This testbench is ORIGINAL to this bundle. Its oracle is INDEPENDENT of the
// DUT internals: for a commanded (period, duty%) it programs the two config
// registers through the real write protocol (sel/wr_en), lets the output reach
// its periodic steady state, then counts pwm_out high-cycles over an exact whole
// number of periods and asserts the measured high-count equals the expected
// on-time  t_on = floor(period*duty/100)  per period. Because pwm_out is
// periodic with `period`, counting over K*period cycles yields exactly K*t_on
// highs for ANY phase, so the check needs no hierarchical peeking. It also
// checks that out_en=0 forces the output low. Emits "TEST PASSED" only if every
// commanded duty is reproduced.
module pwm_generator_tb;
    reg         clk = 1'b0;
    reg         rst_n = 1'b0;
    reg  [11:0] in = 12'd0;
    reg         sel = 1'b0, wr_en = 1'b0, out_en = 1'b0;
    wire        pwm_out;

    integer errors = 0;
    integer i, highs;
    localparam integer K = 3;   // count over K full periods

    pwm_generator dut (
        .in(in), .sel(sel), .wr_en(wr_en), .out_en(out_en),
        .clk(clk), .rst_n(rst_n), .pwm_out(pwm_out)
    );

    always #10 clk = ~clk;   // 50 MHz

    // Program one register (sel=1 period, sel=0 duty) for a single clock.
    task write_reg;
        input        which;      // 1 = period, 0 = duty
        input [11:0] value;
        begin
            @(negedge clk);
            sel   = which;
            in    = value;
            wr_en = 1'b1;
            @(negedge clk);
            wr_en = 1'b0;
        end
    endtask

    // Program (period,duty), settle, then assert measured on-time per period.
    task run_case;
        input [11:0] period;
        input [11:0] duty;      // percent, 1..99
        integer exp_ton;
        begin
            // Fresh reset so the counter restarts cleanly.
            @(negedge clk); rst_n = 1'b0; out_en = 1'b0;
            repeat (3) @(negedge clk);
            rst_n = 1'b1;

            write_reg(1'b1, period);   // period_reg
            write_reg(1'b0, duty);     // duty_reg  (uses in[6:0])
            out_en = 1'b1;

            // Settle: let the counter/pwm reach the periodic steady state.
            repeat (2*period + 4) @(posedge clk);

            // Count pwm_out highs over exactly K full periods.
            highs = 0;
            for (i = 0; i < K*period; i = i + 1) begin
                @(posedge clk); #1;
                if (pwm_out) highs = highs + 1;
            end

            exp_ton = (period * duty) / 100;
            if (highs !== K*exp_ton) begin
                errors = errors + 1;
                $display("ERROR: period=%0d duty=%0d%%: measured %0d highs over %0d cycles, expected %0d (=%0d*%0d)",
                         period, duty, highs, K*period, K*exp_ton, K, exp_ton);
            end else begin
                $display("ok: period=%0d duty=%0d%% -> %0d highs / %0d cycles (t_on=%0d)",
                         period, duty, highs, K*period, exp_ton);
            end

            // out_en low must force the output low.
            out_en = 1'b0;
            @(negedge clk);
            for (i = 0; i < period; i = i + 1) begin
                @(posedge clk); #1;
                if (pwm_out !== 1'b0) begin
                    errors = errors + 1;
                    $display("ERROR: out_en=0 but pwm_out=%b at cycle %0d (period=%0d)", pwm_out, i, period);
                end
            end
        end
    endtask

    initial begin
        $dumpfile("pwm_generator_tb.vcd");
        $dumpvars(0, pwm_generator_tb);

        run_case(12'd100, 12'd25);
        run_case(12'd100, 12'd50);
        run_case(12'd100, 12'd75);
        run_case(12'd100, 12'd10);
        run_case(12'd60,  12'd50);   // t_on = 30

        if (errors == 0) $display("TEST PASSED");
        else             $display("TEST FAILED with %0d error(s)", errors);
        $finish;
    end
endmodule
