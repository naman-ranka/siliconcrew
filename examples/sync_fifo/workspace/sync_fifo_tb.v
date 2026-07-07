`timescale 1ns/1ps
// Self-checking testbench: writes a burst, reads it back in order, and checks
// FIFO ordering + empty behavior. Emits "TEST PASSED" only on a clean run.
module sync_fifo_tb;
    localparam WIDTH = 8;
    localparam DEPTH = 16;

    reg             clk = 1'b0;
    reg             rst_n = 1'b0;
    reg             wr_en = 1'b0;
    reg             rd_en = 1'b0;
    reg  [WIDTH-1:0] din = {WIDTH{1'b0}};
    wire [WIDTH-1:0] dout;
    wire            full;
    wire            empty;

    integer i;
    integer errors = 0;

    sync_fifo #(.WIDTH(WIDTH), .DEPTH(DEPTH)) dut (
        .clk(clk), .rst_n(rst_n), .wr_en(wr_en), .din(din),
        .rd_en(rd_en), .dout(dout), .full(full), .empty(empty)
    );

    always #5 clk = ~clk;

    initial begin
        $dumpfile("sync_fifo_tb.vcd");
        $dumpvars(0, sync_fifo_tb);

        rst_n = 1'b0;
        repeat (3) @(posedge clk);
        rst_n = 1'b1;
        @(posedge clk);
        if (!empty) begin
            errors = errors + 1;
            $display("ERROR: FIFO not empty after reset");
        end

        // Burst-write 10 values.
        for (i = 0; i < 10; i = i + 1) begin
            @(negedge clk);
            wr_en = 1'b1;
            din   = i[WIDTH-1:0] + 8'h10;
        end
        @(negedge clk);
        wr_en = 1'b0;

        // Read them back and check FIFO ordering.
        for (i = 0; i < 10; i = i + 1) begin
            @(negedge clk);
            rd_en = 1'b1;
            @(posedge clk);
            #1;
            if (dout !== (i[WIDTH-1:0] + 8'h10)) begin
                errors = errors + 1;
                $display("ERROR: read %0d got %0h expected %0h", i, dout, i + 8'h10);
            end
        end
        @(negedge clk);
        rd_en = 1'b0;
        @(posedge clk);
        if (!empty) begin
            errors = errors + 1;
            $display("ERROR: FIFO not empty after draining");
        end

        if (errors == 0)
            $display("TEST PASSED");
        else
            $display("TEST FAILED with %0d error(s)", errors);
        $finish;
    end
endmodule
