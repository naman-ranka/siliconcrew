# Simon-128/128 Bit-Serial Block Cipher

A hardware implementation of the NSA **Simon** lightweight block cipher, in the
**Simon-128/128** configuration (128-bit block, 128-bit key, 68 rounds). The
datapath is **bit-serial**: plaintext, key and ciphertext all move one bit per
clock through shift registers, trading throughput for a very small area — the
point of a lightweight cipher. In this design the key is **fixed to all-zeros**
in hardware (see `simon_module.v`), so it encrypts plaintext under a zero key.

## Attribution
The cipher RTL (`simon_datapath_shiftreg.v`, `simon_key_expansion_shiftreg.v`,
`simon_module.v`) is adapted **verbatim** from the Tiny Tapeout TT08 project
**`tt08-simon`** by Secure-Embedded-Systems
(https://github.com/Secure-Embedded-Systems/tt08-simon, commit
`6450fdcaf20be715c022ab28d12d43d5afe90193`), licensed **Apache-2.0**. The repo
`LICENSE` (Apache-2.0) is copied to the bundle root; the upstream top wrapper
carries `SPDX-License-Identifier: Apache-2.0` (© 2024 Secure Embedded Systems),
and origin repo+commit are recorded here, in `template.json`, and in a header on
each RTL file.

**Adaptation.** The upstream design wraps the cipher in the fixed Tiny Tapeout
pin interface (`tt_um_simon_cipher`: `data_rdy` on `ui_in[7:6]`, serial `data_in`
on `ui_in[0]`, serial `cipher_out` on `uo_out[0]`, `valid` on `uo_out[7]`). This
bundle drops that pin mux and exposes the cipher's real named ports on a clean
top (`simon128_cipher.v`); the datapath / key-expansion / core RTL is unchanged.
The self-checking testbench (`simon128_cipher_tb.v`) is **original** to this
bundle.

## Interface (`simon128_cipher`)
| Signal     | Dir | Width | Description                                           |
|------------|-----|-------|-------------------------------------------------------|
| clk        | in  | 1     | Clock                                                 |
| rst_n      | in  | 1     | Active-low synchronous reset                          |
| data_rdy   | in  | 2     | 0 idle · 1 load plaintext · 2 load key · 3 encrypt    |
| data_in    | in  | 1     | Serial data input (LSB first)                         |
| cipher_out | out | 1     | Serial ciphertext output (LSB first)                  |
| valid      | out | 1     | High while `cipher_out` carries valid ciphertext bits |

## Protocol (all serial, LSB first)
1. Hold `rst_n` low a few clocks to reset.
2. `data_rdy = 1`, stream 128 plaintext bits on `data_in`.
3. `data_rdy = 2`, stream 128 key bits (ignored — the key is fixed to 0).
4. `data_rdy = 3` to run encryption; while `valid` is high, read 128 ciphertext
   bits off `cipher_out`.

## Verification
The original self-checking testbench drives this exact protocol and checks two
**published known-answer vectors** taken from the upstream project's own test
suite (a zero key, so plaintext → ciphertext under Simon-128/128):

| Plaintext                          | Ciphertext                         |
|------------------------------------|------------------------------------|
| `9f8e9892959afeeea080f1ea63e65b37` | `e0df57e57d292d90fdbab57cfdde08d4` |
| `d5be0328b8f87ffee3ecce3263f6ffc4` | `d9165a86d28b9937cbd2b69142d29997` |

The testbench captures the serial output LSB-first, asserts exactly 128 valid
bits are produced and that the assembled ciphertext equals the expected value for
each vector, and prints `TEST PASSED`. The design is then synthesized to GDSII on
sky130hd.
