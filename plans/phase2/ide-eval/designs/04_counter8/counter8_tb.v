`timescale 1ns/1ps
module counter8_tb;
    initial begin $dumpfile("counter8_tb.vcd"); $dumpvars(0, counter8_tb); end

    reg clk, rst_n, en, clr; wire [7:0] count; integer errors=0;
    counter8 dut(.clk(clk), .rst_n(rst_n), .en(en), .clr(clr), .count(count));
    always #5 clk = ~clk;
    initial begin
        clk=0; rst_n=0; en=0; clr=0; #12; rst_n=1;
        if (count!==8'd0) begin errors=errors+1; $display("FAIL reset=%0d",count); end
        en=1; repeat(5) @(posedge clk); #1;
        if (count!==8'd5) begin errors=errors+1; $display("FAIL count!=5 got=%0d",count); end
        clr=1; @(posedge clk); #1; clr=0;
        if (count!==8'd0) begin errors=errors+1; $display("FAIL clr got=%0d",count); end
        en=0; repeat(3) @(posedge clk); #1;
        if (count!==8'd0) begin errors=errors+1; $display("FAIL hold got=%0d",count); end
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
