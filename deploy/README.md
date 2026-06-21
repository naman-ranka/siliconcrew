# deploy/ — SiliconCrew hosted backend (deploy-ready)

Everything needed for the **owner** to take the multi-tenant backend live on GCP.
Nothing here provisions or spends on its own.

```
deploy/
├── RUNBOOK.md         step-by-step deploy, secrets, smoke test, rollback, cost
├── terraform/         IaC: Cloud Run + Cloud Run Job + GCS + Cloud SQL + AR + KMS
│   ├── main.tf
│   ├── variables.tf
│   └── outputs.tf
└── orfs_job/          the ORFS Cloud Run Job (isolated synth sandbox)
    ├── Dockerfile     thin layer over the upstream ORFS image + gcloud
    └── entrypoint.sh  stage-in → run ORFS → stage-out (matches CloudJobOrfsRunner)
```

## How it maps to the code

The backend stays single binary; cloud behavior is selected by config, not forks:

| Seam (interface) | Local impl (default) | Cloud impl (HOSTED) | Selected by |
|---|---|---|---|
| `OrfsRunner` | `LocalDockerOrfsRunner` | `CloudJobOrfsRunner` → this Job | `ORFS_ENGINE` |
| `WorkspaceProvider` | `LocalWorkspaceProvider` | `CloudWorkspaceProvider` (GCS) | `WORKSPACE_ENGINE` |
| `MetadataStore` | `SqliteMetadataStore` | `PostgresMetadataStore` (Cloud SQL) | `PERSISTENCE_ENGINE` |
| `LlmKeyProvider` | `EnvLlmKeyProvider` | `ByokHostedLlmKeyProvider` (KMS) | `LLM_KEY_ENGINE` |

Start with `RUNBOOK.md`.
