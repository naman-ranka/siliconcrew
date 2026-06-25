variable "project_id" {
  type        = string
  description = "GCP project id to deploy into."
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "environment" {
  type    = string
  default = "staging"
  validation {
    condition     = contains(["staging", "prod"], var.environment)
    error_message = "environment must be 'staging' or 'prod'."
  }
}

variable "vpc_self_link" {
  type        = string
  description = "Self link of the VPC for private Cloud SQL connectivity."
  default     = null
}

# --- Images (push to Artifact Registry first; digest-pin in prod) ---
variable "backend_image" {
  type        = string
  description = "Backend container image (…/siliconcrew/backend@sha256:…)."
}

variable "frontend_image" {
  type        = string
  description = "Frontend Next.js container image (…/siliconcrew/frontend@sha256:…)."
}

variable "orfs_image" {
  type        = string
  description = "ORFS image, digest-pinned (…/siliconcrew/orfs@sha256:…) for reproducibility."
}

# --- Auth (Google OAuth) ---
variable "google_oauth_client_id" {
  type        = string
  default     = ""
  description = <<-EOT
    Google OAuth Web Client ID. Wired to the backend (GOOGLE_OAUTH_CLIENT_ID, for
    token verification) and the frontend (GOOGLE_CLIENT_ID, injected at runtime for
    the sign-in button). Public value, so plain (not a Secret). Empty = no auth:
    self-host / anonymous-trial behavior. Add the frontend URL to the OAuth
    client's Authorized JavaScript origins or GIS will refuse to load.
  EOT
}

# --- Cloud SQL ---
variable "db_tier" {
  type    = string
  default = "db-custom-1-3840"
}

variable "db_password" {
  type      = string
  sensitive = true
}

# --- Backend scaling ---
variable "backend_min_instances" {
  type    = number
  default = 0 # scale to zero; bursty + mostly idle
}

variable "backend_max_instances" {
  type    = number
  default = 10
}

# --- ORFS job sizing (P&R is memory-heavy) ---
variable "orfs_cpu" {
  type    = string
  default = "4"
}

variable "orfs_memory" {
  type    = string
  default = "8Gi"
}

variable "orfs_timeout_seconds" {
  type    = number
  default = 1800
}

variable "orfs_num_cores" {
  type        = number
  default     = 4
  description = "Pinned NUM_CORES for P&R determinism (matches ORFS_NUM_CORES)."
}

# --- Storage ---
variable "workspace_retention_days" {
  type    = number
  default = 90
}

# --- Budget ---
variable "billing_account" {
  type        = string
  default     = ""
  description = "Billing account id for the budget alert (empty disables it)."
}

variable "monthly_budget_usd" {
  type    = number
  default = 200
}
