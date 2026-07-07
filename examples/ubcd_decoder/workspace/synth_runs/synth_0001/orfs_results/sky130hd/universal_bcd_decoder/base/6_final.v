module universal_bcd_decoder (A,
    AL,
    B,
    BI,
    C,
    D,
    LT,
    Qa,
    Qb,
    Qc,
    Qd,
    Qe,
    Qf,
    Qg,
    RBI,
    RBO,
    V0,
    V1,
    V2,
    X6,
    X7,
    X9);
 input A;
 input AL;
 input B;
 input BI;
 input C;
 input D;
 input LT;
 output Qa;
 output Qb;
 output Qc;
 output Qd;
 output Qe;
 output Qf;
 output Qg;
 input RBI;
 output RBO;
 input V0;
 input V1;
 input V2;
 input X6;
 input X7;
 input X9;

 wire net1;
 wire net2;
 wire net3;
 wire net4;
 wire net5;
 wire net6;
 wire net7;
 wire net15;
 wire net16;
 wire net17;
 wire net18;
 wire net19;
 wire net20;
 wire net21;
 wire net8;
 wire net22;
 wire net9;
 wire net10;
 wire net11;
 wire net12;
 wire net13;
 wire net14;
 wire _000_;
 wire _001_;
 wire _002_;
 wire _003_;
 wire _004_;
 wire _005_;
 wire _008_;
 wire _010_;
 wire _012_;
 wire _013_;
 wire _014_;
 wire _015_;
 wire _016_;
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
 wire _110_;
 wire _114_;
 wire _117_;
 wire _118_;
 wire _119_;
 wire _121_;
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
 wire _152_;
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
 wire _169_;
 wire _170_;
 wire _171_;
 wire _172_;
 wire _173_;
 wire _174_;
 wire _175_;
 wire _176_;
 wire _177_;
 wire _178_;
 wire _179_;
 wire _180_;
 wire _181_;
 wire _182_;
 wire _183_;
 wire net23;
 wire net24;
 wire net25;
 wire net26;

 sky130_fd_sc_hd__nand2_1 _187_ (.A(net24),
    .B(net23),
    .Y(_110_));
 sky130_fd_sc_hd__inv_1 _191_ (.A(net10),
    .Y(_114_));
 sky130_fd_sc_hd__nor3_1 _194_ (.A(net26),
    .B(net25),
    .C(net11),
    .Y(_117_));
 sky130_fd_sc_hd__a21oi_1 _195_ (.A1(net25),
    .A2(_114_),
    .B1(_117_),
    .Y(_118_));
 sky130_fd_sc_hd__inv_1 _196_ (.A(net25),
    .Y(_119_));
 sky130_fd_sc_hd__maj3_1 _198_ (.A(_119_),
    .B(net10),
    .C(net9),
    .X(_121_));
 sky130_fd_sc_hd__nand3_1 _203_ (.A(net26),
    .B(net24),
    .C(net23),
    .Y(_126_));
 sky130_fd_sc_hd__o32ai_1 _204_ (.A1(net9),
    .A2(_110_),
    .A3(_118_),
    .B1(_121_),
    .B2(_126_),
    .Y(_127_));
 sky130_fd_sc_hd__and2b_4 _205_ (.A_N(net11),
    .B(net10),
    .X(_128_));
 sky130_fd_sc_hd__nand2_2 _206_ (.A(net25),
    .B(_128_),
    .Y(_129_));
 sky130_fd_sc_hd__nand2b_1 _207_ (.A_N(net26),
    .B(net9),
    .Y(_130_));
 sky130_fd_sc_hd__nand2b_1 _208_ (.A_N(net9),
    .B(net26),
    .Y(_131_));
 sky130_fd_sc_hd__nand4_1 _209_ (.A(net24),
    .B(net23),
    .C(_130_),
    .D(_131_),
    .Y(_132_));
 sky130_fd_sc_hd__nor3b_2 _210_ (.A(net10),
    .B(net9),
    .C_N(net11),
    .Y(_133_));
 sky130_fd_sc_hd__nor2b_1 _211_ (.A(net26),
    .B_N(net23),
    .Y(_134_));
 sky130_fd_sc_hd__nor2b_1 _212_ (.A(net24),
    .B_N(net25),
    .Y(_135_));
 sky130_fd_sc_hd__nor2b_1 _213_ (.A(net23),
    .B_N(net24),
    .Y(_136_));
 sky130_fd_sc_hd__nor2b_1 _214_ (.A(net25),
    .B_N(net26),
    .Y(_137_));
 sky130_fd_sc_hd__a32oi_1 _215_ (.A1(_133_),
    .A2(_134_),
    .A3(_135_),
    .B1(_136_),
    .B2(_137_),
    .Y(_138_));
 sky130_fd_sc_hd__o21ai_1 _216_ (.A1(_129_),
    .A2(_132_),
    .B1(_138_),
    .Y(_139_));
 sky130_fd_sc_hd__nand2_1 _217_ (.A(net25),
    .B(net23),
    .Y(_140_));
 sky130_fd_sc_hd__nor4_1 _218_ (.A(net10),
    .B(net9),
    .C(net11),
    .D(_140_),
    .Y(_141_));
 sky130_fd_sc_hd__inv_1 _219_ (.A(net8),
    .Y(_142_));
 sky130_fd_sc_hd__a211o_1 _220_ (.A1(net25),
    .A2(_136_),
    .B1(_141_),
    .C1(_142_),
    .X(_143_));
 sky130_fd_sc_hd__nor3_1 _221_ (.A(_127_),
    .B(_139_),
    .C(_143_),
    .Y(_144_));
 sky130_fd_sc_hd__nand3b_1 _222_ (.A_N(net9),
    .B(net11),
    .C(net10),
    .Y(_145_));
 sky130_fd_sc_hd__nand2b_1 _223_ (.A_N(net10),
    .B(net9),
    .Y(_146_));
 sky130_fd_sc_hd__a21oi_1 _224_ (.A1(_145_),
    .A2(_146_),
    .B1(net26),
    .Y(_147_));
 sky130_fd_sc_hd__inv_1 _225_ (.A(net23),
    .Y(_148_));
 sky130_fd_sc_hd__nor2_1 _226_ (.A(net24),
    .B(_148_),
    .Y(_149_));
 sky130_fd_sc_hd__o21ai_0 _227_ (.A1(_119_),
    .A2(_147_),
    .B1(_149_),
    .Y(_150_));
 sky130_fd_sc_hd__nand2_1 _228_ (.A(net26),
    .B(net25),
    .Y(_151_));
 sky130_fd_sc_hd__nor2b_1 _229_ (.A(net11),
    .B_N(net9),
    .Y(_152_));
 sky130_fd_sc_hd__nor2_1 _230_ (.A(net26),
    .B(net25),
    .Y(_153_));
 sky130_fd_sc_hd__and3b_1 _231_ (.A_N(_110_),
    .B(_133_),
    .C(_153_),
    .X(_154_));
 sky130_fd_sc_hd__a41oi_1 _232_ (.A1(net23),
    .A2(_114_),
    .A3(_151_),
    .A4(_152_),
    .B1(_154_),
    .Y(_155_));
 sky130_fd_sc_hd__inv_1 _233_ (.A(net11),
    .Y(_156_));
 sky130_fd_sc_hd__nand2_1 _234_ (.A(net26),
    .B(net9),
    .Y(_157_));
 sky130_fd_sc_hd__nand2b_1 _235_ (.A_N(net9),
    .B(net10),
    .Y(_158_));
 sky130_fd_sc_hd__o22ai_1 _236_ (.A1(net10),
    .A2(_157_),
    .B1(_158_),
    .B2(net26),
    .Y(_159_));
 sky130_fd_sc_hd__nand3_1 _237_ (.A(_156_),
    .B(_149_),
    .C(_159_),
    .Y(_160_));
 sky130_fd_sc_hd__and2b_1 _238_ (.A_N(net10),
    .B(net11),
    .X(_161_));
 sky130_fd_sc_hd__and2b_1 _239_ (.A_N(net25),
    .B(net24),
    .X(_162_));
 sky130_fd_sc_hd__a22oi_1 _240_ (.A1(_161_),
    .A2(_135_),
    .B1(_128_),
    .B2(_162_),
    .Y(_163_));
 sky130_fd_sc_hd__or3_1 _241_ (.A(_148_),
    .B(_131_),
    .C(_163_),
    .X(_164_));
 sky130_fd_sc_hd__and4_1 _242_ (.A(_150_),
    .B(_155_),
    .C(_160_),
    .D(_164_),
    .X(_165_));
 sky130_fd_sc_hd__nand4b_1 _243_ (.A_N(net24),
    .B(net23),
    .C(net26),
    .D(net25),
    .Y(_166_));
 sky130_fd_sc_hd__nand3_1 _244_ (.A(net10),
    .B(net9),
    .C(net11),
    .Y(_167_));
 sky130_fd_sc_hd__nand4b_1 _245_ (.A_N(net25),
    .B(net24),
    .C(net23),
    .D(net26),
    .Y(_168_));
 sky130_fd_sc_hd__o22ai_1 _246_ (.A1(_145_),
    .A2(_166_),
    .B1(_167_),
    .B2(_168_),
    .Y(_169_));
 sky130_fd_sc_hd__a41o_1 _247_ (.A1(net24),
    .A2(net9),
    .A3(net11),
    .A4(_134_),
    .B1(_169_),
    .X(_170_));
 sky130_fd_sc_hd__nand2_1 _248_ (.A(net10),
    .B(net11),
    .Y(_171_));
 sky130_fd_sc_hd__nor2b_1 _249_ (.A(net26),
    .B_N(net24),
    .Y(_172_));
 sky130_fd_sc_hd__xnor2_1 _250_ (.A(net9),
    .B(_172_),
    .Y(_173_));
 sky130_fd_sc_hd__nor3_1 _251_ (.A(_140_),
    .B(_171_),
    .C(_173_),
    .Y(_174_));
 sky130_fd_sc_hd__o2111ai_1 _252_ (.A1(_135_),
    .A2(_162_),
    .B1(net26),
    .C1(_114_),
    .D1(net9),
    .Y(_175_));
 sky130_fd_sc_hd__nand2b_1 _253_ (.A_N(_158_),
    .B(_162_),
    .Y(_176_));
 sky130_fd_sc_hd__a211oi_2 _254_ (.A1(_175_),
    .A2(_176_),
    .B1(_148_),
    .C1(_156_),
    .Y(_177_));
 sky130_fd_sc_hd__nor3_2 _255_ (.A(_170_),
    .B(_174_),
    .C(_177_),
    .Y(_178_));
 sky130_fd_sc_hd__inv_1 _256_ (.A(net26),
    .Y(_179_));
 sky130_fd_sc_hd__nand3b_1 _257_ (.A_N(net11),
    .B(net9),
    .C(net10),
    .Y(_180_));
 sky130_fd_sc_hd__nor2_1 _258_ (.A(_140_),
    .B(_180_),
    .Y(_181_));
 sky130_fd_sc_hd__nand2_1 _259_ (.A(_179_),
    .B(_181_),
    .Y(_182_));
 sky130_fd_sc_hd__nand2_1 _260_ (.A(_136_),
    .B(_153_),
    .Y(_183_));
 sky130_fd_sc_hd__nand4_1 _261_ (.A(net23),
    .B(net10),
    .C(_152_),
    .D(_162_),
    .Y(_000_));
 sky130_fd_sc_hd__o21ai_0 _262_ (.A1(_148_),
    .A2(net9),
    .B1(net25),
    .Y(_001_));
 sky130_fd_sc_hd__a221o_1 _263_ (.A1(net23),
    .A2(_129_),
    .B1(_001_),
    .B2(_179_),
    .C1(net24),
    .X(_002_));
 sky130_fd_sc_hd__and4_4 _264_ (.A(_182_),
    .B(_183_),
    .C(_000_),
    .D(_002_),
    .X(_003_));
 sky130_fd_sc_hd__nand4_2 _265_ (.A(_144_),
    .B(_165_),
    .C(_178_),
    .D(_003_),
    .Y(_004_));
 sky130_fd_sc_hd__nand2b_1 _266_ (.A_N(net24),
    .B(net9),
    .Y(_005_));
 sky130_fd_sc_hd__nand4b_1 _269_ (.A_N(net9),
    .B(net11),
    .C(net24),
    .D(net23),
    .Y(_008_));
 sky130_fd_sc_hd__a211oi_1 _271_ (.A1(_005_),
    .A2(_008_),
    .B1(net26),
    .C1(_114_),
    .Y(_010_));
 sky130_fd_sc_hd__xor2_1 _273_ (.A(net24),
    .B(net9),
    .X(_012_));
 sky130_fd_sc_hd__or3_1 _274_ (.A(_114_),
    .B(net11),
    .C(_012_),
    .X(_013_));
 sky130_fd_sc_hd__nand2b_1 _275_ (.A_N(net12),
    .B(net24),
    .Y(_014_));
 sky130_fd_sc_hd__a21oi_1 _276_ (.A1(_148_),
    .A2(_014_),
    .B1(net26),
    .Y(_015_));
 sky130_fd_sc_hd__a21oi_1 _277_ (.A1(net23),
    .A2(_013_),
    .B1(_015_),
    .Y(_016_));
 sky130_fd_sc_hd__o21ai_0 _279_ (.A1(_010_),
    .A2(_016_),
    .B1(net25),
    .Y(_018_));
 sky130_fd_sc_hd__nand2b_1 _280_ (.A_N(net9),
    .B(net11),
    .Y(_019_));
 sky130_fd_sc_hd__o31ai_1 _281_ (.A1(net26),
    .A2(net10),
    .A3(_019_),
    .B1(_180_),
    .Y(_020_));
 sky130_fd_sc_hd__o21ai_0 _282_ (.A1(_156_),
    .A2(_146_),
    .B1(net23),
    .Y(_021_));
 sky130_fd_sc_hd__a22o_1 _283_ (.A1(net23),
    .A2(_020_),
    .B1(_021_),
    .B2(net26),
    .X(_022_));
 sky130_fd_sc_hd__mux2i_1 _284_ (.A0(_161_),
    .A1(_128_),
    .S(_119_),
    .Y(_023_));
 sky130_fd_sc_hd__o2bb2ai_1 _285_ (.A1_N(_137_),
    .A2_N(_161_),
    .B1(_023_),
    .B2(net26),
    .Y(_024_));
 sky130_fd_sc_hd__nor2_1 _286_ (.A(net9),
    .B(_110_),
    .Y(_025_));
 sky130_fd_sc_hd__a22oi_1 _287_ (.A1(_162_),
    .A2(_022_),
    .B1(_024_),
    .B2(_025_),
    .Y(_026_));
 sky130_fd_sc_hd__a41o_1 _288_ (.A1(net24),
    .A2(net9),
    .A3(net11),
    .A4(_134_),
    .B1(_149_),
    .X(_027_));
 sky130_fd_sc_hd__o31ai_1 _289_ (.A1(net11),
    .A2(_146_),
    .A3(_168_),
    .B1(net7),
    .Y(_028_));
 sky130_fd_sc_hd__nand2_1 _290_ (.A(net24),
    .B(net9),
    .Y(_029_));
 sky130_fd_sc_hd__a21oi_1 _291_ (.A1(net26),
    .A2(_114_),
    .B1(_029_),
    .Y(_030_));
 sky130_fd_sc_hd__nand2b_1 _292_ (.A_N(net24),
    .B(net10),
    .Y(_031_));
 sky130_fd_sc_hd__nor2_1 _293_ (.A(_131_),
    .B(_031_),
    .Y(_032_));
 sky130_fd_sc_hd__o2111a_1 _294_ (.A1(_030_),
    .A2(_032_),
    .B1(net25),
    .C1(net23),
    .D1(net11),
    .X(_033_));
 sky130_fd_sc_hd__a211oi_1 _295_ (.A1(_119_),
    .A2(_027_),
    .B1(_028_),
    .C1(_033_),
    .Y(_034_));
 sky130_fd_sc_hd__inv_1 _296_ (.A(net4),
    .Y(_035_));
 sky130_fd_sc_hd__a41o_1 _297_ (.A1(_004_),
    .A2(_018_),
    .A3(_026_),
    .A4(_034_),
    .B1(_035_),
    .X(_036_));
 sky130_fd_sc_hd__xor2_1 _298_ (.A(net2),
    .B(_036_),
    .X(net15));
 sky130_fd_sc_hd__nand2_1 _299_ (.A(net26),
    .B(_136_),
    .Y(_037_));
 sky130_fd_sc_hd__nand4_1 _300_ (.A(net10),
    .B(net11),
    .C(_134_),
    .D(_012_),
    .Y(_038_));
 sky130_fd_sc_hd__nand2_1 _301_ (.A(_037_),
    .B(_038_),
    .Y(_039_));
 sky130_fd_sc_hd__nor3_1 _302_ (.A(net25),
    .B(_132_),
    .C(_171_),
    .Y(_040_));
 sky130_fd_sc_hd__nand2_1 _303_ (.A(_119_),
    .B(net23),
    .Y(_041_));
 sky130_fd_sc_hd__o31a_1 _305_ (.A1(net26),
    .A2(net11),
    .A3(_146_),
    .B1(net24),
    .X(_043_));
 sky130_fd_sc_hd__o21ai_0 _306_ (.A1(_041_),
    .A2(_043_),
    .B1(net7),
    .Y(_044_));
 sky130_fd_sc_hd__a211oi_1 _307_ (.A1(net25),
    .A2(_039_),
    .B1(_040_),
    .C1(_044_),
    .Y(_045_));
 sky130_fd_sc_hd__a31oi_1 _308_ (.A1(_003_),
    .A2(_004_),
    .A3(_045_),
    .B1(_035_),
    .Y(_046_));
 sky130_fd_sc_hd__xnor2_1 _309_ (.A(net2),
    .B(_046_),
    .Y(net16));
 sky130_fd_sc_hd__o21ai_0 _310_ (.A1(_130_),
    .A2(_171_),
    .B1(net25),
    .Y(_047_));
 sky130_fd_sc_hd__o21ai_0 _311_ (.A1(_148_),
    .A2(_180_),
    .B1(net25),
    .Y(_048_));
 sky130_fd_sc_hd__a22oi_1 _312_ (.A1(net23),
    .A2(_047_),
    .B1(_048_),
    .B2(net26),
    .Y(_049_));
 sky130_fd_sc_hd__o21ai_0 _313_ (.A1(_119_),
    .A2(_180_),
    .B1(net23),
    .Y(_050_));
 sky130_fd_sc_hd__nand2_1 _314_ (.A(net24),
    .B(_050_),
    .Y(_051_));
 sky130_fd_sc_hd__o21ai_0 _315_ (.A1(net26),
    .A2(_019_),
    .B1(_157_),
    .Y(_052_));
 sky130_fd_sc_hd__o31ai_1 _316_ (.A1(net24),
    .A2(net23),
    .A3(_151_),
    .B1(net7),
    .Y(_053_));
 sky130_fd_sc_hd__a41oi_1 _317_ (.A1(net23),
    .A2(net10),
    .A3(_162_),
    .A4(_052_),
    .B1(_053_),
    .Y(_054_));
 sky130_fd_sc_hd__o2111a_1 _318_ (.A1(net24),
    .A2(_049_),
    .B1(_051_),
    .C1(_182_),
    .D1(_054_),
    .X(_055_));
 sky130_fd_sc_hd__nor3_1 _319_ (.A(net26),
    .B(net11),
    .C(_158_),
    .Y(_056_));
 sky130_fd_sc_hd__nor3_1 _320_ (.A(_161_),
    .B(_128_),
    .C(_157_),
    .Y(_057_));
 sky130_fd_sc_hd__o211ai_1 _321_ (.A1(_056_),
    .A2(_057_),
    .B1(net25),
    .C1(_149_),
    .Y(_058_));
 sky130_fd_sc_hd__a31oi_1 _322_ (.A1(_004_),
    .A2(_055_),
    .A3(_058_),
    .B1(_035_),
    .Y(_059_));
 sky130_fd_sc_hd__xnor2_1 _323_ (.A(net2),
    .B(_059_),
    .Y(net17));
 sky130_fd_sc_hd__nand2_1 _324_ (.A(net24),
    .B(net10),
    .Y(_060_));
 sky130_fd_sc_hd__nand2_1 _325_ (.A(_152_),
    .B(_060_),
    .Y(_061_));
 sky130_fd_sc_hd__o21ai_0 _326_ (.A1(net24),
    .A2(net23),
    .B1(net26),
    .Y(_062_));
 sky130_fd_sc_hd__nand2_1 _327_ (.A(net25),
    .B(_062_),
    .Y(_063_));
 sky130_fd_sc_hd__a21oi_1 _328_ (.A1(net23),
    .A2(_061_),
    .B1(_063_),
    .Y(_064_));
 sky130_fd_sc_hd__o31ai_1 _329_ (.A1(_119_),
    .A2(net24),
    .A3(_146_),
    .B1(_176_),
    .Y(_065_));
 sky130_fd_sc_hd__a41o_1 _330_ (.A1(net26),
    .A2(net23),
    .A3(net11),
    .A4(_065_),
    .B1(_028_),
    .X(_066_));
 sky130_fd_sc_hd__nor2_1 _331_ (.A(net26),
    .B(net24),
    .Y(_067_));
 sky130_fd_sc_hd__a31oi_1 _332_ (.A1(net24),
    .A2(net9),
    .A3(_128_),
    .B1(_067_),
    .Y(_068_));
 sky130_fd_sc_hd__nor2_1 _333_ (.A(_041_),
    .B(_068_),
    .Y(_069_));
 sky130_fd_sc_hd__nor4_1 _334_ (.A(_139_),
    .B(_064_),
    .C(_066_),
    .D(_069_),
    .Y(_070_));
 sky130_fd_sc_hd__nand2b_1 _335_ (.A_N(net24),
    .B(net26),
    .Y(_071_));
 sky130_fd_sc_hd__mux2i_1 _336_ (.A0(net14),
    .A1(_133_),
    .S(net25),
    .Y(_072_));
 sky130_fd_sc_hd__nand3_1 _337_ (.A(net24),
    .B(_133_),
    .C(_153_),
    .Y(_073_));
 sky130_fd_sc_hd__o21ai_0 _338_ (.A1(_071_),
    .A2(_072_),
    .B1(_073_),
    .Y(_074_));
 sky130_fd_sc_hd__a21oi_1 _339_ (.A1(net23),
    .A2(_074_),
    .B1(_170_),
    .Y(_075_));
 sky130_fd_sc_hd__a41oi_1 _340_ (.A1(_004_),
    .A2(_058_),
    .A3(_070_),
    .A4(_075_),
    .B1(_035_),
    .Y(_076_));
 sky130_fd_sc_hd__xnor2_1 _341_ (.A(net2),
    .B(_076_),
    .Y(net18));
 sky130_fd_sc_hd__and3_1 _342_ (.A(_144_),
    .B(_165_),
    .C(_003_),
    .X(_077_));
 sky130_fd_sc_hd__nand2_1 _343_ (.A(net24),
    .B(_180_),
    .Y(_078_));
 sky130_fd_sc_hd__a21oi_1 _344_ (.A1(net23),
    .A2(_078_),
    .B1(net25),
    .Y(_079_));
 sky130_fd_sc_hd__a21oi_1 _345_ (.A1(_146_),
    .A2(_031_),
    .B1(net11),
    .Y(_080_));
 sky130_fd_sc_hd__nor2_1 _346_ (.A(_140_),
    .B(_080_),
    .Y(_081_));
 sky130_fd_sc_hd__o311ai_0 _347_ (.A1(net26),
    .A2(_079_),
    .A3(_081_),
    .B1(net7),
    .C1(_178_),
    .Y(_082_));
 sky130_fd_sc_hd__o21ai_1 _348_ (.A1(_077_),
    .A2(_082_),
    .B1(net4),
    .Y(_083_));
 sky130_fd_sc_hd__xor2_1 _349_ (.A(net2),
    .B(_083_),
    .X(net19));
 sky130_fd_sc_hd__nand2_1 _350_ (.A(net9),
    .B(net11),
    .Y(_084_));
 sky130_fd_sc_hd__o21a_1 _351_ (.A1(net11),
    .A2(_131_),
    .B1(_084_),
    .X(_085_));
 sky130_fd_sc_hd__nor3_1 _352_ (.A(_148_),
    .B(_031_),
    .C(_085_),
    .Y(_086_));
 sky130_fd_sc_hd__a21boi_0 _353_ (.A1(net23),
    .A2(_145_),
    .B1_N(_172_),
    .Y(_087_));
 sky130_fd_sc_hd__o21ai_0 _354_ (.A1(_086_),
    .A2(_087_),
    .B1(net25),
    .Y(_088_));
 sky130_fd_sc_hd__nand2_1 _355_ (.A(net26),
    .B(net13),
    .Y(_089_));
 sky130_fd_sc_hd__a21oi_1 _356_ (.A1(net25),
    .A2(_089_),
    .B1(net23),
    .Y(_090_));
 sky130_fd_sc_hd__o21ai_0 _357_ (.A1(_181_),
    .A2(_090_),
    .B1(net24),
    .Y(_091_));
 sky130_fd_sc_hd__mux2_2 _358_ (.A0(net24),
    .A1(net25),
    .S(net10),
    .X(_092_));
 sky130_fd_sc_hd__a31oi_1 _359_ (.A1(_134_),
    .A2(_152_),
    .A3(_092_),
    .B1(_177_),
    .Y(_093_));
 sky130_fd_sc_hd__and3_1 _360_ (.A(_088_),
    .B(_091_),
    .C(_093_),
    .X(_094_));
 sky130_fd_sc_hd__a31oi_1 _361_ (.A1(_004_),
    .A2(_034_),
    .A3(_094_),
    .B1(_035_),
    .Y(_095_));
 sky130_fd_sc_hd__xnor2_1 _362_ (.A(net2),
    .B(_095_),
    .Y(net20));
 sky130_fd_sc_hd__inv_1 _363_ (.A(_165_),
    .Y(_096_));
 sky130_fd_sc_hd__nor2_1 _364_ (.A(net25),
    .B(net23),
    .Y(_097_));
 sky130_fd_sc_hd__o21ai_0 _365_ (.A1(_181_),
    .A2(_097_),
    .B1(net24),
    .Y(_098_));
 sky130_fd_sc_hd__nor3_1 _366_ (.A(_179_),
    .B(net25),
    .C(_110_),
    .Y(_099_));
 sky130_fd_sc_hd__a21oi_1 _367_ (.A1(_133_),
    .A2(_099_),
    .B1(_033_),
    .Y(_100_));
 sky130_fd_sc_hd__nand3_1 _368_ (.A(_054_),
    .B(_098_),
    .C(_100_),
    .Y(_101_));
 sky130_fd_sc_hd__nor2_1 _369_ (.A(net24),
    .B(net23),
    .Y(_102_));
 sky130_fd_sc_hd__nor4_1 _370_ (.A(net25),
    .B(_114_),
    .C(net11),
    .D(_029_),
    .Y(_103_));
 sky130_fd_sc_hd__a21oi_1 _371_ (.A1(net25),
    .A2(_102_),
    .B1(_103_),
    .Y(_104_));
 sky130_fd_sc_hd__o21ai_0 _372_ (.A1(net26),
    .A2(_104_),
    .B1(_088_),
    .Y(_105_));
 sky130_fd_sc_hd__o31ai_2 _373_ (.A1(_096_),
    .A2(_101_),
    .A3(_105_),
    .B1(net4),
    .Y(_106_));
 sky130_fd_sc_hd__xor2_1 _374_ (.A(net2),
    .B(_106_),
    .X(net21));
 sky130_fd_sc_hd__a41oi_1 _375_ (.A1(net7),
    .A2(_142_),
    .A3(_153_),
    .A4(_102_),
    .B1(_035_),
    .Y(net22));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input1 (.A(A),
    .X(net1));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input10 (.A(V1),
    .X(net10));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input11 (.A(V2),
    .X(net11));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input12 (.A(X6),
    .X(net12));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input13 (.A(X7),
    .X(net13));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input14 (.A(X9),
    .X(net14));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input2 (.A(AL),
    .X(net2));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input3 (.A(B),
    .X(net3));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input4 (.A(BI),
    .X(net4));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input5 (.A(C),
    .X(net5));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input6 (.A(D),
    .X(net6));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input7 (.A(LT),
    .X(net7));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input8 (.A(RBI),
    .X(net8));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input9 (.A(V0),
    .X(net9));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output15 (.A(net15),
    .X(Qa));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output16 (.A(net16),
    .X(Qb));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output17 (.A(net17),
    .X(Qc));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output18 (.A(net18),
    .X(Qd));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output19 (.A(net19),
    .X(Qe));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output20 (.A(net20),
    .X(Qf));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output21 (.A(net21),
    .X(Qg));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output22 (.A(net22),
    .X(RBO));
 sky130_fd_sc_hd__buf_4 place23 (.A(net6),
    .X(net23));
 sky130_fd_sc_hd__buf_4 place24 (.A(net5),
    .X(net24));
 sky130_fd_sc_hd__buf_4 place25 (.A(net3),
    .X(net25));
 sky130_fd_sc_hd__buf_4 place26 (.A(net1),
    .X(net26));
endmodule
