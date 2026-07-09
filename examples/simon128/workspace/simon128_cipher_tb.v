// Self-checking testbench for the Simon-128/128 bit-serial cipher (simon128_cipher).
//
// Original to this SiliconCrew bundle. It drives the design's real bit-serial
// protocol and checks two published KNOWN-ANSWER vectors from the upstream Tiny
// Tapeout project's own test suite (tt08-simon, test/test.py). The upstream core
// fixes the key to all-zeros, so these are Simon-128/128 (plaintext -> ciphertext)
// pairs under a zero key:
//
//   PT 9f8e9892959afeeea080f1ea63e65b37 -> CT e0df57e57d292d90fdbab57cfdde08d4
//   PT d5be0328b8f87ffee3ecce3263f6ffc4 -> CT d9165a86d28b9937cbd2b69142d29997
//
// All I/O is bit-serial, LSB first (matching the upstream `hex_to_bits`, which
// reverses the hex value so the least-significant bit is sent/received first).
`default_nettype none
`timescale 1ns / 1ps

module simon128_cipher_tb;

  reg        clk = 1'b0;
  reg        rst_n;
  reg  [1:0] data_rdy;
  reg        data_in;
  wire       cipher_out;
  wire       valid;

  integer    errors = 0;
  integer    cap_count;
  reg [127:0] result;
  reg         encrypting;

  simon128_cipher dut (
      .clk        (clk),
      .rst_n      (rst_n),
      .data_rdy   (data_rdy),
      .data_in    (data_in),
      .cipher_out (cipher_out),
      .valid      (valid)
  );

  // 10 ns clock.
  always #5 clk = ~clk;

  // Watchdog.
  initial begin
    #400_000;  // 400 us = 40k clocks; two vectors need ~10k
    $display("TIMEOUT -- TEST FAILED");
    $finish;
  end

  // Capture the serial ciphertext, LSB first. `valid` is only high during the
  // output window of an encryption, so gating on `encrypting` is belt-and-braces.
  // Sample 1 ns after the edge so registered outputs have settled (matches the
  // upstream cocotb RisingEdge sampling of post-edge values).
  always @(posedge clk) begin
    #1;
    if (encrypting && valid) begin
      result    = {cipher_out, result[127:1]};
      cap_count = cap_count + 1;
    end
  end

  // Drive data_rdy/data_in for n clock cycles.
  task drive(input [1:0] rdy, input din, input integer ncyc);
    integer k;
    begin
      data_rdy = rdy;
      data_in  = din;
      for (k = 0; k < ncyc; k = k + 1) @(posedge clk);
    end
  endtask

  task run_vector(input [127:0] pt, input [127:0] ct);
    integer i;
    begin
      // idle, then load plaintext (LSB first), then load key (all zero).
      drive(2'd0, 1'b0, 2);
      for (i = 0; i < 128; i = i + 1) drive(2'd1, pt[i], 1);
      for (i = 0; i < 128; i = i + 1) drive(2'd2, 1'b0, 1);
      drive(2'd0, 1'b0, 1);

      // Encrypt. Reset the capture just before the output streams out.
      result     = 128'd0;
      cap_count  = 0;
      encrypting = 1'b1;
      drive(2'd3, 1'b0, 64*71);
      encrypting = 1'b0;

      if (cap_count != 128) begin
        errors = errors + 1;
        $display("CHECK FAILED: captured %0d valid bits (expected 128)", cap_count);
      end
      if (result !== ct) begin
        errors = errors + 1;
        $display("CHECK FAILED: pt=%032x  got ct=%032x  expected=%032x", pt, result, ct);
      end else begin
        $display("OK: pt=%032x -> ct=%032x", pt, result);
      end
    end
  endtask

  initial begin
    $dumpfile("simon128_cipher_tb.vcd");
    $dumpvars(0, simon128_cipher_tb);

    encrypting = 1'b0;
    data_rdy   = 2'd0;
    data_in    = 1'b0;

    // Reset (active low).
    rst_n = 1'b0;
    repeat (10) @(posedge clk);
    rst_n = 1'b1;

    // Clear internal shift registers (upstream preamble): run encrypt a while,
    // then idle to reset the round counter.
    drive(2'd3, 1'b0, 260);
    drive(2'd0, 1'b0, 2);

    // Two known-answer vectors (zero key).
    run_vector(128'h9f8e9892959afeeea080f1ea63e65b37, 128'he0df57e57d292d90fdbab57cfdde08d4);
    run_vector(128'hd5be0328b8f87ffee3ecce3263f6ffc4, 128'hd9165a86d28b9937cbd2b69142d29997);

    if (errors == 0)
      $display("TEST PASSED");
    else
      $display("TEST FAILED: %0d check(s) failed", errors);
    $finish;
  end

endmodule
