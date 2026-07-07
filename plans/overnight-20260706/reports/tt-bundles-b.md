# Tiny Tapeout bundles — producer B

Branch: `claude/overnight-showcase`. Three bundles authored by the proven
`seven_seg_seconds` method end-to-end: fetch the upstream repo at its pinned
commit, verify the Apache-2.0 `LICENSE` in-repo myself, strip the `tt_um_*` pin
wrapper to real ports, author an original self-checking testbench, dogfood
locally through the platform's own action-layer tool functions (so
`attempt_events.jsonl` is a genuine trajectory, not hand-written), and take each
design spec → lint → sim → GDS on sky130hd via local ORFS in Docker. Exported
with `scripts/export_bundle.py --prune-pnr`; `LICENSE` copied to each bundle
root; origin repo+commit attributed in `spec.md`, `template.json`, and RTL
headers.

**Outcome: 3 shipped to GDS, 0 sim-only, 0 skipped.**

## Shipped

| Bundle | Design | Upstream @ commit | Flow reached | Real result |
|--------|--------|-------------------|--------------|-------------|
| `examples/cla4` | 4-bit carry-lookahead adder (registered) | `Electom/tt08_CSA_4bits` @ `213ea90` | spec → lint → sim → **GDS** | WNS 0.0 ns · 41 cells · 419.15 µm² · 0.083 mW |
| `examples/ubcd_decoder` | Universal BCD / 7-seg decoder (multi-standard) | `RebeccaRGB/ubcd` @ `b16f134` | spec → lint → sim → **GDS** | WNS 0.0 ns · 192 cells · 1232.43 µm² · 0.646 mW |
| `examples/aes_invsbox` | AES inverse S-box (gate-level GF(2⁸) inverse) | `daosvik/tt08-aes-invsbox` @ `e786368` | spec → lint → sim → **GDS** | WNS 0.0 ns · 540 cells · 3251.87 µm² · 0.283 mW |

## License evidence (verified in-repo before adapting)

For each candidate I checked out the pinned commit and read the actual `LICENSE`
file: all three are the complete canonical **Apache-2.0** text (201 lines, header
"Apache License / Version 2.0", `END OF TERMS AND CONDITIONS` + APPENDIX
present). Each source file also carries an `SPDX-License-Identifier: Apache-2.0`
header. The verbatim `LICENSE` is copied to each bundle root and the origin
repo+commit is attributed in `spec.md`, `template.json.source_note`, and a header
on each adapted RTL file.

- `cla4` ← `github.com/Electom/tt08_CSA_4bits` @ `213ea903e947a2fbc5415d67e893da5d43385ffe`, Copyright (c) 2024 Wei Zhang.
- `ubcd_decoder` ← `github.com/RebeccaRGB/ubcd` @ `b16f134182bcca003b459584bde786ec9539d82a`, Copyright (c) 2024-2026 Rebecca G. Bettencourt.
- `aes_invsbox` ← `github.com/daosvik/tt08-aes-invsbox` @ `e78636840df3af0a11027db7fe2a0d3a82821521`, Copyright 2024 Dag Arne Osvik.

## What really ran (genuine trajectories)

Every event in each bundle's `workspace/attempt_events.jsonl` is a real tool
execution driven through the same functions `src/api/actions.py` calls
(`run_linter`, `run_sim_isolated`, `start_synthesis_job` /
`get_synthesis_status`) inside a real `SessionContext` (`source: "ui"`), plus the
`source: "system"` `completion:<run_id>` event the synthesis worker emits. Each
trajectory is: `linter_tool` passed → `run_isolated_simulation` **sim_0001
passed** (`TEST PASSED`) → `start_synthesis` → **synth_0001 completed** on
sky130hd.

- **cla4** — TB sweeps **all 512 vectors** (a,b ∈ 0..15 × ci ∈ 0..1); oracle is a
  plain integer add `a+b+ci` vs the registered `{co,s}`. synth_0001: 41 cells.
- **ubcd_decoder** — TB holds the control lines transparent and checks the full
  BCD range 0-9 (decimal, version 000) and a sample of extended codes A-F (hex,
  version 111) against the well-known seven-segment hex font (an oracle
  independent of the DUT's `casez` table). synth_0001: 192 cells.
- **aes_invsbox** — TB drives **all 256 input bytes** and checks the
  combinational `y` (and the registered `cy` one clock later) against the
  **FIPS-197 inverse S-box** golden table. synth_0001: 540 cells.

## Adaptation notes (honest deltas from verbatim)

- **cla4** — pure port strip: `a` on `ui_in[3:0]`, `b` on `ui_in[7:4]`, carry-in
  on `uio_in[0]`, sum/carry on `uo_out` → exposed as real ports `a,b,ci → s,co`.
  The carry-lookahead g/p/carry network and the registered outputs are verbatim.
- **ubcd_decoder** — the upstream muxes four decoders behind the TT pins; I use
  the `universal_bcd_decoder` submodule directly as top (it already has clean
  ports). ONE portability edit: SystemVerilog `always_comb` → Verilog-2001
  `always @(*)` so the same source lints, simulates, and synthesizes without a
  `-sv` flag. No logic changed; the `casez` already covers all 128 version×value
  combinations (verified) so no latch/default was added.
- **aes_invsbox** — dropped the `tt_um_*` wrapper and use the `sbox_aesinv` core
  as top; its standard-cell primitives come from the project's own **portable
  behavioral** `sky130.v` (no PDK needed — the earlier candidate note about a
  `sky130.v` `ifdef` shim was moot; the bodies are plain behavioral Verilog).
  ONE edit: removed the upstream `(* keep_hierarchy *)` attribute from each cell
  module in `sky130.v`. **Why:** with `keep_hierarchy`, yosys synthesized each
  cell as a separate module and the flow left the substitution network in
  unelaborated sub-modules — the physical design placed real gates (the timing
  path shows deep logic) but the platform's metric extractor counted only the
  top module (reported a misleading 1 cell / 8.76 µm²). Removing it lets the
  standard flow flatten and report true PPA (540 cells / 3252 µm²). No cell logic
  changed; documented in `sky130.v`, `sbox_aesinv.v`, and `spec.md`.

## Product bugs / friction found

- **Metric under-report with preserved hierarchy (real, worth noting).** A design
  that reaches `finish` with `keep_hierarchy` kept in the netlist reports
  `cell_count: 1` and a tiny area because the summary counts only top-level std
  cells, not cells inside preserved sub-module instances. The run is genuinely
  complete and the GDS is real, but the headline PPA is wrong. Not fixed here
  (out of scope for bundle production); flagging for the metrics owner — the
  summary should count leaf std cells through hierarchy, or the flow should note
  when hierarchy is preserved. Worked around by flattening (removing the
  attribute) for the shipped bundle.
- **Intermittent CTS crash (environment, not the design).** aes_invsbox failed
  once at the CTS stage with `6_finish.rpt not found` even though the CTS log
  showed clean completion (8 sinks, no setup/hold violations, ODB + area report
  written) — the step just didn't finalize. A retry (per the brief's
  fail-twice rule) closed it first try. Matches the known container CTS flake
  seen elsewhere in this run; no design change was needed.

Otherwise the dogfood path (write files → lint → sim → synth → export → prune →
list/preview) worked end-to-end with no application-code changes.

## Sanitization & tests (per bundle)

Exported with `--prune-pnr` (dropped 21 regenerable PnR intermediates each,
keeping `6_final.gds` + netlist + DEF/SDC + reports + logs). For all three:
leak-grep for `C:\Users` / `/Users/` / `naman` = **zero hits**;
`manifest.sessionId` cleared to `""`; every `run_meta.json.netlist_path` = null;
`LICENSE` present at bundle root (verbatim Apache-2.0). Bundle sizes on disk:
cla4 2.4 MB, ubcd_decoder 3.9 MB, aes_invsbox 8.9 MB.

- `tests/test_templates_fork.py` — **29 passed**, zero failures.
- `list_templates()` now includes `aes_invsbox`, `cla4`, `ubcd_decoder`
  alongside the rest of the gallery; `get_template()` previews each with the
  correct `top_module` (`cla4`, `universal_bcd_decoder`, `sbox_aesinv`) and one
  `6_final.gds`.

## Honest limits

- **No `conversations/` in any bundle** — no LLM key in this container, so no
  genuine agent chat was authored; export honestly skips empty transcripts
  rather than fabricate one (same posture as the other bundles). The trajectory
  showcase is the real tool event log.
- `ubcd_decoder` and (the combinational core of) `aes_invsbox` are largely
  combinational; ORFS closes them with a virtual clock (ubcd) or the single
  output register (aes `cy`), so `report_clock_skew` shows no launch/capture
  paths on the pure-combinational cones — expected and honest for these designs.

## Commits (each bundle its own commit; report committed last)

- `d414f0e` feat(templates): cla4 bundle
- `0648806` feat(templates): ubcd_decoder bundle
- `7000063` feat(templates): aes_invsbox bundle
