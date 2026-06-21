# Phase 2 — Deployed Backend: Slice Checklist

Tracking artifact for the multi-tenant / deploy-ready backend work. Each slice
ends runnable + tested. Status: ✅ done · 🟡 in progress · ⬜ not started.

| # | Slice | Status | Verification |
|---|-------|--------|--------------|
| 1 | **Seam enforcement** — kill per-request env mutation, context everywhere, concurrency-isolation gate | ✅ | `tests/test_concurrency_isolation.py` (THE GATE) + `tests/test_session_context*.py` |
| 2 | **`OrfsRunner`** interface + `LocalDockerOrfsRunner` (refactor of `run_docker` path) + `CloudJobOrfsRunner` (Cloud Run Job, code) | ✅ | `tests/test_orfs_runner.py` (contract + local/cloud parity via fakes) |
| 3 | **`WorkspaceProvider`** cloud impl (object storage stage in/out); local stays default | ✅ | `tests/test_workspace_provider.py` (local+cloud parity via in-memory store) |
| 4 | **Identity + quotas** — per-user concurrency cap, runs/day + compute/month, per-user job queue | ✅ | `tests/test_quotas.py`, `tests/test_job_queue.py` |
| 5 | **`LlmKeyProvider`** — BYOK envelope encryption + capped hosted Gemini tier | ✅ | `tests/test_llm_keys.py` |
| 6 | **Shared persistence** — Postgres-backed metadata store behind `session_manager` interface (sqlite default) | ✅ | `tests/test_persistence.py` (sqlite store contract) |
| 7 | **Determinism + provenance** — pin `NUM_CORES`/seed in `config.mk`; stamp `Provenance` on runs | ✅ | `tests/test_provenance_determinism.py` |
| 8 | **IaC + runbook** — Terraform for Cloud Run/Jobs/GCS/Cloud SQL/AR/KMS + deploy runbook | ✅ | `deploy/terraform/*`, `deploy/RUNBOOK.md` (reviewed, not live-applied) |

## Posture

Deploy-ready, owner goes live. Local/self-host behavior is unchanged: every
cloud engine is selected only when `SILICONCREW_HOSTED=1` (see
`src/platform_engines/settings.py`); the default wiring is exactly today's
behavior, now behind interfaces.

## What is live-tested here vs. deploy-time

- **Live-tested in CI (no cloud, no Docker, stdlib + fakes):** the seam/gate,
  every interface contract, local impls, governance (quotas/queue), BYOK
  crypto, provenance/determinism, sqlite persistence.
- **Deploy-time only (owner runs):** the real ORFS Cloud Run Job (6.5 GB image,
  heavy/nightly CI inside the EDA image), GCS workspace round-trip, Cloud SQL,
  Cloud KMS. Code + IaC + runbook are provided; no autonomous provisioning/spend.

## Verification status (this branch)

All Phase-2 slices land green locally with stdlib + fakes (no Docker, no GCP):

```
100 passed, 3 skipped
  (skips: langchain-dep workspace test, RUN_REAL_ORFS smoke, one optional-dep path)
```

Pre-existing, unrelated to this work (verified identical on the pre-Phase-2 base
commit `fe6c693`): `test_llm_factory` (missing optional langchain provider
deps), `test_design_report` / `test_congestion_summary_tool` (test-level
issues), `test_run_cocotb` / `test_run_sby` (need Docker), and the 9 modules
that import `src.tools.wrappers` (need `langchain_core` installed). None are
regressions from Phase 2.

## Heavy verification (owner / nightly)

- A real sky130 synth through `LocalDockerOrfsRunner` (needs Docker + the ORFS
  image) — `tests/test_orfs_runner.py::test_local_runner_real_orfs` is gated
  behind `RUN_REAL_ORFS=1` so it is skipped in per-PR CI and run nightly inside
  the EDA image.
