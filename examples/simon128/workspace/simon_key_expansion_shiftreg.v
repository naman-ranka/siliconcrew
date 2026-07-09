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
// Create Date:    16:55:06 11/12/2013 
// Design Name: 
// Module Name:    simon_key_expansion_shiftreg 
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

module simon_key_expansion_shiftreg(clk,
									reset,
									data_in,
									key_out,
									data_rdy,
									bit_counter,
									round_counter);

   input clk,reset;
   input data_in;
   input [1:0] data_rdy;
   input [5:0] bit_counter;
   output 	   key_out;
   output [6:0] round_counter;
   
   reg [59:0] 	shifter1;
   reg [63:0] 	shifter2;
   reg 			shift_in1,shift_in2;
   wire 		shift_out1,shift_out2;
   reg 			shifter_enable1,shifter_enable2;
   
   reg 			lut_ff_enable,fifo_ff_enable;
   wire 		lut_out;
   reg 			lut_in3;
   reg 			s2;
   reg [1:0] 	s1;
   reg [6:0] 	round_counter;
   reg 			z_value;
   
   reg 			fifo_ff0,fifo_ff1,fifo_ff2,fifo_ff3;
   
   
   reg 			lut_ff0,lut_ff1,lut_ff2,lut_ff3;
   reg 			c;

   //Constant value Z
   wire [0:67] 	Z;
   
   assign Z = 68'b10101111011100000011010010011000101000010001111110010110110011101011;
   
   // Shift Register1 FIFO 60x1 Begin
   // synopsys sync_set_reset "reset"
   always @(posedge clk)
	 begin
		if(!reset)
		  shifter1 <= 60'd0;
		
		else if(shifter_enable1)
		  shifter1 <= {shift_in1, shifter1[59:1]};	
	 end
   
   assign shift_out1 = shifter1[0];
   // Shift Register1 End
   
   // Shift Register2 FIFO 64x1 Begin
   // synopsys sync_set_reset "reset"
   always @(posedge clk)
	 begin
		if(!reset)
		  shifter2<= 63'd0;
		else if(shifter_enable2)
		  shifter2 <= {shift_in2, shifter2[63:1]};
	 end
   
   assign shift_out2 = shifter2[0];
   // Shift Register2 End
   
   // synopsys sync_set_reset "reset"
   always @(posedge clk)
	 begin
		if(!reset)
		  begin
			 fifo_ff3 <= 0;
			 fifo_ff2 <= 0;
			 fifo_ff1 <= 0;
			 fifo_ff0 <= 0;
		  end
		else if(fifo_ff_enable)
		  begin
			 fifo_ff3 <= shift_out1;
			 fifo_ff2 <= fifo_ff3;
			 fifo_ff1 <= fifo_ff2;
			 fifo_ff0 <= fifo_ff1;
		  end
		
	 end
   
   // synopsys sync_set_reset "reset"
   always@(posedge clk)
	 begin
		if(!reset)
		  begin
			 lut_ff3 <= 0;
			 lut_ff2 <= 0;
			 lut_ff1 <= 0;
			 lut_ff0 <= 0;
		  end
		else if(lut_ff_enable)
		  begin
			 lut_ff3 <= lut_out;
			 lut_ff2 <= lut_ff3;
			 lut_ff1 <= lut_ff2;
			 lut_ff0 <= lut_ff1;
		  end
		
	 end
   
   //FIFO 64x1 Input MUX
   always@(*)
	 begin
		if(data_rdy==2)
		  shift_in2 = fifo_ff0;
		else if(data_rdy==3 && (round_counter<1 || bit_counter>3))
		  shift_in2 = fifo_ff0;
		else if(data_rdy==3 && bit_counter<4 && round_counter>0) // NEW ADDED
		  shift_in2 = lut_ff0; // NEW ADDED
		else
		  shift_in2 = 1'bx;
	 end
   
   //LUT >>3 Input MUX
   always@(*)
	 begin
		if(s2==0)
		  lut_in3 = fifo_ff3;
		else
		  lut_in3 = lut_ff3;
	 end
   
   //FIFO 60x1 Input MUX
   always@(*)
	 begin
		if(s1==0)
		  shift_in1 = fifo_ff0;

		else if(s1==1 || data_rdy==2)
		  shift_in1 = data_in;

		else if(s1==2)
		  shift_in1 = lut_out;
		else if(s1==3)
		  shift_in1 = lut_ff0;
		else
		  shift_in1 = 1'b0;
	 end
   
   //S2 MUX
   always@(*)
	 begin
		if(bit_counter==0 && round_counter!=0)
		  s2 = 1;
		else
		  s2 = 0;
	 end
   
   //S1 MUX
   always@(*)
	 begin
		if(data_rdy==2)
		  s1 = 1;
		else if(data_rdy==3 && bit_counter<4 && round_counter==0)
		  s1 = 0;
		else if(data_rdy==3 && bit_counter<4 && round_counter>0)
		  s1 = 3;
		else
		  s1 = 2;
	 end
   
   //LUT FF ENABLE MUX
   always@(*)
	 begin
		if(data_rdy==3 && bit_counter<4)
		  lut_ff_enable = 1;
		else
		  lut_ff_enable = 0;
	 end
   
   //FIFO FF ENABLE MUX
   always@(*)
	 begin
		if(data_rdy==2 || data_rdy==3)
		  fifo_ff_enable = 1;
		else
		  fifo_ff_enable = 0;
	 end
   
   //SHIFTER ENABLES
   always@(*)
	 begin
		if(data_rdy==2 || data_rdy==3)
		  shifter_enable1 = 1;
		else
		  shifter_enable1 = 0;
		
		if(data_rdy==2 || data_rdy==3)
		  shifter_enable2 = 1;
		else
		  shifter_enable2 = 0;
		
	 end
   
   //Round Counter
   // synopsys sync_set_reset "reset"
   always@(posedge clk)
	 begin
		if(!reset)
		  round_counter <= 0;
		else if(data_rdy==3 && bit_counter==63)
		  round_counter <= round_counter + 1;
		else if(data_rdy==0)
		  round_counter <= 0;
		else
		  round_counter <= round_counter;
	 end
 
   
   always @(*)
	 begin
		if(bit_counter==0)
		  z_value = Z[round_counter];
		else
		  z_value = 0;
	 end
    
   always @(*)
	 begin
		if(bit_counter==0 || bit_counter==1)
		  c = 0;
		else 
		  c = 1;
	 end
   
   assign lut_out = shift_out2 ^ lut_in3 ^ shift_out1 ^ z_value ^ c;
   
   assign key_out = shift_out2;
   
endmodule
