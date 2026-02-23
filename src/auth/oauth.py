import os
import httpx
from abc import ABC, abstractmethod
from typing import Dict, Any, Tuple, Optional
from datetime import datetime, timedelta

class OAuthProvider(ABC):
    @abstractmethod
    def get_auth_url(self, redirect_uri: str, state: str = None) -> str:
        pass

    @abstractmethod
    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Returns dict with access_token, refresh_token, expires_in (seconds), meta"""
        pass

    @abstractmethod
    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        """Returns dict with access_token, expires_in, and optional new refresh_token"""
        pass

class GoogleOAuthProvider(OAuthProvider):
    def __init__(self):
        self.client_id = os.environ.get("GOOGLE_CLIENT_ID")
        self.client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
        self.auth_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
        self.token_endpoint = "https://oauth2.googleapis.com/token"

    def get_auth_url(self, redirect_uri: str, state: str = None) -> str:
        if not self.client_id:
            raise ValueError("GOOGLE_CLIENT_ID not set")

        params = [
            f"client_id={self.client_id}",
            f"redirect_uri={redirect_uri}",
            "response_type=code",
            "scope=https://www.googleapis.com/auth/generative-language.retriever", # Example scope
            "access_type=offline",
            "prompt=consent"
        ]
        if state:
            params.append(f"state={state}")

        return f"{self.auth_endpoint}?{'&'.join(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_endpoint, data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri
            })
            resp.raise_for_status()
            data = resp.json()

            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in", 3600),
                "meta": {"scope": data.get("scope")}
            }

    async def refresh_token(self, refresh_token: str) -> Dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(self.token_endpoint, data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token"
            })
            resp.raise_for_status()
            data = resp.json()

            return {
                "access_token": data["access_token"],
                "expires_in": data.get("expires_in", 3600),
                # Google sometimes rotates refresh tokens
                "refresh_token": data.get("refresh_token")
            }

class OAuthFactory:
    _providers = {
        "google": GoogleOAuthProvider
    }

    @classmethod
    def get_provider(cls, name: str) -> OAuthProvider:
        provider_cls = cls._providers.get(name.lower())
        if not provider_cls:
            raise ValueError(f"Provider {name} not supported")
        return provider_cls()
