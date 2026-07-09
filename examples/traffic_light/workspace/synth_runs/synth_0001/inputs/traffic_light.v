// 3-state traffic-light controller (Moore FSM). Cycles GREEN -> YELLOW -> RED,
// holding each phase for a parameterized number of clock ticks. Exactly one of
// the three light outputs is asserted every cycle (one-hot), so the outputs can
// drive three LEDs directly. Async active-low reset returns to GREEN with a
// fresh phase timer.
module traffic_light #(
    parameter integer GREEN_TICKS  = 8,
    parameter integer YELLOW_TICKS = 3,
    parameter integer RED_TICKS    = 8
) (
    input  wire clk,
    input  wire rst_n,
    output reg  green,
    output reg  yellow,
    output reg  red
);
    localparam [1:0] S_GREEN  = 2'd0,
                     S_YELLOW = 2'd1,
                     S_RED    = 2'd2;

    reg [1:0]  state;
    reg [31:0] timer;   // clock ticks remaining in the current phase

    // Sequential FSM: hold the phase while the timer is non-zero, then advance
    // to the next phase and reload its tick count. A phase that lasts N ticks is
    // entered with timer = N-1 (the entry cycle itself counts).
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= S_GREEN;
            timer <= GREEN_TICKS - 1;
        end else if (timer != 0) begin
            timer <= timer - 1'b1;
        end else begin
            case (state)
                S_GREEN:  begin state <= S_YELLOW; timer <= YELLOW_TICKS - 1; end
                S_YELLOW: begin state <= S_RED;    timer <= RED_TICKS    - 1; end
                S_RED:    begin state <= S_GREEN;  timer <= GREEN_TICKS  - 1; end
                default:  begin state <= S_GREEN;  timer <= GREEN_TICKS  - 1; end
            endcase
        end
    end

    // Moore outputs: one-hot decode of the current state.
    always @(*) begin
        green  = (state == S_GREEN);
        yellow = (state == S_YELLOW);
        red    = (state == S_RED);
    end
endmodule
