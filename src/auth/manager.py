from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import base64
import hashlib
import secrets
import threading
import time
from .storage import AuthStorage
from .models import AuthProfile
from .security import SecurityManager
from .oauth import OAuthFactory
import os

class AuthManager:
    _oauth_states: Dict[str, Dict[str, Any]] = {}
    _state_lock = threading.Lock()
    _state_ttl_seconds = 600

    def __init__(self, db_path: str = None):
        if db_path is None:
            home = os.path.expanduser("~")
            db_path = os.path.join(home, ".siliconcrew", "state.db")

        self.security = SecurityManager()
        self.storage = AuthStorage(db_path, self.security)

    @staticmethod
    def _normalize_provider(provider: str) -> str:
        p = provider.lower().strip()
        if p in {"google", "gemini"}:
            return "gemini"
        if p in {"openai-codex", "openai_codex"}:
            return "openai"
        return p

    @staticmethod
    def _oauth_provider_for(provider: str) -> str:
        p = provider.lower().strip()
        if p == "gemini":
            return "google"
        if p == "openai":
            return "openai-codex"
        return p

    @staticmethod
    def _pkce_challenge(code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def create_oauth_session(self, provider: str, profile_id: str, redirect_uri: str) -> Dict[str, str]:
        """
        Create short-lived OAuth state and PKCE verifier/challenge.
        """
        normalized_provider = self._normalize_provider(provider)
        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        code_challenge = self._pkce_challenge(code_verifier)

        with self._state_lock:
            self._oauth_states[state] = {
                "provider": normalized_provider,
                "profile_id": profile_id,
                "redirect_uri": redirect_uri,
                "code_verifier": code_verifier,
                "expires_at": time.time() + self._state_ttl_seconds,
            }

        return {
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

    def consume_oauth_session(self, state: str, provider: str) -> Dict[str, Any]:
        """
        Atomically validate + consume OAuth state.
        """
        normalized_provider = self._normalize_provider(provider)
        with self._state_lock:
            self._cleanup_expired_states_locked()
            payload = self._oauth_states.pop(state, None)

        if not payload:
            raise ValueError("Invalid or expired OAuth state")
        if payload["provider"] != normalized_provider:
            raise ValueError("OAuth state/provider mismatch")
        return payload

    def _cleanup_expired_states_locked(self) -> None:
        now = time.time()
        expired = [k for k, v in self._oauth_states.items() if v.get("expires_at", 0) < now]
        for k in expired:
            self._oauth_states.pop(k, None)

    def add_api_key(self, provider: str, key: str, profile_id: str = "default"):
        """Save a simple API key profile."""
        profile = AuthProfile(
            provider=self._normalize_provider(provider),
            profile_id=profile_id,
            type="api_key",
            access_token=key
        )
        self.storage.save_profile(profile)

    def add_oauth_profile(self, provider: str, data: dict, profile_id: str = "default"):
        """Save an OAuth profile."""
        expires_at = None
        if "expires_in" in data:
            expires_at = datetime.now() + timedelta(seconds=data["expires_in"])

        profile = AuthProfile(
            provider=self._normalize_provider(provider),
            profile_id=profile_id,
            type="oauth",
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            meta=data.get("meta")
        )
        self.storage.save_profile(profile)

    async def aget_token(self, provider: str, profile_id: str = "default") -> Optional[str]:
        """
        Get a usable access token asynchronously. Handles refresh if expired.
        """
        normalized_provider = self._normalize_provider(provider)
        profile = self.storage.get_profile(normalized_provider, profile_id)
        if not profile:
            # Fallback for default profile if explicit profile not found?
            # Ideally handled by caller or fallback logic.
            if profile_id != "default":
                profile = self.storage.get_profile(normalized_provider, "default")

            if not profile:
                return None

        if profile.type == "api_key":
            return profile.access_token

        if profile.type == "oauth":
            # Check expiry with buffer (e.g. 5 minutes)
            if profile.expires_at and profile.expires_at < datetime.now() + timedelta(minutes=5):
                try:
                    return await self._refresh_profile(profile)
                except Exception as e:
                    print(f"Error refreshing token for {provider}: {e}")
                    return None # Failover?

        return profile.access_token

    async def _refresh_profile(self, profile: AuthProfile) -> str:
        if not profile.refresh_token:
            raise ValueError("No refresh token available")

        oauth = OAuthFactory.get_provider(self._oauth_provider_for(profile.provider))
        data = await oauth.refresh_token(profile.refresh_token)

        # Update profile
        profile.access_token = data["access_token"]
        if "refresh_token" in data and data["refresh_token"]:
            profile.refresh_token = data["refresh_token"]

        if "expires_in" in data:
            profile.expires_at = datetime.now() + timedelta(seconds=data["expires_in"])

        profile.updated_at = datetime.now()
        self.storage.save_profile(profile)

        return profile.access_token

    def list_profiles(self, provider: str = None) -> List[dict]:
        profiles = self.storage.list_profiles(provider)
        # Return safe summary (no tokens)
        return [
            {
                "provider": p.provider,
                "profile_id": p.profile_id,
                "type": p.type,
                "is_active": p.is_active,
                "updated_at": str(p.updated_at)
            }
            for p in profiles
        ]
