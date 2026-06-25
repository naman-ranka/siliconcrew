// 4-bit ALU: add/sub/and/or/xor/not/shl/shr with zero & carry flags.
module alu4 (
    input  wire [3:0] a,
    input  wire [3:0] b,
    input  wire [2:0] op,
    output reg  [3:0] y,
    output wire       zero,
    output reg        carry
);
    always @(*) begin
        carry = 1'b0;
        case (op)
            3'd0: {carry, y} = a + b;
            3'd1: {carry, y} = a - b;
            3'd2: y = a & b;
            3'd3: y = a | b;
            3'd4: y = a ^ b;
            3'd5: y = ~a;
            3'd6: {carry, y} = {a, 1'b0};   // shift left
            3'd7: {y, carry} = {1'b0, a};   // shift right
            default y = 4'd0;
        endcase
    end
    assign zero = (y == 4'd0);
endmodule
