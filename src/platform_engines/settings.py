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


def _int_env(name: str, default: int) -> int:
    return int(_env(name, str(default)))


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
    workos_authkit_domain: str # AuthKit OAuth issuer/domain for MCP, if enabled
    workos_api_key: str        # server-side key for Standalone Connect completion
    mcp_authorization_server: str # OAuth AS advertised in RFC 9728 metadata
    mcp_issuer: str            # issuer expected on MCP access tokens
    mcp_jwks_url: str          # JWKS endpoint for MCP access-token verification
    mcp_resource_url: str     # public MCP resource URL named in RFC 9728 metadata
    mcp_scopes_supported: tuple[str, ...] # scopes advertised to MCP clients

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

    # Hosted synth governance
    synth_runs_per_day: int
    synth_compute_minutes_per_month: int
    synth_max_concurrent_per_user: int
    synth_queue_global_workers: int

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

    # Codex runtime extension — OFF by default. When enabled, the Codex agent
    # runtime registers as a selectable extension (see src/agents/codex/). Off
    # means the app is exactly the native-only workbench.
    codex_enabled: bool = False

    @property
    def workos_configured(self) -> bool:
        """True when WorkOS token validation can run (hosted web + MCP auth).

        Requires the issuer and the JWKS endpoint (both derivable from the client
        id — see :func:`get_settings`). Audience is OPTIONAL: it is required only
        on the MCP resource server (where the token is audience-bound to the
        registered resource indicator); AuthKit web tokens carry no ``aud``.
        """
        return bool(self.workos_issuer and self.workos_jwks_url)

    @property
    def mcp_auth_configured(self) -> bool:
        """True when hosted MCP bearer-token validation can run.

        MCP may use the AuthKit OAuth domain as its authorization server while
        the web SPA keeps validating AuthKit JS user-management tokens. Keep the
        two verifier profiles separate so enabling standard MCP OAuth discovery
        does not break existing web sign-in.
        """
        return bool(self.mcp_issuer and self.mcp_jwks_url)

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
    # WorkOS (hosted auth). The issuer and JWKS endpoint are derivable from the
    # client id (api.workos.com defaults), so an operator usually sets only
    # WORKOS_CLIENT_ID (+ WORKOS_AUDIENCE on the MCP resource server). A custom
    # auth domain overrides the issuer/JWKS explicitly.
    workos_client_id = _env("WORKOS_CLIENT_ID")
    workos_issuer = _env("WORKOS_ISSUER") or (
        f"https://api.workos.com/user_management/{workos_client_id}" if workos_client_id else ""
    )
    workos_jwks_url = _env("WORKOS_JWKS_URL") or (
        f"https://api.workos.com/sso/jwks/{workos_client_id}" if workos_client_id else ""
    )
    workos_authkit_domain = _env("WORKOS_AUTHKIT_DOMAIN").rstrip("/")
    mcp_authorization_server = (
        _env("MCP_AUTHORIZATION_SERVER").rstrip("/")
        or workos_authkit_domain
        or workos_issuer
    )
    mcp_issuer = _env("MCP_ISSUER").rstrip("/") or mcp_authorization_server
    mcp_jwks_url = _env("MCP_JWKS_URL") or (
        f"{workos_authkit_domain}/oauth2/jwks" if workos_authkit_domain else workos_jwks_url
    )
    mcp_scopes_raw = _env("MCP_SCOPES_SUPPORTED") or (
        "openid,email,profile,offline_access" if workos_authkit_domain else "mcp"
    )
    mcp_scopes_supported = tuple(
        scope.strip() for scope in mcp_scopes_raw.replace(" ", ",").split(",") if scope.strip()
    )

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
        workos_issuer=workos_issuer,
        workos_jwks_url=workos_jwks_url,
        workos_audience=_env("WORKOS_AUDIENCE"),
        workos_client_id=workos_client_id,
        workos_authkit_domain=workos_authkit_domain,
        workos_api_key=_env("WORKOS_API_KEY"),
        mcp_authorization_server=mcp_authorization_server,
        mcp_issuer=mcp_issuer,
        mcp_jwks_url=mcp_jwks_url,
        mcp_resource_url=_env("MCP_RESOURCE_URL"),
        mcp_scopes_supported=mcp_scopes_supported,
        workspace_engine=workspace_engine,
        workspace_bucket=_env("WORKSPACE_BUCKET"),
        workspace_scratch_dir=_env("WORKSPACE_SCRATCH_DIR", "/tmp/siliconcrew-scratch"),
        persistence_engine=persistence_engine,
        database_url=_env("DATABASE_URL"),
        llm_key_engine=llm_key_engine,
        kms_key_uri=_env("KMS_KEY_URI"),
        hosted_gemini_model=_env("HOSTED_GEMINI_MODEL", "gemini-3.5-flash"),
        hosted_gemini_key=_env("HOSTED_GEMINI_KEY"),
        synth_runs_per_day=_int_env("SYNTH_RUNS_PER_DAY", 20),
        synth_compute_minutes_per_month=_int_env("SYNTH_COMPUTE_MINUTES_PER_MONTH", 600),
        synth_max_concurrent_per_user=_int_env("SYNTH_MAX_CONCURRENT_PER_USER", 5),
        synth_queue_global_workers=_int_env("SYNTH_QUEUE_GLOBAL_WORKERS", 16),
        num_cores=_int_env("ORFS_NUM_CORES", 4),
        dev_insecure_auth=_flag("SILICONCREW_DEV_INSECURE_AUTH", default=False),
        test_bearer_token=_env("SILICONCREW_TEST_BEARER_TOKEN"),
        # Accept either the new flag or the reference's ENABLE_CODEX_RUNTIME.
        codex_enabled=_flag("CODEX_ENABLED", default=False) or _flag("ENABLE_CODEX_RUNTIME", default=False),
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
        # one tenant's backlog cannot starve others while still allowing bounded
        # same-user parallel synths across multiple sessions.
        from src.platform_engines.job_queue import ContextUserExecutor, PerUserJobQueue
        from src.tools import synthesis_manager

        synthesis_manager.set_job_executor(
            ContextUserExecutor(
                PerUserJobQueue(
                    global_workers=max(1, settings.synth_queue_global_workers),
                    per_user_limit=max(1, settings.synth_max_concurrent_per_user),
                )
            )
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
