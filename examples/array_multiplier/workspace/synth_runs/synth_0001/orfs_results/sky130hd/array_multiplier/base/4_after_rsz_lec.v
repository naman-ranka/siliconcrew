module array_multiplier (a,
    b,
    p);
 input [3:0] a;
 input [3:0] b;
 output [7:0] p;

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
 wire _41_;
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
 wire net11;
 wire net12;
 wire net13;
 wire net14;
 wire net15;
 wire net16;

 sky130_fd_sc_hd__and2_1 _42_ (.A(net8),
    .B(net4),
    .X(_21_));
 sky130_fd_sc_hd__and2_1 _43_ (.A(net4),
    .B(net6),
    .X(_01_));
 sky130_fd_sc_hd__and2_1 _44_ (.A(net3),
    .B(net6),
    .X(_25_));
 sky130_fd_sc_hd__and2_1 _45_ (.A(net8),
    .B(net2),
    .X(_08_));
 sky130_fd_sc_hd__and2_1 _46_ (.A(net6),
    .B(net2),
    .X(_27_));
 sky130_fd_sc_hd__nand2_1 _47_ (.A(net7),
    .B(net1),
    .Y(_10_));
 sky130_fd_sc_hd__and2_1 _48_ (.A(net5),
    .B(net2),
    .X(_30_));
 sky130_fd_sc_hd__nand2_1 _49_ (.A(net8),
    .B(net3),
    .Y(_03_));
 sky130_fd_sc_hd__inv_1 _50_ (.A(_09_),
    .Y(_17_));
 sky130_fd_sc_hd__nand2_1 _51_ (.A(net4),
    .B(net7),
    .Y(_04_));
 sky130_fd_sc_hd__inv_1 _52_ (.A(_29_),
    .Y(_11_));
 sky130_fd_sc_hd__inv_1 _53_ (.A(_19_),
    .Y(_23_));
 sky130_fd_sc_hd__inv_1 _54_ (.A(_14_),
    .Y(net11));
 sky130_fd_sc_hd__inv_1 _55_ (.A(_20_),
    .Y(net14));
 sky130_fd_sc_hd__inv_1 _56_ (.A(_02_),
    .Y(_05_));
 sky130_fd_sc_hd__and2_1 _57_ (.A(net4),
    .B(net5),
    .X(_24_));
 sky130_fd_sc_hd__and2_1 _58_ (.A(net3),
    .B(net7),
    .X(_00_));
 sky130_fd_sc_hd__and2_1 _59_ (.A(net3),
    .B(net5),
    .X(_26_));
 sky130_fd_sc_hd__and2_1 _60_ (.A(net7),
    .B(net2),
    .X(_07_));
 sky130_fd_sc_hd__and2_1 _61_ (.A(net8),
    .B(net1),
    .X(_15_));
 sky130_fd_sc_hd__inv_1 _62_ (.A(_06_),
    .Y(_22_));
 sky130_fd_sc_hd__inv_1 _63_ (.A(_13_),
    .Y(_16_));
 sky130_fd_sc_hd__and2_1 _64_ (.A(net6),
    .B(net1),
    .X(_31_));
 sky130_fd_sc_hd__inv_1 _65_ (.A(_28_),
    .Y(_12_));
 sky130_fd_sc_hd__inv_1 _66_ (.A(_32_),
    .Y(_18_));
 sky130_fd_sc_hd__and2_1 _67_ (.A(net5),
    .B(net1),
    .X(net9));
 sky130_fd_sc_hd__fa_1 _68_ (.A(_00_),
    .B(_01_),
    .CIN(_33_),
    .COUT(_02_),
    .SUM(_34_));
 sky130_fd_sc_hd__fa_1 _69_ (.A(_03_),
    .B(_04_),
    .CIN(_05_),
    .COUT(_06_),
    .SUM(_35_));
 sky130_fd_sc_hd__fa_1 _70_ (.A(_07_),
    .B(_36_),
    .CIN(_37_),
    .COUT(_38_),
    .SUM(_39_));
 sky130_fd_sc_hd__fa_1 _71_ (.A(_08_),
    .B(_38_),
    .CIN(_34_),
    .COUT(_09_),
    .SUM(_40_));
 sky130_fd_sc_hd__fa_1 _72_ (.A(_10_),
    .B(_11_),
    .CIN(_12_),
    .COUT(_13_),
    .SUM(_14_));
 sky130_fd_sc_hd__fa_1 _73_ (.A(_15_),
    .B(_16_),
    .CIN(_39_),
    .COUT(_41_),
    .SUM(net12));
 sky130_fd_sc_hd__fa_1 _74_ (.A(_17_),
    .B(_35_),
    .CIN(_18_),
    .COUT(_19_),
    .SUM(_20_));
 sky130_fd_sc_hd__fa_1 _75_ (.A(_21_),
    .B(_22_),
    .CIN(_23_),
    .COUT(net16),
    .SUM(net15));
 sky130_fd_sc_hd__ha_1 _76_ (.A(_24_),
    .B(_25_),
    .COUT(_33_),
    .SUM(_37_));
 sky130_fd_sc_hd__ha_1 _77_ (.A(_26_),
    .B(_27_),
    .COUT(_36_),
    .SUM(_28_));
 sky130_fd_sc_hd__ha_1 _78_ (.A(_30_),
    .B(_31_),
    .COUT(_29_),
    .SUM(net10));
 sky130_fd_sc_hd__ha_1 _79_ (.A(_41_),
    .B(_40_),
    .COUT(_32_),
    .SUM(net13));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input1 (.A(a[0]),
    .X(net1));
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
 sky130_fd_sc_hd__clkdlybuf4s50_1 output10 (.A(net10),
    .X(p[1]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output11 (.A(net11),
    .X(p[2]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output12 (.A(net12),
    .X(p[3]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output13 (.A(net13),
    .X(p[4]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output14 (.A(net14),
    .X(p[5]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output15 (.A(net15),
    .X(p[6]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output16 (.A(net16),
    .X(p[7]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output9 (.A(net9),
    .X(p[0]));
endmodule
