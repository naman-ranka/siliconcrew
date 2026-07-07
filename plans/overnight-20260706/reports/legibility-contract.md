# F11/F12 legibility contract (session 2) — AUTHORITATIVE for the two implementer lanes

Grounded in the legibility-map report (file:line verified by the Explore agent).
Principle: surface the truth we ALREADY compute — no new machinery, no speculation
in the UI, render only fields that are really present.

## Field contract (backend → frontend)

1. **Sim (F11), additive:** `run_simulation.py` result gains `pass_marker` (the
   exact marker string that was grepped, default "TEST PASSED"); SimRun
   run_meta.json gains `passMarker` (camelCase, beside `passMarkerFound`,
   sim_manager.py:238 area). Sim list already returns full run_meta → no list
   changes needed.
2. **Synth (F12), additive:** the failing stage + reason must survive into BOTH
   list surfaces:
   - `list_synthesis_runs` (synthesis_manager.py:2729-2743): add `current_stage`,
     `check_notes` (snake_case, matching that payload's existing keys).
   - `_synth_to_run` (src/api/actions.py:214-228): add `currentStage`,
     `checkNotes` (camelCase, matching RunSummary conventions).
   - `SynthesisRunResponse` (api.py:262-274): add the same two, optional.
   Values come straight from run_meta.json (written at synthesis_manager.py:
   1968-1975 / 1922-1931 / 1439-1452); absent → omit/null, never fabricate.

## Render contract (frontend)

3. **RunsPane Result cell (RunsPane.tsx:123-176):**
   - Failed SIM row: one-line reason under/beside the status —
     `failure.firstFailureLine` if present; else if `passMarkerFound === false`:
     `no pass marker — expected "<passMarker ?? 'TEST PASSED'>"` with the
     stdout tail available via the existing lightweight affordance (title attr
     or the pane's existing detail pattern — NO new heavy component).
   - Failed SYNTH row: `failed @ <currentStage>` when currentStage present, plus
     `checkNotes` as the one-line reason (truncated, full text in title).
4. **ReportArtifact.tsx failed state (:39-56):** replace the bare
   "No report for this run yet" for FAILED runs with an honest failure panel:
   failing stage + checkNotes (from the run row), and `lastLogLines` ONLY when
   `synthJob.runId` matches this run (that's the only place the tail exists
   client-side; do not fetch — the UI is a viewer, invariant 6).
5. **types/index.ts RunSummary:** add optional `passMarker?` (sim),
   `currentStage?`, `checkNotes?` (synth).

## Tests (regression, proven to fail pre-fix where applicable)

- Backend: test_simulation_contract.py — TB printing "ALL TESTS PASSED" (but not
  the exact marker) yields test_failed + passMarkerFound False + the new
  pass_marker field carries "TEST PASSED". test_workbench_v2_api.py — /runs
  synth items now carry currentStage/checkNotes from fixture run_meta.
- Frontend: workbench.components.test.tsx — failed sim row renders the
  no-pass-marker reason; failed synth row renders stage + notes;
  ReportArtifact failed state renders the failure panel.

## Fences

- Backend lane: run_simulation.py, sim_manager.py, synthesis_manager.py,
  src/api/actions.py, api.py (response model only), backend tests. Then F9b as
  a separate item (synthesis_manager.py + tests/fixtures/retry_pd_workspace).
- Frontend lane: frontend/types/index.ts, RunsPane.tsx, ReportArtifact.tsx,
  CommandPalette (F5), save feedback site (F8), frontend tests. NO store
  changes expected; NO polling additions (invariant 6).
- Neither lane touches: mcp_server.py (small-fixes lane), examples/ (bundle
  lane), Launcher/TemplatePreview (stable, reviewed).
