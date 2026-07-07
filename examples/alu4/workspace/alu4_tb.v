`timescale 1ns/1ps
`default_nettype none
// Self-checking testbench for the 4-bit ALU (alu4).
//
// This testbench is ORIGINAL to this bundle. Its oracle is an INDEPENDENT
// golden model computed from the operand/opcode alone (plain integer math), not
// from the DUT's internals. It exhaustively sweeps every opcode over all 256
// (a,b) operand pairs. Each cycle it drives (a,b,opcode), waits one clock for
// the DUT's registered result, and asserts:
//   * result[7:0] matches the golden packing for that op, and
//   * carry_out / overflow match the golden flags for ADD and SUB (the only ops
//     that define them; other ops leave the flag registers unchanged, so they
//     are intentionally not checked there).
// Emits "TEST PASSED" only when every check across the full sweep holds.
module alu4_tb;
    // Opcodes (mirror the DUT encodings).
    localparam [3:0] ADD = 4'b0000, SUB = 4'b0001, MUL = 4'b0010, DIV = 4'b0011,
                     AND = 4'b0100, OR  = 4'b0101, XOR = 4'b0110, NOT = 4'b0111,
                     ENC = 4'b1000;
    localparam [7:0] ENCRYPTION_KEY = 8'hAB;

    reg        clk = 1'b0;
    reg        rst_n = 1'b0;
    reg  [3:0] a = 4'd0, b = 4'd0, opcode = 4'd0;
    wire [7:0] result;
    wire       carry_out, overflow;

    integer errors = 0;
    integer oi, ai, bi;
    integer checks = 0;

    // Golden expectations for the pending (a,b,opcode).
    reg [7:0] exp_result;
    reg       exp_carry, exp_overflow, check_flags;

    // Opcode list to sweep.
    reg [3:0] ops [0:8];

    alu4 dut (
        .clk(clk), .rst_n(rst_n), .a(a), .b(b), .opcode(opcode),
        .result(result), .carry_out(carry_out), .overflow(overflow)
    );

    always #5 clk = ~clk;

    // Compute the golden result/flags for a given operand+opcode.
    task golden;
        input [3:0] ga, gb, gop;
        reg [4:0] add5, sub5;
        reg [3:0] quot, rem;
        begin
            add5 = ga + gb;
            sub5 = ga - gb;
            check_flags  = 1'b0;
            exp_carry    = 1'b0;
            exp_overflow = 1'b0;
            case (gop)
                ADD: begin
                    exp_result   = {4'b0000, add5[3:0]};
                    exp_carry    = add5[4];
                    exp_overflow = (ga[3] & gb[3] & ~add5[3]) |
                                   (~ga[3] & ~gb[3] & add5[3]);
                    check_flags  = 1'b1;
                end
                SUB: begin
                    exp_result   = {4'b0000, sub5[3:0]};
                    exp_carry    = ~sub5[4];
                    exp_overflow = (ga[3] & ~gb[3] & ~sub5[3]) |
                                   (~ga[3] & gb[3] & sub5[3]);
                    check_flags  = 1'b1;
                end
                MUL: exp_result = ga * gb;
                DIV: begin
                    quot = (gb != 0) ? (ga / gb) : 4'd0;
                    rem  = (gb != 0) ? (ga % gb) : 4'd0;
                    exp_result = {rem, quot};
                end
                AND: exp_result = {4'b0000, (ga & gb)};
                OR:  exp_result = {4'b0000, (ga | gb)};
                XOR: exp_result = {4'b0000, (ga ^ gb)};
                NOT: exp_result = {4'b0000, (~ga)};
                ENC: exp_result = ((ga << 4) | gb) ^ ENCRYPTION_KEY;
                default: exp_result = 8'b0;
            endcase
        end
    endtask

    initial begin
        ops[0]=ADD; ops[1]=SUB; ops[2]=MUL; ops[3]=DIV;
        ops[4]=AND; ops[5]=OR;  ops[6]=XOR; ops[7]=NOT; ops[8]=ENC;

        $dumpfile("alu4_tb.vcd");
        $dumpvars(0, alu4_tb);

        // Reset.
        rst_n = 1'b0;
        a = 0; b = 0; opcode = 0;
        repeat (2) @(negedge clk);
        rst_n = 1'b1;

        for (oi = 0; oi < 9; oi = oi + 1) begin
            for (ai = 0; ai < 16; ai = ai + 1) begin
                for (bi = 0; bi < 16; bi = bi + 1) begin
                    // Drive inputs; capture golden for THIS vector.
                    a      = ai[3:0];
                    b      = bi[3:0];
                    opcode = ops[oi];
                    golden(ai[3:0], bi[3:0], ops[oi]);

                    @(posedge clk);   // DUT registers result on this edge
                    #1;               // let outputs settle
                    checks = checks + 1;

                    if (result !== exp_result) begin
                        errors = errors + 1;
                        if (errors <= 20)
                            $display("ERROR@%0t op=%b a=%0d b=%0d: result=%b exp=%b",
                                     $time, opcode, a, b, result, exp_result);
                    end
                    if (check_flags) begin
                        if (carry_out !== exp_carry) begin
                            errors = errors + 1;
                            if (errors <= 20)
                                $display("ERROR@%0t op=%b a=%0d b=%0d: carry=%b exp=%b",
                                         $time, opcode, a, b, carry_out, exp_carry);
                        end
                        if (overflow !== exp_overflow) begin
                            errors = errors + 1;
                            if (errors <= 20)
                                $display("ERROR@%0t op=%b a=%0d b=%0d: ovf=%b exp=%b",
                                         $time, opcode, a, b, overflow, exp_overflow);
                        end
                    end
                end
            end
        end

        if (checks < 9*16*16) begin
            errors = errors + 1;
            $display("ERROR: only %0d checks ran (expected %0d)", checks, 9*16*16);
        end

        if (errors == 0) $display("TEST PASSED (%0d vectors checked)", checks);
        else             $display("TEST FAILED with %0d error(s)", errors);
        $finish;
    end
endmodule
