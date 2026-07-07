# TT bundle producer C — outcomes

Three Tiny Tapeout bundles authored by dogfooding SiliconCrew locally (the real
platform tool functions inside a `SessionContext`, `source: "ui"`, plus the
worker's `source: "system"` completion event). Every one reached **full flow to
GDSII** on sky130hd — none fell back to sim-only.

| Bundle | Upstream | Flow | Result (real) | Commit |
|--------|----------|------|---------------|--------|
| `examples/simon_game` | urish/tt06-simon-game @ 37f3538 | spec→lint→sim→**GDS** | WNS 0.0 ns · 1125 cells · 10374.95 µm² · 2.91 mW | `49cce1d` |
| `examples/simon128` | Secure-Embedded-Systems/tt08-simon @ 6450fdc | spec→lint→sim→**GDS** | WNS 0.0 ns · 1027 cells · 10602.67 µm² · 2.39 mW | `9248cce` |
| `examples/array_multiplier` | HHRB98/Array-multiplier @ f5291c9 | spec→lint→sim→**GDS** | WNS 0.0 ns · 45 cells · 392.88 µm² · 0.28 mW | `13e93f6` |

Skips: **none.** All three assigned/attempted candidates shipped to GDS.

## 1. simon_game (flagship) — Simon Says memory game

- **License evidence.** Repo `LICENSE` = Apache-2.0 (stock TT template, verified
  in the fetched repo). **Nuance (flagged):** the core source file `src/simon.v`
  carries its own per-file `SPDX-License-Identifier: MIT` header (`© 2023 Uri
  Shaked`). MIT and Apache-2.0 are both permissive — adaptation is clearly
  permitted — so I did **not** skip; I honoured BOTH: copied the repo's
  Apache-2.0 `LICENSE` to the bundle root, preserved the MIT copyright + full MIT
  permission text inside `simon.v`, and documented the dual origin in `spec.md`
  and `template.json`. (The candidate report vetted only the repo LICENSE blob
  and missed the per-file MIT header — worth noting for the record.)
- **Adaptation.** Dropped the `tt_um_urish_simon` pin wrapper (7-seg routed over
  the `uio` bus) → clean-port top `simon_game.v`; dropped the upstream `wokwi`
  simulator-top module; added three pure-read observability taps to the `simon`
  core (`game_over`, `level`, `dbg_state`) so the TB has a deterministic oracle;
  made the game "millisecond" a parameter (`TICKS_PER_MILLI`) for fast sim. The
  `score` (7-seg) and `play` (buzzer) back-ends are kept verbatim, so the
  synthesized design is the full playable game (hence the meaty 1125 cells).
- **Original self-checking TB.** Plays a full game deterministically WITHOUT
  hard-coding the pseudo-random sequence: it *observes* the LED playback to learn
  each round's sequence, replays it on the buttons, checks the round advances
  (level 1→2) with no game-over, checks round 2 replays round 1's first symbol
  plus one new one (growing-sequence invariant), then forces a wrong button and
  asserts game-over. Prints `TEST PASSED`.
- **What really ran** (session `simon_game`): `linter_tool` → iverilog passed;
  `run_isolated_simulation` → **sim_0001 passed**; `start_synthesis` →
  **synth_0001 completed** (real ORFS `make -B` in Docker, ~143 s).

## 2. simon128 — bit-serial Simon-128/128 cipher

- **License evidence.** Repo `LICENSE` = Apache-2.0 (verified); the top wrapper
  `tt_um_simon_cipher.v` carries `SPDX-License-Identifier: Apache-2.0` (`© 2024
  Secure Embedded Systems`). Copied to the bundle root; no license conflict.
- **Adaptation.** Dropped the `tt_um_*` pin wrapper (data_rdy on `ui_in[7:6]`,
  serial data on `ui_in[0]`, serial out on `uo_out[0]`, valid on `uo_out[7]`) →
  clean-port top `simon128_cipher.v` (clk, rst_n, data_rdy[1:0], data_in,
  cipher_out, valid). The datapath / key-expansion / core RTL is **verbatim**.
  Note the upstream core hardwires the key to all-zeros, so this is
  Simon-128/128 under a zero key.
- **Original self-checking TB.** Drives the bit-serial protocol (128-bit
  plaintext load LSB-first, 128-bit key load, encrypt, capture 128 serial output
  bits LSB-first) and checks **two published known-answer vectors from the
  upstream project's own test suite** (`test/test.py`):
  `9f8e…5b37 → e0df…08d4` and `d5be…ffc4 → d916…9997`. Asserts exactly 128 valid
  bits and an exact ciphertext match per vector, then prints `TEST PASSED`.
  (Locally the TB reproduced both published ciphertexts before dogfooding.)
- **What really ran** (session `simon128`): `linter_tool` passed;
  **sim_0001 passed**; **synth_0001 completed** (~90 s).

## 3. array_multiplier (bonus) — 4×4 unsigned array multiplier

- **Rationale.** Chosen as the bonus because it is unclaimed (producers A/B took
  4bit_alu, PWM, sn74169, ubcd, CSA, AES inv S-box) and combinational →
  near-certain first-try GDS with an exhaustive oracle.
- **License evidence.** Repo `LICENSE` = Apache-2.0 (verified) + `src/project.v`
  `SPDX-License-Identifier: Apache-2.0`. Copied to the bundle root.
- **Adaptation.** Dropped the `tt_um_*` pin wrapper (`ui_in[3:0]=a`,
  `ui_in[7:4]=b`, `uo_out=product`) and a dead reset flip-flop → clean-port
  combinational top `array_multiplier.v` (a[3:0], b[3:0] → p[7:0]). The AND-array
  + full-adder tree and the `FA` cell are kept verbatim.
- **Original self-checking TB.** Exhaustive: drives all 256 (a,b) pairs and
  asserts `p == a*b`. Prints `TEST PASSED (256/256 products correct)`. (Verified
  the upstream multiplier is actually correct on all 256 before shipping.)
- **What really ran** (session `arraymult`): `linter_tool` passed;
  **sim_0001 passed**; **synth_0001 completed** (~52 s).

## Sanitization (per bundle — all held)

Exported via `scripts/export_bundle.py --prune-pnr` (21 regenerable per-stage
PnR checkpoints dropped each; `6_final.gds` + netlist + reports + logs kept).
For every bundle: leak-grep for `C:\Users` / `/Users/` / `naman` = **0 hits**;
`manifest.sessionId` cleared to `""`; `netlist_path` nulled; Apache-2.0 `LICENSE`
added at the bundle root (copied from the fetched upstream repo — the export
utility only copies the `workspace/` subtree). `conversations/` is honestly empty
(no LLM key in this container → export skips empty transcripts, same posture as
the existing bundles). Bundle sizes: simon_game 16 MB, simon128 18 MB,
array_multiplier 2.3 MB.

## Tests

`tests/test_templates_fork.py` = **29 passed** after each bundle was added.
`list_templates()` returns all three new ids alongside the pre-existing and
sibling-producer bundles.

## Product bug found (fixed my invocation, not app code)

The dogfood path worked end-to-end, but I hit one real friction: `start_synthesis_job`
copies its `verilog_files` with `shutil.copy2(src, dst)` and does **not** resolve
relative paths against the workspace (`src/tools/synthesis_manager.py:433` /
`:1764`). The REST action layer always hands it absolute paths, so this never
surfaces in production; but a caller passing workspace-relative names (as the
logged event args show) gets a bare `FileNotFoundError [WinError 2]` attributed
to the "constraints" stage. Not app-breaking (no supported caller passes relative
paths), so I only fixed my own script — noting it here in case a future
dogfood/tool wants relative-path tolerance or a clearer error.

## Honest limits

- No genuine agent chat transcript in any bundle (no LLM key) — the real
  trajectory is the tool event log, which IS genuine.
- simon128 encrypts under a **fixed zero key** — that is the upstream design, not
  a limitation I introduced; documented in `spec.md`.
