`timescale 1ns/1ps
// Self-checking testbench for the sn74169 4-bit up/down counter.
//
// This testbench is ORIGINAL to this bundle. It carries an INDEPENDENT golden
// model (`exp_q`) that mirrors the '169 transition rule — synchronous load on
// LOADB=0, count up/down when ENPB=ENTB=0 (direction = U_DB), else hold — and an
// independent expectation for the active-low ripple-carry output RCOB (low at
// terminal count: Q=15 counting up, Q=0 counting down). Every clock it drives a
// control vector, advances the golden model, and asserts both Q and RCOB. It
// exercises: parallel load, a full up-count through the 15->0 wrap (with the
// RCOB terminal pulse), a full down-count through the 0->15 wrap, the hold
// (disable) mode, and load overriding an active count. Emits "TEST PASSED" only
// if every cycle matches.
module sn74169_tb;
    reg  [3:0] A = 4'd0;
    reg        U_DB = 1'b1, ENPB = 1'b1, ENTB = 1'b1, LOADB = 1'b1;
    reg        CLK = 1'b0;
    wire [3:0] Q;
    wire       RCOB;

    integer errors = 0;
    integer n;
    reg [3:0] exp_q;
    reg       exp_rcob;
    integer   started;

    sn74169 dut (
        .A(A), .U_DB(U_DB), .CLK(CLK), .ENPB(ENPB), .ENTB(ENTB),
        .LOADB(LOADB), .Q(Q), .RCOB(RCOB)
    );

    always #5 CLK = ~CLK;

    // Drive one control vector for a single clock, advance the golden model,
    // then check Q and RCOB. `started` gates checks until the first load has
    // given the golden model (and the DUT) a defined state.
    task tick;
        input [3:0] a;
        input       u_db, enpb, entb, loadb;
        begin
            @(negedge CLK);
            A = a; U_DB = u_db; ENPB = enpb; ENTB = entb; LOADB = loadb;

            // Golden next-state (same rule as the DUT).
            if (!loadb)
                exp_q = a;
            else if (!enpb && !entb)
                exp_q = u_db ? (exp_q + 4'd1) : (exp_q - 4'd1);
            // else hold

            @(posedge CLK); #1;

            exp_rcob = ~(( (exp_q == 4'd15) &  u_db ) |
                         ( (exp_q == 4'd0)  & ~u_db ));

            if (started) begin
                if (Q !== exp_q) begin
                    errors = errors + 1;
                    $display("ERROR@%0t: Q=%b expected %b (u=%b enpb=%b entb=%b loadb=%b)",
                             $time, Q, exp_q, u_db, enpb, entb, loadb);
                end
                if (RCOB !== exp_rcob) begin
                    errors = errors + 1;
                    $display("ERROR@%0t: RCOB=%b expected %b (Q=%b u=%b)",
                             $time, RCOB, exp_rcob, exp_q, u_db);
                end
            end
        end
    endtask

    initial begin
        $dumpfile("sn74169_tb.vcd");
        $dumpvars(0, sn74169_tb);

        started = 0;
        // Establish a known state via parallel load, then enable checks.
        tick(4'd13, 1'b1, 1'b1, 1'b1, 1'b0);   // LOAD Q=13
        started = 1;

        // Count UP: 13 -> 14 -> 15 (RCOB low here) -> 0 -> 1 -> 2 ...
        for (n = 0; n < 20; n = n + 1)
            tick(4'd0, 1'b1, 1'b0, 1'b0, 1'b1);

        // Load a low value, then count DOWN through the 0 -> 15 wrap.
        tick(4'd2, 1'b0, 1'b1, 1'b1, 1'b0);    // LOAD Q=2 (dir set to down)
        for (n = 0; n < 20; n = n + 1)
            tick(4'd0, 1'b0, 1'b0, 1'b0, 1'b1);

        // HOLD: disable via ENPB (and via ENTB) — Q must not change.
        tick(4'd9, 1'b1, 1'b1, 1'b1, 1'b0);    // LOAD Q=9
        for (n = 0; n < 5; n = n + 1)
            tick(4'd0, 1'b1, 1'b1, 1'b0, 1'b1); // ENPB=1 -> hold
        for (n = 0; n < 5; n = n + 1)
            tick(4'd0, 1'b1, 1'b0, 1'b1, 1'b1); // ENTB=1 -> hold

        // LOAD overrides an active count enable.
        tick(4'd7, 1'b1, 1'b0, 1'b0, 1'b0);    // LOADB=0 wins over enable -> Q=7

        if (errors == 0) $display("TEST PASSED");
        else             $display("TEST FAILED with %0d error(s)", errors);
        $finish;
    end
endmodule
