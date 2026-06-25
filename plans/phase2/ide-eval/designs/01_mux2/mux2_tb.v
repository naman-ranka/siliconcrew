`timescale 1ns/1ps
module mux2_tb;
    initial begin $dumpfile("mux2_tb.vcd"); $dumpvars(0, mux2_tb); end

    reg a, b, sel; wire y;
    integer errors = 0;
    mux2 dut(.a(a), .b(b), .sel(sel), .y(y));
    task check(input exp); begin
        #1; if (y !== exp) begin errors=errors+1;
            $display("FAIL a=%b b=%b sel=%b y=%b exp=%b", a,b,sel,y,exp); end
    end endtask
    initial begin
        a=0;b=1;sel=0; check(0);
        a=0;b=1;sel=1; check(1);
        a=1;b=0;sel=0; check(1);
        a=1;b=0;sel=1; check(0);
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
