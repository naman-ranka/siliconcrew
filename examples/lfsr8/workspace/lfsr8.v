// 8-bit maximal-length Fibonacci LFSR. Polynomial x^8 + x^6 + x^5 + x^4 + 1
// (taps at bits 8,6,5,4 → 0-indexed 7,5,4,3). Period 255; the all-zero state is
// unreachable from a non-zero seed. Async active-low reset seeds 0xFF.
module lfsr8 (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       en,
    output reg  [7:0] state
);
    wire feedback = state[7] ^ state[5] ^ state[4] ^ state[3];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)   state <= 8'hFF;
        else if (en)  state <= {state[6:0], feedback};
    end
endmodule
