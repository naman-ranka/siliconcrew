module simon_game (clk,
    game_over,
    rst_n,
    sound,
    btn,
    dbg_state,
    led,
    level,
    segment_digits,
    segments);
 input clk;
 output game_over;
 input rst_n;
 output sound;
 input [3:0] btn;
 output [2:0] dbg_state;
 output [3:0] led;
 output [4:0] level;
 output [1:0] segment_digits;
 output [6:0] segments;

 wire _0000_;
 wire _0001_;
 wire _0002_;
 wire _0003_;
 wire _0004_;
 wire _0005_;
 wire _0006_;
 wire _0007_;
 wire _0008_;
 wire _0009_;
 wire _0010_;
 wire _0011_;
 wire _0012_;
 wire _0013_;
 wire _0014_;
 wire _0015_;
 wire _0016_;
 wire _0017_;
 wire _0018_;
 wire _0019_;
 wire _0020_;
 wire _0021_;
 wire _0022_;
 wire _0023_;
 wire _0024_;
 wire _0025_;
 wire _0026_;
 wire _0027_;
 wire _0028_;
 wire _0029_;
 wire _0030_;
 wire _0031_;
 wire _0032_;
 wire _0033_;
 wire _0034_;
 wire _0035_;
 wire _0036_;
 wire _0037_;
 wire _0038_;
 wire _0039_;
 wire _0040_;
 wire _0041_;
 wire _0042_;
 wire _0043_;
 wire _0044_;
 wire _0045_;
 wire _0046_;
 wire _0047_;
 wire _0048_;
 wire _0049_;
 wire _0050_;
 wire _0051_;
 wire _0052_;
 wire _0053_;
 wire _0054_;
 wire _0055_;
 wire _0056_;
 wire _0057_;
 wire _0058_;
 wire _0059_;
 wire _0060_;
 wire _0061_;
 wire _0062_;
 wire _0063_;
 wire _0064_;
 wire _0065_;
 wire _0066_;
 wire _0067_;
 wire _0068_;
 wire _0069_;
 wire _0070_;
 wire _0071_;
 wire _0072_;
 wire _0073_;
 wire _0074_;
 wire _0075_;
 wire _0076_;
 wire _0077_;
 wire _0078_;
 wire _0079_;
 wire _0080_;
 wire _0081_;
 wire _0082_;
 wire _0083_;
 wire _0084_;
 wire _0085_;
 wire _0086_;
 wire _0087_;
 wire _0088_;
 wire _0089_;
 wire _0090_;
 wire _0091_;
 wire _0092_;
 wire _0093_;
 wire _0094_;
 wire _0095_;
 wire _0096_;
 wire _0097_;
 wire _0098_;
 wire _0099_;
 wire _0100_;
 wire _0101_;
 wire _0102_;
 wire _0103_;
 wire _0104_;
 wire _0105_;
 wire _0106_;
 wire _0107_;
 wire _0108_;
 wire _0109_;
 wire _0110_;
 wire _0111_;
 wire _0112_;
 wire _0113_;
 wire _0114_;
 wire _0115_;
 wire _0116_;
 wire _0117_;
 wire _0118_;
 wire _0119_;
 wire _0120_;
 wire _0121_;
 wire _0122_;
 wire _0123_;
 wire _0124_;
 wire _0125_;
 wire _0126_;
 wire _0127_;
 wire _0128_;
 wire _0129_;
 wire _0130_;
 wire _0131_;
 wire _0132_;
 wire _0133_;
 wire _0134_;
 wire _0135_;
 wire _0136_;
 wire _0137_;
 wire _0138_;
 wire _0139_;
 wire _0140_;
 wire _0141_;
 wire _0142_;
 wire _0143_;
 wire _0144_;
 wire _0145_;
 wire _0146_;
 wire _0147_;
 wire _0148_;
 wire _0149_;
 wire _0150_;
 wire _0151_;
 wire _0152_;
 wire _0153_;
 wire _0154_;
 wire _0155_;
 wire _0156_;
 wire _0157_;
 wire _0158_;
 wire _0159_;
 wire _0160_;
 wire _0161_;
 wire _0162_;
 wire _0163_;
 wire _0164_;
 wire _0165_;
 wire _0166_;
 wire _0167_;
 wire _0168_;
 wire _0169_;
 wire _0170_;
 wire _0171_;
 wire _0172_;
 wire _0173_;
 wire _0174_;
 wire _0175_;
 wire _0176_;
 wire _0177_;
 wire _0178_;
 wire _0179_;
 wire _0180_;
 wire _0181_;
 wire _0182_;
 wire _0183_;
 wire _0184_;
 wire _0185_;
 wire _0186_;
 wire _0187_;
 wire _0188_;
 wire _0189_;
 wire _0190_;
 wire _0191_;
 wire _0192_;
 wire _0193_;
 wire _0194_;
 wire _0195_;
 wire _0196_;
 wire _0197_;
 wire _0198_;
 wire _0199_;
 wire _0200_;
 wire _0201_;
 wire _0202_;
 wire _0203_;
 wire _0204_;
 wire _0205_;
 wire _0206_;
 wire _0207_;
 wire _0208_;
 wire _0209_;
 wire _0210_;
 wire _0211_;
 wire _0212_;
 wire _0213_;
 wire _0214_;
 wire _0215_;
 wire _0216_;
 wire _0217_;
 wire _0218_;
 wire _0219_;
 wire _0220_;
 wire _0221_;
 wire _0222_;
 wire _0223_;
 wire _0224_;
 wire _0225_;
 wire _0226_;
 wire _0227_;
 wire _0228_;
 wire _0229_;
 wire _0230_;
 wire _0231_;
 wire _0232_;
 wire _0233_;
 wire _0234_;
 wire _0235_;
 wire _0236_;
 wire _0237_;
 wire _0238_;
 wire _0239_;
 wire _0240_;
 wire _0241_;
 wire _0242_;
 wire _0243_;
 wire _0244_;
 wire _0245_;
 wire _0246_;
 wire _0247_;
 wire _0248_;
 wire _0249_;
 wire _0250_;
 wire _0251_;
 wire _0252_;
 wire _0253_;
 wire _0254_;
 wire _0255_;
 wire _0256_;
 wire _0257_;
 wire _0258_;
 wire _0259_;
 wire _0260_;
 wire _0261_;
 wire _0262_;
 wire _0263_;
 wire _0264_;
 wire _0265_;
 wire _0266_;
 wire _0267_;
 wire _0268_;
 wire _0269_;
 wire _0270_;
 wire _0271_;
 wire _0272_;
 wire _0273_;
 wire _0274_;
 wire _0275_;
 wire _0276_;
 wire _0277_;
 wire _0278_;
 wire _0279_;
 wire _0280_;
 wire _0281_;
 wire _0282_;
 wire _0283_;
 wire _0284_;
 wire _0285_;
 wire _0286_;
 wire _0287_;
 wire _0288_;
 wire _0289_;
 wire _0291_;
 wire _0293_;
 wire _0294_;
 wire _0295_;
 wire _0296_;
 wire _0297_;
 wire _0298_;
 wire _0299_;
 wire _0300_;
 wire _0301_;
 wire _0302_;
 wire _0303_;
 wire _0304_;
 wire _0305_;
 wire _0306_;
 wire _0307_;
 wire _0308_;
 wire _0309_;
 wire _0310_;
 wire _0311_;
 wire _0312_;
 wire _0313_;
 wire _0314_;
 wire _0315_;
 wire _0316_;
 wire _0317_;
 wire _0318_;
 wire _0319_;
 wire _0320_;
 wire _0321_;
 wire _0322_;
 wire _0323_;
 wire _0324_;
 wire _0325_;
 wire _0326_;
 wire _0327_;
 wire _0328_;
 wire _0329_;
 wire _0330_;
 wire _0331_;
 wire _0332_;
 wire _0333_;
 wire _0334_;
 wire _0335_;
 wire _0336_;
 wire _0337_;
 wire _0338_;
 wire _0339_;
 wire _0340_;
 wire _0341_;
 wire _0342_;
 wire _0343_;
 wire _0344_;
 wire _0345_;
 wire _0346_;
 wire _0347_;
 wire _0348_;
 wire _0349_;
 wire _0350_;
 wire _0351_;
 wire _0352_;
 wire _0353_;
 wire _0354_;
 wire _0355_;
 wire _0356_;
 wire _0357_;
 wire _0358_;
 wire _0359_;
 wire _0360_;
 wire _0361_;
 wire _0362_;
 wire _0363_;
 wire _0364_;
 wire _0365_;
 wire _0366_;
 wire _0367_;
 wire _0368_;
 wire _0369_;
 wire _0370_;
 wire _0371_;
 wire _0372_;
 wire _0373_;
 wire _0374_;
 wire _0375_;
 wire _0376_;
 wire _0377_;
 wire _0378_;
 wire _0379_;
 wire _0380_;
 wire _0381_;
 wire _0382_;
 wire _0383_;
 wire _0384_;
 wire _0385_;
 wire _0386_;
 wire _0387_;
 wire _0388_;
 wire _0389_;
 wire _0390_;
 wire _0391_;
 wire _0392_;
 wire _0393_;
 wire _0394_;
 wire _0395_;
 wire _0396_;
 wire _0397_;
 wire _0398_;
 wire _0399_;
 wire _0400_;
 wire _0401_;
 wire _0402_;
 wire _0403_;
 wire _0404_;
 wire _0405_;
 wire _0407_;
 wire _0408_;
 wire _0409_;
 wire _0410_;
 wire _0411_;
 wire _0412_;
 wire _0413_;
 wire _0414_;
 wire _0415_;
 wire _0416_;
 wire _0417_;
 wire _0418_;
 wire _0419_;
 wire _0420_;
 wire _0421_;
 wire _0422_;
 wire _0423_;
 wire _0424_;
 wire _0425_;
 wire _0426_;
 wire _0427_;
 wire _0428_;
 wire _0429_;
 wire _0430_;
 wire _0431_;
 wire _0432_;
 wire _0433_;
 wire _0434_;
 wire _0435_;
 wire _0436_;
 wire _0437_;
 wire _0438_;
 wire _0439_;
 wire _0440_;
 wire _0441_;
 wire _0442_;
 wire _0443_;
 wire _0444_;
 wire _0445_;
 wire _0446_;
 wire _0447_;
 wire _0448_;
 wire _0449_;
 wire _0450_;
 wire _0451_;
 wire _0452_;
 wire _0453_;
 wire _0454_;
 wire _0455_;
 wire _0456_;
 wire _0457_;
 wire _0458_;
 wire _0459_;
 wire _0460_;
 wire _0461_;
 wire _0462_;
 wire _0463_;
 wire _0464_;
 wire _0465_;
 wire _0466_;
 wire _0467_;
 wire _0468_;
 wire _0469_;
 wire _0470_;
 wire _0471_;
 wire _0472_;
 wire _0473_;
 wire _0474_;
 wire _0475_;
 wire _0476_;
 wire _0477_;
 wire _0478_;
 wire _0479_;
 wire _0480_;
 wire _0481_;
 wire _0482_;
 wire _0483_;
 wire _0484_;
 wire _0485_;
 wire _0486_;
 wire _0487_;
 wire _0488_;
 wire clknet_4_12_0_clk;
 wire clknet_4_11_0_clk;
 wire clknet_4_10_0_clk;
 wire _0492_;
 wire clknet_4_9_0_clk;
 wire clknet_4_8_0_clk;
 wire _0495_;
 wire clknet_4_7_0_clk;
 wire _0497_;
 wire _0498_;
 wire _0499_;
 wire clknet_4_6_0_clk;
 wire clknet_4_5_0_clk;
 wire _0502_;
 wire _0503_;
 wire clknet_4_4_0_clk;
 wire _0505_;
 wire _0506_;
 wire _0507_;
 wire _0508_;
 wire _0509_;
 wire _0510_;
 wire clknet_4_3_0_clk;
 wire clknet_4_2_0_clk;
 wire _0513_;
 wire _0514_;
 wire _0515_;
 wire _0516_;
 wire _0517_;
 wire _0518_;
 wire _0519_;
 wire _0520_;
 wire _0521_;
 wire clknet_4_1_0_clk;
 wire clknet_4_0_0_clk;
 wire net48;
 wire net44;
 wire _0526_;
 wire _0527_;
 wire _0528_;
 wire _0529_;
 wire _0530_;
 wire _0531_;
 wire _0532_;
 wire _0533_;
 wire _0534_;
 wire _0535_;
 wire _0536_;
 wire _0537_;
 wire _0538_;
 wire _0539_;
 wire _0540_;
 wire _0541_;
 wire _0542_;
 wire _0543_;
 wire _0544_;
 wire _0545_;
 wire net43;
 wire net42;
 wire _0548_;
 wire _0549_;
 wire net40;
 wire _0551_;
 wire _0552_;
 wire _0553_;
 wire net39;
 wire net51;
 wire _0556_;
 wire _0557_;
 wire _0558_;
 wire _0559_;
 wire _0560_;
 wire _0561_;
 wire _0562_;
 wire _0563_;
 wire _0564_;
 wire _0565_;
 wire _0566_;
 wire _0567_;
 wire _0568_;
 wire _0569_;
 wire _0570_;
 wire _0571_;
 wire _0572_;
 wire _0573_;
 wire _0574_;
 wire _0575_;
 wire _0576_;
 wire _0577_;
 wire _0578_;
 wire net50;
 wire net49;
 wire _0581_;
 wire _0582_;
 wire _0583_;
 wire _0584_;
 wire _0585_;
 wire _0586_;
 wire _0587_;
 wire _0588_;
 wire _0589_;
 wire _0590_;
 wire _0591_;
 wire _0592_;
 wire _0593_;
 wire _0594_;
 wire _0595_;
 wire _0596_;
 wire _0597_;
 wire _0598_;
 wire _0599_;
 wire net47;
 wire net46;
 wire _0602_;
 wire _0603_;
 wire _0604_;
 wire _0605_;
 wire _0606_;
 wire _0607_;
 wire _0608_;
 wire net41;
 wire _0610_;
 wire clknet_0_clk;
 wire _0612_;
 wire _0613_;
 wire _0614_;
 wire net45;
 wire _0616_;
 wire _0617_;
 wire _0619_;
 wire _0621_;
 wire _0622_;
 wire _0623_;
 wire _0626_;
 wire _0627_;
 wire _0630_;
 wire _0631_;
 wire _0632_;
 wire _0633_;
 wire _0635_;
 wire _0636_;
 wire _0637_;
 wire _0638_;
 wire _0639_;
 wire _0640_;
 wire _0644_;
 wire _0646_;
 wire _0647_;
 wire _0648_;
 wire _0649_;
 wire _0650_;
 wire _0651_;
 wire _0652_;
 wire _0653_;
 wire _0654_;
 wire _0655_;
 wire _0656_;
 wire _0657_;
 wire _0658_;
 wire _0659_;
 wire _0660_;
 wire _0661_;
 wire _0662_;
 wire _0663_;
 wire _0664_;
 wire _0665_;
 wire _0666_;
 wire _0667_;
 wire _0668_;
 wire _0669_;
 wire _0670_;
 wire _0671_;
 wire _0672_;
 wire _0673_;
 wire _0674_;
 wire _0675_;
 wire _0677_;
 wire _0678_;
 wire _0679_;
 wire _0680_;
 wire _0681_;
 wire _0682_;
 wire _0683_;
 wire _0684_;
 wire _0685_;
 wire _0686_;
 wire _0687_;
 wire _0688_;
 wire _0689_;
 wire _0690_;
 wire _0691_;
 wire _0692_;
 wire _0693_;
 wire _0694_;
 wire _0695_;
 wire _0696_;
 wire _0697_;
 wire _0698_;
 wire _0699_;
 wire _0700_;
 wire _0701_;
 wire _0702_;
 wire _0703_;
 wire _0704_;
 wire _0705_;
 wire _0706_;
 wire _0707_;
 wire _0708_;
 wire _0709_;
 wire _0710_;
 wire _0711_;
 wire _0712_;
 wire _0714_;
 wire _0715_;
 wire _0716_;
 wire _0717_;
 wire _0718_;
 wire _0719_;
 wire _0720_;
 wire _0721_;
 wire _0722_;
 wire _0723_;
 wire _0724_;
 wire _0725_;
 wire _0726_;
 wire _0727_;
 wire _0728_;
 wire _0729_;
 wire _0730_;
 wire _0731_;
 wire _0732_;
 wire _0733_;
 wire _0734_;
 wire _0735_;
 wire _0736_;
 wire _0737_;
 wire _0738_;
 wire _0739_;
 wire _0740_;
 wire _0741_;
 wire _0742_;
 wire _0744_;
 wire _0745_;
 wire _0746_;
 wire _0747_;
 wire _0748_;
 wire _0749_;
 wire _0750_;
 wire _0751_;
 wire _0753_;
 wire _0754_;
 wire _0755_;
 wire _0757_;
 wire _0758_;
 wire _0759_;
 wire _0760_;
 wire _0761_;
 wire _0762_;
 wire _0763_;
 wire _0764_;
 wire _0765_;
 wire _0766_;
 wire _0767_;
 wire _0768_;
 wire _0769_;
 wire _0770_;
 wire _0771_;
 wire _0772_;
 wire _0773_;
 wire _0774_;
 wire _0775_;
 wire _0776_;
 wire _0777_;
 wire _0778_;
 wire _0779_;
 wire _0780_;
 wire _0781_;
 wire _0782_;
 wire _0783_;
 wire _0784_;
 wire _0785_;
 wire _0786_;
 wire _0787_;
 wire _0788_;
 wire _0789_;
 wire _0790_;
 wire _0791_;
 wire _0792_;
 wire _0793_;
 wire _0794_;
 wire _0795_;
 wire _0796_;
 wire _0797_;
 wire _0798_;
 wire _0799_;
 wire _0800_;
 wire _0801_;
 wire _0802_;
 wire _0803_;
 wire _0804_;
 wire _0805_;
 wire _0806_;
 wire _0807_;
 wire _0808_;
 wire _0809_;
 wire _0810_;
 wire _0811_;
 wire _0812_;
 wire _0813_;
 wire _0814_;
 wire _0815_;
 wire _0816_;
 wire _0817_;
 wire _0818_;
 wire _0819_;
 wire _0820_;
 wire _0821_;
 wire _0822_;
 wire _0823_;
 wire _0824_;
 wire _0825_;
 wire _0826_;
 wire _0828_;
 wire _0829_;
 wire _0830_;
 wire _0831_;
 wire _0834_;
 wire _0835_;
 wire _0836_;
 wire _0837_;
 wire _0838_;
 wire _0839_;
 wire _0840_;
 wire _0841_;
 wire _0842_;
 wire _0843_;
 wire _0844_;
 wire _0845_;
 wire _0846_;
 wire _0847_;
 wire _0848_;
 wire _0849_;
 wire _0850_;
 wire _0851_;
 wire _0852_;
 wire _0853_;
 wire _0854_;
 wire _0855_;
 wire _0856_;
 wire _0857_;
 wire _0858_;
 wire _0859_;
 wire _0860_;
 wire _0861_;
 wire _0862_;
 wire _0863_;
 wire _0864_;
 wire _0865_;
 wire _0866_;
 wire _0867_;
 wire _0868_;
 wire _0869_;
 wire _0870_;
 wire _0871_;
 wire _0872_;
 wire _0873_;
 wire _0874_;
 wire _0875_;
 wire _0876_;
 wire _0877_;
 wire _0878_;
 wire _0879_;
 wire _0880_;
 wire _0881_;
 wire _0882_;
 wire _0883_;
 wire _0884_;
 wire _0885_;
 wire _0886_;
 wire _0887_;
 wire _0888_;
 wire _0889_;
 wire _0890_;
 wire _0891_;
 wire _0892_;
 wire _0894_;
 wire _0895_;
 wire _0896_;
 wire _0897_;
 wire _0898_;
 wire _0899_;
 wire _0900_;
 wire _0901_;
 wire _0902_;
 wire _0903_;
 wire _0905_;
 wire _0906_;
 wire _0907_;
 wire _0908_;
 wire _0909_;
 wire _0910_;
 wire _0911_;
 wire _0913_;
 wire _0914_;
 wire _0915_;
 wire _0916_;
 wire _0917_;
 wire _0918_;
 wire _0919_;
 wire _0920_;
 wire _0921_;
 wire _0922_;
 wire _0923_;
 wire _0924_;
 wire _0925_;
 wire _0926_;
 wire _0927_;
 wire _0928_;
 wire _0929_;
 wire _0930_;
 wire _0931_;
 wire _0932_;
 wire _0933_;
 wire _0934_;
 wire _0935_;
 wire _0936_;
 wire _0937_;
 wire _0938_;
 wire _0939_;
 wire _0940_;
 wire _0941_;
 wire _0943_;
 wire _0944_;
 wire _0945_;
 wire _0946_;
 wire _0947_;
 wire _0948_;
 wire _0949_;
 wire _0950_;
 wire _0951_;
 wire _0952_;
 wire _0953_;
 wire _0954_;
 wire _0955_;
 wire _0956_;
 wire _0957_;
 wire _0959_;
 wire _0961_;
 wire _0962_;
 wire _0963_;
 wire _0964_;
 wire _0965_;
 wire _0966_;
 wire _0967_;
 wire _0968_;
 wire _0969_;
 wire _0970_;
 wire _0971_;
 wire _0972_;
 wire _0973_;
 wire _0974_;
 wire _0975_;
 wire _0976_;
 wire _0977_;
 wire _0978_;
 wire _0979_;
 wire _0980_;
 wire net1;
 wire net2;
 wire net3;
 wire net4;
 wire \core.millis_counter[0] ;
 wire \core.millis_counter[1] ;
 wire \core.millis_counter[2] ;
 wire \core.millis_counter[3] ;
 wire \core.millis_counter[4] ;
 wire \core.millis_counter[5] ;
 wire \core.millis_counter[6] ;
 wire \core.millis_counter[7] ;
 wire \core.millis_counter[8] ;
 wire \core.millis_counter[9] ;
 wire \core.next_random[0] ;
 wire \core.next_random[1] ;
 wire \core.play1.freq[0] ;
 wire \core.play1.freq[1] ;
 wire \core.play1.freq[2] ;
 wire \core.play1.freq[3] ;
 wire \core.play1.freq[4] ;
 wire \core.play1.freq[5] ;
 wire \core.play1.freq[6] ;
 wire \core.play1.freq[7] ;
 wire \core.play1.freq[8] ;
 wire \core.play1.freq[9] ;
 wire \core.play1.tick_counter[0] ;
 wire \core.play1.tick_counter[10] ;
 wire \core.play1.tick_counter[11] ;
 wire \core.play1.tick_counter[12] ;
 wire \core.play1.tick_counter[13] ;
 wire \core.play1.tick_counter[14] ;
 wire \core.play1.tick_counter[15] ;
 wire \core.play1.tick_counter[16] ;
 wire \core.play1.tick_counter[17] ;
 wire \core.play1.tick_counter[18] ;
 wire \core.play1.tick_counter[19] ;
 wire \core.play1.tick_counter[1] ;
 wire \core.play1.tick_counter[20] ;
 wire \core.play1.tick_counter[21] ;
 wire \core.play1.tick_counter[22] ;
 wire \core.play1.tick_counter[23] ;
 wire \core.play1.tick_counter[24] ;
 wire \core.play1.tick_counter[25] ;
 wire \core.play1.tick_counter[26] ;
 wire \core.play1.tick_counter[27] ;
 wire \core.play1.tick_counter[28] ;
 wire \core.play1.tick_counter[29] ;
 wire \core.play1.tick_counter[2] ;
 wire \core.play1.tick_counter[30] ;
 wire \core.play1.tick_counter[31] ;
 wire \core.play1.tick_counter[3] ;
 wire \core.play1.tick_counter[4] ;
 wire \core.play1.tick_counter[5] ;
 wire \core.play1.tick_counter[6] ;
 wire \core.play1.tick_counter[7] ;
 wire \core.play1.tick_counter[8] ;
 wire \core.play1.tick_counter[9] ;
 wire \core.score1.active_digit ;
 wire \core.score1.ena ;
 wire \core.score1.inc ;
 wire \core.score1.ones[0] ;
 wire \core.score1.ones[1] ;
 wire \core.score1.ones[2] ;
 wire \core.score1.ones[3] ;
 wire \core.score1.tens[0] ;
 wire \core.score1.tens[1] ;
 wire \core.score1.tens[2] ;
 wire \core.score1.tens[3] ;
 wire \core.score_rst ;
 wire \core.seq[0][0] ;
 wire \core.seq[0][1] ;
 wire \core.seq[10][0] ;
 wire \core.seq[10][1] ;
 wire \core.seq[11][0] ;
 wire \core.seq[11][1] ;
 wire \core.seq[12][0] ;
 wire \core.seq[12][1] ;
 wire \core.seq[13][0] ;
 wire \core.seq[13][1] ;
 wire \core.seq[14][0] ;
 wire \core.seq[14][1] ;
 wire \core.seq[15][0] ;
 wire \core.seq[15][1] ;
 wire \core.seq[16][0] ;
 wire \core.seq[16][1] ;
 wire \core.seq[17][0] ;
 wire \core.seq[17][1] ;
 wire \core.seq[18][0] ;
 wire \core.seq[18][1] ;
 wire \core.seq[19][0] ;
 wire \core.seq[19][1] ;
 wire \core.seq[1][0] ;
 wire \core.seq[1][1] ;
 wire \core.seq[20][0] ;
 wire \core.seq[20][1] ;
 wire \core.seq[21][0] ;
 wire \core.seq[21][1] ;
 wire \core.seq[22][0] ;
 wire \core.seq[22][1] ;
 wire \core.seq[23][0] ;
 wire \core.seq[23][1] ;
 wire \core.seq[24][0] ;
 wire \core.seq[24][1] ;
 wire \core.seq[25][0] ;
 wire \core.seq[25][1] ;
 wire \core.seq[26][0] ;
 wire \core.seq[26][1] ;
 wire \core.seq[27][0] ;
 wire \core.seq[27][1] ;
 wire \core.seq[28][0] ;
 wire \core.seq[28][1] ;
 wire \core.seq[29][0] ;
 wire \core.seq[29][1] ;
 wire \core.seq[2][0] ;
 wire \core.seq[2][1] ;
 wire \core.seq[30][0] ;
 wire \core.seq[30][1] ;
 wire \core.seq[31][0] ;
 wire \core.seq[31][1] ;
 wire \core.seq[3][0] ;
 wire \core.seq[3][1] ;
 wire \core.seq[4][0] ;
 wire \core.seq[4][1] ;
 wire \core.seq[5][0] ;
 wire \core.seq[5][1] ;
 wire \core.seq[6][0] ;
 wire \core.seq[6][1] ;
 wire \core.seq[7][0] ;
 wire \core.seq[7][1] ;
 wire \core.seq[8][0] ;
 wire \core.seq[8][1] ;
 wire \core.seq[9][0] ;
 wire \core.seq[9][1] ;
 wire \core.seq_counter[0] ;
 wire \core.seq_counter[1] ;
 wire \core.seq_counter[2] ;
 wire \core.seq_counter[3] ;
 wire \core.seq_counter[4] ;
 wire \core.tick_counter[0] ;
 wire \core.tick_counter[10] ;
 wire \core.tick_counter[11] ;
 wire \core.tick_counter[12] ;
 wire \core.tick_counter[13] ;
 wire \core.tick_counter[14] ;
 wire \core.tick_counter[15] ;
 wire \core.tick_counter[1] ;
 wire \core.tick_counter[2] ;
 wire \core.tick_counter[3] ;
 wire \core.tick_counter[4] ;
 wire \core.tick_counter[5] ;
 wire \core.tick_counter[6] ;
 wire \core.tick_counter[7] ;
 wire \core.tick_counter[8] ;
 wire \core.tick_counter[9] ;
 wire \core.tone_sequence_counter[0] ;
 wire \core.tone_sequence_counter[1] ;
 wire \core.tone_sequence_counter[2] ;
 wire \core.user_input[0] ;
 wire \core.user_input[1] ;
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
 wire net17;
 wire net18;
 wire net5;
 wire net19;
 wire net20;
 wire net21;
 wire net22;
 wire net23;
 wire net24;
 wire net25;
 wire net26;
 wire net27;
 wire net28;
 wire clknet_4_13_0_clk;
 wire clknet_4_14_0_clk;
 wire clknet_4_15_0_clk;

 sky130_fd_sc_hd__and3_1 _0981_ (.A(net48),
    .B(net7),
    .C(net47),
    .X(net9));
 sky130_fd_sc_hd__clkinv_1 _0985_ (.A(net51),
    .Y(_0492_));
 sky130_fd_sc_hd__nor4_1 _0988_ (.A(net1),
    .B(net2),
    .C(net3),
    .D(net4),
    .Y(_0495_));
 sky130_fd_sc_hd__nand2b_1 _0990_ (.A_N(net7),
    .B(net47),
    .Y(_0497_));
 sky130_fd_sc_hd__nor4_1 _0991_ (.A(_0492_),
    .B(net48),
    .C(_0495_),
    .D(_0497_),
    .Y(_0498_));
 sky130_fd_sc_hd__nand3b_1 _0992_ (.A_N(net14),
    .B(net15),
    .C(net46),
    .Y(_0499_));
 sky130_fd_sc_hd__or3_1 _0995_ (.A(net16),
    .B(net17),
    .C(net18),
    .X(_0502_));
 sky130_fd_sc_hd__nor2_1 _0996_ (.A(_0499_),
    .B(_0502_),
    .Y(_0032_));
 sky130_fd_sc_hd__nand3b_1 _0997_ (.A_N(net15),
    .B(net46),
    .C(net14),
    .Y(_0503_));
 sky130_fd_sc_hd__nor2_1 _0998_ (.A(_0502_),
    .B(_0503_),
    .Y(_0021_));
 sky130_fd_sc_hd__nand3_1 _1000_ (.A(net16),
    .B(net17),
    .C(net18),
    .Y(_0505_));
 sky130_fd_sc_hd__nand3_1 _1001_ (.A(net14),
    .B(net15),
    .C(net46),
    .Y(_0506_));
 sky130_fd_sc_hd__nor2_1 _1002_ (.A(_0505_),
    .B(_0506_),
    .Y(_0034_));
 sky130_fd_sc_hd__nor2_1 _1003_ (.A(_0499_),
    .B(_0505_),
    .Y(_0033_));
 sky130_fd_sc_hd__nor2_1 _1004_ (.A(_0503_),
    .B(_0505_),
    .Y(_0031_));
 sky130_fd_sc_hd__nor2_1 _1005_ (.A(net14),
    .B(net15),
    .Y(_0507_));
 sky130_fd_sc_hd__nand2_1 _1006_ (.A(net46),
    .B(_0507_),
    .Y(_0508_));
 sky130_fd_sc_hd__nor2_1 _1007_ (.A(_0505_),
    .B(_0508_),
    .Y(_0030_));
 sky130_fd_sc_hd__nand3b_1 _1008_ (.A_N(net16),
    .B(net17),
    .C(net18),
    .Y(_0509_));
 sky130_fd_sc_hd__nor2_1 _1009_ (.A(_0506_),
    .B(_0509_),
    .Y(_0029_));
 sky130_fd_sc_hd__nor2_1 _1010_ (.A(_0499_),
    .B(_0509_),
    .Y(_0028_));
 sky130_fd_sc_hd__nor2_1 _1011_ (.A(_0503_),
    .B(_0509_),
    .Y(_0027_));
 sky130_fd_sc_hd__nor2_1 _1012_ (.A(_0508_),
    .B(_0509_),
    .Y(_0026_));
 sky130_fd_sc_hd__nand3b_1 _1013_ (.A_N(net17),
    .B(net18),
    .C(net16),
    .Y(_0510_));
 sky130_fd_sc_hd__nor2_1 _1014_ (.A(_0506_),
    .B(_0510_),
    .Y(_0025_));
 sky130_fd_sc_hd__nor2_1 _1017_ (.A(net48),
    .B(net7),
    .Y(_0513_));
 sky130_fd_sc_hd__a21oi_1 _1018_ (.A1(_0104_),
    .A2(net9),
    .B1(_0513_),
    .Y(_0514_));
 sky130_fd_sc_hd__nor2_1 _1019_ (.A(_0495_),
    .B(_0514_),
    .Y(_0515_));
 sky130_fd_sc_hd__o31ai_1 _1020_ (.A1(net14),
    .A2(net15),
    .A3(_0502_),
    .B1(net46),
    .Y(_0516_));
 sky130_fd_sc_hd__o21a_1 _1021_ (.A1(net50),
    .A2(_0515_),
    .B1(_0516_),
    .X(_0010_));
 sky130_fd_sc_hd__nor2_1 _1022_ (.A(_0499_),
    .B(_0510_),
    .Y(_0024_));
 sky130_fd_sc_hd__nor2_1 _1023_ (.A(_0503_),
    .B(_0510_),
    .Y(_0023_));
 sky130_fd_sc_hd__nor2_1 _1024_ (.A(_0508_),
    .B(_0510_),
    .Y(_0022_));
 sky130_fd_sc_hd__nor2_1 _1025_ (.A(net16),
    .B(net17),
    .Y(_0517_));
 sky130_fd_sc_hd__nand2_1 _1026_ (.A(net18),
    .B(_0517_),
    .Y(_0518_));
 sky130_fd_sc_hd__nor2_1 _1027_ (.A(_0506_),
    .B(_0518_),
    .Y(_0020_));
 sky130_fd_sc_hd__nor2_1 _1028_ (.A(_0499_),
    .B(_0518_),
    .Y(_0019_));
 sky130_fd_sc_hd__nor2_1 _1029_ (.A(_0503_),
    .B(_0518_),
    .Y(_0018_));
 sky130_fd_sc_hd__nor2_1 _1030_ (.A(_0508_),
    .B(_0518_),
    .Y(_0017_));
 sky130_fd_sc_hd__nand3b_1 _1031_ (.A_N(net18),
    .B(net17),
    .C(net16),
    .Y(_0519_));
 sky130_fd_sc_hd__nor2_1 _1032_ (.A(_0506_),
    .B(_0519_),
    .Y(_0016_));
 sky130_fd_sc_hd__nor2_1 _1033_ (.A(_0499_),
    .B(_0519_),
    .Y(_0015_));
 sky130_fd_sc_hd__nor2_1 _1034_ (.A(_0503_),
    .B(_0519_),
    .Y(_0014_));
 sky130_fd_sc_hd__nor2_1 _1035_ (.A(_0508_),
    .B(_0519_),
    .Y(_0013_));
 sky130_fd_sc_hd__or3b_2 _1036_ (.A(net16),
    .B(net18),
    .C_N(net17),
    .X(_0520_));
 sky130_fd_sc_hd__nor2_1 _1037_ (.A(_0506_),
    .B(_0520_),
    .Y(_0012_));
 sky130_fd_sc_hd__nor2_1 _1038_ (.A(_0499_),
    .B(_0520_),
    .Y(_0011_));
 sky130_fd_sc_hd__nor2_1 _1039_ (.A(_0503_),
    .B(_0520_),
    .Y(_0041_));
 sky130_fd_sc_hd__nor2_1 _1040_ (.A(_0508_),
    .B(_0520_),
    .Y(_0040_));
 sky130_fd_sc_hd__or3b_2 _1041_ (.A(net17),
    .B(net18),
    .C_N(net16),
    .X(_0521_));
 sky130_fd_sc_hd__nor2_1 _1042_ (.A(_0506_),
    .B(_0521_),
    .Y(_0039_));
 sky130_fd_sc_hd__nor2_1 _1043_ (.A(_0499_),
    .B(_0521_),
    .Y(_0038_));
 sky130_fd_sc_hd__nor2_1 _1044_ (.A(_0503_),
    .B(_0521_),
    .Y(_0037_));
 sky130_fd_sc_hd__nor2_1 _1045_ (.A(_0508_),
    .B(_0521_),
    .Y(_0036_));
 sky130_fd_sc_hd__nor2_1 _1046_ (.A(_0502_),
    .B(_0506_),
    .Y(_0035_));
 sky130_fd_sc_hd__mux4_2 _1051_ (.A0(\core.seq[0][0] ),
    .A1(\core.seq[1][0] ),
    .A2(\core.seq[2][0] ),
    .A3(\core.seq[3][0] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0526_));
 sky130_fd_sc_hd__mux4_2 _1052_ (.A0(\core.seq[4][0] ),
    .A1(\core.seq[5][0] ),
    .A2(\core.seq[6][0] ),
    .A3(\core.seq[7][0] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0527_));
 sky130_fd_sc_hd__mux4_2 _1053_ (.A0(\core.seq[8][0] ),
    .A1(\core.seq[9][0] ),
    .A2(\core.seq[10][0] ),
    .A3(\core.seq[11][0] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0528_));
 sky130_fd_sc_hd__mux4_2 _1054_ (.A0(\core.seq[12][0] ),
    .A1(\core.seq[13][0] ),
    .A2(\core.seq[14][0] ),
    .A3(\core.seq[15][0] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0529_));
 sky130_fd_sc_hd__mux4_2 _1055_ (.A0(_0526_),
    .A1(_0527_),
    .A2(_0528_),
    .A3(_0529_),
    .S0(_0002_),
    .S1(_0003_),
    .X(_0530_));
 sky130_fd_sc_hd__mux4_2 _1056_ (.A0(\core.seq[16][0] ),
    .A1(\core.seq[17][0] ),
    .A2(\core.seq[18][0] ),
    .A3(\core.seq[19][0] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0531_));
 sky130_fd_sc_hd__mux4_2 _1057_ (.A0(\core.seq[20][0] ),
    .A1(\core.seq[21][0] ),
    .A2(\core.seq[22][0] ),
    .A3(\core.seq[23][0] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0532_));
 sky130_fd_sc_hd__mux4_2 _1058_ (.A0(\core.seq[24][0] ),
    .A1(\core.seq[25][0] ),
    .A2(\core.seq[26][0] ),
    .A3(\core.seq[27][0] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0533_));
 sky130_fd_sc_hd__mux4_2 _1059_ (.A0(\core.seq[28][0] ),
    .A1(\core.seq[29][0] ),
    .A2(\core.seq[30][0] ),
    .A3(\core.seq[31][0] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0534_));
 sky130_fd_sc_hd__mux4_2 _1060_ (.A0(_0531_),
    .A1(_0532_),
    .A2(_0533_),
    .A3(_0534_),
    .S0(_0002_),
    .S1(_0003_),
    .X(_0535_));
 sky130_fd_sc_hd__mux2i_1 _1061_ (.A0(_0530_),
    .A1(_0535_),
    .S(_0004_),
    .Y(_0076_));
 sky130_fd_sc_hd__inv_1 _1062_ (.A(_0076_),
    .Y(_0082_));
 sky130_fd_sc_hd__mux4_2 _1063_ (.A0(\core.seq[0][1] ),
    .A1(\core.seq[1][1] ),
    .A2(\core.seq[2][1] ),
    .A3(\core.seq[3][1] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0536_));
 sky130_fd_sc_hd__mux4_2 _1064_ (.A0(\core.seq[4][1] ),
    .A1(\core.seq[5][1] ),
    .A2(\core.seq[6][1] ),
    .A3(\core.seq[7][1] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0537_));
 sky130_fd_sc_hd__mux4_2 _1065_ (.A0(\core.seq[8][1] ),
    .A1(\core.seq[9][1] ),
    .A2(\core.seq[10][1] ),
    .A3(\core.seq[11][1] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0538_));
 sky130_fd_sc_hd__mux4_2 _1066_ (.A0(\core.seq[12][1] ),
    .A1(\core.seq[13][1] ),
    .A2(\core.seq[14][1] ),
    .A3(\core.seq[15][1] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0539_));
 sky130_fd_sc_hd__mux4_2 _1067_ (.A0(_0536_),
    .A1(_0537_),
    .A2(_0538_),
    .A3(_0539_),
    .S0(_0002_),
    .S1(_0003_),
    .X(_0540_));
 sky130_fd_sc_hd__mux4_2 _1068_ (.A0(\core.seq[16][1] ),
    .A1(\core.seq[17][1] ),
    .A2(\core.seq[18][1] ),
    .A3(\core.seq[19][1] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0541_));
 sky130_fd_sc_hd__mux4_2 _1069_ (.A0(\core.seq[20][1] ),
    .A1(\core.seq[21][1] ),
    .A2(\core.seq[22][1] ),
    .A3(\core.seq[23][1] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0542_));
 sky130_fd_sc_hd__mux4_2 _1070_ (.A0(\core.seq[24][1] ),
    .A1(\core.seq[25][1] ),
    .A2(\core.seq[26][1] ),
    .A3(\core.seq[27][1] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0543_));
 sky130_fd_sc_hd__mux4_2 _1071_ (.A0(\core.seq[28][1] ),
    .A1(\core.seq[29][1] ),
    .A2(\core.seq[30][1] ),
    .A3(\core.seq[31][1] ),
    .S0(net49),
    .S1(_0001_),
    .X(_0544_));
 sky130_fd_sc_hd__mux4_2 _1072_ (.A0(_0541_),
    .A1(_0542_),
    .A2(_0543_),
    .A3(_0544_),
    .S0(_0002_),
    .S1(_0003_),
    .X(_0545_));
 sky130_fd_sc_hd__mux2i_1 _1073_ (.A0(_0540_),
    .A1(_0545_),
    .S(_0004_),
    .Y(_0077_));
 sky130_fd_sc_hd__inv_1 _1074_ (.A(_0077_),
    .Y(_0080_));
 sky130_fd_sc_hd__nor2_1 _1077_ (.A(net7),
    .B(net47),
    .Y(_0548_));
 sky130_fd_sc_hd__nand2_1 _1078_ (.A(net48),
    .B(_0548_),
    .Y(_0549_));
 sky130_fd_sc_hd__nand2_1 _1080_ (.A(net48),
    .B(\core.tone_sequence_counter[2] ),
    .Y(_0551_));
 sky130_fd_sc_hd__nand3_1 _1081_ (.A(\core.millis_counter[5] ),
    .B(\core.millis_counter[7] ),
    .C(\core.millis_counter[6] ),
    .Y(_0552_));
 sky130_fd_sc_hd__nand2_1 _1082_ (.A(\core.millis_counter[8] ),
    .B(\core.millis_counter[9] ),
    .Y(_0553_));
 sky130_fd_sc_hd__inv_1 _1084_ (.A(\core.millis_counter[4] ),
    .Y(_0092_));
 sky130_fd_sc_hd__nand4b_1 _1086_ (.A_N(\core.millis_counter[2] ),
    .B(_0092_),
    .C(_0108_),
    .D(\core.millis_counter[3] ),
    .Y(_0556_));
 sky130_fd_sc_hd__nor3_1 _1087_ (.A(_0552_),
    .B(_0553_),
    .C(_0556_),
    .Y(_0557_));
 sky130_fd_sc_hd__and2_1 _1088_ (.A(net7),
    .B(net47),
    .X(_0558_));
 sky130_fd_sc_hd__o21ai_0 _1089_ (.A1(_0551_),
    .A2(_0557_),
    .B1(_0558_),
    .Y(_0559_));
 sky130_fd_sc_hd__nand3b_1 _1090_ (.A_N(\core.millis_counter[9] ),
    .B(_0108_),
    .C(\core.millis_counter[8] ),
    .Y(_0560_));
 sky130_fd_sc_hd__nand2_1 _1091_ (.A(\core.millis_counter[3] ),
    .B(\core.millis_counter[2] ),
    .Y(_0561_));
 sky130_fd_sc_hd__or4b_2 _1092_ (.A(\core.millis_counter[4] ),
    .B(\core.millis_counter[7] ),
    .C(\core.millis_counter[6] ),
    .D_N(\core.millis_counter[5] ),
    .X(_0562_));
 sky130_fd_sc_hd__or3_1 _1093_ (.A(_0560_),
    .B(_0561_),
    .C(_0562_),
    .X(_0563_));
 sky130_fd_sc_hd__nand2_1 _1094_ (.A(\core.tone_sequence_counter[2] ),
    .B(_0098_),
    .Y(_0564_));
 sky130_fd_sc_hd__o211ai_1 _1095_ (.A1(\core.tone_sequence_counter[2] ),
    .A2(_0563_),
    .B1(_0564_),
    .C1(net9),
    .Y(_0565_));
 sky130_fd_sc_hd__nor4bb_1 _1096_ (.A(\core.millis_counter[5] ),
    .B(\core.millis_counter[6] ),
    .C_N(\core.millis_counter[7] ),
    .D_N(\core.millis_counter[4] ),
    .Y(_0566_));
 sky130_fd_sc_hd__nand2b_1 _1097_ (.A_N(\core.millis_counter[3] ),
    .B(\core.millis_counter[2] ),
    .Y(_0567_));
 sky130_fd_sc_hd__nor3_1 _1098_ (.A(\core.millis_counter[8] ),
    .B(\core.millis_counter[9] ),
    .C(_0567_),
    .Y(_0568_));
 sky130_fd_sc_hd__nand3b_1 _1099_ (.A_N(net6),
    .B(net7),
    .C(net47),
    .Y(_0569_));
 sky130_fd_sc_hd__a31oi_1 _1100_ (.A1(_0111_),
    .A2(_0566_),
    .A3(_0568_),
    .B1(_0569_),
    .Y(_0570_));
 sky130_fd_sc_hd__nor2_1 _1101_ (.A(_0492_),
    .B(_0570_),
    .Y(_0571_));
 sky130_fd_sc_hd__nand2_1 _1102_ (.A(_0565_),
    .B(_0571_),
    .Y(_0572_));
 sky130_fd_sc_hd__a21oi_1 _1103_ (.A1(_0549_),
    .A2(_0559_),
    .B1(_0572_),
    .Y(_0006_));
 sky130_fd_sc_hd__nor3_1 _1104_ (.A(net2),
    .B(net3),
    .C(net4),
    .Y(_0573_));
 sky130_fd_sc_hd__xor2_1 _1105_ (.A(net3),
    .B(net4),
    .X(_0574_));
 sky130_fd_sc_hd__o21ai_0 _1106_ (.A1(net3),
    .A2(net4),
    .B1(net2),
    .Y(_0575_));
 sky130_fd_sc_hd__o21ai_0 _1107_ (.A1(net2),
    .A2(_0574_),
    .B1(_0575_),
    .Y(_0576_));
 sky130_fd_sc_hd__nor2_1 _1108_ (.A(net1),
    .B(_0576_),
    .Y(_0577_));
 sky130_fd_sc_hd__a21oi_1 _1109_ (.A1(net1),
    .A2(_0573_),
    .B1(_0577_),
    .Y(_0578_));
 sky130_fd_sc_hd__nor2b_1 _1110_ (.A(_0578_),
    .B_N(_0498_),
    .Y(_0005_));
 sky130_fd_sc_hd__mux2i_1 _1113_ (.A0(\core.score1.ones[1] ),
    .A1(\core.score1.tens[1] ),
    .S(\core.score1.active_digit ),
    .Y(_0581_));
 sky130_fd_sc_hd__mux2i_1 _1114_ (.A0(\core.score1.ones[3] ),
    .A1(\core.score1.tens[3] ),
    .S(\core.score1.active_digit ),
    .Y(_0582_));
 sky130_fd_sc_hd__nand2_1 _1115_ (.A(\core.score1.ena ),
    .B(_0582_),
    .Y(_0583_));
 sky130_fd_sc_hd__mux2i_1 _1116_ (.A0(\core.score1.ones[2] ),
    .A1(\core.score1.tens[2] ),
    .S(\core.score1.active_digit ),
    .Y(_0584_));
 sky130_fd_sc_hd__nand2_1 _1117_ (.A(\core.score1.ena ),
    .B(_0584_),
    .Y(_0585_));
 sky130_fd_sc_hd__mux2i_1 _1118_ (.A0(\core.score1.ones[0] ),
    .A1(\core.score1.tens[0] ),
    .S(\core.score1.active_digit ),
    .Y(_0586_));
 sky130_fd_sc_hd__nand2_1 _1119_ (.A(\core.score1.ena ),
    .B(_0586_),
    .Y(_0587_));
 sky130_fd_sc_hd__nor3b_1 _1120_ (.A(_0583_),
    .B(_0585_),
    .C_N(_0587_),
    .Y(_0588_));
 sky130_fd_sc_hd__nand3_1 _1121_ (.A(\core.score1.ena ),
    .B(_0585_),
    .C(_0586_),
    .Y(_0589_));
 sky130_fd_sc_hd__nand2b_1 _1122_ (.A_N(_0588_),
    .B(_0589_),
    .Y(_0590_));
 sky130_fd_sc_hd__and2_1 _1123_ (.A(\core.score1.ena ),
    .B(_0582_),
    .X(_0591_));
 sky130_fd_sc_hd__nand2_1 _1124_ (.A(\core.score1.ena ),
    .B(_0581_),
    .Y(_0592_));
 sky130_fd_sc_hd__nor2_1 _1125_ (.A(_0592_),
    .B(_0585_),
    .Y(_0593_));
 sky130_fd_sc_hd__nor2_1 _1126_ (.A(_0591_),
    .B(_0593_),
    .Y(_0594_));
 sky130_fd_sc_hd__a31oi_1 _1127_ (.A1(\core.score1.ena ),
    .A2(_0581_),
    .A3(_0590_),
    .B1(_0594_),
    .Y(_0218_));
 sky130_fd_sc_hd__xor2_1 _1128_ (.A(_0592_),
    .B(_0587_),
    .X(_0595_));
 sky130_fd_sc_hd__a21oi_1 _1129_ (.A1(_0585_),
    .A2(_0595_),
    .B1(_0594_),
    .Y(_0219_));
 sky130_fd_sc_hd__o21ai_0 _1130_ (.A1(_0585_),
    .A2(_0587_),
    .B1(_0591_),
    .Y(_0596_));
 sky130_fd_sc_hd__o21ai_0 _1131_ (.A1(_0592_),
    .A2(_0585_),
    .B1(_0596_),
    .Y(_0220_));
 sky130_fd_sc_hd__nand3_1 _1132_ (.A(\core.score1.ena ),
    .B(_0581_),
    .C(_0590_),
    .Y(_0597_));
 sky130_fd_sc_hd__a31oi_1 _1133_ (.A1(_0592_),
    .A2(_0585_),
    .A3(_0587_),
    .B1(_0594_),
    .Y(_0598_));
 sky130_fd_sc_hd__and2_1 _1134_ (.A(_0597_),
    .B(_0598_),
    .X(_0221_));
 sky130_fd_sc_hd__a21oi_1 _1135_ (.A1(_0591_),
    .A2(_0592_),
    .B1(_0593_),
    .Y(_0599_));
 sky130_fd_sc_hd__nor2_1 _1136_ (.A(_0587_),
    .B(_0599_),
    .Y(_0222_));
 sky130_fd_sc_hd__a221oi_1 _1137_ (.A1(_0583_),
    .A2(_0585_),
    .B1(_0589_),
    .B2(_0592_),
    .C1(_0588_),
    .Y(_0223_));
 sky130_fd_sc_hd__a21boi_0 _1138_ (.A1(_0591_),
    .A2(_0593_),
    .B1_N(_0598_),
    .Y(_0224_));
 sky130_fd_sc_hd__and3_1 _1141_ (.A(\core.next_random[0] ),
    .B(net51),
    .C(_0515_),
    .X(_0007_));
 sky130_fd_sc_hd__and3_1 _1142_ (.A(\core.next_random[1] ),
    .B(net51),
    .C(_0515_),
    .X(_0008_));
 sky130_fd_sc_hd__a21o_1 _1143_ (.A1(_0042_),
    .A2(_0046_),
    .B1(_0045_),
    .X(_0602_));
 sky130_fd_sc_hd__a21oi_1 _1144_ (.A1(_0048_),
    .A2(_0602_),
    .B1(_0047_),
    .Y(_0603_));
 sky130_fd_sc_hd__xor2_1 _1145_ (.A(_0057_),
    .B(_0603_),
    .X(_0060_));
 sky130_fd_sc_hd__a21o_1 _1146_ (.A1(_0043_),
    .A2(_0048_),
    .B1(_0047_),
    .X(_0604_));
 sky130_fd_sc_hd__a21oi_1 _1147_ (.A1(_0057_),
    .A2(_0604_),
    .B1(_0056_),
    .Y(_0605_));
 sky130_fd_sc_hd__xor2_1 _1148_ (.A(_0059_),
    .B(_0605_),
    .X(_0061_));
 sky130_fd_sc_hd__inv_1 _1149_ (.A(\core.score1.active_digit ),
    .Y(_0009_));
 sky130_fd_sc_hd__xnor2_1 _1150_ (.A(net2),
    .B(net4),
    .Y(_0606_));
 sky130_fd_sc_hd__nor3_1 _1151_ (.A(net1),
    .B(net3),
    .C(_0606_),
    .Y(_0213_));
 sky130_fd_sc_hd__nor3b_1 _1152_ (.A(net1),
    .B(net2),
    .C_N(_0574_),
    .Y(_0214_));
 sky130_fd_sc_hd__nand2b_1 _1153_ (.A_N(_0110_),
    .B(\core.millis_counter[2] ),
    .Y(_0607_));
 sky130_fd_sc_hd__nor2b_1 _1154_ (.A(\core.millis_counter[3] ),
    .B_N(_0607_),
    .Y(_0093_));
 sky130_fd_sc_hd__inv_1 _1155_ (.A(\core.tone_sequence_counter[0] ),
    .Y(_0096_));
 sky130_fd_sc_hd__and2_1 _1156_ (.A(\core.tone_sequence_counter[2] ),
    .B(_0098_),
    .X(_0608_));
 sky130_fd_sc_hd__nand2_1 _1158_ (.A(net48),
    .B(_0608_),
    .Y(_0610_));
 sky130_fd_sc_hd__nand2_1 _1160_ (.A(net7),
    .B(net47),
    .Y(_0612_));
 sky130_fd_sc_hd__a21oi_1 _1161_ (.A1(\core.tone_sequence_counter[0] ),
    .A2(_0610_),
    .B1(_0612_),
    .Y(_0215_));
 sky130_fd_sc_hd__a21oi_1 _1162_ (.A1(net48),
    .A2(_0608_),
    .B1(_0099_),
    .Y(_0613_));
 sky130_fd_sc_hd__nor2_1 _1163_ (.A(_0612_),
    .B(_0613_),
    .Y(_0216_));
 sky130_fd_sc_hd__a21oi_1 _1164_ (.A1(net48),
    .A2(_0608_),
    .B1(_0105_),
    .Y(_0614_));
 sky130_fd_sc_hd__nor2_1 _1165_ (.A(_0612_),
    .B(_0614_),
    .Y(_0217_));
 sky130_fd_sc_hd__inv_1 _1166_ (.A(\core.millis_counter[1] ),
    .Y(_0107_));
 sky130_fd_sc_hd__inv_1 _1167_ (.A(\core.user_input[0] ),
    .Y(_0085_));
 sky130_fd_sc_hd__inv_1 _1168_ (.A(\core.millis_counter[0] ),
    .Y(_0106_));
 sky130_fd_sc_hd__inv_1 _1169_ (.A(\core.tick_counter[1] ),
    .Y(_0051_));
 sky130_fd_sc_hd__inv_1 _1170_ (.A(\core.user_input[1] ),
    .Y(_0086_));
 sky130_fd_sc_hd__inv_1 _1171_ (.A(\core.tone_sequence_counter[1] ),
    .Y(_0097_));
 sky130_fd_sc_hd__o21a_1 _1173_ (.A1(\core.play1.tick_counter[4] ),
    .A2(\core.play1.tick_counter[3] ),
    .B1(\core.play1.tick_counter[5] ),
    .X(_0616_));
 sky130_fd_sc_hd__o211ai_1 _1174_ (.A1(\core.play1.tick_counter[6] ),
    .A2(_0616_),
    .B1(\core.play1.tick_counter[8] ),
    .C1(\core.play1.tick_counter[7] ),
    .Y(_0617_));
 sky130_fd_sc_hd__nor4_1 _1176_ (.A(\core.play1.tick_counter[12] ),
    .B(\core.play1.tick_counter[10] ),
    .C(\core.play1.tick_counter[11] ),
    .D(\core.play1.tick_counter[9] ),
    .Y(_0619_));
 sky130_fd_sc_hd__nand2_1 _1178_ (.A(\core.play1.tick_counter[14] ),
    .B(\core.play1.tick_counter[13] ),
    .Y(_0621_));
 sky130_fd_sc_hd__a21oi_1 _1179_ (.A1(_0617_),
    .A2(_0619_),
    .B1(_0621_),
    .Y(_0622_));
 sky130_fd_sc_hd__nor2_1 _1180_ (.A(\core.play1.tick_counter[20] ),
    .B(\core.play1.tick_counter[19] ),
    .Y(_0623_));
 sky130_fd_sc_hd__nor4_1 _1183_ (.A(\core.play1.tick_counter[28] ),
    .B(\core.play1.tick_counter[29] ),
    .C(\core.play1.tick_counter[27] ),
    .D(\core.play1.tick_counter[23] ),
    .Y(_0626_));
 sky130_fd_sc_hd__nor4_1 _1184_ (.A(\core.play1.tick_counter[31] ),
    .B(\core.play1.tick_counter[26] ),
    .C(\core.play1.tick_counter[25] ),
    .D(\core.play1.tick_counter[24] ),
    .Y(_0627_));
 sky130_fd_sc_hd__nor4_1 _1187_ (.A(\core.play1.tick_counter[22] ),
    .B(\core.play1.tick_counter[21] ),
    .C(\core.play1.tick_counter[18] ),
    .D(\core.play1.tick_counter[16] ),
    .Y(_0630_));
 sky130_fd_sc_hd__nand4_1 _1188_ (.A(_0623_),
    .B(_0626_),
    .C(_0627_),
    .D(_0630_),
    .Y(_0631_));
 sky130_fd_sc_hd__or3_1 _1189_ (.A(\core.play1.tick_counter[30] ),
    .B(\core.play1.tick_counter[17] ),
    .C(\core.play1.tick_counter[15] ),
    .X(_0632_));
 sky130_fd_sc_hd__or3_1 _1190_ (.A(_0622_),
    .B(_0631_),
    .C(_0632_),
    .X(_0633_));
 sky130_fd_sc_hd__xnor2_1 _1192_ (.A(net28),
    .B(_0633_),
    .Y(_0635_));
 sky130_fd_sc_hd__nor2_1 _1193_ (.A(\core.play1.freq[5] ),
    .B(\core.play1.freq[4] ),
    .Y(_0636_));
 sky130_fd_sc_hd__nor2_1 _1194_ (.A(\core.play1.freq[9] ),
    .B(\core.play1.freq[8] ),
    .Y(_0637_));
 sky130_fd_sc_hd__nor2_1 _1195_ (.A(\core.play1.freq[7] ),
    .B(\core.play1.freq[6] ),
    .Y(_0638_));
 sky130_fd_sc_hd__nor4_1 _1196_ (.A(\core.play1.freq[1] ),
    .B(\core.play1.freq[0] ),
    .C(\core.play1.freq[3] ),
    .D(\core.play1.freq[2] ),
    .Y(_0639_));
 sky130_fd_sc_hd__and4_1 _1197_ (.A(_0636_),
    .B(_0637_),
    .C(_0638_),
    .D(_0639_),
    .X(_0640_));
 sky130_fd_sc_hd__nor3_1 _1201_ (.A(net50),
    .B(_0635_),
    .C(net45),
    .Y(_0134_));
 sky130_fd_sc_hd__nand2b_1 _1202_ (.A_N(\core.score_rst ),
    .B(net51),
    .Y(_0644_));
 sky130_fd_sc_hd__nor2_1 _1204_ (.A(\core.score1.active_digit ),
    .B(_0644_),
    .Y(_0167_));
 sky130_fd_sc_hd__xnor2_1 _1205_ (.A(\core.score1.ones[0] ),
    .B(\core.score1.inc ),
    .Y(_0646_));
 sky130_fd_sc_hd__nor2_1 _1206_ (.A(_0644_),
    .B(_0646_),
    .Y(_0168_));
 sky130_fd_sc_hd__nand2_1 _1207_ (.A(\core.score1.ones[0] ),
    .B(\core.score1.inc ),
    .Y(_0647_));
 sky130_fd_sc_hd__nor2b_1 _1208_ (.A(\core.score1.ones[2] ),
    .B_N(\core.score1.ones[3] ),
    .Y(_0648_));
 sky130_fd_sc_hd__nor3_1 _1209_ (.A(\core.score1.ones[1] ),
    .B(_0647_),
    .C(_0648_),
    .Y(_0649_));
 sky130_fd_sc_hd__a21oi_1 _1210_ (.A1(\core.score1.ones[1] ),
    .A2(_0647_),
    .B1(_0649_),
    .Y(_0650_));
 sky130_fd_sc_hd__nor2_1 _1211_ (.A(_0644_),
    .B(_0650_),
    .Y(_0169_));
 sky130_fd_sc_hd__nand3_1 _1212_ (.A(\core.score1.ones[0] ),
    .B(\core.score1.ones[1] ),
    .C(\core.score1.inc ),
    .Y(_0651_));
 sky130_fd_sc_hd__xor2_1 _1213_ (.A(\core.score1.ones[2] ),
    .B(_0651_),
    .X(_0652_));
 sky130_fd_sc_hd__nor2_1 _1214_ (.A(_0644_),
    .B(_0652_),
    .Y(_0170_));
 sky130_fd_sc_hd__nor2b_1 _1215_ (.A(\core.score1.ones[1] ),
    .B_N(\core.score1.ones[2] ),
    .Y(_0653_));
 sky130_fd_sc_hd__o21ai_0 _1216_ (.A1(_0647_),
    .A2(_0653_),
    .B1(\core.score1.ones[3] ),
    .Y(_0654_));
 sky130_fd_sc_hd__nor3b_1 _1217_ (.A(\core.score1.ones[3] ),
    .B(_0647_),
    .C_N(\core.score1.ones[2] ),
    .Y(_0655_));
 sky130_fd_sc_hd__o21ai_0 _1218_ (.A1(_0648_),
    .A2(_0655_),
    .B1(\core.score1.ones[1] ),
    .Y(_0656_));
 sky130_fd_sc_hd__a21oi_1 _1219_ (.A1(_0654_),
    .A2(_0656_),
    .B1(_0644_),
    .Y(_0171_));
 sky130_fd_sc_hd__nor3b_1 _1220_ (.A(\core.score1.ones[1] ),
    .B(_0647_),
    .C_N(_0648_),
    .Y(_0657_));
 sky130_fd_sc_hd__xnor2_1 _1221_ (.A(\core.score1.tens[0] ),
    .B(_0657_),
    .Y(_0658_));
 sky130_fd_sc_hd__nor2_1 _1222_ (.A(_0644_),
    .B(_0658_),
    .Y(_0172_));
 sky130_fd_sc_hd__nand2_1 _1223_ (.A(\core.score1.tens[0] ),
    .B(_0657_),
    .Y(_0659_));
 sky130_fd_sc_hd__nor2b_1 _1224_ (.A(\core.score1.tens[2] ),
    .B_N(\core.score1.tens[3] ),
    .Y(_0660_));
 sky130_fd_sc_hd__nor3_1 _1225_ (.A(\core.score1.tens[1] ),
    .B(_0659_),
    .C(_0660_),
    .Y(_0661_));
 sky130_fd_sc_hd__a21oi_1 _1226_ (.A1(\core.score1.tens[1] ),
    .A2(_0659_),
    .B1(_0661_),
    .Y(_0662_));
 sky130_fd_sc_hd__nor2_1 _1227_ (.A(_0644_),
    .B(_0662_),
    .Y(_0173_));
 sky130_fd_sc_hd__nand3_1 _1228_ (.A(\core.score1.tens[0] ),
    .B(\core.score1.tens[1] ),
    .C(_0657_),
    .Y(_0663_));
 sky130_fd_sc_hd__xor2_1 _1229_ (.A(\core.score1.tens[2] ),
    .B(_0663_),
    .X(_0664_));
 sky130_fd_sc_hd__nor2_1 _1230_ (.A(_0644_),
    .B(_0664_),
    .Y(_0174_));
 sky130_fd_sc_hd__nor2b_1 _1231_ (.A(\core.score1.tens[1] ),
    .B_N(\core.score1.tens[2] ),
    .Y(_0665_));
 sky130_fd_sc_hd__o21ai_0 _1232_ (.A1(_0659_),
    .A2(_0665_),
    .B1(\core.score1.tens[3] ),
    .Y(_0666_));
 sky130_fd_sc_hd__nor3b_1 _1233_ (.A(\core.score1.tens[3] ),
    .B(_0659_),
    .C_N(\core.score1.tens[2] ),
    .Y(_0667_));
 sky130_fd_sc_hd__o21ai_0 _1234_ (.A1(_0660_),
    .A2(_0667_),
    .B1(\core.score1.tens[1] ),
    .Y(_0668_));
 sky130_fd_sc_hd__a21oi_1 _1235_ (.A1(_0666_),
    .A2(_0668_),
    .B1(_0644_),
    .Y(_0175_));
 sky130_fd_sc_hd__nor2_1 _1236_ (.A(\core.tick_counter[14] ),
    .B(\core.tick_counter[15] ),
    .Y(_0669_));
 sky130_fd_sc_hd__nor4_1 _1237_ (.A(\core.tick_counter[2] ),
    .B(\core.tick_counter[11] ),
    .C(\core.tick_counter[12] ),
    .D(\core.tick_counter[13] ),
    .Y(_0670_));
 sky130_fd_sc_hd__or4_1 _1238_ (.A(\core.tick_counter[6] ),
    .B(\core.tick_counter[7] ),
    .C(\core.tick_counter[8] ),
    .D(\core.tick_counter[9] ),
    .X(_0671_));
 sky130_fd_sc_hd__nand2_1 _1239_ (.A(\core.tick_counter[4] ),
    .B(\core.tick_counter[5] ),
    .Y(_0672_));
 sky130_fd_sc_hd__nor4_1 _1240_ (.A(\core.tick_counter[3] ),
    .B(\core.tick_counter[10] ),
    .C(_0671_),
    .D(_0672_),
    .Y(_0673_));
 sky130_fd_sc_hd__nand4_1 _1241_ (.A(_0052_),
    .B(_0669_),
    .C(_0670_),
    .D(_0673_),
    .Y(_0674_));
 sky130_fd_sc_hd__nand2_1 _1242_ (.A(net51),
    .B(_0674_),
    .Y(_0675_));
 sky130_fd_sc_hd__nor2_1 _1244_ (.A(\core.tick_counter[0] ),
    .B(_0675_),
    .Y(_0197_));
 sky130_fd_sc_hd__and3_1 _1245_ (.A(\core.tick_counter[5] ),
    .B(\core.tick_counter[6] ),
    .C(\core.tick_counter[7] ),
    .X(_0677_));
 sky130_fd_sc_hd__and3_1 _1246_ (.A(_0054_),
    .B(\core.tick_counter[2] ),
    .C(\core.tick_counter[3] ),
    .X(_0678_));
 sky130_fd_sc_hd__nand3_1 _1247_ (.A(\core.tick_counter[4] ),
    .B(_0677_),
    .C(_0678_),
    .Y(_0679_));
 sky130_fd_sc_hd__nand2_1 _1248_ (.A(\core.tick_counter[8] ),
    .B(\core.tick_counter[9] ),
    .Y(_0680_));
 sky130_fd_sc_hd__nor2_1 _1249_ (.A(_0679_),
    .B(_0680_),
    .Y(_0681_));
 sky130_fd_sc_hd__xnor2_1 _1250_ (.A(\core.tick_counter[10] ),
    .B(_0681_),
    .Y(_0682_));
 sky130_fd_sc_hd__nor2_1 _1251_ (.A(_0675_),
    .B(_0682_),
    .Y(_0198_));
 sky130_fd_sc_hd__nand3_1 _1252_ (.A(\core.tick_counter[2] ),
    .B(\core.tick_counter[3] ),
    .C(\core.tick_counter[4] ),
    .Y(_0683_));
 sky130_fd_sc_hd__nand2_1 _1253_ (.A(\core.tick_counter[0] ),
    .B(\core.tick_counter[1] ),
    .Y(_0684_));
 sky130_fd_sc_hd__nor2_1 _1254_ (.A(_0683_),
    .B(_0684_),
    .Y(_0685_));
 sky130_fd_sc_hd__and2_1 _1255_ (.A(_0677_),
    .B(_0685_),
    .X(_0686_));
 sky130_fd_sc_hd__and3_1 _1256_ (.A(\core.tick_counter[8] ),
    .B(\core.tick_counter[9] ),
    .C(\core.tick_counter[10] ),
    .X(_0687_));
 sky130_fd_sc_hd__nand2_1 _1257_ (.A(_0686_),
    .B(_0687_),
    .Y(_0688_));
 sky130_fd_sc_hd__xor2_1 _1258_ (.A(\core.tick_counter[11] ),
    .B(_0688_),
    .X(_0689_));
 sky130_fd_sc_hd__nor2_1 _1259_ (.A(_0675_),
    .B(_0689_),
    .Y(_0199_));
 sky130_fd_sc_hd__nand2_1 _1260_ (.A(\core.tick_counter[11] ),
    .B(_0687_),
    .Y(_0690_));
 sky130_fd_sc_hd__nor2_1 _1261_ (.A(_0679_),
    .B(_0690_),
    .Y(_0691_));
 sky130_fd_sc_hd__xnor2_1 _1262_ (.A(\core.tick_counter[12] ),
    .B(_0691_),
    .Y(_0692_));
 sky130_fd_sc_hd__nor2_1 _1263_ (.A(_0675_),
    .B(_0692_),
    .Y(_0200_));
 sky130_fd_sc_hd__nand4_1 _1264_ (.A(\core.tick_counter[11] ),
    .B(\core.tick_counter[12] ),
    .C(_0686_),
    .D(_0687_),
    .Y(_0693_));
 sky130_fd_sc_hd__xor2_1 _1265_ (.A(\core.tick_counter[13] ),
    .B(_0693_),
    .X(_0694_));
 sky130_fd_sc_hd__nor2_1 _1266_ (.A(_0675_),
    .B(_0694_),
    .Y(_0201_));
 sky130_fd_sc_hd__nand4_1 _1267_ (.A(\core.tick_counter[11] ),
    .B(\core.tick_counter[12] ),
    .C(\core.tick_counter[13] ),
    .D(_0687_),
    .Y(_0695_));
 sky130_fd_sc_hd__nor2_1 _1268_ (.A(_0679_),
    .B(_0695_),
    .Y(_0696_));
 sky130_fd_sc_hd__xnor2_1 _1269_ (.A(\core.tick_counter[14] ),
    .B(_0696_),
    .Y(_0697_));
 sky130_fd_sc_hd__nor2_1 _1270_ (.A(_0675_),
    .B(_0697_),
    .Y(_0202_));
 sky130_fd_sc_hd__nand2_1 _1271_ (.A(\core.tick_counter[14] ),
    .B(_0686_),
    .Y(_0698_));
 sky130_fd_sc_hd__o21ai_0 _1272_ (.A1(_0695_),
    .A2(_0698_),
    .B1(\core.tick_counter[15] ),
    .Y(_0699_));
 sky130_fd_sc_hd__or3_1 _1273_ (.A(\core.tick_counter[15] ),
    .B(_0695_),
    .C(_0698_),
    .X(_0700_));
 sky130_fd_sc_hd__a21oi_1 _1274_ (.A1(_0699_),
    .A2(_0700_),
    .B1(_0675_),
    .Y(_0203_));
 sky130_fd_sc_hd__nor2_1 _1275_ (.A(_0053_),
    .B(_0675_),
    .Y(_0204_));
 sky130_fd_sc_hd__xnor2_1 _1276_ (.A(_0054_),
    .B(\core.tick_counter[2] ),
    .Y(_0701_));
 sky130_fd_sc_hd__nor2_1 _1277_ (.A(_0675_),
    .B(_0701_),
    .Y(_0205_));
 sky130_fd_sc_hd__nand3_1 _1278_ (.A(\core.tick_counter[0] ),
    .B(\core.tick_counter[2] ),
    .C(\core.tick_counter[1] ),
    .Y(_0702_));
 sky130_fd_sc_hd__xor2_1 _1279_ (.A(\core.tick_counter[3] ),
    .B(_0702_),
    .X(_0703_));
 sky130_fd_sc_hd__nor2_1 _1280_ (.A(_0675_),
    .B(_0703_),
    .Y(_0206_));
 sky130_fd_sc_hd__xnor2_1 _1281_ (.A(\core.tick_counter[4] ),
    .B(_0678_),
    .Y(_0704_));
 sky130_fd_sc_hd__nor2_1 _1282_ (.A(_0675_),
    .B(_0704_),
    .Y(_0207_));
 sky130_fd_sc_hd__xnor2_1 _1283_ (.A(\core.tick_counter[5] ),
    .B(_0685_),
    .Y(_0705_));
 sky130_fd_sc_hd__nor2_1 _1284_ (.A(_0675_),
    .B(_0705_),
    .Y(_0208_));
 sky130_fd_sc_hd__nand3_1 _1285_ (.A(\core.tick_counter[4] ),
    .B(\core.tick_counter[5] ),
    .C(_0678_),
    .Y(_0706_));
 sky130_fd_sc_hd__xor2_1 _1286_ (.A(\core.tick_counter[6] ),
    .B(_0706_),
    .X(_0707_));
 sky130_fd_sc_hd__nor2_1 _1287_ (.A(_0675_),
    .B(_0707_),
    .Y(_0209_));
 sky130_fd_sc_hd__nand3_1 _1288_ (.A(\core.tick_counter[5] ),
    .B(\core.tick_counter[6] ),
    .C(_0685_),
    .Y(_0708_));
 sky130_fd_sc_hd__xor2_1 _1289_ (.A(\core.tick_counter[7] ),
    .B(_0708_),
    .X(_0709_));
 sky130_fd_sc_hd__nor2_1 _1290_ (.A(_0675_),
    .B(_0709_),
    .Y(_0210_));
 sky130_fd_sc_hd__xor2_1 _1291_ (.A(\core.tick_counter[8] ),
    .B(_0679_),
    .X(_0710_));
 sky130_fd_sc_hd__nor2_1 _1292_ (.A(_0675_),
    .B(_0710_),
    .Y(_0211_));
 sky130_fd_sc_hd__nand2_1 _1293_ (.A(\core.tick_counter[8] ),
    .B(_0686_),
    .Y(_0711_));
 sky130_fd_sc_hd__xor2_1 _1294_ (.A(\core.tick_counter[9] ),
    .B(_0711_),
    .X(_0712_));
 sky130_fd_sc_hd__nor2_1 _1295_ (.A(_0675_),
    .B(_0712_),
    .Y(_0212_));
 sky130_fd_sc_hd__nand3_1 _1297_ (.A(\core.seq_counter[0] ),
    .B(\core.seq_counter[2] ),
    .C(\core.seq_counter[1] ),
    .Y(_0714_));
 sky130_fd_sc_hd__nor2_1 _1298_ (.A(\core.seq_counter[4] ),
    .B(_0714_),
    .Y(_0715_));
 sky130_fd_sc_hd__mux2_2 _1299_ (.A0(_0714_),
    .A1(_0715_),
    .S(\core.seq_counter[3] ),
    .X(_0716_));
 sky130_fd_sc_hd__xor2_1 _1300_ (.A(\core.seq_counter[3] ),
    .B(_0714_),
    .X(_0717_));
 sky130_fd_sc_hd__nand2_1 _1301_ (.A(net17),
    .B(_0717_),
    .Y(_0718_));
 sky130_fd_sc_hd__xor2_1 _1302_ (.A(_0049_),
    .B(\core.seq_counter[2] ),
    .X(_0719_));
 sky130_fd_sc_hd__xnor2_1 _1303_ (.A(net16),
    .B(_0719_),
    .Y(_0720_));
 sky130_fd_sc_hd__nand3_1 _1304_ (.A(_0049_),
    .B(\core.seq_counter[2] ),
    .C(\core.seq_counter[3] ),
    .Y(_0721_));
 sky130_fd_sc_hd__xor2_1 _1305_ (.A(net18),
    .B(\core.seq_counter[4] ),
    .X(_0722_));
 sky130_fd_sc_hd__xnor2_1 _1306_ (.A(_0721_),
    .B(_0722_),
    .Y(_0723_));
 sky130_fd_sc_hd__xor2_1 _1307_ (.A(net15),
    .B(_0050_),
    .X(_0724_));
 sky130_fd_sc_hd__xnor2_1 _1308_ (.A(net14),
    .B(\core.seq_counter[0] ),
    .Y(_0725_));
 sky130_fd_sc_hd__nor3_1 _1309_ (.A(_0723_),
    .B(_0724_),
    .C(_0725_),
    .Y(_0726_));
 sky130_fd_sc_hd__o2111a_1 _1310_ (.A1(net17),
    .A2(_0716_),
    .B1(_0718_),
    .C1(_0720_),
    .D1(_0726_),
    .X(_0727_));
 sky130_fd_sc_hd__xnor2_1 _1311_ (.A(_0086_),
    .B(_0077_),
    .Y(_0728_));
 sky130_fd_sc_hd__xnor2_1 _1312_ (.A(_0085_),
    .B(_0076_),
    .Y(_0729_));
 sky130_fd_sc_hd__nand2_1 _1313_ (.A(_0728_),
    .B(_0729_),
    .Y(_0730_));
 sky130_fd_sc_hd__o311a_1 _1314_ (.A1(net7),
    .A2(_0727_),
    .A3(_0730_),
    .B1(net47),
    .C1(net48),
    .X(_0731_));
 sky130_fd_sc_hd__nor3_1 _1315_ (.A(_0560_),
    .B(_0561_),
    .C(_0562_),
    .Y(_0732_));
 sky130_fd_sc_hd__nand2b_1 _1316_ (.A_N(net8),
    .B(net7),
    .Y(_0733_));
 sky130_fd_sc_hd__nor4b_1 _1317_ (.A(\core.millis_counter[3] ),
    .B(\core.millis_counter[2] ),
    .C(_0560_),
    .D_N(_0566_),
    .Y(_0734_));
 sky130_fd_sc_hd__o22ai_1 _1318_ (.A1(_0497_),
    .A2(_0732_),
    .B1(_0733_),
    .B2(_0734_),
    .Y(_0735_));
 sky130_fd_sc_hd__a21o_1 _1319_ (.A1(net48),
    .A2(_0735_),
    .B1(_0570_),
    .X(_0736_));
 sky130_fd_sc_hd__a31oi_1 _1320_ (.A1(\core.tone_sequence_counter[2] ),
    .A2(\core.tone_sequence_counter[1] ),
    .A3(\core.tone_sequence_counter[0] ),
    .B1(_0569_),
    .Y(_0737_));
 sky130_fd_sc_hd__or2_2 _1321_ (.A(_0736_),
    .B(_0737_),
    .X(_0738_));
 sky130_fd_sc_hd__nor2_1 _1322_ (.A(net48),
    .B(_0558_),
    .Y(_0739_));
 sky130_fd_sc_hd__nor3_1 _1323_ (.A(_0731_),
    .B(_0738_),
    .C(_0739_),
    .Y(_0740_));
 sky130_fd_sc_hd__o21ai_0 _1324_ (.A1(_0727_),
    .A2(_0733_),
    .B1(_0497_),
    .Y(_0741_));
 sky130_fd_sc_hd__and2_1 _1325_ (.A(net48),
    .B(_0741_),
    .X(_0742_));
 sky130_fd_sc_hd__nand2_1 _1327_ (.A(_0740_),
    .B(_0742_),
    .Y(_0744_));
 sky130_fd_sc_hd__mux2_2 _1328_ (.A0(_0744_),
    .A1(_0740_),
    .S(\core.seq_counter[0] ),
    .X(_0745_));
 sky130_fd_sc_hd__nor2_1 _1329_ (.A(net50),
    .B(_0745_),
    .Y(_0113_));
 sky130_fd_sc_hd__nor2b_1 _1330_ (.A(_0740_),
    .B_N(\core.seq_counter[1] ),
    .Y(_0746_));
 sky130_fd_sc_hd__a31oi_1 _1331_ (.A1(_0050_),
    .A2(_0740_),
    .A3(_0742_),
    .B1(_0746_),
    .Y(_0747_));
 sky130_fd_sc_hd__nor2_1 _1332_ (.A(net50),
    .B(_0747_),
    .Y(_0114_));
 sky130_fd_sc_hd__inv_1 _1333_ (.A(_0742_),
    .Y(_0748_));
 sky130_fd_sc_hd__o21ai_0 _1334_ (.A1(_0049_),
    .A2(_0748_),
    .B1(_0740_),
    .Y(_0749_));
 sky130_fd_sc_hd__nand2_1 _1335_ (.A(\core.seq_counter[2] ),
    .B(_0749_),
    .Y(_0750_));
 sky130_fd_sc_hd__nand4b_1 _1336_ (.A_N(\core.seq_counter[2] ),
    .B(_0740_),
    .C(_0742_),
    .D(_0049_),
    .Y(_0751_));
 sky130_fd_sc_hd__a21oi_1 _1338_ (.A1(_0750_),
    .A2(_0751_),
    .B1(net50),
    .Y(_0115_));
 sky130_fd_sc_hd__nand2_1 _1339_ (.A(_0714_),
    .B(_0742_),
    .Y(_0753_));
 sky130_fd_sc_hd__a21boi_0 _1340_ (.A1(_0740_),
    .A2(_0753_),
    .B1_N(\core.seq_counter[3] ),
    .Y(_0754_));
 sky130_fd_sc_hd__nor3_1 _1341_ (.A(\core.seq_counter[3] ),
    .B(_0714_),
    .C(_0744_),
    .Y(_0755_));
 sky130_fd_sc_hd__o21a_1 _1343_ (.A1(_0754_),
    .A2(_0755_),
    .B1(net51),
    .X(_0116_));
 sky130_fd_sc_hd__nand2_1 _1344_ (.A(_0721_),
    .B(_0742_),
    .Y(_0757_));
 sky130_fd_sc_hd__a21boi_0 _1345_ (.A1(_0740_),
    .A2(_0757_),
    .B1_N(\core.seq_counter[4] ),
    .Y(_0758_));
 sky130_fd_sc_hd__nor3_1 _1346_ (.A(\core.seq_counter[4] ),
    .B(_0721_),
    .C(_0744_),
    .Y(_0759_));
 sky130_fd_sc_hd__o21a_1 _1347_ (.A1(_0758_),
    .A2(_0759_),
    .B1(net51),
    .X(_0117_));
 sky130_fd_sc_hd__nand3b_1 _1348_ (.A_N(net7),
    .B(net47),
    .C(net48),
    .Y(_0760_));
 sky130_fd_sc_hd__nor2_1 _1349_ (.A(\core.user_input[0] ),
    .B(_0760_),
    .Y(_0761_));
 sky130_fd_sc_hd__a21oi_1 _1350_ (.A1(_0076_),
    .A2(_0760_),
    .B1(_0761_),
    .Y(_0762_));
 sky130_fd_sc_hd__inv_1 _1351_ (.A(_0087_),
    .Y(_0763_));
 sky130_fd_sc_hd__nor2_1 _1352_ (.A(_0763_),
    .B(_0760_),
    .Y(_0764_));
 sky130_fd_sc_hd__a21oi_1 _1353_ (.A1(_0078_),
    .A2(_0760_),
    .B1(_0764_),
    .Y(_0765_));
 sky130_fd_sc_hd__or3b_2 _1354_ (.A(net48),
    .B(net47),
    .C_N(net7),
    .X(_0766_));
 sky130_fd_sc_hd__o22a_1 _1355_ (.A1(_0088_),
    .A2(_0760_),
    .B1(_0766_),
    .B2(_0079_),
    .X(_0767_));
 sky130_fd_sc_hd__or3_1 _1356_ (.A(_0762_),
    .B(_0765_),
    .C(_0767_),
    .X(_0768_));
 sky130_fd_sc_hd__or4_1 _1357_ (.A(net1),
    .B(net2),
    .C(net3),
    .D(net4),
    .X(_0769_));
 sky130_fd_sc_hd__nand2_1 _1358_ (.A(_0104_),
    .B(_0769_),
    .Y(_0770_));
 sky130_fd_sc_hd__and2_1 _1359_ (.A(net9),
    .B(_0770_),
    .X(_0771_));
 sky130_fd_sc_hd__nand2b_1 _1360_ (.A_N(net47),
    .B(net48),
    .Y(_0772_));
 sky130_fd_sc_hd__a21o_1 _1361_ (.A1(net7),
    .A2(_0732_),
    .B1(_0772_),
    .X(_0773_));
 sky130_fd_sc_hd__a21boi_0 _1362_ (.A1(\core.millis_counter[7] ),
    .A2(_0771_),
    .B1_N(_0773_),
    .Y(_0774_));
 sky130_fd_sc_hd__or2_2 _1363_ (.A(net7),
    .B(net47),
    .X(_0775_));
 sky130_fd_sc_hd__nor2_1 _1364_ (.A(_0769_),
    .B(_0775_),
    .Y(_0776_));
 sky130_fd_sc_hd__o21ai_0 _1365_ (.A1(\core.millis_counter[8] ),
    .A2(\core.millis_counter[9] ),
    .B1(_0776_),
    .Y(_0777_));
 sky130_fd_sc_hd__o21ai_0 _1366_ (.A1(net10),
    .A2(_0773_),
    .B1(net51),
    .Y(_0778_));
 sky130_fd_sc_hd__a31oi_1 _1367_ (.A1(_0768_),
    .A2(_0774_),
    .A3(_0777_),
    .B1(_0778_),
    .Y(_0118_));
 sky130_fd_sc_hd__inv_1 _1368_ (.A(_0088_),
    .Y(_0779_));
 sky130_fd_sc_hd__inv_1 _1369_ (.A(_0079_),
    .Y(_0780_));
 sky130_fd_sc_hd__o22ai_1 _1370_ (.A1(_0779_),
    .A2(_0760_),
    .B1(_0766_),
    .B2(_0780_),
    .Y(_0781_));
 sky130_fd_sc_hd__and2_1 _1371_ (.A(_0765_),
    .B(_0781_),
    .X(_0782_));
 sky130_fd_sc_hd__nand2_1 _1372_ (.A(_0762_),
    .B(_0782_),
    .Y(_0783_));
 sky130_fd_sc_hd__inv_1 _1373_ (.A(\core.millis_counter[8] ),
    .Y(_0784_));
 sky130_fd_sc_hd__o21ai_0 _1374_ (.A1(_0784_),
    .A2(\core.millis_counter[9] ),
    .B1(_0776_),
    .Y(_0785_));
 sky130_fd_sc_hd__o21ai_0 _1375_ (.A1(net11),
    .A2(_0773_),
    .B1(net51),
    .Y(_0786_));
 sky130_fd_sc_hd__a31oi_1 _1376_ (.A1(_0774_),
    .A2(_0783_),
    .A3(_0785_),
    .B1(_0786_),
    .Y(_0119_));
 sky130_fd_sc_hd__nand2b_1 _1377_ (.A_N(_0762_),
    .B(_0782_),
    .Y(_0787_));
 sky130_fd_sc_hd__inv_1 _1378_ (.A(\core.millis_counter[9] ),
    .Y(_0788_));
 sky130_fd_sc_hd__o21ai_0 _1379_ (.A1(\core.millis_counter[8] ),
    .A2(_0788_),
    .B1(_0776_),
    .Y(_0789_));
 sky130_fd_sc_hd__o21ai_0 _1380_ (.A1(net12),
    .A2(_0773_),
    .B1(net51),
    .Y(_0790_));
 sky130_fd_sc_hd__a31oi_1 _1381_ (.A1(_0774_),
    .A2(_0787_),
    .A3(_0789_),
    .B1(_0790_),
    .Y(_0120_));
 sky130_fd_sc_hd__nand3b_1 _1382_ (.A_N(_0767_),
    .B(_0765_),
    .C(_0762_),
    .Y(_0791_));
 sky130_fd_sc_hd__nand2_1 _1383_ (.A(_0553_),
    .B(_0776_),
    .Y(_0792_));
 sky130_fd_sc_hd__o21ai_0 _1384_ (.A1(net13),
    .A2(_0773_),
    .B1(net51),
    .Y(_0793_));
 sky130_fd_sc_hd__a31oi_1 _1385_ (.A1(_0774_),
    .A2(_0791_),
    .A3(_0792_),
    .B1(_0793_),
    .Y(_0121_));
 sky130_fd_sc_hd__nor2_1 _1386_ (.A(net48),
    .B(_0495_),
    .Y(_0794_));
 sky130_fd_sc_hd__nor2_1 _1387_ (.A(_0794_),
    .B(_0775_),
    .Y(_0795_));
 sky130_fd_sc_hd__nand2_1 _1388_ (.A(net9),
    .B(_0770_),
    .Y(_0796_));
 sky130_fd_sc_hd__a21oi_1 _1389_ (.A1(_0564_),
    .A2(_0732_),
    .B1(_0796_),
    .Y(_0797_));
 sky130_fd_sc_hd__o2111ai_1 _1390_ (.A1(net17),
    .A2(_0716_),
    .B1(_0718_),
    .C1(_0720_),
    .D1(_0726_),
    .Y(_0798_));
 sky130_fd_sc_hd__o21ai_0 _1391_ (.A1(_0497_),
    .A2(_0730_),
    .B1(_0733_),
    .Y(_0799_));
 sky130_fd_sc_hd__and3_1 _1392_ (.A(net48),
    .B(_0798_),
    .C(_0799_),
    .X(_0800_));
 sky130_fd_sc_hd__o41ai_2 _1393_ (.A1(_0736_),
    .A2(_0795_),
    .A3(_0797_),
    .A4(_0800_),
    .B1(net51),
    .Y(_0801_));
 sky130_fd_sc_hd__xnor2_1 _1394_ (.A(_0106_),
    .B(_0674_),
    .Y(_0802_));
 sky130_fd_sc_hd__nor2_1 _1395_ (.A(net39),
    .B(_0802_),
    .Y(_0122_));
 sky130_fd_sc_hd__nand2_1 _1396_ (.A(\core.millis_counter[1] ),
    .B(_0674_),
    .Y(_0803_));
 sky130_fd_sc_hd__inv_1 _1397_ (.A(_0674_),
    .Y(_0804_));
 sky130_fd_sc_hd__nand2_1 _1398_ (.A(_0109_),
    .B(_0804_),
    .Y(_0805_));
 sky130_fd_sc_hd__a21oi_1 _1399_ (.A1(_0803_),
    .A2(_0805_),
    .B1(net39),
    .Y(_0123_));
 sky130_fd_sc_hd__nand2_1 _1400_ (.A(_0112_),
    .B(_0804_),
    .Y(_0806_));
 sky130_fd_sc_hd__xor2_1 _1401_ (.A(\core.millis_counter[2] ),
    .B(_0806_),
    .X(_0807_));
 sky130_fd_sc_hd__nor2_1 _1402_ (.A(net39),
    .B(_0807_),
    .Y(_0124_));
 sky130_fd_sc_hd__nand4_1 _1403_ (.A(\core.millis_counter[2] ),
    .B(\core.millis_counter[0] ),
    .C(\core.millis_counter[1] ),
    .D(_0804_),
    .Y(_0808_));
 sky130_fd_sc_hd__xor2_1 _1404_ (.A(\core.millis_counter[3] ),
    .B(_0808_),
    .X(_0809_));
 sky130_fd_sc_hd__nor2_1 _1405_ (.A(net39),
    .B(_0809_),
    .Y(_0125_));
 sky130_fd_sc_hd__nor2_1 _1406_ (.A(_0561_),
    .B(_0806_),
    .Y(_0810_));
 sky130_fd_sc_hd__xnor2_1 _1407_ (.A(\core.millis_counter[4] ),
    .B(_0810_),
    .Y(_0811_));
 sky130_fd_sc_hd__nor2_1 _1408_ (.A(net39),
    .B(_0811_),
    .Y(_0126_));
 sky130_fd_sc_hd__nand3_1 _1409_ (.A(\core.millis_counter[3] ),
    .B(\core.millis_counter[2] ),
    .C(\core.millis_counter[4] ),
    .Y(_0812_));
 sky130_fd_sc_hd__nor4_1 _1410_ (.A(_0106_),
    .B(_0107_),
    .C(_0674_),
    .D(_0812_),
    .Y(_0813_));
 sky130_fd_sc_hd__xnor2_1 _1411_ (.A(\core.millis_counter[5] ),
    .B(_0813_),
    .Y(_0814_));
 sky130_fd_sc_hd__nor2_1 _1412_ (.A(net39),
    .B(_0814_),
    .Y(_0127_));
 sky130_fd_sc_hd__nor2_1 _1413_ (.A(_0806_),
    .B(_0812_),
    .Y(_0815_));
 sky130_fd_sc_hd__nand2_1 _1414_ (.A(\core.millis_counter[5] ),
    .B(_0815_),
    .Y(_0816_));
 sky130_fd_sc_hd__xor2_1 _1415_ (.A(\core.millis_counter[6] ),
    .B(_0816_),
    .X(_0817_));
 sky130_fd_sc_hd__nor2_1 _1416_ (.A(net39),
    .B(_0817_),
    .Y(_0128_));
 sky130_fd_sc_hd__nand3_1 _1417_ (.A(\core.millis_counter[5] ),
    .B(\core.millis_counter[6] ),
    .C(_0813_),
    .Y(_0818_));
 sky130_fd_sc_hd__xor2_1 _1418_ (.A(\core.millis_counter[7] ),
    .B(_0818_),
    .X(_0819_));
 sky130_fd_sc_hd__nor2_1 _1419_ (.A(net39),
    .B(_0819_),
    .Y(_0129_));
 sky130_fd_sc_hd__or3_1 _1420_ (.A(_0552_),
    .B(_0806_),
    .C(_0812_),
    .X(_0820_));
 sky130_fd_sc_hd__xnor2_1 _1421_ (.A(_0784_),
    .B(_0820_),
    .Y(_0821_));
 sky130_fd_sc_hd__nor2_1 _1422_ (.A(net39),
    .B(_0821_),
    .Y(_0130_));
 sky130_fd_sc_hd__or3b_2 _1423_ (.A(_0784_),
    .B(_0552_),
    .C_N(_0813_),
    .X(_0822_));
 sky130_fd_sc_hd__xnor2_1 _1424_ (.A(_0788_),
    .B(_0822_),
    .Y(_0823_));
 sky130_fd_sc_hd__nor2_1 _1425_ (.A(net39),
    .B(_0823_),
    .Y(_0131_));
 sky130_fd_sc_hd__nor2_1 _1426_ (.A(\core.next_random[0] ),
    .B(net50),
    .Y(_0132_));
 sky130_fd_sc_hd__xnor2_1 _1427_ (.A(\core.next_random[0] ),
    .B(\core.next_random[1] ),
    .Y(_0824_));
 sky130_fd_sc_hd__nor2_1 _1428_ (.A(net50),
    .B(_0824_),
    .Y(_0133_));
 sky130_fd_sc_hd__nand2_1 _1429_ (.A(\core.play1.tick_counter[0] ),
    .B(net45),
    .Y(_0825_));
 sky130_fd_sc_hd__nand4_1 _1430_ (.A(_0636_),
    .B(_0637_),
    .C(_0638_),
    .D(_0639_),
    .Y(_0826_));
 sky130_fd_sc_hd__nand2_1 _1432_ (.A(_0055_),
    .B(net44),
    .Y(_0828_));
 sky130_fd_sc_hd__a21oi_1 _1433_ (.A1(_0825_),
    .A2(_0828_),
    .B1(net50),
    .Y(_0135_));
 sky130_fd_sc_hd__a21o_1 _1434_ (.A1(_0059_),
    .A2(_0056_),
    .B1(_0058_),
    .X(_0829_));
 sky130_fd_sc_hd__and3_1 _1435_ (.A(_0057_),
    .B(_0059_),
    .C(_0065_),
    .X(_0830_));
 sky130_fd_sc_hd__a221o_1 _1436_ (.A1(_0065_),
    .A2(_0829_),
    .B1(_0830_),
    .B2(_0604_),
    .C1(_0064_),
    .X(_0831_));
 sky130_fd_sc_hd__and4_1 _1439_ (.A(_0067_),
    .B(_0069_),
    .C(_0071_),
    .D(_0073_),
    .X(_0834_));
 sky130_fd_sc_hd__nand2_1 _1440_ (.A(_0071_),
    .B(_0073_),
    .Y(_0835_));
 sky130_fd_sc_hd__a21oi_1 _1441_ (.A1(_0069_),
    .A2(_0066_),
    .B1(_0068_),
    .Y(_0836_));
 sky130_fd_sc_hd__a21o_1 _1442_ (.A1(_0073_),
    .A2(_0070_),
    .B1(_0072_),
    .X(_0837_));
 sky130_fd_sc_hd__o21bai_1 _1443_ (.A1(_0835_),
    .A2(_0836_),
    .B1_N(_0837_),
    .Y(_0838_));
 sky130_fd_sc_hd__a21o_1 _1444_ (.A1(_0831_),
    .A2(_0834_),
    .B1(_0838_),
    .X(_0839_));
 sky130_fd_sc_hd__a31oi_1 _1445_ (.A1(_0057_),
    .A2(_0059_),
    .A3(_0047_),
    .B1(_0829_),
    .Y(_0840_));
 sky130_fd_sc_hd__nand4_1 _1446_ (.A(_0048_),
    .B(_0057_),
    .C(_0059_),
    .D(_0602_),
    .Y(_0841_));
 sky130_fd_sc_hd__a21boi_0 _1447_ (.A1(_0840_),
    .A2(_0841_),
    .B1_N(_0065_),
    .Y(_0842_));
 sky130_fd_sc_hd__a31o_1 _1448_ (.A1(_0057_),
    .A2(_0059_),
    .A3(_0047_),
    .B1(_0829_),
    .X(_0843_));
 sky130_fd_sc_hd__and4_1 _1449_ (.A(_0048_),
    .B(_0057_),
    .C(_0059_),
    .D(_0602_),
    .X(_0844_));
 sky130_fd_sc_hd__nor3_1 _1450_ (.A(_0065_),
    .B(_0843_),
    .C(_0844_),
    .Y(_0845_));
 sky130_fd_sc_hd__a211oi_1 _1451_ (.A1(_0060_),
    .A2(_0061_),
    .B1(_0842_),
    .C1(_0845_),
    .Y(_0846_));
 sky130_fd_sc_hd__a221oi_1 _1452_ (.A1(_0065_),
    .A2(_0829_),
    .B1(_0830_),
    .B2(_0604_),
    .C1(_0064_),
    .Y(_0847_));
 sky130_fd_sc_hd__xnor2_1 _1453_ (.A(_0067_),
    .B(_0847_),
    .Y(_0848_));
 sky130_fd_sc_hd__nand2_1 _1454_ (.A(_0067_),
    .B(_0069_),
    .Y(_0849_));
 sky130_fd_sc_hd__o21ai_0 _1455_ (.A1(_0847_),
    .A2(_0849_),
    .B1(_0836_),
    .Y(_0850_));
 sky130_fd_sc_hd__xor2_1 _1456_ (.A(_0071_),
    .B(_0850_),
    .X(_0851_));
 sky130_fd_sc_hd__a21o_1 _1457_ (.A1(_0067_),
    .A2(_0064_),
    .B1(_0066_),
    .X(_0852_));
 sky130_fd_sc_hd__nand2_1 _1458_ (.A(_0067_),
    .B(_0065_),
    .Y(_0853_));
 sky130_fd_sc_hd__a21oi_1 _1459_ (.A1(_0840_),
    .A2(_0841_),
    .B1(_0853_),
    .Y(_0854_));
 sky130_fd_sc_hd__o21ai_0 _1460_ (.A1(_0852_),
    .A2(_0854_),
    .B1(_0069_),
    .Y(_0855_));
 sky130_fd_sc_hd__or3_1 _1461_ (.A(_0069_),
    .B(_0852_),
    .C(_0854_),
    .X(_0856_));
 sky130_fd_sc_hd__o2111ai_1 _1462_ (.A1(_0846_),
    .A2(_0848_),
    .B1(_0851_),
    .C1(_0855_),
    .D1(_0856_),
    .Y(_0857_));
 sky130_fd_sc_hd__nor3_1 _1463_ (.A(_0622_),
    .B(_0631_),
    .C(_0632_),
    .Y(_0858_));
 sky130_fd_sc_hd__and4_1 _1464_ (.A(_0067_),
    .B(_0065_),
    .C(_0069_),
    .D(_0071_),
    .X(_0859_));
 sky130_fd_sc_hd__o21ai_0 _1465_ (.A1(_0843_),
    .A2(_0844_),
    .B1(_0859_),
    .Y(_0860_));
 sky130_fd_sc_hd__inv_1 _1466_ (.A(_0073_),
    .Y(_0861_));
 sky130_fd_sc_hd__a21oi_1 _1467_ (.A1(_0071_),
    .A2(_0068_),
    .B1(_0070_),
    .Y(_0862_));
 sky130_fd_sc_hd__nand3_1 _1468_ (.A(_0069_),
    .B(_0071_),
    .C(_0852_),
    .Y(_0863_));
 sky130_fd_sc_hd__and3_1 _1469_ (.A(_0861_),
    .B(_0862_),
    .C(_0863_),
    .X(_0864_));
 sky130_fd_sc_hd__nand3_1 _1470_ (.A(_0069_),
    .B(_0071_),
    .C(_0073_),
    .Y(_0865_));
 sky130_fd_sc_hd__a21oi_1 _1471_ (.A1(_0067_),
    .A2(_0064_),
    .B1(_0066_),
    .Y(_0866_));
 sky130_fd_sc_hd__o22ai_1 _1472_ (.A1(_0865_),
    .A2(_0866_),
    .B1(_0862_),
    .B2(_0861_),
    .Y(_0867_));
 sky130_fd_sc_hd__nor2_1 _1473_ (.A(_0865_),
    .B(_0853_),
    .Y(_0868_));
 sky130_fd_sc_hd__a21boi_1 _1474_ (.A1(_0840_),
    .A2(_0841_),
    .B1_N(_0868_),
    .Y(_0869_));
 sky130_fd_sc_hd__a211oi_1 _1475_ (.A1(_0860_),
    .A2(_0864_),
    .B1(_0867_),
    .C1(_0869_),
    .Y(_0870_));
 sky130_fd_sc_hd__nor2_1 _1476_ (.A(net43),
    .B(_0870_),
    .Y(_0871_));
 sky130_fd_sc_hd__and3_1 _1477_ (.A(_0839_),
    .B(_0857_),
    .C(_0871_),
    .X(_0872_));
 sky130_fd_sc_hd__a21oi_1 _1478_ (.A1(_0857_),
    .A2(_0871_),
    .B1(_0839_),
    .Y(_0873_));
 sky130_fd_sc_hd__nor3_1 _1479_ (.A(net45),
    .B(_0872_),
    .C(_0873_),
    .Y(_0874_));
 sky130_fd_sc_hd__xnor2_1 _1480_ (.A(\core.play1.tick_counter[10] ),
    .B(_0874_),
    .Y(_0875_));
 sky130_fd_sc_hd__nor2_1 _1481_ (.A(net50),
    .B(_0875_),
    .Y(_0136_));
 sky130_fd_sc_hd__inv_1 _1482_ (.A(\core.play1.tick_counter[11] ),
    .Y(_0876_));
 sky130_fd_sc_hd__nor3_1 _1483_ (.A(_0062_),
    .B(_0842_),
    .C(_0845_),
    .Y(_0877_));
 sky130_fd_sc_hd__o2111ai_1 _1484_ (.A1(_0848_),
    .A2(_0877_),
    .B1(_0856_),
    .C1(_0855_),
    .D1(_0851_),
    .Y(_0878_));
 sky130_fd_sc_hd__a21oi_1 _1485_ (.A1(_0836_),
    .A2(_0849_),
    .B1(_0835_),
    .Y(_0879_));
 sky130_fd_sc_hd__nand2_1 _1486_ (.A(\core.play1.tick_counter[10] ),
    .B(_0838_),
    .Y(_0880_));
 sky130_fd_sc_hd__a21o_1 _1487_ (.A1(_0069_),
    .A2(_0066_),
    .B1(_0068_),
    .X(_0881_));
 sky130_fd_sc_hd__or3_1 _1488_ (.A(\core.play1.tick_counter[10] ),
    .B(_0837_),
    .C(_0881_),
    .X(_0882_));
 sky130_fd_sc_hd__nand2_1 _1489_ (.A(\core.play1.tick_counter[10] ),
    .B(_0834_),
    .Y(_0883_));
 sky130_fd_sc_hd__mux2_4 _1490_ (.A0(_0882_),
    .A1(_0883_),
    .S(_0831_),
    .X(_0884_));
 sky130_fd_sc_hd__o311a_2 _1491_ (.A1(\core.play1.tick_counter[10] ),
    .A2(_0837_),
    .A3(_0879_),
    .B1(_0880_),
    .C1(_0884_),
    .X(_0885_));
 sky130_fd_sc_hd__nor3_1 _1492_ (.A(net43),
    .B(_0870_),
    .C(_0885_),
    .Y(_0886_));
 sky130_fd_sc_hd__o21ai_1 _1493_ (.A1(_0843_),
    .A2(_0844_),
    .B1(_0868_),
    .Y(_0887_));
 sky130_fd_sc_hd__nor2_1 _1494_ (.A(_0072_),
    .B(_0867_),
    .Y(_0888_));
 sky130_fd_sc_hd__nand2_1 _1495_ (.A(_0887_),
    .B(_0888_),
    .Y(_0889_));
 sky130_fd_sc_hd__nand2_1 _1496_ (.A(\core.play1.tick_counter[10] ),
    .B(_0889_),
    .Y(_0890_));
 sky130_fd_sc_hd__a21oi_1 _1497_ (.A1(_0878_),
    .A2(_0886_),
    .B1(_0890_),
    .Y(_0891_));
 sky130_fd_sc_hd__and3_1 _1498_ (.A(_0890_),
    .B(_0878_),
    .C(_0886_),
    .X(_0892_));
 sky130_fd_sc_hd__o21ai_0 _1500_ (.A1(_0891_),
    .A2(_0892_),
    .B1(net44),
    .Y(_0894_));
 sky130_fd_sc_hd__xnor2_1 _1501_ (.A(_0876_),
    .B(_0894_),
    .Y(_0895_));
 sky130_fd_sc_hd__nor2_1 _1502_ (.A(net50),
    .B(_0895_),
    .Y(_0137_));
 sky130_fd_sc_hd__nand3_1 _1503_ (.A(\core.play1.tick_counter[10] ),
    .B(\core.play1.tick_counter[11] ),
    .C(_0839_),
    .Y(_0896_));
 sky130_fd_sc_hd__nor2b_1 _1504_ (.A(\core.play1.tick_counter[11] ),
    .B_N(\core.play1.tick_counter[10] ),
    .Y(_0897_));
 sky130_fd_sc_hd__or3_1 _1505_ (.A(_0876_),
    .B(_0072_),
    .C(_0867_),
    .X(_0898_));
 sky130_fd_sc_hd__o22ai_1 _1506_ (.A1(\core.play1.tick_counter[10] ),
    .A2(_0876_),
    .B1(_0869_),
    .B2(_0898_),
    .Y(_0899_));
 sky130_fd_sc_hd__a2111oi_4 _1507_ (.A1(_0889_),
    .A2(_0897_),
    .B1(_0899_),
    .C1(_0885_),
    .D1(_0870_),
    .Y(_0900_));
 sky130_fd_sc_hd__nand3_1 _1508_ (.A(_0633_),
    .B(_0857_),
    .C(_0900_),
    .Y(_0901_));
 sky130_fd_sc_hd__xnor2_1 _1509_ (.A(_0896_),
    .B(_0901_),
    .Y(_0902_));
 sky130_fd_sc_hd__o21ai_0 _1510_ (.A1(net45),
    .A2(_0902_),
    .B1(\core.play1.tick_counter[12] ),
    .Y(_0903_));
 sky130_fd_sc_hd__or3_1 _1512_ (.A(\core.play1.tick_counter[12] ),
    .B(net45),
    .C(_0902_),
    .X(_0905_));
 sky130_fd_sc_hd__a21oi_1 _1513_ (.A1(_0903_),
    .A2(_0905_),
    .B1(net50),
    .Y(_0138_));
 sky130_fd_sc_hd__or2_2 _1514_ (.A(_0072_),
    .B(_0867_),
    .X(_0906_));
 sky130_fd_sc_hd__nor2_1 _1515_ (.A(_0869_),
    .B(_0906_),
    .Y(_0907_));
 sky130_fd_sc_hd__nand3_1 _1516_ (.A(\core.play1.tick_counter[12] ),
    .B(\core.play1.tick_counter[10] ),
    .C(\core.play1.tick_counter[11] ),
    .Y(_0908_));
 sky130_fd_sc_hd__nor2_1 _1517_ (.A(_0907_),
    .B(_0908_),
    .Y(_0909_));
 sky130_fd_sc_hd__a31oi_1 _1518_ (.A1(\core.play1.tick_counter[10] ),
    .A2(\core.play1.tick_counter[11] ),
    .A3(_0839_),
    .B1(\core.play1.tick_counter[12] ),
    .Y(_0910_));
 sky130_fd_sc_hd__and3_1 _1519_ (.A(\core.play1.tick_counter[12] ),
    .B(\core.play1.tick_counter[10] ),
    .C(\core.play1.tick_counter[11] ),
    .X(_0911_));
 sky130_fd_sc_hd__nand2_1 _1521_ (.A(_0839_),
    .B(_0911_),
    .Y(_0913_));
 sky130_fd_sc_hd__nand2b_1 _1522_ (.A_N(_0910_),
    .B(_0913_),
    .Y(_0914_));
 sky130_fd_sc_hd__a31oi_1 _1523_ (.A1(_0878_),
    .A2(_0900_),
    .A3(_0914_),
    .B1(net43),
    .Y(_0915_));
 sky130_fd_sc_hd__xnor2_1 _1524_ (.A(_0909_),
    .B(_0915_),
    .Y(_0916_));
 sky130_fd_sc_hd__o21ai_0 _1525_ (.A1(net45),
    .A2(_0916_),
    .B1(\core.play1.tick_counter[13] ),
    .Y(_0917_));
 sky130_fd_sc_hd__or3_1 _1526_ (.A(\core.play1.tick_counter[13] ),
    .B(net45),
    .C(_0916_),
    .X(_0918_));
 sky130_fd_sc_hd__a21oi_1 _1527_ (.A1(_0917_),
    .A2(_0918_),
    .B1(net50),
    .Y(_0139_));
 sky130_fd_sc_hd__o21ai_0 _1528_ (.A1(_0907_),
    .A2(_0908_),
    .B1(_0633_),
    .Y(_0919_));
 sky130_fd_sc_hd__nor2_1 _1529_ (.A(\core.play1.tick_counter[13] ),
    .B(_0913_),
    .Y(_0920_));
 sky130_fd_sc_hd__o211ai_1 _1530_ (.A1(_0910_),
    .A2(_0920_),
    .B1(_0857_),
    .C1(_0900_),
    .Y(_0921_));
 sky130_fd_sc_hd__a21oi_1 _1531_ (.A1(_0633_),
    .A2(_0909_),
    .B1(\core.play1.tick_counter[13] ),
    .Y(_0922_));
 sky130_fd_sc_hd__a311oi_1 _1532_ (.A1(\core.play1.tick_counter[13] ),
    .A2(_0913_),
    .A3(_0919_),
    .B1(_0922_),
    .C1(net45),
    .Y(_0923_));
 sky130_fd_sc_hd__o211ai_1 _1533_ (.A1(_0913_),
    .A2(_0919_),
    .B1(_0921_),
    .C1(_0923_),
    .Y(_0924_));
 sky130_fd_sc_hd__xor2_1 _1534_ (.A(\core.play1.tick_counter[14] ),
    .B(_0924_),
    .X(_0925_));
 sky130_fd_sc_hd__nor2_1 _1535_ (.A(net50),
    .B(_0925_),
    .Y(_0140_));
 sky130_fd_sc_hd__o31ai_1 _1536_ (.A1(_0839_),
    .A2(_0869_),
    .A3(_0906_),
    .B1(_0911_),
    .Y(_0926_));
 sky130_fd_sc_hd__nand3_1 _1537_ (.A(\core.play1.tick_counter[14] ),
    .B(\core.play1.tick_counter[13] ),
    .C(_0926_),
    .Y(_0927_));
 sky130_fd_sc_hd__nand2b_1 _1538_ (.A_N(\core.play1.tick_counter[13] ),
    .B(\core.play1.tick_counter[14] ),
    .Y(_0928_));
 sky130_fd_sc_hd__a21oi_1 _1539_ (.A1(_0887_),
    .A2(_0888_),
    .B1(_0928_),
    .Y(_0929_));
 sky130_fd_sc_hd__a21oi_1 _1540_ (.A1(_0831_),
    .A2(_0834_),
    .B1(_0838_),
    .Y(_0930_));
 sky130_fd_sc_hd__nand2b_1 _1541_ (.A_N(\core.play1.tick_counter[14] ),
    .B(\core.play1.tick_counter[13] ),
    .Y(_0931_));
 sky130_fd_sc_hd__nor4_1 _1542_ (.A(_0930_),
    .B(_0869_),
    .C(_0906_),
    .D(_0931_),
    .Y(_0932_));
 sky130_fd_sc_hd__o21ai_0 _1543_ (.A1(_0929_),
    .A2(_0932_),
    .B1(_0911_),
    .Y(_0933_));
 sky130_fd_sc_hd__a32oi_2 _1544_ (.A1(_0878_),
    .A2(_0900_),
    .A3(_0914_),
    .B1(_0927_),
    .B2(_0933_),
    .Y(_0934_));
 sky130_fd_sc_hd__a211oi_1 _1545_ (.A1(_0887_),
    .A2(_0888_),
    .B1(_0908_),
    .C1(_0621_),
    .Y(_0935_));
 sky130_fd_sc_hd__nor4_1 _1546_ (.A(net43),
    .B(net45),
    .C(_0934_),
    .D(_0935_),
    .Y(_0936_));
 sky130_fd_sc_hd__xnor2_1 _1547_ (.A(\core.play1.tick_counter[15] ),
    .B(_0936_),
    .Y(_0937_));
 sky130_fd_sc_hd__nor2_1 _1548_ (.A(net50),
    .B(_0937_),
    .Y(_0141_));
 sky130_fd_sc_hd__a32oi_1 _1549_ (.A1(_0857_),
    .A2(_0900_),
    .A3(_0914_),
    .B1(_0927_),
    .B2(_0933_),
    .Y(_0938_));
 sky130_fd_sc_hd__nor2_1 _1550_ (.A(\core.play1.tick_counter[15] ),
    .B(_0935_),
    .Y(_0939_));
 sky130_fd_sc_hd__and3_1 _1551_ (.A(\core.play1.tick_counter[14] ),
    .B(\core.play1.tick_counter[15] ),
    .C(\core.play1.tick_counter[13] ),
    .X(_0940_));
 sky130_fd_sc_hd__nand2_1 _1552_ (.A(_0911_),
    .B(_0940_),
    .Y(_0941_));
 sky130_fd_sc_hd__a21oi_1 _1554_ (.A1(_0887_),
    .A2(_0888_),
    .B1(_0941_),
    .Y(_0943_));
 sky130_fd_sc_hd__o21ai_0 _1555_ (.A1(_0939_),
    .A2(_0943_),
    .B1(_0633_),
    .Y(_0944_));
 sky130_fd_sc_hd__a31oi_1 _1556_ (.A1(_0071_),
    .A2(_0073_),
    .A3(_0881_),
    .B1(_0837_),
    .Y(_0945_));
 sky130_fd_sc_hd__nand3_1 _1557_ (.A(_0834_),
    .B(_0911_),
    .C(_0940_),
    .Y(_0946_));
 sky130_fd_sc_hd__o22ai_1 _1558_ (.A1(_0945_),
    .A2(_0941_),
    .B1(_0946_),
    .B2(_0847_),
    .Y(_0947_));
 sky130_fd_sc_hd__o21ai_0 _1559_ (.A1(_0938_),
    .A2(_0944_),
    .B1(_0947_),
    .Y(_0948_));
 sky130_fd_sc_hd__or3_1 _1560_ (.A(_0947_),
    .B(_0938_),
    .C(_0944_),
    .X(_0949_));
 sky130_fd_sc_hd__a21oi_1 _1561_ (.A1(_0948_),
    .A2(_0949_),
    .B1(net45),
    .Y(_0950_));
 sky130_fd_sc_hd__xnor2_1 _1562_ (.A(\core.play1.tick_counter[16] ),
    .B(_0950_),
    .Y(_0951_));
 sky130_fd_sc_hd__nor2_1 _1563_ (.A(net50),
    .B(_0951_),
    .Y(_0142_));
 sky130_fd_sc_hd__a21o_1 _1564_ (.A1(_0887_),
    .A2(_0888_),
    .B1(_0941_),
    .X(_0952_));
 sky130_fd_sc_hd__a21oi_1 _1565_ (.A1(_0633_),
    .A2(_0947_),
    .B1(_0952_),
    .Y(_0953_));
 sky130_fd_sc_hd__nor4_1 _1566_ (.A(\core.play1.tick_counter[16] ),
    .B(_0934_),
    .C(_0947_),
    .D(_0944_),
    .Y(_0954_));
 sky130_fd_sc_hd__a21oi_1 _1567_ (.A1(\core.play1.tick_counter[16] ),
    .A2(_0953_),
    .B1(_0954_),
    .Y(_0955_));
 sky130_fd_sc_hd__o21ai_0 _1568_ (.A1(net45),
    .A2(_0955_),
    .B1(\core.play1.tick_counter[17] ),
    .Y(_0956_));
 sky130_fd_sc_hd__or3_1 _1569_ (.A(\core.play1.tick_counter[17] ),
    .B(net45),
    .C(_0955_),
    .X(_0957_));
 sky130_fd_sc_hd__a21oi_1 _1571_ (.A1(_0956_),
    .A2(_0957_),
    .B1(net50),
    .Y(_0143_));
 sky130_fd_sc_hd__and2_1 _1572_ (.A(\core.play1.tick_counter[16] ),
    .B(\core.play1.tick_counter[17] ),
    .X(_0959_));
 sky130_fd_sc_hd__nand2_1 _1574_ (.A(_0947_),
    .B(_0959_),
    .Y(_0961_));
 sky130_fd_sc_hd__nand3b_1 _1575_ (.A_N(\core.play1.tick_counter[17] ),
    .B(_0947_),
    .C(\core.play1.tick_counter[16] ),
    .Y(_0962_));
 sky130_fd_sc_hd__mux2i_1 _1576_ (.A0(_0961_),
    .A1(_0962_),
    .S(_0952_),
    .Y(_0963_));
 sky130_fd_sc_hd__nor3_1 _1577_ (.A(\core.play1.tick_counter[16] ),
    .B(\core.play1.tick_counter[17] ),
    .C(_0947_),
    .Y(_0964_));
 sky130_fd_sc_hd__o221ai_1 _1578_ (.A1(_0939_),
    .A2(_0943_),
    .B1(_0963_),
    .B2(_0964_),
    .C1(_0633_),
    .Y(_0965_));
 sky130_fd_sc_hd__nand3_1 _1579_ (.A(_0911_),
    .B(_0940_),
    .C(_0959_),
    .Y(_0966_));
 sky130_fd_sc_hd__nand4_1 _1580_ (.A(_0834_),
    .B(_0911_),
    .C(_0940_),
    .D(_0959_),
    .Y(_0225_));
 sky130_fd_sc_hd__o22ai_1 _1581_ (.A1(_0945_),
    .A2(_0966_),
    .B1(_0225_),
    .B2(_0847_),
    .Y(_0226_));
 sky130_fd_sc_hd__o21ai_0 _1582_ (.A1(_0938_),
    .A2(_0965_),
    .B1(_0226_),
    .Y(_0227_));
 sky130_fd_sc_hd__a32o_1 _1583_ (.A1(_0857_),
    .A2(_0900_),
    .A3(_0914_),
    .B1(_0927_),
    .B2(_0933_),
    .X(_0228_));
 sky130_fd_sc_hd__o221a_2 _1584_ (.A1(_0939_),
    .A2(_0943_),
    .B1(_0963_),
    .B2(_0964_),
    .C1(_0633_),
    .X(_0229_));
 sky130_fd_sc_hd__nand3_1 _1585_ (.A(_0228_),
    .B(_0961_),
    .C(_0229_),
    .Y(_0230_));
 sky130_fd_sc_hd__a21oi_1 _1586_ (.A1(_0227_),
    .A2(_0230_),
    .B1(net45),
    .Y(_0231_));
 sky130_fd_sc_hd__xnor2_1 _1587_ (.A(\core.play1.tick_counter[18] ),
    .B(_0231_),
    .Y(_0232_));
 sky130_fd_sc_hd__nor2_1 _1588_ (.A(net50),
    .B(_0232_),
    .Y(_0144_));
 sky130_fd_sc_hd__nor2_1 _1589_ (.A(_0943_),
    .B(_0961_),
    .Y(_0233_));
 sky130_fd_sc_hd__nor2_1 _1590_ (.A(\core.play1.tick_counter[18] ),
    .B(_0226_),
    .Y(_0234_));
 sky130_fd_sc_hd__a21oi_1 _1591_ (.A1(\core.play1.tick_counter[18] ),
    .A2(_0233_),
    .B1(_0234_),
    .Y(_0235_));
 sky130_fd_sc_hd__nand4_1 _1592_ (.A(\core.play1.tick_counter[18] ),
    .B(_0943_),
    .C(_0959_),
    .D(_0961_),
    .Y(_0236_));
 sky130_fd_sc_hd__o31ai_1 _1593_ (.A1(_0934_),
    .A2(_0965_),
    .A3(_0235_),
    .B1(_0236_),
    .Y(_0237_));
 sky130_fd_sc_hd__nand2_1 _1594_ (.A(net44),
    .B(_0237_),
    .Y(_0238_));
 sky130_fd_sc_hd__xor2_1 _1595_ (.A(\core.play1.tick_counter[19] ),
    .B(_0238_),
    .X(_0239_));
 sky130_fd_sc_hd__nor2_1 _1596_ (.A(net50),
    .B(_0239_),
    .Y(_0145_));
 sky130_fd_sc_hd__nand2_1 _1597_ (.A(\core.play1.tick_counter[1] ),
    .B(net45),
    .Y(_0240_));
 sky130_fd_sc_hd__nand2_1 _1598_ (.A(_0044_),
    .B(net44),
    .Y(_0241_));
 sky130_fd_sc_hd__a21oi_1 _1599_ (.A1(_0240_),
    .A2(_0241_),
    .B1(net50),
    .Y(_0146_));
 sky130_fd_sc_hd__nor3_1 _1600_ (.A(\core.play1.tick_counter[18] ),
    .B(\core.play1.tick_counter[19] ),
    .C(_0226_),
    .Y(_0242_));
 sky130_fd_sc_hd__nand3_1 _1601_ (.A(_0228_),
    .B(_0229_),
    .C(_0242_),
    .Y(_0243_));
 sky130_fd_sc_hd__o2111ai_1 _1602_ (.A1(_0952_),
    .A2(_0965_),
    .B1(_0226_),
    .C1(\core.play1.tick_counter[18] ),
    .D1(\core.play1.tick_counter[19] ),
    .Y(_0244_));
 sky130_fd_sc_hd__a21oi_1 _1603_ (.A1(_0243_),
    .A2(_0244_),
    .B1(net45),
    .Y(_0245_));
 sky130_fd_sc_hd__xnor2_1 _1604_ (.A(\core.play1.tick_counter[20] ),
    .B(_0245_),
    .Y(_0246_));
 sky130_fd_sc_hd__nor2_1 _1605_ (.A(net50),
    .B(_0246_),
    .Y(_0147_));
 sky130_fd_sc_hd__and3_1 _1606_ (.A(\core.play1.tick_counter[20] ),
    .B(\core.play1.tick_counter[18] ),
    .C(\core.play1.tick_counter[19] ),
    .X(_0247_));
 sky130_fd_sc_hd__nand2_1 _1607_ (.A(_0959_),
    .B(_0247_),
    .Y(_0248_));
 sky130_fd_sc_hd__a211oi_1 _1608_ (.A1(_0887_),
    .A2(_0888_),
    .B1(_0941_),
    .C1(_0248_),
    .Y(_0249_));
 sky130_fd_sc_hd__nor4_1 _1609_ (.A(\core.play1.tick_counter[20] ),
    .B(\core.play1.tick_counter[18] ),
    .C(\core.play1.tick_counter[19] ),
    .D(_0226_),
    .Y(_0250_));
 sky130_fd_sc_hd__nand2_1 _1610_ (.A(_0226_),
    .B(_0247_),
    .Y(_0251_));
 sky130_fd_sc_hd__nand3_1 _1611_ (.A(\core.play1.tick_counter[18] ),
    .B(_0623_),
    .C(_0226_),
    .Y(_0252_));
 sky130_fd_sc_hd__mux2i_1 _1612_ (.A0(_0251_),
    .A1(_0252_),
    .S(_0952_),
    .Y(_0253_));
 sky130_fd_sc_hd__nor2_1 _1613_ (.A(_0250_),
    .B(_0253_),
    .Y(_0254_));
 sky130_fd_sc_hd__nor3_1 _1614_ (.A(_0934_),
    .B(_0965_),
    .C(_0254_),
    .Y(_0255_));
 sky130_fd_sc_hd__xnor2_1 _1615_ (.A(_0249_),
    .B(_0255_),
    .Y(_0256_));
 sky130_fd_sc_hd__o21ai_0 _1616_ (.A1(net45),
    .A2(_0256_),
    .B1(\core.play1.tick_counter[21] ),
    .Y(_0257_));
 sky130_fd_sc_hd__or3_1 _1617_ (.A(\core.play1.tick_counter[21] ),
    .B(net45),
    .C(_0256_),
    .X(_0258_));
 sky130_fd_sc_hd__a21oi_1 _1618_ (.A1(_0257_),
    .A2(_0258_),
    .B1(net50),
    .Y(_0148_));
 sky130_fd_sc_hd__xnor2_1 _1619_ (.A(\core.play1.tick_counter[21] ),
    .B(_0249_),
    .Y(_0259_));
 sky130_fd_sc_hd__o21ai_0 _1620_ (.A1(_0250_),
    .A2(_0253_),
    .B1(_0259_),
    .Y(_0260_));
 sky130_fd_sc_hd__nor3_1 _1621_ (.A(_0938_),
    .B(_0965_),
    .C(_0260_),
    .Y(_0261_));
 sky130_fd_sc_hd__and3_1 _1622_ (.A(\core.play1.tick_counter[21] ),
    .B(_0226_),
    .C(_0247_),
    .X(_0262_));
 sky130_fd_sc_hd__xnor2_1 _1623_ (.A(_0261_),
    .B(_0262_),
    .Y(_0263_));
 sky130_fd_sc_hd__o21ai_0 _1624_ (.A1(net45),
    .A2(_0263_),
    .B1(\core.play1.tick_counter[22] ),
    .Y(_0264_));
 sky130_fd_sc_hd__or3_1 _1625_ (.A(\core.play1.tick_counter[22] ),
    .B(net45),
    .C(_0263_),
    .X(_0265_));
 sky130_fd_sc_hd__a21oi_1 _1626_ (.A1(_0264_),
    .A2(_0265_),
    .B1(net50),
    .Y(_0149_));
 sky130_fd_sc_hd__nand4_1 _1627_ (.A(\core.play1.tick_counter[22] ),
    .B(\core.play1.tick_counter[21] ),
    .C(_0959_),
    .D(_0247_),
    .Y(_0266_));
 sky130_fd_sc_hd__nor2_1 _1628_ (.A(_0941_),
    .B(_0266_),
    .Y(_0267_));
 sky130_fd_sc_hd__o21ai_1 _1629_ (.A1(_0869_),
    .A2(_0906_),
    .B1(_0267_),
    .Y(_0268_));
 sky130_fd_sc_hd__xor2_1 _1630_ (.A(\core.play1.tick_counter[22] ),
    .B(_0262_),
    .X(_0269_));
 sky130_fd_sc_hd__nor4_1 _1631_ (.A(_0934_),
    .B(_0965_),
    .C(_0260_),
    .D(_0269_),
    .Y(_0270_));
 sky130_fd_sc_hd__xor2_1 _1632_ (.A(_0268_),
    .B(_0270_),
    .X(_0271_));
 sky130_fd_sc_hd__o21ai_0 _1633_ (.A1(net45),
    .A2(_0271_),
    .B1(\core.play1.tick_counter[23] ),
    .Y(_0272_));
 sky130_fd_sc_hd__or3_1 _1634_ (.A(\core.play1.tick_counter[23] ),
    .B(net45),
    .C(_0271_),
    .X(_0273_));
 sky130_fd_sc_hd__a21oi_1 _1635_ (.A1(_0272_),
    .A2(_0273_),
    .B1(net50),
    .Y(_0150_));
 sky130_fd_sc_hd__nor3_1 _1636_ (.A(_0930_),
    .B(_0941_),
    .C(_0266_),
    .Y(_0274_));
 sky130_fd_sc_hd__mux2i_1 _1637_ (.A0(_0261_),
    .A1(_0274_),
    .S(\core.play1.tick_counter[23] ),
    .Y(_0275_));
 sky130_fd_sc_hd__nand2_1 _1638_ (.A(net44),
    .B(_0268_),
    .Y(_0276_));
 sky130_fd_sc_hd__o31ai_1 _1639_ (.A1(_0269_),
    .A2(_0275_),
    .A3(_0276_),
    .B1(\core.play1.tick_counter[24] ),
    .Y(_0277_));
 sky130_fd_sc_hd__or4_1 _1640_ (.A(\core.play1.tick_counter[24] ),
    .B(_0269_),
    .C(_0275_),
    .D(_0276_),
    .X(_0278_));
 sky130_fd_sc_hd__a21oi_1 _1641_ (.A1(_0277_),
    .A2(_0278_),
    .B1(net50),
    .Y(_0151_));
 sky130_fd_sc_hd__and4_1 _1642_ (.A(\core.play1.tick_counter[22] ),
    .B(\core.play1.tick_counter[21] ),
    .C(_0959_),
    .D(_0247_),
    .X(_0279_));
 sky130_fd_sc_hd__nand3_1 _1643_ (.A(\core.play1.tick_counter[24] ),
    .B(\core.play1.tick_counter[23] ),
    .C(_0279_),
    .Y(_0280_));
 sky130_fd_sc_hd__nor3_1 _1644_ (.A(_0907_),
    .B(_0941_),
    .C(_0280_),
    .Y(_0281_));
 sky130_fd_sc_hd__or4b_2 _1645_ (.A(\core.play1.tick_counter[24] ),
    .B(_0274_),
    .C(_0268_),
    .D_N(\core.play1.tick_counter[23] ),
    .X(_0282_));
 sky130_fd_sc_hd__nor2_1 _1646_ (.A(\core.play1.tick_counter[24] ),
    .B(\core.play1.tick_counter[23] ),
    .Y(_0283_));
 sky130_fd_sc_hd__nand2_1 _1647_ (.A(_0268_),
    .B(_0283_),
    .Y(_0284_));
 sky130_fd_sc_hd__nand2_1 _1648_ (.A(_0947_),
    .B(_0279_),
    .Y(_0285_));
 sky130_fd_sc_hd__nand2_1 _1649_ (.A(\core.play1.tick_counter[24] ),
    .B(\core.play1.tick_counter[23] ),
    .Y(_0286_));
 sky130_fd_sc_hd__or3_1 _1650_ (.A(_0268_),
    .B(_0285_),
    .C(_0286_),
    .X(_0287_));
 sky130_fd_sc_hd__a31oi_1 _1651_ (.A1(_0282_),
    .A2(_0284_),
    .A3(_0287_),
    .B1(_0269_),
    .Y(_0288_));
 sky130_fd_sc_hd__or4b_1 _1652_ (.A(_0934_),
    .B(_0965_),
    .C(_0260_),
    .D_N(_0288_),
    .X(_0289_));
 sky130_fd_sc_hd__xor2_1 _1654_ (.A(_0281_),
    .B(_0289_),
    .X(_0291_));
 sky130_fd_sc_hd__nand2b_1 _1656_ (.A_N(\core.play1.tick_counter[25] ),
    .B(net51),
    .Y(_0293_));
 sky130_fd_sc_hd__o211ai_1 _1657_ (.A1(net45),
    .A2(_0291_),
    .B1(net51),
    .C1(\core.play1.tick_counter[25] ),
    .Y(_0294_));
 sky130_fd_sc_hd__o31ai_1 _1658_ (.A1(net45),
    .A2(_0291_),
    .A3(_0293_),
    .B1(_0294_),
    .Y(_0152_));
 sky130_fd_sc_hd__nand2_1 _1659_ (.A(net51),
    .B(\core.play1.tick_counter[26] ),
    .Y(_0295_));
 sky130_fd_sc_hd__inv_1 _1660_ (.A(\core.play1.tick_counter[26] ),
    .Y(_0296_));
 sky130_fd_sc_hd__nand2_1 _1661_ (.A(net51),
    .B(_0296_),
    .Y(_0297_));
 sky130_fd_sc_hd__nand3_1 _1662_ (.A(\core.play1.tick_counter[24] ),
    .B(\core.play1.tick_counter[23] ),
    .C(_0274_),
    .Y(_0298_));
 sky130_fd_sc_hd__o21ai_0 _1663_ (.A1(net45),
    .A2(_0298_),
    .B1(\core.play1.tick_counter[25] ),
    .Y(_0299_));
 sky130_fd_sc_hd__o21ai_0 _1664_ (.A1(_0268_),
    .A2(_0286_),
    .B1(_0299_),
    .Y(_0300_));
 sky130_fd_sc_hd__nand3_1 _1665_ (.A(\core.play1.tick_counter[25] ),
    .B(_0281_),
    .C(_0289_),
    .Y(_0301_));
 sky130_fd_sc_hd__nand4b_1 _1666_ (.A_N(_0260_),
    .B(_0228_),
    .C(_0229_),
    .D(_0288_),
    .Y(_0302_));
 sky130_fd_sc_hd__nor2_1 _1667_ (.A(_0285_),
    .B(_0286_),
    .Y(_0303_));
 sky130_fd_sc_hd__nand3_1 _1668_ (.A(\core.play1.tick_counter[25] ),
    .B(_0268_),
    .C(_0303_),
    .Y(_0304_));
 sky130_fd_sc_hd__a221oi_1 _1669_ (.A1(_0300_),
    .A2(_0301_),
    .B1(_0302_),
    .B2(_0304_),
    .C1(net45),
    .Y(_0305_));
 sky130_fd_sc_hd__mux2i_1 _1670_ (.A0(_0295_),
    .A1(_0297_),
    .S(_0305_),
    .Y(_0153_));
 sky130_fd_sc_hd__nand2_1 _1671_ (.A(net51),
    .B(\core.play1.tick_counter[27] ),
    .Y(_0306_));
 sky130_fd_sc_hd__nand2b_1 _1672_ (.A_N(\core.play1.tick_counter[27] ),
    .B(net51),
    .Y(_0307_));
 sky130_fd_sc_hd__a211oi_1 _1673_ (.A1(_0887_),
    .A2(_0888_),
    .B1(_0941_),
    .C1(_0280_),
    .Y(_0308_));
 sky130_fd_sc_hd__nand2_1 _1674_ (.A(\core.play1.tick_counter[26] ),
    .B(\core.play1.tick_counter[25] ),
    .Y(_0309_));
 sky130_fd_sc_hd__or4_1 _1675_ (.A(_0907_),
    .B(_0941_),
    .C(_0280_),
    .D(_0309_),
    .X(_0310_));
 sky130_fd_sc_hd__o32ai_1 _1676_ (.A1(\core.play1.tick_counter[26] ),
    .A2(\core.play1.tick_counter[25] ),
    .A3(_0308_),
    .B1(_0310_),
    .B2(_0285_),
    .Y(_0311_));
 sky130_fd_sc_hd__a41oi_1 _1677_ (.A1(_0296_),
    .A2(\core.play1.tick_counter[25] ),
    .A3(_0285_),
    .A4(_0281_),
    .B1(_0311_),
    .Y(_0312_));
 sky130_fd_sc_hd__nand2_1 _1678_ (.A(net44),
    .B(_0310_),
    .Y(_0313_));
 sky130_fd_sc_hd__nor2_1 _1679_ (.A(net45),
    .B(_0310_),
    .Y(_0314_));
 sky130_fd_sc_hd__o21ai_0 _1680_ (.A1(_0289_),
    .A2(_0312_),
    .B1(_0314_),
    .Y(_0315_));
 sky130_fd_sc_hd__o31ai_1 _1681_ (.A1(_0289_),
    .A2(_0312_),
    .A3(_0313_),
    .B1(_0315_),
    .Y(_0316_));
 sky130_fd_sc_hd__mux2i_1 _1682_ (.A0(_0306_),
    .A1(_0307_),
    .S(_0316_),
    .Y(_0154_));
 sky130_fd_sc_hd__or2_2 _1683_ (.A(\core.play1.tick_counter[25] ),
    .B(_0308_),
    .X(_0317_));
 sky130_fd_sc_hd__nand3_1 _1684_ (.A(\core.play1.tick_counter[25] ),
    .B(_0285_),
    .C(_0308_),
    .Y(_0318_));
 sky130_fd_sc_hd__a211oi_1 _1685_ (.A1(_0317_),
    .A2(_0318_),
    .B1(\core.play1.tick_counter[27] ),
    .C1(\core.play1.tick_counter[26] ),
    .Y(_0319_));
 sky130_fd_sc_hd__and2_1 _1686_ (.A(\core.play1.tick_counter[27] ),
    .B(\core.play1.tick_counter[26] ),
    .X(_0320_));
 sky130_fd_sc_hd__and4_1 _1687_ (.A(\core.play1.tick_counter[25] ),
    .B(_0274_),
    .C(_0308_),
    .D(_0320_),
    .X(_0321_));
 sky130_fd_sc_hd__nor2_1 _1688_ (.A(_0319_),
    .B(_0321_),
    .Y(_0322_));
 sky130_fd_sc_hd__and3_1 _1689_ (.A(\core.play1.tick_counter[25] ),
    .B(_0303_),
    .C(_0320_),
    .X(_0323_));
 sky130_fd_sc_hd__o211ai_1 _1690_ (.A1(_0302_),
    .A2(_0322_),
    .B1(_0323_),
    .C1(net44),
    .Y(_0324_));
 sky130_fd_sc_hd__or4_1 _1691_ (.A(net45),
    .B(_0302_),
    .C(_0323_),
    .D(_0322_),
    .X(_0325_));
 sky130_fd_sc_hd__nand3_1 _1692_ (.A(\core.play1.tick_counter[28] ),
    .B(_0324_),
    .C(_0325_),
    .Y(_0326_));
 sky130_fd_sc_hd__a21o_1 _1693_ (.A1(_0324_),
    .A2(_0325_),
    .B1(\core.play1.tick_counter[28] ),
    .X(_0327_));
 sky130_fd_sc_hd__a21oi_1 _1694_ (.A1(_0326_),
    .A2(_0327_),
    .B1(net50),
    .Y(_0155_));
 sky130_fd_sc_hd__nand2_1 _1695_ (.A(net51),
    .B(\core.play1.tick_counter[29] ),
    .Y(_0328_));
 sky130_fd_sc_hd__nand2b_1 _1696_ (.A_N(\core.play1.tick_counter[29] ),
    .B(net51),
    .Y(_0329_));
 sky130_fd_sc_hd__mux2_2 _1697_ (.A0(_0319_),
    .A1(_0321_),
    .S(\core.play1.tick_counter[28] ),
    .X(_0330_));
 sky130_fd_sc_hd__nor2b_1 _1698_ (.A(_0289_),
    .B_N(_0330_),
    .Y(_0331_));
 sky130_fd_sc_hd__nand3_1 _1699_ (.A(\core.play1.tick_counter[28] ),
    .B(\core.play1.tick_counter[25] ),
    .C(_0320_),
    .Y(_0332_));
 sky130_fd_sc_hd__nor4_1 _1700_ (.A(_0907_),
    .B(_0941_),
    .C(_0280_),
    .D(_0332_),
    .Y(_0333_));
 sky130_fd_sc_hd__nand2_1 _1701_ (.A(net44),
    .B(_0333_),
    .Y(_0334_));
 sky130_fd_sc_hd__or4b_1 _1702_ (.A(net45),
    .B(_0289_),
    .C(_0333_),
    .D_N(_0330_),
    .X(_0335_));
 sky130_fd_sc_hd__o21ai_2 _1703_ (.A1(_0331_),
    .A2(_0334_),
    .B1(_0335_),
    .Y(_0336_));
 sky130_fd_sc_hd__mux2i_1 _1704_ (.A0(_0328_),
    .A1(_0329_),
    .S(_0336_),
    .Y(_0156_));
 sky130_fd_sc_hd__xnor2_1 _1705_ (.A(_0043_),
    .B(_0048_),
    .Y(_0337_));
 sky130_fd_sc_hd__nor2_1 _1706_ (.A(\core.play1.tick_counter[2] ),
    .B(net44),
    .Y(_0338_));
 sky130_fd_sc_hd__a211oi_1 _1707_ (.A1(net44),
    .A2(_0337_),
    .B1(_0338_),
    .C1(net50),
    .Y(_0157_));
 sky130_fd_sc_hd__nand2_1 _1708_ (.A(net51),
    .B(\core.play1.tick_counter[30] ),
    .Y(_0339_));
 sky130_fd_sc_hd__inv_1 _1709_ (.A(\core.play1.tick_counter[30] ),
    .Y(_0340_));
 sky130_fd_sc_hd__nand2_1 _1710_ (.A(net51),
    .B(_0340_),
    .Y(_0341_));
 sky130_fd_sc_hd__nand2_1 _1711_ (.A(\core.play1.tick_counter[29] ),
    .B(net44),
    .Y(_0342_));
 sky130_fd_sc_hd__a2111oi_0 _1712_ (.A1(_0333_),
    .A2(_0330_),
    .B1(_0342_),
    .C1(_0332_),
    .D1(_0298_),
    .Y(_0343_));
 sky130_fd_sc_hd__nor3_1 _1713_ (.A(\core.play1.tick_counter[29] ),
    .B(net45),
    .C(_0333_),
    .Y(_0344_));
 sky130_fd_sc_hd__nand3b_1 _1714_ (.A_N(_0302_),
    .B(_0330_),
    .C(_0344_),
    .Y(_0345_));
 sky130_fd_sc_hd__nand2b_1 _1715_ (.A_N(_0343_),
    .B(_0345_),
    .Y(_0346_));
 sky130_fd_sc_hd__mux2i_1 _1716_ (.A0(_0339_),
    .A1(_0341_),
    .S(_0346_),
    .Y(_0158_));
 sky130_fd_sc_hd__nand2_1 _1717_ (.A(net51),
    .B(\core.play1.tick_counter[31] ),
    .Y(_0347_));
 sky130_fd_sc_hd__nand2b_1 _1718_ (.A_N(\core.play1.tick_counter[31] ),
    .B(net51),
    .Y(_0348_));
 sky130_fd_sc_hd__nand2_1 _1719_ (.A(\core.play1.tick_counter[30] ),
    .B(\core.play1.tick_counter[29] ),
    .Y(_0349_));
 sky130_fd_sc_hd__nor4_1 _1720_ (.A(_0268_),
    .B(_0286_),
    .C(_0332_),
    .D(_0349_),
    .Y(_0350_));
 sky130_fd_sc_hd__nand2_1 _1721_ (.A(net44),
    .B(_0350_),
    .Y(_0351_));
 sky130_fd_sc_hd__or2_2 _1722_ (.A(net45),
    .B(_0350_),
    .X(_0352_));
 sky130_fd_sc_hd__a2111oi_0 _1723_ (.A1(_0887_),
    .A2(_0888_),
    .B1(_0941_),
    .C1(_0280_),
    .D1(_0332_),
    .Y(_0353_));
 sky130_fd_sc_hd__o311ai_0 _1724_ (.A1(_0285_),
    .A2(_0286_),
    .A3(_0332_),
    .B1(_0353_),
    .C1(\core.play1.tick_counter[29] ),
    .Y(_0354_));
 sky130_fd_sc_hd__o21ai_0 _1725_ (.A1(\core.play1.tick_counter[29] ),
    .A2(_0353_),
    .B1(_0354_),
    .Y(_0355_));
 sky130_fd_sc_hd__nand3_1 _1726_ (.A(\core.play1.tick_counter[30] ),
    .B(\core.play1.tick_counter[29] ),
    .C(_0353_),
    .Y(_0356_));
 sky130_fd_sc_hd__nor3_1 _1727_ (.A(_0298_),
    .B(_0332_),
    .C(_0356_),
    .Y(_0357_));
 sky130_fd_sc_hd__a21oi_1 _1728_ (.A1(_0340_),
    .A2(_0355_),
    .B1(_0357_),
    .Y(_0358_));
 sky130_fd_sc_hd__nor3b_1 _1729_ (.A(_0358_),
    .B(_0289_),
    .C_N(_0330_),
    .Y(_0359_));
 sky130_fd_sc_hd__mux2i_1 _1730_ (.A0(_0351_),
    .A1(_0352_),
    .S(_0359_),
    .Y(_0360_));
 sky130_fd_sc_hd__mux2i_1 _1731_ (.A0(_0347_),
    .A1(_0348_),
    .S(_0360_),
    .Y(_0159_));
 sky130_fd_sc_hd__and2_1 _1732_ (.A(\core.play1.tick_counter[3] ),
    .B(net45),
    .X(_0361_));
 sky130_fd_sc_hd__xnor2_1 _1733_ (.A(_0060_),
    .B(net43),
    .Y(_0362_));
 sky130_fd_sc_hd__nor2_1 _1734_ (.A(net45),
    .B(_0362_),
    .Y(_0363_));
 sky130_fd_sc_hd__o21a_1 _1735_ (.A1(_0361_),
    .A2(_0363_),
    .B1(net51),
    .X(_0160_));
 sky130_fd_sc_hd__nor2_1 _1736_ (.A(\core.play1.tick_counter[4] ),
    .B(net44),
    .Y(_0364_));
 sky130_fd_sc_hd__mux2i_1 _1737_ (.A0(_0063_),
    .A1(_0061_),
    .S(net43),
    .Y(_0365_));
 sky130_fd_sc_hd__nor2_1 _1738_ (.A(net45),
    .B(_0365_),
    .Y(_0366_));
 sky130_fd_sc_hd__nor3_1 _1739_ (.A(net50),
    .B(_0364_),
    .C(_0366_),
    .Y(_0161_));
 sky130_fd_sc_hd__or2_2 _1740_ (.A(_0842_),
    .B(_0845_),
    .X(_0367_));
 sky130_fd_sc_hd__nand2b_1 _1741_ (.A_N(_0062_),
    .B(_0633_),
    .Y(_0368_));
 sky130_fd_sc_hd__xnor2_1 _1742_ (.A(_0367_),
    .B(_0368_),
    .Y(_0369_));
 sky130_fd_sc_hd__nor2_1 _1743_ (.A(\core.play1.tick_counter[5] ),
    .B(net44),
    .Y(_0370_));
 sky130_fd_sc_hd__a211oi_1 _1744_ (.A1(net44),
    .A2(_0369_),
    .B1(_0370_),
    .C1(net50),
    .Y(_0162_));
 sky130_fd_sc_hd__o21ai_0 _1745_ (.A1(net43),
    .A2(_0846_),
    .B1(_0848_),
    .Y(_0371_));
 sky130_fd_sc_hd__or3_1 _1746_ (.A(net43),
    .B(_0846_),
    .C(_0848_),
    .X(_0372_));
 sky130_fd_sc_hd__nor2_1 _1747_ (.A(\core.play1.tick_counter[6] ),
    .B(net44),
    .Y(_0373_));
 sky130_fd_sc_hd__a311oi_1 _1748_ (.A1(net44),
    .A2(_0371_),
    .A3(_0372_),
    .B1(_0373_),
    .C1(net50),
    .Y(_0163_));
 sky130_fd_sc_hd__and2_1 _1749_ (.A(_0855_),
    .B(_0856_),
    .X(_0374_));
 sky130_fd_sc_hd__o21ai_0 _1750_ (.A1(_0848_),
    .A2(_0877_),
    .B1(_0633_),
    .Y(_0375_));
 sky130_fd_sc_hd__xor2_1 _1751_ (.A(_0374_),
    .B(_0375_),
    .X(_0376_));
 sky130_fd_sc_hd__nor2_1 _1752_ (.A(\core.play1.tick_counter[7] ),
    .B(net44),
    .Y(_0377_));
 sky130_fd_sc_hd__a211oi_1 _1753_ (.A1(net44),
    .A2(_0376_),
    .B1(_0377_),
    .C1(net50),
    .Y(_0164_));
 sky130_fd_sc_hd__o211ai_1 _1754_ (.A1(_0846_),
    .A2(_0848_),
    .B1(_0374_),
    .C1(_0633_),
    .Y(_0378_));
 sky130_fd_sc_hd__xor2_1 _1755_ (.A(_0851_),
    .B(_0378_),
    .X(_0379_));
 sky130_fd_sc_hd__nor2_1 _1756_ (.A(\core.play1.tick_counter[8] ),
    .B(net44),
    .Y(_0380_));
 sky130_fd_sc_hd__a211oi_1 _1757_ (.A1(net44),
    .A2(_0379_),
    .B1(_0380_),
    .C1(net50),
    .Y(_0165_));
 sky130_fd_sc_hd__nand2_1 _1758_ (.A(_0633_),
    .B(_0878_),
    .Y(_0381_));
 sky130_fd_sc_hd__xor2_1 _1759_ (.A(_0870_),
    .B(_0381_),
    .X(_0382_));
 sky130_fd_sc_hd__nor2_1 _1760_ (.A(\core.play1.tick_counter[9] ),
    .B(net44),
    .Y(_0383_));
 sky130_fd_sc_hd__a211oi_1 _1761_ (.A1(net44),
    .A2(_0382_),
    .B1(_0383_),
    .C1(net50),
    .Y(_0166_));
 sky130_fd_sc_hd__a21oi_1 _1762_ (.A1(_0794_),
    .A2(_0548_),
    .B1(\core.score1.ena ),
    .Y(_0384_));
 sky130_fd_sc_hd__nor2_1 _1763_ (.A(_0492_),
    .B(_0384_),
    .Y(_0176_));
 sky130_fd_sc_hd__nor4_1 _1764_ (.A(\core.millis_counter[7] ),
    .B(\core.millis_counter[6] ),
    .C(_0560_),
    .D(_0561_),
    .Y(_0385_));
 sky130_fd_sc_hd__nand4_1 _1765_ (.A(_0092_),
    .B(\core.millis_counter[5] ),
    .C(_0385_),
    .D(_0727_),
    .Y(_0386_));
 sky130_fd_sc_hd__nor4_1 _1766_ (.A(_0492_),
    .B(_0730_),
    .C(_0760_),
    .D(_0386_),
    .Y(_0177_));
 sky130_fd_sc_hd__nor4_1 _1767_ (.A(_0092_),
    .B(_0552_),
    .C(_0560_),
    .D(_0567_),
    .Y(_0387_));
 sky130_fd_sc_hd__nor3b_1 _1768_ (.A(_0492_),
    .B(_0549_),
    .C_N(_0387_),
    .Y(_0178_));
 sky130_fd_sc_hd__nand2_1 _1769_ (.A(_0732_),
    .B(_0727_),
    .Y(_0388_));
 sky130_fd_sc_hd__o31ai_1 _1770_ (.A1(_0730_),
    .A2(_0760_),
    .A3(_0388_),
    .B1(net14),
    .Y(_0389_));
 sky130_fd_sc_hd__o21ai_0 _1771_ (.A1(_0730_),
    .A2(_0388_),
    .B1(net47),
    .Y(_0390_));
 sky130_fd_sc_hd__and3b_1 _1772_ (.A_N(net7),
    .B(_0390_),
    .C(net48),
    .X(_0391_));
 sky130_fd_sc_hd__nand2b_1 _1773_ (.A_N(net14),
    .B(_0391_),
    .Y(_0392_));
 sky130_fd_sc_hd__a21oi_1 _1774_ (.A1(_0389_),
    .A2(_0392_),
    .B1(_0492_),
    .Y(_0179_));
 sky130_fd_sc_hd__nand2b_1 _1775_ (.A_N(_0391_),
    .B(net15),
    .Y(_0393_));
 sky130_fd_sc_hd__nand3_1 _1776_ (.A(net47),
    .B(_0075_),
    .C(_0391_),
    .Y(_0394_));
 sky130_fd_sc_hd__a21oi_1 _1777_ (.A1(_0393_),
    .A2(_0394_),
    .B1(_0492_),
    .Y(_0180_));
 sky130_fd_sc_hd__nand2_1 _1778_ (.A(net51),
    .B(_0549_),
    .Y(_0395_));
 sky130_fd_sc_hd__nand2_1 _1779_ (.A(_0074_),
    .B(_0391_),
    .Y(_0396_));
 sky130_fd_sc_hd__xor2_1 _1780_ (.A(net16),
    .B(_0396_),
    .X(_0397_));
 sky130_fd_sc_hd__nor2_1 _1781_ (.A(_0395_),
    .B(_0397_),
    .Y(_0181_));
 sky130_fd_sc_hd__nand4_1 _1782_ (.A(net14),
    .B(net15),
    .C(net16),
    .D(_0391_),
    .Y(_0398_));
 sky130_fd_sc_hd__xor2_1 _1783_ (.A(net17),
    .B(_0398_),
    .X(_0399_));
 sky130_fd_sc_hd__nor2_1 _1784_ (.A(_0395_),
    .B(_0399_),
    .Y(_0182_));
 sky130_fd_sc_hd__nand4_1 _1785_ (.A(net16),
    .B(net17),
    .C(_0074_),
    .D(_0391_),
    .Y(_0400_));
 sky130_fd_sc_hd__xor2_1 _1786_ (.A(net18),
    .B(_0400_),
    .X(_0401_));
 sky130_fd_sc_hd__nor2_1 _1787_ (.A(_0395_),
    .B(_0401_),
    .Y(_0183_));
 sky130_fd_sc_hd__a21oi_1 _1788_ (.A1(_0104_),
    .A2(_0769_),
    .B1(_0565_),
    .Y(_0402_));
 sky130_fd_sc_hd__nand2_1 _1789_ (.A(net48),
    .B(_0563_),
    .Y(_0403_));
 sky130_fd_sc_hd__a22oi_1 _1790_ (.A1(net48),
    .A2(net47),
    .B1(_0403_),
    .B2(net7),
    .Y(_0404_));
 sky130_fd_sc_hd__nor3_1 _1791_ (.A(_0570_),
    .B(_0402_),
    .C(_0404_),
    .Y(_0405_));
 sky130_fd_sc_hd__o21ai_0 _1793_ (.A1(\core.millis_counter[0] ),
    .A2(_0557_),
    .B1(_0608_),
    .Y(_0407_));
 sky130_fd_sc_hd__o311ai_0 _1794_ (.A1(_0102_),
    .A2(_0103_),
    .A3(_0608_),
    .B1(_0771_),
    .C1(_0407_),
    .Y(_0408_));
 sky130_fd_sc_hd__nor2_1 _1795_ (.A(_0103_),
    .B(_0101_),
    .Y(_0409_));
 sky130_fd_sc_hd__o21ai_0 _1796_ (.A1(\core.tone_sequence_counter[2] ),
    .A2(_0409_),
    .B1(_0564_),
    .Y(_0410_));
 sky130_fd_sc_hd__nand2_1 _1797_ (.A(_0737_),
    .B(_0410_),
    .Y(_0411_));
 sky130_fd_sc_hd__nor2_1 _1798_ (.A(\core.play1.freq[0] ),
    .B(net40),
    .Y(_0412_));
 sky130_fd_sc_hd__a311oi_1 _1799_ (.A1(net40),
    .A2(_0408_),
    .A3(_0411_),
    .B1(_0412_),
    .C1(net50),
    .Y(_0184_));
 sky130_fd_sc_hd__o21ai_0 _1800_ (.A1(_0109_),
    .A2(_0557_),
    .B1(_0608_),
    .Y(_0413_));
 sky130_fd_sc_hd__nand2_1 _1801_ (.A(_0771_),
    .B(_0413_),
    .Y(_0414_));
 sky130_fd_sc_hd__a21oi_1 _1802_ (.A1(net48),
    .A2(_0775_),
    .B1(_0558_),
    .Y(_0415_));
 sky130_fd_sc_hd__mux2i_1 _1803_ (.A0(\core.tone_sequence_counter[0] ),
    .A1(\core.tone_sequence_counter[2] ),
    .S(\core.tone_sequence_counter[1] ),
    .Y(_0416_));
 sky130_fd_sc_hd__and3b_1 _1804_ (.A_N(net48),
    .B(net7),
    .C(net47),
    .X(_0417_));
 sky130_fd_sc_hd__nor2_1 _1805_ (.A(_0732_),
    .B(_0760_),
    .Y(_0418_));
 sky130_fd_sc_hd__a222oi_1 _1806_ (.A1(_0079_),
    .A2(_0415_),
    .B1(_0416_),
    .B2(_0417_),
    .C1(_0418_),
    .C2(_0088_),
    .Y(_0419_));
 sky130_fd_sc_hd__nor2_1 _1807_ (.A(\core.play1.freq[1] ),
    .B(net40),
    .Y(_0420_));
 sky130_fd_sc_hd__a311oi_1 _1808_ (.A1(net40),
    .A2(_0414_),
    .A3(_0419_),
    .B1(_0420_),
    .C1(net50),
    .Y(_0185_));
 sky130_fd_sc_hd__nand2b_1 _1809_ (.A_N(net40),
    .B(\core.play1.freq[2] ),
    .Y(_0421_));
 sky130_fd_sc_hd__nor2_1 _1810_ (.A(_0548_),
    .B(_0739_),
    .Y(_0422_));
 sky130_fd_sc_hd__xor2_1 _1811_ (.A(\core.millis_counter[2] ),
    .B(_0110_),
    .X(_0423_));
 sky130_fd_sc_hd__nor3_1 _1812_ (.A(_0557_),
    .B(_0564_),
    .C(_0423_),
    .Y(_0424_));
 sky130_fd_sc_hd__a21oi_1 _1813_ (.A1(_0100_),
    .A2(_0564_),
    .B1(_0424_),
    .Y(_0425_));
 sky130_fd_sc_hd__o21ai_0 _1814_ (.A1(_0087_),
    .A2(_0090_),
    .B1(_0418_),
    .Y(_0426_));
 sky130_fd_sc_hd__o211ai_1 _1815_ (.A1(_0796_),
    .A2(_0425_),
    .B1(_0426_),
    .C1(_0422_),
    .Y(_0427_));
 sky130_fd_sc_hd__o311ai_0 _1816_ (.A1(_0078_),
    .A2(_0083_),
    .A3(_0422_),
    .B1(_0427_),
    .C1(net40),
    .Y(_0428_));
 sky130_fd_sc_hd__a21oi_1 _1817_ (.A1(_0421_),
    .A2(_0428_),
    .B1(net50),
    .Y(_0186_));
 sky130_fd_sc_hd__nand2_1 _1818_ (.A(_0089_),
    .B(_0418_),
    .Y(_0429_));
 sky130_fd_sc_hd__o21ai_0 _1819_ (.A1(\core.millis_counter[0] ),
    .A2(\core.millis_counter[1] ),
    .B1(\core.millis_counter[2] ),
    .Y(_0430_));
 sky130_fd_sc_hd__xnor2_1 _1820_ (.A(\core.millis_counter[3] ),
    .B(_0430_),
    .Y(_0431_));
 sky130_fd_sc_hd__nand2_1 _1821_ (.A(_0608_),
    .B(_0431_),
    .Y(_0432_));
 sky130_fd_sc_hd__mux2i_1 _1822_ (.A0(\core.tone_sequence_counter[1] ),
    .A1(\core.tone_sequence_counter[2] ),
    .S(\core.tone_sequence_counter[0] ),
    .Y(_0433_));
 sky130_fd_sc_hd__a222oi_1 _1823_ (.A1(_0081_),
    .A2(_0415_),
    .B1(_0432_),
    .B2(_0771_),
    .C1(_0433_),
    .C2(_0417_),
    .Y(_0434_));
 sky130_fd_sc_hd__nor2_1 _1824_ (.A(\core.play1.freq[3] ),
    .B(net40),
    .Y(_0435_));
 sky130_fd_sc_hd__a311oi_1 _1825_ (.A1(net40),
    .A2(_0429_),
    .A3(_0434_),
    .B1(_0435_),
    .C1(net50),
    .Y(_0187_));
 sky130_fd_sc_hd__mux2_2 _1826_ (.A0(_0101_),
    .A1(_0102_),
    .S(\core.tone_sequence_counter[2] ),
    .X(_0436_));
 sky130_fd_sc_hd__a22oi_1 _1827_ (.A1(_0084_),
    .A2(_0415_),
    .B1(_0436_),
    .B2(_0737_),
    .Y(_0437_));
 sky130_fd_sc_hd__nand2_1 _1828_ (.A(_0091_),
    .B(_0418_),
    .Y(_0438_));
 sky130_fd_sc_hd__and3_1 _1829_ (.A(net40),
    .B(_0437_),
    .C(_0438_),
    .X(_0439_));
 sky130_fd_sc_hd__nor3_1 _1830_ (.A(_0557_),
    .B(_0564_),
    .C(_0796_),
    .Y(_0440_));
 sky130_fd_sc_hd__nand2b_1 _1831_ (.A_N(_0095_),
    .B(_0440_),
    .Y(_0441_));
 sky130_fd_sc_hd__o21ai_0 _1832_ (.A1(\core.play1.freq[4] ),
    .A2(net40),
    .B1(net51),
    .Y(_0442_));
 sky130_fd_sc_hd__a21oi_1 _1833_ (.A1(_0439_),
    .A2(_0441_),
    .B1(_0442_),
    .Y(_0188_));
 sky130_fd_sc_hd__nor2_1 _1834_ (.A(\core.millis_counter[3] ),
    .B(\core.millis_counter[4] ),
    .Y(_0443_));
 sky130_fd_sc_hd__nand2_1 _1835_ (.A(_0430_),
    .B(_0443_),
    .Y(_0444_));
 sky130_fd_sc_hd__a21oi_1 _1836_ (.A1(_0608_),
    .A2(_0444_),
    .B1(_0796_),
    .Y(_0445_));
 sky130_fd_sc_hd__o311ai_0 _1837_ (.A1(_0101_),
    .A2(_0100_),
    .A3(_0608_),
    .B1(net40),
    .C1(_0445_),
    .Y(_0446_));
 sky130_fd_sc_hd__nand2b_1 _1838_ (.A_N(net40),
    .B(\core.play1.freq[5] ),
    .Y(_0447_));
 sky130_fd_sc_hd__a21oi_1 _1839_ (.A1(_0446_),
    .A2(_0447_),
    .B1(net50),
    .Y(_0189_));
 sky130_fd_sc_hd__o21ai_0 _1840_ (.A1(_0087_),
    .A2(_0089_),
    .B1(_0418_),
    .Y(_0448_));
 sky130_fd_sc_hd__nor2_1 _1841_ (.A(_0102_),
    .B(_0101_),
    .Y(_0449_));
 sky130_fd_sc_hd__o21ai_0 _1842_ (.A1(_0098_),
    .A2(_0449_),
    .B1(\core.tone_sequence_counter[2] ),
    .Y(_0450_));
 sky130_fd_sc_hd__o31ai_1 _1843_ (.A1(_0102_),
    .A2(_0103_),
    .A3(_0101_),
    .B1(_0450_),
    .Y(_0451_));
 sky130_fd_sc_hd__o21ai_0 _1844_ (.A1(_0102_),
    .A2(_0100_),
    .B1(_0564_),
    .Y(_0452_));
 sky130_fd_sc_hd__nand3_1 _1845_ (.A(_0608_),
    .B(_0607_),
    .C(_0443_),
    .Y(_0453_));
 sky130_fd_sc_hd__a21oi_1 _1846_ (.A1(_0452_),
    .A2(_0453_),
    .B1(_0796_),
    .Y(_0454_));
 sky130_fd_sc_hd__a211oi_1 _1847_ (.A1(_0737_),
    .A2(_0451_),
    .B1(_0454_),
    .C1(_0415_),
    .Y(_0455_));
 sky130_fd_sc_hd__nor3_1 _1848_ (.A(_0078_),
    .B(_0081_),
    .C(_0422_),
    .Y(_0456_));
 sky130_fd_sc_hd__a21oi_1 _1849_ (.A1(_0448_),
    .A2(_0455_),
    .B1(_0456_),
    .Y(_0457_));
 sky130_fd_sc_hd__mux2i_1 _1850_ (.A0(\core.play1.freq[6] ),
    .A1(_0457_),
    .S(net40),
    .Y(_0458_));
 sky130_fd_sc_hd__nor2_1 _1851_ (.A(net50),
    .B(_0458_),
    .Y(_0190_));
 sky130_fd_sc_hd__nor2_1 _1852_ (.A(_0078_),
    .B(_0422_),
    .Y(_0459_));
 sky130_fd_sc_hd__nor3_1 _1853_ (.A(_0564_),
    .B(_0796_),
    .C(_0444_),
    .Y(_0460_));
 sky130_fd_sc_hd__nor3_1 _1854_ (.A(\core.tone_sequence_counter[2] ),
    .B(_0569_),
    .C(_0449_),
    .Y(_0461_));
 sky130_fd_sc_hd__a2111oi_0 _1855_ (.A1(_0087_),
    .A2(_0418_),
    .B1(_0460_),
    .C1(_0461_),
    .D1(_0415_),
    .Y(_0462_));
 sky130_fd_sc_hd__nor2_1 _1856_ (.A(_0459_),
    .B(_0462_),
    .Y(_0463_));
 sky130_fd_sc_hd__mux2i_1 _1857_ (.A0(\core.play1.freq[7] ),
    .A1(_0463_),
    .S(net40),
    .Y(_0464_));
 sky130_fd_sc_hd__nor2_1 _1858_ (.A(net50),
    .B(_0464_),
    .Y(_0191_));
 sky130_fd_sc_hd__a21oi_1 _1859_ (.A1(\core.tone_sequence_counter[2] ),
    .A2(_0096_),
    .B1(\core.tone_sequence_counter[1] ),
    .Y(_0465_));
 sky130_fd_sc_hd__a21o_1 _1860_ (.A1(_0417_),
    .A2(_0465_),
    .B1(_0459_),
    .X(_0466_));
 sky130_fd_sc_hd__a221oi_1 _1861_ (.A1(_0763_),
    .A2(_0418_),
    .B1(_0440_),
    .B2(_0094_),
    .C1(_0466_),
    .Y(_0467_));
 sky130_fd_sc_hd__nor2_1 _1862_ (.A(\core.play1.freq[8] ),
    .B(net40),
    .Y(_0468_));
 sky130_fd_sc_hd__a211oi_1 _1863_ (.A1(net40),
    .A2(_0467_),
    .B1(_0468_),
    .C1(net50),
    .Y(_0192_));
 sky130_fd_sc_hd__nand2b_1 _1864_ (.A_N(_0557_),
    .B(_0444_),
    .Y(_0469_));
 sky130_fd_sc_hd__a21oi_1 _1865_ (.A1(_0608_),
    .A2(_0469_),
    .B1(_0796_),
    .Y(_0470_));
 sky130_fd_sc_hd__inv_1 _1866_ (.A(_0103_),
    .Y(_0471_));
 sky130_fd_sc_hd__o21ai_0 _1867_ (.A1(\core.tone_sequence_counter[2] ),
    .A2(_0471_),
    .B1(_0564_),
    .Y(_0472_));
 sky130_fd_sc_hd__o22ai_1 _1868_ (.A1(_0737_),
    .A2(_0470_),
    .B1(_0472_),
    .B2(_0771_),
    .Y(_0473_));
 sky130_fd_sc_hd__o21ai_0 _1869_ (.A1(\core.play1.freq[9] ),
    .A2(net40),
    .B1(net51),
    .Y(_0474_));
 sky130_fd_sc_hd__a21oi_1 _1870_ (.A1(_0439_),
    .A2(_0473_),
    .B1(_0474_),
    .Y(_0193_));
 sky130_fd_sc_hd__o2bb2ai_1 _1871_ (.A1_N(_0558_),
    .A2_N(_0770_),
    .B1(_0387_),
    .B2(_0775_),
    .Y(_0475_));
 sky130_fd_sc_hd__a221oi_1 _1872_ (.A1(_0495_),
    .A2(_0513_),
    .B1(_0475_),
    .B2(net48),
    .C1(_0738_),
    .Y(_0476_));
 sky130_fd_sc_hd__o21ai_0 _1873_ (.A1(net7),
    .A2(_0730_),
    .B1(net47),
    .Y(_0477_));
 sky130_fd_sc_hd__o21ai_0 _1874_ (.A1(net7),
    .A2(_0578_),
    .B1(net47),
    .Y(_0478_));
 sky130_fd_sc_hd__a21oi_1 _1875_ (.A1(_0476_),
    .A2(_0478_),
    .B1(net48),
    .Y(_0479_));
 sky130_fd_sc_hd__a311oi_1 _1876_ (.A1(net48),
    .A2(_0476_),
    .A3(_0477_),
    .B1(_0479_),
    .C1(_0492_),
    .Y(_0194_));
 sky130_fd_sc_hd__o21ai_0 _1877_ (.A1(net47),
    .A2(_0727_),
    .B1(net48),
    .Y(_0480_));
 sky130_fd_sc_hd__nand2_1 _1878_ (.A(net7),
    .B(_0476_),
    .Y(_0481_));
 sky130_fd_sc_hd__nor2_1 _1879_ (.A(_0480_),
    .B(_0481_),
    .Y(_0482_));
 sky130_fd_sc_hd__o21a_1 _1880_ (.A1(net48),
    .A2(net47),
    .B1(_0476_),
    .X(_0483_));
 sky130_fd_sc_hd__o21ai_0 _1881_ (.A1(net7),
    .A2(_0483_),
    .B1(net51),
    .Y(_0484_));
 sky130_fd_sc_hd__o21a_1 _1882_ (.A1(_0727_),
    .A2(_0730_),
    .B1(net48),
    .X(_0485_));
 sky130_fd_sc_hd__nor2_1 _1883_ (.A(_0497_),
    .B(_0485_),
    .Y(_0486_));
 sky130_fd_sc_hd__nor3_1 _1884_ (.A(_0482_),
    .B(_0484_),
    .C(_0486_),
    .Y(_0195_));
 sky130_fd_sc_hd__nand2_1 _1885_ (.A(net47),
    .B(_0481_),
    .Y(_0487_));
 sky130_fd_sc_hd__o31a_1 _1886_ (.A1(_0772_),
    .A2(_0798_),
    .A3(_0481_),
    .B1(_0487_),
    .X(_0488_));
 sky130_fd_sc_hd__nor2_1 _1887_ (.A(_0492_),
    .B(_0488_),
    .Y(_0196_));
 sky130_fd_sc_hd__fa_1 _1888_ (.A(\core.play1.tick_counter[1] ),
    .B(\core.play1.freq[1] ),
    .CIN(_0042_),
    .COUT(_0043_),
    .SUM(_0044_));
 sky130_fd_sc_hd__ha_1 _1889_ (.A(\core.play1.tick_counter[1] ),
    .B(\core.play1.freq[1] ),
    .COUT(_0045_),
    .SUM(_0046_));
 sky130_fd_sc_hd__ha_1 _1890_ (.A(\core.play1.tick_counter[2] ),
    .B(\core.play1.freq[2] ),
    .COUT(_0047_),
    .SUM(_0048_));
 sky130_fd_sc_hd__ha_1 _1891_ (.A(\core.seq_counter[0] ),
    .B(\core.seq_counter[1] ),
    .COUT(_0049_),
    .SUM(_0050_));
 sky130_fd_sc_hd__ha_1 _1892_ (.A(\core.tick_counter[0] ),
    .B(_0051_),
    .COUT(_0052_),
    .SUM(_0053_));
 sky130_fd_sc_hd__ha_1 _1893_ (.A(\core.tick_counter[0] ),
    .B(\core.tick_counter[1] ),
    .COUT(_0054_),
    .SUM(_0967_));
 sky130_fd_sc_hd__ha_1 _1894_ (.A(\core.play1.tick_counter[0] ),
    .B(\core.play1.freq[0] ),
    .COUT(_0042_),
    .SUM(_0055_));
 sky130_fd_sc_hd__ha_1 _1895_ (.A(\core.play1.tick_counter[3] ),
    .B(\core.play1.freq[3] ),
    .COUT(_0056_),
    .SUM(_0057_));
 sky130_fd_sc_hd__ha_1 _1896_ (.A(\core.play1.tick_counter[4] ),
    .B(\core.play1.freq[4] ),
    .COUT(_0058_),
    .SUM(_0059_));
 sky130_fd_sc_hd__ha_1 _1897_ (.A(_0060_),
    .B(_0061_),
    .COUT(_0062_),
    .SUM(_0063_));
 sky130_fd_sc_hd__ha_1 _1898_ (.A(\core.play1.tick_counter[5] ),
    .B(\core.play1.freq[5] ),
    .COUT(_0064_),
    .SUM(_0065_));
 sky130_fd_sc_hd__ha_1 _1899_ (.A(\core.play1.tick_counter[6] ),
    .B(\core.play1.freq[6] ),
    .COUT(_0066_),
    .SUM(_0067_));
 sky130_fd_sc_hd__ha_1 _1900_ (.A(\core.play1.tick_counter[7] ),
    .B(\core.play1.freq[7] ),
    .COUT(_0068_),
    .SUM(_0069_));
 sky130_fd_sc_hd__ha_1 _1901_ (.A(\core.play1.tick_counter[8] ),
    .B(\core.play1.freq[8] ),
    .COUT(_0070_),
    .SUM(_0071_));
 sky130_fd_sc_hd__ha_1 _1902_ (.A(\core.play1.tick_counter[9] ),
    .B(\core.play1.freq[9] ),
    .COUT(_0072_),
    .SUM(_0073_));
 sky130_fd_sc_hd__ha_1 _1903_ (.A(net14),
    .B(net15),
    .COUT(_0074_),
    .SUM(_0075_));
 sky130_fd_sc_hd__ha_1 _1904_ (.A(_0076_),
    .B(_0077_),
    .COUT(_0078_),
    .SUM(_0079_));
 sky130_fd_sc_hd__ha_1 _1905_ (.A(_0076_),
    .B(_0080_),
    .COUT(_0081_),
    .SUM(_0968_));
 sky130_fd_sc_hd__ha_1 _1906_ (.A(_0082_),
    .B(_0077_),
    .COUT(_0083_),
    .SUM(_0969_));
 sky130_fd_sc_hd__ha_1 _1907_ (.A(_0082_),
    .B(_0080_),
    .COUT(_0084_),
    .SUM(_0970_));
 sky130_fd_sc_hd__ha_1 _1908_ (.A(_0085_),
    .B(_0086_),
    .COUT(_0087_),
    .SUM(_0088_));
 sky130_fd_sc_hd__ha_1 _1909_ (.A(_0085_),
    .B(\core.user_input[1] ),
    .COUT(_0089_),
    .SUM(_0971_));
 sky130_fd_sc_hd__ha_1 _1910_ (.A(\core.user_input[0] ),
    .B(_0086_),
    .COUT(_0090_),
    .SUM(_0972_));
 sky130_fd_sc_hd__ha_1 _1911_ (.A(\core.user_input[0] ),
    .B(\core.user_input[1] ),
    .COUT(_0091_),
    .SUM(_0973_));
 sky130_fd_sc_hd__ha_1 _1912_ (.A(_0092_),
    .B(_0093_),
    .COUT(_0094_),
    .SUM(_0095_));
 sky130_fd_sc_hd__ha_1 _1913_ (.A(_0096_),
    .B(_0097_),
    .COUT(_0098_),
    .SUM(_0099_));
 sky130_fd_sc_hd__ha_1 _1914_ (.A(_0096_),
    .B(_0097_),
    .COUT(_0100_),
    .SUM(_0974_));
 sky130_fd_sc_hd__ha_1 _1915_ (.A(_0096_),
    .B(\core.tone_sequence_counter[1] ),
    .COUT(_0101_),
    .SUM(_0975_));
 sky130_fd_sc_hd__ha_1 _1916_ (.A(\core.tone_sequence_counter[0] ),
    .B(_0097_),
    .COUT(_0102_),
    .SUM(_0976_));
 sky130_fd_sc_hd__ha_1 _1917_ (.A(\core.tone_sequence_counter[0] ),
    .B(\core.tone_sequence_counter[1] ),
    .COUT(_0103_),
    .SUM(_0977_));
 sky130_fd_sc_hd__ha_1 _1918_ (.A(\core.tone_sequence_counter[2] ),
    .B(_0103_),
    .COUT(_0104_),
    .SUM(_0105_));
 sky130_fd_sc_hd__ha_1 _1919_ (.A(_0106_),
    .B(_0107_),
    .COUT(_0108_),
    .SUM(_0109_));
 sky130_fd_sc_hd__ha_1 _1920_ (.A(_0106_),
    .B(_0107_),
    .COUT(_0110_),
    .SUM(_0978_));
 sky130_fd_sc_hd__ha_1 _1921_ (.A(_0106_),
    .B(\core.millis_counter[1] ),
    .COUT(_0111_),
    .SUM(_0979_));
 sky130_fd_sc_hd__ha_1 _1922_ (.A(\core.millis_counter[0] ),
    .B(\core.millis_counter[1] ),
    .COUT(_0112_),
    .SUM(_0980_));
 sky130_fd_sc_hd__dfxtp_1 _1923_ (.D(_0113_),
    .Q(_0000_),
    .CLK(clknet_4_8_0_clk));
 sky130_fd_sc_hd__dfxtp_1 _1924_ (.D(_0114_),
    .Q(_0001_),
    .CLK(clknet_4_8_0_clk));
 sky130_fd_sc_hd__dfxtp_1 _1925_ (.D(_0115_),
    .Q(_0002_),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__dfxtp_1 _1926_ (.D(_0116_),
    .Q(_0003_),
    .CLK(clknet_4_8_0_clk));
 sky130_fd_sc_hd__dfxtp_1 _1927_ (.D(_0117_),
    .Q(_0004_),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_0_clk (.A(clk),
    .X(clknet_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_0_0_clk (.A(clknet_0_clk),
    .X(clknet_4_0_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_10_0_clk (.A(clknet_0_clk),
    .X(clknet_4_10_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_11_0_clk (.A(clknet_0_clk),
    .X(clknet_4_11_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_12_0_clk (.A(clknet_0_clk),
    .X(clknet_4_12_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_13_0_clk (.A(clknet_0_clk),
    .X(clknet_4_13_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_14_0_clk (.A(clknet_0_clk),
    .X(clknet_4_14_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_15_0_clk (.A(clknet_0_clk),
    .X(clknet_4_15_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_1_0_clk (.A(clknet_0_clk),
    .X(clknet_4_1_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_2_0_clk (.A(clknet_0_clk),
    .X(clknet_4_2_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_3_0_clk (.A(clknet_0_clk),
    .X(clknet_4_3_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_4_0_clk (.A(clknet_0_clk),
    .X(clknet_4_4_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_5_0_clk (.A(clknet_0_clk),
    .X(clknet_4_5_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_6_0_clk (.A(clknet_0_clk),
    .X(clknet_4_6_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_7_0_clk (.A(clknet_0_clk),
    .X(clknet_4_7_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_8_0_clk (.A(clknet_0_clk),
    .X(clknet_4_8_0_clk));
 sky130_fd_sc_hd__clkbuf_16 clkbuf_4_9_0_clk (.A(clknet_0_clk),
    .X(clknet_4_9_0_clk));
 sky130_fd_sc_hd__clkinv_8 clkload0 (.A(clknet_4_0_0_clk));
 sky130_fd_sc_hd__inv_8 clkload1 (.A(clknet_4_1_0_clk));
 sky130_fd_sc_hd__inv_8 clkload10 (.A(clknet_4_10_0_clk));
 sky130_fd_sc_hd__clkinv_4 clkload11 (.A(clknet_4_11_0_clk));
 sky130_fd_sc_hd__clkbuf_1 clkload12 (.A(clknet_4_12_0_clk));
 sky130_fd_sc_hd__clkbuf_8 clkload13 (.A(clknet_4_13_0_clk));
 sky130_fd_sc_hd__bufinv_16 clkload14 (.A(clknet_4_14_0_clk));
 sky130_fd_sc_hd__clkinvlp_4 clkload2 (.A(clknet_4_2_0_clk));
 sky130_fd_sc_hd__inv_6 clkload3 (.A(clknet_4_3_0_clk));
 sky130_fd_sc_hd__clkinv_8 clkload4 (.A(clknet_4_4_0_clk));
 sky130_fd_sc_hd__inv_8 clkload5 (.A(clknet_4_5_0_clk));
 sky130_fd_sc_hd__inv_8 clkload6 (.A(clknet_4_6_0_clk));
 sky130_fd_sc_hd__inv_6 clkload7 (.A(clknet_4_7_0_clk));
 sky130_fd_sc_hd__inv_6 clkload8 (.A(clknet_4_8_0_clk));
 sky130_fd_sc_hd__clkinvlp_4 clkload9 (.A(clknet_4_9_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.led[0]$_SDFFE_PN0P_  (.D(_0118_),
    .Q(net10),
    .CLK(clknet_4_11_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.led[1]$_SDFFE_PN0P_  (.D(_0119_),
    .Q(net11),
    .CLK(clknet_4_10_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.led[2]$_SDFFE_PN0P_  (.D(_0120_),
    .Q(net12),
    .CLK(clknet_4_10_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.led[3]$_SDFFE_PN0P_  (.D(_0121_),
    .Q(net13),
    .CLK(clknet_4_10_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.millis_counter[0]$_SDFF_PN0_  (.D(_0122_),
    .Q(\core.millis_counter[0] ),
    .CLK(clknet_4_2_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.millis_counter[1]$_SDFF_PN0_  (.D(_0123_),
    .Q(\core.millis_counter[1] ),
    .CLK(clknet_4_2_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.millis_counter[2]$_SDFF_PN0_  (.D(_0124_),
    .Q(\core.millis_counter[2] ),
    .CLK(clknet_4_11_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.millis_counter[3]$_SDFF_PN0_  (.D(_0125_),
    .Q(\core.millis_counter[3] ),
    .CLK(clknet_4_10_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.millis_counter[4]$_SDFF_PN0_  (.D(_0126_),
    .Q(\core.millis_counter[4] ),
    .CLK(clknet_4_10_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.millis_counter[5]$_SDFF_PN0_  (.D(_0127_),
    .Q(\core.millis_counter[5] ),
    .CLK(clknet_4_10_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.millis_counter[6]$_SDFF_PN0_  (.D(_0128_),
    .Q(\core.millis_counter[6] ),
    .CLK(clknet_4_11_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.millis_counter[7]$_SDFF_PN0_  (.D(_0129_),
    .Q(\core.millis_counter[7] ),
    .CLK(clknet_4_11_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.millis_counter[8]$_SDFF_PN0_  (.D(_0130_),
    .Q(\core.millis_counter[8] ),
    .CLK(clknet_4_10_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.millis_counter[9]$_SDFF_PN0_  (.D(_0131_),
    .Q(\core.millis_counter[9] ),
    .CLK(clknet_4_11_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.next_random[0]$_SDFF_PN0_  (.D(_0132_),
    .Q(\core.next_random[0] ),
    .CLK(clknet_4_6_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.next_random[1]$_SDFF_PN0_  (.D(_0133_),
    .Q(\core.next_random[1] ),
    .CLK(clknet_4_6_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.sound$_SDFFE_PP0N_  (.D(_0134_),
    .Q(net28),
    .CLK(clknet_4_5_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[0]$_SDFFE_PN0N_  (.D(_0135_),
    .Q(\core.play1.tick_counter[0] ),
    .CLK(clknet_4_3_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[10]$_SDFFE_PN0N_  (.D(_0136_),
    .Q(\core.play1.tick_counter[10] ),
    .CLK(clknet_4_7_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[11]$_SDFFE_PN0N_  (.D(_0137_),
    .Q(\core.play1.tick_counter[11] ),
    .CLK(clknet_4_5_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[12]$_SDFFE_PN0N_  (.D(_0138_),
    .Q(\core.play1.tick_counter[12] ),
    .CLK(clknet_4_5_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[13]$_SDFFE_PN0N_  (.D(_0139_),
    .Q(\core.play1.tick_counter[13] ),
    .CLK(clknet_4_5_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[14]$_SDFFE_PN0N_  (.D(_0140_),
    .Q(\core.play1.tick_counter[14] ),
    .CLK(clknet_4_5_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[15]$_SDFFE_PN0N_  (.D(_0141_),
    .Q(\core.play1.tick_counter[15] ),
    .CLK(clknet_4_5_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[16]$_SDFFE_PN0N_  (.D(_0142_),
    .Q(\core.play1.tick_counter[16] ),
    .CLK(clknet_4_4_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[17]$_SDFFE_PN0N_  (.D(_0143_),
    .Q(\core.play1.tick_counter[17] ),
    .CLK(clknet_4_5_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[18]$_SDFFE_PN0N_  (.D(_0144_),
    .Q(\core.play1.tick_counter[18] ),
    .CLK(clknet_4_1_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[19]$_SDFFE_PN0N_  (.D(_0145_),
    .Q(\core.play1.tick_counter[19] ),
    .CLK(clknet_4_1_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[1]$_SDFFE_PN0N_  (.D(_0146_),
    .Q(\core.play1.tick_counter[1] ),
    .CLK(clknet_4_3_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[20]$_SDFFE_PN0N_  (.D(_0147_),
    .Q(\core.play1.tick_counter[20] ),
    .CLK(clknet_4_1_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[21]$_SDFFE_PN0N_  (.D(_0148_),
    .Q(\core.play1.tick_counter[21] ),
    .CLK(clknet_4_1_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[22]$_SDFFE_PN0N_  (.D(_0149_),
    .Q(\core.play1.tick_counter[22] ),
    .CLK(clknet_4_1_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[23]$_SDFFE_PN0N_  (.D(_0150_),
    .Q(\core.play1.tick_counter[23] ),
    .CLK(clknet_4_1_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[24]$_SDFFE_PN0N_  (.D(_0151_),
    .Q(\core.play1.tick_counter[24] ),
    .CLK(clknet_4_4_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[25]$_SDFFE_PN0N_  (.D(_0152_),
    .Q(\core.play1.tick_counter[25] ),
    .CLK(clknet_4_4_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[26]$_SDFFE_PN0N_  (.D(_0153_),
    .Q(\core.play1.tick_counter[26] ),
    .CLK(clknet_4_4_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[27]$_SDFFE_PN0N_  (.D(_0154_),
    .Q(\core.play1.tick_counter[27] ),
    .CLK(clknet_4_4_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[28]$_SDFFE_PN0N_  (.D(_0155_),
    .Q(\core.play1.tick_counter[28] ),
    .CLK(clknet_4_5_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[29]$_SDFFE_PN0N_  (.D(_0156_),
    .Q(\core.play1.tick_counter[29] ),
    .CLK(clknet_4_4_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[2]$_SDFFE_PN0N_  (.D(_0157_),
    .Q(\core.play1.tick_counter[2] ),
    .CLK(clknet_4_1_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[30]$_SDFFE_PN0N_  (.D(_0158_),
    .Q(\core.play1.tick_counter[30] ),
    .CLK(clknet_4_5_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[31]$_SDFFE_PN0N_  (.D(_0159_),
    .Q(\core.play1.tick_counter[31] ),
    .CLK(clknet_4_4_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[3]$_SDFFE_PN0N_  (.D(_0160_),
    .Q(\core.play1.tick_counter[3] ),
    .CLK(clknet_4_1_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[4]$_SDFFE_PN0N_  (.D(_0161_),
    .Q(\core.play1.tick_counter[4] ),
    .CLK(clknet_4_3_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[5]$_SDFFE_PN0N_  (.D(_0162_),
    .Q(\core.play1.tick_counter[5] ),
    .CLK(clknet_4_6_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[6]$_SDFFE_PN0N_  (.D(_0163_),
    .Q(\core.play1.tick_counter[6] ),
    .CLK(clknet_4_7_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[7]$_SDFFE_PN0N_  (.D(_0164_),
    .Q(\core.play1.tick_counter[7] ),
    .CLK(clknet_4_7_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[8]$_SDFFE_PN0N_  (.D(_0165_),
    .Q(\core.play1.tick_counter[8] ),
    .CLK(clknet_4_6_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.play1.tick_counter[9]$_SDFFE_PN0N_  (.D(_0166_),
    .Q(\core.play1.tick_counter[9] ),
    .CLK(clknet_4_7_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.active_digit$_SDFF_PP0_  (.D(_0167_),
    .Q(\core.score1.active_digit ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.digits[0]$_DFF_P_  (.D(_0009_),
    .Q(net19),
    .CLK(clknet_4_9_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.digits[1]$_DFF_P_  (.D(\core.score1.active_digit ),
    .Q(net20),
    .CLK(clknet_4_9_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.ones[0]$_SDFFE_PP0P_  (.D(_0168_),
    .Q(\core.score1.ones[0] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.ones[1]$_SDFFE_PP0P_  (.D(_0169_),
    .Q(\core.score1.ones[1] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.ones[2]$_SDFFE_PP0P_  (.D(_0170_),
    .Q(\core.score1.ones[2] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.ones[3]$_SDFFE_PP0P_  (.D(_0171_),
    .Q(\core.score1.ones[3] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.segments[0]$_DFF_P_  (.D(_0218_),
    .Q(net21),
    .CLK(clknet_4_14_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.segments[1]$_DFF_P_  (.D(_0219_),
    .Q(net22),
    .CLK(clknet_4_14_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.segments[2]$_DFF_P_  (.D(_0220_),
    .Q(net23),
    .CLK(clknet_4_14_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.segments[3]$_DFF_P_  (.D(_0221_),
    .Q(net24),
    .CLK(clknet_4_14_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.segments[4]$_DFF_P_  (.D(_0222_),
    .Q(net25),
    .CLK(clknet_4_14_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.segments[5]$_DFF_P_  (.D(_0223_),
    .Q(net26),
    .CLK(clknet_4_9_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.segments[6]$_DFF_P_  (.D(_0224_),
    .Q(net27),
    .CLK(clknet_4_14_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.tens[0]$_SDFFE_PP0P_  (.D(_0172_),
    .Q(\core.score1.tens[0] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.tens[1]$_SDFFE_PP0P_  (.D(_0173_),
    .Q(\core.score1.tens[1] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.tens[2]$_SDFFE_PP0P_  (.D(_0174_),
    .Q(\core.score1.tens[2] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score1.tens[3]$_SDFFE_PP0P_  (.D(_0175_),
    .Q(\core.score1.tens[3] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score_ena$_SDFFE_PN0P_  (.D(_0176_),
    .Q(\core.score1.ena ),
    .CLK(clknet_4_11_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score_inc$_SDFF_PN0_  (.D(_0177_),
    .Q(\core.score1.inc ),
    .CLK(clknet_4_14_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.score_rst$_SDFF_PN0_  (.D(_0178_),
    .Q(\core.score_rst ),
    .CLK(clknet_4_9_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[0][0]$_DFFE_PP_  (.D(net42),
    .DE(_0010_),
    .Q(\core.seq[0][0] ),
    .CLK(clknet_4_7_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[0][1]$_DFFE_PP_  (.D(net41),
    .DE(_0010_),
    .Q(\core.seq[0][1] ),
    .CLK(clknet_4_8_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[10][0]$_DFFE_PP_  (.D(net42),
    .DE(_0011_),
    .Q(\core.seq[10][0] ),
    .CLK(clknet_4_8_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[10][1]$_DFFE_PP_  (.D(net41),
    .DE(_0011_),
    .Q(\core.seq[10][1] ),
    .CLK(clknet_4_8_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[11][0]$_DFFE_PP_  (.D(net42),
    .DE(_0012_),
    .Q(\core.seq[11][0] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[11][1]$_DFFE_PP_  (.D(net41),
    .DE(_0012_),
    .Q(\core.seq[11][1] ),
    .CLK(clknet_4_8_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[12][0]$_DFFE_PP_  (.D(net42),
    .DE(_0013_),
    .Q(\core.seq[12][0] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[12][1]$_DFFE_PP_  (.D(net41),
    .DE(_0013_),
    .Q(\core.seq[12][1] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[13][0]$_DFFE_PP_  (.D(net42),
    .DE(_0014_),
    .Q(\core.seq[13][0] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[13][1]$_DFFE_PP_  (.D(net41),
    .DE(_0014_),
    .Q(\core.seq[13][1] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[14][0]$_DFFE_PP_  (.D(net42),
    .DE(_0015_),
    .Q(\core.seq[14][0] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[14][1]$_DFFE_PP_  (.D(net41),
    .DE(_0015_),
    .Q(\core.seq[14][1] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[15][0]$_DFFE_PP_  (.D(net42),
    .DE(_0016_),
    .Q(\core.seq[15][0] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[15][1]$_DFFE_PP_  (.D(net41),
    .DE(_0016_),
    .Q(\core.seq[15][1] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[16][0]$_DFFE_PP_  (.D(net42),
    .DE(_0017_),
    .Q(\core.seq[16][0] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[16][1]$_DFFE_PP_  (.D(net41),
    .DE(_0017_),
    .Q(\core.seq[16][1] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[17][0]$_DFFE_PP_  (.D(net42),
    .DE(_0018_),
    .Q(\core.seq[17][0] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[17][1]$_DFFE_PP_  (.D(net41),
    .DE(_0018_),
    .Q(\core.seq[17][1] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[18][0]$_DFFE_PP_  (.D(net42),
    .DE(_0019_),
    .Q(\core.seq[18][0] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[18][1]$_DFFE_PP_  (.D(net41),
    .DE(_0019_),
    .Q(\core.seq[18][1] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[19][0]$_DFFE_PP_  (.D(net42),
    .DE(_0020_),
    .Q(\core.seq[19][0] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[19][1]$_DFFE_PP_  (.D(net41),
    .DE(_0020_),
    .Q(\core.seq[19][1] ),
    .CLK(clknet_4_13_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[1][0]$_DFFE_PP_  (.D(net42),
    .DE(_0021_),
    .Q(\core.seq[1][0] ),
    .CLK(clknet_4_7_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[1][1]$_DFFE_PP_  (.D(net41),
    .DE(_0021_),
    .Q(\core.seq[1][1] ),
    .CLK(clknet_4_6_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[20][0]$_DFFE_PP_  (.D(net42),
    .DE(_0022_),
    .Q(\core.seq[20][0] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[20][1]$_DFFE_PP_  (.D(net41),
    .DE(_0022_),
    .Q(\core.seq[20][1] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[21][0]$_DFFE_PP_  (.D(net42),
    .DE(_0023_),
    .Q(\core.seq[21][0] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[21][1]$_DFFE_PP_  (.D(net41),
    .DE(_0023_),
    .Q(\core.seq[21][1] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[22][0]$_DFFE_PP_  (.D(net42),
    .DE(_0024_),
    .Q(\core.seq[22][0] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[22][1]$_DFFE_PP_  (.D(net41),
    .DE(_0024_),
    .Q(\core.seq[22][1] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[23][0]$_DFFE_PP_  (.D(net42),
    .DE(_0025_),
    .Q(\core.seq[23][0] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[23][1]$_DFFE_PP_  (.D(net41),
    .DE(_0025_),
    .Q(\core.seq[23][1] ),
    .CLK(clknet_4_15_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[24][0]$_DFFE_PP_  (.D(net42),
    .DE(_0026_),
    .Q(\core.seq[24][0] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[24][1]$_DFFE_PP_  (.D(net41),
    .DE(_0026_),
    .Q(\core.seq[24][1] ),
    .CLK(clknet_4_14_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[25][0]$_DFFE_PP_  (.D(net42),
    .DE(_0027_),
    .Q(\core.seq[25][0] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[25][1]$_DFFE_PP_  (.D(net41),
    .DE(_0027_),
    .Q(\core.seq[25][1] ),
    .CLK(clknet_4_14_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[26][0]$_DFFE_PP_  (.D(net42),
    .DE(_0028_),
    .Q(\core.seq[26][0] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[26][1]$_DFFE_PP_  (.D(net41),
    .DE(_0028_),
    .Q(\core.seq[26][1] ),
    .CLK(clknet_4_8_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[27][0]$_DFFE_PP_  (.D(net42),
    .DE(_0029_),
    .Q(\core.seq[27][0] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[27][1]$_DFFE_PP_  (.D(net41),
    .DE(_0029_),
    .Q(\core.seq[27][1] ),
    .CLK(clknet_4_14_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[28][0]$_DFFE_PP_  (.D(net42),
    .DE(_0030_),
    .Q(\core.seq[28][0] ),
    .CLK(clknet_4_14_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[28][1]$_DFFE_PP_  (.D(net41),
    .DE(_0030_),
    .Q(\core.seq[28][1] ),
    .CLK(clknet_4_14_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[29][0]$_DFFE_PP_  (.D(net42),
    .DE(_0031_),
    .Q(\core.seq[29][0] ),
    .CLK(clknet_4_14_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[29][1]$_DFFE_PP_  (.D(net41),
    .DE(_0031_),
    .Q(\core.seq[29][1] ),
    .CLK(clknet_4_14_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[2][0]$_DFFE_PP_  (.D(net42),
    .DE(_0032_),
    .Q(\core.seq[2][0] ),
    .CLK(clknet_4_7_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[2][1]$_DFFE_PP_  (.D(net41),
    .DE(_0032_),
    .Q(\core.seq[2][1] ),
    .CLK(clknet_4_7_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[30][0]$_DFFE_PP_  (.D(net42),
    .DE(_0033_),
    .Q(\core.seq[30][0] ),
    .CLK(clknet_4_9_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[30][1]$_DFFE_PP_  (.D(net41),
    .DE(_0033_),
    .Q(\core.seq[30][1] ),
    .CLK(clknet_4_9_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[31][0]$_DFFE_PP_  (.D(net42),
    .DE(_0034_),
    .Q(\core.seq[31][0] ),
    .CLK(clknet_4_9_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[31][1]$_DFFE_PP_  (.D(net41),
    .DE(_0034_),
    .Q(\core.seq[31][1] ),
    .CLK(clknet_4_9_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[3][0]$_DFFE_PP_  (.D(net42),
    .DE(_0035_),
    .Q(\core.seq[3][0] ),
    .CLK(clknet_4_7_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[3][1]$_DFFE_PP_  (.D(net41),
    .DE(_0035_),
    .Q(\core.seq[3][1] ),
    .CLK(clknet_4_7_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[4][0]$_DFFE_PP_  (.D(net42),
    .DE(_0036_),
    .Q(\core.seq[4][0] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[4][1]$_DFFE_PP_  (.D(net41),
    .DE(_0036_),
    .Q(\core.seq[4][1] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[5][0]$_DFFE_PP_  (.D(net42),
    .DE(_0037_),
    .Q(\core.seq[5][0] ),
    .CLK(clknet_4_7_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[5][1]$_DFFE_PP_  (.D(net41),
    .DE(_0037_),
    .Q(\core.seq[5][1] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[6][0]$_DFFE_PP_  (.D(net42),
    .DE(_0038_),
    .Q(\core.seq[6][0] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[6][1]$_DFFE_PP_  (.D(net41),
    .DE(_0038_),
    .Q(\core.seq[6][1] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[7][0]$_DFFE_PP_  (.D(net42),
    .DE(_0039_),
    .Q(\core.seq[7][0] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[7][1]$_DFFE_PP_  (.D(net41),
    .DE(_0039_),
    .Q(\core.seq[7][1] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[8][0]$_DFFE_PP_  (.D(net42),
    .DE(_0040_),
    .Q(\core.seq[8][0] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[8][1]$_DFFE_PP_  (.D(net41),
    .DE(_0040_),
    .Q(\core.seq[8][1] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[9][0]$_DFFE_PP_  (.D(net42),
    .DE(_0041_),
    .Q(\core.seq[9][0] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.seq[9][1]$_DFFE_PP_  (.D(net41),
    .DE(_0041_),
    .Q(\core.seq[9][1] ),
    .CLK(clknet_4_12_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.seq_counter[0]$_SDFFE_PN0P_  (.D(_0113_),
    .Q(\core.seq_counter[0] ),
    .CLK(clknet_4_8_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.seq_counter[1]$_SDFFE_PN0P_  (.D(_0114_),
    .Q(\core.seq_counter[1] ),
    .CLK(clknet_4_11_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.seq_counter[2]$_SDFFE_PN0P_  (.D(_0115_),
    .Q(\core.seq_counter[2] ),
    .CLK(clknet_4_11_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.seq_counter[3]$_SDFFE_PN0P_  (.D(_0116_),
    .Q(\core.seq_counter[3] ),
    .CLK(clknet_4_8_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.seq_counter[4]$_SDFFE_PN0P_  (.D(_0117_),
    .Q(\core.seq_counter[4] ),
    .CLK(clknet_4_9_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.seq_length[0]$_SDFFE_PN0P_  (.D(_0179_),
    .Q(net14),
    .CLK(clknet_4_11_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.seq_length[1]$_SDFFE_PN0P_  (.D(_0180_),
    .Q(net15),
    .CLK(clknet_4_9_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.seq_length[2]$_SDFFE_PN0P_  (.D(_0181_),
    .Q(net16),
    .CLK(clknet_4_9_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.seq_length[3]$_SDFFE_PN0P_  (.D(_0182_),
    .Q(net17),
    .CLK(clknet_4_9_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.seq_length[4]$_SDFFE_PN0P_  (.D(_0183_),
    .Q(net18),
    .CLK(clknet_4_9_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.sound_freq[0]$_SDFFE_PN0P_  (.D(_0184_),
    .Q(\core.play1.freq[0] ),
    .CLK(clknet_4_3_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.sound_freq[1]$_SDFFE_PN0P_  (.D(_0185_),
    .Q(\core.play1.freq[1] ),
    .CLK(clknet_4_3_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.sound_freq[2]$_SDFFE_PN0P_  (.D(_0186_),
    .Q(\core.play1.freq[2] ),
    .CLK(clknet_4_3_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.sound_freq[3]$_SDFFE_PN0P_  (.D(_0187_),
    .Q(\core.play1.freq[3] ),
    .CLK(clknet_4_3_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.sound_freq[4]$_SDFFE_PN0P_  (.D(_0188_),
    .Q(\core.play1.freq[4] ),
    .CLK(clknet_4_3_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.sound_freq[5]$_SDFFE_PN0P_  (.D(_0189_),
    .Q(\core.play1.freq[5] ),
    .CLK(clknet_4_3_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.sound_freq[6]$_SDFFE_PN0P_  (.D(_0190_),
    .Q(\core.play1.freq[6] ),
    .CLK(clknet_4_6_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.sound_freq[7]$_SDFFE_PN0P_  (.D(_0191_),
    .Q(\core.play1.freq[7] ),
    .CLK(clknet_4_6_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.sound_freq[8]$_SDFFE_PN0P_  (.D(_0192_),
    .Q(\core.play1.freq[8] ),
    .CLK(clknet_4_6_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.sound_freq[9]$_SDFFE_PN0P_  (.D(_0193_),
    .Q(\core.play1.freq[9] ),
    .CLK(clknet_4_3_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.state[0]$_SDFFE_PN0P_  (.D(_0194_),
    .Q(net6),
    .CLK(clknet_4_10_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.state[1]$_SDFFE_PN0P_  (.D(_0195_),
    .Q(net7),
    .CLK(clknet_4_11_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.state[2]$_SDFFE_PN0P_  (.D(_0196_),
    .Q(net8),
    .CLK(clknet_4_10_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[0]$_SDFF_PP0_  (.D(_0197_),
    .Q(\core.tick_counter[0] ),
    .CLK(clknet_4_2_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[10]$_SDFF_PP0_  (.D(_0198_),
    .Q(\core.tick_counter[10] ),
    .CLK(clknet_4_0_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[11]$_SDFF_PP0_  (.D(_0199_),
    .Q(\core.tick_counter[11] ),
    .CLK(clknet_4_2_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[12]$_SDFF_PP0_  (.D(_0200_),
    .Q(\core.tick_counter[12] ),
    .CLK(clknet_4_2_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[13]$_SDFF_PP0_  (.D(_0201_),
    .Q(\core.tick_counter[13] ),
    .CLK(clknet_4_2_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[14]$_SDFF_PP0_  (.D(_0202_),
    .Q(\core.tick_counter[14] ),
    .CLK(clknet_4_2_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[15]$_SDFF_PP0_  (.D(_0203_),
    .Q(\core.tick_counter[15] ),
    .CLK(clknet_4_2_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[1]$_SDFF_PP0_  (.D(_0204_),
    .Q(\core.tick_counter[1] ),
    .CLK(clknet_4_2_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[2]$_SDFF_PP0_  (.D(_0205_),
    .Q(\core.tick_counter[2] ),
    .CLK(clknet_4_0_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[3]$_SDFF_PP0_  (.D(_0206_),
    .Q(\core.tick_counter[3] ),
    .CLK(clknet_4_2_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[4]$_SDFF_PP0_  (.D(_0207_),
    .Q(\core.tick_counter[4] ),
    .CLK(clknet_4_1_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[5]$_SDFF_PP0_  (.D(_0208_),
    .Q(\core.tick_counter[5] ),
    .CLK(clknet_4_0_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[6]$_SDFF_PP0_  (.D(_0209_),
    .Q(\core.tick_counter[6] ),
    .CLK(clknet_4_0_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[7]$_SDFF_PP0_  (.D(_0210_),
    .Q(\core.tick_counter[7] ),
    .CLK(clknet_4_0_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[8]$_SDFF_PP0_  (.D(_0211_),
    .Q(\core.tick_counter[8] ),
    .CLK(clknet_4_0_0_clk));
 sky130_fd_sc_hd__dfxtp_1 \core.tick_counter[9]$_SDFF_PP0_  (.D(_0212_),
    .Q(\core.tick_counter[9] ),
    .CLK(clknet_4_0_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.tone_sequence_counter[0]$_DFFE_PP_  (.D(_0215_),
    .DE(_0006_),
    .Q(\core.tone_sequence_counter[0] ),
    .CLK(clknet_4_2_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.tone_sequence_counter[1]$_DFFE_PP_  (.D(_0216_),
    .DE(_0006_),
    .Q(\core.tone_sequence_counter[1] ),
    .CLK(clknet_4_2_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.tone_sequence_counter[2]$_DFFE_PP_  (.D(_0217_),
    .DE(_0006_),
    .Q(\core.tone_sequence_counter[2] ),
    .CLK(clknet_4_2_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.user_input[0]$_DFFE_PP_  (.D(_0213_),
    .DE(_0005_),
    .Q(\core.user_input[0] ),
    .CLK(clknet_4_11_0_clk));
 sky130_fd_sc_hd__edfxtp_1 \core.user_input[1]$_DFFE_PP_  (.D(_0214_),
    .DE(_0005_),
    .Q(\core.user_input[1] ),
    .CLK(clknet_4_11_0_clk));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input1 (.A(btn[0]),
    .X(net1));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input2 (.A(btn[1]),
    .X(net2));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input3 (.A(btn[2]),
    .X(net3));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input4 (.A(btn[3]),
    .X(net4));
 sky130_fd_sc_hd__clkdlybuf4s50_1 input5 (.A(rst_n),
    .X(net5));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output10 (.A(net10),
    .X(led[0]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output11 (.A(net11),
    .X(led[1]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output12 (.A(net12),
    .X(led[2]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output13 (.A(net13),
    .X(led[3]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output14 (.A(net14),
    .X(level[0]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output15 (.A(net15),
    .X(level[1]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output16 (.A(net16),
    .X(level[2]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output17 (.A(net17),
    .X(level[3]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output18 (.A(net18),
    .X(level[4]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output19 (.A(net19),
    .X(segment_digits[0]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output20 (.A(net20),
    .X(segment_digits[1]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output21 (.A(net21),
    .X(segments[0]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output22 (.A(net22),
    .X(segments[1]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output23 (.A(net23),
    .X(segments[2]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output24 (.A(net24),
    .X(segments[3]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output25 (.A(net25),
    .X(segments[4]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output26 (.A(net26),
    .X(segments[5]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output27 (.A(net27),
    .X(segments[6]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output28 (.A(net28),
    .X(sound));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output6 (.A(net48),
    .X(dbg_state[0]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output7 (.A(net7),
    .X(dbg_state[1]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output8 (.A(net47),
    .X(dbg_state[2]));
 sky130_fd_sc_hd__clkdlybuf4s50_1 output9 (.A(net9),
    .X(game_over));
 sky130_fd_sc_hd__buf_4 place39 (.A(_0801_),
    .X(net39));
 sky130_fd_sc_hd__buf_4 place40 (.A(_0405_),
    .X(net40));
 sky130_fd_sc_hd__buf_4 place41 (.A(_0008_),
    .X(net41));
 sky130_fd_sc_hd__buf_4 place42 (.A(_0007_),
    .X(net42));
 sky130_fd_sc_hd__buf_4 place43 (.A(_0858_),
    .X(net43));
 sky130_fd_sc_hd__buf_4 place44 (.A(_0826_),
    .X(net44));
 sky130_fd_sc_hd__buf_4 place45 (.A(_0640_),
    .X(net45));
 sky130_fd_sc_hd__buf_4 place46 (.A(_0498_),
    .X(net46));
 sky130_fd_sc_hd__buf_4 place47 (.A(net8),
    .X(net47));
 sky130_fd_sc_hd__buf_4 place48 (.A(net6),
    .X(net48));
 sky130_fd_sc_hd__buf_4 place49 (.A(_0000_),
    .X(net49));
 sky130_fd_sc_hd__buf_4 place50 (.A(_0492_),
    .X(net50));
 sky130_fd_sc_hd__buf_4 place51 (.A(net5),
    .X(net51));
endmodule
