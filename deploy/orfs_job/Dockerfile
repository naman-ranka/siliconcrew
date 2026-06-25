# ORFS Cloud Run Job image: the upstream ORFS flow image + the gcloud CLI and
# our staging entrypoint. Keep the heavy ORFS layers intact (Image Streaming in
# Artifact Registry handles the ~6.5 GB efficiently); we only add a thin layer.
#
# Build & push (see RUNBOOK.md), then digest-pin the result as var.orfs_image.
ARG ORFS_BASE=openroad/orfs:latest
FROM ${ORFS_BASE}

# google-cloud-cli for `gcloud storage` (staging in/out).
RUN apt-get update && apt-get install -y --no-install-recommends curl python3 \
    && echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
       > /etc/apt/sources.list.d/google-cloud-sdk.list \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
       | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
    && apt-get update && apt-get install -y --no-install-recommends google-cloud-cli \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /usr/local/bin/orfs-job-entrypoint.sh
RUN chmod +x /usr/local/bin/orfs-job-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/orfs-job-entrypoint.sh"]
