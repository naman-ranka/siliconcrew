import pytest

from src.auth.manager import AuthManager


def _isolated_manager(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    db_path = tmp_path / "state.db"
    return AuthManager(db_path=str(db_path))


@pytest.mark.asyncio
async def test_google_alias_normalizes_to_gemini(tmp_path, monkeypatch):
    mgr = _isolated_manager(tmp_path, monkeypatch)
    mgr.add_api_key("google", "abc123", profile_id="default")
    token = await mgr.aget_token("gemini", profile_id="default")
    assert token == "abc123"


def test_oauth_state_pkce_roundtrip(tmp_path, monkeypatch):
    mgr = _isolated_manager(tmp_path, monkeypatch)
    created = mgr.create_oauth_session(
        provider="google",
        profile_id="default",
        redirect_uri="http://localhost:3000/auth/callback?provider=google",
    )

    assert created["state"]
    assert created["code_challenge"]
    assert created["code_challenge_method"] == "S256"

    session = mgr.consume_oauth_session(created["state"], provider="google")
    assert session["profile_id"] == "default"
    assert session["provider"] == "gemini"
    assert session["code_verifier"]
    assert session["redirect_uri"].startswith("http://localhost:3000/auth/callback")

    with pytest.raises(ValueError):
        mgr.consume_oauth_session(created["state"], provider="google")
