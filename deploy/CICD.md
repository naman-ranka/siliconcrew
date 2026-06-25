# CI/CD — how a push reaches Google Cloud

Three GitHub Actions workflows, with a clean split between fast app rollouts and
deliberate, manual infra changes.

| Workflow | File | Trigger | Does |
|----------|------|---------|------|
| **CI** | `.github/workflows/ci.yml` | every push + PR | backend pytest, frontend vitest + build, `terraform fmt -check` |
| **Deploy App** | `.github/workflows/deploy-app.yml` | **auto**, after CI succeeds on `main` | build + push SHA-tagged backend & frontend images, `gcloud run deploy` |
| **Terraform** | `.github/workflows/terraform.yml` | **manual** (`workflow_dispatch`) | `terraform plan` / `apply` for infra |

**Deploy model = Model A.** App images are rolled out by `gcloud run deploy`; the
two Cloud Run services have `lifecycle.ignore_changes` on their image so
Terraform never reverts a rollout. Everything else (env vars, secrets, scaling,
the OAuth var, Cloud SQL, the ORFS job) stays Terraform-owned.

> **Routine reminder:** after you change anything under `deploy/terraform/`, run
> the **Terraform** workflow yourself (plan, then apply). Deploy App will *not*
> apply infra for you — that separation is intentional.

Auth is **keyless** via Workload Identity Federation — no service-account JSON key
is ever stored in GitHub.

---

## One-time setup (~30 min, run locally with `gcloud`)

```bash
# --- fill these in ---
export PROJECT_ID="your-project-id"
export REGION="us-central1"
export REPO="naman-ranka/siliconcrew"          # owner/repo
export SA="siliconcrew-deployer"
# ---------------------
export PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
export SA_EMAIL="${SA}@${PROJECT_ID}.iam.gserviceaccount.com"

# 1) Enable the APIs the pipeline needs
gcloud services enable \
  iamcredentials.googleapis.com sts.googleapis.com \
  run.googleapis.com artifactregistry.googleapis.com \
  cloudresourcemanager.googleapis.com --project "$PROJECT_ID"

# 2) Deployer service account + roles
gcloud iam service-accounts create "$SA" --project "$PROJECT_ID" \
  --display-name "SiliconCrew CI/CD deployer"

# run.admin + artifactregistry.writer + act-as cover Deploy App. The rest let the
# Terraform workflow manage infra. roles/editor is broad for convenience — scope
# it down once things are stable.
for ROLE in \
  roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser \
  roles/editor roles/storage.admin roles/secretmanager.admin roles/cloudsql.admin; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:${SA_EMAIL}" --role="$ROLE" --condition=None
done

# 3) Workload Identity Federation — let GitHub Actions impersonate the SA (keyless)
gcloud iam workload-identity-pools create github-pool \
  --project "$PROJECT_ID" --location global --display-name "GitHub Actions"

gcloud iam workload-identity-pools providers create-oidc github-provider \
  --project "$PROJECT_ID" --location global --workload-identity-pool github-pool \
  --display-name "GitHub OIDC" \
  --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
  --attribute-condition="assertion.repository=='${REPO}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Bind: only THIS repo may impersonate the deployer SA
gcloud iam service-accounts add-iam-policy-binding "$SA_EMAIL" --project "$PROJECT_ID" \
  --role roles/iam.workloadIdentityUser \
  --member "principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/attribute.repository/${REPO}"

# This is the GCP_WIF_PROVIDER value you'll paste into GitHub:
echo "projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/github-pool/providers/github-provider"

# 4) GCS bucket for Terraform remote state (created before terraform init)
gcloud storage buckets create "gs://${PROJECT_ID}-siliconcrew-tfstate" \
  --project "$PROJECT_ID" --location "$REGION" --uniform-bucket-level-access
gcloud storage buckets update "gs://${PROJECT_ID}-siliconcrew-tfstate" --versioning
```

## GitHub configuration

**Settings → Secrets and variables → Actions → Variables** (not secret):

| Variable | Value |
|----------|-------|
| `GCP_PROJECT_ID` | your project id |
| `GCP_REGION` | `us-central1` |
| `GCP_WIF_PROVIDER` | the `projects/…/providers/github-provider` string printed above |
| `GCP_DEPLOY_SA` | `siliconcrew-deployer@<PROJECT_ID>.iam.gserviceaccount.com` |
| `GOOGLE_OAUTH_CLIENT_ID` | your OAuth Web client id (or leave empty for no auth) |
| `WORKOS_ISSUER` / `WORKOS_JWKS_URL` / `WORKOS_AUDIENCE` / `WORKOS_CLIENT_ID` / `MCP_RESOURCE_URL` | remote-MCP auth + web/MCP unification (hosted only; leave empty to keep Google sign-in). See `deploy/MCP_REMOTE_AUTH.md` |
| `BACKEND_IMAGE` | bootstrap with `us-docker.pkg.dev/cloudrun/container/hello` |
| `FRONTEND_IMAGE` | bootstrap with `us-docker.pkg.dev/cloudrun/container/hello` |
| `ORFS_IMAGE` | the real ORFS image once pushed (see bootstrap) |

**Settings → Secrets** (secret):

| Secret | Value |
|--------|-------|
| `TF_DB_PASSWORD` | a strong Cloud SQL password |

> The `…/hello` placeholders exist only so the **first** Terraform apply can
> create the Cloud Run services (a service needs *some* image to exist). Because
> the services ignore image changes, Deploy App immediately replaces them with
> real builds and Terraform never reverts. The ORFS **job** image is *not*
> ignored, so set `ORFS_IMAGE` to the real one.

## Bootstrap order (first time only)

1. Do the `gcloud` setup + GitHub config above (placeholders for the two app images).
2. Run the **Terraform** workflow → `plan`, eyeball it, then `apply`. This creates
   Artifact Registry, the Cloud Run services (on the placeholder), the ORFS job,
   Cloud SQL, secrets, etc.
3. Build + push the real **ORFS** image once, set `ORFS_IMAGE` to it, re-run
   **Terraform** → `apply` (updates the job).
4. Push to `main` (or merge a PR). CI runs; on success **Deploy App** builds and
   rolls out the real backend + frontend. Done.

After bootstrap, the steady state is just: **push to `main` → live in a few
minutes**; **infra change → run the Terraform workflow yourself**.

## Day-to-day

- **Ship code:** open a PR (CI runs) → merge to `main` → Deploy App auto-rolls it out.
- **Change infra** (env, secrets, scaling, OAuth, resources): edit `deploy/terraform/**`,
  push, then Actions → **Terraform** → run with `plan`, review, run again with `apply`.
- **Roll back app:** `gcloud run services update-traffic siliconcrew-backend \
  --region us-central1 --to-revisions=<previous-revision>=100` (Cloud Run keeps
  every revision). Same for the frontend.

## Optional hardening (later)

- Require a reviewer on apply: create a GitHub **Environment** with a protection
  rule and add `environment: production` to the apply job.
- Replace `roles/editor` on the deployer SA with the minimal role set.
- Digest-pin images (`@sha256:…`) for fully reproducible deploys.
- Protect `main` so merges require CI to pass (then direct pushes can't skip it).
