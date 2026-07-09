// Simon-128/128 bit-serial block cipher — clean-port top for the SiliconCrew showcase.
//
// Adapted from Secure-Embedded-Systems' Tiny Tapeout TT08 project tt08-simon
//   repo:    https://github.com/Secure-Embedded-Systems/tt08-simon
//   commit:  6450fdcaf20be715c022ab28d12d43d5afe90193
//   license: Apache-2.0 (see LICENSE at the bundle root and spec.md)
//
// Adaptation: the upstream design wraps the cipher in the fixed Tiny Tapeout pin
// interface (tt_um_simon_cipher: data_rdy on ui_in[7:6], serial data_in on
// ui_in[0], serial cipher_out on uo_out[0], valid on uo_out[7]). This top drops
// that pin mux and exposes the cipher's real named ports. The core RTL
// (simon_module / datapath / key-expansion) is unchanged; note the upstream core
// hardwires the key to all-zeros (see simon_module.v), so this is Simon-128/128
// with a fixed zero key.
//
// Protocol (all I/O is bit-serial, one bit per clock, LSB first):
//   1. hold rst_n low a few clocks to reset;
//   2. data_rdy = 2'd1 and stream 128 plaintext bits on data_in (LSB first);
//   3. data_rdy = 2'd2 and stream 128 key bits (ignored: key is fixed to 0);
//   4. data_rdy = 2'd3 to run encryption; when `valid` is high, `cipher_out`
//      carries the ciphertext bits (LSB first), 128 bits total.
`default_nettype none

module simon128_cipher (
    input  wire       clk,
    input  wire       rst_n,      // active-low synchronous reset
    input  wire [1:0] data_rdy,   // 0 idle, 1 load plaintext, 2 load key, 3 encrypt
    input  wire       data_in,    // serial data input (LSB first)
    output wire       cipher_out, // serial ciphertext output (LSB first)
    output wire       valid       // high while cipher_out is valid
);

    simon_module core (
        .clk        (clk),
        .reset      (rst_n),      // core `reset` is active-low
        .data_in    (data_in),
        .data_rdy   (data_rdy),
        .cipher_out (cipher_out),
        .valid      (valid)
    );

endmodule
