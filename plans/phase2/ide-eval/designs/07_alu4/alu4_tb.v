`timescale 1ns/1ps
module alu4_tb;
    reg [3:0] a,b; reg [2:0] op; wire [3:0] y; wire zero; wire carry;
    integer errors=0; reg [3:0] ey; reg ec;
    alu4 dut(.a(a),.b(b),.op(op),.y(y),.zero(zero),.carry(carry));
    task chk; begin #1;
        if (y!==ey || carry!==ec) begin errors=errors+1;
            $display("FAIL op=%0d a=%h b=%h y=%h(exp %h) c=%b(exp %b)",op,a,b,y,ey,carry,ec); end
    end endtask
    initial begin
        a=4'h3;b=4'h5;op=0; {ec,ey}=a+b; chk;
        a=4'h8;b=4'h1;op=1; {ec,ey}=a-b; chk;
        a=4'hC;b=4'hA;op=2; ey=a&b; ec=0; chk;
        a=4'hC;b=4'hA;op=3; ey=a|b; ec=0; chk;
        a=4'hC;b=4'hA;op=4; ey=a^b; ec=0; chk;
        a=4'h5;b=4'h0;op=5; ey=~a; ec=0; chk;
        a=4'hF;b=4'h0;op=6; {ec,ey}={a,1'b0}; chk;
        a=4'h3;b=4'h0;op=7; ey={1'b0,a[3:1]}; ec=a[0]; chk;
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
