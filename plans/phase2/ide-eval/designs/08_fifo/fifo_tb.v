`timescale 1ns/1ps
module fifo_tb;
    initial begin $dumpfile("fifo_tb.vcd"); $dumpvars(0, fifo_tb); end

    reg clk,rst_n,wr,rd; reg [7:0] din; wire [7:0] dout; wire full, empty;
    integer errors=0;
    fifo dut(.clk(clk),.rst_n(rst_n),.wr(wr),.rd(rd),.din(din),.dout(dout),.full(full),.empty(empty));
    always #5 clk=~clk;
    task wpush(input [7:0] d); begin din=d; wr=1; rd=0; @(posedge clk); #1; wr=0; end endtask
    task wpop;                begin wr=0; rd=1; @(posedge clk); #1; rd=0; end endtask
    initial begin
        clk=0;rst_n=0;wr=0;rd=0;din=0;#12;rst_n=1;#1;
        if (!empty) begin errors=errors+1; $display("FAIL not empty at reset"); end
        wpush(8'h11); wpush(8'h22); wpush(8'h33); wpush(8'h44);
        if (!full) begin errors=errors+1; $display("FAIL not full after 4 writes"); end
        wpop; if (dout!==8'h11) begin errors=errors+1; $display("FAIL pop1=%h exp 11",dout); end
        wpop; if (dout!==8'h22) begin errors=errors+1; $display("FAIL pop2=%h exp 22",dout); end
        wpop; if (dout!==8'h33) begin errors=errors+1; $display("FAIL pop3=%h exp 33",dout); end
        wpop; if (dout!==8'h44) begin errors=errors+1; $display("FAIL pop4=%h exp 44",dout); end
        if (!empty) begin errors=errors+1; $display("FAIL not empty after draining"); end
        if (errors==0) $display("TEST PASSED"); else $display("TEST FAILED (%0d errors)", errors);
        $finish;
    end
endmodule
