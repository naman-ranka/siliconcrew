# Phase 2 — Reference & Architecture (deployed backend)

Real-world direction for the Phase 2 agent, analogous to `ui-design-language.md`
for Phase 1. North star: **`docs/hosted_workbench_plan.md`** (GCP architecture,
cost budget, phasing — read it first). This doc adds the locked decisions, the
swappable-engine pattern, and curated reference sources.

## Locked decisions (from the project owner)

| Decision | Choice | Implication |
|---|---|---|
| **Cloud target** | **GCP** — Cloud Run (backend) + Cloud Run Jobs (ORFS) + Cloud Storage (workspaces) + Cloud SQL/Postgres (metadata) + Artifact Registry (ORFS image) | Best fit for a bursty, heavy, mostly-idle workload (scale-to-zero + parallel jobs). Stay portable via the wrappers below. |
| **LLM keys** | **Both.** BYOK for all three providers (Anthropic / OpenAI / Google); a **hosted** free tier defaulting to **Gemini 3.5 Flash** (cheap/fast) with strict caps. | BYOK = no cost/abuse risk; hosted tier needs quota + cost ceilings. |
| **Auth** | **Google OAuth.** Anonymous trial allowed (lint/sim); sign-in required for synth + save + MCP. | Matches the student/dev audience and the hosted plan. |
| **Deploy posture** | **Deploy-ready, owner goes live.** Agent produces code + IaC + a runbook; the human runs the actual deploy. | No autonomous cloud provisioning or spend. Can upgrade to assisted-live later. |

## The core pattern: swappable engines (wrappers), not a hosted fork

Do **not** scatter `if hosted: … else: …` across the codebase. Instead define a
**small set of interfaces**, each with a **local** and a **cloud** implementation,
chosen once at startup by config. The tool/agent code calls the interface and
never knows which engine is active. Local/self-host keeps working exactly as
today (the local impls *are* today's behavior, just behind an interface).

```python
class OrfsRunner(Protocol):
    def run(self, run_dir, config_mk, targets) -> OrfsResult: ...

class LocalDockerOrfsRunner:   # ≈ today: refactor of the run_docker_command path
    def run(...): run_docker_command("make ...", volumes=[run_dir])

class CloudJobOrfsRunner:      # hosted: submit a Cloud Run Job, poll, collect
    def run(...): submit_job(image, inputs=run_dir); wait(); fetch_outputs()

# chosen once at startup:
orfs = CloudJobOrfsRunner() if settings.HOSTED else LocalDockerOrfsRunner()
```

### The seams (each its own small wrapper, local + cloud impl)

| Seam | Local impl (today) | Cloud impl (hosted) |
|---|---|---|
| **`OrfsRunner`** — where ORFS executes | `docker run` here (refactor of `synthesis_manager` → `run_docker_command`) | Cloud Run Job |
| **`WorkspaceProvider`** — where files live (defined in Phase 0) | folder on disk (`LocalWorkspaceProvider`) | Cloud Storage, staged to local scratch (download tar → run → upload) |
| **Persistence** — session/run metadata | SQLite (`session_manager`) | Cloud SQL / Postgres |
| **`LlmKeyProvider`** — which key a request uses | `.env` key | per-user BYOK (decrypted) or the capped hosted Gemini key |

Everything else — run dirs, snapshots, staged retry, report parsing — is
**unchanged**; it just calls the interface.

## ORFS as an isolated job (not Docker-outside-of-Docker)

- **Why move off DooD:** today `synthesis_manager` shells `docker run openroad/orfs`
  via the host Docker socket. Sharing that socket = effectively root on the host
  — unacceptable when untrusted users' designs run on a shared box.
- **Local impl:** keep the current `docker run` behavior, just behind `OrfsRunner`.
- **Cloud impl:** submit a **Cloud Run Job** per synth run — isolated sandbox,
  parallel by default, pay-per-use, scales to zero.
- **Cold-start reality (corrected):** Cloud Run cold start is driven by *init
  complexity, not image size*, and **Image Streaming** handles images <10 GB
  efficiently — so the 6.5 GB ORFS image is **not** the blocker it first seems.
  Cache it in **Artifact Registry**; consider startup-CPU-boost and a small
  warm pool only if measured latency demands it. Don't over-engineer up front.

## LLM keys (BYOK + capped hosted Gemini)

- **BYOK:** user provides a key for any of the three providers. Store with
  **envelope encryption** (encrypt the key with a per-user DEK, encrypt the DEK
  with a master key in **GCP KMS**; store only the wrapped key). Decrypt per
  request into the request scope — **never** an env var, never logged.
- **Hosted tier:** a single owner-provided **Gemini 3.5 Flash** key, used only
  when the user has no BYOK key, gated by hard caps (tokens/day, runs/day) and a
  global cost ceiling. Choose model by the existing `model_catalog`.
- Surface both behind `LlmKeyProvider` so the agent loop is unchanged.

## Tenancy isolation (the non-negotiable)

- The Phase 0 seam (`SessionContext` → `get_workspace_path()`) already exists and
  is the foundation. **Every** request must run in a session scope; the new
  action endpoints (Phase 1) included.
- **Defense in depth:** shared-schema + `tenant_id` (or `user_id`) column,
  **filtered on every query** (tenant-scoped by construction, not by habit);
  tenant/user id in the OAuth session/JWT, validated on every authorization
  decision (not just login).
- **Red-team tests are a release gate:** automated tests that use a valid token
  from user A to fetch user B's workspace/runs and assert `403` / empty. If they
  don't, the build fails. Plus the Phase 0 concurrency-isolation test running
  two real sessions through the agent.

## Quotas / abuse (the real risk is retry-looping, not raw demand)

- Per-user: synth runs/day, compute-minutes/month, **1 concurrent synth job**.
- Replace the process-global `ThreadPoolExecutor` with a **per-user job queue**.
- Global cost ceiling on the hosted-key tier; rate-limit the action + MCP
  endpoints.

## Determinism / provenance

- Pin `NUM_CORES` (and seeds where ORFS exposes them) in the generated
  `config.mk` — P&R is the only real nondeterminism source.
- Stamp `Provenance` (repo commit, ORFS image **digest**, PDK, iverilog version)
  on every run (see `data-model.md`).

## Deploy-ready posture (what to produce — do NOT go live)

- **IaC** (Terraform or `gcloud` scripts) for Cloud Run, Cloud Run Jobs, Cloud
  Storage, Cloud SQL, Artifact Registry, KMS.
- Container build configs (backend image; the ORFS image pushed to Artifact
  Registry).
- A **runbook**: step-by-step deploy, required secrets, rollback, cost dashboard
  + budget alerts.
- Stop there. The owner runs the deploy; the agent may assist interactively.

## Build order (seam-first; each slice runnable + tested locally)

1. **Seam enforcement** — every request in a session scope; red-team + concurrency
   isolation tests (the gate).
2. **`OrfsRunner` interface** + `LocalDockerOrfsRunner` (refactor today's path),
   verified against a real local synth (no behavior change).
3. **`WorkspaceProvider` cloud impl** (stage in/out); local stays default.
4. **`LlmKeyProvider`** — BYOK envelope encryption + capped hosted Gemini.
5. **Google OAuth** + anonymous-trial gating (sign-in for synth/save).
6. **`CloudJobOrfsRunner`** (Cloud Run Job) + Postgres persistence + per-user
   quotas/queue.
7. **IaC + runbook** (deploy-ready).

## Curated reference sources (study these; the web has good current material)

Cloud Run / jobs / cold start:
- https://cloud.google.com/blog/topics/developers-practitioners/a-guide-to-ai-cold-starts-on-cloud-run
- https://docs.cloud.google.com/run/docs/tips/general
- https://github.com/ahmetb/cloud-run-faq

Multi-tenant isolation:
- https://docs.aws.amazon.com/whitepapers/latest/saas-architecture-fundamentals/tenant-isolation.html
- https://workos.com/blog/developers-guide-saas-multi-tenant-architecture

BYOK / envelope encryption:
- https://aws.amazon.com/blogs/security/demystifying-kms-keys-operations-bring-your-own-key-byok-custom-key-store-and-ciphertext-portability/
- https://ironcorelabs.com/byok/  (GCP KMS equivalent: Cloud KMS envelope encryption)

Deployment north star (in-repo):
- `docs/hosted_workbench_plan.md`
