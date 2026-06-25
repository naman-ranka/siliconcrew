`timescale 1ns/1ps
module dff_tb;
    reg clk, rst_n, d; wire q; integer errors=0;
    dff dut(.clk(clk), .rst_n(rst_n), .d(d), .q(q));
    always #5 clk = ~clk;
    initial begin
        clk=0; rst_n=0; d=1; #12;
        if (q!==1'b0) begin errors=errors+1; $display("FAIL reset q=%b",q); end
        rst_n=1; d=1; @(posedge clk); #1;
        if (q!==1'b1) begin errors=errors+1; $display("FAIL capture-1 q=%b",q); end
        d=0; @(posedge clk); #1;
        if (q!==1'b0) begin errors=errors+1; $display("FAIL capture-0 q=%b",q); end
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
