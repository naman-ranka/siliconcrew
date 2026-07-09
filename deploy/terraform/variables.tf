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

# --- Auth (WorkOS AuthKit remote auth + identity unification) ---
variable "workos_client_id" {
  type        = string
  default     = ""
  description = "WorkOS Client ID. Enables unified AuthKit authentication across web and remote MCP."
}

variable "workos_authkit_domain" {
  type        = string
  default     = ""
  description = "AuthKit OAuth issuer/domain for MCP discovery, e.g. https://tenant.authkit.app. When set, MCP clients use AuthKit OAuth metadata/DCR while web tokens keep using WORKOS_CLIENT_ID."
}

variable "workos_audience" {
  type        = string
  default     = ""
  description = "MCP service audience (the registered resource indicator, e.g. https://api.siliconcrew.app/mcp). Leave empty on web-only."
}

variable "mcp_resource_url" {
  type        = string
  default     = ""
  description = "Public MCP resource URL named in RFC 9728 metadata."
}

variable "workos_redirect_uri" {
  type        = string
  default     = ""
  description = "Custom redirect URI callback registered in WorkOS (defaults to browser origin if empty)."
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

# --- Hosted synth governance ---
variable "synth_runs_per_day" {
  type        = number
  default     = 20
  description = "Signed-in per-user synthesis run cap per UTC day."
}

variable "synth_compute_minutes_per_month" {
  type        = number
  default     = 600
  description = "Signed-in per-user synthesis compute-minute cap per UTC month."
}

variable "synth_max_concurrent_per_user" {
  type        = number
  default     = 5
  description = "Maximum in-flight synthesis jobs per signed-in user."
}

variable "synth_queue_global_workers" {
  type        = number
  default     = 16
  description = "Backend process-wide synth queue worker count."
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
