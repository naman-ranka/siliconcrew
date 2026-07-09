// Simon-128/128 bit-serial block cipher (fixed all-zero key) — core module.
//
// Adapted (verbatim RTL) from the Tiny Tapeout TT08 project tt08-simon by
// Secure-Embedded-Systems.
//   repo:    https://github.com/Secure-Embedded-Systems/tt08-simon
//   commit:  6450fdcaf20be715c022ab28d12d43d5afe90193
//   license: Apache-2.0 (repo LICENSE; the top wrapper tt_um_simon_cipher.v
//            carries an SPDX-License-Identifier: Apache-2.0, (c) 2024
//            Secure Embedded Systems). Full LICENSE shipped at the bundle root.
// Adaptation: the Tiny Tapeout tt_um_* pin wrapper is replaced by a clean-port
//   top (simon128_cipher.v); this datapath/key-expansion/top RTL is unchanged.
//   The self-checking testbench (simon128_cipher_tb.v) is original to this
//   bundle and checks the project's own published known-answer vectors.
//
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date:    17:21:26 11/13/2013 
// Design Name: 
// Module Name:    simon_datapath_shiftreg 
// Project Name: 
// Target Devices: 
// Tool versions: 
// Description: 
//
// Dependencies: 
//
// Revision: 
// Revision 0.01 - File Created
// Additional Comments: 
//
//////////////////////////////////////////////////////////////////////////////////
module simon_datapath_shiftreg(clk,reset,data_in,data_rdy,key_in,cipher_out,round_counter,bit_counter,valid);

   input clk,data_in,key_in,reset;
   input [1:0] data_rdy;
   input [6:0] round_counter;
   output 	   cipher_out;
   output [5:0] bit_counter;
   output 		valid;
   
   reg [55:0] 	shifter1;
   reg [63:0] 	shifter2;
   reg 			shift_in1,shift_in2;
   wire 		shift_out1,shift_out2;
   reg 			shifter_enable1,shifter_enable2;
   
   reg 			fifo_ff63,fifo_ff62,fifo_ff61,fifo_ff60,fifo_ff59,fifo_ff58,fifo_ff57,fifo_ff56;
   reg 			lut_ff63,lut_ff62,lut_ff61,lut_ff60,lut_ff59,lut_ff58,lut_ff57,lut_ff56;
   
   reg 			lut_ff_input,fifo_ff_input;
   reg 			lut_rol1,lut_rol2,lut_rol8;
   reg 			s1,s4,s5,s6,s7;
   reg [1:0] 	s3;
   reg [5:0] 	bit_counter;
   wire 		lut_out;
   reg 			valid;
   
   
   // synopsys sync_set_reset "reset"
   // Shift Register1 FIFO 56x1 Begin
   always @(posedge clk)
	 begin
		
		if(!reset)
		  shifter1 <= 56'd0;
		
		else if(shifter_enable1)
		  shifter1 <= {shift_in1, shifter1[55:1]};
	 end
   
   assign shift_out1 = shifter1[0];
   // Shift Register1 End
   
   // Shift Register2 FIFO 64x1 Begin
   // synopsys sync_set_reset "reset"
   always @(posedge clk)
	 begin
		if(!reset)
		  shifter2 <= 64'd0;
		else if(shifter_enable2)
		  shifter2 <= {shift_in2, shifter2[63:1]};
	 end
   
   assign shift_out2 = shifter2[0];
   // Shift Register1 End
   
   always@(posedge clk)
	 begin
		if(!reset)
		  begin
			 fifo_ff63 <= 0;
			 fifo_ff62 <= 0;
			 fifo_ff61 <= 0;
			 fifo_ff60 <= 0;
			 fifo_ff59 <= 0;
			 fifo_ff58 <= 0;
			 fifo_ff57 <= 0;
			 fifo_ff56 <= 0;
		  end
		
		else if(shifter_enable1)
		  begin
			 fifo_ff63 <= fifo_ff_input;
			 fifo_ff62 <= fifo_ff63;
			 fifo_ff61 <= fifo_ff62;
			 fifo_ff60 <= fifo_ff61;
			 fifo_ff59 <= fifo_ff60;
			 fifo_ff58 <= fifo_ff59;
			 fifo_ff57 <= fifo_ff58;
			 fifo_ff56 <= fifo_ff57;
		  end
	 end
   
   always@(posedge clk)
	 begin
		if(!reset)
		  begin
			 lut_ff63 <= 0;
			 lut_ff62 <= 0;
			 lut_ff61 <= 0;
			 lut_ff60 <= 0;
			 lut_ff59 <= 0;
			 lut_ff58 <= 0;
			 lut_ff57 <= 0;
			 lut_ff56 <= 0;
		  end
		
		else
		  begin
			 lut_ff63 <= lut_ff_input;
			 lut_ff62 <= lut_ff63;
			 lut_ff61 <= lut_ff62;
			 lut_ff60 <= lut_ff61;
			 lut_ff59 <= lut_ff60;
			 lut_ff58 <= lut_ff59;
			 lut_ff57 <= lut_ff58;
			 lut_ff56 <= lut_ff57;
		  end
	 end
   
   //FIFO 64x1 Input MUX
   always@(*)
	 begin
		shift_in2 = shift_out1;
	 end
   
   //FIFO 56x1 Input MUX
   always@(*)
	 begin
		if(s1==0)
		  shift_in1 = lut_ff56;
		else
		  shift_in1 = fifo_ff56;
	 end
   
   //FIFO FF Input MUX
   always@(*)
	 begin
		if(s3==0)
		  fifo_ff_input = data_in;
		else if(s3==1)
		  fifo_ff_input = shift_out1;
		else if(s3==2)
		  fifo_ff_input = lut_out;
		else
		  fifo_ff_input = 1'bx;
	 end
   
   //LUT FF Input MUX
   always@(*)
	 begin
		if(s5==0)
		  lut_ff_input = shift_out1;
		else
		  lut_ff_input = lut_out;
	 end
   
   //LUT Input MUX
   always@(*)
	 begin
		if(s7==0)
		  lut_rol1 = fifo_ff63;
		else
		  lut_rol1 = lut_ff63;
		
		if(s4==0)
		  lut_rol2 = fifo_ff62;
		else
		  lut_rol2 = lut_ff62;
		
		if(s6==0)
		  lut_rol8 = fifo_ff56;
		else
		  lut_rol8 = lut_ff56;
	 end
   
   //Selection MUX
   always@(*)
	 begin
		if((round_counter[0]==0 && bit_counter<8)||(round_counter[0]==1 && bit_counter>7)||(data_rdy==1))
		  s1 = 1;
		else 
		  s1 = 0;
		
		if(data_rdy==1)
		  s3 = 0;
		else if(round_counter[0]==0)
		  s3 = 1;
		else if(round_counter[0]==1)
		  s3 = 2;
		else 
		  s3 = 1'bx;
		
		if(round_counter[0]==0)
		  s6 = 0;
		else
		  s6 = 1;
		
		s4 = s6;
		s7 = s6;
		s5 = ~s6;
	 end
   
   //SHIFTER ENABLES
   always@(*)
	 begin
		if(data_rdy==1 || data_rdy==3)
		  shifter_enable2 = 1;
		else
		  shifter_enable2 = 0;
		
		if(data_rdy==1 || data_rdy==3)
		  shifter_enable1 = 1;
		else
		  shifter_enable1 = 0;
		
	 end
   
   // synopsys sync_set_reset "reset"
   always@(posedge clk)
	 begin
		if(!reset)
		  bit_counter <= 0;
		else if(data_rdy==0)
		  bit_counter <= 0;
		else if(data_rdy==3)
		  bit_counter <= bit_counter + 1;
		else 
		  bit_counter <= bit_counter;
	 end
   
   assign lut_out = (lut_rol1 & lut_rol8) ^ shift_out2 ^ lut_rol2 ^ key_in;
   
   assign cipher_out = shift_out2;
   
   always@(*)
	 begin
		if(round_counter==68 || round_counter==69)
		  valid = 1;
		else
		  valid = 0;
	 end

endmodule
