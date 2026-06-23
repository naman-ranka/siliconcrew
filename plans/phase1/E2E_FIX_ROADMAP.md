# End-to-end flow fixes (post remote-synth E2E review)

Branch `claude/integration-p1p2`. Driven by the live full-flow UX review (create →
upload → lint → sim → **remote synth** → artifacts). Goal: a successful tape-out
must *look* successful — render the chip, show real PPA, communicate remote
progress, and stop contradicting itself. Scope chosen by the user: **frontend +
backend (full)**.

## Context that matters
- Remote synth works: `ORFS_ENGINE=remote` → tunnel → GCP VM → artifacts pulled
  back. Trigger: `POST /api/workspace/<sid>/synthesize` (allow-ruled for localhost).
- A real completed run for reference: session `synth-demo-1782173761`, run
  `synth_0001`. Artifacts on disk under
  `workspace/<sid>/synth_runs/synth_0001/orfs_{results,reports,logs}/sky130hd/counter/base/`
  — incl. `synth_stat.txt` (37 cells, 339.08 µm²), `6_finish.rpt`, `6_final.gds`.
- Runs list maps from the synthesis-runs index via `_synth_to_run`
  (`src/api/actions.py:121`): reads `status` + `summary_metrics`. Single-run uses
  `get_synthesis_job_status`/`get_ppa`. `start_synthesis_job` lives in
  `src/tools/synthesis_manager.py:1353`.

## Stages (sequential; each: implement → verify → commit+push → tick)
| # | Area | Scope | Status |
|---|---|---|---|
| 1 | **Finalizer + PPA** — remote ORFS job completion writes `status=completed` + parsed `summary_metrics` (area/cells from synth_stat; WNS/TNS/Fmax/power from finish/sta reports). Fixes stuck-"running" + null PPA. | backend | ✅ |
| 2 | **Render the GDS** — enable `gdstk`; layout endpoint returns a real SVG/PNG of `6_final.gds`. | backend | ✅ |
| 3 | **Remote-synth progress** — expose ORFS per-stage status + elapsed to the job-status payload; label "running on remote VM". | backend (+fe in 5) | ✅ |
| 4 | **Fresh-session history** — `/chat/{id}/history` returns empty (not 500) when no LLM key / no history. | backend | ✅ |
| 5 | **Frontend batch** — PPA hero never-green-for-unknown WNS + graceful null metrics; refresh layout/schem/report on synth completion; Layout "GDS ready — download" card + render when available; auto-generate report + fix empty-state copy; fresh-session red banner → calm; stepper idle-highlight follows pipeline; new-session naming; ORFS stage stepper UI. | frontend | ✅ |
| 6 | **E2E verify** — full UI flow again (dark+light), confirm success looks successful. | review | ⬜ |

## Guardrails
- Keep frontend green: `cd frontend && npx tsc --noEmit && npm run test && npm run build`.
- Backend: don't break existing tests; run targeted suites for touched modules.
- Test synth against a real run via the localhost trigger; verify on disk + API.
- Commit with trailers; push with backoff; tick this file per stage.
