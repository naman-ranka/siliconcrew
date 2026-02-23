from typing import Optional, List
from datetime import datetime, timedelta
import asyncio
from .storage import AuthStorage
from .models import AuthProfile
from .security import SecurityManager
from .oauth import OAuthFactory
import os

class AuthManager:
    def __init__(self, db_path: str = None):
        if db_path is None:
            home = os.path.expanduser("~")
            db_path = os.path.join(home, ".siliconcrew", "state.db")

        self.security = SecurityManager()
        self.storage = AuthStorage(db_path, self.security)

    def add_api_key(self, provider: str, key: str, profile_id: str = "default"):
        """Save a simple API key profile."""
        profile = AuthProfile(
            provider=provider,
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
            provider=provider,
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
        profile = self.storage.get_profile(provider, profile_id)
        if not profile:
            # Fallback for default profile if explicit profile not found?
            # Ideally handled by caller or fallback logic.
            if profile_id != "default":
                profile = self.storage.get_profile(provider, "default")

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

        oauth = OAuthFactory.get_provider(profile.provider)
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
