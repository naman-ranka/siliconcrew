// 8-bit up counter with enable and synchronous clear.
module counter8 (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       en,
    input  wire       clr,
    output reg  [7:0] count
);
    always @(posedge clk or negedge rst_n)
        if (!rst_n)     count <= 8'd0;
        else if (clr)   count <= 8'd0;
        else if (en)    count <= count + 8'd1;
endmodule
