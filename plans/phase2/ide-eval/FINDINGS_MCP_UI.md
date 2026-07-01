# MCP → Web UI Cross-Surface Sync — Findings

**Test:** an agent acting as the user's own AI client (Codex/Cursor-style) drove an
8-bit adder **spec → files → lint → sim → synthesis → GDS via the SiliconCrew MCP**
on the **deployed** backend, while a Web UI (local FE → same deployed backend, same
identity via the Next proxy) was observed **simultaneously** after each step.

**Setup that made this a faithful test**
- MCP driver → deployed `/mcp` (`mcp_client.py`, static bearer = `SILICONCREW_MCP_TOKEN`).
- Web UI → local FE on `:3002`, REST routed through the Next proxy to the **same
  deployed backend**, authenticated as the **same identity** (test-only proxy token
  injection). So both surfaces read/write one shared backend state.
- Synthesis is real: deployed backend uses `ORFS_ENGINE=remote` → remote ORFS
  service, so spec→GDS actually completes (area 337.8 µm², 43 cells, 100 MHz).

## Verdict

The shared-backend / shared-identity story is **real** — files, waveforms, and the
GDS/layout created via MCP all appear correctly in the Web UI and match MCP exactly.
**But the handoff is not seamless:** the UI is **not reactive** (everything requires a
manual reload), and the **synthesis run status is split-brain** — MCP reports the job
completed with full metrics + GDS, while the UI-facing API is frozen at `running`
forever. So the flagship "drive from my AI app, flip to the Web UI" moment currently
shows a *finished* design as a *hung* job.

## Cross-surface consistency

| Artifact | In UI? | Live or reload-only? | Matches MCP? |
|---|---|---|---|
| Session created | ✅ | reload-only | ✅ name + active state |
| Files (adder8.v/_tb.v) | ✅ | reload-only | ✅ content + RTL/TB roles + synthTop/simTop |
| Lint | ❌ | never | ❌ leaves no trace ("No lint output yet") |
| Sim run (Runs panel) | ❌ | never | ❌ `simulation_tool` is ephemeral, registers no run |
| Waveform (Wave tab) | ✅ | reload + manual VCD select | ✅ `adder8_tb.vcd`, 13 signals |
| Synth run row | ✅ | reload-only | ⚠️ run_id matches, **status wrong** |
| Synth progress | ⚠️ | reload-only, no auto-poll | ❌ UI shows only "running" |
| Synth result / metrics | ❌ | never | ❌ **frozen "running", metrics null forever** |
| GDS / Layout | ✅ | reload-only | ✅ renders + **GDS downloads (252 KB)** |
| Report (PPA) | ❌ | never | ❌ gated on the stale "running" status |

## Key findings (ranked)

**1 — Split-brain synthesis status (CRITICAL, independently confirmed).**
Same run `synth_0001`, session `adder8_mcp_live`:
- MCP `get_synthesis_metrics` → `status: ok`, `area_um2: 337.824`, `cell_count: 43`; GDS
  `6_1_merged.gds` + `6_final.gds` present.
- REST `GET /api/workspace/.../synthesis-runs` → `status:"running"`, `finished_at:null`,
  `summary_metrics:null`, `report_available:false` — never updated.
The MCP job store and the UI-facing run store don't sync on terminal state. Cascades to
Signoff "—" and Report "No report yet" despite a finished GDS. **This is the #1 fix.**

**2 — The Web UI is not reactive to another client's changes.**
Verified by network inspection: the UI fetches `/runs`, `/synthesis-runs`, `/waveforms`,
`/layouts`, `/files`, `/manifest` **once per navigation**, then stops — no polling, SSE,
or websocket. 20 s open during an active synth = zero new requests. The real UX today is
"drive via MCP, then **reload** the Web UI." For the cross-surface promise this is the
core gap. (Minimal fix: poll runs/synthesis-runs while a job is active; better: push.)

**3 — Lint and simulation leave no UI trace.**
`linter_tool` returns "Syntax OK" but writes nothing the UI reads. `run_isolated_simulation`
(the persisted-run tool) returns **Unknown tool** on the deployed backend, so only the
ephemeral `simulation_tool` works — it produces the VCD (which does sync) but registers no
run in the Runs panel. Result: from the UI, lint/sim never happened.

**4 — GDS from the UI works well.** Reload → select run → Artifacts → Layout → interactive
standard-cell layout (29,293 polygons, port labels, zoom, 2 GDS variants) + working
**Download** (verified 252 KB GDSII). Ironically the one signoff artifact that syncs cleanly.

**5 — Smaller issues.** Reload load-flash briefly shows the empty "Let's build a chip"
state (looks like data loss ~1–2 s); Monaco editor CDN blocked (`cdn.jsdelivr.net` →
ERR_CONNECTION_CLOSED) so the editable editor hangs on "Loading editor…"; repeated
`/spec` 404s; tool-arg quirks (`get_current_session` → "datetime not JSON serializable";
`start_synthesis` needed explicit `verilog_files`/`top_module` despite being described as
manifest-driven; `get_synthesis_metrics` only accepts `job_id`/`run_id` inconsistently).

## Fix priority

1. **Sync terminal synth state to the UI run store** (split-brain) — the single most
   misleading defect; makes finished work look hung.
2. **Make the UI poll while a job is active** (runs + synthesis-runs) — turns "reload to
   see it" into a live handoff; the whole cross-surface promise hinges on this.
3. **Persist lint + simulation as runs** the UI reads (and restore `run_isolated_simulation`
   on the deployed backend) so those stages aren't invisible.
4. Self-host Monaco; fix the reload empty-state flash and the `/spec` 404 noise.

*Evidence: screenshots in `plans/phase2/screenshots/mcp-ui-sync/` (01-baseline … 10-report).*
