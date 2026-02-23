from typing import Optional, List
from .storage import AuthStorage
from .models import AuthProfile
from .security import SecurityManager
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

    def get_token(self, provider: str, profile_id: str = "default") -> Optional[str]:
        """
        Get a usable access token.
        TODO: Handle OAuth refresh logic here.
        """
        profile = self.storage.get_profile(provider, profile_id)
        if not profile:
            return None

        if profile.type == "api_key":
            return profile.access_token

        # Placeholder for OAuth logic
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
