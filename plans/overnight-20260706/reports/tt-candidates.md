# Vetted Tiny Tapeout bundle candidates (licenses verified)

Goal: a VETTED, forkable candidate list of Tiny Tapeout projects a production fleet can
adapt into SiliconCrew `examples/` bundles, using the proven `seven_seg_seconds` recipe
(fetch upstream → verify Apache-2.0 → copy `LICENSE` + attribute repo/commit → strip the
`tt_um_*` pin wrapper to real ports → author an original self-checking TB → full flow to
GDS). See `bundles-authored.md §seven_seg_seconds`.

**Method.** Candidates were sourced from the Tiny Tapeout shuttle index
(`index.tinytapeout.com/tt06.json`, `/tt08.json`) filtered to simple digital synthesizable
designs, then each was verified in its OWN project repo: I fetched the actual `LICENSE`
file and the `info.yaml` (top module + real pinout) via the GitHub API. **Every LICENSE
below is the verbatim canonical Apache-2.0 text** — GitHub returns the identical blob SHA
`261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64` for all of them (the stock TT-template
`LICENSE`), so the SPDX id is `Apache-2.0` and the file path is `/LICENSE` in each repo.
No MIT candidates surfaced in this sweep, so there is no MIT section to flag.

**What "vetted" means here:** license confirmed in-repo + digital/synthesizable/self-contained
(pure RTL, std-cells only, no memory macros / analog / external IP) + the `tt_um_*` wrapper
is strippable to a clean port list + a deterministic self-checking TB is authorable. Size
is comfortably in the range the local ORFS flow already closed (`seven_seg` = 194 cells /
~118 s; `traffic_light` = 172; `lfsr8` = 21) — none of these is a 10k-cell monster.

**Avoids the existing gallery** (`sync_fifo`, `seq_detector_0011`, `traffic_light`, `lfsr8`,
`seven_seg_seconds`) — no counter-on-7seg or plain FSM re-treads.

---

## RANKED — 14 vetted Apache-2.0 candidates (best-first)

All top modules begin `tt_um_`. Difficulty S/M/L = adaptation + TB authoring effort.
"Sim TB checks" = what an original self-checking testbench asserts. Repo + commit is the
exact SHA I inspected; `LICENSE` (SPDX `Apache-2.0`) verified in each.

| # | Project | Shuttle | Repo @ commit | Category | Diff | Sim TB checks | Adaptation risks |
|---|---------|---------|---------------|----------|------|---------------|------------------|
| 1 | **4-bit ALU** (Richard Xu et al.) | TT08 | `Richard28277/4bit_alu` @ `fa22976` | ALU (combinational) | **S** | Enumerate opcodes (add/sub/and/or/xor/…) over sample operands; assert `result[7:0]`, `carry_out`, `overflow` vs a golden model | Purely combinational (`clock_hz:0`). Clean: `a`,`b` on `ui`, **`opcode` on the `uio` input bus**, results on `uo` + 2 status bits back on `uio`. Strip to `a,b,op→result,co,ovf`. |
| 2 | **4-bit carry-lookahead adder** (Wei Zhang) | TT08 | `Electom/tt08_CSA_4bits` @ `213ea90` | Adder (combinational) | **S** | Exhaustive: all 256 `a,b` × `ci` → assert `{co,s[3:0]} == a+b+ci` | Combinational. `a`,`b` on `ui`, `ci` on `uio[0]`, `s`/`co` on `uo`. Trivial strip. Smallest "real datapath" tile. |
| 3 | **sn74169 up/down counter** (andychip1) | TT08 | `andychip1/sn74169` @ `cdab2c2` | Counter / TTL replica | **S** | Load a value via `LOADB`, count up/down with `UP`, verify wrap and `RCOB` (ripple-carry) pulse at terminal count; gate on `ENPB/ENTB` | Fully documented clean ports (`A0..3`,`ENPB`,`ENTB`,`LOADB`,`UP` → `Q0..3`,`RCOB`). No `uio` used. Synchronous, textbook. |
| 4 | **PWM generator** (Matea Samuel) | TT08 | `MateaSamuel/tt08-pwm-generator` @ `731fb91` | PWM / signal gen | **M** | Program period + duty via the write iface, then count high-cycles over one period and assert measured duty == commanded (1–99%) | 12-bit configurable. Config loaded through a muxed write port (`ui`+`uio[3:0]` = data, `uio[6]=sel`, `uio[7]=wr_en`). Strip the load-mux to direct `period`/`duty` inputs, or drive the sequence in the TB. `clk 50 MHz`. |
| 5 | **AES inverse S-box** (Dag Arne Osvik) | TT08 | `daosvik/tt08-aes-invsbox` @ `e786368` | Crypto LUT (combinational) | **M** | Drive all 256 `x` bytes; assert `y == AES⁻¹Sbox[x]` from the FIPS-197 golden table | "Serious block" with a meaty PPA report. **Flag:** `source_files` includes `sky130.v` — a PDK-cell/mux shim; adaptation must select its behavioral (`ifdef`) path so it stays PDK-neutral for iverilog + generic synth. `x→y`, no `uio`. |
| 6 | **Universal binary→segment decoder** (R. Bettencourt) | TT08 | `RebeccaRGB/ubcd` @ `b16f134` | Decoder (combinational) | **M** | For a chosen mode (M1/M0), drive input codes and assert 7-seg outputs against a golden table (BCD, ASCII, Cistercian, Kaktovik) | Multi-mode: `M0/M1` on `uio[7:6]` pick decode style; blanking/lamp-test controls. Pick ONE mode for the bundle to keep the TB tight. Combinational, multi-file but all decode logic. |
| 7 | **Simon Says game** (Uri Shaked) | TT06 | `urish/tt06-simon-game` @ `37f3538` | Interactive FSM / game | **M** | Reset, replay the growing button sequence via `btn1..4`, assert `led1..4` sequence + round advance; assert loss on wrong input | The most memorable fork. Seven-seg score digits are on the **`uio` bus** (`seg_a..g`), speaker/LEDs on `uo`. `clk 50 kHz` (so counters are sim-friendly). Author TB around the button/LED protocol. |
| 8 | **Simon-128 cipher** (Secure-Embedded-Systems) | TT08 | `Secure-Embedded-Systems/tt08-simon` @ `6450fdc` | Crypto FSM (bit-serial) | **M** | Load key+plaintext bit-serially, run, assert ciphertext == the published Simon-128 test vector | Clean `ui`/`uo` only, no `uio`. Bit-serial → longer but fully deterministic sim. Multi-file (datapath / key-expansion / top). A genuine "real security block" tile. |
| 9 | **Hardware UTF-8/16/32 codec** (R. Bettencourt) | TT08 | `RebeccaRGB/hardware-utf8` @ `b0440db` | Encoder/decoder | **M** | Feed code points, read the encoded byte stream (and back); assert against a golden UTF-8/16/32 model incl. the error flags (overlong, surrogate, non-uni) | Data crosses the **bidirectional `uio` bus** (`I/O LSB..MSB`) with `READ`//`WRITE` + code-plane selects on `ui`. Needs a small io-direction shim in the TB (drive when writing, sample when reading). Combinational core. |
| 10 | **Iambic Morse keyer** (Brady Etz) | TT08 | `b-etz/tt08-morse-keyer` @ `2370bdd` | FSM + timing | **M** | Drive dit/dah paddles, assert the 7-seg character output and the tone/keyed timing for a known letter at a chosen WPM | `clk 12 MHz` with an on-chip **debounce** → set WPM select high and keep the TB short, or the dit/dah timing sim gets long. Paddles on `uio`, 7-seg on `uo`. Multi-file (morse/debounce/misc). |
| 11 | **Simple stopwatch** (Fabio Ramirez Stern) | TT08 | `faramire/TT08-simple-stopwatch` @ `e59bca8` | Stopwatch / BCD | **M** | Assert the internal centi-second BCD count advances, laps freeze the display, and reset zeroes it | **Adaptation delta:** the design serializes its count out **SPI to an external MAX7219** 7-seg driver — the pins are MOSI/CS/CLK, not the digits. Strip the SPI serializer and expose the BCD count on real output ports so the TB checks the count, not an SPI waveform. `clk 1 MHz`. |
| 12 | **Super Mario tune player** (Milosch Meriac) | TT08 | `meriac/tt08-play-tune` @ `e524392` | Music / tone gen | **M** | Step the note ROM; assert the square-wave output frequency (period) matches the expected note for each ROM entry, and the sequence advances/loops | Audible = great demo. **Flag:** output is a differential piezo drive on `uio_out[1:0]` (+ tied GND pins). Strip to a single `tone_out`; TB verifies note-index stepping / period rather than "sound". `clk 100 kHz`, `tune.v` is a note ROM. |
| 13 | **Array multiplier** (UACJ Group A) | TT06 | `HHRB98/Array-multiplier` @ `f5291c9` | Multiplier (combinational) | **M** | Exhaustively drive operands; assert `product == a*b` | Combinational partial-product array — a nice PPA tile alongside the FIR/ALU. **Risk:** `info.yaml` pinout is generic (`ui[n]`/`uo[n]`), so the operand widths (likely 4×4→8) must be read from `src/` before wiring the TB. |
| 14 | **INTERCAL ALU** (R. Bettencourt) | TT08 | `RebeccaRGB/intercal-alu` @ `8f49fa9` | Novelty ALU / bus periph | **M** | Write operands over the data bus, select one of the five INTERCAL ops (`⊻ ? & V ∀`), read result; assert vs a golden model | Fun + pedagogically odd (mingle/select/AND/OR/XOR reductions). **Risk:** it's a **tri-state bus peripheral** — `D[7:0]` is shared across `uo` and the bidirectional `uio` bus with `/OE`//`/WE`; the fork should split read/write ports or the TB must model bus turnaround. |

**Producibility:** items 1–3 are S (near-certain first-try GDS, minimal TB) and items 4–14
are M. Even with a few M-tier dropouts (sky130.v shim in #5, bus turnaround in #9/#14,
timing-length in #10/#12), this comfortably yields **8–12 shipped bundles**, and the mix
reads like a course: combinational datapath (ALU, adder, multiplier, S-box, decoder, UTF),
sequential/FSM (counter, stopwatch, keyer, Simon game), crypto (Simon-128), and audio.

---

## Second-tier — vetted Apache-2.0 but needs a source read before committing

| Project | Shuttle | Repo @ commit | Why second-tier |
|---------|---------|---------------|-----------------|
| **8-bit Calculator** (Randy Zhu) | TT08 | `ezchips/tt08-my-calc` @ `02fd6ad` | LICENSE = Apache-2.0 ✓, single `project.sv`, but the `info.yaml` pinout is **entirely "Unused"** (a ChipCraft/Wokwi-style lab) — the real interface is undocumented and must be recovered from source before it can be wrapped/TB'd. Good design if the read pays off. |
| **16-bit "dummy" counter + mult** (Chinmay) | TT08 | `pyamnihc/tt08-dummy-counter` @ `2b4d2ed` | LICENSE ✓ and source is clean synthesizable DFF logic (I read `src/project.v`), but it's low novelty (overlaps existing counters) and its enable path has a 16-tick **debounce** the TB must clock through. Use only if breadth runs short. |

---

## Excluded notables (so nobody re-litigates them)

| Project | Reason excluded |
|---------|-----------------|
| **jwjbadger/tt08-8bit-alu** (Simple 8-bit ALU) | Apache-2.0 ✓ **but it's a Wokwi project** (`language: Wokwi`, `wokwi_id`, no hand-written `source_files`) — the RTL is diagram-generated, so there's no clean human-authored source to strip/attribute. Prefer the two real-Verilog ALUs (#1, #14). |
| **ccattuto/tt08-sr-latch** (512-bit shift register) | Apache-2.0 ✓ but **intentionally latch-based** (the whole point is exploiting transparent latches for density). That does not synthesize cleanly through the standard sky130hd ORFS flow and isn't an honest "clean synth" showcase. A clean DFF shift register should be authored clean-room instead. |
| **rejunity/tt05-psg-sn76489** (SN76489 PSG) | Apache-2.0 but near the tile size ceiling and routes PWM audio through the `uio` bus (annoying I/O) — flagged in `template-candidates.md`; skip for a first gallery. |
| **TinyTapeout/vga-playground** | **GPL-3.0 (copyleft)** — cannot verbatim-fork. Replicate the VGA-pattern concept clean-room only. |
| **alex-segura/tt06-pong**, **aiju/tt06-aiju-8080**, **AeroX2 jrb8-computer** | Visually/technically great (Pong, 8080, retro CPU) but larger and/or tied to a fixed external pinout (VGA R/G/B/HSync/VSync) — heavier synth + I/O-map work than a first wave warrants. Park as "stretch" tiles. |
| **silicon-efabless/…-lm07**, **faramire/…-WS2812B**, **embelon/…-oled**, **benpayne/…-ps2** | Depend on **external peripherals** (SPI temp sensor, WS2812 LEDs, SSD1306 OLED, PS/2 device) — not self-contained; the "design" is mostly a serial protocol to an off-chip part. |

---

## Adaptation recipe deltas vs the `seven_seg_seconds` recipe

The `seven_seg` recipe (strip `tt_um_*` → real ports, tie `ena=1`, invert `rst_n`, drop
unused `uio_*`, own TB, copy `LICENSE`, attribute repo+commit in `spec.md`/`template.json`
+ RTL headers) holds for all 14. New wrinkles this set introduces:

1. **`uio` carries REAL signals, not just spare pins.** Unlike `seven_seg` (which dropped
   `uio` entirely), many here route live signals through the bidirectional bus: opcodes
   (#1), carry-in (#2), score digits (#7), data bus (#9, #14), paddles (#10), piezo (#12).
   The fork must read `uio_oe` to learn each pin's direction and map it to a real input or
   output port — do **not** blindly drop `uio`.

2. **True bidirectional/tri-state buses need a shim.** #9 (UTF codec) and #14 (INTERCAL
   ALU) share one `D[7:0]` bus for read and write via `/OE`//`/WE`. Cleanest adaptation is
   to **split into separate `data_in`/`data_out` ports**; if kept as one bus, the TB must
   model turnaround (drive on write cycles, sample on read cycles, honor the enable).

3. **Strip on-chip display/serializer back-ends to expose the datapath.** #11 (stopwatch)
   emits SPI to a MAX7219; #7/#10 drive multiplexed 7-seg. Where the interesting state is
   hidden behind a serializer, remove it and expose the raw count/character so the TB has a
   deterministic oracle instead of decoding a serial waveform.

4. **PDK-cell shims must be neutralized.** #5 (AES inv S-box) ships a `sky130.v` that
   instantiates sky130-specific cells behind an `ifdef`; select the behavioral branch so
   the RTL lints under iverilog and synthesizes portably (ORFS supplies the real cells).

5. **Watch clock dividers / debounce for sim time.** #10 (12 MHz + debounce), #4 (50 MHz),
   #11/#12 (real-time counters). As with `seven_seg`'s `MAX_COUNT` param, expose or override
   the divide/WPM/debounce constant so the sim ticks fast while synth still uses the real
   (meatier) value.

6. **Golden vectors already exist for the datapath blocks** — lean on standards instead of
   hand-rolling oracles: FIPS-197 for #5 (AES inv S-box), the published Simon-128 test
   vectors for #8, Unicode reference encodings for #9, and plain arithmetic models for
   #1/#2/#13. These make the self-checking TBs both authoritative and cheap.

---

Sources (all fetched live, read-only): Tiny Tapeout shuttle index
`index.tinytapeout.com/tt06.json`, `/tt08.json`; each candidate's own GitHub repo `LICENSE`
+ `info.yaml` at the pinned commits above. Curation rules inherited from
`template-candidates.md` (Apache-2.0 verbatim-fork OK; GPL/analog/external-IP out) and the
proven recipe in `bundles-authored.md §seven_seg_seconds`.
