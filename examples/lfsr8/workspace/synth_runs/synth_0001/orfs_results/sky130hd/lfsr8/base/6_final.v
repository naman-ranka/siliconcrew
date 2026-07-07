module lfsr8 (clk,
    en,
    rst_n,
    state);
 input clk;
 input en;
 input rst_n;
 output [7:0] state;

 wire _00_;
 wire _01_;
 wire _02_;
 wire _03_;
 wire _04_;
 wire _05_;
 wire _06_;
 wire _07_;
 wire _09_;
 wire _10_;
 wire _11_;
 wire _12_;
 wire net1;
 wire net2;
 wire net3;
 wire net4;
 wire net5;
 wire net6;
 wire net7;
 wire net8;
 wire net9;
 wire net10;
 wire clknet_0_clk;
 wire clknet_1_0__leaf_clk;
 wire clknet_1_1__leaf_clk;

 sky130_fd_sc_hd__xnor2_1 _14_ (.A(net7),
    .B(net6),
    .Y(_09_));
 sky130_fd_sc_hd__xnor2_1 _15_ (.A(net8),
    .B(net10),
    .Y(_10_));
 sky130_fd_sc_hd__xnor2_1 _16_ (.A(_09_),
    .B(_10_),
    .Y(_11_));
 sky130_fd_sc_hd__nor2_1 _17_ (.A(net3),
    .B(net1),
    .Y(_12_));
 sky130_fd_sc_hd__a21oi_1 _18_ (.A1(net1),
    .A2(_11_),
    .B1(_12_),
    .Y(_00_));
 sky130_fd_sc_hd__mux2_1 _19_ (.A0(net4),
    .A1(net3),
    .S(net1),
    .X(_01_));
 sky130_fd_sc_hd__mux2_1 _20_ (.A0(net5),
    .A1(net4),
    .S(net1),
    .X(_02_));
 sky130_fd_sc_hd__mux2_1 _21_ (.A0(net6),
    .A1(net5),
    .S(net1),
    .X(_03_));
 sky130_fd_sc_hd__mux2_2 _22_ (.A0(net7),
    .A1(net6),
    .S(net1),
    .X(_04_));
 sky130_fd_sc_hd__mux2_2 _23_ (.A0(net8),
    .A1(net7),
    .S(net1),
    .X(_05_));
 sky130_fd_sc_hd__mux2_2 _24_ (.A0(net9),
    .A1(net8),
    .S(net1),
    .X(_06_));
 sky130_fd_sc_hd__mux2_2 _25_ (.A0(net10),
    .A1(net9),
    .S(net1),
    .X(_07_));
 sky130_fd_sc_hd__clkbuf_8 clkbuf_0_clk (.A(clk),
    .X(clknet_0_clk));
 sky130_fd_sc_hd__clkbuf_8 clkbuf_1_0__f_clk (.A(clknet_0_clk),
    .X(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__clkbuf_8 clkbuf_1_1__f_clk (.A(clknet_0_clk),
    .X(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input1 (.A(en),
    .X(net1));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input2 (.A(rst_n),
    .X(net2));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output10 (.A(net10),
    .X(state[7]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output3 (.A(net3),
    .X(state[0]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output4 (.A(net4),
    .X(state[1]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output5 (.A(net5),
    .X(state[2]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output6 (.A(net6),
    .X(state[3]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output7 (.A(net7),
    .X(state[4]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output8 (.A(net8),
    .X(state[5]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output9 (.A(net9),
    .X(state[6]));
 sky130_fd_sc_hd__dfstp_2 \state[0]$_DFFE_PN1P_  (.D(_00_),
    .Q(net3),
    .SET_B(net2),
    .CLK(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__dfstp_2 \state[1]$_DFFE_PN1P_  (.D(_01_),
    .Q(net4),
    .SET_B(net2),
    .CLK(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__dfstp_2 \state[2]$_DFFE_PN1P_  (.D(_02_),
    .Q(net5),
    .SET_B(net2),
    .CLK(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__dfstp_2 \state[3]$_DFFE_PN1P_  (.D(_03_),
    .Q(net6),
    .SET_B(net2),
    .CLK(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__dfstp_2 \state[4]$_DFFE_PN1P_  (.D(_04_),
    .Q(net7),
    .SET_B(net2),
    .CLK(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__dfstp_2 \state[5]$_DFFE_PN1P_  (.D(_05_),
    .Q(net8),
    .SET_B(net2),
    .CLK(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__dfstp_2 \state[6]$_DFFE_PN1P_  (.D(_06_),
    .Q(net9),
    .SET_B(net2),
    .CLK(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__dfstp_2 \state[7]$_DFFE_PN1P_  (.D(_07_),
    .Q(net10),
    .SET_B(net2),
    .CLK(clknet_1_0__leaf_clk));
endmodule
