// Simon Says memory game — clean-port top for the SiliconCrew showcase.
//
// Adapted from Uri Shaked's Tiny Tapeout TT06 project `tt06-simon-game`
//   repo:    https://github.com/urish/tt06-simon-game
//   commit:  37f3538ba18fb3eeea73ad37d0f36e631189ae75
// The game core (simon/score/play) lives in simon.v; that file's per-file
// license is MIT (© 2023 Uri Shaked), the repo LICENSE is Apache-2.0 — both are
// shipped/attributed in this bundle (see LICENSE and spec.md).
//
// Adaptation: the upstream chip wraps the game in the fixed Tiny Tapeout pin
// interface (ui_in/uo_out/uio_*/ena). This top exposes real named ports and
// makes the game's "milliseconds" tunable via the TICKS_PER_MILLI parameter so
// simulation can tick fast while synthesis uses the real (50 kHz clock) value.
// Reset is active-low (rst_n, platform convention) and inverted to the core's
// active-high rst.
`default_nettype none

module simon_game #(
    // Clock ticks per game-millisecond. Upstream ties this to 50 (a 50 kHz
    // clock); a self-checking TB overrides it to a small value for fast sim.
    parameter [15:0] TICKS_PER_MILLI = 16'd50
) (
    input  wire       clk,
    input  wire       rst_n,           // active-low synchronous reset
    input  wire [3:0] btn,             // btn1..btn4 (one-hot press)
    output wire [3:0] led,             // led1..led4 (sequence playback / echo)
    output wire       sound,           // buzzer square wave
    output wire [6:0] segments,        // 7-segment score digit (active-high)
    output wire [1:0] segment_digits,  // which score digit is driven (mux)
    output wire       game_over,       // high when the player lost
    output wire [4:0] level,           // rounds survived (score)
    output wire [2:0] dbg_state         // raw FSM state (observability)
);

    simon core (
        .clk             (clk),
        .rst             (~rst_n),
        .ticks_per_milli (TICKS_PER_MILLI),
        .btn             (btn),
        .segments_invert (1'b0),        // common-cathode: active-high segments
        .led             (led),
        .sound           (sound),
        .segments        (segments),
        .segment_digits  (segment_digits),
        .game_over       (game_over),
        .level           (level),
        .dbg_state       (dbg_state)
    );

endmodule
