// sn74169 — 4-bit synchronous up/down binary counter (TTL '169 functional replica).
//
// Adapted from a Tiny Tapeout TT08 project:
//   repo:    https://github.com/andychip1/sn74169
//   commit:  cdab2c267cc94306c23f4e0c6a62559c30e6bed3
//   license: Apache-2.0 (see LICENSE in this bundle)
//
// Adaptation: upstream ships this synthesizable core (`sn74169`) with a thin
// Tiny Tapeout wrapper (`tt_um_andychip1_sn74169`) that maps the control/data
// pins onto ui_in/uo_out. This bundle drops that pin wrapper and uses the core
// directly as the top module — its ports are already the real '169 interface.
// The counter logic is kept VERBATIM; only this attribution header was added.
//
// Behaviour (active-low controls, matching the TTL part):
//   * LOADB=0            -> synchronous parallel load  Q <= A
//   * LOADB=1, ENPB=ENTB=0 -> count: U_DB=1 up, U_DB=0 down
//   * otherwise          -> hold
//   * RCOB (ripple-carry out, active low) pulses low at terminal count
//     (Q=15 while counting up, or Q=0 while counting down).

module sn74169(
           input  [3:0] A,
           input  U_DB, input CLK, input ENPB, input ENTB, input LOADB,
	   output reg [3:0] Q,
	   output RCOB
    );

 // loadb=0: load
 // NOR(enpb, entb) and U_DB: count up
 //                and !U_DB: count down

    always @(posedge CLK)
	begin
        if(!LOADB)
     		Q = A;
	else
		if (!ENPB && !ENTB)
			if(U_DB)
				Q=Q+1;
			else
				Q=Q-1;
		end

	assign RCOB = !( (Q[3]&Q[2]&Q[1]&Q[0]&U_DB) | (!Q[3]&!Q[2]&!Q[1]&!Q[0]&!U_DB));


endmodule
