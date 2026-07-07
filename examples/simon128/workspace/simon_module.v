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
// Create Date:    19:14:37 11/13/2013 
// Design Name: 
// Module Name:    top_module 
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
module simon_module(clk,reset,data_in,data_rdy,cipher_out,valid);
   
   input clk,data_in,reset;
   input [1:0] data_rdy;
   output reg  cipher_out;
   output 	   valid;
   
   wire 	   key;
   wire 	   cipher_data;
   wire [5:0]  bit_counter;
   wire [6:0]  round_counter;

   simon_datapath_shiftreg datapath(.clk(clk), 
									.reset(reset),
									.data_in(data_in), 
									.data_rdy(data_rdy), 
									.key_in(key), 
									.cipher_out(cipher_data), 
									.round_counter(round_counter), 
									.bit_counter(bit_counter),
									.valid(valid));
   
   // FIXED KEY IMPLEMENTATION TO KEY VALUE 00000000_00000000_00000000_00000000
   // THIS DESIGN FORCES ALL KEY BITS TO 0 UPON LOADING

   (*keep = "true" *)  wire zero;
   assign zero = 1'b0;
   
   simon_key_expansion_shiftreg key_exp(.clk(clk), 
										.reset(reset), 
										.data_in(zero),   // was: data_in 
										.data_rdy(data_rdy), 
										.key_out(key), 
										.bit_counter(bit_counter), 
										.round_counter(round_counter));

   assign cipher_out = cipher_data;
   

endmodule
