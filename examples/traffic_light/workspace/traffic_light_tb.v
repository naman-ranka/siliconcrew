`timescale 1ns/1ps
// Self-checking testbench for the traffic-light FSM. Uses short phase timers so
// the full GREEN->YELLOW->RED cycle simulates quickly. Every clock it checks:
//   (a) one-hot outputs   — exactly one light is lit;
//   (b) phase durations   — each COMPLETED phase run-length equals its param;
//   (c) legal ordering    — phase advances only GREEN->YELLOW->RED->GREEN.
// The duration check is independent of the DUT's internal timer: it measures the
// run-length of each light directly. The first (reset-truncated) run is checked
// for ordering only, since sampling begins mid-phase. Emits "TEST PASSED" only
// when every check holds across several full cycles.
module traffic_light_tb;
    localparam integer G = 4, Y = 2, R = 4;

    reg  clk = 1'b0;
    reg  rst_n = 1'b0;
    wire green, yellow, red;

    integer errors = 0;
    integer i;
    integer phase;        // decoded phase this cycle: 0=G,1=Y,2=R,-1=invalid
    integer prev_phase;   // phase on the previous cycle
    integer run_len;      // consecutive cycles in the current phase
    integer completed;    // # of fully-observed phase runs checked
    integer first_run;    // 1 until we cross the first phase boundary

    traffic_light #(.GREEN_TICKS(G), .YELLOW_TICKS(Y), .RED_TICKS(R)) dut (
        .clk(clk), .rst_n(rst_n), .green(green), .yellow(yellow), .red(red)
    );

    always #5 clk = ~clk;

    // expected tick count for a decoded phase
    function integer expected_ticks(input integer p);
        case (p)
            0:       expected_ticks = G;
            1:       expected_ticks = Y;
            default: expected_ticks = R;
        endcase
    endfunction

    initial begin
        $dumpfile("traffic_light_tb.vcd");
        $dumpvars(0, traffic_light_tb);

        rst_n = 1'b0;
        repeat (2) @(negedge clk);
        rst_n = 1'b1;

        prev_phase = -2;   // force "changed" on the first sample
        run_len    = 0;
        completed  = 0;
        first_run  = 1;

        // Observe three full cycles worth of ticks.
        for (i = 0; i < 3*(G+Y+R); i = i + 1) begin
            @(posedge clk); #1;

            // decode one-hot -> phase index
            case ({red, yellow, green})
                3'b001:  phase = 0;
                3'b010:  phase = 1;
                3'b100:  phase = 2;
                default: phase = -1;
            endcase

            // (a) one-hot invariant
            if (phase == -1) begin
                errors = errors + 1;
                $display("ERROR@%0t: outputs not one-hot: g=%b y=%b r=%b",
                         $time, green, yellow, red);
            end else if (phase == prev_phase) begin
                run_len = run_len + 1;
            end else begin
                // Phase boundary (or the very first sample). prev_phase < 0 is the
                // initial entry — nothing has completed yet. The first REAL run is
                // reset-truncated (sampling began mid-phase), so it gets the
                // ordering check but not the length check; every run after is fully
                // checked.
                if (prev_phase >= 0) begin
                    // (c) legal successor: G->Y->R->G
                    if (phase != (prev_phase + 1) % 3) begin
                        errors = errors + 1;
                        $display("ERROR@%0t: illegal transition %0d -> %0d",
                                 $time, prev_phase, phase);
                    end
                    if (first_run) begin
                        first_run = 0;   // skip length check on the truncated run
                    end else begin
                        // (b) the run we just finished must equal its param
                        if (run_len != expected_ticks(prev_phase)) begin
                            errors = errors + 1;
                            $display("ERROR@%0t: phase %0d held %0d ticks, expected %0d",
                                     $time, prev_phase, run_len, expected_ticks(prev_phase));
                        end
                        completed = completed + 1;
                    end
                end
                run_len = 1;
            end
            prev_phase = phase;
        end

        // Must have actually exercised several complete phases.
        if (completed < 4) begin
            errors = errors + 1;
            $display("ERROR: only %0d complete phases observed (expected >= 4)", completed);
        end

        if (errors == 0) $display("TEST PASSED");
        else             $display("TEST FAILED with %0d error(s)", errors);
        $finish;
    end
endmodule
