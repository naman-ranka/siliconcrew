# Remote state in GCS — required so the manual Terraform GitHub Actions workflow
# (and your laptop) share one authoritative state. The bucket itself is created
# ONCE, out-of-band, before `terraform init` (a bucket can't store the state that
# creates it). See deploy/CICD.md for the one-time `gcloud storage buckets create`.
#
# The bucket name is supplied at init time, not hardcoded, so this file has no
# project-specific values:
#   terraform init -backend-config="bucket=<PROJECT_ID>-siliconcrew-tfstate"
terraform {
  backend "gcs" {
    prefix = "terraform/state"
  }
}
