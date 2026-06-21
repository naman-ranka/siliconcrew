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

## 4. Initialize the database

The backend calls `MetadataStore.init_schema()` on boot (idempotent). Verify:

```bash
gcloud sql connect siliconcrew-metadata --user=siliconcrew --database=siliconcrew \
  -e "\dt"   # expect: projects, session_metadata
```

## 5. Smoke test

1. Open `backend_url`; confirm anonymous lint/sim works.
2. Sign in with Google; start a synth — confirm a Cloud Run **Job** execution
   appears (`gcloud run jobs executions list --job siliconcrew-orfs`).
3. Confirm artifacts land in `gs://<workspace_bucket>/orfs-runs/<handle>/out.tar.gz`
   and the run's `run_meta.json` carries a `provenance` block (commit + digest).
4. Verify quotas: a second concurrent synth for the same user is rejected
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
- Per-user synth caps (1 concurrent, runs/day, compute-minutes/month) bound the
  expensive path. Scale-to-zero keeps idle cost ~0.
- Watch: Cloud Run Job vCPU-seconds, Cloud SQL tier, egress, GCS storage.

## Security notes

- BYOK keys are envelope-encrypted (KMS KEK wraps a per-key DEK); only wrapped
  DEK + ciphertext are stored, decrypted per-request, never logged or env-set.
- ORFS runs in an isolated Cloud Run Job — **no host Docker socket** is shared.
- Least-privilege service accounts; the ORFS job touches only the workspace
  bucket. Tenant isolation is enforced by the session seam + per-query scoping
  and gated by `tests/test_concurrency_isolation.py`.
