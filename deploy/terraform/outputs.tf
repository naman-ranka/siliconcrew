output "backend_url" {
  value       = google_cloud_run_v2_service.backend.uri
  description = "Public URL of the SiliconCrew backend."
}

output "workspace_bucket" {
  value = google_storage_bucket.workspaces.name
}

output "orfs_job_name" {
  value = google_cloud_run_v2_job.orfs.name
}

output "kms_key_uri" {
  value = google_kms_crypto_key.byok_kek.id
}

output "cloud_sql_connection_name" {
  value = google_sql_database_instance.metadata.connection_name
}

output "artifact_registry" {
  value = google_artifact_registry_repository.images.name
}
