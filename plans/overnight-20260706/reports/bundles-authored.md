# Showcase bundles authored (dogfood, self-host)

Branch: `claude/overnight-showcase`. Two new `examples/` bundles authored by
DOGFOODING the platform locally, the same way `examples/seq_detector_0011` and
`examples/sync_fifo` were: clean-room spec + RTL + self-checking TB, a GENUINE
agent-tool trajectory produced by really running the platform's tools, real run
artifacts, then exported via `scripts/export_bundle.py`
(`export_session_bundle`) with `--prune-pnr`.

Both reached **full flow to GDSII** on the local ORFS Docker flow — better than
the sim-only floor the brief allowed for `lfsr8`.

## Bundles shipped

| Bundle | Design | Flow reached | Real result |
|--------|--------|--------------|-------------|
| `examples/traffic_light` | 3-state Moore FSM (GREEN→YELLOW→RED), parameterized phase timers | spec → lint → sim → **GDS** (sky130hd) | WNS 0.0 ns · 172 cells · 1841.77 µm² · 0.304 mW |
| `examples/lfsr8` | 8-bit maximal-length Fibonacci LFSR (x⁸+x⁶+x⁵+x⁴+1, period 255) | spec → lint → sim → **GDS** (sky130hd) | WNS 0.0 ns · 21 cells · 335.32 µm² · 0.182 mW |

## What is real (evidence)

Every event in each bundle's `workspace/attempt_events.jsonl` is a real tool
execution driven through the SAME functions the REST action layer
(`src/api/actions.py`) calls — `run_linter`, `run_sim_isolated`,
`start_synthesis_job`/`get_synthesis_status` — inside a real `SessionContext`
(`source: "ui"`, plus the `source: "system"` `completion:<run_id>` event the
synthesis worker emits). No event log was hand-written.

**traffic_light** (`session_id: traffic_light`, repo commit at author time
`c07c374`):
- `linter_tool` → iverilog, **passed**, 0 warnings / 0 errors.
- `run_isolated_simulation` → **sim_0001 passed** (`TEST PASSED`; VCD shipped).
  The TB is genuinely self-checking: every clock it verifies one-hot outputs,
  each completed phase's run-length against its parameter, and legal ordering
  GREEN→YELLOW→RED→GREEN over 3 full cycles.
- `start_synthesis` → **synth_0001 completed** on `sky130hd`, real OpenROAD/ORFS
  run in Docker (`make -B`, `local_docker` backend), WNS 0.0 ns, 172 cells,
  elapsed ~65 s. `6_final.gds` + netlist + reports + logs shipped.

**lfsr8** (`session_id: lfsr8`, repo commit `441342b`) — authored in an earlier
run of this task; verified genuine and complete before export:
- `linter_tool` → iverilog, **passed**.
- `run_isolated_simulation` → **sim_0001 passed** (`TEST PASSED`). The TB runs
  255 enabled clocks and asserts (a) the state never hits the all-zero lockup and
  (b) the sequence returns to the 0xFF seed exactly at step 255 (maximal period).
- `start_synthesis` → **synth_0001 completed** on `sky130hd`, WNS 0.0 ns,
  21 cells, elapsed ~50 s. `6_final.gds` + netlist + reports + logs shipped.

Design correctness note: the traffic_light TB initially FAILED a real check
(first green run measured one tick short) because sampling begins mid-phase after
reset. Fixed the TB (skip the length check on the first reset-truncated run;
ordering still checked) — a genuine authoring iteration, not a seeded demo. The
committed trajectory is the clean pass after that fix.

## Sanitization (F16 verification — held)

Exported with `--prune-pnr`, which dropped 21 regenerable per-stage checkpoints
(`*.odb` + intermediate `*.gds`) per bundle, keeping `6_final.gds`, netlist,
DEF/SDC, reports, and logs. After export I grepped BOTH bundles for host-path
leaks (`C:\\Users`, `/Users/`, `naman`): **zero hits**. Verified:
- `manifest.json.sessionId` cleared to `""`.
- every `run_meta.json.netlist_path` nulled (fork re-derives it).
- `docker_command` / log tails redacted to `<workspace>`.
- no stray `*.out` / `*.vvp` build products; no leftover `*.odb`.

Bundle sizes: traffic_light 4.2 MB, lfsr8 2.2 MB (cf. seq_detector_0011 1.8 MB).

## Tests

- `tests/test_templates_fork.py` — **29 passed**, zero failures.
- Functional check: `list_templates()` now returns `lfsr8`, `seq_detector_0011`,
  `sync_fifo`, `traffic_light`; `get_template()` previews both new bundles with
  the correct `top_module`, 2 runs each, `spec.md`, and one `6_final.gds`.

## Product bugs found

None. The dogfood path (create files → lint → sim → synth → export → prune →
list/preview) worked end-to-end with no application-code changes. Docker ORFS
closed both FSMs on the first attempt at the default 10 ns clock.

## Deferred / honest limits

- **No `conversations/` in either bundle.** No LLM key in this container, so no
  genuine agent chat was authored; export honestly skips empty transcripts
  rather than fabricate one (same posture as `sync_fifo`). The trajectory
  showcase is the tool event log, which IS real.
- traffic_light's 32-bit phase timer inflates cell count (172) relative to a
  minimal FSM; kept as-authored because it is honest and gives a meatier PPA
  report than a near-empty design.
