// Synchronous FIFO (single clock) with first-word-fall-through-free reads.
// Gray-free binary pointers with an extra MSB to disambiguate full vs empty.
module sync_fifo #(
    parameter WIDTH = 8,
    parameter DEPTH = 16
) (
    input  wire             clk,
    input  wire             rst_n,
    input  wire             wr_en,
    input  wire [WIDTH-1:0] din,
    input  wire             rd_en,
    output reg  [WIDTH-1:0] dout,
    output wire             full,
    output wire             empty
);
    localparam ADDR_W = $clog2(DEPTH);

    reg [WIDTH-1:0] mem [0:DEPTH-1];
    reg [ADDR_W:0]  wr_ptr;
    reg [ADDR_W:0]  rd_ptr;

    wire [ADDR_W-1:0] wr_addr = wr_ptr[ADDR_W-1:0];
    wire [ADDR_W-1:0] rd_addr = rd_ptr[ADDR_W-1:0];

    assign empty = (wr_ptr == rd_ptr);
    assign full  = (wr_addr == rd_addr) && (wr_ptr[ADDR_W] != rd_ptr[ADDR_W]);

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            wr_ptr <= {(ADDR_W+1){1'b0}};
        else if (wr_en && !full) begin
            mem[wr_addr] <= din;
            wr_ptr <= wr_ptr + 1'b1;
        end
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rd_ptr <= {(ADDR_W+1){1'b0}};
            dout   <= {WIDTH{1'b0}};
        end else if (rd_en && !empty) begin
            dout   <= mem[rd_addr];
            rd_ptr <= rd_ptr + 1'b1;
        end
    end
endmodule
