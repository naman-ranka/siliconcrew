// Synchronous FIFO, depth 4, 8-bit data, with full/empty flags.
module fifo (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       wr,
    input  wire       rd,
    input  wire [7:0] din,
    output reg  [7:0] dout,
    output wire       full,
    output wire       empty
);
    reg [7:0] mem [0:3];
    reg [2:0] count;          // 0..4
    reg [1:0] wptr, rptr;
    assign full  = (count == 3'd4);
    assign empty = (count == 3'd0);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count <= 0; wptr <= 0; rptr <= 0; dout <= 0;
        end else begin
            if (wr && !full) begin mem[wptr] <= din; wptr <= wptr + 1'b1; end
            if (rd && !empty) begin dout <= mem[rptr]; rptr <= rptr + 1'b1; end
            case ({wr && !full, rd && !empty})
                2'b10: count <= count + 1'b1;
                2'b01: count <= count - 1'b1;
                default: count <= count;
            endcase
        end
    end
endmodule
