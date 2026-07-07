module alu4 (carry_out,
    clk,
    overflow,
    rst_n,
    a,
    b,
    opcode,
    result);
 output carry_out;
 input clk;
 output overflow;
 input rst_n;
 input [3:0] a;
 input [3:0] b;
 input [3:0] opcode;
 output [7:0] result;

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
 wire _089_;
 wire _090_;
 wire _091_;
 wire _092_;
 wire _093_;
 wire _094_;
 wire _096_;
 wire _097_;
 wire _098_;
 wire _099_;
 wire _100_;
 wire _103_;
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
 wire _184_;
 wire _185_;
 wire _186_;
 wire _187_;
 wire _188_;
 wire _189_;
 wire _190_;
 wire _191_;
 wire _192_;
 wire _193_;
 wire _194_;
 wire _195_;
 wire _196_;
 wire _197_;
 wire _198_;
 wire _199_;
 wire _200_;
 wire _201_;
 wire _202_;
 wire _203_;
 wire _204_;
 wire _205_;
 wire _206_;
 wire _207_;
 wire _208_;
 wire _209_;
 wire _210_;
 wire _211_;
 wire _212_;
 wire _213_;
 wire _214_;
 wire _215_;
 wire _216_;
 wire _217_;
 wire _218_;
 wire _219_;
 wire _220_;
 wire _221_;
 wire _222_;
 wire _223_;
 wire _224_;
 wire _225_;
 wire _226_;
 wire _227_;
 wire _228_;
 wire _229_;
 wire _230_;
 wire _231_;
 wire _232_;
 wire _233_;
 wire _234_;
 wire _235_;
 wire _236_;
 wire _237_;
 wire _238_;
 wire _239_;
 wire _240_;
 wire _241_;
 wire _242_;
 wire _243_;
 wire _244_;
 wire _245_;
 wire _246_;
 wire _247_;
 wire _248_;
 wire _249_;
 wire _250_;
 wire _251_;
 wire _252_;
 wire _253_;
 wire _254_;
 wire _255_;
 wire _256_;
 wire _257_;
 wire _258_;
 wire _259_;
 wire _260_;
 wire _261_;
 wire _262_;
 wire _263_;
 wire _264_;
 wire _265_;
 wire _266_;
 wire _267_;
 wire _268_;
 wire _269_;
 wire _270_;
 wire _271_;
 wire net1;
 wire net2;
 wire net3;
 wire net4;
 wire net5;
 wire net6;
 wire net7;
 wire net8;
 wire net14;
 wire net9;
 wire net10;
 wire net11;
 wire net12;
 wire net15;
 wire net16;
 wire net17;
 wire net18;
 wire net19;
 wire net20;
 wire net21;
 wire net22;
 wire net23;
 wire net13;
 wire clknet_0_clk;
 wire clknet_1_0__leaf_clk;
 wire clknet_1_1__leaf_clk;

 sky130_fd_sc_hd__inv_1 _272_ (.A(net4),
    .Y(_077_));
 sky130_fd_sc_hd__inv_1 _273_ (.A(net2),
    .Y(_000_));
 sky130_fd_sc_hd__inv_1 _274_ (.A(net3),
    .Y(_070_));
 sky130_fd_sc_hd__inv_1 _276_ (.A(net8),
    .Y(_046_));
 sky130_fd_sc_hd__o21ai_0 _277_ (.A1(_037_),
    .A2(_038_),
    .B1(_045_),
    .Y(_096_));
 sky130_fd_sc_hd__nor2_1 _278_ (.A(_041_),
    .B(_044_),
    .Y(_097_));
 sky130_fd_sc_hd__o21bai_1 _279_ (.A1(_042_),
    .A2(_041_),
    .B1_N(net8),
    .Y(_098_));
 sky130_fd_sc_hd__a21oi_1 _280_ (.A1(_096_),
    .A2(_097_),
    .B1(_098_),
    .Y(_099_));
 sky130_fd_sc_hd__nand2_1 _281_ (.A(_037_),
    .B(_099_),
    .Y(_100_));
 sky130_fd_sc_hd__o21ai_0 _282_ (.A1(net2),
    .A2(_099_),
    .B1(_100_),
    .Y(_024_));
 sky130_fd_sc_hd__inv_1 _285_ (.A(net9),
    .Y(_103_));
 sky130_fd_sc_hd__nand2_1 _288_ (.A(net11),
    .B(_005_),
    .Y(_106_));
 sky130_fd_sc_hd__mux2_2 _289_ (.A0(_005_),
    .A1(_058_),
    .S(net11),
    .X(_107_));
 sky130_fd_sc_hd__nand2_1 _290_ (.A(net10),
    .B(_107_),
    .Y(_108_));
 sky130_fd_sc_hd__o21ai_0 _291_ (.A1(net10),
    .A2(_106_),
    .B1(_108_),
    .Y(_109_));
 sky130_fd_sc_hd__nor2_1 _292_ (.A(net10),
    .B(net11),
    .Y(_110_));
 sky130_fd_sc_hd__a22oi_1 _293_ (.A1(_103_),
    .A2(_109_),
    .B1(_110_),
    .B2(_058_),
    .Y(_111_));
 sky130_fd_sc_hd__nand2b_1 _294_ (.A_N(_058_),
    .B(_055_),
    .Y(_112_));
 sky130_fd_sc_hd__nand2_1 _295_ (.A(_049_),
    .B(_052_),
    .Y(_113_));
 sky130_fd_sc_hd__a21oi_1 _296_ (.A1(_025_),
    .A2(_112_),
    .B1(_113_),
    .Y(_114_));
 sky130_fd_sc_hd__a21o_1 _297_ (.A1(_049_),
    .A2(_051_),
    .B1(_048_),
    .X(_115_));
 sky130_fd_sc_hd__inv_1 _298_ (.A(net11),
    .Y(_116_));
 sky130_fd_sc_hd__and2b_4 _299_ (.A_N(net12),
    .B(net9),
    .X(_117_));
 sky130_fd_sc_hd__or4_4 _300_ (.A(net5),
    .B(net7),
    .C(net6),
    .D(net8),
    .X(_118_));
 sky130_fd_sc_hd__nand4_4 _301_ (.A(net10),
    .B(_116_),
    .C(_117_),
    .D(_118_),
    .Y(_119_));
 sky130_fd_sc_hd__o21bai_1 _302_ (.A1(_114_),
    .A2(_115_),
    .B1_N(_119_),
    .Y(_120_));
 sky130_fd_sc_hd__nor2_1 _303_ (.A(net9),
    .B(net11),
    .Y(_121_));
 sky130_fd_sc_hd__nand2_1 _304_ (.A(net12),
    .B(_121_),
    .Y(_122_));
 sky130_fd_sc_hd__nand2_1 _305_ (.A(net11),
    .B(_117_),
    .Y(_123_));
 sky130_fd_sc_hd__o22ai_1 _306_ (.A1(net5),
    .A2(_122_),
    .B1(_123_),
    .B2(_057_),
    .Y(_124_));
 sky130_fd_sc_hd__o21ai_0 _307_ (.A1(net1),
    .A2(_123_),
    .B1(net10),
    .Y(_125_));
 sky130_fd_sc_hd__o21ai_0 _308_ (.A1(net10),
    .A2(_124_),
    .B1(_125_),
    .Y(_126_));
 sky130_fd_sc_hd__o211ai_1 _309_ (.A1(net12),
    .A2(_111_),
    .B1(_120_),
    .C1(_126_),
    .Y(_236_));
 sky130_fd_sc_hd__inv_1 _310_ (.A(net1),
    .Y(_056_));
 sky130_fd_sc_hd__inv_1 _311_ (.A(net6),
    .Y(_004_));
 sky130_fd_sc_hd__nor2_1 _312_ (.A(_056_),
    .B(_004_),
    .Y(_059_));
 sky130_fd_sc_hd__a21o_1 _313_ (.A1(_096_),
    .A2(_097_),
    .B1(_098_),
    .X(_127_));
 sky130_fd_sc_hd__inv_1 _314_ (.A(net12),
    .Y(_128_));
 sky130_fd_sc_hd__mux2_2 _315_ (.A0(_000_),
    .A1(_062_),
    .S(_103_),
    .X(_129_));
 sky130_fd_sc_hd__nor2_1 _316_ (.A(net10),
    .B(net9),
    .Y(_130_));
 sky130_fd_sc_hd__a22o_1 _317_ (.A1(net10),
    .A2(_129_),
    .B1(_130_),
    .B2(_064_),
    .X(_131_));
 sky130_fd_sc_hd__nand2_1 _318_ (.A(net9),
    .B(net11),
    .Y(_132_));
 sky130_fd_sc_hd__a2bb2oi_1 _319_ (.A1_N(_061_),
    .A2_N(_132_),
    .B1(_121_),
    .B2(_007_),
    .Y(_133_));
 sky130_fd_sc_hd__nor3b_1 _320_ (.A(net12),
    .B(_003_),
    .C_N(net9),
    .Y(_134_));
 sky130_fd_sc_hd__nor3b_1 _321_ (.A(net9),
    .B(net6),
    .C_N(net12),
    .Y(_135_));
 sky130_fd_sc_hd__o21ai_0 _322_ (.A1(_134_),
    .A2(_135_),
    .B1(_110_),
    .Y(_136_));
 sky130_fd_sc_hd__nor2b_1 _323_ (.A(net12),
    .B_N(net10),
    .Y(_137_));
 sky130_fd_sc_hd__nand3_1 _324_ (.A(_060_),
    .B(_121_),
    .C(_137_),
    .Y(_138_));
 sky130_fd_sc_hd__o311ai_0 _325_ (.A1(net10),
    .A2(net12),
    .A3(_133_),
    .B1(_136_),
    .C1(_138_),
    .Y(_139_));
 sky130_fd_sc_hd__a31oi_1 _326_ (.A1(net11),
    .A2(_128_),
    .A3(_131_),
    .B1(_139_),
    .Y(_140_));
 sky130_fd_sc_hd__o21ai_0 _327_ (.A1(_127_),
    .A2(_119_),
    .B1(_140_),
    .Y(_237_));
 sky130_fd_sc_hd__inv_1 _328_ (.A(net7),
    .Y(_039_));
 sky130_fd_sc_hd__nor2_1 _329_ (.A(_056_),
    .B(_039_),
    .Y(_065_));
 sky130_fd_sc_hd__inv_1 _330_ (.A(_071_),
    .Y(_141_));
 sky130_fd_sc_hd__mux4_2 _331_ (.A0(_141_),
    .A1(_021_),
    .A2(_070_),
    .A3(_072_),
    .S0(_103_),
    .S1(net10),
    .X(_142_));
 sky130_fd_sc_hd__mux2i_1 _332_ (.A0(_006_),
    .A1(_002_),
    .S(net9),
    .Y(_143_));
 sky130_fd_sc_hd__xnor2_1 _333_ (.A(_072_),
    .B(_143_),
    .Y(_144_));
 sky130_fd_sc_hd__a22oi_1 _334_ (.A1(net11),
    .A2(_142_),
    .B1(_144_),
    .B2(_110_),
    .Y(_145_));
 sky130_fd_sc_hd__o21ai_0 _335_ (.A1(_035_),
    .A2(_034_),
    .B1(_033_),
    .Y(_146_));
 sky130_fd_sc_hd__inv_1 _336_ (.A(_146_),
    .Y(_147_));
 sky130_fd_sc_hd__nor2_1 _337_ (.A(net7),
    .B(net8),
    .Y(_148_));
 sky130_fd_sc_hd__o21ai_0 _338_ (.A1(_032_),
    .A2(_147_),
    .B1(_148_),
    .Y(_149_));
 sky130_fd_sc_hd__nor2b_1 _339_ (.A(net10),
    .B_N(net12),
    .Y(_150_));
 sky130_fd_sc_hd__a22o_2 _340_ (.A1(_069_),
    .A2(_137_),
    .B1(_150_),
    .B2(net7),
    .X(_151_));
 sky130_fd_sc_hd__nand2_1 _341_ (.A(_121_),
    .B(_151_),
    .Y(_152_));
 sky130_fd_sc_hd__o221ai_1 _342_ (.A1(net12),
    .A2(_145_),
    .B1(_149_),
    .B2(_119_),
    .C1(_152_),
    .Y(_238_));
 sky130_fd_sc_hd__nor2_1 _343_ (.A(_056_),
    .B(_046_),
    .Y(_008_));
 sky130_fd_sc_hd__nor2_1 _344_ (.A(_000_),
    .B(_039_),
    .Y(_009_));
 sky130_fd_sc_hd__nor2_1 _345_ (.A(_070_),
    .B(_004_),
    .Y(_010_));
 sky130_fd_sc_hd__inv_1 _346_ (.A(_020_),
    .Y(_153_));
 sky130_fd_sc_hd__a22o_1 _347_ (.A1(_153_),
    .A2(_137_),
    .B1(_150_),
    .B2(_046_),
    .X(_154_));
 sky130_fd_sc_hd__inv_1 _348_ (.A(_082_),
    .Y(_155_));
 sky130_fd_sc_hd__inv_1 _349_ (.A(_079_),
    .Y(_156_));
 sky130_fd_sc_hd__mux4_2 _350_ (.A0(_078_),
    .A1(_155_),
    .A2(net4),
    .A3(_156_),
    .S0(_103_),
    .S1(net10),
    .X(_157_));
 sky130_fd_sc_hd__nor3_1 _351_ (.A(net7),
    .B(net6),
    .C(net8),
    .Y(_158_));
 sky130_fd_sc_hd__o21ai_0 _352_ (.A1(_029_),
    .A2(_028_),
    .B1(_158_),
    .Y(_159_));
 sky130_fd_sc_hd__o32ai_1 _353_ (.A1(_116_),
    .A2(net12),
    .A3(_157_),
    .B1(_159_),
    .B2(_119_),
    .Y(_160_));
 sky130_fd_sc_hd__a21oi_1 _354_ (.A1(_121_),
    .A2(_154_),
    .B1(_160_),
    .Y(_161_));
 sky130_fd_sc_hd__nor2_1 _355_ (.A(net11),
    .B(net12),
    .Y(_162_));
 sky130_fd_sc_hd__a21o_1 _356_ (.A1(_005_),
    .A2(_062_),
    .B1(_064_),
    .X(_163_));
 sky130_fd_sc_hd__a21oi_1 _357_ (.A1(_072_),
    .A2(_163_),
    .B1(_021_),
    .Y(_164_));
 sky130_fd_sc_hd__xnor2_1 _358_ (.A(_079_),
    .B(_164_),
    .Y(_165_));
 sky130_fd_sc_hd__nand3_1 _359_ (.A(_162_),
    .B(_130_),
    .C(_165_),
    .Y(_166_));
 sky130_fd_sc_hd__inv_1 _360_ (.A(_072_),
    .Y(_167_));
 sky130_fd_sc_hd__o21bai_1 _361_ (.A1(_062_),
    .A2(_001_),
    .B1_N(_063_),
    .Y(_168_));
 sky130_fd_sc_hd__a21oi_1 _362_ (.A1(_167_),
    .A2(_168_),
    .B1(_073_),
    .Y(_169_));
 sky130_fd_sc_hd__xnor2_1 _363_ (.A(_156_),
    .B(_169_),
    .Y(_170_));
 sky130_fd_sc_hd__nand3_1 _364_ (.A(_117_),
    .B(_110_),
    .C(_170_),
    .Y(_171_));
 sky130_fd_sc_hd__nand3_1 _365_ (.A(_161_),
    .B(_166_),
    .C(_171_),
    .Y(_239_));
 sky130_fd_sc_hd__nor2_1 _366_ (.A(_000_),
    .B(_046_),
    .Y(_022_));
 sky130_fd_sc_hd__nor2_1 _367_ (.A(_004_),
    .B(_077_),
    .Y(_023_));
 sky130_fd_sc_hd__nor2_1 _368_ (.A(_114_),
    .B(_115_),
    .Y(_172_));
 sky130_fd_sc_hd__nor2_1 _369_ (.A(_119_),
    .B(_172_),
    .Y(_173_));
 sky130_fd_sc_hd__nand2_1 _370_ (.A(_121_),
    .B(_137_),
    .Y(_174_));
 sky130_fd_sc_hd__nor2b_1 _371_ (.A(_019_),
    .B_N(_085_),
    .Y(_175_));
 sky130_fd_sc_hd__nor2b_1 _372_ (.A(_085_),
    .B_N(_019_),
    .Y(_176_));
 sky130_fd_sc_hd__nor3_1 _373_ (.A(_174_),
    .B(_175_),
    .C(_176_),
    .Y(_177_));
 sky130_fd_sc_hd__or3_4 _374_ (.A(_119_),
    .B(_114_),
    .C(_115_),
    .X(_178_));
 sky130_fd_sc_hd__nand2_1 _375_ (.A(_121_),
    .B(_150_),
    .Y(_179_));
 sky130_fd_sc_hd__a21oi_2 _376_ (.A1(_178_),
    .A2(_179_),
    .B1(_056_),
    .Y(_180_));
 sky130_fd_sc_hd__a211o_1 _377_ (.A1(_058_),
    .A2(_173_),
    .B1(_177_),
    .C1(_180_),
    .X(_240_));
 sky130_fd_sc_hd__nor2_1 _378_ (.A(_070_),
    .B(_046_),
    .Y(_086_));
 sky130_fd_sc_hd__nor2_1 _379_ (.A(_039_),
    .B(_077_),
    .Y(_087_));
 sky130_fd_sc_hd__a21o_1 _380_ (.A1(_068_),
    .A2(_076_),
    .B1(_075_),
    .X(_181_));
 sky130_fd_sc_hd__a211oi_1 _381_ (.A1(_085_),
    .A2(_181_),
    .B1(_084_),
    .C1(_089_),
    .Y(_182_));
 sky130_fd_sc_hd__a211oi_1 _382_ (.A1(_068_),
    .A2(_076_),
    .B1(_075_),
    .C1(_084_),
    .Y(_183_));
 sky130_fd_sc_hd__o21ai_0 _383_ (.A1(_085_),
    .A2(_084_),
    .B1(_089_),
    .Y(_184_));
 sky130_fd_sc_hd__o21ai_0 _384_ (.A1(_183_),
    .A2(_184_),
    .B1(_137_),
    .Y(_185_));
 sky130_fd_sc_hd__o2bb2ai_1 _385_ (.A1_N(_000_),
    .A2_N(_150_),
    .B1(_182_),
    .B2(_185_),
    .Y(_186_));
 sky130_fd_sc_hd__nand2_1 _386_ (.A(_121_),
    .B(_186_),
    .Y(_187_));
 sky130_fd_sc_hd__o221ai_1 _387_ (.A1(_026_),
    .A2(_120_),
    .B1(_178_),
    .B2(_024_),
    .C1(_187_),
    .Y(_241_));
 sky130_fd_sc_hd__o21a_1 _388_ (.A1(_084_),
    .A2(_175_),
    .B1(_089_),
    .X(_188_));
 sky130_fd_sc_hd__o21ai_0 _389_ (.A1(_088_),
    .A2(_188_),
    .B1(_092_),
    .Y(_189_));
 sky130_fd_sc_hd__or3_1 _390_ (.A(_092_),
    .B(_088_),
    .C(_188_),
    .X(_190_));
 sky130_fd_sc_hd__a32oi_1 _391_ (.A1(_137_),
    .A2(_189_),
    .A3(_190_),
    .B1(_150_),
    .B2(net3),
    .Y(_191_));
 sky130_fd_sc_hd__xnor2_1 _392_ (.A(_025_),
    .B(_052_),
    .Y(_192_));
 sky130_fd_sc_hd__a21oi_1 _393_ (.A1(_033_),
    .A2(_034_),
    .B1(_032_),
    .Y(_193_));
 sky130_fd_sc_hd__or4_4 _394_ (.A(net7),
    .B(net8),
    .C(_035_),
    .D(_193_),
    .X(_194_));
 sky130_fd_sc_hd__o21ai_0 _395_ (.A1(_033_),
    .A2(_032_),
    .B1(_035_),
    .Y(_195_));
 sky130_fd_sc_hd__o31ai_1 _396_ (.A1(net7),
    .A2(net8),
    .A3(_195_),
    .B1(net3),
    .Y(_196_));
 sky130_fd_sc_hd__xnor2_1 _397_ (.A(_045_),
    .B(_036_),
    .Y(_197_));
 sky130_fd_sc_hd__a211oi_1 _398_ (.A1(_096_),
    .A2(_097_),
    .B1(_197_),
    .C1(_098_),
    .Y(_198_));
 sky130_fd_sc_hd__a31oi_2 _399_ (.A1(_127_),
    .A2(_194_),
    .A3(_196_),
    .B1(_198_),
    .Y(_050_));
 sky130_fd_sc_hd__mux2i_1 _400_ (.A0(_192_),
    .A1(_050_),
    .S(_172_),
    .Y(_199_));
 sky130_fd_sc_hd__o32ai_1 _401_ (.A1(net9),
    .A2(net11),
    .A3(_191_),
    .B1(_199_),
    .B2(_119_),
    .Y(_242_));
 sky130_fd_sc_hd__a21oi_1 _402_ (.A1(_028_),
    .A2(_158_),
    .B1(net4),
    .Y(_200_));
 sky130_fd_sc_hd__a21oi_1 _403_ (.A1(_029_),
    .A2(_158_),
    .B1(_200_),
    .Y(_031_));
 sky130_fd_sc_hd__nand2b_1 _404_ (.A_N(_044_),
    .B(_096_),
    .Y(_201_));
 sky130_fd_sc_hd__nor2b_1 _405_ (.A(net8),
    .B_N(_042_),
    .Y(_202_));
 sky130_fd_sc_hd__or3_1 _406_ (.A(_035_),
    .B(_033_),
    .C(_034_),
    .X(_203_));
 sky130_fd_sc_hd__nand4_1 _407_ (.A(_032_),
    .B(_148_),
    .C(_146_),
    .D(_203_),
    .Y(_204_));
 sky130_fd_sc_hd__nand2_1 _408_ (.A(_046_),
    .B(_041_),
    .Y(_205_));
 sky130_fd_sc_hd__nor2_1 _409_ (.A(net8),
    .B(_042_),
    .Y(_206_));
 sky130_fd_sc_hd__and4b_1 _410_ (.A_N(_044_),
    .B(_096_),
    .C(_206_),
    .D(_041_),
    .X(_207_));
 sky130_fd_sc_hd__a221oi_1 _411_ (.A1(_201_),
    .A2(_202_),
    .B1(_204_),
    .B2(_205_),
    .C1(_207_),
    .Y(_208_));
 sky130_fd_sc_hd__a31oi_1 _412_ (.A1(_127_),
    .A2(_149_),
    .A3(_031_),
    .B1(_208_),
    .Y(_209_));
 sky130_fd_sc_hd__nand2_1 _413_ (.A(_055_),
    .B(_052_),
    .Y(_210_));
 sky130_fd_sc_hd__a21oi_1 _414_ (.A1(_052_),
    .A2(_054_),
    .B1(_051_),
    .Y(_211_));
 sky130_fd_sc_hd__o21ai_0 _415_ (.A1(_001_),
    .A2(_210_),
    .B1(_211_),
    .Y(_212_));
 sky130_fd_sc_hd__xnor2_1 _416_ (.A(_049_),
    .B(_212_),
    .Y(_213_));
 sky130_fd_sc_hd__o22a_1 _417_ (.A1(net4),
    .A2(_179_),
    .B1(_213_),
    .B2(_120_),
    .X(_214_));
 sky130_fd_sc_hd__nor2_1 _418_ (.A(_090_),
    .B(_174_),
    .Y(_215_));
 sky130_fd_sc_hd__and3_1 _419_ (.A(_090_),
    .B(_121_),
    .C(_137_),
    .X(_216_));
 sky130_fd_sc_hd__o21bai_1 _420_ (.A1(_183_),
    .A2(_184_),
    .B1_N(_088_),
    .Y(_217_));
 sky130_fd_sc_hd__a21oi_1 _421_ (.A1(_092_),
    .A2(_217_),
    .B1(_091_),
    .Y(_218_));
 sky130_fd_sc_hd__mux2i_1 _422_ (.A0(_215_),
    .A1(_216_),
    .S(_218_),
    .Y(_219_));
 sky130_fd_sc_hd__o211ai_1 _423_ (.A1(_178_),
    .A2(_209_),
    .B1(_214_),
    .C1(_219_),
    .Y(_243_));
 sky130_fd_sc_hd__inv_1 _424_ (.A(_030_),
    .Y(_012_));
 sky130_fd_sc_hd__inv_1 _425_ (.A(_067_),
    .Y(_017_));
 sky130_fd_sc_hd__inv_1 _426_ (.A(_066_),
    .Y(_014_));
 sky130_fd_sc_hd__inv_1 _427_ (.A(_068_),
    .Y(_018_));
 sky130_fd_sc_hd__inv_1 _428_ (.A(_011_),
    .Y(_013_));
 sky130_fd_sc_hd__inv_1 _429_ (.A(_016_),
    .Y(_074_));
 sky130_fd_sc_hd__nand2_1 _430_ (.A(_149_),
    .B(_031_),
    .Y(_220_));
 sky130_fd_sc_hd__nand2_1 _431_ (.A(_220_),
    .B(_204_),
    .Y(_040_));
 sky130_fd_sc_hd__nand2_1 _432_ (.A(_194_),
    .B(_196_),
    .Y(_043_));
 sky130_fd_sc_hd__inv_1 _433_ (.A(_209_),
    .Y(_047_));
 sky130_fd_sc_hd__inv_1 _434_ (.A(_024_),
    .Y(_053_));
 sky130_fd_sc_hd__inv_1 _435_ (.A(net5),
    .Y(_027_));
 sky130_fd_sc_hd__inv_1 _436_ (.A(_015_),
    .Y(_083_));
 sky130_fd_sc_hd__nor2_1 _437_ (.A(_002_),
    .B(_072_),
    .Y(_221_));
 sky130_fd_sc_hd__nor2_1 _438_ (.A(_073_),
    .B(_221_),
    .Y(_222_));
 sky130_fd_sc_hd__nor2_1 _439_ (.A(_079_),
    .B(_222_),
    .Y(_223_));
 sky130_fd_sc_hd__o21ai_0 _440_ (.A1(_081_),
    .A2(_223_),
    .B1(_117_),
    .Y(_224_));
 sky130_fd_sc_hd__a21oi_1 _441_ (.A1(_072_),
    .A2(_006_),
    .B1(_021_),
    .Y(_225_));
 sky130_fd_sc_hd__o211ai_1 _442_ (.A1(_156_),
    .A2(_225_),
    .B1(_128_),
    .C1(_155_),
    .Y(_226_));
 sky130_fd_sc_hd__o211ai_1 _443_ (.A1(_128_),
    .A2(net14),
    .B1(_226_),
    .C1(_103_),
    .Y(_227_));
 sky130_fd_sc_hd__a21oi_1 _444_ (.A1(_128_),
    .A2(net14),
    .B1(_110_),
    .Y(_228_));
 sky130_fd_sc_hd__a31oi_1 _445_ (.A1(_110_),
    .A2(_224_),
    .A3(_227_),
    .B1(_228_),
    .Y(_093_));
 sky130_fd_sc_hd__nand2_1 _446_ (.A(_162_),
    .B(_130_),
    .Y(_229_));
 sky130_fd_sc_hd__mux2i_1 _447_ (.A0(_082_),
    .A1(_078_),
    .S(_165_),
    .Y(_230_));
 sky130_fd_sc_hd__nand3_1 _448_ (.A(_081_),
    .B(_117_),
    .C(_110_),
    .Y(_231_));
 sky130_fd_sc_hd__nand3_1 _449_ (.A(_080_),
    .B(_117_),
    .C(_110_),
    .Y(_232_));
 sky130_fd_sc_hd__mux2_2 _450_ (.A0(_231_),
    .A1(_232_),
    .S(_170_),
    .X(_233_));
 sky130_fd_sc_hd__o21ai_0 _451_ (.A1(net12),
    .A2(_110_),
    .B1(_179_),
    .Y(_234_));
 sky130_fd_sc_hd__nand2_1 _452_ (.A(net15),
    .B(_234_),
    .Y(_235_));
 sky130_fd_sc_hd__o211ai_1 _453_ (.A1(_229_),
    .A2(_230_),
    .B1(_233_),
    .C1(_235_),
    .Y(_094_));
 sky130_fd_sc_hd__fa_1 _454_ (.A(_000_),
    .B(net6),
    .CIN(_001_),
    .COUT(_002_),
    .SUM(_003_));
 sky130_fd_sc_hd__fa_1 _455_ (.A(net2),
    .B(net6),
    .CIN(_005_),
    .COUT(_006_),
    .SUM(_007_));
 sky130_fd_sc_hd__fa_1 _456_ (.A(_008_),
    .B(_009_),
    .CIN(_010_),
    .COUT(_244_),
    .SUM(_011_));
 sky130_fd_sc_hd__fa_1 _457_ (.A(_012_),
    .B(_013_),
    .CIN(_014_),
    .COUT(_015_),
    .SUM(_016_));
 sky130_fd_sc_hd__fa_1 _458_ (.A(_016_),
    .B(_017_),
    .CIN(_018_),
    .COUT(_019_),
    .SUM(_020_));
 sky130_fd_sc_hd__fa_1 _459_ (.A(_021_),
    .B(_022_),
    .CIN(_023_),
    .COUT(_245_),
    .SUM(_246_));
 sky130_fd_sc_hd__fa_1 _460_ (.A(net6),
    .B(_024_),
    .CIN(_001_),
    .COUT(_025_),
    .SUM(_026_));
 sky130_fd_sc_hd__ha_1 _461_ (.A(net4),
    .B(_027_),
    .COUT(_028_),
    .SUM(_029_));
 sky130_fd_sc_hd__ha_1 _462_ (.A(net4),
    .B(net5),
    .COUT(_030_),
    .SUM(_247_));
 sky130_fd_sc_hd__ha_1 _463_ (.A(_004_),
    .B(_031_),
    .COUT(_032_),
    .SUM(_033_));
 sky130_fd_sc_hd__ha_1 _464_ (.A(net3),
    .B(_027_),
    .COUT(_034_),
    .SUM(_035_));
 sky130_fd_sc_hd__ha_1 _465_ (.A(net3),
    .B(net5),
    .COUT(_248_),
    .SUM(_249_));
 sky130_fd_sc_hd__ha_1 _466_ (.A(_000_),
    .B(net5),
    .COUT(_036_),
    .SUM(_037_));
 sky130_fd_sc_hd__ha_1 _467_ (.A(net2),
    .B(_027_),
    .COUT(_038_),
    .SUM(_250_));
 sky130_fd_sc_hd__ha_1 _468_ (.A(net2),
    .B(net5),
    .COUT(_251_),
    .SUM(_252_));
 sky130_fd_sc_hd__ha_1 _469_ (.A(_039_),
    .B(_040_),
    .COUT(_041_),
    .SUM(_042_));
 sky130_fd_sc_hd__ha_1 _470_ (.A(_004_),
    .B(_043_),
    .COUT(_044_),
    .SUM(_045_));
 sky130_fd_sc_hd__ha_1 _471_ (.A(_046_),
    .B(_047_),
    .COUT(_048_),
    .SUM(_049_));
 sky130_fd_sc_hd__ha_1 _472_ (.A(_039_),
    .B(_050_),
    .COUT(_051_),
    .SUM(_052_));
 sky130_fd_sc_hd__ha_1 _473_ (.A(_004_),
    .B(_053_),
    .COUT(_054_),
    .SUM(_055_));
 sky130_fd_sc_hd__ha_1 _474_ (.A(_056_),
    .B(_027_),
    .COUT(_057_),
    .SUM(_058_));
 sky130_fd_sc_hd__ha_1 _475_ (.A(_056_),
    .B(net5),
    .COUT(_001_),
    .SUM(_253_));
 sky130_fd_sc_hd__ha_1 _476_ (.A(net1),
    .B(net5),
    .COUT(_005_),
    .SUM(_254_));
 sky130_fd_sc_hd__ha_1 _477_ (.A(_251_),
    .B(_059_),
    .COUT(_255_),
    .SUM(_060_));
 sky130_fd_sc_hd__ha_1 _478_ (.A(_000_),
    .B(_004_),
    .COUT(_061_),
    .SUM(_062_));
 sky130_fd_sc_hd__ha_1 _479_ (.A(net2),
    .B(_004_),
    .COUT(_063_),
    .SUM(_256_));
 sky130_fd_sc_hd__ha_1 _480_ (.A(net2),
    .B(net6),
    .COUT(_064_),
    .SUM(_257_));
 sky130_fd_sc_hd__ha_1 _481_ (.A(_064_),
    .B(_065_),
    .COUT(_066_),
    .SUM(_258_));
 sky130_fd_sc_hd__ha_1 _482_ (.A(_248_),
    .B(_258_),
    .COUT(_067_),
    .SUM(_259_));
 sky130_fd_sc_hd__ha_1 _483_ (.A(_259_),
    .B(_255_),
    .COUT(_068_),
    .SUM(_069_));
 sky130_fd_sc_hd__ha_1 _484_ (.A(_070_),
    .B(_039_),
    .COUT(_071_),
    .SUM(_072_));
 sky130_fd_sc_hd__ha_1 _485_ (.A(net3),
    .B(_039_),
    .COUT(_073_),
    .SUM(_260_));
 sky130_fd_sc_hd__ha_1 _486_ (.A(net3),
    .B(net7),
    .COUT(_021_),
    .SUM(_261_));
 sky130_fd_sc_hd__ha_1 _487_ (.A(_074_),
    .B(_067_),
    .COUT(_075_),
    .SUM(_076_));
 sky130_fd_sc_hd__ha_1 _488_ (.A(_077_),
    .B(_046_),
    .COUT(_078_),
    .SUM(_079_));
 sky130_fd_sc_hd__ha_1 _489_ (.A(_077_),
    .B(net8),
    .COUT(_080_),
    .SUM(_262_));
 sky130_fd_sc_hd__ha_1 _490_ (.A(net4),
    .B(_046_),
    .COUT(_081_),
    .SUM(_263_));
 sky130_fd_sc_hd__ha_1 _491_ (.A(net4),
    .B(net8),
    .COUT(_082_),
    .SUM(_264_));
 sky130_fd_sc_hd__ha_1 _492_ (.A(_246_),
    .B(_244_),
    .COUT(_265_),
    .SUM(_266_));
 sky130_fd_sc_hd__ha_1 _493_ (.A(_266_),
    .B(_083_),
    .COUT(_084_),
    .SUM(_085_));
 sky130_fd_sc_hd__ha_1 _494_ (.A(_086_),
    .B(_087_),
    .COUT(_267_),
    .SUM(_268_));
 sky130_fd_sc_hd__ha_1 _495_ (.A(_268_),
    .B(_245_),
    .COUT(_269_),
    .SUM(_270_));
 sky130_fd_sc_hd__ha_1 _496_ (.A(_270_),
    .B(_265_),
    .COUT(_088_),
    .SUM(_089_));
 sky130_fd_sc_hd__ha_1 _497_ (.A(_082_),
    .B(_267_),
    .COUT(_090_),
    .SUM(_271_));
 sky130_fd_sc_hd__ha_1 _498_ (.A(_271_),
    .B(_269_),
    .COUT(_091_),
    .SUM(_092_));
 sky130_fd_sc_hd__dfrtp_1 \carry_out_r$_DFFE_PN0N_  (.D(_093_),
    .Q(net14),
    .RESET_B(net13),
    .CLK(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_0_clk (.A(clk),
    .X(clknet_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_1_0__f_clk (.A(clknet_0_clk),
    .X(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_1_1__f_clk (.A(clknet_0_clk),
    .X(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__clkbuf_8 clkload0 (.A(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input1 (.A(a[0]),
    .X(net1));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input10 (.A(opcode[1]),
    .X(net10));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input11 (.A(opcode[2]),
    .X(net11));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input12 (.A(opcode[3]),
    .X(net12));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input13 (.A(rst_n),
    .X(net13));
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
 sky130_fd_sc_hd__clkdlybuf4s50_1 input9 (.A(opcode[0]),
    .X(net9));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output14 (.A(net14),
    .X(carry_out));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output15 (.A(net15),
    .X(overflow));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output16 (.A(net16),
    .X(result[0]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output17 (.A(net17),
    .X(result[1]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output18 (.A(net18),
    .X(result[2]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output19 (.A(net19),
    .X(result[3]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output20 (.A(net20),
    .X(result[4]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output21 (.A(net21),
    .X(result[5]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output22 (.A(net22),
    .X(result[6]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output23 (.A(net23),
    .X(result[7]));
 sky130_fd_sc_hd__dfrtp_1 \overflow_r$_DFFE_PN0N_  (.D(_094_),
    .Q(net15),
    .RESET_B(net13),
    .CLK(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \result_r[0]$_DFF_PN0_  (.D(_236_),
    .Q(net16),
    .RESET_B(net13),
    .CLK(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \result_r[1]$_DFF_PN0_  (.D(_237_),
    .Q(net17),
    .RESET_B(net13),
    .CLK(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \result_r[2]$_DFF_PN0_  (.D(_238_),
    .Q(net18),
    .RESET_B(net13),
    .CLK(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \result_r[3]$_DFF_PN0_  (.D(_239_),
    .Q(net19),
    .RESET_B(net13),
    .CLK(clknet_1_0__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \result_r[4]$_DFF_PN0_  (.D(_240_),
    .Q(net20),
    .RESET_B(net13),
    .CLK(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \result_r[5]$_DFF_PN0_  (.D(_241_),
    .Q(net21),
    .RESET_B(net13),
    .CLK(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \result_r[6]$_DFF_PN0_  (.D(_242_),
    .Q(net22),
    .RESET_B(net13),
    .CLK(clknet_1_1__leaf_clk));
 sky130_fd_sc_hd__dfrtp_1 \result_r[7]$_DFF_PN0_  (.D(_243_),
    .Q(net23),
    .RESET_B(net13),
    .CLK(clknet_1_1__leaf_clk));
endmodule
