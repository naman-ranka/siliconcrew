// Self-checking testbench for the Simon Says memory game (simon_game).
//
// Original to this SiliconCrew bundle (NOT adapted from upstream). It plays a
// full game deterministically through the design's real I/O contract:
//
//   1. Reset, then press a button during power-on to seed + start the game.
//   2. ROUND 1: OBSERVE the LED playback to learn the 1-symbol sequence, then
//      replay it correctly on the buttons. Assert the round advances
//      (level 1 -> 2) and the game is NOT over.
//   3. ROUND 2: OBSERVE the 2-symbol playback. Assert Simon shows the SAME
//      first symbol as round 1 plus one new one (the game's growing-sequence
//      invariant). Then deliberately press the WRONG button on the first
//      symbol and assert the design enters game-over.
//
// The oracle is independent of the DUT's internal RNG: the testbench never
// hard-codes the sequence, it reads it back from the LEDs and replays it, so
// the run is fully deterministic (fixed clock + fixed press timing) yet checks
// real game behaviour. TICKS_PER_MILLI is overridden small so the game's
// "milliseconds" tick fast in simulation.
`default_nettype none
`timescale 1ns / 1ps

module simon_game_tb;

  // FSM state encodings (mirror simon.v localparams; observed via dbg_state).
  localparam [2:0] S_POWERON   = 3'd0;
  localparam [2:0] S_INIT      = 3'd1;
  localparam [2:0] S_PLAY      = 3'd2;
  localparam [2:0] S_PLAYWAIT  = 3'd3;
  localparam [2:0] S_USERWAIT  = 3'd4;
  localparam [2:0] S_USERINPUT = 3'd5;
  localparam [2:0] S_NEXTLEVEL = 3'd6;
  localparam [2:0] S_GAMEOVER  = 3'd7;

  reg        clk = 1'b0;
  reg        rst_n;
  reg  [3:0] btn;

  wire [3:0] led;
  wire       sound;
  wire [6:0] segments;
  wire [1:0] segment_digits;
  wire       game_over;
  wire [4:0] level;
  wire [2:0] dbg_state;

  integer errors = 0;
  integer i;
  reg [1:0] obs_seq [0:31];   // sequence learned by watching the LEDs
  reg [1:0] r1_sym0;
  reg [4:0] level_before;
  reg [1:0] wrong_sym;

  // Fast game-millisecond so the whole game runs in a few thousand clocks.
  simon_game #(.TICKS_PER_MILLI(16'd2)) dut (
      .clk            (clk),
      .rst_n          (rst_n),
      .btn            (btn),
      .led            (led),
      .sound          (sound),
      .segments       (segments),
      .segment_digits (segment_digits),
      .game_over      (game_over),
      .level          (level),
      .dbg_state      (dbg_state)
  );

  // 10 ns clock.
  always #5 clk = ~clk;

  // Watchdog: fail loudly instead of hanging if the game never progresses.
  initial begin
    #2_000_000;  // 2 ms sim time = 200k clocks; the game needs ~7k
    $display("TIMEOUT: game did not finish in time -- TEST FAILED");
    $finish;
  end

  // Decode a one-hot LED value to a 0..3 symbol index.
  function [1:0] decode_led(input [3:0] l);
    begin
      case (l)
        4'b0001: decode_led = 2'd0;
        4'b0010: decode_led = 2'd1;
        4'b0100: decode_led = 2'd2;
        4'b1000: decode_led = 2'd3;
        default: decode_led = 2'd0;  // should not happen mid-playback
      endcase
    end
  endfunction

  task check(input cond, input [255:0] msg);
    begin
      if (!cond) begin
        errors = errors + 1;
        $display("CHECK FAILED: %0s (t=%0t, state=%0d, led=%b, level=%0d)",
                 msg, $time, dbg_state, led, level);
      end
    end
  endtask

  // Watch the LED playback and record `n` symbols into obs_seq[0..n-1].
  // Each symbol is one StatePlay cycle; the LED is one-hot in the following
  // StatePlayWait cycle.
  task observe_round(input integer n);
    integer got;
    begin
      got = 0;
      while (got < n) begin
        @(posedge clk);
        if (dbg_state == S_PLAY) begin
          @(posedge clk);                 // advance into StatePlayWait
          check(led == 4'b0001 || led == 4'b0010 || led == 4'b0100 || led == 4'b1000,
                "playback LED is not one-hot");
          obs_seq[got] = decode_led(led);
          got = got + 1;
        end
      end
    end
  endtask

  // Press one button (one-hot from `sym`), then wait out the echo until the
  // design reaches a decision state (UserWait / NextLevel / GameOver).
  task press_symbol(input [1:0] sym);
    begin
      @(posedge clk);
      while (dbg_state != S_USERWAIT) @(posedge clk);
      btn = (4'b0001 << sym);
      @(posedge clk);
      while (dbg_state == S_USERWAIT) @(posedge clk);  // -> StateUserInput
      btn = 4'b0000;
      while (dbg_state == S_USERINPUT) @(posedge clk); // -> decision state
    end
  endtask

  initial begin
    $dumpfile("simon_game_tb.vcd");
    $dumpvars(0, simon_game_tb);

    // --- Reset ---
    rst_n = 1'b0;
    btn   = 4'b0000;
    repeat (6) @(posedge clk);
    rst_n = 1'b1;
    @(posedge clk);

    // --- Power-on: press a button to seed the RNG and start the game ---
    while (dbg_state != S_POWERON) @(posedge clk);
    repeat (20) @(posedge clk);           // let time pass so the seed varies
    btn = 4'b0001;
    while (dbg_state == S_POWERON) @(posedge clk);  // -> StateInit
    btn = 4'b0000;

    // --- ROUND 1: one symbol ---
    observe_round(1);
    r1_sym0 = obs_seq[0];
    level_before = level;                 // = 1 after StateInit
    check(level_before == 5'd1, "level should be 1 during round 1");
    check(!game_over, "game_over asserted during round 1 playback");

    press_symbol(obs_seq[0]);             // replay correctly (last symbol)
    check(dbg_state == S_NEXTLEVEL, "round 1 correct input did not reach NextLevel");
    check(!game_over, "unexpected game_over after a correct round 1");
    check(level == 5'd2, "level did not advance to 2 after round 1");

    // --- ROUND 2: two symbols, growing-sequence invariant, then a wrong input ---
    observe_round(2);
    check(obs_seq[0] == r1_sym0,
          "round 2 did not replay round 1's first symbol (growing-sequence broken)");

    wrong_sym = (r1_sym0 + 2'd1);         // any symbol != the correct one
    press_symbol(wrong_sym);              // deliberately wrong
    check(dbg_state == S_GAMEOVER, "wrong input did not cause game over");
    check(game_over, "game_over not asserted after a wrong input");

    // --- Verdict ---
    if (errors == 0)
      $display("TEST PASSED");
    else
      $display("TEST FAILED: %0d check(s) failed", errors);
    $finish;
  end

endmodule
