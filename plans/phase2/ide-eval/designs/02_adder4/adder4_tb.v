`timescale 1ns/1ps
module adder4_tb;
    initial begin $dumpfile("adder4_tb.vcd"); $dumpvars(0, adder4_tb); end

    reg [3:0] a,b; reg cin; wire [3:0] sum; wire cout;
    integer i, errors = 0; reg [4:0] exp;
    adder4 dut(.a(a), .b(b), .cin(cin), .sum(sum), .cout(cout));
    initial begin
        for (i=0;i<200;i=i+1) begin
            a=$random; b=$random; cin=$random;
            #1; exp = a + b + cin;
            if ({cout,sum} !== exp) begin errors=errors+1;
                $display("FAIL a=%0d b=%0d cin=%b got=%0d exp=%0d", a,b,cin,{cout,sum},exp); end
        end
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
