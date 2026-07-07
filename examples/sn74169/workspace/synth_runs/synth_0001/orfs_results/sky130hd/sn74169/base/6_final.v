module sn74169 (CLK,
    ENPB,
    ENTB,
    LOADB,
    RCOB,
    U_DB,
    A,
    Q);
 input CLK;
 input ENPB;
 input ENTB;
 input LOADB;
 output RCOB;
 input U_DB;
 input [3:0] A;
 output [3:0] Q;

 wire net1;
 wire net2;
 wire net3;
 wire net4;
 wire net5;
 wire net6;
 wire net7;
 wire net8;
 wire net10;
 wire net11;
 wire net12;
 wire net13;
 wire net14;
 wire net9;
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

 sky130_fd_sc_hd__edfxtp_1 \Q[0]$_DFFE_PP_  (.D(_00_),
    .DE(_04_),
    .Q(net10),
    .CLK(net5));
 sky130_fd_sc_hd__edfxtp_1 \Q[1]$_DFFE_PP_  (.D(_01_),
    .DE(_04_),
    .Q(net11),
    .CLK(net5));
 sky130_fd_sc_hd__edfxtp_1 \Q[2]$_DFFE_PP_  (.D(_02_),
    .DE(_04_),
    .Q(net12),
    .CLK(net5));
 sky130_fd_sc_hd__edfxtp_1 \Q[3]$_DFFE_PP_  (.D(_03_),
    .DE(_04_),
    .Q(net13),
    .CLK(net5));
 sky130_fd_sc_hd__o21ai_0 _24_ (.A1(net6),
    .A2(net7),
    .B1(net8),
    .Y(_04_));
 sky130_fd_sc_hd__inv_1 _25_ (.A(net8),
    .Y(_12_));
 sky130_fd_sc_hd__nand2_1 _26_ (.A(_12_),
    .B(net1),
    .Y(_13_));
 sky130_fd_sc_hd__o21ai_0 _27_ (.A1(_12_),
    .A2(net10),
    .B1(_13_),
    .Y(_00_));
 sky130_fd_sc_hd__mux2_2 _28_ (.A0(net2),
    .A1(_07_),
    .S(net8),
    .X(_01_));
 sky130_fd_sc_hd__xnor2_1 _29_ (.A(_06_),
    .B(_11_),
    .Y(_14_));
 sky130_fd_sc_hd__nor2_1 _30_ (.A(net8),
    .B(net3),
    .Y(_15_));
 sky130_fd_sc_hd__a21oi_1 _31_ (.A1(net8),
    .A2(_14_),
    .B1(_15_),
    .Y(_02_));
 sky130_fd_sc_hd__nand3_1 _32_ (.A(net10),
    .B(_09_),
    .C(_11_),
    .Y(_16_));
 sky130_fd_sc_hd__a21oi_1 _33_ (.A1(_11_),
    .A2(_08_),
    .B1(_10_),
    .Y(_17_));
 sky130_fd_sc_hd__xnor2_1 _34_ (.A(net13),
    .B(net9),
    .Y(_18_));
 sky130_fd_sc_hd__a211oi_1 _35_ (.A1(_16_),
    .A2(_17_),
    .B1(_18_),
    .C1(_12_),
    .Y(_19_));
 sky130_fd_sc_hd__and4_4 _36_ (.A(net8),
    .B(_16_),
    .C(_17_),
    .D(_18_),
    .X(_20_));
 sky130_fd_sc_hd__a211o_1 _37_ (.A1(_12_),
    .A2(net4),
    .B1(_19_),
    .C1(_20_),
    .X(_03_));
 sky130_fd_sc_hd__inv_1 _38_ (.A(net9),
    .Y(_05_));
 sky130_fd_sc_hd__nor4_1 _39_ (.A(net10),
    .B(net12),
    .C(net13),
    .D(net11),
    .Y(_21_));
 sky130_fd_sc_hd__nand4_1 _40_ (.A(net10),
    .B(net12),
    .C(net13),
    .D(net11),
    .Y(_22_));
 sky130_fd_sc_hd__nor2_1 _41_ (.A(_05_),
    .B(_22_),
    .Y(_23_));
 sky130_fd_sc_hd__a21oi_1 _42_ (.A1(_05_),
    .A2(_21_),
    .B1(_23_),
    .Y(net14));
 sky130_fd_sc_hd__fa_1 _43_ (.A(net10),
    .B(net11),
    .CIN(_05_),
    .COUT(_06_),
    .SUM(_07_));
 sky130_fd_sc_hd__ha_1 _44_ (.A(net11),
    .B(_05_),
    .COUT(_08_),
    .SUM(_09_));
 sky130_fd_sc_hd__ha_1 _45_ (.A(net12),
    .B(_05_),
    .COUT(_10_),
    .SUM(_11_));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input1 (.A(A[0]),
    .X(net1));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input2 (.A(A[1]),
    .X(net2));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input3 (.A(A[2]),
    .X(net3));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input4 (.A(A[3]),
    .X(net4));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input5 (.A(CLK),
    .X(net5));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input6 (.A(ENPB),
    .X(net6));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input7 (.A(ENTB),
    .X(net7));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input8 (.A(LOADB),
    .X(net8));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input9 (.A(U_DB),
    .X(net9));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output10 (.A(net10),
    .X(Q[0]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output11 (.A(net11),
    .X(Q[1]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output12 (.A(net12),
    .X(Q[2]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output13 (.A(net13),
    .X(Q[3]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output14 (.A(net14),
    .X(RCOB));
endmodule
