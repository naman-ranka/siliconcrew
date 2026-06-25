"""Swappable platform engines for the deployed SiliconCrew backend (Phase 2).

The tool/agent code is single-tenant and locally correct. Multi-tenant
deployment is achieved **not** by forking that code but by routing its
side-effecting seams through small interfaces, each with a *local* impl (=
today's behavior, refactored) and a *cloud* impl, chosen once at startup by
config (:mod:`src.platform_engines.settings`).

Interfaces:
  * :mod:`orfs_runner`        — where ORFS executes (local Docker vs Cloud Run Job)
  * :mod:`workspace_provider` — where workspaces live (local dir vs object storage)
  * :mod:`persistence`        — session/run metadata (sqlite vs Postgres)
  * :mod:`llm_keys`           — which LLM key a request uses (env vs BYOK / hosted)
  * :mod:`quotas`, :mod:`job_queue`, :mod:`identity` — tenancy governance
  * :mod:`provenance`         — reproducibility stamp on every run

Nothing here changes self-host behavior: the cloud engines activate only when
``SILICONCREW_HOSTED`` is set. Local stays the default.
"""
