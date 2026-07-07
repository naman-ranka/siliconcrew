module cla4 (ci,
    clk,
    co,
    rst_n,
    a,
    b,
    s);
 input ci;
 input clk;
 output co;
 input rst_n;
 input [3:0] a;
 input [3:0] b;
 output [3:0] s;

 wire _00_;
 wire _01_;
 wire _02_;
 wire _03_;
 wire _04_;
 wire _05_;
 wire _06_;
 wire _07_;
 wire _08_;
 wire _09_;
 wire _10_;
 wire _11_;
 wire _12_;
 wire _13_;
 wire _14_;
 wire _15_;
 wire _16_;
 wire _17_;
 wire _18_;
 wire _19_;
 wire _20_;
 wire _21_;
 wire _22_;
 wire _23_;
 wire _24_;
 wire _25_;
 wire _26_;
 wire _27_;
 wire _28_;
 wire _29_;
 wire _30_;
 wire _31_;
 wire _32_;
 wire _33_;
 wire _34_;
 wire _35_;
 wire _36_;
 wire _37_;
 wire _38_;
 wire _39_;
 wire _40_;
 wire net1;
 wire net2;
 wire net3;
 wire net4;
 wire net5;
 wire net6;
 wire net7;
 wire net8;
 wire net9;
 wire net11;
 wire co_w;
 wire net10;
 wire net12;
 wire net13;
 wire net14;
 wire net15;
 wire \s_w[0] ;
 wire \s_w[1] ;
 wire \s_w[2] ;
 wire \s_w[3] ;
 wire clknet_0_clk;
 wire clknet_1_0__leaf_clk;
 wire clknet_1_1__leaf_clk;

 sky130_fd_sc_hd__inv_1 _41_ (.A(net9),
    .Y(_02_));
 sky130_fd_sc_hd__inv_1 _42_ (.A(_04_),
    .Y(\s_w[0] ));
 sky130_fd_sc_hd__inv_1 _43_ (.A(net1),
    .Y(_00_));
 sky130_fd_sc_hd__inv_1 _44_ (.A(net2),
    .Y(_08_));
 sky130_fd_sc_hd__inv_1 _45_ (.A(net3),
    .Y(_13_));
 sky130_fd_sc_hd__inv_1 _46_ (.A(net4),
    .Y(_18_));
 sky130_fd_sc_hd__inv_1 _47_ (.A(net5),
    .Y(_01_));
 sky130_fd_sc_hd__inv_1 _48_ (.A(net6),
    .Y(_09_));
 sky130_fd_sc_hd__inv_1 _49_ (.A(net7),
    .Y(_14_));
 sky130_fd_sc_hd__inv_1 _50_ (.A(net8),
    .Y(_19_));
 sky130_fd_sc_hd__nor2b_4 _51_ (.A(_05_),
    .B_N(net9),
    .Y(_23_));
 sky130_fd_sc_hd__nand2b_1 _52_ (.A_N(_12_),
    .B(_10_),
    .Y(_24_));
 sky130_fd_sc_hd__inv_1 _53_ (.A(_15_),
    .Y(_25_));
 sky130_fd_sc_hd__o311ai_2 _54_ (.A1(_12_),
    .A2(_07_),
    .A3(_23_),
    .B1(_24_),
    .C1(_25_),
    .Y(_26_));
 sky130_fd_sc_hd__nor2_1 _55_ (.A(_17_),
    .B(_22_),
    .Y(_27_));
 sky130_fd_sc_hd__nor2b_1 _56_ (.A(_22_),
    .B_N(_20_),
    .Y(_28_));
 sky130_fd_sc_hd__a21oi_1 _57_ (.A1(_26_),
    .A2(_27_),
    .B1(_28_),
    .Y(co_w));
 sky130_fd_sc_hd__xnor2_1 _58_ (.A(_11_),
    .B(_03_),
    .Y(\s_w[1] ));
 sky130_fd_sc_hd__o31ai_1 _59_ (.A1(_12_),
    .A2(_06_),
    .A3(_23_),
    .B1(_24_),
    .Y(_29_));
 sky130_fd_sc_hd__xnor2_1 _60_ (.A(_16_),
    .B(_29_),
    .Y(\s_w[2] ));
 sky130_fd_sc_hd__nor2_1 _61_ (.A(_17_),
    .B(_21_),
    .Y(_30_));
 sky130_fd_sc_hd__nor2_1 _62_ (.A(_10_),
    .B(_15_),
    .Y(_31_));
 sky130_fd_sc_hd__o211a_1 _63_ (.A1(_07_),
    .A2(_23_),
    .B1(_31_),
    .C1(_21_),
    .X(_32_));
 sky130_fd_sc_hd__nor2b_1 _64_ (.A(_15_),
    .B_N(_12_),
    .Y(_33_));
 sky130_fd_sc_hd__o21a_1 _65_ (.A1(_17_),
    .A2(_33_),
    .B1(_21_),
    .X(_34_));
 sky130_fd_sc_hd__a211oi_2 _66_ (.A1(_26_),
    .A2(_30_),
    .B1(_32_),
    .C1(_34_),
    .Y(\s_w[3] ));
 sky130_fd_sc_hd__fa_1 _67_ (.A(_00_),
    .B(_01_),
    .CIN(_02_),
    .COUT(_03_),
    .SUM(_04_));
 sky130_fd_sc_hd__ha_1 _68_ (.A(_00_),
    .B(_01_),
    .COUT(_05_),
    .SUM(_35_));
 sky130_fd_sc_hd__ha_1 _69_ (.A(net1),
    .B(net5),
    .COUT(_06_),
    .SUM(_36_));
 sky130_fd_sc_hd__ha_1 _70_ (.A(net1),
    .B(net5),
    .COUT(_07_),
    .SUM(_37_));
 sky130_fd_sc_hd__ha_1 _71_ (.A(_08_),
    .B(_09_),
    .COUT(_10_),
    .SUM(_11_));
 sky130_fd_sc_hd__ha_1 _72_ (.A(net2),
    .B(net6),
    .COUT(_12_),
    .SUM(_38_));
 sky130_fd_sc_hd__ha_1 _73_ (.A(_13_),
    .B(_14_),
    .COUT(_15_),
    .SUM(_16_));
 sky130_fd_sc_hd__ha_1 _74_ (.A(net3),
    .B(net7),
    .COUT(_17_),
    .SUM(_39_));
 sky130_fd_sc_hd__ha_1 _75_ (.A(_18_),
    .B(_19_),
    .COUT(_20_),
    .SUM(_21_));
 sky130_fd_sc_hd__ha_1 _76_ (.A(net4),
    .B(net8),
    .COUT(_22_),
    .SUM(_40_));
 sky130_fd_sc_hd__clkbuf_8 clkbuf_0_clk (.A(clk),
    .X(clknet_0_clk));
 sky130_fd_sc_hd__clkbuf_8 clkbuf_1_0__f_clk (.A(clknet_0_clk),
    .X(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__clkbuf_8 clkbuf_1_1__f_clk (.A(clknet_0_clk),
    .X(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__clkbuf_1 clkload0 (.A(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \co$_DFF_PN0_  (.D(co_w),
    .Q(net11),
    .RESET_B(net10),
    .CLK(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input1 (.A(a[0]),
    .X(net1));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input10 (.A(rst_n),
    .X(net10));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input2 (.A(a[1]),
    .X(net2));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input3 (.A(a[2]),
    .X(net3));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input4 (.A(a[3]),
    .X(net4));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input5 (.A(b[0]),
    .X(net5));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input6 (.A(b[1]),
    .X(net6));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input7 (.A(b[2]),
    .X(net7));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input8 (.A(b[3]),
    .X(net8));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input9 (.A(ci),
    .X(net9));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output11 (.A(net11),
    .X(co));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output12 (.A(net12),
    .X(s[0]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output13 (.A(net13),
    .X(s[1]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output14 (.A(net14),
    .X(s[2]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output15 (.A(net15),
    .X(s[3]));
 sky130_fd_sc_hd__dfrtp_1 \s[0]$_DFF_PN0_  (.D(\s_w[0] ),
    .Q(net12),
    .RESET_B(net10),
    .CLK(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \s[1]$_DFF_PN0_  (.D(\s_w[1] ),
    .Q(net13),
    .RESET_B(net10),
    .CLK(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \s[2]$_DFF_PN0_  (.D(\s_w[2] ),
    .Q(net14),
    .RESET_B(net10),
    .CLK(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \s[3]$_DFF_PN0_  (.D(\s_w[3] ),
    .Q(net15),
    .RESET_B(net10),
    .CLK(clknet_1_1__leaf_clk));
endmodule
