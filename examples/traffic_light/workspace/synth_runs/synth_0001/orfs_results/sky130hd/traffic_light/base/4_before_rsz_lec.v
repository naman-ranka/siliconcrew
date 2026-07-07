module traffic_light (clk,
    green,
    red,
    rst_n,
    yellow);
 input clk;
 output green;
 output red;
 input rst_n;
 output yellow;

 wire _000_;
 wire _001_;
 wire _002_;
 wire _003_;
 wire _004_;
 wire _005_;
 wire _006_;
 wire _007_;
 wire _008_;
 wire _009_;
 wire _010_;
 wire _011_;
 wire _012_;
 wire _013_;
 wire _014_;
 wire _015_;
 wire _016_;
 wire _017_;
 wire _018_;
 wire _019_;
 wire _020_;
 wire _021_;
 wire _022_;
 wire _023_;
 wire _024_;
 wire _025_;
 wire _026_;
 wire _027_;
 wire _028_;
 wire _029_;
 wire _030_;
 wire _031_;
 wire _032_;
 wire _033_;
 wire _034_;
 wire _035_;
 wire _036_;
 wire _037_;
 wire _038_;
 wire _039_;
 wire _040_;
 wire _041_;
 wire _042_;
 wire _043_;
 wire _044_;
 wire _045_;
 wire _046_;
 wire _048_;
 wire _049_;
 wire _050_;
 wire _051_;
 wire _053_;
 wire _054_;
 wire _055_;
 wire _056_;
 wire _057_;
 wire _058_;
 wire _059_;
 wire _060_;
 wire _061_;
 wire _062_;
 wire _063_;
 wire _064_;
 wire _065_;
 wire _066_;
 wire _067_;
 wire _068_;
 wire _069_;
 wire _070_;
 wire _071_;
 wire _072_;
 wire _073_;
 wire _074_;
 wire _075_;
 wire _076_;
 wire _077_;
 wire _078_;
 wire _079_;
 wire _080_;
 wire _081_;
 wire _082_;
 wire _083_;
 wire _084_;
 wire _086_;
 wire _087_;
 wire _088_;
 wire _089_;
 wire _090_;
 wire _091_;
 wire _092_;
 wire _093_;
 wire _094_;
 wire _095_;
 wire _096_;
 wire _097_;
 wire _098_;
 wire _099_;
 wire _100_;
 wire _101_;
 wire _102_;
 wire _103_;
 wire _104_;
 wire _105_;
 wire _106_;
 wire _107_;
 wire _108_;
 wire _109_;
 wire _110_;
 wire _111_;
 wire _112_;
 wire _113_;
 wire _114_;
 wire _115_;
 wire _116_;
 wire _117_;
 wire _118_;
 wire _119_;
 wire _120_;
 wire _121_;
 wire _122_;
 wire _123_;
 wire _124_;
 wire _125_;
 wire _126_;
 wire _127_;
 wire _128_;
 wire _129_;
 wire _130_;
 wire net10;
 wire _132_;
 wire _133_;
 wire _134_;
 wire net9;
 wire _136_;
 wire _138_;
 wire net2;
 wire net3;
 wire net1;
 wire \timer[0] ;
 wire \timer[10] ;
 wire \timer[11] ;
 wire \timer[12] ;
 wire \timer[13] ;
 wire \timer[14] ;
 wire \timer[15] ;
 wire \timer[16] ;
 wire \timer[17] ;
 wire \timer[18] ;
 wire \timer[19] ;
 wire \timer[1] ;
 wire \timer[20] ;
 wire \timer[21] ;
 wire \timer[22] ;
 wire \timer[23] ;
 wire \timer[24] ;
 wire \timer[25] ;
 wire \timer[26] ;
 wire \timer[27] ;
 wire \timer[28] ;
 wire \timer[29] ;
 wire \timer[2] ;
 wire \timer[30] ;
 wire \timer[31] ;
 wire \timer[3] ;
 wire \timer[4] ;
 wire \timer[5] ;
 wire \timer[6] ;
 wire \timer[7] ;
 wire \timer[8] ;
 wire \timer[9] ;
 wire net4;
 wire net7;
 wire net8;
 wire clknet_0_clk;
 wire clknet_2_0__leaf_clk;
 wire clknet_2_1__leaf_clk;
 wire clknet_2_2__leaf_clk;
 wire clknet_2_3__leaf_clk;

 sky130_fd_sc_hd__inv_1 _139_ (.A(\timer[0] ),
    .Y(_032_));
 sky130_fd_sc_hd__nor4_4 _140_ (.A(\timer[8] ),
    .B(\timer[9] ),
    .C(\timer[10] ),
    .D(\timer[11] ),
    .Y(_119_));
 sky130_fd_sc_hd__nor4_2 _141_ (.A(\timer[12] ),
    .B(\timer[13] ),
    .C(\timer[14] ),
    .D(\timer[15] ),
    .Y(_120_));
 sky130_fd_sc_hd__nor4_4 _142_ (.A(\timer[4] ),
    .B(\timer[5] ),
    .C(\timer[6] ),
    .D(\timer[7] ),
    .Y(_121_));
 sky130_fd_sc_hd__nor4_2 _143_ (.A(\timer[17] ),
    .B(\timer[16] ),
    .C(\timer[19] ),
    .D(\timer[18] ),
    .Y(_122_));
 sky130_fd_sc_hd__nand4_4 _144_ (.A(_119_),
    .B(_120_),
    .C(_121_),
    .D(_122_),
    .Y(_123_));
 sky130_fd_sc_hd__nor4b_1 _145_ (.A(\timer[2] ),
    .B(\timer[3] ),
    .C(\timer[31] ),
    .D_N(_034_),
    .Y(_124_));
 sky130_fd_sc_hd__nor3_1 _146_ (.A(\timer[29] ),
    .B(\timer[28] ),
    .C(\timer[30] ),
    .Y(_125_));
 sky130_fd_sc_hd__nand2_1 _147_ (.A(_124_),
    .B(_125_),
    .Y(_126_));
 sky130_fd_sc_hd__nor4_1 _148_ (.A(\timer[21] ),
    .B(\timer[20] ),
    .C(\timer[23] ),
    .D(\timer[22] ),
    .Y(_127_));
 sky130_fd_sc_hd__nor4_1 _149_ (.A(\timer[25] ),
    .B(\timer[24] ),
    .C(\timer[27] ),
    .D(\timer[26] ),
    .Y(_128_));
 sky130_fd_sc_hd__nand2_1 _150_ (.A(_127_),
    .B(_128_),
    .Y(_129_));
 sky130_fd_sc_hd__nor3_4 _151_ (.A(_123_),
    .B(_126_),
    .C(_129_),
    .Y(_130_));
 sky130_fd_sc_hd__mux2i_1 _153_ (.A0(\timer[0] ),
    .A1(net2),
    .S(net7),
    .Y(_000_));
 sky130_fd_sc_hd__nand2b_1 _154_ (.A_N(net7),
    .B(_035_),
    .Y(_011_));
 sky130_fd_sc_hd__xnor2_1 _155_ (.A(\timer[2] ),
    .B(_036_),
    .Y(_132_));
 sky130_fd_sc_hd__mux2i_1 _156_ (.A0(_132_),
    .A1(net2),
    .S(net7),
    .Y(_022_));
 sky130_fd_sc_hd__o31ai_1 _157_ (.A1(\timer[2] ),
    .A2(\timer[1] ),
    .A3(\timer[0] ),
    .B1(\timer[3] ),
    .Y(_133_));
 sky130_fd_sc_hd__or4_1 _158_ (.A(\timer[2] ),
    .B(\timer[3] ),
    .C(\timer[1] ),
    .D(\timer[0] ),
    .X(_134_));
 sky130_fd_sc_hd__a21oi_1 _159_ (.A1(_133_),
    .A2(_134_),
    .B1(net7),
    .Y(_025_));
 sky130_fd_sc_hd__nor3b_1 _161_ (.A(\timer[2] ),
    .B(\timer[3] ),
    .C_N(_036_),
    .Y(_136_));
 sky130_fd_sc_hd__xnor2_1 _163_ (.A(\timer[4] ),
    .B(net8),
    .Y(_040_));
 sky130_fd_sc_hd__nor2_1 _164_ (.A(net7),
    .B(_040_),
    .Y(_026_));
 sky130_fd_sc_hd__nor2_1 _165_ (.A(\timer[4] ),
    .B(_134_),
    .Y(_041_));
 sky130_fd_sc_hd__xnor2_1 _166_ (.A(\timer[5] ),
    .B(_041_),
    .Y(_042_));
 sky130_fd_sc_hd__nor2_1 _167_ (.A(net7),
    .B(_042_),
    .Y(_027_));
 sky130_fd_sc_hd__nor2_1 _168_ (.A(\timer[4] ),
    .B(\timer[5] ),
    .Y(_043_));
 sky130_fd_sc_hd__nand2_1 _169_ (.A(_043_),
    .B(net8),
    .Y(_044_));
 sky130_fd_sc_hd__xor2_1 _170_ (.A(\timer[6] ),
    .B(_044_),
    .X(_045_));
 sky130_fd_sc_hd__nor2_1 _171_ (.A(net7),
    .B(_045_),
    .Y(_028_));
 sky130_fd_sc_hd__o41ai_1 _172_ (.A1(\timer[4] ),
    .A2(\timer[5] ),
    .A3(\timer[6] ),
    .A4(_134_),
    .B1(\timer[7] ),
    .Y(_046_));
 sky130_fd_sc_hd__nor4_1 _174_ (.A(\timer[2] ),
    .B(\timer[3] ),
    .C(\timer[1] ),
    .D(\timer[0] ),
    .Y(_048_));
 sky130_fd_sc_hd__nand2_1 _175_ (.A(_121_),
    .B(net9),
    .Y(_049_));
 sky130_fd_sc_hd__a21oi_1 _176_ (.A1(_046_),
    .A2(_049_),
    .B1(net7),
    .Y(_029_));
 sky130_fd_sc_hd__nand2_1 _177_ (.A(_121_),
    .B(net8),
    .Y(_050_));
 sky130_fd_sc_hd__xor2_1 _178_ (.A(\timer[8] ),
    .B(_050_),
    .X(_051_));
 sky130_fd_sc_hd__nor2_1 _179_ (.A(net7),
    .B(_051_),
    .Y(_030_));
 sky130_fd_sc_hd__nand3b_1 _181_ (.A_N(\timer[8] ),
    .B(_121_),
    .C(net9),
    .Y(_053_));
 sky130_fd_sc_hd__xnor2_1 _182_ (.A(\timer[9] ),
    .B(_053_),
    .Y(_054_));
 sky130_fd_sc_hd__nor2b_1 _183_ (.A(net7),
    .B_N(_054_),
    .Y(_031_));
 sky130_fd_sc_hd__nor2_1 _184_ (.A(\timer[8] ),
    .B(\timer[9] ),
    .Y(_055_));
 sky130_fd_sc_hd__nand3_1 _185_ (.A(_055_),
    .B(_121_),
    .C(net8),
    .Y(_056_));
 sky130_fd_sc_hd__xor2_1 _186_ (.A(\timer[10] ),
    .B(_056_),
    .X(_057_));
 sky130_fd_sc_hd__nor2_1 _187_ (.A(net7),
    .B(_057_),
    .Y(_001_));
 sky130_fd_sc_hd__nor3_1 _188_ (.A(\timer[8] ),
    .B(\timer[9] ),
    .C(\timer[10] ),
    .Y(_058_));
 sky130_fd_sc_hd__nand3_1 _189_ (.A(_058_),
    .B(_121_),
    .C(net9),
    .Y(_059_));
 sky130_fd_sc_hd__xor2_1 _190_ (.A(\timer[11] ),
    .B(_059_),
    .X(_060_));
 sky130_fd_sc_hd__nor2_1 _191_ (.A(net7),
    .B(_060_),
    .Y(_002_));
 sky130_fd_sc_hd__nand3_1 _192_ (.A(_119_),
    .B(_121_),
    .C(net8),
    .Y(_061_));
 sky130_fd_sc_hd__xor2_1 _193_ (.A(\timer[12] ),
    .B(_061_),
    .X(_062_));
 sky130_fd_sc_hd__nor2_1 _194_ (.A(net7),
    .B(_062_),
    .Y(_003_));
 sky130_fd_sc_hd__nor2_1 _195_ (.A(\timer[11] ),
    .B(\timer[12] ),
    .Y(_063_));
 sky130_fd_sc_hd__nand4_1 _196_ (.A(_058_),
    .B(_121_),
    .C(net9),
    .D(_063_),
    .Y(_064_));
 sky130_fd_sc_hd__xor2_1 _197_ (.A(\timer[13] ),
    .B(_064_),
    .X(_065_));
 sky130_fd_sc_hd__nor2_1 _198_ (.A(net7),
    .B(_065_),
    .Y(_004_));
 sky130_fd_sc_hd__nor2_1 _199_ (.A(\timer[12] ),
    .B(\timer[13] ),
    .Y(_066_));
 sky130_fd_sc_hd__nand4_1 _200_ (.A(_119_),
    .B(_066_),
    .C(_121_),
    .D(net8),
    .Y(_067_));
 sky130_fd_sc_hd__xor2_1 _201_ (.A(\timer[14] ),
    .B(_067_),
    .X(_068_));
 sky130_fd_sc_hd__nor2_1 _202_ (.A(net7),
    .B(_068_),
    .Y(_005_));
 sky130_fd_sc_hd__o31ai_1 _203_ (.A1(\timer[13] ),
    .A2(\timer[14] ),
    .A3(_064_),
    .B1(\timer[15] ),
    .Y(_069_));
 sky130_fd_sc_hd__nand2_1 _204_ (.A(_119_),
    .B(_120_),
    .Y(_070_));
 sky130_fd_sc_hd__or2_2 _205_ (.A(_070_),
    .B(_049_),
    .X(_071_));
 sky130_fd_sc_hd__a21oi_1 _206_ (.A1(_069_),
    .A2(_071_),
    .B1(net7),
    .Y(_006_));
 sky130_fd_sc_hd__nand4_1 _207_ (.A(_119_),
    .B(_120_),
    .C(_121_),
    .D(net8),
    .Y(_072_));
 sky130_fd_sc_hd__xor2_1 _208_ (.A(\timer[16] ),
    .B(_072_),
    .X(_073_));
 sky130_fd_sc_hd__nor2_1 _209_ (.A(net7),
    .B(_073_),
    .Y(_007_));
 sky130_fd_sc_hd__o31ai_1 _210_ (.A1(\timer[16] ),
    .A2(_070_),
    .A3(_049_),
    .B1(\timer[17] ),
    .Y(_074_));
 sky130_fd_sc_hd__or4_1 _211_ (.A(\timer[17] ),
    .B(\timer[16] ),
    .C(_070_),
    .D(_049_),
    .X(_075_));
 sky130_fd_sc_hd__a21oi_1 _212_ (.A1(_074_),
    .A2(_075_),
    .B1(net7),
    .Y(_008_));
 sky130_fd_sc_hd__o31ai_1 _213_ (.A1(\timer[17] ),
    .A2(\timer[16] ),
    .A3(_072_),
    .B1(\timer[18] ),
    .Y(_076_));
 sky130_fd_sc_hd__or4_1 _214_ (.A(\timer[17] ),
    .B(\timer[16] ),
    .C(\timer[18] ),
    .D(_072_),
    .X(_077_));
 sky130_fd_sc_hd__a21oi_1 _215_ (.A1(_076_),
    .A2(_077_),
    .B1(net7),
    .Y(_009_));
 sky130_fd_sc_hd__or3_1 _216_ (.A(\timer[17] ),
    .B(\timer[16] ),
    .C(\timer[18] ),
    .X(_078_));
 sky130_fd_sc_hd__o31ai_1 _217_ (.A1(_070_),
    .A2(_078_),
    .A3(_049_),
    .B1(\timer[19] ),
    .Y(_079_));
 sky130_fd_sc_hd__or4_1 _218_ (.A(\timer[19] ),
    .B(_070_),
    .C(_078_),
    .D(_049_),
    .X(_080_));
 sky130_fd_sc_hd__a21oi_1 _219_ (.A1(_079_),
    .A2(_080_),
    .B1(net7),
    .Y(_010_));
 sky130_fd_sc_hd__or4_4 _220_ (.A(\timer[21] ),
    .B(\timer[20] ),
    .C(\timer[23] ),
    .D(\timer[22] ),
    .X(_081_));
 sky130_fd_sc_hd__or4_4 _221_ (.A(\timer[25] ),
    .B(\timer[24] ),
    .C(\timer[26] ),
    .D(_081_),
    .X(_082_));
 sky130_fd_sc_hd__nor4_4 _222_ (.A(\timer[27] ),
    .B(_123_),
    .C(_126_),
    .D(_082_),
    .Y(_083_));
 sky130_fd_sc_hd__and4_1 _223_ (.A(_119_),
    .B(_120_),
    .C(_121_),
    .D(_122_),
    .X(_084_));
 sky130_fd_sc_hd__and3_1 _225_ (.A(\timer[20] ),
    .B(_084_),
    .C(net8),
    .X(_086_));
 sky130_fd_sc_hd__a21oi_1 _226_ (.A1(_084_),
    .A2(net8),
    .B1(\timer[20] ),
    .Y(_087_));
 sky130_fd_sc_hd__nor3_1 _227_ (.A(_083_),
    .B(_086_),
    .C(_087_),
    .Y(_012_));
 sky130_fd_sc_hd__inv_1 _228_ (.A(\timer[20] ),
    .Y(_088_));
 sky130_fd_sc_hd__and4_2 _229_ (.A(\timer[21] ),
    .B(_088_),
    .C(_084_),
    .D(net9),
    .X(_089_));
 sky130_fd_sc_hd__a31oi_1 _230_ (.A1(_088_),
    .A2(_084_),
    .A3(net9),
    .B1(\timer[21] ),
    .Y(_090_));
 sky130_fd_sc_hd__nor3_1 _231_ (.A(_083_),
    .B(_089_),
    .C(_090_),
    .Y(_013_));
 sky130_fd_sc_hd__nor2_1 _232_ (.A(\timer[21] ),
    .B(\timer[20] ),
    .Y(_091_));
 sky130_fd_sc_hd__nand3_1 _233_ (.A(\timer[22] ),
    .B(_091_),
    .C(net8),
    .Y(_092_));
 sky130_fd_sc_hd__nor2_1 _234_ (.A(_123_),
    .B(_092_),
    .Y(_093_));
 sky130_fd_sc_hd__a31oi_1 _235_ (.A1(_084_),
    .A2(_091_),
    .A3(net8),
    .B1(\timer[22] ),
    .Y(_094_));
 sky130_fd_sc_hd__nor3_1 _236_ (.A(_083_),
    .B(_093_),
    .C(_094_),
    .Y(_014_));
 sky130_fd_sc_hd__nor3_1 _237_ (.A(\timer[21] ),
    .B(\timer[20] ),
    .C(\timer[22] ),
    .Y(_095_));
 sky130_fd_sc_hd__and3_1 _238_ (.A(\timer[23] ),
    .B(_095_),
    .C(net9),
    .X(_096_));
 sky130_fd_sc_hd__a31oi_1 _239_ (.A1(_084_),
    .A2(_095_),
    .A3(net9),
    .B1(\timer[23] ),
    .Y(_097_));
 sky130_fd_sc_hd__a211oi_1 _240_ (.A1(_084_),
    .A2(_096_),
    .B1(_097_),
    .C1(_083_),
    .Y(_015_));
 sky130_fd_sc_hd__nand3_1 _241_ (.A(\timer[24] ),
    .B(_127_),
    .C(net8),
    .Y(_098_));
 sky130_fd_sc_hd__nor2_1 _242_ (.A(_123_),
    .B(_098_),
    .Y(_099_));
 sky130_fd_sc_hd__a31oi_1 _243_ (.A1(_084_),
    .A2(_127_),
    .A3(net8),
    .B1(\timer[24] ),
    .Y(_100_));
 sky130_fd_sc_hd__nor3_1 _244_ (.A(_083_),
    .B(_099_),
    .C(_100_),
    .Y(_016_));
 sky130_fd_sc_hd__nor2_1 _245_ (.A(\timer[24] ),
    .B(_081_),
    .Y(_101_));
 sky130_fd_sc_hd__and4_1 _246_ (.A(\timer[25] ),
    .B(_084_),
    .C(_101_),
    .D(net9),
    .X(_102_));
 sky130_fd_sc_hd__a31oi_1 _247_ (.A1(_084_),
    .A2(_101_),
    .A3(net9),
    .B1(\timer[25] ),
    .Y(_103_));
 sky130_fd_sc_hd__nor3_1 _248_ (.A(_083_),
    .B(_102_),
    .C(_103_),
    .Y(_017_));
 sky130_fd_sc_hd__inv_1 _249_ (.A(\timer[27] ),
    .Y(_104_));
 sky130_fd_sc_hd__and2_1 _250_ (.A(_124_),
    .B(_125_),
    .X(_105_));
 sky130_fd_sc_hd__a21oi_1 _251_ (.A1(_104_),
    .A2(_105_),
    .B1(\timer[26] ),
    .Y(_106_));
 sky130_fd_sc_hd__nand4b_1 _252_ (.A_N(\timer[25] ),
    .B(_084_),
    .C(_101_),
    .D(net8),
    .Y(_107_));
 sky130_fd_sc_hd__mux2_2 _253_ (.A0(_106_),
    .A1(\timer[26] ),
    .S(_107_),
    .X(_018_));
 sky130_fd_sc_hd__nor2_1 _254_ (.A(\timer[27] ),
    .B(_105_),
    .Y(_108_));
 sky130_fd_sc_hd__nor3_2 _255_ (.A(_123_),
    .B(_082_),
    .C(_134_),
    .Y(_109_));
 sky130_fd_sc_hd__mux2_2 _256_ (.A0(\timer[27] ),
    .A1(_108_),
    .S(_109_),
    .X(_019_));
 sky130_fd_sc_hd__nand3_1 _257_ (.A(_127_),
    .B(_128_),
    .C(net8),
    .Y(_110_));
 sky130_fd_sc_hd__o21ai_0 _258_ (.A1(_123_),
    .A2(_110_),
    .B1(\timer[28] ),
    .Y(_111_));
 sky130_fd_sc_hd__o41ai_1 _259_ (.A1(\timer[28] ),
    .A2(_123_),
    .A3(_105_),
    .A4(_110_),
    .B1(_111_),
    .Y(_020_));
 sky130_fd_sc_hd__nor2_1 _260_ (.A(\timer[29] ),
    .B(_105_),
    .Y(_112_));
 sky130_fd_sc_hd__nor4_1 _261_ (.A(\timer[28] ),
    .B(_123_),
    .C(_129_),
    .D(_134_),
    .Y(_113_));
 sky130_fd_sc_hd__mux2_2 _262_ (.A0(\timer[29] ),
    .A1(_112_),
    .S(_113_),
    .X(_021_));
 sky130_fd_sc_hd__nor2_1 _263_ (.A(\timer[30] ),
    .B(_124_),
    .Y(_114_));
 sky130_fd_sc_hd__nor4_1 _264_ (.A(\timer[29] ),
    .B(\timer[28] ),
    .C(_123_),
    .D(_110_),
    .Y(_115_));
 sky130_fd_sc_hd__mux2_2 _265_ (.A0(\timer[30] ),
    .A1(_114_),
    .S(_115_),
    .X(_023_));
 sky130_fd_sc_hd__nor2_1 _266_ (.A(\timer[31] ),
    .B(_105_),
    .Y(_116_));
 sky130_fd_sc_hd__nand2_1 _267_ (.A(_125_),
    .B(net9),
    .Y(_117_));
 sky130_fd_sc_hd__nor3_1 _268_ (.A(_123_),
    .B(_129_),
    .C(_117_),
    .Y(_118_));
 sky130_fd_sc_hd__mux2_2 _269_ (.A0(\timer[31] ),
    .A1(_116_),
    .S(_118_),
    .X(_024_));
 sky130_fd_sc_hd__inv_1 _270_ (.A(\timer[1] ),
    .Y(_033_));
 sky130_fd_sc_hd__mux2_2 _271_ (.A0(net4),
    .A1(net2),
    .S(net7),
    .X(_037_));
 sky130_fd_sc_hd__mux2_2 _272_ (.A0(net3),
    .A1(net4),
    .S(net7),
    .X(_038_));
 sky130_fd_sc_hd__mux2_2 _273_ (.A0(net2),
    .A1(net3),
    .S(net7),
    .X(_039_));
 sky130_fd_sc_hd__ha_1 _274_ (.A(_032_),
    .B(_033_),
    .COUT(_034_),
    .SUM(_035_));
 sky130_fd_sc_hd__ha_1 _275_ (.A(_032_),
    .B(_033_),
    .COUT(_036_),
    .SUM(_138_));
 sky130_fd_sc_hd__dfrtp_1 _276_ (.D(_037_),
    .Q(net4),
    .RESET_B(net10),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 _277_ (.D(_038_),
    .Q(net3),
    .RESET_B(net10),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfstp_2 _278_ (.D(_039_),
    .Q(net2),
    .SET_B(net10),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_0_clk (.A(clk),
    .X(clknet_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_2_0__f_clk (.A(clknet_0_clk),
    .X(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_2_1__f_clk (.A(clknet_0_clk),
    .X(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_2_2__f_clk (.A(clknet_0_clk),
    .X(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_2_3__f_clk (.A(clknet_0_clk),
    .X(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__clkbuf_8 clkload0 (.A(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__clkinvlp_4 clkload1 (.A(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__clkbuf_8 clkload2 (.A(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__buf_2 input1 (.A(rst_n),
    .X(net1));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output2 (.A(net2),
    .X(green));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output3 (.A(net3),
    .X(red));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output4 (.A(net4),
    .X(yellow));
 sky130_fd_sc_hd__buf_4 place10 (.A(net1),
    .X(net10));
 sky130_fd_sc_hd__buf_4 place7 (.A(_130_),
    .X(net7));
 sky130_fd_sc_hd__buf_4 place8 (.A(_136_),
    .X(net8));
 sky130_fd_sc_hd__buf_4 place9 (.A(_048_),
    .X(net9));
 sky130_fd_sc_hd__dfstp_2 \timer[0]$_DFF_PN1_  (.D(_000_),
    .Q(\timer[0] ),
    .SET_B(net10),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[10]$_DFF_PN0_  (.D(_001_),
    .Q(\timer[10] ),
    .RESET_B(net10),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[11]$_DFF_PN0_  (.D(_002_),
    .Q(\timer[11] ),
    .RESET_B(net10),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[12]$_DFF_PN0_  (.D(_003_),
    .Q(\timer[12] ),
    .RESET_B(net10),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[13]$_DFF_PN0_  (.D(_004_),
    .Q(\timer[13] ),
    .RESET_B(net10),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[14]$_DFF_PN0_  (.D(_005_),
    .Q(\timer[14] ),
    .RESET_B(net10),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[15]$_DFF_PN0_  (.D(_006_),
    .Q(\timer[15] ),
    .RESET_B(net10),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[16]$_DFF_PN0_  (.D(_007_),
    .Q(\timer[16] ),
    .RESET_B(net10),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[17]$_DFF_PN0_  (.D(_008_),
    .Q(\timer[17] ),
    .RESET_B(net10),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[18]$_DFF_PN0_  (.D(_009_),
    .Q(\timer[18] ),
    .RESET_B(net10),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[19]$_DFF_PN0_  (.D(_010_),
    .Q(\timer[19] ),
    .RESET_B(net10),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfstp_2 \timer[1]$_DFF_PN1_  (.D(_011_),
    .Q(\timer[1] ),
    .SET_B(net10),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[20]$_DFF_PN0_  (.D(_012_),
    .Q(\timer[20] ),
    .RESET_B(net10),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[21]$_DFF_PN0_  (.D(_013_),
    .Q(\timer[21] ),
    .RESET_B(net10),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[22]$_DFF_PN0_  (.D(_014_),
    .Q(\timer[22] ),
    .RESET_B(net10),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[23]$_DFF_PN0_  (.D(_015_),
    .Q(\timer[23] ),
    .RESET_B(net10),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[24]$_DFF_PN0_  (.D(_016_),
    .Q(\timer[24] ),
    .RESET_B(net10),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[25]$_DFF_PN0_  (.D(_017_),
    .Q(\timer[25] ),
    .RESET_B(net10),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[26]$_DFF_PN0_  (.D(_018_),
    .Q(\timer[26] ),
    .RESET_B(net10),
    .CLK(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[27]$_DFF_PN0_  (.D(_019_),
    .Q(\timer[27] ),
    .RESET_B(net10),
    .CLK(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[28]$_DFF_PN0_  (.D(_020_),
    .Q(\timer[28] ),
    .RESET_B(net10),
    .CLK(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[29]$_DFF_PN0_  (.D(_021_),
    .Q(\timer[29] ),
    .RESET_B(net10),
    .CLK(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__dfstp_2 \timer[2]$_DFF_PN1_  (.D(_022_),
    .Q(\timer[2] ),
    .SET_B(net10),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[30]$_DFF_PN0_  (.D(_023_),
    .Q(\timer[30] ),
    .RESET_B(net10),
    .CLK(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[31]$_DFF_PN0_  (.D(_024_),
    .Q(\timer[31] ),
    .RESET_B(net10),
    .CLK(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[3]$_DFF_PN0_  (.D(_025_),
    .Q(\timer[3] ),
    .RESET_B(net10),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[4]$_DFF_PN0_  (.D(_026_),
    .Q(\timer[4] ),
    .RESET_B(net10),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[5]$_DFF_PN0_  (.D(_027_),
    .Q(\timer[5] ),
    .RESET_B(net10),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[6]$_DFF_PN0_  (.D(_028_),
    .Q(\timer[6] ),
    .RESET_B(net10),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[7]$_DFF_PN0_  (.D(_029_),
    .Q(\timer[7] ),
    .RESET_B(net10),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[8]$_DFF_PN0_  (.D(_030_),
    .Q(\timer[8] ),
    .RESET_B(net10),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \timer[9]$_DFF_PN0_  (.D(_031_),
    .Q(\timer[9] ),
    .RESET_B(net10),
    .CLK(clknet_2_3__leaf_clk));
endmodule
