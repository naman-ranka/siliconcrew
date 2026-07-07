# Legibility backend lane — F11 / F12 / F9b

Branch `claude/overnight-showcase`. Contract:
`plans/overnight-20260706/reports/legibility-contract.md` (authoritative).
All backend items done. F9b investigated to root cause; the code path is
already correct and the remaining live fix is a deploy, so it is locked with a
regression test and left honestly OPEN. Baseline held at exactly 9 known
failures throughout (zero new).

---

## ITEM 1 — F11: persist the grepped pass marker · commit `c8ab0b0`

**What changed**
- `src/tools/run_simulation.py`: the result dict now carries `pass_marker` (the
  exact string that was grepped, default `"TEST PASSED"`) on both the successful
  sim return and the compile-failed return. Additive; status semantics
  unchanged.
- `src/tools/sim_manager.py`: the `SimRun` run_meta gains `passMarker`
  (camelCase, `sim_result.get("pass_marker") or pass_marker`) beside
  `passMarkerFound`, so a failed run stays self-describing on disk.
- `tests/test_simulation_contract.py`: two regressions — a TB printing
  `"ALL TESTS PASSED"` (which does **not** contain the exact `"TEST PASSED"`
  substring — the `S` in `TESTS` breaks it) is honestly `test_failed`,
  `pass_marker_found` False, and the result / run_meta carry the grepped marker.

**Pre-fix failure proof** — stashed only the two source files and ran the new
tests: both failed with `KeyError: 'passMarker'` (and the result-field variant
failed on the missing `pass_marker`). Restored, both pass.

## ITEM 2 — F12: surface failing stage + check notes in run lists · commit `910ecb1`

**What changed**
- `src/tools/synthesis_manager.py` (`list_synthesis_runs`): each item now
  carries `current_stage` and `check_notes` (snake_case, from run_meta;
  absent → null).
- `src/api/actions.py` (`_synth_to_run`): maps them to `currentStage` /
  `checkNotes` (camelCase, RunSummary convention).
- `api.py` (`SynthesisRunResponse`): two new optional fields
  `current_stage` / `check_notes`; the `/synthesis-runs` endpoint constructs
  the model with `**item`, so they flow through automatically.
- `tests/test_workbench_v2_api.py`: a failed synth run seeded into a workspace
  (run_meta with `current_stage="cts"`, `check_notes="…4_1_cts.log"`) surfaces
  those fields camelCased on `GET /runs?kind=synth`.

**Pre-fix failure proof** — stashed the three source files, ran the new test:
`KeyError: 'currentStage'`. Restored, passes.

## ITEM 3 — F9b: retry_pd resume checkpoint staging · commit `3927e60` (test-only, F9b left OPEN)

**Finding (explore-mcp F2):** a cloud `retry_pd` resume-from-CTS died with
`[ERROR ORD-0007] .../base/3_place.odb does not exist` — the place checkpoint
was not materialized where `do-cts` reads it; the run also listed `place.odb`
as an artifact it could not consume (honest-state concern).

**Root cause — it is a deploy issue, not a `synthesis_manager` bug.**
I traced the entire resume path (self-host docker and hosted Cloud Run job):

1. `_retry_pd_worker` → `_copy_retry_prerequisites` copies the parent's
   `orfs_results/<plat>/<top>/base/3_place.odb` + `3_place.sdc` into the **child**
   run dir at the identical nested path (`rel = relpath(src, parent orfs_results)`),
   BEFORE ORFS is invoked (worker line ~1360, run at ~1415).
2. Self-host: `orfs_results` is bind-mounted to `/…/flow/results`, so the copied
   checkpoint is already visible to `make do-cts`. Never broken.
3. Hosted: `stage_in` tars the whole child run dir (checkpoint included) to GCS;
   the Cloud Run job's `deploy/orfs_job/entrypoint.sh` **stage-in block** copies
   `RUN_DIR/orfs_results/.` into the container's `flow/results/` before running
   ORFS, using the `orfs_results::/OpenROAD-flow-scripts/flow/results` volume-map
   entry the manager emits. So `flow/results/<plat>/<top>/base/3_place.odb`
   exists where `do-cts` reads it.

The entrypoint stage-in has existed since commit **`868907e` (2026-06-24)**,
`git merge-base --is-ancestor` confirms it is in the branch. But the recent
hosted deploys were **backend-only** (revs 00059, 00060 per FINDINGS) — the
separate `siliconcrew-orfs` **job image** was not rebuilt, so the live job runs
a pre-`868907e` entrypoint with no stage-in. That is why the checkpoint was
absent on the worker while the manager (correctly) had staged it into the tar.
The known-failing `tests/test_orfs_job_entrypoint.py::test_stage_in_copies_
checkpoint_into_container_path` is a Windows/git-bash `cp` path artifact (env),
not a logic gap — the block is correct on Linux.

**What I did (in-fence):** rather than fabricate a `synthesis_manager` change
where the code is already correct, I added a regression test
(`tests/test_retry_pd_resume_staging.py`) that drives `_retry_pd_worker` with a
recording fake `OrfsRunner` (no docker) and **locks the manager-side contract**
the entrypoint depends on:
- the place checkpoint is physically present at
  `orfs_results/<plat>/<top>/base/3_place.odb` at the instant ORFS is invoked;
- the emitted volume map still resolves `orfs_results` → the container results
  path (`orfs_results::/OpenROAD-flow-scripts/flow/results`);
- honest state: a failed resume reports no phantom netlist
  (`netlist_path is None or os.path.isfile(netlist_path)`).
Both tests pass on current code — the proof that the manager path is sound.

**Concrete remaining fix (out of this fence — deploy/ops):**
Rebuild and redeploy the `siliconcrew-orfs` Cloud Run **job image** from the
current `deploy/orfs_job/entrypoint.sh` (has stage-in) as part of the endgame
deploy, then re-verify a hosted retry_pd resume-from-CTS produces `4_cts.odb`
(no ORD-0007). Until that redeploy, **F9b stays OPEN** — a documented deferral,
not a speculative half-fix.

**Optional follow-up (not done, would be new machinery):** the manager could
detect an `ORD-0007 … does not exist` in the ORFS stderr on a resume and set a
targeted `check_notes` ("prior-stage checkpoint not visible to the worker —
job image may predate the stage-in fix") so the failure is self-explaining via
F12. Left out deliberately to avoid speculative machinery; flag for the owner.

---

## Gates

- Backend, each item: `python -m pytest tests/ -q --ignore=…identity_migration
  --ignore=…mcp --ignore=…mcp_remote_auth` → **9 failed** (the known baseline:
  congestion ×2, lint norm_file, llm_factory, orfs_job stage_in,
  perf_read_no_sync, sby_engine, xls ×2), zero new. My new tests: 5 pass
  (3 sim contract additions counting both files, 1 workbench synth, 2 retry
  staging).
- One transient anomaly: a full-suite run once showed `test_byok_endpoints.py::
  test_sqlite_store_tenant_isolation_and_delete` failing; it **passes in
  isolation** — a shared-sqlite collision from a concurrent test run (the
  predicted concurrency artifact), not a regression.
- Fixtures restored after each suite (`git checkout -- tests/fixtures/
  test_sby_output.txt`); staged only my own files each commit; pushed after each.

## ITEM 4 — X2U-2: honest sim status + spec detection in the design report · commit `e3f3844`

**Finding (explore2-ui, LOW/honesty):** the synthesis Design Report showed
"Simulation ⏳ Not Run" even after sims passed in the session, and "No
specification file found" even with `spec.md` present — both mislead a newcomer
about their own progress.

**Root causes (both in `src/tools/design_report.py`):**
- Sim status was derived by scanning the **workspace root** for `.out` /
  `simulation.log` and grepping pass/fail. Isolated sim runs write to
  `sim_runs/<id>/run_meta.json` and never to the workspace root, so the scan
  always fell through to "Not Run".
- Spec detection matched only `*_spec.yaml` (write_spec's output). A markdown
  `spec.md` (Spec tab / user-authored) is `role=other` to the manifest, so it
  was invisible → "No specification file found."

**Fix:**
- `_simulation_status_cell(workspace)` reads `list_sim_runs` (authoritative,
  newest-first) and reports the LATEST run's verdict with its id and a
  "latest of N runs" count when several exist; the legacy root scan is kept
  only as a fallback for pre-isolation sessions. "Not Run" now appears only
  when nothing actually ran.
- `_is_spec_like` / `_spec_like_files` recognize `spec.md`, `*_spec.md`,
  `spec.{yaml,yml,txt}` in addition to `*_spec.yaml`. A YAML spec still yields
  the full summary table; when only a markdown spec exists the report names it
  and points to the Spec tab. The Generated Files "Specifications" row uses the
  same predicate.

**Fence honored:** only `design_report.py` + its tests. Reads (does not modify)
`sim_manager.list_sim_runs`; did not touch synthesis_manager/actions/api.py,
mcp_server, wrappers/tool_catalog, frontend, examples.

**Pre-fix proof:** stashed only `design_report.py`, ran `TestReportHonestyX2U2`
— the 4 truth-surfacing tests failed (report still said "Not Run" / "No
specification file found" with sim_runs and spec.md present); the 2 negative
tests (Not Run / no-spec only when truly absent) passed pre-fix as intended.
Restored → 30/30 pass. Full gate: 9 known baseline + one concurrent-lane
artifact (`test_cocotb_engine` `TypeError: FakeEngine.run` — passes solo).

## Commits (all pushed)

| Commit | Item | Outcome |
|--------|------|---------|
| `c8ab0b0` | F11 backend | `pass_marker` in sim result + `passMarker` in run_meta |
| `910ecb1` | F12 backend | `current_stage`/`check_notes` through list + `_synth_to_run` + response model |
| `3927e60` | F9b | contract-lock regression test; root cause = stale ORFS job image (deploy), F9b left OPEN |
| `e3f3844` | X2U-2 | design report reads sim status from sim_runs + recognizes spec.md |
