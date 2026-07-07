// 4-bit ALU with registered result and status flags.
//
// Adapted from a Tiny Tapeout TT08 project:
//   repo:    https://github.com/Richard28277/4bit_alu
//   commit:  fa2297666160eec4a520bfe3d236cf8fba00f93a
//   license: Apache-2.0 (see LICENSE in this bundle)
//
// Adaptation: the original `tt_um_Richard28277` wraps the ALU in the fixed Tiny
// Tapeout pin interface (ui_in / uo_out / uio_in / uio_out / uio_oe / ena),
// packing operands `a`,`b` into ui_in and the opcode into the bidirectional
// uio bus, and returning carry/overflow on uio_out[6]/[7]. This version exposes
// the real datapath ports (a, b, opcode -> result, carry_out, overflow) and
// drops the uio_oe direction plumbing. The operation logic, encodings, result
// packing, and the synchronous active-low reset are kept verbatim.
`default_nettype none

module alu4 (
    input  wire       clk,
    input  wire       rst_n,        // active-low synchronous-style reset
    input  wire [3:0] a,            // operand A
    input  wire [3:0] b,            // operand B
    input  wire [3:0] opcode,       // operation select (see encodings below)
    output wire [7:0] result,       // registered result
    output wire       carry_out,    // ADD carry / SUB borrow-bar (valid for ADD/SUB)
    output wire       overflow       // signed overflow (valid for ADD/SUB)
);

    // Operation encoding (verbatim from upstream).
    parameter ADD = 4'b0000;
    parameter SUB = 4'b0001;
    parameter MUL = 4'b0010;
    parameter DIV = 4'b0011;
    parameter AND = 4'b0100; // Logical AND
    parameter OR  = 4'b0101; // Logical OR
    parameter XOR = 4'b0110; // Logical XOR
    parameter NOT = 4'b0111; // Logical NOT (unary, on a)
    parameter ENC = 4'b1000; // Encryption operation

    // Encryption key (verbatim).
    parameter [7:0] ENCRYPTION_KEY = 8'hAB;

    // Combinational operation results (verbatim).
    wire [4:0] add_result;          // 5 bits to capture carry
    wire [4:0] sub_result;          // 5 bits to capture borrow
    wire [7:0] mul_result;          // 8 bits for multiplication
    wire [3:0] div_quotient;
    wire [3:0] div_remainder;
    wire [3:0] and_result = a & b;
    wire [3:0] or_result  = a | b;
    wire [3:0] xor_result = a ^ b;
    wire [3:0] not_result = ~a;

    reg  [7:0] result_r;
    reg        carry_out_r;
    reg        overflow_r;

    assign add_result   = a + b;
    assign sub_result   = a - b;
    assign mul_result   = a * b;
    assign div_quotient = (b != 0) ? a / b : 4'b0000;
    assign div_remainder= (b != 0) ? a % b : 4'b0000;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            result_r    <= 8'b0;
            carry_out_r <= 1'b0;
            overflow_r  <= 1'b0;
        end else begin
            case (opcode)
                ADD: begin
                    result_r    <= {4'b0000, add_result[3:0]};
                    carry_out_r <= add_result[4];
                    overflow_r  <= (a[3] & b[3] & ~add_result[3]) |
                                   (~a[3] & ~b[3] & add_result[3]);
                end
                SUB: begin
                    result_r    <= {4'b0000, sub_result[3:0]};
                    carry_out_r <= ~sub_result[4];
                    overflow_r  <= (a[3] & ~b[3] & ~sub_result[3]) |
                                   (~a[3] & b[3] & sub_result[3]);
                end
                MUL: result_r <= mul_result;
                DIV: result_r <= {div_remainder, div_quotient};
                AND: result_r <= {4'b0000, and_result};
                OR:  result_r <= {4'b0000, or_result};
                XOR: result_r <= {4'b0000, xor_result};
                NOT: result_r <= {4'b0000, not_result};
                ENC: result_r <= (a << 4 | b) ^ ENCRYPTION_KEY;
                default: begin
                    result_r    <= 8'b0;
                    carry_out_r <= 1'b0;
                    overflow_r  <= 1'b0;
                end
            endcase
        end
    end

    assign result    = result_r;
    assign carry_out = carry_out_r;
    assign overflow  = overflow_r;

endmodule
