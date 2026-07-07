// Seven-segment seconds counter.
//
// Adapted from Tiny Tapeout's tt05-verilog-demo
//   repo:    https://github.com/TinyTapeout/tt05-verilog-demo
//   commit:  a7e71a2f1b954fff59597838ef1453dba01f8861
//   license: Apache-2.0 (see LICENSE in this bundle)
//
// Adaptation: the original `tt_um_seven_segment_seconds` wraps the logic in the
// fixed Tiny Tapeout pin interface (ui_in/uo_out/uio_*/ena). This version keeps
// the same counter + BCD digit + 7-seg decoder logic but exposes real ports —
// a free-running clock divider (MAX_COUNT) ticks a 0-9 BCD digit, decoded onto
// the seven-segment output `seg`. Reduce MAX_COUNT to make the digit tick fast
// in simulation. Async-free, active-low synchronous reset `rst_n`.
`default_nettype none

module seven_segment_seconds #(
    parameter [23:0] MAX_COUNT = 24'd10_000_000  // clk ticks per BCD increment
) (
    input  wire       clk,
    input  wire       rst_n,   // active-low reset (synchronous)
    output wire [6:0] seg      // 7-segment segments for the current digit
);
    reg [23:0] second_counter;
    reg [3:0]  digit;          // current BCD digit, 0-9

    always @(posedge clk) begin
        if (!rst_n) begin
            second_counter <= 24'd0;
            digit          <= 4'd0;
        end else if (second_counter == MAX_COUNT) begin
            second_counter <= 24'd0;
            if (digit == 4'd9) digit <= 4'd0;      // wrap 9 -> 0
            else               digit <= digit + 4'd1;
        end else begin
            second_counter <= second_counter + 24'd1;
        end
    end

    seg7 seg7_inst (.counter(digit), .segments(seg));
endmodule
