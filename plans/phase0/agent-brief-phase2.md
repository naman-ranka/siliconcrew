# Agent Brief — Phase 2: Deployed Backend

You are a senior backend / platform engineer who understands both multi-tenant
SaaS and the realities of the open EDA toolchain (ORFS is a ~6.5 GB image, P&R
is minutes and memory-hungry, the flow expects a POSIX filesystem). Your job is
to make the SiliconCrew backend a **safe, multi-tenant, deployable** service
without touching the EDA tool logic (it is correct — leave it alone).

Read first: `plans/phase0/README.md`, `api-contract.md`, `data-model.md`, and
`docs/hosted_workbench_plan.md` (the deployment vision). Honor the README
principles.

## Mission

Take the single-tenant, locally-correct backend and fill the gaps that block a
multi-user deployment — enforcing the Phase 0 session/workspace seam, isolating
ORFS execution, externalizing storage, and adding tenancy controls — behind the
interfaces Phase 1 already codes against, so the frontend needs no changes.

## High-level requirements (decide the details yourself, as a senior would)

- **Enforce the tenancy seam everywhere.** The mechanism exists
  (`src/utils/session_context.py`, `get_workspace_path()` precedence). Make the
  whole request lifecycle set and rely on it; **eliminate** the
  `os.environ["RTL_WORKSPACE"]` mutation. Prove isolation under concurrency
  (the README propagation gate) with an integration test that runs concurrent
  sessions through the agent and asserts no cross-workspace writes.
- **ORFS as an isolated job, not Docker-outside-of-Docker.** Today
  `synthesis_manager` shells `docker run openroad/orfs`. Behind the same
  input/output contract, submit an isolated job (e.g. Cloud Run Job / k8s Job).
  Keep run dirs, snapshots, staged retry, and the index unchanged. Mind the
  6.5 GB image cold-start (warm pool / slimmer image / image streaming).
- **Externalize workspaces** behind `WorkspaceProvider`. Implement a
  cloud-backed provider (object storage staged to local scratch: download
  tarball → run → upload results). Do **not** pretend object storage is a POSIX
  FS to the tools. `LocalWorkspaceProvider` stays the default for self-host.
- **Persistence for scale.** Move session/run metadata from per-process SQLite
  toward a shared store (Postgres) where needed; keep the existing
  `session_manager` interface.
- **Tenancy controls.** Identity/auth (who is this user), per-user concurrency
  caps + quotas (synth runs/day, compute/month), and abuse limits. Per-user job
  queue, not the process-global `ThreadPoolExecutor`.
- **Determinism + provenance.** Pin `NUM_CORES`/seeds in generated `config.mk`;
  stamp `Provenance` (repo commit, ORFS digest, PDK, iverilog version) on runs.

## Build order (slice by slice; each ends runnable + tested)

1. **Seam enforcement** — remove the env-var mutation, context everywhere,
   concurrency isolation test (the gate).
2. **WorkspaceProvider abstraction** + cloud provider (stage in/out), local
   provider preserved.
3. **ORFS job runner** behind the existing `_run_orfs` contract; verify a real
   sky130 synth end to end.
4. **Identity + per-user quotas / concurrency caps.**
5. **Shared persistence** where SQLite blocks horizontal scale.
6. **Determinism pins + provenance stamping.**

## Verification (mandatory feedback loop)

- Concurrency isolation integration test (the gate) — non-negotiable.
- A real ORFS run through the job runner (nightly/heavy CI, inside the EDA
  image — not per-PR).
- Quota/limit unit tests; provider contract tests (local + cloud parity).
- Keep a checklist artifact of slices done / in progress.

## Non-goals (Phase 2)

The frontend and UX (Phase 1). New EDA features. Rewriting the tool logic —
synth run management, simulation correctness, and staged retry are already
solid; you are wrapping and governing them, not rebuilding them.
