`timescale 1ns/1ps
module shiftreg_tb;
    initial begin $dumpfile("shiftreg_tb.vcd"); $dumpvars(0, shiftreg_tb); end

    reg clk,rst_n,load,sin; reg [7:0] din; wire [7:0] q; wire sout; integer errors=0;
    shiftreg dut(.clk(clk),.rst_n(rst_n),.load(load),.din(din),.sin(sin),.q(q),.sout(sout));
    always #5 clk=~clk;
    initial begin
        clk=0;rst_n=0;load=0;sin=0;din=8'h00;#12;rst_n=1;
        load=1; din=8'hA5; @(posedge clk); #1; load=0;
        if (q!==8'hA5) begin errors=errors+1; $display("FAIL load q=%h",q); end
        if (sout!==1'b1) begin errors=errors+1; $display("FAIL sout-after-load=%b (q[7] of A5)",sout); end
        sin=1; @(posedge clk); #1;
        if (q!==8'h4B) begin errors=errors+1; $display("FAIL shift q=%h exp=4B",q); end
        if (sout!==1'b0) begin errors=errors+1; $display("FAIL sout-after-shift=%b (q[7] of 4B)",sout); end
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
