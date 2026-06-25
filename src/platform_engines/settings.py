"""Startup configuration that selects local vs cloud engines — once, centrally.

The README's core rule: do **not** scatter ``if hosted: ... else: ...`` across
the codebase. Read config here, build the chosen engines once, and let call
sites depend only on the interfaces. ``HOSTED`` is the single master switch;
individual engines can still be overridden for staged rollout / testing.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class PlatformSettings:
    """Resolved platform configuration. Built once from the environment."""

    hosted: bool

    # ORFS execution
    orfs_engine: str          # "local_docker" | "cloud_job" | "remote"
    orfs_image: str           # repo/name:tag (cloud should pin @sha256:...)
    cloud_run_job: str        # Cloud Run Job resource name (cloud only)
    gcp_project: str
    gcp_region: str
    orfs_service_url: str     # standalone ORFS HTTP service (orfs_engine=remote)
    orfs_service_token: str   # bearer token for that service

    # Light EDA tools (xls / sby / cocotb) execution: "docker" | "native".
    # native = subprocess in the per-session cwd (Cloud Run safe, no nested
    # containers); docker = today's container path (local default).
    sim_engine: str

    # Auth
    google_oauth_client_id: str  # OAuth audience; empty disables token verification

    # Remote-MCP auth via WorkOS (hosted only — the deployed multi-tenant
    # service). WorkOS is the "front desk": it runs the login UI, "Sign in with
    # Google", and token issue/refresh/revoke. We only validate the token it
    # issues on each MCP request. Every field is empty in local/self-host and is
    # never read there — gated by ``hosted`` at the call sites.
    workos_issuer: str        # token `iss` (e.g. https://api.workos.com/.../<client>)
    workos_jwks_url: str      # JWKS endpoint for RS256 signature verification
    workos_audience: str      # expected `aud` = our MCP resource identifier
    workos_client_id: str     # WorkOS client id (informational / web sign-in)
    mcp_resource_url: str     # public MCP resource URL named in RFC 9728 metadata

    # Workspace storage
    workspace_engine: str     # "local" | "cloud"
    workspace_bucket: str     # GCS bucket (cloud only)
    workspace_scratch_dir: str

    # Persistence
    persistence_engine: str   # "sqlite" | "postgres"
    database_url: str

    # LLM keys
    llm_key_engine: str       # "env" | "byok"
    kms_key_uri: str          # Cloud KMS key for envelope encryption (byok)
    hosted_gemini_model: str
    hosted_gemini_key: str

    # Determinism
    num_cores: int            # pinned NUM_CORES for ORFS P&R

    # Dev-only auth escape hatch — OFF by default; explicit opt-in only, never
    # enabled by mere misconfiguration. (Must be last: it carries a default.)
    dev_insecure_auth: bool = False

    # Static service/test bearer token (staging only). When set, a request whose
    # Bearer equals this secret authenticates as a fixed test identity — so
    # automated agents/CI can drive signed-in flows without a real Google login.
    # Empty (default) = feature off. NEVER set in production.
    test_bearer_token: str = ""

    @property
    def workos_configured(self) -> bool:
        """True when WorkOS token validation can run (hosted MCP auth).

        Requires the issuer, the JWKS endpoint, and the expected audience; the
        absence of any one disables remote-MCP auth (and is a misconfiguration
        in hosted mode, surfaced as a 401 rather than silent anonymous access).
        """
        return bool(self.workos_issuer and self.workos_jwks_url and self.workos_audience)

    @property
    def is_cloud_orfs(self) -> bool:
        return self.orfs_engine == "cloud_job"

    @property
    def is_cloud_workspace(self) -> bool:
        return self.workspace_engine == "cloud"


@lru_cache(maxsize=1)
def get_settings() -> PlatformSettings:
    """Build (and cache) the platform settings from the environment."""
    hosted = _flag("SILICONCREW_HOSTED", default=False)

    # Each engine defaults to its local impl, flipping to cloud under HOSTED,
    # but every choice is independently overridable for staged rollout.
    orfs_engine = _env("ORFS_ENGINE", "cloud_job" if hosted else "local_docker")
    sim_engine = _env("SIM_ENGINE", "native" if hosted else "docker")
    workspace_engine = _env("WORKSPACE_ENGINE", "cloud" if hosted else "local")
    persistence_engine = _env("PERSISTENCE_ENGINE", "postgres" if hosted else "sqlite")
    llm_key_engine = _env("LLM_KEY_ENGINE", "byok" if hosted else "env")

    return PlatformSettings(
        hosted=hosted,
        orfs_engine=orfs_engine,
        orfs_image=_env("ORFS_IMAGE", "openroad/orfs:latest"),
        cloud_run_job=_env("ORFS_CLOUD_RUN_JOB", "siliconcrew-orfs"),
        gcp_project=_env("GCP_PROJECT"),
        gcp_region=_env("GCP_REGION", "us-central1"),
        orfs_service_url=_env("ORFS_SERVICE_URL"),
        orfs_service_token=_env("ORFS_SERVICE_TOKEN"),
        sim_engine=sim_engine,
        google_oauth_client_id=_env("GOOGLE_OAUTH_CLIENT_ID"),
        workos_issuer=_env("WORKOS_ISSUER"),
        workos_jwks_url=_env("WORKOS_JWKS_URL"),
        workos_audience=_env("WORKOS_AUDIENCE"),
        workos_client_id=_env("WORKOS_CLIENT_ID"),
        mcp_resource_url=_env("MCP_RESOURCE_URL"),
        workspace_engine=workspace_engine,
        workspace_bucket=_env("WORKSPACE_BUCKET"),
        workspace_scratch_dir=_env("WORKSPACE_SCRATCH_DIR", "/tmp/siliconcrew-scratch"),
        persistence_engine=persistence_engine,
        database_url=_env("DATABASE_URL"),
        llm_key_engine=llm_key_engine,
        kms_key_uri=_env("KMS_KEY_URI"),
        hosted_gemini_model=_env("HOSTED_GEMINI_MODEL", "gemini-3-flash-preview"),
        hosted_gemini_key=_env("HOSTED_GEMINI_KEY"),
        num_cores=int(_env("ORFS_NUM_CORES", "4")),
        dev_insecure_auth=_flag("SILICONCREW_DEV_INSECURE_AUTH", default=False),
        test_bearer_token=_env("SILICONCREW_TEST_BEARER_TOKEN"),
    )


def reset_settings_cache() -> None:
    """Test hook: drop the cached settings so env overrides take effect."""
    get_settings.cache_clear()


_WIRED = False


def apply_platform_wiring(force: bool = False) -> None:
    """The single wiring point: bind cloud engines from settings, once.

    Called at app startup (api.py, mcp_server.py). No-op in self-host — the
    engine factories already default to local impls, so nothing changes. In
    hosted mode this installs the per-user job queue and the shared quota
    manager so synthesis is governed across the fleet. All imports are lazy so
    importing this module never drags in cloud deps.
    """
    global _WIRED
    if _WIRED and not force:
        return

    settings = get_settings()
    if settings.hosted:
        # Replace the process-global ThreadPoolExecutor with a per-user queue so
        # one tenant's backlog cannot starve others (and enforce 1 synth/user).
        from src.platform_engines.job_queue import ContextUserExecutor, PerUserJobQueue
        from src.tools import synthesis_manager

        synthesis_manager.set_job_executor(
            ContextUserExecutor(PerUserJobQueue(global_workers=8, per_user_limit=1))
        )

        # Shared quota manager (Postgres-backed under hosted+Postgres) enforced
        # around every synth submission. See quotas.build_quota_manager.
        from src.platform_engines.quotas import build_quota_manager

        synthesis_manager.set_quota_manager(build_quota_manager(settings))

    _WIRED = True


def reset_wiring() -> None:
    """Test hook: allow apply_platform_wiring to run again."""
    global _WIRED
    _WIRED = False
