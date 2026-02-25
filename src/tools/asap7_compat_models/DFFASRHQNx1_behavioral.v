// Behavioral replacement for DFFASRHQNx1_ASAP7_75t_R.
// This avoids delayed/timing-check behavior that often leaves QN as X in Icarus.
module DFFASRHQNx1_ASAP7_75t_R (
    output QN,
    input D,
    input RESETN,
    input SETN,
    input CLK
);
  reg q;
  always @(posedge CLK or negedge RESETN or negedge SETN) begin
    if (!RESETN) q <= 1'b0;
    else if (!SETN) q <= 1'b1;
    else q <= D;
  end
  assign QN = ~q;
endmodule
