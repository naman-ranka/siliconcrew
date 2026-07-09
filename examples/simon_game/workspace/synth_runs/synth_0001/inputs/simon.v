// Simon Says memory game — core game FSM, score (7-seg) and tone (buzzer) units.
//
// SPDX-FileCopyrightText: © 2023 Uri Shaked <uri@wokwi.com>
// SPDX-License-Identifier: MIT
//
// -----------------------------------------------------------------------------
// Provenance / adaptation note (SiliconCrew showcase bundle)
// -----------------------------------------------------------------------------
// Source repo:   https://github.com/urish/tt06-simon-game
//   commit:      37f3538ba18fb3eeea73ad37d0f36e631189ae75  (Tiny Tapeout TT06)
//   file:        src/simon.v  (this file's upstream original)
// Licensing:     the source file carries the MIT SPDX header above (the author's
//                own per-file license). The repository's LICENSE file is the
//                stock Tiny Tapeout Apache-2.0 template (copied to LICENSE at this
//                bundle root). BOTH are permissive; the MIT copyright/notice is
//                preserved here, and the Apache-2.0 repo license is shipped too.
//                The full MIT permission notice is reproduced at the bottom of
//                this file to satisfy MIT's "include this notice" clause.
// Adaptation:    (1) dropped the upstream `wokwi` module (a Wokwi-simulator top,
//                not part of the chip design); (2) added three observability taps
//                to `simon` — `game_over`, `level`, `dbg_state` — so a
//                self-checking testbench has a deterministic oracle (see the
//                original `state`/`seq_length` regs; the taps are pure reads, no
//                behavioural change). The `score` and `play` back-ends are kept
//                verbatim. The clean-port top lives in simon_game.v; the
//                self-checking testbench (simon_game_tb.v) is original to this
//                bundle.
// -----------------------------------------------------------------------------

`default_nettype none

/* verilator lint_off UNUSED */

module score (
    input wire clk,
    input wire rst,
    input wire ena,
    input wire invert,
    input wire inc,
    output reg [6:0] segments,
    output reg [1:0] digits
);
  reg active_digit;
  reg [3:0] ones;
  reg [3:0] tens;
  wire [3:0] digit_value = active_digit ? tens : ones;

  always @(posedge clk) begin
    active_digit <= ~active_digit;

    if (rst) begin
      ones <= 0;
      tens <= 0;
      active_digit <= 0;
    end else if (inc) begin
      ones <= ones + 1;
      if (ones == 9) begin
        ones <= 0;
        tens <= tens + 1;
        if (tens == 9) begin
          tens <= 0;
        end
      end
    end

    case(active_digit)
      1'b0: digits <= invert ? 2'b10 : 2'b01;
      1'b1: digits <= invert ? 2'b01 : 2'b10;
    endcase

    case (ena ? digit_value : 4'd15)
      4'd0: segments <= invert ? 7'b1000000 : 7'b0111111;
      4'd1: segments <= invert ? 7'b1111001 : 7'b0000110;
      4'd2: segments <= invert ? 7'b0100100 : 7'b1011011;
      4'd3: segments <= invert ? 7'b0110000 : 7'b1001111;
      4'd4: segments <= invert ? 7'b0011001 : 7'b1100110;
      4'd5: segments <= invert ? 7'b0010010 : 7'b1101101;
      4'd6: segments <= invert ? 7'b0000010 : 7'b1111101;
      4'd7: segments <= invert ? 7'b1111000 : 7'b0000111;
      4'd8: segments <= invert ? 7'b0000000 : 7'b1111111;
      4'd9: segments <= invert ? 7'b0010000 : 7'b1101111;
      default: segments <= invert ? 7'b1111111 : 7'b0000000;
    endcase
  end

endmodule


module play (
    input wire clk,
    input wire rst,
    input wire [15:0] ticks_per_milli,
    input wire [9:0] freq,
    output reg sound
);
  reg [31:0] tick_counter;
  wire [31:0] ticks_per_second = ticks_per_milli * 1000;
  wire [31:0] freq32 = {22'b0, freq};

  always @(posedge clk) begin
    if (rst) begin
      tick_counter <= 0;
      sound <= 0;
    end else if (freq == 0) begin
      sound <= 0;
    end else begin
      tick_counter <= tick_counter + freq32;
      if (tick_counter >= (ticks_per_second >> 1)) begin
        sound <= !sound;
        tick_counter <= tick_counter + freq32 - (ticks_per_second >> 1);
      end
    end
  end

endmodule

module simon (
    input wire clk,
    input wire rst,
    input wire [15:0] ticks_per_milli,
    input wire [3:0] btn,
    input wire segments_invert,
    output reg [3:0] led,
    output wire sound,
    output wire [6:0] segments,
    output wire [1:0] segment_digits,
    // --- observability taps added for the self-checking testbench oracle ---
    output wire       game_over,   // high in StateGameOver
    output wire [4:0] level,       // current sequence length (rounds survived)
    output wire [2:0] dbg_state    // raw FSM state (see State* localparams)
);

  localparam MAX_GAME_LEN = 32;

  wire [9:0] GAME_TONES[3:0];
  assign GAME_TONES[0] = 196;  // G3
  assign GAME_TONES[1] = 262;  // C4
  assign GAME_TONES[2] = 330;  // E4
  assign GAME_TONES[3] = 784;  // G5

  wire [9:0] SUCCESS_TONES[6:0];
  assign SUCCESS_TONES[0] = 330;  // E4
  assign SUCCESS_TONES[1] = 392;  // G4
  assign SUCCESS_TONES[2] = 659;  // E5
  assign SUCCESS_TONES[3] = 523;  // C5
  assign SUCCESS_TONES[4] = 587;  // D5
  assign SUCCESS_TONES[5] = 784;  // G5
  assign SUCCESS_TONES[6] = 0;  // silence

  wire [9:0] GAMEOVER_TONES[3:0];
  assign GAMEOVER_TONES[0] = 622;  // D#5
  assign GAMEOVER_TONES[1] = 587;  // D5
  assign GAMEOVER_TONES[2] = 554;  // C#5
  assign GAMEOVER_TONES[3] = 523;  // C5

  localparam StatePowerOn = 0;
  localparam StateInit = 1;
  localparam StatePlay = 2;
  localparam StatePlayWait = 3;
  localparam StateUserWait = 4;
  localparam StateUserInput = 5;
  localparam StateNextLevel = 6;
  localparam StateGameOver = 7;

  reg [4:0] seq_counter;
  reg [4:0] seq_length;
  reg [1:0] seq[MAX_GAME_LEN-1:0];
  reg [2:0] state;

  reg [15:0] tick_counter;
  reg [9:0] millis_counter;
  reg [2:0] tone_sequence_counter;
  reg [9:0] sound_freq;

  reg [1:0] next_random;
  reg [1:0] user_input;
  reg score_inc;
  reg score_rst;
  reg score_ena;

  // Observability taps (pure reads of existing state — no behaviour change).
  assign game_over = (state == StateGameOver);
  assign level     = seq_length;
  assign dbg_state = state;

  play play1 (
      .clk(clk),
      .rst(rst),
      .ticks_per_milli(ticks_per_milli),
      .freq(sound_freq),
      .sound(sound)
  );

  score score1 (
      .clk(clk),
      .rst(rst | score_rst),
      .ena(score_ena),
      .inc(score_inc),
      .invert(segments_invert),
      .segments(segments),
      .digits(segment_digits)
  );

  always @(posedge clk) begin
    if (rst) begin
      seq_length <= 0;
      seq_counter <= 0;
      tick_counter <= 0;
      millis_counter <= 0;
      sound_freq <= 0;
      next_random <= 0;
      state <= StatePowerOn;
      seq[0] <= 0;
      led <= 4'b0000;
      score_inc <= 0;
      score_rst <= 0;
      score_ena <= 0;
    end else begin
      tick_counter <= tick_counter + 1;
      next_random  <= next_random + 1;
      score_inc <= 0;
      score_rst <= 0;

      if (tick_counter == ticks_per_milli - 1) begin
        tick_counter   <= 0;
        millis_counter <= millis_counter + 1;
      end

      case (state)
        StatePowerOn: begin
          led <= 4'b1111;
          led[millis_counter[9:8]] <= 1'b0;
          // Wait until the user presses some button - the delay will seed the random sequence
          if (btn != 0) begin
            state <= StateInit;
            led <= 4'b0000;
            millis_counter <= 0;
            score_ena <= 1;
            seq[0] <= next_random;
          end
        end
        StateInit: begin
          seq_length <= 1;
          seq_counter <= 0;
          tone_sequence_counter <= 0;
          if (millis_counter == 500) begin
            score_rst <= 1;
            state <= StatePlay;
          end
        end
        StatePlay: begin
          led <= 0;
          led[seq[seq_counter]] <= 1'b1;
          sound_freq <= GAME_TONES[seq[seq_counter]];
          millis_counter <= 0;
          state <= StatePlayWait;
        end
        StatePlayWait: begin
          if (millis_counter == 300) begin
            led <= 0;
            sound_freq <= 0;
          end
          if (millis_counter == 400) begin
            if (seq_counter + 1 == seq_length) begin
              state <= StateUserWait;
              millis_counter <= 0;
              seq_counter <= 0;
            end else begin
              seq_counter <= seq_counter + 1;
              state <= StatePlay;
            end
          end
        end
        StateUserWait: begin
          led <= 0;
          millis_counter <= 0;
          if (btn != 0) begin
            state <= StateUserInput;
            seq[seq_length] <= next_random;
            case (btn)
              4'b0001: user_input <= 0;
              4'b0010: user_input <= 1;
              4'b0100: user_input <= 2;
              4'b1000: user_input <= 3;
              default: state <= StateUserWait;
            endcase
          end
        end
        StateUserInput: begin
          led <= 0;
          led[user_input] <= 1'b1;
          sound_freq <= GAME_TONES[user_input];
          if (millis_counter == 300) begin
            sound_freq <= 0;
            if (user_input == seq[seq_counter]) begin
              if (seq_counter + 1 == seq_length) begin
                millis_counter <= 0;
                seq_length <= seq_length + 1;
                state <= StateNextLevel;
                score_inc <= 1;
              end else begin
                seq_counter <= seq_counter + 1;
                state <= StateUserWait;
              end
            end else begin
              millis_counter <= 0;
              state <= StateGameOver;
            end
          end
        end
        StateNextLevel: begin
          led <= 0;
          if (millis_counter == 150) begin
            if (tone_sequence_counter < 7) begin
              sound_freq <= SUCCESS_TONES[tone_sequence_counter];
            end else begin
              sound_freq <= 0;
              tone_sequence_counter <= 0;
              seq_counter <= 0;
              state <= StatePlay;
            end
            tone_sequence_counter <= tone_sequence_counter + 1;
            millis_counter <= 0;
          end
        end
        StateGameOver: begin
          led <= millis_counter[7] ? 4'b1111 : 4'b0000;

          if (tone_sequence_counter == 4) begin
            // trembling sound
            sound_freq <= GAMEOVER_TONES[3] - 16 + {5'b0, millis_counter[4:0]};
            if (millis_counter == 1000) begin
              tone_sequence_counter <= 7;
              sound_freq <= 0;
            end
          end else if (millis_counter == 300) begin
            if (tone_sequence_counter < 4) begin
              sound_freq <= GAMEOVER_TONES[tone_sequence_counter[1:0]];
              tone_sequence_counter <= tone_sequence_counter + 1;
            end
            millis_counter <= 0;
          end

          if ((btn != 0) && (tone_sequence_counter == 7)) begin
            led <= 4'b0000;
            sound_freq <= 0;
            millis_counter <= 0;
            seq[0] <= next_random;
            state <= StateInit;
          end
        end
      endcase
    end
  end

endmodule

// -----------------------------------------------------------------------------
// MIT License (for this file, per the SPDX header above)
//
// Copyright (c) 2023 Uri Shaked
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.
// -----------------------------------------------------------------------------
