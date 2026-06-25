# SiliconCrew Hosted Frontend — Cloud Run Service (Phase 2, deploy-ready).

resource "google_cloud_run_v2_service" "frontend" {
  name     = "siliconcrew-frontend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"
  depends_on = [
    google_project_service.services,
    google_cloud_run_v2_service.backend
  ]

  template {
    # Simple scaling settings for the frontend UI
    scaling {
      min_instance_count = 0 # scale to zero when idle
      max_instance_count = 5
    }

    containers {
      image = var.frontend_image
      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      # Backend URLs are read at RUNTIME (non-NEXT_PUBLIC_, so not inlined at
      # build) and injected into the page by the server layout. This is what
      # makes the prebuilt image environment-agnostic. See lib/runtime-config.ts.
      env {
        name  = "API_URL"
        value = google_cloud_run_v2_service.backend.uri
      }

      env {
        name  = "WS_URL"
        value = replace(google_cloud_run_v2_service.backend.uri, "https://", "wss://")
      }

      # Google sign-in client ID, injected at runtime (public value). Empty = no
      # sign-in UI (self-host / anonymous). Must equal the backend's
      # GOOGLE_OAUTH_CLIENT_ID. See lib/runtime-config.ts + lib/auth.tsx.
      env {
        name  = "GOOGLE_CLIENT_ID"
        value = var.google_oauth_client_id
      }
    }
  }

  # Image rolled out by the CD pipeline (gcloud run deploy, SHA-tagged); keep
  # Terraform from reverting it. See deploy/CICD.md.
  lifecycle {
    ignore_changes = [template[0].containers[0].image]
  }
}

# Allow public unauthenticated access to the frontend UI
resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  name     = google_cloud_run_v2_service.frontend.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# Output the public URL for the frontend application
output "frontend_url" {
  value       = google_cloud_run_v2_service.frontend.uri
  description = "The public URL of the SiliconCrew web application UI."
}
