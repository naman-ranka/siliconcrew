module seven_segment_seconds (clk,
    rst_n,
    seg);
 input clk;
 input rst_n;
 output [6:0] seg;

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
 wire _047_;
 wire _048_;
 wire _049_;
 wire _050_;
 wire _051_;
 wire _052_;
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
 wire _085_;
 wire _086_;
 wire _087_;
 wire _088_;
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
 wire _131_;
 wire _132_;
 wire _133_;
 wire _134_;
 wire _135_;
 wire _136_;
 wire _137_;
 wire _138_;
 wire _139_;
 wire _140_;
 wire _141_;
 wire _142_;
 wire _143_;
 wire _144_;
 wire _145_;
 wire _146_;
 wire _147_;
 wire _148_;
 wire _149_;
 wire _150_;
 wire _151_;
 wire _153_;
 wire _154_;
 wire _155_;
 wire _156_;
 wire _157_;
 wire _158_;
 wire _159_;
 wire _160_;
 wire _161_;
 wire _162_;
 wire _163_;
 wire _164_;
 wire _165_;
 wire _166_;
 wire _167_;
 wire _168_;
 wire \digit[0] ;
 wire \digit[1] ;
 wire \digit[2] ;
 wire \digit[3] ;
 wire net1;
 wire \second_counter[0] ;
 wire \second_counter[10] ;
 wire \second_counter[11] ;
 wire \second_counter[12] ;
 wire \second_counter[13] ;
 wire \second_counter[14] ;
 wire \second_counter[15] ;
 wire \second_counter[16] ;
 wire \second_counter[17] ;
 wire \second_counter[18] ;
 wire \second_counter[19] ;
 wire \second_counter[1] ;
 wire \second_counter[20] ;
 wire \second_counter[21] ;
 wire \second_counter[22] ;
 wire \second_counter[23] ;
 wire \second_counter[2] ;
 wire \second_counter[3] ;
 wire \second_counter[4] ;
 wire \second_counter[5] ;
 wire \second_counter[6] ;
 wire \second_counter[7] ;
 wire \second_counter[8] ;
 wire \second_counter[9] ;
 wire net2;
 wire net3;
 wire net4;
 wire net5;
 wire net6;
 wire net7;
 wire net8;
 wire clknet_0_clk;
 wire net10;
 wire clknet_2_0__leaf_clk;
 wire clknet_2_1__leaf_clk;
 wire clknet_2_2__leaf_clk;
 wire clknet_2_3__leaf_clk;

 sky130_fd_sc_hd__inv_1 _169_ (.A(\digit[1] ),
    .Y(_012_));
 sky130_fd_sc_hd__nor4b_2 _170_ (.A(\second_counter[4] ),
    .B(\second_counter[5] ),
    .C(\second_counter[6] ),
    .D_N(\second_counter[7] ),
    .Y(_148_));
 sky130_fd_sc_hd__and4b_1 _171_ (.A_N(\second_counter[3] ),
    .B(\second_counter[12] ),
    .C(\second_counter[19] ),
    .D(\second_counter[20] ),
    .X(_149_));
 sky130_fd_sc_hd__nand2_1 _172_ (.A(_148_),
    .B(_149_),
    .Y(_150_));
 sky130_fd_sc_hd__and4bb_2 _173_ (.A_N(\second_counter[8] ),
    .B_N(\second_counter[11] ),
    .C(\second_counter[10] ),
    .D(\second_counter[9] ),
    .X(_151_));
 sky130_fd_sc_hd__nor4b_4 _175_ (.A(\second_counter[2] ),
    .B(\second_counter[13] ),
    .C(\second_counter[14] ),
    .D_N(\second_counter[15] ),
    .Y(_153_));
 sky130_fd_sc_hd__nor4_4 _176_ (.A(\second_counter[16] ),
    .B(\second_counter[17] ),
    .C(\second_counter[18] ),
    .D(\second_counter[21] ),
    .Y(_154_));
 sky130_fd_sc_hd__and3b_1 _177_ (.A_N(\second_counter[22] ),
    .B(\second_counter[23] ),
    .C(_009_),
    .X(_155_));
 sky130_fd_sc_hd__nand4_4 _178_ (.A(_151_),
    .B(_153_),
    .C(_154_),
    .D(_155_),
    .Y(_156_));
 sky130_fd_sc_hd__nor2_1 _179_ (.A(_150_),
    .B(_156_),
    .Y(_157_));
 sky130_fd_sc_hd__and3b_1 _180_ (.A_N(\digit[2] ),
    .B(\digit[3] ),
    .C(_013_),
    .X(_158_));
 sky130_fd_sc_hd__nor2_1 _181_ (.A(_014_),
    .B(_158_),
    .Y(_159_));
 sky130_fd_sc_hd__and2_1 _182_ (.A(_148_),
    .B(_149_),
    .X(_160_));
 sky130_fd_sc_hd__and4_2 _183_ (.A(_151_),
    .B(_153_),
    .C(_154_),
    .D(_155_),
    .X(_161_));
 sky130_fd_sc_hd__nand3_1 _184_ (.A(_159_),
    .B(_160_),
    .C(_161_),
    .Y(_055_));
 sky130_fd_sc_hd__o21ai_0 _185_ (.A1(_012_),
    .A2(_157_),
    .B1(_055_),
    .Y(_056_));
 sky130_fd_sc_hd__and2_1 _186_ (.A(net1),
    .B(_056_),
    .X(_016_));
 sky130_fd_sc_hd__inv_1 _187_ (.A(_016_),
    .Y(_021_));
 sky130_fd_sc_hd__inv_1 _188_ (.A(net1),
    .Y(_057_));
 sky130_fd_sc_hd__nor2_1 _189_ (.A(\digit[0] ),
    .B(_158_),
    .Y(_058_));
 sky130_fd_sc_hd__mux2i_1 _190_ (.A0(\digit[0] ),
    .A1(_058_),
    .S(_157_),
    .Y(_059_));
 sky130_fd_sc_hd__nor2_1 _191_ (.A(_057_),
    .B(_059_),
    .Y(_024_));
 sky130_fd_sc_hd__o211ai_1 _192_ (.A1(_150_),
    .A2(_156_),
    .B1(\digit[0] ),
    .C1(\digit[1] ),
    .Y(_060_));
 sky130_fd_sc_hd__nand4b_1 _193_ (.A_N(\digit[0] ),
    .B(_159_),
    .C(_160_),
    .D(_161_),
    .Y(_061_));
 sky130_fd_sc_hd__a21oi_1 _194_ (.A1(_060_),
    .A2(_061_),
    .B1(_057_),
    .Y(_062_));
 sky130_fd_sc_hd__nand3_1 _195_ (.A(\digit[2] ),
    .B(\digit[0] ),
    .C(\digit[1] ),
    .Y(_063_));
 sky130_fd_sc_hd__nor2b_1 _196_ (.A(_158_),
    .B_N(_063_),
    .Y(_064_));
 sky130_fd_sc_hd__o31a_2 _197_ (.A1(_150_),
    .A2(_156_),
    .A3(_064_),
    .B1(\digit[3] ),
    .X(_065_));
 sky130_fd_sc_hd__nor4_1 _198_ (.A(\digit[3] ),
    .B(_150_),
    .C(_156_),
    .D(_063_),
    .Y(_066_));
 sky130_fd_sc_hd__o21ai_2 _199_ (.A1(_065_),
    .A2(_066_),
    .B1(net1),
    .Y(_067_));
 sky130_fd_sc_hd__nand3_1 _200_ (.A(_015_),
    .B(_148_),
    .C(_149_),
    .Y(_068_));
 sky130_fd_sc_hd__o21ai_1 _201_ (.A1(_156_),
    .A2(_068_),
    .B1(\digit[2] ),
    .Y(_069_));
 sky130_fd_sc_hd__a21oi_1 _202_ (.A1(\digit[3] ),
    .A2(_013_),
    .B1(\digit[2] ),
    .Y(_070_));
 sky130_fd_sc_hd__nand4_4 _203_ (.A(_015_),
    .B(_160_),
    .C(_161_),
    .D(_070_),
    .Y(_071_));
 sky130_fd_sc_hd__a21oi_2 _204_ (.A1(_069_),
    .A2(_071_),
    .B1(_057_),
    .Y(_029_));
 sky130_fd_sc_hd__nor2_1 _205_ (.A(_067_),
    .B(_029_),
    .Y(_072_));
 sky130_fd_sc_hd__inv_1 _206_ (.A(_067_),
    .Y(_030_));
 sky130_fd_sc_hd__o31ai_1 _207_ (.A1(_150_),
    .A2(_156_),
    .A3(_063_),
    .B1(\digit[3] ),
    .Y(_073_));
 sky130_fd_sc_hd__or4_4 _208_ (.A(\digit[3] ),
    .B(_150_),
    .C(_156_),
    .D(_063_),
    .X(_074_));
 sky130_fd_sc_hd__a221oi_4 _209_ (.A1(_069_),
    .A2(_071_),
    .B1(_073_),
    .B2(_074_),
    .C1(_057_),
    .Y(_075_));
 sky130_fd_sc_hd__o21bai_1 _210_ (.A1(_030_),
    .A2(_029_),
    .B1_N(_075_),
    .Y(_076_));
 sky130_fd_sc_hd__and3_1 _211_ (.A(_022_),
    .B(_067_),
    .C(_029_),
    .X(_077_));
 sky130_fd_sc_hd__a221oi_2 _212_ (.A1(_062_),
    .A2(_072_),
    .B1(_076_),
    .B2(_025_),
    .C1(_077_),
    .Y(_000_));
 sky130_fd_sc_hd__xor2_1 _213_ (.A(\digit[0] ),
    .B(_157_),
    .X(_078_));
 sky130_fd_sc_hd__nand2_1 _214_ (.A(_030_),
    .B(_078_),
    .Y(_079_));
 sky130_fd_sc_hd__nand2_1 _215_ (.A(_019_),
    .B(_067_),
    .Y(_080_));
 sky130_fd_sc_hd__a32oi_1 _216_ (.A1(_029_),
    .A2(_079_),
    .A3(_080_),
    .B1(_030_),
    .B2(_062_),
    .Y(_001_));
 sky130_fd_sc_hd__inv_1 _217_ (.A(_026_),
    .Y(_081_));
 sky130_fd_sc_hd__nor2_1 _218_ (.A(_030_),
    .B(_029_),
    .Y(_082_));
 sky130_fd_sc_hd__a22oi_1 _219_ (.A1(_081_),
    .A2(_075_),
    .B1(_082_),
    .B2(_018_),
    .Y(_002_));
 sky130_fd_sc_hd__a32o_1 _220_ (.A1(_019_),
    .A2(_067_),
    .A3(_029_),
    .B1(_075_),
    .B2(_062_),
    .X(_083_));
 sky130_fd_sc_hd__a221oi_1 _221_ (.A1(_018_),
    .A2(_072_),
    .B1(_082_),
    .B2(_025_),
    .C1(_083_),
    .Y(_003_));
 sky130_fd_sc_hd__nand2b_1 _222_ (.A_N(_029_),
    .B(_023_),
    .Y(_084_));
 sky130_fd_sc_hd__nor2_1 _223_ (.A(_020_),
    .B(_030_),
    .Y(_085_));
 sky130_fd_sc_hd__a22oi_1 _224_ (.A1(_025_),
    .A2(_072_),
    .B1(_084_),
    .B2(_085_),
    .Y(_004_));
 sky130_fd_sc_hd__and3_1 _225_ (.A(_062_),
    .B(_067_),
    .C(_029_),
    .X(_086_));
 sky130_fd_sc_hd__nor3_1 _226_ (.A(_023_),
    .B(_030_),
    .C(_029_),
    .Y(_087_));
 sky130_fd_sc_hd__a211oi_1 _227_ (.A1(_025_),
    .A2(_075_),
    .B1(_086_),
    .C1(_087_),
    .Y(_005_));
 sky130_fd_sc_hd__a221oi_1 _228_ (.A1(_022_),
    .A2(_075_),
    .B1(_082_),
    .B2(_021_),
    .C1(_086_),
    .Y(_006_));
 sky130_fd_sc_hd__inv_1 _229_ (.A(\second_counter[0] ),
    .Y(_007_));
 sky130_fd_sc_hd__inv_1 _230_ (.A(\second_counter[1] ),
    .Y(_008_));
 sky130_fd_sc_hd__inv_1 _231_ (.A(_024_),
    .Y(_017_));
 sky130_fd_sc_hd__o21ai_1 _232_ (.A1(_150_),
    .A2(_156_),
    .B1(net1),
    .Y(_088_));
 sky130_fd_sc_hd__nor2_1 _234_ (.A(\second_counter[0] ),
    .B(net10),
    .Y(_031_));
 sky130_fd_sc_hd__and4_2 _235_ (.A(_011_),
    .B(\second_counter[2] ),
    .C(\second_counter[3] ),
    .D(\second_counter[4] ),
    .X(_090_));
 sky130_fd_sc_hd__and4_1 _236_ (.A(\second_counter[5] ),
    .B(\second_counter[6] ),
    .C(\second_counter[7] ),
    .D(\second_counter[8] ),
    .X(_091_));
 sky130_fd_sc_hd__and3_1 _237_ (.A(\second_counter[9] ),
    .B(_090_),
    .C(_091_),
    .X(_092_));
 sky130_fd_sc_hd__xnor2_1 _238_ (.A(\second_counter[10] ),
    .B(_092_),
    .Y(_093_));
 sky130_fd_sc_hd__nor2_1 _239_ (.A(net10),
    .B(_093_),
    .Y(_032_));
 sky130_fd_sc_hd__nand2_1 _240_ (.A(\second_counter[9] ),
    .B(_091_),
    .Y(_094_));
 sky130_fd_sc_hd__and3_1 _241_ (.A(\second_counter[1] ),
    .B(\second_counter[0] ),
    .C(\second_counter[4] ),
    .X(_095_));
 sky130_fd_sc_hd__nand3_1 _242_ (.A(\second_counter[2] ),
    .B(\second_counter[3] ),
    .C(_095_),
    .Y(_096_));
 sky130_fd_sc_hd__nor2_1 _243_ (.A(_094_),
    .B(_096_),
    .Y(_097_));
 sky130_fd_sc_hd__nand2_1 _244_ (.A(\second_counter[10] ),
    .B(_097_),
    .Y(_098_));
 sky130_fd_sc_hd__xor2_1 _245_ (.A(\second_counter[11] ),
    .B(_098_),
    .X(_099_));
 sky130_fd_sc_hd__nor2_1 _246_ (.A(net10),
    .B(_099_),
    .Y(_033_));
 sky130_fd_sc_hd__nand3_1 _247_ (.A(\second_counter[10] ),
    .B(\second_counter[11] ),
    .C(_092_),
    .Y(_100_));
 sky130_fd_sc_hd__xor2_1 _248_ (.A(\second_counter[12] ),
    .B(_100_),
    .X(_101_));
 sky130_fd_sc_hd__nor2_1 _249_ (.A(net10),
    .B(_101_),
    .Y(_034_));
 sky130_fd_sc_hd__nand4_1 _250_ (.A(\second_counter[10] ),
    .B(\second_counter[11] ),
    .C(\second_counter[12] ),
    .D(_097_),
    .Y(_102_));
 sky130_fd_sc_hd__xor2_1 _251_ (.A(\second_counter[13] ),
    .B(_102_),
    .X(_103_));
 sky130_fd_sc_hd__nor2_1 _252_ (.A(net10),
    .B(_103_),
    .Y(_035_));
 sky130_fd_sc_hd__and4_1 _253_ (.A(\second_counter[10] ),
    .B(\second_counter[11] ),
    .C(\second_counter[12] ),
    .D(\second_counter[13] ),
    .X(_104_));
 sky130_fd_sc_hd__nand2_1 _254_ (.A(_092_),
    .B(_104_),
    .Y(_105_));
 sky130_fd_sc_hd__xor2_1 _255_ (.A(\second_counter[14] ),
    .B(_105_),
    .X(_106_));
 sky130_fd_sc_hd__nor2_1 _256_ (.A(net10),
    .B(_106_),
    .Y(_036_));
 sky130_fd_sc_hd__nand2_1 _257_ (.A(\second_counter[14] ),
    .B(_104_),
    .Y(_107_));
 sky130_fd_sc_hd__nor3_1 _258_ (.A(_094_),
    .B(_096_),
    .C(_107_),
    .Y(_108_));
 sky130_fd_sc_hd__xnor2_1 _259_ (.A(\second_counter[15] ),
    .B(_108_),
    .Y(_109_));
 sky130_fd_sc_hd__nor2_1 _260_ (.A(net10),
    .B(_109_),
    .Y(_037_));
 sky130_fd_sc_hd__nand3_1 _261_ (.A(\second_counter[9] ),
    .B(_090_),
    .C(_091_),
    .Y(_110_));
 sky130_fd_sc_hd__nor2_1 _262_ (.A(_110_),
    .B(_107_),
    .Y(_111_));
 sky130_fd_sc_hd__nand2_1 _263_ (.A(\second_counter[15] ),
    .B(_111_),
    .Y(_112_));
 sky130_fd_sc_hd__xor2_1 _264_ (.A(\second_counter[16] ),
    .B(_112_),
    .X(_113_));
 sky130_fd_sc_hd__nor2_1 _265_ (.A(net10),
    .B(_113_),
    .Y(_038_));
 sky130_fd_sc_hd__nand3_1 _266_ (.A(\second_counter[15] ),
    .B(\second_counter[16] ),
    .C(_108_),
    .Y(_114_));
 sky130_fd_sc_hd__xor2_1 _267_ (.A(\second_counter[17] ),
    .B(_114_),
    .X(_115_));
 sky130_fd_sc_hd__nor2_1 _268_ (.A(net10),
    .B(_115_),
    .Y(_039_));
 sky130_fd_sc_hd__nand4_1 _270_ (.A(\second_counter[15] ),
    .B(\second_counter[16] ),
    .C(\second_counter[17] ),
    .D(_111_),
    .Y(_117_));
 sky130_fd_sc_hd__xor2_1 _271_ (.A(\second_counter[18] ),
    .B(_117_),
    .X(_118_));
 sky130_fd_sc_hd__nor2_1 _272_ (.A(net10),
    .B(_118_),
    .Y(_040_));
 sky130_fd_sc_hd__nand4_1 _273_ (.A(\second_counter[15] ),
    .B(\second_counter[16] ),
    .C(\second_counter[17] ),
    .D(\second_counter[18] ),
    .Y(_119_));
 sky130_fd_sc_hd__nor4_1 _274_ (.A(_094_),
    .B(_096_),
    .C(_107_),
    .D(_119_),
    .Y(_120_));
 sky130_fd_sc_hd__xnor2_1 _275_ (.A(\second_counter[19] ),
    .B(_120_),
    .Y(_121_));
 sky130_fd_sc_hd__nor2_1 _276_ (.A(net10),
    .B(_121_),
    .Y(_041_));
 sky130_fd_sc_hd__inv_1 _277_ (.A(_010_),
    .Y(_122_));
 sky130_fd_sc_hd__nor2_1 _278_ (.A(_122_),
    .B(net10),
    .Y(_042_));
 sky130_fd_sc_hd__nor3_1 _279_ (.A(_110_),
    .B(_107_),
    .C(_119_),
    .Y(_123_));
 sky130_fd_sc_hd__nand2_1 _280_ (.A(\second_counter[19] ),
    .B(_123_),
    .Y(_124_));
 sky130_fd_sc_hd__xor2_1 _281_ (.A(\second_counter[20] ),
    .B(_124_),
    .X(_125_));
 sky130_fd_sc_hd__nor2_1 _282_ (.A(net10),
    .B(_125_),
    .Y(_043_));
 sky130_fd_sc_hd__nand3_1 _283_ (.A(\second_counter[19] ),
    .B(\second_counter[20] ),
    .C(_120_),
    .Y(_126_));
 sky130_fd_sc_hd__xor2_1 _284_ (.A(\second_counter[21] ),
    .B(_126_),
    .X(_127_));
 sky130_fd_sc_hd__nor2_1 _285_ (.A(net10),
    .B(_127_),
    .Y(_044_));
 sky130_fd_sc_hd__and3_1 _286_ (.A(\second_counter[19] ),
    .B(\second_counter[20] ),
    .C(\second_counter[21] ),
    .X(_128_));
 sky130_fd_sc_hd__nand2_1 _287_ (.A(_123_),
    .B(_128_),
    .Y(_129_));
 sky130_fd_sc_hd__xor2_1 _288_ (.A(\second_counter[22] ),
    .B(_129_),
    .X(_130_));
 sky130_fd_sc_hd__nor2_1 _289_ (.A(net10),
    .B(_130_),
    .Y(_045_));
 sky130_fd_sc_hd__nand3_1 _290_ (.A(\second_counter[22] ),
    .B(_120_),
    .C(_128_),
    .Y(_131_));
 sky130_fd_sc_hd__xor2_1 _291_ (.A(\second_counter[23] ),
    .B(_131_),
    .X(_132_));
 sky130_fd_sc_hd__nor2_1 _292_ (.A(net10),
    .B(_132_),
    .Y(_046_));
 sky130_fd_sc_hd__xnor2_1 _293_ (.A(_011_),
    .B(\second_counter[2] ),
    .Y(_133_));
 sky130_fd_sc_hd__nor2_1 _294_ (.A(net10),
    .B(_133_),
    .Y(_047_));
 sky130_fd_sc_hd__nand3_1 _295_ (.A(\second_counter[2] ),
    .B(\second_counter[1] ),
    .C(\second_counter[0] ),
    .Y(_134_));
 sky130_fd_sc_hd__xor2_1 _296_ (.A(\second_counter[3] ),
    .B(_134_),
    .X(_135_));
 sky130_fd_sc_hd__nor2_1 _297_ (.A(net10),
    .B(_135_),
    .Y(_048_));
 sky130_fd_sc_hd__nand3_1 _298_ (.A(_011_),
    .B(\second_counter[2] ),
    .C(\second_counter[3] ),
    .Y(_136_));
 sky130_fd_sc_hd__xor2_1 _299_ (.A(\second_counter[4] ),
    .B(_136_),
    .X(_137_));
 sky130_fd_sc_hd__nor2_1 _300_ (.A(net10),
    .B(_137_),
    .Y(_049_));
 sky130_fd_sc_hd__xor2_1 _301_ (.A(\second_counter[5] ),
    .B(_096_),
    .X(_138_));
 sky130_fd_sc_hd__nor2_1 _302_ (.A(net10),
    .B(_138_),
    .Y(_050_));
 sky130_fd_sc_hd__nand2_1 _303_ (.A(\second_counter[5] ),
    .B(_090_),
    .Y(_139_));
 sky130_fd_sc_hd__xor2_1 _304_ (.A(\second_counter[6] ),
    .B(_139_),
    .X(_140_));
 sky130_fd_sc_hd__nor2_1 _305_ (.A(net10),
    .B(_140_),
    .Y(_051_));
 sky130_fd_sc_hd__nand2_1 _306_ (.A(\second_counter[5] ),
    .B(\second_counter[6] ),
    .Y(_141_));
 sky130_fd_sc_hd__nor2_1 _307_ (.A(_141_),
    .B(_096_),
    .Y(_142_));
 sky130_fd_sc_hd__xnor2_1 _308_ (.A(\second_counter[7] ),
    .B(_142_),
    .Y(_143_));
 sky130_fd_sc_hd__nor2_1 _309_ (.A(net10),
    .B(_143_),
    .Y(_052_));
 sky130_fd_sc_hd__nand4_1 _310_ (.A(\second_counter[5] ),
    .B(\second_counter[6] ),
    .C(\second_counter[7] ),
    .D(_090_),
    .Y(_144_));
 sky130_fd_sc_hd__xor2_1 _311_ (.A(\second_counter[8] ),
    .B(_144_),
    .X(_145_));
 sky130_fd_sc_hd__nor2_1 _312_ (.A(net10),
    .B(_145_),
    .Y(_053_));
 sky130_fd_sc_hd__nand4_1 _313_ (.A(\second_counter[2] ),
    .B(\second_counter[3] ),
    .C(_091_),
    .D(_095_),
    .Y(_146_));
 sky130_fd_sc_hd__xor2_1 _314_ (.A(\second_counter[9] ),
    .B(_146_),
    .X(_147_));
 sky130_fd_sc_hd__nor2_1 _315_ (.A(net10),
    .B(_147_),
    .Y(_054_));
 sky130_fd_sc_hd__nor2_1 _316_ (.A(_057_),
    .B(_059_),
    .Y(_027_));
 sky130_fd_sc_hd__and2_1 _317_ (.A(net1),
    .B(_056_),
    .X(_028_));
 sky130_fd_sc_hd__ha_1 _318_ (.A(_007_),
    .B(_008_),
    .COUT(_009_),
    .SUM(_010_));
 sky130_fd_sc_hd__ha_1 _319_ (.A(\second_counter[0] ),
    .B(\second_counter[1] ),
    .COUT(_011_),
    .SUM(_162_));
 sky130_fd_sc_hd__ha_1 _320_ (.A(\digit[0] ),
    .B(_012_),
    .COUT(_013_),
    .SUM(_014_));
 sky130_fd_sc_hd__ha_1 _321_ (.A(\digit[0] ),
    .B(\digit[1] ),
    .COUT(_015_),
    .SUM(_163_));
 sky130_fd_sc_hd__ha_1 _322_ (.A(_016_),
    .B(_017_),
    .COUT(_018_),
    .SUM(_019_));
 sky130_fd_sc_hd__ha_1 _323_ (.A(_016_),
    .B(_017_),
    .COUT(_020_),
    .SUM(_164_));
 sky130_fd_sc_hd__ha_1 _324_ (.A(_021_),
    .B(_017_),
    .COUT(_022_),
    .SUM(_165_));
 sky130_fd_sc_hd__ha_1 _325_ (.A(_021_),
    .B(_017_),
    .COUT(_023_),
    .SUM(_166_));
 sky130_fd_sc_hd__ha_1 _326_ (.A(_021_),
    .B(_024_),
    .COUT(_025_),
    .SUM(_167_));
 sky130_fd_sc_hd__ha_1 _327_ (.A(_021_),
    .B(_024_),
    .COUT(_026_),
    .SUM(_168_));
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
 sky130_fd_sc_hd__clkbuf_1 clkload0 (.A(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__clkbuf_8 clkload1 (.A(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__clkbuf_8 clkload2 (.A(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \digit[0]$_SDFFE_PN0N_  (.D(_027_),
    .Q(\digit[0] ),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \digit[1]$_SDFFE_PN0N_  (.D(_028_),
    .Q(\digit[1] ),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \digit[2]$_SDFFE_PN0N_  (.D(_029_),
    .Q(\digit[2] ),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \digit[3]$_SDFFE_PN0N_  (.D(_030_),
    .Q(\digit[3] ),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input1 (.A(rst_n),
    .X(net1));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output2 (.A(net2),
    .X(seg[0]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output3 (.A(net3),
    .X(seg[1]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output4 (.A(net4),
    .X(seg[2]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output5 (.A(net5),
    .X(seg[3]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output6 (.A(net6),
    .X(seg[4]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output7 (.A(net7),
    .X(seg[5]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output8 (.A(net8),
    .X(seg[6]));
 sky130_fd_sc_hd__buf_4 place10 (.A(_088_),
    .X(net10));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[0]$_SDFF_PP0_  (.D(_031_),
    .Q(\second_counter[0] ),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[10]$_SDFF_PP0_  (.D(_032_),
    .Q(\second_counter[10] ),
    .CLK(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[11]$_SDFF_PP0_  (.D(_033_),
    .Q(\second_counter[11] ),
    .CLK(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[12]$_SDFF_PP0_  (.D(_034_),
    .Q(\second_counter[12] ),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[13]$_SDFF_PP0_  (.D(_035_),
    .Q(\second_counter[13] ),
    .CLK(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[14]$_SDFF_PP0_  (.D(_036_),
    .Q(\second_counter[14] ),
    .CLK(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[15]$_SDFF_PP0_  (.D(_037_),
    .Q(\second_counter[15] ),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[16]$_SDFF_PP0_  (.D(_038_),
    .Q(\second_counter[16] ),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[17]$_SDFF_PP0_  (.D(_039_),
    .Q(\second_counter[17] ),
    .CLK(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[18]$_SDFF_PP0_  (.D(_040_),
    .Q(\second_counter[18] ),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[19]$_SDFF_PP0_  (.D(_041_),
    .Q(\second_counter[19] ),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[1]$_SDFF_PP0_  (.D(_042_),
    .Q(\second_counter[1] ),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[20]$_SDFF_PP0_  (.D(_043_),
    .Q(\second_counter[20] ),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[21]$_SDFF_PP0_  (.D(_044_),
    .Q(\second_counter[21] ),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[22]$_SDFF_PP0_  (.D(_045_),
    .Q(\second_counter[22] ),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[23]$_SDFF_PP0_  (.D(_046_),
    .Q(\second_counter[23] ),
    .CLK(clknet_2_0__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[2]$_SDFF_PP0_  (.D(_047_),
    .Q(\second_counter[2] ),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[3]$_SDFF_PP0_  (.D(_048_),
    .Q(\second_counter[3] ),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[4]$_SDFF_PP0_  (.D(_049_),
    .Q(\second_counter[4] ),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[5]$_SDFF_PP0_  (.D(_050_),
    .Q(\second_counter[5] ),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[6]$_SDFF_PP0_  (.D(_051_),
    .Q(\second_counter[6] ),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[7]$_SDFF_PP0_  (.D(_052_),
    .Q(\second_counter[7] ),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[8]$_SDFF_PP0_  (.D(_053_),
    .Q(\second_counter[8] ),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \second_counter[9]$_SDFF_PP0_  (.D(_054_),
    .Q(\second_counter[9] ),
    .CLK(clknet_2_1__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \seg[0]$_DFF_P_  (.D(_000_),
    .Q(net2),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \seg[1]$_DFF_P_  (.D(_001_),
    .Q(net3),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \seg[2]$_DFF_P_  (.D(_002_),
    .Q(net4),
    .CLK(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \seg[3]$_DFF_P_  (.D(_003_),
    .Q(net5),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \seg[4]$_DFF_P_  (.D(_004_),
    .Q(net6),
    .CLK(clknet_2_3__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \seg[5]$_DFF_P_  (.D(_005_),
    .Q(net7),
    .CLK(clknet_2_2__leaf_clk));
 sky130_fd_sc_hd__dfxtp_1 \seg[6]$_DFF_P_  (.D(_006_),
    .Q(net8),
    .CLK(clknet_2_2__leaf_clk));
endmodule
