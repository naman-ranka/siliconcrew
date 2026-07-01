# SiliconCrew hosted backend — GCP infrastructure (Phase 2, deploy-ready).
#
# Locked architecture: Cloud Run (backend) + Cloud Run Jobs (ORFS) + Cloud
# Storage (workspaces) + Cloud SQL/Postgres (metadata) + Artifact Registry
# (images) + Cloud KMS (BYOK envelope encryption).
#
# Posture: the OWNER runs `terraform apply`. This file provisions nothing on its
# own. Review variables.tf and RUNBOOK.md first. Costs accrue on apply.

terraform {
  required_version = ">= 1.5"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  # Recommended: a GCS backend for shared state (configure in backend.tf).
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  labels = {
    app = "siliconcrew"
    env = var.environment
  }
}

# ---------------------------------------------------------------------------
# APIs
# ---------------------------------------------------------------------------

resource "google_project_service" "services" {
  for_each = toset([
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudkms.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbuild.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------------------
# Artifact Registry — backend image + the 6.5 GB ORFS image
# ---------------------------------------------------------------------------

resource "google_artifact_registry_repository" "images" {
  location      = var.region
  repository_id = "siliconcrew"
  format        = "DOCKER"
  description   = "SiliconCrew backend + ORFS images"
  labels        = local.labels
  depends_on    = [google_project_service.services]
}

# ---------------------------------------------------------------------------
# Cloud Storage — per-session workspaces + staged ORFS run dirs
# ---------------------------------------------------------------------------

resource "google_storage_bucket" "workspaces" {
  name                        = "${var.project_id}-siliconcrew-workspaces"
  location                    = var.region
  uniform_bucket_level_access = true
  force_destroy               = false
  labels                      = local.labels

  # Tenant data: short-lived staging tarballs are cleaned up; keep real
  # workspaces. Tune to taste.
  lifecycle_rule {
    condition { age = var.workspace_retention_days }
    action { type = "Delete" }
  }
}

# ---------------------------------------------------------------------------
# Cloud KMS — KEK for BYOK envelope encryption
# ---------------------------------------------------------------------------

resource "google_kms_key_ring" "byok" {
  name       = "siliconcrew-byok"
  location   = var.region
  depends_on = [google_project_service.services]
}

resource "google_kms_crypto_key" "byok_kek" {
  name            = "byok-kek"
  key_ring        = google_kms_key_ring.byok.id
  rotation_period = "7776000s" # 90 days
  purpose         = "ENCRYPT_DECRYPT"
  lifecycle { prevent_destroy = true }
}

# ---------------------------------------------------------------------------
# Cloud SQL — Postgres metadata store
# ---------------------------------------------------------------------------

resource "google_sql_database_instance" "metadata" {
  name             = "siliconcrew-metadata"
  database_version = "POSTGRES_15"
  region           = var.region
  depends_on       = [google_project_service.services]

  settings {
    tier              = var.db_tier
    availability_type = var.environment == "prod" ? "REGIONAL" : "ZONAL"
    disk_autoresize   = true
    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }
    ip_configuration {
      ipv4_enabled    = var.vpc_self_link == null ? true : false
      private_network = var.vpc_self_link
    }
  }
  deletion_protection = var.environment == "prod"
}

resource "google_sql_database" "metadata" {
  name     = "siliconcrew"
  instance = google_sql_database_instance.metadata.name
}

resource "google_sql_user" "app" {
  name     = "siliconcrew"
  instance = google_sql_database_instance.metadata.name
  password = var.db_password # supply via TF_VAR_db_password / Secret Manager
}

# ---------------------------------------------------------------------------
# Service accounts — least privilege for backend + ORFS job
# ---------------------------------------------------------------------------

resource "google_service_account" "backend" {
  account_id   = "siliconcrew-backend"
  display_name = "SiliconCrew backend (Cloud Run)"
}

resource "google_service_account" "orfs_job" {
  account_id   = "siliconcrew-orfs"
  display_name = "SiliconCrew ORFS runner (Cloud Run Job)"
}

# Backend: read/write workspaces, use the KEK, connect to Cloud SQL, run jobs.
resource "google_storage_bucket_iam_member" "backend_workspaces" {
  bucket = google_storage_bucket.workspaces.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_kms_crypto_key_iam_member" "backend_kek" {
  crypto_key_id = google_kms_crypto_key.byok_kek.id
  role          = "roles/cloudkms.cryptoKeyEncrypterDecrypter"
  member        = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_sql" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_run_invoker" {
  project = var.project_id
  role    = "roles/run.developer" # submit Cloud Run Job executions
  member  = "serviceAccount:${google_service_account.backend.email}"
}

# ORFS job: read/write the staged run dirs in the workspace bucket only.
resource "google_storage_bucket_iam_member" "orfs_workspaces" {
  bucket = google_storage_bucket.workspaces.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.orfs_job.email}"
}

# ---------------------------------------------------------------------------
# Cloud Run Job — ORFS (isolated synth sandbox, parallel, scale-to-zero)
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_job" "orfs" {
  name       = "siliconcrew-orfs"
  location   = var.region
  depends_on = [google_project_service.services]

  template {
    template {
      service_account = google_service_account.orfs_job.email
      timeout         = "${var.orfs_timeout_seconds}s"
      max_retries     = 0
      containers {
        image = var.orfs_image # digest-pinned ORFS image in Artifact Registry
        resources {
          limits = {
            cpu    = var.orfs_cpu
            memory = var.orfs_memory # P&R is memory-hungry; size generously
          }
        }
        env {
          name  = "WORKSPACE_BUCKET"
          value = google_storage_bucket.workspaces.name
        }
      }
    }
  }
}

# ---------------------------------------------------------------------------
# Cloud Run — backend service (scale-to-zero; startup CPU boost for cold starts)
# ---------------------------------------------------------------------------

resource "google_cloud_run_v2_service" "backend" {
  name       = "siliconcrew-backend"
  location   = var.region
  ingress    = "INGRESS_TRAFFIC_ALL"
  depends_on = [google_project_service.services]

  template {
    service_account = google_service_account.backend.email
    scaling {
      min_instance_count = var.backend_min_instances
      max_instance_count = var.backend_max_instances
    }
    containers {
      image = var.backend_image
      resources {
        limits            = { cpu = "2", memory = "2Gi" }
        startup_cpu_boost = true
      }
      volume_mounts {
        name       = "cloudsql"
        mount_path = "/cloudsql"
      }
      env {
        name  = "SILICONCREW_HOSTED"
        value = "1"
      }
      # Allow the frontend Cloud Run service (cross-origin) by name. Using a regex
      # avoids referencing frontend.uri here, which would create a dependency
      # cycle (frontend already depends on the backend). Matches both the legacy
      # (...-<hash>-<region>.a.run.app) and current (...-<num>.<region>.run.app)
      # Cloud Run URL shapes.
      env {
        name  = "CORS_ALLOW_ORIGIN_REGEX"
        value = "https://siliconcrew-frontend-[a-z0-9-]+\\.(a\\.)?run\\.app"
      }
      env {
        name  = "FORCE_REDEPLOY"
        value = "1"
      }
      # OAuth audience for verifying Google ID tokens. Empty disables token
      # verification (self-host / anonymous-trial). Public value; same ID the
      # frontend uses. See src/platform_engines/auth.py.
      env {
        name  = "GOOGLE_OAUTH_CLIENT_ID"
        value = var.google_oauth_client_id
      }
      env {
        name  = "WORKOS_CLIENT_ID"
        value = var.workos_client_id
      }
      env {
        name  = "WORKOS_AUTHKIT_DOMAIN"
        value = var.workos_authkit_domain
      }
      env {
        name = "WORKOS_API_KEY"
        value_source {
          secret_key_ref {
            secret  = "workos-api-key"
            version = "latest"
          }
        }
      }
      env {
        name  = "WORKOS_AUDIENCE"
        value = var.workos_audience
      }
      env {
        name  = "MCP_RESOURCE_URL"
        value = var.mcp_resource_url
      }
      env {
        name  = "WORKSPACE_BUCKET"
        value = google_storage_bucket.workspaces.name
      }
      env {
        name  = "ORFS_CLOUD_RUN_JOB"
        value = google_cloud_run_v2_job.orfs.name
      }
      env {
        name  = "ORFS_IMAGE"
        value = var.orfs_image
      }
      env {
        name  = "KMS_KEY_URI"
        value = google_kms_crypto_key.byok_kek.id
      }
      env {
        name  = "GCP_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "ORFS_NUM_CORES"
        value = tostring(var.orfs_num_cores)
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = "database-url"
            version = "latest"
          }
        }
      }
      env {
        name = "HOSTED_GEMINI_KEY"
        value_source {
          secret_key_ref {
            secret  = "hosted-gemini-key"
            version = "latest"
          }
        }
      }
      env {
        name = "GOOGLE_API_KEY"
        value_source {
          secret_key_ref {
            secret  = "hosted-gemini-key"
            version = "latest"
          }
        }
      }
      env {
        name = "OPENAI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = "openai-api-key"
            version = "latest"
          }
        }
      }
      env {
        name = "ANTHROPIC_API_KEY"
        value_source {
          secret_key_ref {
            secret  = "anthropic-api-key"
            version = "latest"
          }
        }
      }
      env {
        name = "SILICONCREW_TEST_BEARER_TOKEN"
        value_source {
          secret_key_ref {
            secret  = "siliconcrew-test-bearer"
            version = "latest"
          }
        }
      }
    }
    volumes {
      name = "cloudsql"
      cloud_sql_instance {
        instances = [google_sql_database_instance.metadata.connection_name]
      }
    }
  }

  # The image is rolled out by the CD pipeline (gcloud run deploy, SHA-tagged),
  # so Terraform must not revert it on the next apply. Infra (env, scaling,
  # secrets) stays Terraform-owned. See deploy/CICD.md.
  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
}

# Public access to the backend (auth handled in-app via Google OAuth).
resource "google_cloud_run_v2_service_iam_member" "public" {
  name     = google_cloud_run_v2_service.backend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ---------------------------------------------------------------------------
# Budget alert — guard the hosted-tier spend ceiling
# ---------------------------------------------------------------------------

resource "google_billing_budget" "monthly" {
  count           = var.billing_account == "" ? 0 : 1
  billing_account = var.billing_account
  display_name    = "siliconcrew-${var.environment}-monthly"
  budget_filter {
    projects = ["projects/${var.project_id}"]
  }
  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.monthly_budget_usd)
    }
  }
  threshold_rules { threshold_percent = 0.5 }
  threshold_rules { threshold_percent = 0.9 }
  threshold_rules { threshold_percent = 1.0 }
}

# ---------------------------------------------------------------------------
# IAM bindings for Secret Manager
# ---------------------------------------------------------------------------

resource "google_secret_manager_secret_iam_member" "backend_db_url" {
  secret_id  = "database-url"
  role       = "roles/secretmanager.secretAccessor"
  member     = "serviceAccount:${google_service_account.backend.email}"
  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret_iam_member" "backend_gemini_key" {
  secret_id  = "hosted-gemini-key"
  role       = "roles/secretmanager.secretAccessor"
  member     = "serviceAccount:${google_service_account.backend.email}"
  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret_iam_member" "backend_openai_key" {
  secret_id  = "openai-api-key"
  role       = "roles/secretmanager.secretAccessor"
  member     = "serviceAccount:${google_service_account.backend.email}"
  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret_iam_member" "backend_anthropic_key" {
  secret_id  = "anthropic-api-key"
  role       = "roles/secretmanager.secretAccessor"
  member     = "serviceAccount:${google_service_account.backend.email}"
  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret_iam_member" "backend_test_bearer" {
  secret_id  = "siliconcrew-test-bearer"
  role       = "roles/secretmanager.secretAccessor"
  member     = "serviceAccount:${google_service_account.backend.email}"
  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret_iam_member" "backend_workos_api_key" {
  secret_id  = "workos-api-key"
  role       = "roles/secretmanager.secretAccessor"
  member     = "serviceAccount:${google_service_account.backend.email}"
  depends_on = [google_project_service.services]
}
