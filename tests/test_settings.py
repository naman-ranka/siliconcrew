from src.platform_engines.settings import get_settings, reset_settings_cache


def _clear_synth_governance_env(monkeypatch):
    for name in (
        "SYNTH_RUNS_PER_DAY",
        "SYNTH_COMPUTE_MINUTES_PER_MONTH",
        "SYNTH_MAX_CONCURRENT_PER_USER",
        "SYNTH_QUEUE_GLOBAL_WORKERS",
    ):
        monkeypatch.delenv(name, raising=False)


def _clear_mcp_auth_env(monkeypatch):
    for name in (
        "WORKOS_ISSUER",
        "WORKOS_JWKS_URL",
        "WORKOS_AUTHKIT_DOMAIN",
        "MCP_AUTHORIZATION_SERVER",
        "MCP_ISSUER",
        "MCP_JWKS_URL",
        "MCP_SCOPES_SUPPORTED",
    ):
        monkeypatch.delenv(name, raising=False)


def test_workos_defaults_derive_authkit_user_management_issuer(monkeypatch):
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_01ABC")
    _clear_mcp_auth_env(monkeypatch)
    reset_settings_cache()
    try:
        settings = get_settings()
    finally:
        reset_settings_cache()

    assert settings.workos_issuer == "https://api.workos.com/user_management/client_01ABC"
    assert settings.workos_jwks_url == "https://api.workos.com/sso/jwks/client_01ABC"
    assert settings.mcp_authorization_server == settings.workos_issuer
    assert settings.mcp_issuer == settings.workos_issuer
    assert settings.mcp_jwks_url == settings.workos_jwks_url
    assert settings.mcp_scopes_supported == ("mcp",)


def test_workos_issuer_override_wins(monkeypatch):
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_01ABC")
    monkeypatch.setenv("WORKOS_ISSUER", "https://auth.example.com/")
    monkeypatch.setenv("WORKOS_JWKS_URL", "https://jwks.example.com")
    monkeypatch.delenv("WORKOS_AUTHKIT_DOMAIN", raising=False)
    monkeypatch.delenv("MCP_AUTHORIZATION_SERVER", raising=False)
    monkeypatch.delenv("MCP_ISSUER", raising=False)
    monkeypatch.delenv("MCP_JWKS_URL", raising=False)
    reset_settings_cache()
    try:
        settings = get_settings()
    finally:
        reset_settings_cache()

    assert settings.workos_issuer == "https://auth.example.com/"
    assert settings.workos_jwks_url == "https://jwks.example.com"
    assert settings.mcp_issuer == "https://auth.example.com/"


def test_authkit_domain_drives_mcp_oauth_profile_without_changing_web_verifier(monkeypatch):
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_01ABC")
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "https://tenant.authkit.app/")
    monkeypatch.delenv("MCP_AUTHORIZATION_SERVER", raising=False)
    monkeypatch.delenv("MCP_ISSUER", raising=False)
    monkeypatch.delenv("MCP_JWKS_URL", raising=False)
    monkeypatch.delenv("MCP_SCOPES_SUPPORTED", raising=False)
    reset_settings_cache()
    try:
        settings = get_settings()
    finally:
        reset_settings_cache()

    assert settings.workos_issuer == "https://api.workos.com/user_management/client_01ABC"
    assert settings.workos_jwks_url == "https://api.workos.com/sso/jwks/client_01ABC"
    assert settings.workos_authkit_domain == "https://tenant.authkit.app"
    assert settings.mcp_authorization_server == "https://tenant.authkit.app"
    assert settings.mcp_issuer == "https://tenant.authkit.app"
    assert settings.mcp_jwks_url == "https://tenant.authkit.app/oauth2/jwks"
    assert settings.mcp_scopes_supported == ("openid", "email", "profile", "offline_access")


def test_mcp_oauth_overrides_win(monkeypatch):
    monkeypatch.setenv("WORKOS_CLIENT_ID", "client_01ABC")
    monkeypatch.setenv("WORKOS_AUTHKIT_DOMAIN", "https://tenant.authkit.app")
    monkeypatch.setenv("MCP_AUTHORIZATION_SERVER", "https://as.example")
    monkeypatch.setenv("MCP_ISSUER", "https://issuer.example")
    monkeypatch.setenv("MCP_JWKS_URL", "https://issuer.example/jwks")
    monkeypatch.setenv("MCP_SCOPES_SUPPORTED", "read write")
    reset_settings_cache()
    try:
        settings = get_settings()
    finally:
        reset_settings_cache()

    assert settings.mcp_authorization_server == "https://as.example"
    assert settings.mcp_issuer == "https://issuer.example"
    assert settings.mcp_jwks_url == "https://issuer.example/jwks"
    assert settings.mcp_scopes_supported == ("read", "write")


def test_synth_governance_defaults_and_overrides(monkeypatch):
    _clear_synth_governance_env(monkeypatch)
    reset_settings_cache()
    try:
        defaults = get_settings()
    finally:
        reset_settings_cache()

    assert defaults.synth_runs_per_day == 20
    assert defaults.synth_compute_minutes_per_month == 600
    assert defaults.synth_max_concurrent_per_user == 5
    assert defaults.synth_queue_global_workers == 16

    monkeypatch.setenv("SYNTH_RUNS_PER_DAY", "7")
    monkeypatch.setenv("SYNTH_COMPUTE_MINUTES_PER_MONTH", "90")
    monkeypatch.setenv("SYNTH_MAX_CONCURRENT_PER_USER", "3")
    monkeypatch.setenv("SYNTH_QUEUE_GLOBAL_WORKERS", "11")
    reset_settings_cache()
    try:
        overridden = get_settings()
    finally:
        reset_settings_cache()

    assert overridden.synth_runs_per_day == 7
    assert overridden.synth_compute_minutes_per_month == 90
    assert overridden.synth_max_concurrent_per_user == 3
    assert overridden.synth_queue_global_workers == 11
