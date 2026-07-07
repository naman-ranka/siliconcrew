`timescale 1ns/1ps
`default_nettype none
// Self-checking testbench for the universal BCD / seven-segment decoder.
//
// Two glyph families are exercised with an INDEPENDENT golden oracle -- the
// well-known common-cathode seven-segment hex font (segment bit order
// {g,f,e,d,c,b,a}), which is knowledge external to the DUT's casez table:
//
//   * version 000 (standard decimal): the full BCD range 0..9;
//   * version 111 (hexadecimal): a sample of the extended codes A..F.
//
// Control lines are held at their transparent values (LT=1 lamp-test off,
// BI=1 blanking off, AL=1 active-high, RBI=1 ripple-blank off) so each active
// segment Qx equals the decoded data bit; the glyph-variant selects are fixed
// (X6=1, X7=0, X9=0) and the golden table is chosen to match. Emits
// "TEST PASSED" only when every checked code matches.
module ubcd_tb;
    reg A, B, C, D, V0, V1, V2;
    reg X6, X7, X9, RBI, LT, BI, AL;
    wire Qa, Qb, Qc, Qd, Qe, Qf, Qg, RBO;

    wire [6:0] seg = {Qg, Qf, Qe, Qd, Qc, Qb, Qa};

    reg [6:0] golden_dec [0:9];
    reg [6:0] golden_hex [0:5];   // codes 10..15 -> A..F

    integer errors = 0;
    integer checks = 0;
    integer v;

    universal_bcd_decoder dut (
        .A(A), .B(B), .C(C), .D(D), .V0(V0), .V1(V1), .V2(V2),
        .X6(X6), .X7(X7), .X9(X9), .RBI(RBI), .LT(LT), .BI(BI), .AL(AL),
        .Qa(Qa), .Qb(Qb), .Qc(Qc), .Qd(Qd), .Qe(Qe), .Qf(Qf), .Qg(Qg), .RBO(RBO)
    );

    initial begin
        $dumpfile("ubcd_tb.vcd");
        $dumpvars(0, ubcd_tb);

        // Independent golden seven-segment hex font ({g,f,e,d,c,b,a}).
        golden_dec[0] = 7'h3F;
        golden_dec[1] = 7'h06;
        golden_dec[2] = 7'h5B;
        golden_dec[3] = 7'h4F;
        golden_dec[4] = 7'h66;
        golden_dec[5] = 7'h6D;
        golden_dec[6] = 7'h7D;   // X6=1 variant (with top bar)
        golden_dec[7] = 7'h07;   // X7=0 variant
        golden_dec[8] = 7'h7F;
        golden_dec[9] = 7'h67;   // X9=0 variant (no bottom bar)
        golden_hex[0] = 7'h77;   // A
        golden_hex[1] = 7'h7C;   // b
        golden_hex[2] = 7'h39;   // C
        golden_hex[3] = 7'h5E;   // d
        golden_hex[4] = 7'h79;   // E
        golden_hex[5] = 7'h71;   // F

        // Transparent control levels + fixed glyph variants.
        LT = 1'b1; BI = 1'b1; AL = 1'b1; RBI = 1'b1;
        X6 = 1'b1; X7 = 1'b0; X9 = 1'b0;

        // --- Standard decimal (version 000): exhaustive BCD range 0..9 ---
        {V2, V1, V0} = 3'b000;
        for (v = 0; v <= 9; v = v + 1) begin
            {D, C, B, A} = v[3:0];
            #1;
            checks = checks + 1;
            if (seg !== golden_dec[v]) begin
                errors = errors + 1;
                $display("ERROR dec %0d: seg=%b expected=%b", v, seg, golden_dec[v]);
            end
        end

        // --- Hexadecimal (version 111): sample of extended codes A..F ---
        {V2, V1, V0} = 3'b111;
        for (v = 10; v <= 15; v = v + 1) begin
            {D, C, B, A} = v[3:0];
            #1;
            checks = checks + 1;
            if (seg !== golden_hex[v-10]) begin
                errors = errors + 1;
                $display("ERROR hex %0d: seg=%b expected=%b", v, seg, golden_hex[v-10]);
            end
        end

        if (checks != 16) begin
            errors = errors + 1;
            $display("ERROR: expected 16 checks, ran %0d", checks);
        end

        if (errors == 0) $display("TEST PASSED (%0d codes)", checks);
        else             $display("TEST FAILED with %0d error(s)", errors);
        $finish;
    end
endmodule
