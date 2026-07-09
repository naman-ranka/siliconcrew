# SiliconCrew Hosted Backend — Deploy Runbook

Deploy-ready posture: **the owner runs the live deploy.** This runbook is the
step-by-step. The Terraform in `deploy/terraform/` provisions nothing until you
`apply`; costs accrue then.

## Architecture (what gets created)

| Component | GCP service | Purpose |
|---|---|---|
| Backend API | Cloud Run service | FastAPI + agent; scale-to-zero, startup-CPU-boost |
| ORFS runner | Cloud Run **Job** | one isolated synth per run; no shared Docker socket |
| Workspaces | Cloud Storage | per-session tarballs, staged to local scratch |
| Metadata | Cloud SQL (Postgres) | sessions/projects (shared across replicas) |
| Images | Artifact Registry | backend image + 6.5 GB ORFS image (Image Streaming) |
| BYOK keys | Cloud KMS | KEK for envelope-encrypted user API keys |
| Secrets | Secret Manager | DB password, hosted Gemini key, OAuth client id |

The backend selects cloud engines via `SILICONCREW_HOSTED=1`; every seam
(`OrfsRunner`, `WorkspaceProvider`, `MetadataStore`, `LlmKeyProvider`) flips to
its cloud impl. Self-host leaves the flag unset and behaves exactly as today.

## Prerequisites

- `gcloud`, `terraform >= 1.5`, Docker, a GCP project + billing account.
- A Google OAuth 2.0 Client ID (Web) for sign-in.
- An owner-provided Gemini 3.5 Flash API key for the capped hosted tier.

## 1. Build & push images

```bash
REGION=us-central1
PROJECT=<your-project>
REPO="${REGION}-docker.pkg.dev/${PROJECT}/siliconcrew"

# (Terraform creates the Artifact Registry repo; run step 2 first if needed,
#  or create the repo manually, then return here.)

# Backend image
gcloud builds submit --tag "${REPO}/backend:$(git rev-parse --short HEAD)"

# ORFS job image (thin layer over the upstream ORFS image)
docker build -t "${REPO}/orfs:$(date +%Y%m%d)" \
  --build-arg ORFS_BASE=openroad/orfs:latest deploy/orfs_job
docker push "${REPO}/orfs:$(date +%Y%m%d)"

# Capture immutable digests — pin these in prod for reproducible provenance:
gcloud artifacts docker images describe "${REPO}/orfs:..." --format='value(image_summary.digest)'
```

## 2. Provision infrastructure

```bash
cd deploy/terraform
cat > terraform.tfvars <<EOF
project_id     = "${PROJECT}"
region         = "${REGION}"
environment    = "staging"
backend_image  = "${REPO}/backend@sha256:..."
orfs_image     = "${REPO}/orfs@sha256:..."      # digest-pinned
db_password    = "<generated>"                  # or pull from Secret Manager
billing_account = "<billing-account-id>"
monthly_budget_usd = 200
EOF

terraform init
terraform plan      # REVIEW carefully — this is where spend begins
terraform apply
```

Outputs: `backend_url`, `workspace_bucket`, `orfs_job_name`, `kms_key_uri`,
`cloud_sql_connection_name`, `artifact_registry`.

## 3. Secrets (Secret Manager)

```bash
printf '%s' "<gemini-key>"        | gcloud secrets create hosted-gemini-key --data-file=-
printf '%s' "<oauth-client-id>"   | gcloud secrets create google-oauth-client-id --data-file=-
printf '%s' "postgresql+psycopg://siliconcrew:<pw>@/siliconcrew?host=/cloudsql/<conn-name>" \
  | gcloud secrets create database-url --data-file=-
```

Grant the backend service account `roles/secretmanager.secretAccessor`, then
wire them as env `value_source` references on the Cloud Run service (DATABASE_URL,
HOSTED_GEMINI_KEY, GOOGLE_OAUTH_CLIENT_ID). Attach the Cloud SQL connection
(`--add-cloudsql-instances <conn-name>`).

### Frontend Google sign-in (pair the client ID)

Set the Terraform variable `google_oauth_client_id` to your Google OAuth Web
Client ID. It's wired to **both** services from this one value (public, so it's a
plain env var — not a Secret, not a build arg):
- backend → `GOOGLE_OAUTH_CLIENT_ID` (verifies tokens)
- frontend → `GOOGLE_CLIENT_ID`, injected at runtime by the server layout, so the
  prebuilt image stays environment-agnostic (no rebuild per client ID)

Behavior:
- **Set** → users sign in with Google; the ID token is sent as
  `Authorization: Bearer` (REST) and `?token=` (WS); synth/save require sign-in.
- **Empty (default)** → no sign-in UI, no token sent (self-host / anonymous
  trial). If you run hosted with it empty, every request lands anonymous and
  synth/save 403.

Also add the deployed frontend origin to the OAuth client's **Authorized
JavaScript origins** in the Google Cloud console, or GIS will refuse to load.

### Static test bearer for automated agents / CI (staging only)

To let an automated agent (or CI) drive signed-in flows without a real Google
login, set a secret on the **backend** only:

```bash
printf '%s' "$(openssl rand -hex 32)" | gcloud secrets create siliconcrew-test-bearer --data-file=-
# wire it as env SILICONCREW_TEST_BEARER_TOKEN on the backend service (value_source)
```

A request whose `Authorization: Bearer <secret>` matches (constant-time) then
authenticates as the fixed **`test-bot`** identity — its own tenant, full
capabilities, via the same Bearer/WS path real users use. The agent provides the
secret the same way a real token is provided: `Authorization: Bearer <secret>` on
REST and `?token=<secret>` on the chat WebSocket (e.g. inject it into the
frontend's auth seam / `sessionStorage["sc-auth-token"]`).

- **Off by default** — empty secret disables it entirely; genuine Google tokens
  still verify normally when it's set (exact-match only).
- **STAGING ONLY. Never set `SILICONCREW_TEST_BEARER_TOKEN` in production.** It is
  a standing full-access credential; keep it in Secret Manager and rotate it.
- Backend logs a one-time warning at first use so it's never silently on.

## 4. Initialize the database

The backend calls `MetadataStore.init_schema()` on boot (idempotent), and — in
hosted/Postgres mode — the LangGraph checkpointer runs its own `.setup()` on
startup to create the conversation tables (Wave 10). Verify:

```bash
gcloud sql connect siliconcrew-metadata --user=siliconcrew --database=siliconcrew \
  -e "\dt"   # expect: projects, session_metadata, chat_threads,
             #         checkpoints, checkpoint_blobs, checkpoint_writes, checkpoint_migrations
```

**Connection budget (Wave 10).** The checkpointer pools against this same
instance. Keep `CHECKPOINT_POOL_MAX` (default 10) × `backend_max_instances`
(default 10) + metadata connect-per-op headroom **under** Postgres
`max_connections`. On the default `db_tier` (db-custom-1-3840, 3.75 GB)
Postgres's computed default is in the hundreds — ample for 10 × 10 = 100 — so
the terraform pins no lower value. `min_size` is 0, so idle/scaled-to-zero
instances hold no connections; the budget is a peak-load ceiling. If you shrink
`db_tier` to a shared-core micro, add an explicit `database_flags`
`max_connections` ≥ the budget. See `plans/hosted-chat-durability.md`.

**Config fail-fast.** With `persistence_engine=postgres` (the hosted default) and
an empty `DATABASE_URL`, the backend **refuses to boot** (rather than silently
degrading to ephemeral SQLite and losing conversations). If startup logs show
that RuntimeError, the `database-url` secret is unpopulated or mis-resolved.

## 5. Smoke test

1. Open `backend_url`; confirm anonymous lint/sim works.
2. Sign in with Google; start a synth — confirm a Cloud Run **Job** execution
   appears (`gcloud run jobs executions list --job siliconcrew-orfs`).
3. Confirm artifacts land in `gs://<workspace_bucket>/orfs-runs/<handle>/out.tar.gz`
   and the run's `run_meta.json` carries a `provenance` block (commit + digest).
4. Verify quotas: a sixth concurrent synth for the same user is rejected
   (`concurrency_limit`); anonymous synth is rejected (`signin_required`).

## 6. Heavy verification (nightly, inside the EDA image)

Run the gated real-ORFS check — it is skipped in per-PR CI:

```bash
RUN_REAL_ORFS=1 ORFS_IMAGE="${REPO}/orfs@sha256:..." pytest tests/test_orfs_runner.py
```

## Rollback

- **Backend:** Cloud Run keeps revisions — `gcloud run services update-traffic
  siliconcrew-backend --to-revisions=<prev>=100`.
- **ORFS image:** revert `orfs_image` to the previous digest and `terraform apply`.
- **DB schema:** migrations are additive (CREATE IF NOT EXISTS / guarded
  ALTERs); to recover data use Cloud SQL PITR (enabled in prod).
- **Infra:** `terraform apply` a previous state; `prevent_destroy` guards the
  KMS key and (in prod) the SQL instance.

## Cost controls

- Budget alerts at 50/90/100% (`google_billing_budget`).
- Hosted-tier hard caps in-app: per-user tokens/day + a global cost ceiling
  (`HostedTierLimiter`) — when hit, users are asked to add a BYOK key.
- Per-user synth caps (5 concurrent by default, runs/day, compute-minutes/month) bound the
  expensive path. Scale-to-zero keeps idle cost ~0.
- Watch: Cloud Run Job vCPU-seconds, Cloud SQL tier, egress, GCS storage.

## Light EDA tools without Docker (`SIM_ENGINE`)

ORFS runs as an isolated Cloud Run Job. The three lighter engines — **XLS**
(DSLX→Verilog), **SymbiYosys** (formal), **cocotb** — run via the `ToolEngine`
seam (`src/platform_engines/tool_engine.py`), selected once by `SIM_ENGINE`:

| `SIM_ENGINE` | Engine | Where it runs | Default |
|---|---|---|---|
| `docker` | `DockerToolEngine` | a container via `run_docker_command` | **local** (plug-and-play) |
| `native` | `NativeToolEngine` | a subprocess in the per-session workspace cwd | **hosted** (Cloud Run has no nested containers) |

Hosted uses `native` because Cloud Run cannot run nested containers; native sims
are subprocesses (<~1s overhead), keeping the interactive edit-run loop fast.
The hosted image (`Dockerfile`, `INSTALL_NATIVE_TOOLCHAINS=1`) ships the
binaries: `iverilog`/`yosys` (base) + cocotb (pip) + `build-essential` + `z3` +
`sby` + Google XLS on PATH. **Verify the XLS release tarball** lands its binaries
on PATH (`XLS_VERSION`, optionally `XLS_SHA256`); a failed download now fails the
backend image build instead of shipping an image where native XLS reports
`interpreter_main: not found`.

### Isolation — honest scope (NOT container-grade)

Native subprocesses share the **app's Cloud Run instance**, and Cloud Run may
serve **multiple requests per instance** — so this is **per-instance**, not
**per-run**, isolation (weaker than Docker-per-run). It is made safe-enough by:

- **Per-session cwd:** every tool runs in its own session workspace dir (the
  tenancy seam), never a shared dir; cross-tenant paths can't be reached.
- **Timeouts + tree-kill:** each tool has a hard timeout; the native engine puts
  the subprocess in its own process group and SIGKILLs the whole tree on expiry.
- **Build artifacts off-workspace:** cocotb builds in a unique `/tmp/sc_build_*`.

Operational recommendations (do these for true per-request isolation):

- **Set Cloud Run `containerConcurrency = 1`** on the app service so one instance
  handles one request at a time → effectively per-run isolation for native sims.
- Run the app process as a **non-root user** (Cloud Run already sandboxes each
  instance with gVisor; non-root + read-only base FS further limits blast radius).
- Keep per-user synth/compute quotas (already enforced) to bound abuse.

Do **not** describe native mode as "fully isolated / container-grade." For
untrusted multi-tenant workloads needing strict per-run isolation while allowing
user-level parallelism, run the light tools as Cloud Run Jobs too (same seam can
grow a `cloud_job` `ToolEngine`), trading the ~6s cold-start the interactive loop
avoids.

## Security notes

- BYOK keys are envelope-encrypted (KMS KEK wraps a per-key DEK); only wrapped
  DEK + ciphertext are stored, decrypted per-request, never logged or env-set.
- ORFS runs in an isolated Cloud Run Job — **no host Docker socket** is shared.
- Least-privilege service accounts; the ORFS job touches only the workspace
  bucket. Tenant isolation is enforced by the session seam + per-query scoping
  and gated by `tests/test_concurrency_isolation.py`.
