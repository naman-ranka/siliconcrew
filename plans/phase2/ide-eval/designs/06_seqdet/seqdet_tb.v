`timescale 1ns/1ps
module seqdet_tb;
    initial begin $dumpfile("seqdet_tb.vcd"); $dumpvars(0, seqdet_tb); end

    reg clk,rst_n,din; wire found; integer errors=0, i;
    // stimulus 1 0 1 1 0 1 1  -> 'found' should pulse after the 4th and 7th bits
    reg [0:6] stim = 7'b1011011;
    reg [0:6] exp  = 7'b0001001; // found asserted in the cycle the pattern completes
    seqdet dut(.clk(clk),.rst_n(rst_n),.din(din),.found(found));
    always #5 clk=~clk;
    initial begin
        clk=0;rst_n=0;din=0;#12;rst_n=1;
        for (i=0;i<7;i=i+1) begin
            din=stim[i]; @(posedge clk); #1;
            if (found!==exp[i]) begin errors=errors+1;
                $display("FAIL i=%0d din=%b found=%b exp=%b",i,din,found,exp[i]); end
        end
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
