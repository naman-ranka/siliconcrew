# TT bundle producer A — outcomes

Producer A candidates: 4-bit ALU, PWM generator, sn74169 up/down counter.
**All three shipped full flow to GDSII** on sky130hd — no skips, no sim-only
fallbacks. Method followed the proven `seven_seg_seconds` recipe end-to-end:
verify the upstream Apache-2.0 `LICENSE` in the fetched repo, strip the
`tt_um_*` pin wrapper to real ports (keeping the design logic verbatim), author
an ORIGINAL self-checking testbench with an independent oracle, then dogfood
locally through the platform's own action-layer tool functions
(`run_linter` / `run_sim_isolated` / `start_synthesis_job` +
`get_synthesis_status`) inside a real `SessionContext` so `attempt_events.jsonl`
is a genuine `source:"ui"` trajectory plus the `source:"system"`
`completion:<run_id>` event the synth worker emits.

## Shipped bundles

| Bundle | Design | Flow | Real PPA (sky130hd) |
|--------|--------|------|---------------------|
| `examples/alu4` | 4-bit registered ALU, 9 ops (add/sub/mul/div/and/or/xor/not/xor-encrypt) | spec → lint → sim → **GDS** | WNS 0.0 ns · 237 cells · 1974.39 µm² · 0.229 mW · fmax 100 MHz (10 ns) |
| `examples/pwm_generator` | Configurable PWM (12-bit period, % duty) | spec → lint → sim → **GDS** | WNS 0.0 ns · 1040 cells · 8077.75 µm² · 0.43 mW · fmax 50 MHz (20 ns) |
| `examples/sn74169` | 4-bit synchronous up/down counter (TTL '169 replica) | spec → lint → sim → **GDS** | WNS 0.0 ns · 26 cells · 282.77 µm² · 0.129 mW · fmax 100 MHz (10 ns) |

Each bundle: run ids `sim_0001` (passed) and `synth_0001` (completed), one
`sky130hd` ORFS `make -B` run in Docker, `6_final.gds` + netlist + DEF/SDC +
reports + logs shipped; `--prune-pnr` dropped 21 regenerable per-stage
checkpoints each.

## License evidence (verified in the fetched repo, per bundle)

Every upstream `LICENSE` is the canonical stock Tiny Tapeout Apache-2.0 text —
identical git blob SHA **`261eeb9e9f8b2b4b0d119366dda99c6fd7d35c64`** — copied
verbatim to `examples/<name>/LICENSE`, with the origin repo+commit attributed in
`spec.md`, the `template.json` description/source_note, and a header on each
adapted RTL file.

| Bundle | Upstream repo | Commit (verified) | LICENSE |
|--------|---------------|-------------------|---------|
| alu4 | `Richard28277/4bit_alu` | `fa2297666160eec4a520bfe3d236cf8fba00f93a` | Apache-2.0 ✓ |
| pwm_generator | `MateaSamuel/tt08-pwm-generator` | `731fb9162500ee5c35bdf9be478586b346df94ef` | Apache-2.0 ✓ |
| sn74169 | `andychip1/sn74169` | `cdab2c267cc94306c23f4e0c6a62559c30e6bed3` | Apache-2.0 ✓ |

## What really ran (genuine trajectory)

For all three, `workspace/attempt_events.jsonl` records the real tool calls:
`linter_tool` → **passed** (iverilog, 0 warn / 0 err), `run_isolated_simulation`
→ **sim_0001 passed** (`TEST PASSED` marker), `start_synthesis` → **synth_0001
completed**, and the system `completion:synth_0001` event. No event log was
hand-written.

Testbenches are original and self-checking with independent oracles:
- **alu4** — exhaustive sweep of all 9 opcodes × 256 `(a,b)` operand pairs
  (2304 vectors); golden model is plain integer arithmetic; checks `result` for
  every op and `carry_out`/`overflow` for ADD/SUB (the ops that define them).
- **pwm_generator** — programs the config registers through the real
  `sel`/`wr_en` write protocol, then counts `pwm_out` highs over an exact whole
  number of periods and asserts `= K·floor(period·duty/100)` (periodicity makes
  the count phase-independent, so no hierarchical peeking); also checks
  `out_en=0` forces low. Cases 25/50/75/10 % @ period 100, 50 % @ period 60.
- **sn74169** — independent golden model of the load/count/hold transition rule
  and of `RCOB`; exercises parallel load, a full up-count through the 15→0 wrap
  (with the RCOB terminal pulse), a full down-count through the 0→15 wrap, both
  disable modes (`ENPB`/`ENTB`), and load overriding an active count.

## Adaptation notes (recipe deltas actually hit)

- **alu4**: the candidate note predicted a purely combinational tile, but the
  upstream RTL is actually **registered** (result/carry/overflow latch on
  `posedge clk`, async-low reset) — a meatier sequential datapath. `a`,`b` were
  unpacked from `ui_in`; `opcode` was lifted off the `uio` input bus; carry/
  overflow were lifted off `uio_out[6]/[7]` and the `uio_oe` direction plumbing
  dropped. Status flags are meaningful only for ADD/SUB (other ops leave the
  flag registers unchanged) — the TB checks them exactly where they are defined.
- **pwm_generator**: upstream already ships a clean synthesizable core
  (`pwm_generator`) behind the TT mux wrapper — the core's own ports ARE the
  real interface, so adaptation was just dropping the wrapper and promoting the
  core to top (logic verbatim). The write mux is driven by the TB instead.
  Synthesized at the 50 MHz design intent (20 ns); the `period·duty` multiply
  makes it the heaviest tile (1040 cells) and it still meets timing at 0.0 ns.
- **sn74169**: core has the real '169 port list already; dropped the wrapper,
  used the core as top. Kept the upstream blocking-assignment style verbatim
  (single clocked block, deterministic); no reset pin — the TB establishes state
  via a parallel load before enabling checks.

## Sanitization (per bundle, held)

Leak-grep for `C:\Users` / `/Users/` / `naman` across each bundle = **zero
hits** (the copied Apache LICENSE is clean text). `manifest.sessionId` cleared
to `""`; every `run_meta.json.netlist_path` nulled; no stray `*.odb` / `*.vvp` /
`*.out`. Bundle sizes: alu4 5.0 MB, pwm_generator 13 MB (1040-cell design → real
4 MB GDS + 3.5 MB DEF, all authoritative), sn74169 2.2 MB.

## Tests

`tests/test_templates_fork.py` — **29 passed** after each export.
`list_templates()` now returns: `alu4`, `lfsr8`, `pwm_generator`,
`seq_detector_0011`, `seven_seg_seconds`, `sn74169`, `sync_fifo`,
`traffic_light`.

## Product bugs found

None. The dogfood path (write files → derive manifest → lint → sim → synth →
poll → export → prune → sanitize → list/preview) worked end-to-end with no
application-code changes. ORFS closed all three designs on the first attempt.

## Honest limits

- No `conversations/` in any bundle (no LLM key in this container → the export
  utility honestly skips empty transcripts rather than fabricate a chat; same
  posture as the earlier bundles). The real trajectory is the tool event log.
- `LICENSE` sits at each bundle root; the export copies only the `workspace/`
  subtree, so the LICENSE was added by hand post-export (a curator step).

## Commits (this branch, one bundle each)

- `alu4` — `feat(templates): alu4 bundle — real spec->lint->sim->GDS (Apache-2.0 upstream)`
- `pwm_generator` — `feat(templates): pwm_generator bundle — real spec->lint->sim->GDS (Apache-2.0 upstream)`
- `sn74169` — `feat(templates): sn74169 bundle — real spec->lint->sim->GDS (Apache-2.0 upstream)`
