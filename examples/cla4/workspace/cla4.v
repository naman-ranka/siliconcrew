// 4-bit carry-lookahead adder (registered outputs).
//
// Adapted from the Tiny Tapeout project "4-bit CLA" (tt08_CSA_4bits)
//   repo:    https://github.com/Electom/tt08_CSA_4bits
//   commit:  213ea903e947a2fbc5415d67e893da5d43385ffe
//   author:  Wei Zhang
//   license: Apache-2.0 (see LICENSE in this bundle)
//
// Adaptation: the original `tt_um_Electom_cla_4bits` wraps the adder in the
// fixed Tiny Tapeout pin interface (ui_in/uo_out/uio_*/ena) — operand a on
// ui_in[3:0], b on ui_in[7:4], carry-in on uio_in[0], sum on uo_out[3:0] and
// carry-out on uo_out[4]. This version exposes those live signals as real ports
// (a, b, ci -> s, co). The carry-lookahead generate/propagate/carry network and
// the registered outputs are kept verbatim. The self-checking testbench is
// original to this bundle.
`default_nettype none

module cla4 (
    input  wire       clk,
    input  wire       rst_n,   // active-low async reset
    input  wire [3:0] a,       // operand A
    input  wire [3:0] b,       // operand B
    input  wire       ci,      // carry-in
    output reg  [3:0] s,       // sum (registered)
    output reg        co       // carry-out (registered)
);
    wire [3:0] g;
    wire [3:0] p;
    wire [2:0] c;
    wire [3:0] s_w;
    wire       co_w;

    // generate / propagate
    assign g = a & b;
    assign p = a | b;

    // carry lookahead
    assign c[0] = g[0] | (p[0] & ci);
    assign c[1] = g[1] | (p[1] & g[0]) | (p[1] & p[0] & ci);
    assign c[2] = g[2] | (p[2] & g[1]) | (p[2] & p[1] & g[0]) | (p[2] & p[1] & p[0] & ci);
    assign co_w = g[3] | (p[3] & g[2]) | (p[3] & p[2] & g[1]) | (p[3] & p[2] & p[1] & g[0])
                       | (p[3] & p[2] & p[1] & p[0] & ci);

    // sum = (a ^ b) XOR carry-in chain
    assign s_w = (p & ~g) ^ {c[2:0], ci};

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            s  <= 4'd0;
            co <= 1'b0;
        end else begin
            s  <= s_w;
            co <= co_w;
        end
    end
endmodule
