module seq_detector_0011 (clk,
    detected,
    din,
    rst_n);
 input clk;
 output detected;
 input din;
 input rst_n;

 wire net3;
 wire net1;
 wire net2;
 wire \window[0] ;
 wire \window[1] ;
 wire \window[2] ;
 wire \window[3] ;
 wire clknet_0_clk;
 wire clknet_1_0__leaf_clk;
 wire clknet_1_1__leaf_clk;

 sky130_fd_sc_hd__and4bb_2 _0_ (.A_N(\window[3] ),
    .B_N(\window[2] ),
    .C(\window[0] ),
    .D(\window[1] ),
    .X(net3));
 sky130_fd_sc_hd__clkbuf_4 clkbuf_0_clk (.A(clk),
    .X(clknet_0_clk));
 sky130_fd_sc_hd__clkbuf_4 clkbuf_1_0__f_clk (.A(clknet_0_clk),
    .X(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__clkbuf_4 clkbuf_1_1__f_clk (.A(clknet_0_clk),
    .X(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input1 (.A(din),
    .X(net1));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input2 (.A(rst_n),
    .X(net2));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output3 (.A(net3),
    .X(detected));
 sky130_fd_sc_hd__dfrtp_1 \window[0]$_DFF_PN0_  (.D(net1),
    .Q(\window[0] ),
    .RESET_B(net2),
    .CLK(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \window[1]$_DFF_PN0_  (.D(\window[0] ),
    .Q(\window[1] ),
    .RESET_B(net2),
    .CLK(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \window[2]$_DFF_PN0_  (.D(\window[1] ),
    .Q(\window[2] ),
    .RESET_B(net2),
    .CLK(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \window[3]$_DFF_PN0_  (.D(\window[2] ),
    .Q(\window[3] ),
    .RESET_B(net2),
    .CLK(clknet_1_1__leaf_clk));
endmodule
