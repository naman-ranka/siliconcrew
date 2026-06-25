// 8-bit shift register: parallel load, then serial shift-left with serial-in.
module shiftreg (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       load,
    input  wire [7:0] din,
    input  wire       sin,
    output reg  [7:0] q,
    output wire       sout
);
    assign sout = q[7];
    always @(posedge clk or negedge rst_n)
        if (!rst_n)     q <= 8'd0;
        else if (load)  q <= din;
        else            q <= {q[6:0], sin};
endmodule
