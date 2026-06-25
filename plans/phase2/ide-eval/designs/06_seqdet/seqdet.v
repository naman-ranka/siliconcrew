// Moore FSM: detects overlapping bit sequence 1011 on serial input `din`.
module seqdet (
    input  wire clk,
    input  wire rst_n,
    input  wire din,
    output wire found
);
    localparam S0=3'd0, S1=3'd1, S10=3'd2, S101=3'd3, S1011=3'd4;
    reg [2:0] state, nxt;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) state <= S0; else state <= nxt;
    always @(*) begin
        case (state)
            S0:    nxt = din ? S1   : S0;
            S1:    nxt = din ? S1   : S10;
            S10:   nxt = din ? S101 : S0;
            S101:  nxt = din ? S1011: S10;
            S1011: nxt = din ? S1   : S10;
            default nxt = S0;
        endcase
    end
    assign found = (state == S1011);
endmodule
